#!/usr/bin/env python3
"""
Comprehensive WebServer Test Suite for PingIT

This script:
1. Generates 2 months of dummy ping statistics and disconnect events
2. Starts the webserver in background
3. Tests all API endpoints (excluding admin dashboard)
4. Measures performance
5. Validates data series accuracy for three time slices: 1h, 24h, 30d
"""

import os
import sys
import json
import time
import sqlite3
import subprocess
import requests
import threading
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple
import statistics
import signal


class Colors:
    """ANSI color codes for terminal output."""
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


class TestConfig:
    """Test configuration constants."""
    PROJECT_DIR = Path(__file__).parent
    DB_PATH = PROJECT_DIR / "pingit_test.db"
    WEB_PORT = 7030
    WEB_URL = f"http://localhost:{WEB_PORT}"
    WEBSERVER_TIMEOUT = 30  # seconds to wait for webserver startup (large test DB)
    API_TIMEOUT = 5  # seconds timeout for API calls
    
    # Test data generation
    DAYS_BACK = 60  # 2 months of data
    NUM_TARGETS = 4
    TARGETS = [
        {'name': 'Amdocs Israel VPN', 'host': 'isr-fullvpn.amdocs.com'},
        {'name': 'Device at home', 'host': '10.10.0.44'},
        {'name': 'Home gateway', 'host': '10.10.0.138'},
        {'name': 'Google DNS', 'host': '8.8.8.8'},
    ]
    
    # Performance thresholds
    API_RESPONSE_TIME_THRESHOLD = 1.0  # seconds
    MEDIAN_RESPONSE_TIME_MS = 25.0


class TestResults:
    """Track and report test results."""
    
    def __init__(self):
        self.tests_passed = 0
        self.tests_failed = 0
        self.tests_total = 0
        self.performance_metrics = {}
        self.accuracy_results = {}
        self.errors = []
    
    def add_pass(self, test_name: str):
        """Record a passed test."""
        self.tests_passed += 1
        self.tests_total += 1
        print(f"{Colors.OKGREEN}✓{Colors.ENDC} {test_name}")
    
    def add_fail(self, test_name: str, error: str):
        """Record a failed test."""
        self.tests_failed += 1
        self.tests_total += 1
        self.errors.append(f"{test_name}: {error}")
        print(f"{Colors.FAIL}✗{Colors.ENDC} {test_name}: {error}")
    
    def print_summary(self):
        """Print test summary."""
        print(f"\n{Colors.BOLD}{'='*80}{Colors.ENDC}")
        print(f"{Colors.BOLD}TEST SUMMARY{Colors.ENDC}")
        print(f"{Colors.BOLD}{'='*80}{Colors.ENDC}\n")
        
        passed_color = Colors.OKGREEN if self.tests_passed > 0 else Colors.ENDC
        failed_color = Colors.FAIL if self.tests_failed > 0 else Colors.ENDC
        
        print(f"Total Tests: {self.tests_total}")
        print(f"{passed_color}Passed: {self.tests_passed}{Colors.ENDC}")
        print(f"{failed_color}Failed: {self.tests_failed}{Colors.ENDC}")
        
        if self.tests_total > 0:
            pass_rate = (self.tests_passed / self.tests_total) * 100
            print(f"Pass Rate: {pass_rate:.1f}%")
        
        if self.performance_metrics:
            print(f"\n{Colors.BOLD}PERFORMANCE METRICS{Colors.ENDC}")
            for metric_name, metric_data in self.performance_metrics.items():
                if isinstance(metric_data, (int, float)):
                    print(f"  {metric_name}: {metric_data:.3f}s")
                elif isinstance(metric_data, dict):
                    print(f"  {metric_name}:")
                    for key, value in metric_data.items():
                        if isinstance(value, (int, float)):
                            print(f"    {key}: {value:.3f}s")
        
        if self.accuracy_results:
            print(f"\n{Colors.BOLD}ACCURACY RESULTS{Colors.ENDC}")
            for slice_name, accuracy in self.accuracy_results.items():
                print(f"  {slice_name}: {accuracy:.1f}%")
        
        if self.errors:
            print(f"\n{Colors.BOLD}ERRORS{Colors.ENDC}")
            for error in self.errors:
                print(f"  {Colors.FAIL}• {error}{Colors.ENDC}")
        
        print(f"\n{Colors.BOLD}{'='*80}{Colors.ENDC}\n")
        
        return self.tests_failed == 0


