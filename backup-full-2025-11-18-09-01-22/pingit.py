#!/usr/bin/env python3
"""
PingIT - A ping service that stores metrics to SQLite database.
Runs as a systemd service on Linux.
"""

import logging
import time
import threading
import requests
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import sys

import yaml
import ecs_logging
import icmplib


# Configuration
DEFAULT_CONFIG_PATH = "/etc/pingit/pingit-config.yaml"
DEFAULT_LOG_PATH = "/var/log/pingit"
DEFAULT_PID_PATH = "/var/run/pingit.pid"

# Test mode - all files in same directory
TEST_MODE = False
TEST_DIR = None


class PingTarget:
    """Represents a ping target configuration."""
    
    def __init__(self, name: str, host: str, timeout: int = 5):
        self.name = name
        self.host = host
        self.timeout = timeout
    
    def __repr__(self):
        return f"PingTarget(name={self.name}, host={self.host})"




class TargetStats:
    """Statistics tracker for a ping target."""
    
    def __init__(self, target_name: str, host: str):
        self.target_name = target_name
        self.host = host
        self.total_pings = 0
        self.successful_pings = 0
        self.failed_pings = 0
        self.last_status = None  # None = unknown, 1 = up, 0 = down
        self.response_times = []
        self.ping_iteration = 0  # Counter for iterations
    
    def add_ping(self, success: bool, response_time: Optional[float]):
        """Record a ping result."""
        self.total_pings += 1
        self.ping_iteration += 1
        
        if success:
            self.successful_pings += 1
            if response_time:
                self.response_times.append(response_time)
        else:
            self.failed_pings += 1
    
    def get_statistics(self) -> dict:
        """Get current statistics."""
        success_rate = (self.successful_pings / self.total_pings * 100) if self.total_pings > 0 else 0
        avg_rt = sum(self.response_times) / len(self.response_times) if self.response_times else None
        min_rt = min(self.response_times) if self.response_times else None
        max_rt = max(self.response_times) if self.response_times else None
        
        return {
            'target_name': self.target_name,
            'host': self.host,
            'total_pings': self.total_pings,
            'successful_pings': self.successful_pings,
            'failed_pings': self.failed_pings,
            'success_rate': round(success_rate, 2),
            'avg_response_time': round(avg_rt, 2) if avg_rt else None,
            'min_response_time': round(min_rt, 2) if min_rt else None,
            'max_response_time': round(max_rt, 2) if max_rt else None,
            'last_status': self.last_status
        }
    
    def reset_iteration(self):
        """Reset iteration counter and statistics for next reporting cycle."""
        self.ping_iteration = 0
        self.total_pings = 0
        self.successful_pings = 0
        self.failed_pings = 0
        self.response_times = []


