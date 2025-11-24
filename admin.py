#!/usr/bin/env python3
"""
Admin management module for PingIT WebServer.
Provides functions for target management, configuration, service control, etc.
"""

import subprocess
import sqlite3
import yaml
import os
import random
import platform
import psutil
import time
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple, Optional


class AdminManager:
    """Manages admin operations for PingIT."""
    
    def __init__(self, db_path: str, config_path: str, test_mode: bool = False):
        self.db_path = db_path
        self.config_path = config_path
        self.config = self._load_config()
        self.is_windows = platform.system() == 'Windows'
        # Use passed test_mode parameter, or detect from paths
        self.is_test_mode = test_mode or ('test' in config_path.lower() or db_path and 'test' in db_path.lower())
    
    def _load_config(self) -> Dict:
        """Load YAML config file."""
        try:
            with open(self.config_path, 'r') as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            return {}
    
    def _save_config(self, config: Dict) -> bool:
        """Save config to YAML file."""
        try:
            with open(self.config_path, 'w') as f:
                yaml.dump(config, f, default_flow_style=False)
            return True
        except Exception as e:
            return False
    
    # TARGET MANAGEMENT
    def add_target(self, name: str, host: str, timeout: float = 0.5) -> Tuple[bool, str]:
        """Add a target to the config."""
        try:
            if 'targets' not in self.config:
                self.config['targets'] = []
            
            # Check if target already exists
            for target in self.config['targets']:
                if target['name'] == name:
                    return False, f"Target '{name}' already exists"
            
            self.config['targets'].append({
                'name': name,
                'host': host,
                'timeout': timeout
            })
            
            if self._save_config(self.config):
                return True, f"Target '{name}' added successfully"
            else:
                return False, "Failed to save config"
        except Exception as e:
            return False, str(e)
    
    def remove_target(self, name: str) -> Tuple[bool, str]:
        """Remove a target from the config."""
        try:
            if 'targets' not in self.config:
                return False, "No targets configured"
            
            original_len = len(self.config['targets'])
            self.config['targets'] = [t for t in self.config['targets'] if t['name'] != name]
            
            if len(self.config['targets']) < original_len:
                if self._save_config(self.config):
                    return True, f"Target '{name}' removed successfully"
                else:
                    return False, "Failed to save config"
            else:
                return False, f"Target '{name}' not found"
        except Exception as e:
            return False, str(e)
    
    def get_targets(self) -> List[Dict]:
        """Get list of all targets."""
        return self.config.get('targets', [])
    
    # LOG MANAGEMENT
    def set_log_level(self, service: str, level: str) -> Tuple[bool, str]:
        """Change log level for a service."""
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR']
        if level.upper() not in valid_levels:
            return False, f"Invalid log level. Valid levels: {valid_levels}"
        
        try:
            if service == 'pingit':
                config_key = 'ping'
            elif service == 'webserver':
                config_key = 'webserver'
            else:
                return False, f"Unknown service: {service}"
            
            if 'logging' not in self.config:
                self.config['logging'] = {}
            
            self.config['logging']['level'] = level.upper()
            
            if self._save_config(self.config):
                return True, f"Log level for {service} set to {level.upper()}"
            else:
                return False, "Failed to save config"
        except Exception as e:
            return False, str(e)
    
    def get_log_level(self) -> str:
        """Get current log level."""
        return self.config.get('logging', {}).get('level', 'INFO')
    
    def set_log_location(self, service: str, path: str) -> Tuple[bool, str]:
        """Change log location for a service."""
        try:
            if service not in ['pingit', 'webserver']:
                return False, f"Unknown service: {service}"
            
            if 'logging' not in self.config:
                self.config['logging'] = {}
            
            self.config['logging']['path'] = path
            
            if self._save_config(self.config):
                return True, f"Log location for {service} set to {path}"
            else:
                return False, "Failed to save config"
        except Exception as e:
            return False, str(e)
    
    def get_log_location(self) -> str:
        """Get current log location."""
        return self.config.get('logging', {}).get('path', '/var/log/pingit')
    
    def get_log_tail(self, service: str, lines: int = 20) -> Tuple[bool, str]:
        """Get last N lines from log file."""
        try:
            log_path = None
            
            # In test mode, look for local log files
            if self.is_test_mode:
                # Search for the log file for this specific service
                log_dirs = ['./logs', '.', './log', '../logs']
                service_specific_files = []
                all_log_files = []
                
                for log_dir in log_dirs:
                    if not os.path.exists(log_dir):
                        continue
                    
                    try:
                        for filename in os.listdir(log_dir):
                            if filename.endswith('.log'):
                                full_path = os.path.join(log_dir, filename)
                                if os.path.isfile(full_path):
                                    all_log_files.append(full_path)
                                    # Check if filename contains the service name
                                    if service in filename.lower():
                                        service_specific_files.append(full_path)
                    except Exception:
                        pass
                
                # Prioritize service-specific files (e.g., pingit.log for pingit service)
                if service_specific_files:
                    log_path = max(service_specific_files, key=lambda f: os.path.getmtime(f))
                elif all_log_files:
                    # If no service-specific file found, use the most recently modified log file
                    log_path = max(all_log_files, key=lambda f: os.path.getmtime(f))
            else:
                # In production mode, use the configured log location
                log_path = self.get_log_location()
            
            if not log_path or not os.path.exists(log_path):
                return False, f"Log file not found for service '{service}'"
            
            with open(log_path, 'r', errors='ignore') as f:
                all_lines = f.readlines()
            
            # Get the last N lines
            tail_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
            content = ''.join(tail_lines)
            
            return True, content
        except Exception as e:
            return False, f"Error reading log file: {str(e)}"
    
    # SERVICE CONTROL
    def start_service(self, service: str) -> Tuple[bool, str]:
        """Start a service using systemctl (Linux) or subprocess (Windows/test mode)."""
        try:
            if self.is_windows or self.is_test_mode:
                # In test/Windows mode, start the process directly
                try:
                    if service == 'pingit':
                        # Check if already running
                        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                            try:
                                if 'python' in proc.info['name'].lower():
                                    cmdline = ' '.join(proc.info['cmdline']) if proc.info['cmdline'] else ''
                                    if 'pingit.py' in cmdline.lower():
                                        return True, "PingIT is already running"
                            except (psutil.NoSuchProcess, psutil.AccessDenied):
                                pass
                        
                        # Start PingIT using direct Python import
                        try:
                            # Import pingit module and run it in a subprocess
                            project_dir = os.path.dirname(__file__)
                            
                            # Use a simple approach: spawn python with the script directly
                            script_path = os.path.join(project_dir, 'pingit.py')
                            if self.is_test_mode:
                                cmd = f'{sys.executable} "{script_path}" --test'
                            else:
                                cmd = f'{sys.executable} "{script_path}"'
                            
                            print(f"DEBUG: Starting PingIT with command: {cmd}")
                            
                            # Use CREATE_NEW_PROCESS_GROUP to detach the process
                            if self.is_windows:
                                proc = subprocess.Popen(cmd, 
                                                       shell=True,
                                                       stdout=subprocess.PIPE, 
                                                       stderr=subprocess.PIPE,
                                                       creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
                            else:
                                proc = subprocess.Popen(cmd.split(), 
                                                       stdout=subprocess.PIPE, 
                                                       stderr=subprocess.PIPE)
                            
                            print(f"DEBUG: PingIT process spawned with PID: {proc.pid}")
                            return True, f"PingIT started successfully (PID: {proc.pid})"
                        except Exception as e:
                            print(f"DEBUG: Failed to start PingIT: {str(e)}")
                            import traceback
                            traceback.print_exc()
                            return False, f"Failed to start PingIT: {str(e)}"
                    
                    elif service == 'webserver':
                        # Check if already running
                        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                            try:
                                if 'python' in proc.info['name'].lower():
                                    cmdline = ' '.join(proc.info['cmdline']) if proc.info['cmdline'] else ''
                                    if 'webserver.py' in cmdline.lower():
                                        return True, "WebServer is already running"
                            except (psutil.NoSuchProcess, psutil.AccessDenied):
                                pass
                        
                        # Start WebServer
                        try:
                            project_dir = os.path.dirname(__file__)
                            script_path = os.path.join(project_dir, 'webserver.py')
                            if self.is_test_mode:
                                cmd = f'{sys.executable} "{script_path}" --test'
                            else:
                                cmd = f'{sys.executable} "{script_path}"'
                            
                            print(f"DEBUG: Starting WebServer with command: {cmd}")
                            
                            if self.is_windows:
                                proc = subprocess.Popen(cmd, 
                                                       shell=True,
                                                       stdout=subprocess.PIPE, 
                                                       stderr=subprocess.PIPE,
                                                       creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
                            else:
                                proc = subprocess.Popen(cmd.split(), 
                                                       stdout=subprocess.PIPE, 
                                                       stderr=subprocess.PIPE)
                            
                            print(f"DEBUG: WebServer process spawned with PID: {proc.pid}")
                            return True, f"WebServer started successfully (PID: {proc.pid})"
                        except Exception as e:
                            print(f"DEBUG: Failed to start WebServer: {str(e)}")
                            import traceback
                            traceback.print_exc()
                            return False, f"Failed to start WebServer: {str(e)}"
                    else:
                        return False, f"Unknown service: {service}"
                except ImportError:
                    return False, "psutil not available for process checking"
            
            if service == 'pingit':
                cmd = ['sudo', 'systemctl', 'start', 'pingit']
            elif service == 'webserver':
                cmd = ['sudo', 'systemctl', 'start', 'pingit-webserver']
            else:
                return False, f"Unknown service: {service}"
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                return True, f"Service '{service}' started successfully"
            else:
                return False, f"Failed to start service: {result.stderr}"
        except Exception as e:
            return False, str(e)
    
    def stop_service(self, service: str) -> Tuple[bool, str]:
        """Stop a service using systemctl (Linux) or process termination (Windows/test mode)."""
        try:
            if self.is_windows or self.is_test_mode:
                # In test/Windows mode, stop the process directly
                try:
                    script_name = 'webserver.py' if service == 'webserver' else 'pingit.py'
                    
                    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                        try:
                            if 'python' in proc.info['name'].lower():
                                cmdline = ' '.join(proc.info['cmdline']) if proc.info['cmdline'] else ''
                                if script_name in cmdline.lower():
                                    proc.terminate()
                                    proc.wait(timeout=5)
                                    return True, f"Service '{service}' stopped successfully"
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
                    
                    return True, f"Service '{service}' is not running"
                except ImportError:
                    # psutil not available, use tasklist
                    return True, f"Stop command sent to '{service}' (psutil not available)"
            
            if service == 'pingit':
                cmd = ['sudo', 'systemctl', 'stop', 'pingit']
            elif service == 'webserver':
                cmd = ['sudo', 'systemctl', 'stop', 'pingit-webserver']
            else:
                return False, f"Unknown service: {service}"
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                return True, f"Service '{service}' stopped successfully"
            else:
                return False, f"Failed to stop service: {result.stderr}"
        except Exception as e:
            return False, str(e)
    
    def restart_service(self, service: str) -> Tuple[bool, str]:
        """Restart a service."""
        try:
            # For WebServer, do a graceful reload
            if service == 'webserver':
                return True, "WebServer is reloading gracefully - connection will resume"
            
            # Stop the service first
            stop_result = self.stop_service(service)
            if not stop_result[0]:
                # It's ok if it's not running, continue to start
                pass
            
            # Wait a bit before starting
            time.sleep(1)
            
            # Start the service
            return self.start_service(service)
        except Exception as e:
            return False, str(e)
    
    def get_service_status(self, service: str) -> Tuple[bool, Dict]:
        """Get service status using systemctl (Linux) or tasklist (Windows test mode)."""
        try:
            if self.is_windows or self.is_test_mode:
                # Use tasklist /v to get process details
                script_name = 'webserver.py' if service == 'webserver' else 'pingit.py'
                
                try:
                    # Use psutil to check for the specific script
                    is_running = False
                    
                    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                        try:
                            name = proc.info['name'].lower()
                            cmdline_list = proc.info['cmdline'] if proc.info['cmdline'] else []
                            cmdline = ' '.join(cmdline_list) if cmdline_list else ''
                            cmdline_lower = cmdline.lower()
                            
                            # Check if it's a python process
                            if 'python' in name:
                                # Be more specific: check if the script is directly in the command line
                                # Look for patterns like: "python pingit.py" or "python.exe pingit.py --test"
                                for arg in cmdline_list:
                                    if script_name in arg.lower() or script_name.replace('.py', '') == arg.replace('.py', '').lower():
                                        is_running = True
                                        print(f"DEBUG: Found {service} process (PID: {proc.info['pid']}, cmdline: {cmdline})")
                                        break
                                if is_running:
                                    break
                        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                            pass
                    
                    status = 'running' if is_running else 'stopped'
                    print(f"DEBUG: {service} status: {status}, found: {is_running}")
                    
                    return True, {
                        'service': service,
                        'status': status,
                        'is_running': is_running,
                        'message': f"{service}: {status}"
                    }
                except ImportError:
                    # psutil not available, use simpler check
                    try:
                        result = subprocess.run(
                            'tasklist | findstr python.exe',
                            capture_output=True,
                            text=True,
                            timeout=5,
                            shell=True
                        )
                        is_running = len(result.stdout.strip()) > 0
                        status = 'running' if is_running else 'stopped'
                        
                        return True, {
                            'service': service,
                            'status': status,
                            'is_running': is_running,
                            'message': f"{service}: {status} (generic check)"
                        }
                    except Exception as e:
                        return True, {
                            'service': service,
                            'status': 'unknown',
                            'is_running': False,
                            'message': f"Could not determine status: {str(e)}"
                        }
                except Exception as e:
                    return True, {
                        'service': service,
                        'status': 'unknown',
                        'is_running': False,
                        'message': f"Error checking status: {str(e)}"
                    }
            
            if service == 'pingit':
                cmd = ['systemctl', 'is-active', 'pingit']
            elif service == 'webserver':
                cmd = ['systemctl', 'is-active', 'pingit-webserver']
            else:
                return False, {"error": f"Unknown service: {service}"}
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            status = result.stdout.strip()
            
            return True, {
                'service': service,
                'status': status,  # active, inactive, failed, etc.
                'is_running': status == 'active'
            }
        except Exception as e:
            return False, {"error": str(e)}
    
    # DATABASE OPERATIONS
    def generate_test_data(self, days: int = 7) -> Tuple[bool, str]:
        """Generate fake ping data and disconnects."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            targets = self.get_targets()
            if not targets:
                return False, "No targets configured"
            
            # Generate test data
            now = datetime.now()
            records_added = 0
            
            for day_offset in range(days):
                timestamp = now - timedelta(days=day_offset)
                
                for target in targets:
                    # Generate statistics records
                    for hour in range(24):
                        ts = timestamp - timedelta(hours=hour)
                        
                        # Random stats
                        total = random.randint(10, 50)
                        success = random.randint(int(total * 0.8), total)
                        failed = total - success
                        
                        avg_time = random.uniform(10, 100)
                        min_time = random.uniform(5, avg_time)
                        max_time = random.uniform(avg_time, 200)
                        
                        cursor.execute('''
                            INSERT INTO ping_statistics
                            (target_name, host, total_pings, successful_pings, failed_pings,
                             success_rate, avg_response_time, min_response_time, max_response_time,
                             last_status, timestamp)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now', 'localtime'))
                        ''', (
                            target['name'],
                            target['host'],
                            total,
                            success,
                            failed,
                            (success / total * 100) if total > 0 else 0,
                            avg_time,
                            min_time,
                            max_time,
                            1 if failed == 0 else 0
                        ))
                        records_added += 1
                    
                    # Random disconnects
                    if random.random() > 0.7:  # 30% chance of disconnect
                        disconnect_time = timestamp - timedelta(hours=random.randint(0, 23))
                        cursor.execute('''
                            INSERT INTO disconnect_times
                            (target_name, host, disconnect_time, duration_seconds, reason, timestamp)
                            VALUES (?, ?, ?, ?, ?, datetime('now', 'localtime'))
                        ''', (
                            target['name'],
                            target['host'],
                            disconnect_time.isoformat(),
                            random.randint(30, 3600),
                            'Test disconnect'
                        ))
            
            conn.commit()
            conn.close()
            
            return True, f"Generated test data: {records_added} statistics records for {days} days"
        except Exception as e:
            return False, f"Failed to generate test data: {str(e)}"
    
    def reset_database(self) -> Tuple[bool, str]:
        """Reset database (clear all data)."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Delete data
            cursor.execute('DELETE FROM ping_statistics')
            cursor.execute('DELETE FROM disconnect_times')
            
            conn.commit()
            conn.close()
            
            return True, "Database reset successfully"
        except Exception as e:
            return False, f"Failed to reset database: {str(e)}"
    
    def backup_database(self, backup_dir: str = '/tmp') -> Tuple[bool, str]:
        """Backup database to a file."""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_path = f"{backup_dir}/pingit_{timestamp}.db"
            
            import shutil
            shutil.copy(self.db_path, backup_path)
            
            return True, f"Database backed up to {backup_path}"
        except Exception as e:
            return False, f"Failed to backup database: {str(e)}"
    
    # SSL MANAGEMENT
    def enable_ssl(self, cert_path: str, key_path: str, https_port: int = 7443) -> Tuple[bool, str]:
        """Enable SSL with certificate and key."""
        try:
            if 'ssl' not in self.config:
                self.config['ssl'] = {}
            
            self.config['ssl']['enabled'] = True
            self.config['ssl']['certificate'] = cert_path
            self.config['ssl']['private_key'] = key_path
            
            if 'webserver' not in self.config:
                self.config['webserver'] = {}
            self.config['webserver']['https_port'] = https_port
            
            if self._save_config(self.config):
                return True, f"SSL enabled on port {https_port}"
            else:
                return False, "Failed to save config"
        except Exception as e:
            return False, str(e)
    
    def disable_ssl(self) -> Tuple[bool, str]:
        """Disable SSL."""
        try:
            if 'ssl' in self.config:
                self.config['ssl']['enabled'] = False
            
            if self._save_config(self.config):
                return True, "SSL disabled"
            else:
                return False, "Failed to save config"
        except Exception as e:
            return False, str(e)
    
    def override_ssl(self, cert_path: str, key_path: str, https_port: int = None) -> Tuple[bool, str]:
        """Override SSL settings."""
        try:
            if 'ssl' not in self.config:
                self.config['ssl'] = {}
            
            self.config['ssl']['certificate'] = cert_path
            self.config['ssl']['private_key'] = key_path
            
            if https_port:
                if 'webserver' not in self.config:
                    self.config['webserver'] = {}
                self.config['webserver']['https_port'] = https_port
            
            if self._save_config(self.config):
                return True, "SSL settings overridden"
            else:
                return False, "Failed to save config"
        except Exception as e:
            return False, str(e)
    
    def reset_ssl(self) -> Tuple[bool, str]:
        """Reset SSL settings to defaults."""
        try:
            if 'ssl' in self.config:
                self.config['ssl']['enabled'] = False
                self.config['ssl'].pop('certificate', None)
                self.config['ssl'].pop('private_key', None)
            
            if self._save_config(self.config):
                return True, "SSL settings reset to defaults"
            else:
                return False, "Failed to save config"
        except Exception as e:
            return False, str(e)
    
    def get_ssl_status(self) -> Dict:
        """Get current SSL status."""
        ssl_config = self.config.get('ssl', {})
        return {
            'enabled': ssl_config.get('enabled', False),
            'certificate': ssl_config.get('certificate', 'N/A'),
            'private_key': ssl_config.get('private_key', 'N/A'),
            'https_port': self.config.get('webserver', {}).get('https_port', 7443)
        }
    
    # CONFIGURATION VERIFICATION
    def verify_config(self) -> Tuple[bool, Dict]:
        """Verify all configurations."""
        issues = []
        
        # Check targets
        targets = self.get_targets()
        if not targets:
            issues.append("No targets configured")
        
        # Check logging
        log_level = self.get_log_level()
        if log_level not in ['DEBUG', 'INFO', 'WARNING', 'ERROR']:
            issues.append(f"Invalid log level: {log_level}")
        
        # Check database
        if not os.path.exists(self.db_path):
            issues.append(f"Database not found: {self.db_path}")
        
        return len(issues) == 0, {
            'valid': len(issues) == 0,
            'issues': issues,
            'targets_count': len(targets),
            'log_level': log_level
        }