class DummyDataGenerator:
    """Generate realistic dummy data for testing."""
    
    def __init__(self, db_path: Path, days_back: int = 60):
        self.db_path = db_path
        self.days_back = days_back
        self.conn = None
    
    def connect(self):
        """Connect to database."""
        if self.db_path.exists():
            self.db_path.unlink()
        
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
    
    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
    
    def create_schema(self):
        """Create database schema."""
        cursor = self.conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ping_statistics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_name TEXT NOT NULL,
                host TEXT NOT NULL,
                total_pings INTEGER NOT NULL,
                successful_pings INTEGER NOT NULL,
                failed_pings INTEGER NOT NULL,
                success_rate REAL NOT NULL,
                avg_response_time REAL,
                min_response_time REAL,
                max_response_time REAL,
                last_status INTEGER,
                timestamp INTEGER DEFAULT (CAST(STRFTIME('%s', 'now') * 1000 AS INTEGER)),
                UNIQUE(target_name, timestamp)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS disconnect_times (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_name TEXT NOT NULL,
                host TEXT NOT NULL,
                disconnect_time INTEGER NOT NULL,
                duration_seconds INTEGER,
                reason TEXT,
                timestamp INTEGER DEFAULT (CAST(STRFTIME('%s', 'now') * 1000 AS INTEGER))
            )
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_ping_statistics_target_timestamp 
            ON ping_statistics(target_name, timestamp)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_disconnect_times_target 
            ON disconnect_times(target_name, disconnect_time)
        ''')
        
        self.conn.commit()
    
    def generate_data(self) -> int:
        """Generate dummy data for the past days_back days."""
        cursor = self.conn.cursor()
        now = datetime.now()
        record_count = 0
        
        print(f"\n{Colors.OKCYAN}Generating {self.days_back} days of dummy data...{Colors.ENDC}")
        
        for target_idx, target in enumerate(TestConfig.TARGETS):
            target_name = target['name']
            host = target['host']
            
            print(f"  Generating data for {target_name}...", end='', flush=True)
            
            target_records = 0
            disconnect_records = 0
            
            # Generate data every 20 seconds over the past days_back days
            current_time = now - timedelta(days=self.days_back)
            end_time = now
            
            while current_time < end_time:
                # Convert to milliseconds since epoch
                timestamp_ms = int(current_time.timestamp() * 1000)
                
                # Random variations based on time of day and target
                hour = current_time.hour
                is_night = 22 <= hour or hour < 6
                
                # Generate realistic ping statistics
                if target_idx == 3:  # Google DNS - most reliable
                    success_rate = 99.5 if not is_night else 99.0
                    total_pings = 30
                    avg_response_time = 15.2
                else:  # Other targets - less reliable
                    success_rate = (95 + (5 * (hash(target_name + str(current_time.date())) % 100) / 100))
                    total_pings = 30
                    avg_response_time = 25.0 + (10 * (hash(target_name) % 10) / 10)
                
                # Add some variation
                minute_variation = (current_time.minute / 60.0) * 5  # ±5ms variation
                avg_response_time += minute_variation - 2.5
                
                successful_pings = int(total_pings * success_rate / 100)
                failed_pings = total_pings - successful_pings
                
                # Calculate min/max response times
                min_response_time = max(1, avg_response_time - 10)
                max_response_time = avg_response_time + 10
                
                last_status = 1 if failed_pings == 0 else 0
                
                try:
                    cursor.execute('''
                        INSERT INTO ping_statistics 
                        (target_name, host, total_pings, successful_pings, failed_pings,
                         success_rate, avg_response_time, min_response_time, max_response_time,
                         last_status, timestamp)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        target_name, host, total_pings, successful_pings, failed_pings,
                        success_rate, avg_response_time, min_response_time, max_response_time,
                        last_status, timestamp_ms
                    ))
                    target_records += 1
                    record_count += 1
                except sqlite3.IntegrityError:
                    pass  # Duplicate, skip
                
                # Occasionally add disconnect events
                if failed_pings > 0 and not (current_time.minute % 7):  # Every ~7 min
                    try:
                        duration = failed_pings * 2  # 2 seconds per failed ping
                        cursor.execute('''
                            INSERT INTO disconnect_times
                            (target_name, host, disconnect_time, duration_seconds, reason, timestamp)
                            VALUES (?, ?, ?, ?, ?, ?)
                        ''', (
                            target_name, host, timestamp_ms, duration,
                            'Connection timeout', timestamp_ms
                        ))
                        disconnect_records += 1
                        record_count += 1
                    except sqlite3.IntegrityError:
                        pass
                
                # Move to next interval (20 seconds)
                current_time += timedelta(seconds=20)
            
            print(f" {Colors.OKGREEN}{target_records} records + {disconnect_records} disconnects{Colors.ENDC}")
        
        self.conn.commit()
        print(f"{Colors.OKGREEN}✓{Colors.ENDC} Generated {record_count} total records\n")
        
        return record_count


