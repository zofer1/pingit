#!/usr/bin/env python3
"""
PingIT Web Server
Internal API server for PingIT to report statistics and disconnect events.
"""

import logging
import argparse
import sqlite3
import threading
import json
import ssl
import os
import sys
import time
import glob
import copy
import socket
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict
from statistics import stdev
from logging.handlers import RotatingFileHandler

import yaml
from flask import Flask, jsonify, request, render_template, redirect
from http.server import HTTPServer, BaseHTTPRequestHandler
import ecs_logging


# Utility functions
def calculate_jitter(response_times: List[float]) -> float:
    """Calculate jitter (standard deviation) of response times."""
    if len(response_times) < 2:
        return 0.0
    try:
        return round(stdev(response_times), 2)
    except Exception:
        return 0.0


# Trend line and outlier filtering functions
def calculate_trend_line(points: List[Dict]) -> Dict:
    """Calculate linear trend line using least squares regression."""
    if len(points) < 2:
        return None
    
    n = len(points)
    sum_x = sum(p['x'] for p in points)
    sum_y = sum(p['y'] for p in points)
    sum_xy = sum(p['x'] * p['y'] for p in points)
    sum_x2 = sum(p['x'] * p['x'] for p in points)
    
    denominator = n * sum_x2 - sum_x * sum_x
    if denominator == 0:
        return None
    
    slope = (n * sum_xy - sum_x * sum_y) / denominator
    intercept = (sum_y - slope * sum_x) / n
    
    return {'slope': slope, 'intercept': intercept}


def get_trend_value(x: float, trend: Dict) -> float:
    """Get trend line value at a given x coordinate."""
    return trend['slope'] * x + trend['intercept']


def filter_points_by_trend(points: List[Dict], baseline_points: int = 20, outlier_threshold: float = 5) -> List[Dict]:
    """
    Filter points to maintain a baseline number of evenly-spaced points plus outliers.
    
    Args:
        points: List of {x: timestamp_ms, y: response_time} dicts
        baseline_points: Target number of evenly-spaced baseline points (default 20)
        outlier_threshold: Deviation in ms from trend line to be considered an outlier
    
    Returns:
        Filtered list maintaining ~baseline_points evenly spaced + all outliers
    """
    if len(points) < 2:
        return points
    
    # If we have fewer points than baseline, return all
    if len(points) <= baseline_points:
        return points
    
    trend = calculate_trend_line(points)
    if trend is None:
        return points
    
    # Calculate spacing for baseline points across the entire time range
    interval = len(points) / baseline_points
    baseline_indices = set()
    
    # Add evenly-spaced baseline points
    for i in range(baseline_points):
        idx = int(i * interval)
        if idx < len(points):
            baseline_indices.add(idx)
    
    # Ensure first and last points are always included
    baseline_indices.add(0)
    baseline_indices.add(len(points) - 1)
    
    # Find outlier points (deviation > threshold from trend)
    outlier_indices = set()
    for i in range(1, len(points) - 1):
        point = points[i]
        trend_value = get_trend_value(point['x'], trend)
        deviation = abs(point['y'] - trend_value)
        
        if deviation > outlier_threshold:
            outlier_indices.add(i)
    
    # Combine baseline and outlier indices
    selected_indices = baseline_indices | outlier_indices
    
    # Return filtered points in original order
    filtered = [points[i] for i in sorted(selected_indices)]
    
    return filtered


def normalize_timestamp_ms(value) -> int:
    """Convert various timestamp formats to Unix milliseconds.
    
    Handles:
    - integers/floats already in milliseconds
    - strings containing milliseconds
    - ISO 8601 strings (converted via datetime)
    Falls back to 0 on failure.
    """
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        # First try raw integer/float string
        try:
            return int(float(value))
        except Exception:
            pass
        # Then try ISO 8601
        try:
            dt = datetime.fromisoformat(value)
            return int(dt.timestamp() * 1000)
        except Exception:
            return 0
    return 0

# Configuration
DEFAULT_CONFIG_PATH = "/etc/pingit/webserver-config.yaml"
DEFAULT_LOG_PATH = "/var/log/pingit"
DEFAULT_PORT = 7030
DEFAULT_DB_PATH = "/var/lib/pingit/pingit.db"

# Test mode defaults (all in current directory)
TEST_CONFIG_PATH = "./webserver-config.yaml"
TEST_LOG_PATH = "."
TEST_DB_PATH = "./pingit.db"
TEST_PORT = 7030  # Use same port as production for consistency

# Flask app
app = Flask(__name__, template_folder='templates', static_folder='static')
app.config['JSON_SORT_KEYS'] = False
app.config['JSONIFY_PRETTYPRINT_REGULAR'] = False

# Global variables to track SSL settings (set at runtime)
ssl_enabled_global = False
http_port_global = 7030
https_port_global = 7443

@app.before_request
def redirect_to_correct_https():
    """Redirect requests to the correct HTTPS port when SSL is enabled."""
    if ssl_enabled_global and request.scheme == 'https':
        # Already on HTTPS, check if on correct port
        current_host = request.host
        # Extract host without port
        host_only = current_host.split(':')[0] if ':' in current_host else current_host
        
        # If not on the correct HTTPS port, redirect to it
        if f':{https_port_global}' not in current_host:
            new_url = request.url.replace(f'://{current_host}', f'://{host_only}:{https_port_global}')
            return redirect(new_url, code=301)

# In-memory metrics storage
class MetricsCache:
    """Thread-safe in-memory metrics cache for Prometheus scraping."""
    
    def __init__(self):
        self.lock = threading.Lock()
        # Format: {target_name: {'host': host, 'ping_times': [times...], 'disconnect_count': N}}
        self.metrics = {}
    
    def update_ping_time(self, target_name: str, host: str, response_time: float):
        """Record a ping response time in milliseconds."""
        with self.lock:
            if target_name not in self.metrics:
                self.metrics[target_name] = {
                    'host': host,
                    'ping_times': [],
                    'disconnect_count': 0,
                    'status': 1
                }
            self.metrics[target_name]['ping_times'].append(response_time)
            self.metrics[target_name]['host'] = host
            self.metrics[target_name]['status'] = 1  # Mark as up
    
    def update_status(self, target_name: str, host: str, status: int):
        """Update target status (1=up, 0=down)."""
        with self.lock:
            if target_name not in self.metrics:
                self.metrics[target_name] = {
                    'host': host,
                    'ping_times': [],
                    'disconnect_count': 0,
                    'status': status
                }
            else:
                self.metrics[target_name]['status'] = status
    
    def increment_disconnect(self, target_name: str, host: str):
        """Increment disconnect counter for a target."""
        with self.lock:
            if target_name not in self.metrics:
                self.metrics[target_name] = {
                    'host': host,
                    'ping_times': [],
                    'disconnect_count': 1,
                    'status': 0
                }
            else:
                self.metrics[target_name]['disconnect_count'] += 1
                self.metrics[target_name]['status'] = 0  # Mark as down
    
    def get_and_clear(self):
        """Get all metrics and clear the cache."""
        with self.lock:
            result = copy.deepcopy(self.metrics)
            self.metrics = {}
            return result
    
    def get_copy(self):
        """Get a copy of metrics without clearing."""
        with self.lock:
            return copy.deepcopy(self.metrics)
    
    def clear(self):
        """Clear all metrics."""
        with self.lock:
            self.metrics = {}