class PingService:
    """Main ping service."""
    
    def __init__(self, config_path: str = DEFAULT_CONFIG_PATH, test_mode: bool = False, 
                 test_dir: Optional[str] = None, report_to_log: bool = False, 
                 webserver_url: str = "http://localhost:7030"):
        self.test_mode = test_mode
        self.test_dir = test_dir
        self.report_to_log = report_to_log
        self.webserver_url = webserver_url
        self.log_level = "INFO"  # Default log level
        
        # In test mode, logs and pid file are local; in production, use system paths
        if self.test_mode:
            self.config_path = config_path
            self.log_dir = "."  # Current directory for logs
            self.pid_file = "./pingit.pid"
        else:
            self.config_path = config_path
            self.log_dir = DEFAULT_LOG_PATH
            self.pid_file = DEFAULT_PID_PATH
        
        # Setup logging with default level first
        self.logger = self._setup_logging(log_level=self.log_level)
        self.targets: List[PingTarget] = []
        self.target_stats: Dict[str, TargetStats] = {}
        self.running = False
        self.ping_interval = 60  # Global ping interval in seconds (default: 60)
        self.report_interval = 10  # Report every 10 iterations by default
        
        self.logger.debug(f"PingIT Service initializing... (test_mode={self.test_mode}, report_to_log={self.report_to_log})")
    
    def _setup_logging(self, log_level: str = "INFO") -> logging.Logger:
        """Set up ECS logging configuration."""
        log_dir = Path(self.log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        
        logger = logging.getLogger("pingit")
        log_level_obj = logging.DEBUG if log_level.upper() == "DEBUG" else logging.INFO
        logger.setLevel(log_level_obj)
        
        # Remove any existing handlers
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
        
        # Create log filename with date and time
        log_filename = f"pingit-{datetime.now().strftime('%Y-%m-%d-%H-%M-%S')}.log"
        
        # File handler with ECS formatter
        fh = logging.FileHandler(log_dir / log_filename)
        fh.setLevel(log_level_obj)
        fh.setFormatter(ecs_logging.StdlibFormatter())
        
        # Console handler with ECS formatter
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(log_level_obj)
        ch.setFormatter(ecs_logging.StdlibFormatter())
        
        logger.addHandler(fh)
        logger.addHandler(ch)
        
        return logger
    
    def load_config(self):
        """Load configuration from file."""
        config_path = Path(self.config_path)
        
        # In test mode, config file is optional
        if not config_path.exists():
            if self.test_mode:
                self.logger.info(f"Test mode: config file not found ({config_path}), using defaults")
                return
            else:
                self.logger.error(f"Config file not found: {config_path}")
                raise FileNotFoundError(f"Config file not found: {config_path}")
        
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
        except Exception as e:
            self.logger.error(f"Failed to load config: {e}")
            raise
        
        # Load and apply log level from config (even in test mode)
        new_log_level = config.get('logging', {}).get('level', 'INFO')
        if new_log_level.upper() != self.log_level.upper():
            self.log_level = new_log_level
            self.logger = self._setup_logging(log_level=self.log_level)
            self.logger.info(f"Log level changed to {self.log_level}")
        
        # Load and apply log path from config (in production mode)
        if not self.test_mode:
            config_log_path = config.get('logging', {}).get('path')
            if config_log_path and config_log_path != self.log_dir:
                self.log_dir = config_log_path
                self.logger = self._setup_logging(log_level=self.log_level)
                self.logger.info(f"Log path changed to {self.log_dir}")
        
        # Load webserver config path from pingit config
        webserver_config_path = config.get('webserver_config')
        if webserver_config_path and not self.test_mode:
            try:
                if Path(webserver_config_path).exists():
                    with open(webserver_config_path, 'r') as f:
                        webserver_config = yaml.safe_load(f) or {}
                        host = webserver_config.get('webserver', {}).get('host', 'localhost')
                        port = webserver_config.get('webserver', {}).get('port', 7030)
                        self.webserver_url = f"http://{host}:{port}"
                        self.logger.debug(f"Loaded webserver URL from config: {self.webserver_url}")
            except Exception as e:
                self.logger.warning(f"Could not load webserver config from {webserver_config_path}, using default: {e}")
        
        # Load global ping interval (only from config file if reading targets)
        self.ping_interval = config.get('ping', {}).get('interval', 60)
        
        # Parse targets (in test mode, only read targets from config)
        targets_config = config.get('targets', [])
        for target_config in targets_config:
            target = PingTarget(
                name=target_config['name'],
                host=target_config['host'],
                timeout=target_config.get('timeout', 5)
            )
            self.targets.append(target)
            self.target_stats[target.name] = TargetStats(target.name, target.host)
            self.logger.debug(f"Loaded target: {target}")
        
        # Load report interval
        self.report_interval = config.get('reporting', {}).get('interval', 10)
        
        if len(self.targets) > 0:
            self.logger.debug(f"Configuration loaded. Found {len(self.targets)} targets, "
                             f"ping interval: {self.ping_interval}s, report interval: {self.report_interval} iterations")
    
    def ping_target(self, target: PingTarget):
        """Ping a single target using ICMP."""
        self.logger.debug(f"Pinging {target.name} ({target.host})...")
        
        try:
            # Use icmplib for pure Python ICMP pinging
            host = icmplib.ping(target.host, count=1, timeout=target.timeout)
            success = host.is_alive
            response_time = host.avg_rtt if success else None
            error = None if success else "Host unreachable"
        
        except Exception as e:
            success = False
            response_time = None
            error = str(e)
            self.logger.error(f"Error pinging {target.name}: {e}")
        
        # Log result
        status = "✓" if success else "✗"
        time_str = f"{response_time:.2f}ms" if response_time else "N/A"
        self.logger.debug(f"[{status}] {target.name}: {time_str}")
        
        # Track statistics
        stats = self.target_stats[target.name]
        current_status = 1 if success else 0
        stats.add_ping(success, response_time)
        
        # Detect disconnection (status changed from up to down)
        # Note: last_status can be None (initial), 1 (up), or 0 (down)
        # We only report disconnect when transitioning TO down
        if stats.last_status != 0 and current_status == 0:
            self._report_disconnect(target, error)
        
        # Update status
        stats.last_status = current_status
        
        # Check if we should report statistics
        if stats.ping_iteration >= self.report_interval:
            self.logger.debug(f"Report cycle triggered for {target.name} "
                            f"({stats.ping_iteration}/{self.report_interval} iterations)")
            self._report_statistics(target)
            stats.reset_iteration()
    
    def _report_disconnect(self, target: PingTarget, reason: str):
        """Report a disconnection event."""
        disconnect_time = datetime.now().isoformat()
        
        self.logger.debug(f"Disconnect detected for {target.name} ({target.host}): {reason}")
        
        if self.report_to_log:
            self.logger.warning(f"DISCONNECT: {target.name} ({target.host}) - {reason}")
        else:
            # Report to webserver API
            try:
                payload = {
                    'target_name': target.name,
                    'host': target.host,
                    'disconnect_time': disconnect_time,
                    'reason': reason
                }
                self.logger.debug(f"Sending disconnect event to {self.webserver_url}/api/report/disconnects")
                response = requests.post(
                    f"{self.webserver_url}/api/report/disconnects",
                    json=payload,
                    timeout=5
                )
                if response.status_code == 201:
                    self.logger.info(f"✅ Successfully reported disconnect for {target.name} (HTTP {response.status_code})")
                else:
                    self.logger.warning(f"❌ Failed to report disconnect for {target.name}: HTTP {response.status_code}")
            except requests.exceptions.Timeout:
                self.logger.error(f"❌ Timeout reporting disconnect for {target.name}")
            except requests.exceptions.ConnectionError:
                self.logger.error(f"❌ Connection error reporting disconnect for {target.name}: Cannot reach {self.webserver_url}")
            except Exception as e:
                self.logger.error(f"❌ Error reporting disconnect for {target.name}: {type(e).__name__}: {e}")
    
    def _report_statistics(self, target: PingTarget):
        """Report statistics for a target."""
        stats = self.target_stats[target.name]
        stats_data = stats.get_statistics()
        
        self.logger.debug(f"Preparing to report statistics for {target.name}: "
                         f"{stats_data['total_pings']} pings, "
                         f"{stats_data['successful_pings']} success, "
                         f"{stats_data['success_rate']}% rate")
        
        if self.report_to_log:
            self.logger.debug(f"STATISTICS: {target.name} - Total: {stats_data['total_pings']}, "
                           f"Success: {stats_data['successful_pings']}, "
                           f"Failed: {stats_data['failed_pings']}, "
                           f"Rate: {stats_data['success_rate']}%")
        else:
            # Report to webserver API
            try:
                self.logger.debug(f"Sending POST to {self.webserver_url}/api/report/statistics")
                response = requests.post(
                    f"{self.webserver_url}/api/report/statistics",
                    json=stats_data,
                    timeout=5
                )
                if response.status_code == 201:
                    self.logger.debug(f"✅ Successfully reported statistics for {target.name} "
                                    f"(HTTP {response.status_code})")
                else:
                    self.logger.warning(f"❌ Failed to report statistics for {target.name}: "
                                      f"HTTP {response.status_code} - {response.text[:100]}")
            except requests.exceptions.Timeout:
                self.logger.error(f"❌ Timeout reporting statistics for {target.name} "
                                 f"to {self.webserver_url}")
            except requests.exceptions.ConnectionError as e:
                self.logger.error(f"❌ Connection error reporting statistics for {target.name}: "
                                 f"Cannot reach {self.webserver_url}")
            except Exception as e:
                self.logger.error(f"❌ Error reporting statistics for {target.name}: {type(e).__name__}: {e}")
    
    def start(self):
        """Start the ping service."""
        if self.running:
            self.logger.warning("Service already running")
            return
        
        self.logger.info("Starting PingIT service...")
        self.running = True
        self._run_scheduled()
    
    def _run_scheduled(self):
        """Run with simple sleep loop."""
        try:
            self.logger.debug(f"Starting ping loop with {self.ping_interval}s interval")
            
            # Keep running
            while self.running:
                # Ping all targets
                for target in self.targets:
                    if self.running:
                        self.ping_target(target)
                
                # Sleep for the configured interval
                time.sleep(self.ping_interval)
        
        except KeyboardInterrupt:
            self.logger.info("Received interrupt signal")
        except Exception as e:
            self.logger.error(f"Error in ping loop: {e}")
        finally:
            self.stop()
    
    def stop(self):
        """Stop the ping service."""
        self.logger.info("Stopping PingIT service...")
        self.running = False
        self.logger.info("PingIT service stopped")


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description='PingIT - Ping Service')
    parser.add_argument('--config', '-c', default=DEFAULT_CONFIG_PATH,
                       help='Path to configuration file')
    parser.add_argument('--test', '-t', action='store_true',
                       help='Run in test mode (logs locally, reads local pingit-config.yaml)')
    parser.add_argument('--log-reports', action='store_true',
                       help='Report disconnects and statistics to log instead of webserver API')
    
    args = parser.parse_args()
    
    # Create service
    test_mode = args.test
    report_to_log = args.log_reports
    
    # Use default config path if not in test mode, otherwise use local pingit-config.yaml
    if not test_mode:
        config_path = args.config
        webserver_config_path = "/etc/pingit/webserver-config.yaml"
    else:
        config_path = "./pingit-config.yaml"
        webserver_config_path = "./webserver-config.yaml"
    
    # Load webserver URL (will be updated from config if available)
    webserver_url = "http://localhost:7030"  # Default webserver URL
    
    service = PingService(config_path=config_path, test_mode=test_mode, test_dir=None,
                         report_to_log=report_to_log, webserver_url=webserver_url)
    
    try:
        service.load_config()
        service.start()
    except KeyboardInterrupt:
        service.logger.info("Interrupted by user")
    except Exception as e:
        service.logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()