class WebServerManager:
    """Manage webserver subprocess."""
    
    def __init__(self, db_path: Path):
        self.process = None
        self.db_path = db_path
        self.thread = None
    
    def start(self):
        """Start webserver in background."""
        print(f"{Colors.OKCYAN}Starting WebServer in background...{Colors.ENDC}")
        
        try:
            # Start webserver process
            cmd = [
                sys.executable, 'webserver.py', '--test'
            ]
            
            # Set environment variable to use test database
            env = os.environ.copy()
            
            self.process = subprocess.Popen(
                cmd,
                cwd=str(TestConfig.PROJECT_DIR),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                preexec_fn=None if sys.platform == 'win32' else lambda: None
            )
            
            # Wait for server to be ready
            return self._wait_for_startup()
        
        except Exception as e:
            print(f"{Colors.FAIL}✗ Failed to start WebServer: {e}{Colors.ENDC}")
            return False
    
    def _wait_for_startup(self, timeout: int = TestConfig.WEBSERVER_TIMEOUT) -> bool:
        """Wait for webserver to start and be responsive."""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                response = requests.get(f"{TestConfig.WEB_URL}/health", timeout=1)
                if response.status_code == 200:
                    print(f"{Colors.OKGREEN}✓{Colors.ENDC} WebServer started successfully")
                    return True
            except requests.ConnectionError:
                time.sleep(0.5)
            except Exception as e:
                time.sleep(0.5)
        
        print(f"{Colors.FAIL}✗ WebServer failed to start within {timeout}s{Colors.ENDC}")
        return False
    
    def stop(self):
        """Stop webserver."""
        if self.process:
            print(f"{Colors.OKCYAN}Stopping WebServer...{Colors.ENDC}")
            
            try:
                if sys.platform == 'win32':
                    self.process.terminate()
                else:
                    os.kill(self.process.pid, signal.SIGTERM)
                
                # Wait for process to terminate
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                
                print(f"{Colors.OKGREEN}✓{Colors.ENDC} WebServer stopped")
            except Exception as e:
                print(f"{Colors.FAIL}✗ Error stopping WebServer: {e}{Colors.ENDC}")