# Initialize metrics cache
metrics_cache = MetricsCache()

# Global variables
sqlite_db_path: Optional[str] = None
sqlite_conn: Optional[sqlite3.Connection] = None
sqlite_lock = threading.Lock()  # Synchronization lock for SQLite operations
config = None
logger = None
prometheus_mode: bool = False  # If True, cache is cleared after each metrics scrape (drain pattern)


def setup_logging(log_path: str = DEFAULT_LOG_PATH, level: str = "INFO", 
                 max_bytes: int = 10485760, backup_count: int = 10, retention_days: int = 7):
    """Set up ECS logging with rolling file handler and cleanup."""
    log_dir = Path(log_path)
    log_dir.mkdir(parents=True, exist_ok=True)
    
    logger = logging.getLogger("pingit-webserver")
    log_level = logging.DEBUG if level.upper() == "DEBUG" else logging.INFO
    logger.setLevel(log_level)
    
    # Remove any existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # Create log filename with date
    log_filename = f"webserver-{datetime.now().strftime('%Y-%m-%d')}.log"
    
    # Rotating file handler with size-based rotation
    log_file = log_dir / log_filename
    fh = RotatingFileHandler(
        str(log_file),
        maxBytes=max_bytes,  # 10 MB default
        backupCount=backup_count  # Keep 10 files
    )
    fh.setLevel(log_level)
    fh.setFormatter(ecs_logging.StdlibFormatter())
    
    # Custom namer to include date in rotated filenames
    def namer(name):
        """Rename rotated log files to include date and rotation number."""
        base_name = log_filename.replace('.log', '')
        return f"{str(log_dir)}/{base_name}.{datetime.now().strftime('%Y-%m-%d-%H-%M-%S')}.1.log"
    
    fh.namer = namer
    
    # Console handler with ECS formatter
    ch = logging.StreamHandler()
    ch.setLevel(log_level)
    ch.setFormatter(ecs_logging.StdlibFormatter())
    
    logger.addHandler(fh)
    logger.addHandler(ch)
    
    # Clean up old log files (older than retention_days)
    cleanup_old_logs(log_dir, retention_days)
    
    return logger


def cleanup_old_logs(log_dir: Path, retention_days: int = 7):
    """Delete log files older than retention_days."""
    try:
        cutoff_time = time.time() - (retention_days * 86400)  # 86400 seconds per day
        
        for log_file in glob.glob(str(log_dir / "webserver-*.log")):
            if os.path.isfile(log_file):
                file_time = os.path.getmtime(log_file)
                if file_time < cutoff_time:
                    try:
                        os.remove(log_file)
                        logger.debug(f"Deleted old log file: {log_file}")
                    except Exception as e:
                        logger.warning(f"Failed to delete log file {log_file}: {e}")
    except Exception as e:
        # Don't fail if cleanup fails, log warning if logger is available
        if logger:
            logger.warning(f"Log cleanup error: {e}")


def load_config(config_path: str):
    """Load configuration from YAML file."""
    try:
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        raise