class APITestSuite:
    """Test WebServer API endpoints."""
    
    def __init__(self, results: TestResults):
        self.results = results
        self.session = requests.Session()
    
    def test_health_endpoint(self) -> bool:
        """Test /health endpoint."""
        try:
            start_time = time.time()
            response = self.session.get(
                f"{TestConfig.WEB_URL}/health",
                timeout=TestConfig.API_TIMEOUT
            )
            elapsed = time.time() - start_time
            
            if response.status_code == 200:
                data = response.json()
                if 'status' in data and data['status'] == 'healthy':
                    self._record_performance('health_endpoint', elapsed)
                    self.results.add_pass("Health endpoint")
                    return True
            
            self.results.add_fail("Health endpoint", f"Status code: {response.status_code}")
            return False
        
        except Exception as e:
            self.results.add_fail("Health endpoint", str(e))
            return False
    
    def test_api_data_1h(self) -> bool:
        """Test /api/data?range=1h endpoint."""
        return self._test_api_data_range('1h', '1 hour slice')
    
    def test_api_data_24h(self) -> bool:
        """Test /api/data?range=24h endpoint."""
        return self._test_api_data_range('24h', '24 hour slice')
    
    def test_api_data_30d(self) -> bool:
        """Test /api/data?range=30d endpoint."""
        return self._test_api_data_range('30d', '30 day slice')
    
    def _test_api_data_range(self, time_range: str, description: str) -> bool:
        """Test /api/data with specific time range."""
        try:
            start_time = time.time()
            response = self.session.get(
                f"{TestConfig.WEB_URL}/api/data?range={time_range}",
                timeout=TestConfig.API_TIMEOUT
            )
            elapsed = time.time() - start_time
            
            if response.status_code == 200:
                data = response.json()
                
                # Validate response structure
                required_fields = ['time_range', 'targets', 'disconnects', 'timeseries',
                                  'total_targets', 'total_disconnects', 'uptime_percentage']
                
                for field in required_fields:
                    if field not in data:
                        self.results.add_fail(
                            f"API data {description}",
                            f"Missing required field: {field}"
                        )
                        return False
                
                # Validate targets structure
                for target in data['targets']:
                    required_target_fields = ['name', 'host', 'pings', 'success_rate',
                                            'avg_response_time', 'status']
                    for field in required_target_fields:
                        if field not in target:
                            self.results.add_fail(
                                f"API data {description}",
                                f"Target missing field: {field}"
                            )
                            return False
                
                self._record_performance(f'api_data_{time_range}', elapsed)
                self.results.add_pass(f"API data {description}")
                return True
            else:
                self.results.add_fail(
                    f"API data {description}",
                    f"Status code: {response.status_code}"
                )
                return False
        
        except Exception as e:
            self.results.add_fail(f"API data {description}", str(e))
            return False
    
    def test_api_statistics_endpoint(self) -> bool:
        """Test /api/statistics/<target_name> endpoint."""
        try:
            target_name = TestConfig.TARGETS[0]['name']
            start_time = time.time()
            response = self.session.get(
                f"{TestConfig.WEB_URL}/api/statistics/{target_name}",
                timeout=TestConfig.API_TIMEOUT
            )
            elapsed = time.time() - start_time
            
            if response.status_code == 200:
                data = response.json()
                required_fields = ['target_name', 'host', 'total_pings', 'successful_pings',
                                  'failed_pings', 'success_rate', 'last_status']
                
                for field in required_fields:
                    if field not in data:
                        self.results.add_fail(
                            "Statistics endpoint",
                            f"Missing field: {field}"
                        )
                        return False
                
                self._record_performance('statistics_endpoint', elapsed)
                self.results.add_pass("Statistics endpoint")
                return True
            else:
                self.results.add_fail(
                    "Statistics endpoint",
                    f"Status code: {response.status_code}"
                )
                return False
        
        except Exception as e:
            self.results.add_fail("Statistics endpoint", str(e))
            return False
    
    def test_api_disconnects_endpoint(self) -> bool:
        """Test /api/disconnects/<target_name> endpoint."""
        try:
            target_name = TestConfig.TARGETS[0]['name']
            start_time = time.time()
            response = self.session.get(
                f"{TestConfig.WEB_URL}/api/disconnects/{target_name}",
                timeout=TestConfig.API_TIMEOUT
            )
            elapsed = time.time() - start_time
            
            if response.status_code == 200:
                data = response.json()
                required_fields = ['target_name', 'disconnect_count', 'disconnects']
                
                for field in required_fields:
                    if field not in data:
                        self.results.add_fail(
                            "Disconnects endpoint",
                            f"Missing field: {field}"
                        )
                        return False
                
                self._record_performance('disconnects_endpoint', elapsed)
                self.results.add_pass("Disconnects endpoint")
                return True
            else:
                self.results.add_fail(
                    "Disconnects endpoint",
                    f"Status code: {response.status_code}"
                )
                return False
        
        except Exception as e:
            self.results.add_fail("Disconnects endpoint", str(e))
            return False
    
    def test_metrics_endpoint(self) -> bool:
        """Test /metrics (Prometheus) endpoint."""
        try:
            start_time = time.time()
            response = self.session.get(
                f"{TestConfig.WEB_URL}/metrics",
                timeout=TestConfig.API_TIMEOUT
            )
            elapsed = time.time() - start_time
            
            if response.status_code == 200:
                content = response.text
                # Prometheus format should have HELP and TYPE comments
                if '# HELP' in content and '# TYPE' in content:
                    self._record_performance('metrics_endpoint', elapsed)
                    self.results.add_pass("Prometheus metrics endpoint")
                    return True
            
            self.results.add_fail(
                "Prometheus metrics endpoint",
                f"Invalid Prometheus format (status: {response.status_code})"
            )
            return False
        
        except Exception as e:
            self.results.add_fail("Prometheus metrics endpoint", str(e))
            return False
    
    def _record_performance(self, endpoint: str, elapsed: float):
        """Record API response time."""
        if endpoint not in self.results.performance_metrics:
            self.results.performance_metrics[endpoint] = elapsed
        else:
            # Keep track of multiple calls
            if not isinstance(self.results.performance_metrics[endpoint], list):
                self.results.performance_metrics[endpoint] = [self.results.performance_metrics[endpoint]]
            self.results.performance_metrics[endpoint].append(elapsed)


class AccuracyTestSuite:
    """Test data series accuracy for different time ranges."""
    
    def __init__(self, results: TestResults, db_path: Path):
        self.results = results
        self.db_path = db_path
    
    def validate_data_series(self) -> bool:
        """Validate data accuracy for all time ranges."""
        print(f"\n{Colors.OKCYAN}Validating data series accuracy...{Colors.ENDC}")
        
        time_ranges = [
            ('1h', 1, 'Last 1 hour'),
            ('24h', 24, 'Last 24 hours'),
            ('30d', 24 * 30, 'Last 30 days')
        ]
        
        all_passed = True
        
        for range_key, hours_back, description in time_ranges:
            if not self._validate_range(range_key, hours_back, description):
                all_passed = False
        
        return all_passed
    
    def _validate_range(self, range_key: str, hours_back: int, description: str) -> bool:
        """Validate a specific time range."""
        try:
            # Fetch data from API
            response = requests.get(
                f"{TestConfig.WEB_URL}/api/data?range={range_key}",
                timeout=TestConfig.API_TIMEOUT
            )
            
            if response.status_code != 200:
                self.results.add_fail(
                    f"Data series accuracy ({description})",
                    f"API returned status {response.status_code}"
                )
                return False
            
            api_data = response.json()
            
            # Validate against database
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cutoff_ms = int((datetime.now().timestamp() - (hours_back * 3600)) * 1000)
            tolerance_ms = 2000  # allow small clock drift/slop
            cutoff_with_slop = cutoff_ms - tolerance_ms
            
            # Get expected counts from database
            cursor.execute('''
                SELECT COUNT(*) as count FROM ping_statistics WHERE timestamp > ?
            ''', (cutoff_ms,))
            expected_stats_count = cursor.fetchone()['count']
            
            cursor.execute('''
                SELECT COUNT(*) as count FROM disconnect_times WHERE disconnect_time > ?
            ''', (cutoff_ms,))
            expected_disconnect_count = cursor.fetchone()['count']
            
            conn.close()
            
            # Validate response data
            total_targets = api_data.get('total_targets', 0)
            total_disconnect_events = api_data.get('total_disconnect_events', 0)
            
            # Check if we have data
            if expected_stats_count == 0:
                self.results.add_fail(
                    f"Data series accuracy ({description})",
                    "No data in database for this range"
                )
                return False
            
            # Calculate accuracy
            accuracy = 100.0  # Start at 100%
            
            # Validate targets have data
            if not api_data.get('targets'):
                self.results.add_fail(
                    f"Data series accuracy ({description})",
                    "No targets returned"
                )
                return False
            
            # Validate timeseries data exists
            if not api_data.get('timeseries'):
                self.results.add_fail(
                    f"Data series accuracy ({description})",
                    "No timeseries data returned"
                )
                return False

            # Validate API time range label
            if api_data.get('time_range') != range_key:
                self.results.add_fail(
                    f"Data series accuracy ({description})",
                    f"time_range mismatch: expected {range_key}, got {api_data.get('time_range')}"
                )
                return False

            # Ensure all timeseries points are within the requested window
            timeseries = api_data.get('timeseries', {})
            for target_name, series in timeseries.items():
                timestamps = series.get('timestamps', [])
                if not timestamps:
                    self.results.add_fail(
                        f"Data series accuracy ({description})",
                        f"No timestamps for target {target_name}"
                    )
                    return False
                if min(timestamps) < cutoff_with_slop:
                    self.results.add_fail(
                        f"Data series accuracy ({description})",
                        f"Timeseries includes data older than window for target {target_name}"
                    )
                    return False

            # Ensure disconnect markers are within the window
            for dc in api_data.get('disconnects', []):
                last_dc = dc.get('last_disconnect', 0)
                if last_dc < cutoff_with_slop:
                    self.results.add_fail(
                        f"Data series accuracy ({description})",
                        f"Disconnect data older than window for target {dc.get('name')}"
                    )
                    return False
            
            self.results.accuracy_results[description] = accuracy
            self.results.add_pass(f"Data series accuracy ({description})")
            return True
        
        except Exception as e:
            self.results.add_fail(f"Data series accuracy ({description})", str(e))
            return False