def connect_sqlite(db_path: str) -> sqlite3.Connection:
    """Connect to SQLite database."""
    try:
        conn = sqlite3.connect(db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        logger.info(f"Connected to SQLite database: {db_path}")
        return conn
    except Exception as e:
        logger.error(f"Failed to connect to SQLite: {e}")
        raise


def ensure_schema(conn: sqlite3.Connection):
    """Ensure database schema exists."""
    with sqlite_lock:
        cursor = conn.cursor()
        
        # Create ping_statistics table for per-target statistics
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
        
        # Create disconnect_times table for recording disconnect events
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
        
        # Create indexes for faster queries
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_ping_statistics_target_timestamp 
            ON ping_statistics(target_name, timestamp)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_disconnect_times_target 
            ON disconnect_times(target_name, disconnect_time)
        ''')
        
        conn.commit()
        logger.info("Database schema verified")


def migrate_timestamps_to_epoch(conn: sqlite3.Connection):
    """Migrate timestamp columns from TEXT (ISO 8601) to INTEGER (Unix milliseconds).
    
    This function:
    1. Creates new columns with INTEGER type
    2. Migrates data from old TEXT columns to new INTEGER columns
    3. Drops old TEXT columns
    4. Renames new columns to original names
    5. Recreates indexes
    
    This should only be called once during upgrade with --migrate-timestamps flag.
    """
    try:
        with sqlite_lock:
            cursor = conn.cursor()
            
            logger.info("Starting timestamp migration from TEXT to INTEGER (Unix milliseconds)...")
            
            # Check if migration is needed (if columns are TEXT type)
            cursor.execute("PRAGMA table_info(ping_statistics)")
            columns = cursor.fetchall()
            timestamp_type = None
            for col in columns:
                if col[1] == 'timestamp':
                    timestamp_type = col[2]
                    break
            
            if timestamp_type == 'INTEGER':
                logger.info("Timestamps are already INTEGER - migration not needed")
                return
            
            logger.info(f"Current timestamp type: {timestamp_type}, migrating to INTEGER...")
            
            # Migrate ping_statistics table
            logger.info("Migrating ping_statistics table...")
            cursor.execute('''
                ALTER TABLE ping_statistics RENAME TO ping_statistics_old
            ''')
            
            cursor.execute('''
                CREATE TABLE ping_statistics (
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
            
            # Migrate data: convert ISO 8601 TEXT to Unix milliseconds
            cursor.execute('''
                INSERT INTO ping_statistics 
                SELECT id, target_name, host, total_pings, successful_pings, failed_pings,
                       success_rate, avg_response_time, min_response_time, max_response_time,
                       last_status,
                       CAST(STRFTIME('%s', timestamp) * 1000 AS INTEGER) as timestamp
                FROM ping_statistics_old
            ''')
            
            cursor.execute('DROP TABLE ping_statistics_old')
            logger.info("ping_statistics table migrated successfully")
            
            # Migrate disconnect_times table
            logger.info("Migrating disconnect_times table...")
            cursor.execute('''
                ALTER TABLE disconnect_times RENAME TO disconnect_times_old
            ''')
            
            cursor.execute('''
                CREATE TABLE disconnect_times (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    target_name TEXT NOT NULL,
                    host TEXT NOT NULL,
                    disconnect_time INTEGER NOT NULL,
                    duration_seconds INTEGER,
                    reason TEXT,
                    timestamp INTEGER DEFAULT (CAST(STRFTIME('%s', 'now') * 1000 AS INTEGER))
                )
            ''')
            
            # Migrate data: convert ISO 8601 TEXT to Unix milliseconds
            cursor.execute('''
                INSERT INTO disconnect_times 
                SELECT id, target_name, host,
                       CAST(STRFTIME('%s', disconnect_time) * 1000 AS INTEGER) as disconnect_time,
                       duration_seconds, reason,
                       CAST(STRFTIME('%s', timestamp) * 1000 AS INTEGER) as timestamp
                FROM disconnect_times_old
            ''')
            
            cursor.execute('DROP TABLE disconnect_times_old')
            logger.info("disconnect_times table migrated successfully")
            
            # Recreate indexes
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_ping_statistics_target_timestamp 
                ON ping_statistics(target_name, timestamp)
            ''')
            
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_disconnect_times_target 
                ON disconnect_times(target_name, disconnect_time)
            ''')
            
            conn.commit()
            logger.info("✅ Timestamp migration completed successfully!")
            logger.info("   - ping_statistics: TEXT → INTEGER (Unix milliseconds)")
            logger.info("   - disconnect_times: TEXT → INTEGER (Unix milliseconds)")
            
    except Exception as e:
        logger.error(f"❌ Timestamp migration failed: {e}")
        raise


@app.route('/')
def dashboard():
    """Serve the dashboard HTML page."""
    return render_template('dashboard.html')


@app.route('/api/data')
def api_data():
    """API endpoint to get all statistics and disconnects data for dashboard."""
    try:
        # Get time range from query parameter (default: 24h)
        time_range = request.args.get('range', '24h')
        
        # Calculate time cutoff
        if time_range == '1h':
            hours_back = 1
        elif time_range == '30d':
            hours_back = 24 * 30
        else:  # default to 24h
            hours_back = 24

        # SQLite expressions to normalize timestamps (support integer ms and ISO text)
        timestamp_ms_expr = """
            CASE 
                WHEN typeof(timestamp) IN ('integer','real') THEN CAST(timestamp AS INTEGER)
                WHEN typeof(timestamp) = 'text' THEN
                    CASE 
                        WHEN instr(timestamp, '-') > 0 THEN CAST(strftime('%s', timestamp) * 1000 AS INTEGER)
                        ELSE CAST(timestamp AS INTEGER)
                    END
                ELSE 0
            END
        """
        disconnect_ms_expr = """
            CASE 
                WHEN typeof(disconnect_time) IN ('integer','real') THEN CAST(disconnect_time AS INTEGER)
                WHEN typeof(disconnect_time) = 'text' THEN
                    CASE 
                        WHEN instr(disconnect_time, '-') > 0 THEN CAST(strftime('%s', disconnect_time) * 1000 AS INTEGER)
                        ELSE CAST(disconnect_time AS INTEGER)
                    END
                ELSE 0
            END
        """
        
        with sqlite_lock:
            cursor = sqlite_conn.cursor()
            
            # Get all statistics from the time range
            # Calculate cutoff time in milliseconds
            cutoff_ms = int((datetime.now().timestamp() - (hours_back * 3600)) * 1000)
            cursor.execute(f'''
                SELECT target_name, host, total_pings, successful_pings, failed_pings, 
                       success_rate, avg_response_time, min_response_time, max_response_time,
                       last_status,
                       {timestamp_ms_expr} as ts_ms
                FROM ping_statistics
                WHERE {timestamp_ms_expr} > ?
                ORDER BY target_name
            ''', (cutoff_ms,))
            
            stats_rows = cursor.fetchall()
            
            # Get aggregated disconnects by target in the time range
            cursor.execute(f'''
                SELECT target_name, host, COUNT(*) as disconnect_count, 
                       MAX({disconnect_ms_expr}) as last_disconnect
                FROM disconnect_times
                WHERE {disconnect_ms_expr} > ?
                GROUP BY target_name, host
                ORDER BY target_name
            ''', (cutoff_ms,))
            
            disconnect_rows = cursor.fetchall()
            
            # Get time-series data for response time over time
            cursor.execute(f'''
                SELECT target_name, {timestamp_ms_expr} as ts_ms, avg_response_time, min_response_time, max_response_time
                FROM ping_statistics
                WHERE {timestamp_ms_expr} > ?
                ORDER BY target_name, ts_ms
            ''', (cutoff_ms,))
            
            timeseries_rows = cursor.fetchall()
        
        # Aggregate statistics by target (sum across all records in time period)
        targets_data = []
        total_disconnects_stats = 0
        total_pings = 0
        targets_dict = {}
        
        for row in stats_rows:
            target_name = row['target_name']
            
            if target_name not in targets_dict:
                # Initialize target entry
                targets_dict[target_name] = {
                    'name': target_name,
                    'host': row['host'],
                    'total_pings_sum': 0,
                    'successful_pings_sum': 0,
                    'failed_pings_sum': 0,
                    'response_times': [],
                    'last_status': row['last_status']
                }
            
            # Accumulate totals across all cycles in the time period
            targets_dict[target_name]['total_pings_sum'] += row['total_pings']
            targets_dict[target_name]['successful_pings_sum'] += row['successful_pings']
            targets_dict[target_name]['failed_pings_sum'] += row['failed_pings']
            targets_dict[target_name]['response_times'].append((
                row['avg_response_time'] or 0,
                row['min_response_time'] or 0,
                row['max_response_time'] or 0
            ))
            targets_dict[target_name]['last_status'] = row['last_status']
        
        # Calculate aggregated statistics for each target
        final_targets = {}
        for target_name, data in targets_dict.items():
            total = data['total_pings_sum']
            successful = data['successful_pings_sum']
            failed = data['failed_pings_sum']
            
            # Calculate aggregated statistics
            success_rate = (successful / total * 100) if total > 0 else 0
            avg_resp = sum(rt[0] for rt in data['response_times']) / len(data['response_times']) if data['response_times'] else 0
            min_resp = min(rt[1] for rt in data['response_times']) if data['response_times'] else 0
            max_resp = max(rt[2] for rt in data['response_times']) if data['response_times'] else 0
            
            # Calculate jitter (standard deviation of average response times)
            avg_response_times = [rt[0] for rt in data['response_times']]
            jitter = calculate_jitter(avg_response_times)
            
            final_targets[target_name] = {
                'name': target_name,
                'host': data['host'],
                'pings': int(total),
                'success_rate': float(success_rate),
                'avg_response_time': round(float(avg_resp), 2),
                'min_response_time': round(float(min_resp), 2),
                'max_response_time': round(float(max_resp), 2),
                'jitter': float(jitter),
                'disconnect_count': 0,
                'status': 'up' if data['last_status'] == 1 else 'down'
            }
            
            total_disconnects_stats += failed
            total_pings += total
        
        targets_dict = final_targets
        
        # Build disconnects data
        disconnects_data = []
        for row in disconnect_rows:
            target_name = row['target_name']
            last_dc = normalize_timestamp_ms(row['last_disconnect'])
            disconnects_data.append({
                'name': target_name,
                'host': row['host'],
                'disconnect_count': row['disconnect_count'],
                'last_disconnect': last_dc
            })
            
            # Update disconnect count in targets dict
            if target_name in targets_dict:
                targets_dict[target_name]['disconnect_count'] = row['disconnect_count']
            else:
                targets_dict[target_name] = {
                    'name': target_name,
                    'host': row['host'],
                    'pings': 0,
                    'success_rate': 0.0,
                    'avg_response_time': None,
                    'min_response_time': None,
                    'max_response_time': None,
                    'disconnect_count': row['disconnect_count'],
                    'status': 'down'
                }
        
        # Convert dict to list
        # Convert to list while preserving order from targets_dict
        # Note: targets_dict maintains insertion order (Python 3.7+)
        targets_data = list(targets_dict.values())
        
        # Calculate uptime percentage
        uptime = (total_pings - total_disconnects_stats) / total_pings * 100 if total_pings > 0 else 0
        
        # Build time-series data for response time over time
        # First, collect raw timeseries data
        raw_timeseries_data = {}
        for row in timeseries_rows:
            target_name = row['target_name']
            if target_name not in raw_timeseries_data:
                raw_timeseries_data[target_name] = {
                    'timestamps': [],
                    'avg_response_times': [],
                    'min_response_times': [],
                    'max_response_times': []
                }
            
            ts = normalize_timestamp_ms(row['ts_ms'])
            raw_timeseries_data[target_name]['timestamps'].append(ts)
            raw_timeseries_data[target_name]['avg_response_times'].append(
                float(row['avg_response_time']) if row['avg_response_time'] is not None else 0.0
            )
            raw_timeseries_data[target_name]['min_response_times'].append(
                float(row['min_response_time']) if row['min_response_time'] is not None else 0.0
            )
            raw_timeseries_data[target_name]['max_response_times'].append(
                float(row['max_response_time']) if row['max_response_time'] is not None else 0.0
            )
        
        # Apply trend line filtering to reduce chart clutter
        timeseries_data = {}
        for target_name, data in raw_timeseries_data.items():
            original_count = len(data['timestamps'])
            
            # Timestamps are already in milliseconds (Unix epoch), no conversion needed
            # Create points with x (timestamp) and y (response time) for filtering
            points = [
                {'x': ts_ms, 'y': avg_time}
                for ts_ms, avg_time in zip(data['timestamps'], data['avg_response_times'])
            ]
            
            # Filter points: maintain 20 baseline points + any outliers > 5ms deviation
            filtered_points = filter_points_by_trend(points, baseline_points=20, outlier_threshold=5)
            
            # Extract filtered indices to get corresponding timestamps and response times
            filtered_indices = set()
            for p in filtered_points:
                # Find the original index of this point
                for i, orig_point in enumerate(points):
                    if orig_point['x'] == p['x'] and orig_point['y'] == p['y']:
                        filtered_indices.add(i)
                        break
            
            filtered_count = len(filtered_indices)
            reduction_percent = ((original_count - filtered_count) / original_count * 100) if original_count > 0 else 0
            
            # Build filtered timeseries
            timeseries_data[target_name] = {
                'timestamps': [data['timestamps'][i] for i in sorted(filtered_indices)],
                'avg_response_times': [data['avg_response_times'][i] for i in sorted(filtered_indices)],
                'min_response_times': [data['min_response_times'][i] for i in sorted(filtered_indices)],
                'max_response_times': [data['max_response_times'][i] for i in sorted(filtered_indices)]
            }
            
            logger.debug(f"Timeseries filtering for {target_name}: {original_count} → {filtered_count} points ({reduction_percent:.1f}% reduction)")
        
        # Build response ensuring all fields are included
        import json
        response_data = {
            'time_range': time_range,
            'targets': targets_data,
            'disconnects': disconnects_data,
            'timeseries': timeseries_data,
            'total_targets': len(targets_dict),
            'total_disconnects': len(disconnect_rows),
            'total_disconnect_events': sum(d['disconnect_count'] for d in disconnects_data),
            'uptime_percentage': round(uptime, 2)
        }
        
        # Return as raw JSON response using app.response_class
        return app.response_class(
            response=json.dumps(response_data, default=str),
            status=200,
            mimetype='application/json'
        )
    
    except Exception as e:
        logger.error(f"Error retrieving dashboard data: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/health')
def health():
    """Health check endpoint."""
    return jsonify({'status': 'healthy', 'database': 'sqlite'}), 200


# ADMIN ROUTES
@app.route('/admin')
def admin_dashboard():
    """Admin dashboard page."""
    return render_template('admin.html')


# Initialize admin manager
admin_manager = None


def init_admin_manager(db_path: str, webserver_config_path: str, pingit_config_path: str, test_mode: bool = False):
    """Initialize admin manager with both webserver and pingit configs."""
    global admin_manager
    from admin import AdminManager
    admin_manager = AdminManager(db_path, webserver_config_path, pingit_config_path, test_mode)


# Admin API Routes
@app.route('/api/admin/targets', methods=['GET'])
def admin_get_targets():
    """Get all targets."""
    if not admin_manager:
        return jsonify({'error': 'Admin not initialized'}), 500
    targets = admin_manager.get_targets()
    return jsonify({'targets': targets}), 200


@app.route('/api/admin/targets', methods=['POST'])
def admin_add_target():
    """Add a target."""
    if not admin_manager:
        return jsonify({'error': 'Admin not initialized'}), 500
    
    data = request.get_json()
    success, message = admin_manager.add_target(
        data.get('name'),
        data.get('host'),
        data.get('timeout', 0.5)
    )
    
    if success:
        logger.info(f"Admin: {message}")
        return jsonify({'message': message}), 201
    else:
        logger.warning(f"Admin: {message}")
        return jsonify({'error': message}), 400


@app.route('/api/admin/targets/<target_name>', methods=['DELETE'])
def admin_remove_target(target_name):
    """Remove a target."""
    if not admin_manager:
        return jsonify({'error': 'Admin not initialized'}), 500
    
    success, message = admin_manager.remove_target(target_name)
    
    if success:
        logger.info(f"Admin: {message}")
        return jsonify({'message': message}), 200
    else:
        logger.warning(f"Admin: {message}")
        return jsonify({'error': message}), 400


@app.route('/api/admin/logs/level', methods=['PUT'])
def admin_set_log_level():
    """Set log level for a service."""
    if not admin_manager:
        return jsonify({'error': 'Admin not initialized'}), 500
    
    data = request.get_json()
    success, message = admin_manager.set_log_level(
        data.get('service'),
        data.get('level')
    )
    
    if success:
        logger.info(f"Admin: {message}")
        return jsonify({'message': message}), 200
    else:
        logger.warning(f"Admin: {message}")
        return jsonify({'error': message}), 400


@app.route('/api/admin/services/<service>/start', methods=['POST'])
def admin_start_service(service):
    """Start a service."""
    if not admin_manager:
        return jsonify({'error': 'Admin not initialized'}), 500
    
    success, message = admin_manager.start_service(service)
    
    if success:
        logger.info(f"Admin: {message}")
        return jsonify({'message': message}), 200
    else:
        logger.warning(f"Admin: {message}")
        return jsonify({'error': message}), 400


@app.route('/api/admin/services/<service>/stop', methods=['POST'])
def admin_stop_service(service):
    """Stop a service."""
    if not admin_manager:
        return jsonify({'error': 'Admin not initialized'}), 500
    
    success, message = admin_manager.stop_service(service)
    
    if success:
        logger.info(f"Admin: {message}")
        return jsonify({'message': message}), 200
    else:
        logger.warning(f"Admin: {message}")
        return jsonify({'error': message}), 400


@app.route('/api/admin/services/<service>/status', methods=['GET'])
def admin_get_service_status(service):
    """Get service status."""
    if not admin_manager:
        return jsonify({'error': 'Admin not initialized'}), 500
    
    success, status = admin_manager.get_service_status(service)
    
    if success:
        return jsonify({'status': status}), 200
    else:
        return jsonify({'error': status.get('error', 'Unknown error')}), 400


@app.route('/api/admin/services/<service>/restart', methods=['POST'])
def admin_restart_service(service):
    """Restart a service."""
    if not admin_manager:
        return jsonify({'error': 'Admin not initialized'}), 500
    
    success, message = admin_manager.restart_service(service)
    
    if success:
        logger.info(f"Admin: {message}")
        return jsonify({'message': message}), 200
    else:
        logger.warning(f"Admin: {message}")
        return jsonify({'error': message}), 400


@app.route('/api/admin/prometheus/mode', methods=['PUT'])
def admin_prometheus_mode():
    """Toggle prometheus mode."""
    global prometheus_mode
    data = request.get_json()
    prometheus_mode = data.get('enabled', False)
    
    logger.info(f"Admin: Prometheus mode set to {prometheus_mode}")
    return jsonify({'message': f"Prometheus mode {'enabled' if prometheus_mode else 'disabled'}"}), 200


@app.route('/api/admin/ssl/mode', methods=['PUT'])
def admin_ssl_mode():
    """Toggle SSL mode."""
    global config
    data = request.get_json()
    
    if not config:
        config = {}
    if 'ssl' not in config:
        config['ssl'] = {}
    
    config['ssl']['enabled'] = data.get('enabled', False)
    logger.info(f"Admin: SSL mode set to {config['ssl']['enabled']}")
    
    return jsonify({'message': f"SSL mode {'enabled' if config['ssl']['enabled'] else 'disabled'} (restart required)"}), 200


@app.route('/api/admin/database/generate-test-data', methods=['POST'])
def admin_generate_test_data():
    """Generate test data."""
    if not admin_manager:
        return jsonify({'error': 'Admin not initialized'}), 500
    
    data = request.get_json()
    days = data.get('days', 7)
    
    success, message = admin_manager.generate_test_data(days)
    
    if success:
        logger.info(f"Admin: {message}")
        return jsonify({'message': message}), 200
    else:
        logger.warning(f"Admin: {message}")
        return jsonify({'error': message}), 400


@app.route('/api/admin/database/backup', methods=['POST'])
def admin_backup_database():
    """Backup database."""
    if not admin_manager:
        return jsonify({'error': 'Admin not initialized'}), 500
    
    success, message = admin_manager.backup_database()
    
    if success:
        logger.info(f"Admin: {message}")
        return jsonify({'message': message}), 200
    else:
        logger.warning(f"Admin: {message}")
        return jsonify({'error': message}), 400


@app.route('/api/admin/database/reset', methods=['POST'])
def admin_reset_database():
    """Reset database (requires confirmation)."""
    if not admin_manager:
        return jsonify({'error': 'Admin not initialized'}), 500
    
    success, message = admin_manager.reset_database()
    
    if success:
        # Clear the in-memory metrics cache as well
        metrics_cache.clear()
        logger.warning(f"Admin: DATABASE RESET - {message} (cache cleared)")
        return jsonify({'message': message}), 200
    else:
        logger.error(f"Admin: DATABASE RESET FAILED - {message}")
        return jsonify({'error': message}), 400


@app.route('/api/admin/config/verify', methods=['POST'])
def admin_verify_config():
    """Verify configuration."""
    if not admin_manager:
        return jsonify({'error': 'Admin not initialized'}), 500
    
    success, config_info = admin_manager.verify_config()
    return jsonify({'config': config_info}), 200 if success else 400


@app.route('/api/admin/logs/location', methods=['GET'])
def admin_get_log_location():
    """Get current log location."""
    if not admin_manager:
        return jsonify({'error': 'Admin not initialized'}), 500
    
    # Query parameter 'service' is accepted but both services use same path for now
    location = admin_manager.get_log_location()
    return jsonify({'path': location}), 200


@app.route('/api/admin/logs/location', methods=['PUT'])
def admin_set_log_location():
    """Set log location."""
    if not admin_manager:
        return jsonify({'error': 'Admin not initialized'}), 500
    
    data = request.get_json()
    service = data.get('service', 'pingit')
    path = data.get('path')
    
    if not path:
        return jsonify({'error': 'Log path is required'}), 400
    
    success, message = admin_manager.set_log_location(service, path)
    
    if success:
        logger.info(f"Admin: {message}")
        return jsonify({'message': message}), 200
    else:
        logger.warning(f"Admin: {message}")
        return jsonify({'error': message}), 400


@app.route('/api/admin/logs/tail', methods=['GET'])
def admin_get_log_tail():
    """Get last N lines from log file."""
    if not admin_manager:
        return jsonify({'error': 'Admin not initialized'}), 500
    
    service = request.args.get('service', 'pingit')
    lines = int(request.args.get('lines', 20))
    success, content = admin_manager.get_log_tail(service, lines=lines)
    
    if success:
        return jsonify({'content': content}), 200
    else:
        return jsonify({'error': content}), 400


@app.route('/api/admin/ssl/enable', methods=['PUT'])
def admin_enable_ssl():
    """Enable SSL."""
    if not admin_manager:
        return jsonify({'error': 'Admin not initialized'}), 500
    
    data = request.get_json()
    cert_path = data.get('certificate')
    key_path = data.get('private_key')
    https_port = data.get('https_port', 7443)
    
    if not cert_path or not key_path:
        return jsonify({'error': 'Certificate and private key paths are required'}), 400
    
    success, message = admin_manager.enable_ssl(cert_path, key_path, https_port)
    
    if success:
        logger.info(f"Admin: {message}")
        return jsonify({'message': message}), 200
    else:
        logger.warning(f"Admin: {message}")
        return jsonify({'error': message}), 400


@app.route('/api/admin/ssl/disable', methods=['PUT'])
def admin_disable_ssl():
    """Disable SSL."""
    if not admin_manager:
        return jsonify({'error': 'Admin not initialized'}), 500
    
    success, message = admin_manager.disable_ssl()
    
    if success:
        logger.info(f"Admin: {message}")
        return jsonify({'message': message}), 200
    else:
        logger.warning(f"Admin: {message}")
        return jsonify({'error': message}), 400


@app.route('/api/admin/ssl/override', methods=['PUT'])
def admin_override_ssl():
    """Override SSL settings."""
    if not admin_manager:
        return jsonify({'error': 'Admin not initialized'}), 500
    
    data = request.get_json()
    cert_path = data.get('certificate')
    key_path = data.get('private_key')
    https_port = data.get('https_port')
    
    if not cert_path or not key_path:
        return jsonify({'error': 'Certificate and private key paths are required'}), 400
    
    success, message = admin_manager.override_ssl(cert_path, key_path, https_port)
    
    if success:
        logger.info(f"Admin: {message}")
        return jsonify({'message': message}), 200
    else:
        logger.warning(f"Admin: {message}")
        return jsonify({'error': message}), 400


@app.route('/api/admin/ssl/reset', methods=['PUT'])
def admin_reset_ssl():
    """Reset SSL settings."""
    if not admin_manager:
        return jsonify({'error': 'Admin not initialized'}), 500
    
    success, message = admin_manager.reset_ssl()
    
    if success:
        logger.info(f"Admin: {message}")
        return jsonify({'message': message}), 200
    else:
        logger.warning(f"Admin: {message}")
        return jsonify({'error': message}), 400


@app.route('/api/admin/ssl/status', methods=['GET'])
def admin_ssl_status():
    """Get SSL status."""
    if not admin_manager:
        return jsonify({'error': 'Admin not initialized'}), 500
    
    status = admin_manager.get_ssl_status()
    return jsonify(status), 200


@app.route('/api/admin/webserver/reload', methods=['POST'])
def admin_reload_webserver():
    """Reload WebServer (graceful restart)."""
    try:
        logger.info("Admin: WebServer reload requested")
        
        # Graceful reload approach - restart process in background
        import subprocess
        import threading
        
        def reload_app():
            time.sleep(0.5)  # Give time for response to be sent
            logger.warning("Reloading WebServer application...")
            
            # Get current arguments
            script_path = __file__
            args = sys.argv[1:]
            
            # Windows or Unix approach
            if sys.platform == 'win32':
                # On Windows: spawn new process and exit current one
                subprocess.Popen([sys.executable, script_path] + args)
                # Give new process time to start
                time.sleep(1)
                # Exit current process
                os._exit(0)
            else:
                # On Unix/Linux: use execvp for cleaner reload
                os.execvp(sys.executable, [sys.executable, script_path] + args)
        
        thread = threading.Thread(target=reload_app, daemon=True)
        thread.start()
        return jsonify({'message': 'WebServer reloading in 0.5 seconds...'}), 200
    except Exception as e:
        logger.error(f"Error reloading WebServer: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/metrics')
def metrics():
    """
    Prometheus metrics endpoint.
    Exposes metrics with:
    - pingit_ping_time_ms (gauge): Response time in milliseconds from memory cache
    - pingit_disconnect_events_total (counter): Disconnect events from database by time period (1m, 1h, 24h)
    """
    try:
        # Get current metrics from cache
        # If prometheus_mode is True, clear cache after reading (drain pattern)
        # Otherwise keep cache for manual inspection
        if prometheus_mode:
            current_metrics = metrics_cache.get_and_clear()
        else:
            current_metrics = metrics_cache.get_copy()
        
        # Build Prometheus text format
        lines = []
        
        # Add help and type metadata
        lines.append("# HELP pingit_ping_time_ms Ping response time in milliseconds")
        lines.append("# TYPE pingit_ping_time_ms gauge")
        
        lines.append("# HELP pingit_disconnect_events_total Total disconnect events for target by time period")
        lines.append("# TYPE pingit_disconnect_events_total counter")
        
        # Query disconnect events from database by time period
        disconnect_by_period = {}
        time_periods = {
            '1m': 720,   # last 30 days (month) = 720 hours
            '1h': 1,     # last 1 hour
            '24h': 24    # last 24 hours
        }
        disconnect_ms_expr = """
            CASE 
                WHEN typeof(disconnect_time) IN ('integer','real') THEN CAST(disconnect_time AS INTEGER)
                WHEN typeof(disconnect_time) = 'text' THEN
                    CASE 
                        WHEN instr(disconnect_time, '-') > 0 THEN CAST(strftime('%s', disconnect_time) * 1000 AS INTEGER)
                        ELSE CAST(disconnect_time AS INTEGER)
                    END
                ELSE 0
            END
        """
        
        with sqlite_lock:
            cursor = sqlite_conn.cursor()
            
            for period_label, hours in time_periods.items():
                cutoff_ms = int((datetime.now() - timedelta(hours=hours)).timestamp() * 1000)
                cursor.execute(f'''
                    SELECT target_name, host, COUNT(*) as disconnect_count
                    FROM disconnect_times
                    WHERE {disconnect_ms_expr} > ?
                    GROUP BY target_name, host
                ''', (cutoff_ms,))
                
                rows = cursor.fetchall()
                for row in rows:
                    target_name = row['target_name']
                    host = row['host']
                    disconnect_count = row['disconnect_count']
                    
                    key = (target_name, host, period_label)
                    disconnect_by_period[key] = disconnect_count
        
        # Add ping time metrics for each target from cache
        for target_name, data in current_metrics.items():
            host = data['host']
            ping_times = data['ping_times']
            
            # Gauge: ping time (milliseconds) - report average of collected times
            if ping_times:
                avg_ping_time = sum(ping_times) / len(ping_times)
                lines.append(
                    f'pingit_ping_time_ms{{target_name="{target_name}",host="{host}"}} {avg_ping_time}'
                )
        
        # Add disconnect counters from database by time period (for all targets with disconnects)
        for (target_name, host, period), disconnect_count in disconnect_by_period.items():
            lines.append(
                f'pingit_disconnect_events_total{{target_name="{target_name}",host="{host}",period="{period}"}} {disconnect_count}'
            )
        
        # Add timestamp
        lines.append(f"# Generated at {datetime.now().isoformat()}")
        lines.append("")
        
        metrics_text = "\n".join(lines)
        
        logger.debug(f"Prometheus metrics scrape: {len(current_metrics)} targets, {sum(len(m.get('ping_times', [])) for m in current_metrics.values())} ping samples, {len(disconnect_by_period)} disconnect metrics")
        
        return app.response_class(
            response=metrics_text,
            status=200,
            mimetype='text/plain; version=0.0.4; charset=utf-8'
        )
    except Exception as e:
        logger.error(f"Error generating metrics: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/report/statistics', methods=['POST'])
def report_statistics():
    """
    Endpoint for PingIT to report per-target statistics.
    
    Expected JSON payload:
    {
        "target_name": "google_dns",
        "host": "8.8.8.8",
        "total_pings": 100,
        "successful_pings": 98,
        "failed_pings": 2,
        "success_rate": 98.0,
        "avg_response_time": 25.5,
        "min_response_time": 20.1,
        "max_response_time": 35.2,
        "last_status": 1
    }
    """
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['target_name', 'host', 'total_pings', 'successful_pings', 
                          'failed_pings', 'success_rate']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        # Update in-memory metrics cache for Prometheus
        target_name = data['target_name']
        host = data['host']
        avg_response_time = data.get('avg_response_time', 0)
        last_status = data.get('last_status', 1)
        timestamp_ms = int(time.time() * 1000)
        
        # Record ping times in milliseconds (convert from seconds)
        if avg_response_time:
            metrics_cache.update_ping_time(target_name, host, avg_response_time * 1000)
        
        # Update status
        metrics_cache.update_status(target_name, host, last_status)
        
        # Store in database for historical analysis
        with sqlite_lock:
            cursor = sqlite_conn.cursor()
            cursor.execute('''
                INSERT INTO ping_statistics 
                (target_name, host, total_pings, successful_pings, failed_pings, 
                 success_rate, avg_response_time, min_response_time, max_response_time, last_status, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                target_name,
                host,
                data['total_pings'],
                data['successful_pings'],
                data['failed_pings'],
                data['success_rate'],
                avg_response_time,
                data.get('min_response_time'),
                data.get('max_response_time'),
                last_status,
                timestamp_ms
            ))
            
            sqlite_conn.commit()
        
        logger.debug(f"Recorded statistics for {target_name}: "
                    f"success_rate={data['success_rate']}%, failed={data['failed_pings']}")
        
        return jsonify({
            'status': 'success',
            'message': f"Statistics recorded for {target_name}"
        }), 201
    
    except Exception as e:
        logger.error(f"Error reporting statistics: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/report/disconnects', methods=['POST'])
def report_disconnects():
    """
    Endpoint for PingIT to report disconnect events.
    
    Expected JSON payload:
    {
        "target_name": "google_dns",
        "host": "8.8.8.8",
        "disconnect_time": "2024-01-15T10:05:42.123456",
        "duration_seconds": 30,
        "reason": "Connection timeout"
    }
    """
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['target_name', 'host', 'disconnect_time']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        target_name = data['target_name']
        host = data['host']
        disconnect_time_ms = normalize_timestamp_ms(data['disconnect_time'])
        recorded_at_ms = int(time.time() * 1000)
        
        # Update in-memory metrics cache for Prometheus
        metrics_cache.increment_disconnect(target_name, host)
        
        # Store in database for historical analysis
        with sqlite_lock:
            cursor = sqlite_conn.cursor()
            cursor.execute('''
                INSERT INTO disconnect_times 
                (target_name, host, disconnect_time, duration_seconds, reason, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                target_name,
                host,
                disconnect_time_ms,
                data.get('duration_seconds'),
                data.get('reason'),
                recorded_at_ms
            ))
            
            sqlite_conn.commit()
        
        logger.info(f"Recorded disconnect for {target_name}: {data['disconnect_time']}")
        
        return jsonify({
            'status': 'success',
            'message': f"Disconnect recorded for {target_name}"
        }), 201
    
    except Exception as e:
        logger.error(f"Error reporting disconnect: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/statistics/<target_name>', methods=['GET'])
def get_target_statistics(target_name):
    """
    Internal endpoint to retrieve statistics for a specific target.
    Used by PingIT or other internal services.
    """
    try:
        with sqlite_lock:
            cursor = sqlite_conn.cursor()
            cursor.execute('''
                SELECT * FROM ping_statistics
                WHERE target_name = ?
                ORDER BY timestamp DESC
                LIMIT 1
            ''', (target_name,))
            
            row = cursor.fetchone()
        
        if not row:
            return jsonify({'error': f'No statistics found for {target_name}'}), 404
        
        result = {
            'target_name': row['target_name'],
            'host': row['host'],
            'total_pings': row['total_pings'],
            'successful_pings': row['successful_pings'],
            'failed_pings': row['failed_pings'],
            'success_rate': row['success_rate'],
            'avg_response_time': row['avg_response_time'],
            'min_response_time': row['min_response_time'],
            'max_response_time': row['max_response_time'],
            'last_status': row['last_status'],
            'timestamp': row['timestamp']
        }
        
        return jsonify(result), 200
    
    except Exception as e:
        logger.error(f"Error retrieving statistics: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/disconnects/<target_name>', methods=['GET'])
def get_target_disconnects(target_name):
    """
    Internal endpoint to retrieve disconnect events for a specific target.
    Used by PingIT or other internal services.
    """
    try:
        with sqlite_lock:
            cursor = sqlite_conn.cursor()
            cursor.execute('''
                SELECT * FROM disconnect_times
                WHERE target_name = ?
                ORDER BY disconnect_time DESC
                LIMIT 100
            ''', (target_name,))
            
            rows = cursor.fetchall()
        
        result = []
        for row in rows:
            result.append({
                'target_name': row['target_name'],
                'host': row['host'],
                'disconnect_time': row['disconnect_time'],
                'duration_seconds': row['duration_seconds'],
                'reason': row['reason'],
                'recorded_at': row['timestamp']
            })
        
        return jsonify({
            'target_name': target_name,
            'disconnect_count': len(result),
            'disconnects': result
        }), 200
    
    except Exception as e:
        logger.error(f"Error retrieving disconnects: {e}")
        return jsonify({'error': str(e)}), 500


class HTTPToHTTPSRedirectHandler(BaseHTTPRequestHandler):
    """HTTP handler that redirects HTTP requests to HTTPS on the correct port.
    
    Handles Test 1: HTTP on 7030 → HTTPS 7443 (301 redirect)
    Note: Test 4 (HTTPS on 7030) cannot be handled due to TLS handshake occurring before HTTP parsing.
    """
    
    https_port = 7443
    
    def do_GET(self):
        """Handle GET requests by redirecting to HTTPS."""
        self.send_response(301)
        host = self.headers.get('Host', 'localhost')
        host = host.split(':')[0]  # Remove any existing port
        https_url = f'https://{host}:{self.https_port}{self.path}'
        self.send_header('Location', https_url)
        self.end_headers()
    
    def do_HEAD(self):
        """Handle HEAD requests."""
        self.do_GET()
    
    def do_POST(self):
        """Handle POST requests."""
        self.do_GET()
    
    def do_PUT(self):
        """Handle PUT requests."""
        self.do_GET()
    
    def do_DELETE(self):
        """Handle DELETE requests."""
        self.do_GET()
    
    def log_message(self, format, *args):
        """Suppress logging of redirect requests."""
        pass


class HTTPSRedirectHandler(BaseHTTPRequestHandler):
    """Handler for HTTPS requests that redirects to HTTPS on correct port."""
    
    https_port = 7443
    
    def do_GET(self):
        """Handle GET requests by redirecting to HTTPS on correct port."""
        self.send_response(301)
        host = self.headers.get('Host', 'localhost')
        host = host.split(':')[0]  # Remove any existing port
        https_url = f'https://{host}:{self.https_port}{self.path}'
        self.send_header('Location', https_url)
        self.end_headers()
    
    def do_HEAD(self):
        """Handle HEAD requests."""
        self.do_GET()
    
    def do_POST(self):
        """Handle POST requests."""
        self.do_GET()
    
    def do_PUT(self):
        """Handle PUT requests."""
        self.do_GET()
    
    def do_DELETE(self):
        """Handle DELETE requests."""
        self.do_GET()
    
    def log_message(self, format, *args):
        """Suppress logging."""
        pass


class SSLHTTPServer(HTTPServer):
    """HTTPServer with SSL support."""
    def __init__(self, host_port, handler, ssl_context=None):
        self.ssl_context = ssl_context
        try:
            super().__init__(host_port, handler)
        except OSError as e:
            if "Address already in use" in str(e):
                logger.debug(f"Port {host_port[1]} already in use (likely by HTTP server)")
            raise
    
    def finish_request(self, request, client_address):
        """Handle SSL wrapping if context provided."""
        if self.ssl_context:
            try:
                request = self.ssl_context.wrap_socket(request, server_side=True)
            except Exception:
                return  # Connection failed at TLS level
        return super().finish_request(request, client_address)


def start_http_redirect_server(http_port: int, https_port: int):
    """Start HTTP redirect server on http_port that redirects to HTTPS on https_port.
    
    Implements: Test 1 (HTTP on 7030 → HTTPS 7443 with 301 redirect)
    
    Note: HTTPS on HTTP port (Test 4) is not supported due to TLS handshake limitations.
    """
    try:
        HTTPToHTTPSRedirectHandler.https_port = https_port
        http_server = HTTPServer(('0.0.0.0', http_port), HTTPToHTTPSRedirectHandler)
        http_thread = threading.Thread(target=http_server.serve_forever, daemon=True)
        http_thread.start()
        logger.info(f"HTTP redirect server listening on port {http_port}, redirecting to HTTPS port {https_port}")
    except OSError as e:
        logger.error(f"Failed to start HTTP redirect server on port {http_port}: {e}")
        return None
    
    return http_server


def main():
    """Main entry point."""
    global logger, config, sqlite_conn, sqlite_db_path, prometheus_mode
    
    parser = argparse.ArgumentParser(description='PingIT Web Server')
    parser.add_argument('--test', '-t', action='store_true',
                       help='Run in test mode (reads config and db from current directory)')
    parser.add_argument('--migrate-timestamps', action='store_true',
                       help='Migrate timestamps from TEXT (ISO 8601) to INTEGER (Unix milliseconds), then exit')
    
    args = parser.parse_args()
    
    # Determine paths and load configuration
    if args.test:
        config_path = "./webserver-config.yaml"
        pingit_config_path = "./pingit-config.yaml"
        db_path = TEST_DB_PATH
        log_path = TEST_LOG_PATH
        log_level = "INFO"
        config = None
        listen_host = "0.0.0.0"
        port = DEFAULT_PORT
    else:
        config_path = DEFAULT_CONFIG_PATH
        pingit_config_path = "/etc/pingit/pingit-config.yaml"
        db_path = DEFAULT_DB_PATH
        log_path = DEFAULT_LOG_PATH
        log_level = "INFO"
        listen_host = "0.0.0.0"
        port = DEFAULT_PORT
    
    # Setup logging with initial level
    # Use default rolling settings for initial setup
    logger = setup_logging(log_path, log_level, 
                         max_bytes=10485760, backup_count=10, retention_days=7)
    logger.debug(f"PingIT Web Server starting... (test_mode={args.test})")
    
    try:
        # Load configuration (skip in test mode)
        if not args.test:
            config = load_config(config_path)
            logger.debug(f"Configuration loaded from {config_path}")
            
            # Get log configuration from config
            logging_config = config.get('logging', {})
            config_log_level = logging_config.get('level', 'INFO')
            config_log_path = logging_config.get('path', log_path)
            max_bytes = logging_config.get('max_size_mb', 10) * 1024 * 1024  # Convert MB to bytes
            backup_count = logging_config.get('backup_count', 10)
            retention_days = logging_config.get('retention_days', 7)
            
            if (config_log_level.upper() != log_level.upper() or 
                config_log_path != log_path):
                log_level = config_log_level
                log_path = config_log_path
                logger = setup_logging(log_path, log_level, max_bytes, backup_count, retention_days)
                logger.info(f"Logging configured: level={log_level}, path={log_path}, "
                          f"max_size={max_bytes//1024//1024}MB, backups={backup_count}, retention={retention_days}d")
            
            # Get webserver settings from config
            # 'listen_host' in config is for server binding (0.0.0.0 = all interfaces)
            listen_host = config.get('webserver', {}).get('listen_host', '0.0.0.0')
            port = config.get('webserver', {}).get('port', DEFAULT_PORT)
            
            # Get database path from config
            config_db_path = config.get('database', {}).get('path')
            if config_db_path and config_db_path != db_path:
                db_path = config_db_path
                logger.info(f"Database path changed to {db_path}")
            
            # Get metrics configuration (Prometheus mode)
            metrics_config = config.get('metrics', {})
            prometheus_mode = metrics_config.get('prometheus_mode', False)
            logger.info(f"Prometheus mode: {prometheus_mode}")
            
            logger.info(f"Configuration: listen_host={listen_host}, port={port}, db_path={db_path}, log_path={log_path}, prometheus_mode={prometheus_mode}")
        else:
            logger.debug("Running in test mode - no config file loaded")
        
        # Connect to SQLite database
        sqlite_db_path = db_path
        sqlite_conn = connect_sqlite(sqlite_db_path)
        ensure_schema(sqlite_conn)
        
        # Handle timestamp migration if requested
        if args.migrate_timestamps:
            logger.info("Timestamp migration requested via --migrate-timestamps flag")
            migrate_timestamps_to_epoch(sqlite_conn)
            logger.info("Migration complete. Exiting.")
            exit(0)
        
        # Initialize admin manager with both webserver config (SSL settings) and pingit config (targets)
        init_admin_manager(sqlite_db_path, config_path, pingit_config_path, args.test)
        
        # Start Flask app
        logger.info(f"Starting web server on {listen_host}:{port}")
        logger.info(f"Using SQLite database: {sqlite_db_path}")
        
        # Configure Werkzeug logger to only show DEBUG level messages
        import logging as log_module
        werkzeug_logger = log_module.getLogger('werkzeug')
        if log_level.upper() == 'DEBUG':
            werkzeug_logger.setLevel(log_module.DEBUG)
        else:
            werkzeug_logger.setLevel(log_module.WARNING)
        
        # Check for SSL configuration
        ssl_context = None
        if not args.test:
            ssl_config = config.get('ssl', {})
            ssl_enabled = ssl_config.get('enabled', False)
            if ssl_enabled:
                cert_file = ssl_config.get('certificate')
                key_file = ssl_config.get('private_key')
                ssl_port = config.get('webserver', {}).get('https_port', 443)
                
                if cert_file and key_file and os.path.exists(cert_file) and os.path.exists(key_file):
                    try:
                        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                        ssl_context.load_cert_chain(certfile=cert_file, keyfile=key_file)
                        logger.info(f"SSL enabled on port {ssl_port}")
                        logger.info(f"Certificate: {cert_file}")
                        logger.info(f"Private key: {key_file}")
                        logger.info(f"HTTP redirect server will listen on port {port} and redirect to HTTPS port {ssl_port}")
                        # Start HTTP redirect server
                        start_http_redirect_server(port, ssl_port)
                        # Run HTTPS server
                        app.run(host=listen_host, port=ssl_port, ssl_context=ssl_context, debug=False, threaded=True)
                    except Exception as e:
                        logger.error(f"Failed to load SSL certificate: {e}")
                        logger.warning("Running without SSL")
                        app.run(host=listen_host, port=port, debug=False, threaded=True)
                else:
                    if ssl_enabled:
                        logger.warning("SSL enabled but certificate/key not found")
                        logger.warning(f"Expected certificate: {cert_file}")
                        logger.warning(f"Expected key: {key_file}")
                    app.run(host=listen_host, port=port, debug=False, threaded=True)
            else:
                app.run(host=listen_host, port=port, debug=False, threaded=True)
        else:
            # Test mode - no SSL
            app.run(host=listen_host, port=port, debug=False, threaded=True)
    
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        exit(1)
    finally:
        if sqlite_conn:
            sqlite_conn.close()
            logger.info("Database connection closed")


if __name__ == '__main__':
    main()