class PerformanceTestSuite:
    """Test webserver performance."""
    
    def __init__(self, results: TestResults):
        self.results = results
        self.session = requests.Session()
    
    def test_concurrent_requests(self, num_requests: int = 10) -> bool:
        """Test concurrent API requests."""
        print(f"\n{Colors.OKCYAN}Testing concurrent requests ({num_requests} requests)...{Colors.ENDC}")
        
        try:
            start_time = time.time()
            
            # Make multiple requests concurrently
            import concurrent.futures
            
            def make_request(i):
                try:
                    time_range = ['1h', '24h', '30d'][i % 3]
                    response = self.session.get(
                        f"{TestConfig.WEB_URL}/api/data?range={time_range}",
                        timeout=TestConfig.API_TIMEOUT
                    )
                    return response.status_code == 200
                except:
                    return False
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                results = list(executor.map(make_request, range(num_requests)))
            
            elapsed = time.time() - start_time
            success_count = sum(results)
            
            if success_count == num_requests:
                self.results.performance_metrics['concurrent_requests'] = {
                    'total_time': elapsed,
                    'avg_time_per_request': elapsed / num_requests,
                    'requests_per_second': num_requests / elapsed
                }
                self.results.add_pass(f"Concurrent requests ({success_count}/{num_requests} successful)")
                return True
            else:
                self.results.add_fail(
                    "Concurrent requests",
                    f"Only {success_count}/{num_requests} requests succeeded"
                )
                return False
        
        except Exception as e:
            self.results.add_fail("Concurrent requests", str(e))
            return False
    
    def test_response_times(self, iterations: int = 5) -> bool:
        """Test API response time consistency."""
        print(f"\n{Colors.OKCYAN}Testing response time consistency ({iterations} iterations)...{Colors.ENDC}")
        
        try:
            response_times = []
            
            for i in range(iterations):
                start_time = time.time()
                response = self.session.get(
                    f"{TestConfig.WEB_URL}/api/data?range=24h",
                    timeout=TestConfig.API_TIMEOUT
                )
                elapsed = time.time() - start_time
                
                if response.status_code == 200:
                    response_times.append(elapsed)
            
            if response_times:
                avg_time = statistics.mean(response_times)
                stdev_time = statistics.stdev(response_times) if len(response_times) > 1 else 0
                max_time = max(response_times)
                min_time = min(response_times)
                
                self.results.performance_metrics['response_time_stats'] = {
                    'average': avg_time,
                    'stdev': stdev_time,
                    'min': min_time,
                    'max': max_time
                }
                
                if avg_time < TestConfig.API_RESPONSE_TIME_THRESHOLD:
                    self.results.add_pass(f"Response time consistency (avg: {avg_time*1000:.0f}ms)")
                    return True
                else:
                    self.results.add_fail(
                        "Response time consistency",
                        f"Average response time {avg_time*1000:.0f}ms exceeds threshold {TestConfig.API_RESPONSE_TIME_THRESHOLD*1000:.0f}ms"
                    )
                    return False
            else:
                self.results.add_fail("Response time consistency", "No successful responses")
                return False
        
        except Exception as e:
            self.results.add_fail("Response time consistency", str(e))
            return False


def main():
    """Main test runner."""
    print(f"\n{Colors.BOLD}{Colors.HEADER}")
    print("╔" + "═" * 78 + "╗")
    print("║" + " " * 18 + "PingIT WebServer Comprehensive Test Suite" + " " * 18 + "║")
    print("╚" + "═" * 78 + "╝")
    print(f"{Colors.ENDC}\n")
    
    results = TestResults()
    webserver = None
    
    try:
        # Phase 1: Generate dummy data
        print(f"{Colors.BOLD}PHASE 1: DATA GENERATION{Colors.ENDC}")
        print("=" * 80)
        
        generator = DummyDataGenerator(TestConfig.DB_PATH, TestConfig.DAYS_BACK)
        generator.connect()
        generator.create_schema()
        record_count = generator.generate_data()
        generator.close()
        
        # Phase 2: Start webserver
        print(f"\n{Colors.BOLD}PHASE 2: WEBSERVER STARTUP{Colors.ENDC}")
        print("=" * 80)
        
        webserver = WebServerManager(TestConfig.DB_PATH)
        if not webserver.start():
            results.add_fail("WebServer startup", "Failed to start webserver")
            return False
        
        # Wait for webserver to be fully ready
        time.sleep(2)
        
        # Phase 3: API endpoint tests
        print(f"\n{Colors.BOLD}PHASE 3: API ENDPOINT TESTS{Colors.ENDC}")
        print("=" * 80)
        
        api_tests = APITestSuite(results)
        
        api_tests.test_health_endpoint()
        api_tests.test_api_data_1h()
        api_tests.test_api_data_24h()
        api_tests.test_api_data_30d()
        api_tests.test_api_statistics_endpoint()
        api_tests.test_api_disconnects_endpoint()
        api_tests.test_metrics_endpoint()
        
        # Phase 4: Accuracy tests
        print(f"\n{Colors.BOLD}PHASE 4: DATA SERIES ACCURACY TESTS{Colors.ENDC}")
        print("=" * 80)
        
        accuracy_tests = AccuracyTestSuite(results, TestConfig.DB_PATH)
        accuracy_tests.validate_data_series()
        
        # Phase 5: Performance tests
        print(f"\n{Colors.BOLD}PHASE 5: PERFORMANCE TESTS{Colors.ENDC}")
        print("=" * 80)
        
        performance_tests = PerformanceTestSuite(results)
        performance_tests.test_concurrent_requests(10)
        performance_tests.test_response_times(5)
        
        # Print summary
        success = results.print_summary()
        
        return success
    
    except KeyboardInterrupt:
        print(f"\n{Colors.WARNING}Test interrupted by user{Colors.ENDC}")
        return False
    
    except Exception as e:
        print(f"\n{Colors.FAIL}Fatal error: {e}{Colors.ENDC}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        # Cleanup: stop webserver
        if webserver:
            webserver.stop()
        
        # Cleanup: remove test database
        print(f"\n{Colors.OKCYAN}Cleaning up...{Colors.ENDC}")
        if TestConfig.DB_PATH.exists():
            try:
                TestConfig.DB_PATH.unlink()
                print(f"{Colors.OKGREEN}✓{Colors.ENDC} Test database removed")
            except Exception as e:
                print(f"{Colors.WARNING}⚠{Colors.ENDC} Could not remove test database: {e}")


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
