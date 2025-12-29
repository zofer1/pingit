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
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict

import yaml
from flask import Flask, jsonify, request, render_template
import ecs_logging


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

# Global variables
sqlite_db_path: Optional[str] = None
sqlite_conn: Optional[sqlite3.Connection] = None
sqlite_lock = threading.Lock()  # Synchronization lock for SQLite operations
config = None
logger = None


def setup_logging(log_path: str = DEFAULT_LOG_PATH, level: str = "INFO"):
    """Set up ECS logging."""
    log_dir = Path(log_path)
    log_dir.mkdir(parents=True, exist_ok=True)
    
    logger = logging.getLogger("pingit-webserver")
    log_level = logging.DEBUG if level.upper() == "DEBUG" else logging.INFO
    logger.setLevel(log_level)
    
    # Remove any existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # Create log filename with date and time
    from datetime import datetime
    log_filename = f"webserver-{datetime.now().strftime('%Y-%m-%d-%H-%M-%S')}.log"
    
    # File handler with ECS formatter
    fh = logging.FileHandler(log_dir / log_filename)
    fh.setLevel(log_level)
    fh.setFormatter(ecs_logging.StdlibFormatter())
    
    # Console handler with ECS formatter
    ch = logging.StreamHandler()
    ch.setLevel(log_level)
    ch.setFormatter(ecs_logging.StdlibFormatter())
    
    logger.addHandler(fh)
    logger.addHandler(ch)
    
    return logger


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
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(target_name, timestamp)
            )
        ''')
        
        # Create disconnect_times table for recording disconnect events
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS disconnect_times (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_name TEXT NOT NULL,
                host TEXT NOT NULL,
                disconnect_time DATETIME NOT NULL,
                duration_seconds INTEGER,
                reason TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
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
        
        with sqlite_lock:
            cursor = sqlite_conn.cursor()
            
            # Get all statistics from the time range
            cursor.execute('''
                SELECT target_name, host, total_pings, successful_pings, failed_pings, 
                       success_rate, avg_response_time, min_response_time, max_response_time,
                       last_status
                FROM ping_statistics
                WHERE datetime(timestamp) > datetime('now', '-' || ? || ' hours', 'localtime')
                ORDER BY target_name
            ''', (hours_back,))
            
            stats_rows = cursor.fetchall()
            
            # Get aggregated disconnects by target in the time range
            cursor.execute('''
                SELECT target_name, host, COUNT(*) as disconnect_count, 
                       MAX(disconnect_time) as last_disconnect
                FROM disconnect_times
                WHERE datetime(substr(disconnect_time, 1, 19)) > datetime('now', '-' || ? || ' hours', 'localtime')
                GROUP BY target_name, host
                ORDER BY target_name
            ''', (hours_back,))
            
            disconnect_rows = cursor.fetchall()
            
            # Get time-series data for response time over time
            cursor.execute('''
                SELECT target_name, timestamp, avg_response_time, min_response_time, max_response_time
                FROM ping_statistics
                WHERE datetime(timestamp) > datetime('now', '-' || ? || ' hours', 'localtime')
                ORDER BY target_name, timestamp
            ''', (hours_back,))
            
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
            
            final_targets[target_name] = {
                'name': target_name,
                'host': data['host'],
                'pings': int(total),
                'success_rate': float(success_rate),
                'avg_response_time': round(float(avg_resp), 2),
                'min_response_time': round(float(min_resp), 2),
                'max_response_time': round(float(max_resp), 2),
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
            disconnects_data.append({
                'name': target_name,
                'host': row['host'],
                'disconnect_count': row['disconnect_count'],
                'last_disconnect': row['last_disconnect']
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
            
            raw_timeseries_data[target_name]['timestamps'].append(row['timestamp'])
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
            
            # Convert timestamps to milliseconds (Unix epoch) for X-axis
            timestamps_ms = [int(datetime.fromisoformat(ts.replace('Z', '+00:00')).timestamp() * 1000) 
                            for ts in data['timestamps']]
            
            # Create points with x (timestamp) and y (response time) for filtering
            points = [
                {'x': ts_ms, 'y': avg_time}
                for ts_ms, avg_time in zip(timestamps_ms, data['avg_response_times'])
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
        
        with sqlite_lock:
            cursor = sqlite_conn.cursor()
            cursor.execute('''
                INSERT INTO ping_statistics 
                (target_name, host, total_pings, successful_pings, failed_pings, 
                 success_rate, avg_response_time, min_response_time, max_response_time, last_status, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now', 'localtime'))
            ''', (
                data['target_name'],
                data['host'],
                data['total_pings'],
                data['successful_pings'],
                data['failed_pings'],
                data['success_rate'],
                data.get('avg_response_time'),
                data.get('min_response_time'),
                data.get('max_response_time'),
                data.get('last_status')
            ))
            
            sqlite_conn.commit()
        
        logger.debug(f"Recorded statistics for {data['target_name']}: "
                    f"success_rate={data['success_rate']}%, failed={data['failed_pings']}")
        
        return jsonify({
            'status': 'success',
            'message': f"Statistics recorded for {data['target_name']}"
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
        
        with sqlite_lock:
            cursor = sqlite_conn.cursor()
            cursor.execute('''
                INSERT INTO disconnect_times 
                (target_name, host, disconnect_time, duration_seconds, reason, timestamp)
                VALUES (?, ?, ?, ?, ?, datetime('now', 'localtime'))
            ''', (
                data['target_name'],
                data['host'],
                data['disconnect_time'],
                data.get('duration_seconds'),
                data.get('reason')
            ))
            
            sqlite_conn.commit()
        
        logger.info(f"Recorded disconnect for {data['target_name']}: {data['disconnect_time']}")
        
        return jsonify({
            'status': 'success',
            'message': f"Disconnect recorded for {data['target_name']}"
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


def main():
    """Main entry point."""
    global logger, config, sqlite_conn, sqlite_db_path
    
    parser = argparse.ArgumentParser(description='PingIT Web Server')
    parser.add_argument('--test', '-t', action='store_true',
                       help='Run in test mode (reads config and db from current directory)')
    
    args = parser.parse_args()
    
    # Determine paths and load configuration
    if args.test:
        config_path = "./webserver-config.yaml"
        db_path = TEST_DB_PATH
        log_path = TEST_LOG_PATH
        log_level = "INFO"
        config = None
        host = "0.0.0.0"
        port = DEFAULT_PORT
    else:
        config_path = DEFAULT_CONFIG_PATH
        db_path = DEFAULT_DB_PATH
        log_path = DEFAULT_LOG_PATH
        log_level = "INFO"
        host = "0.0.0.0"
        port = DEFAULT_PORT
    
    # Setup logging with initial level
    logger = setup_logging(log_path, log_level)
    logger.debug(f"PingIT Web Server starting... (test_mode={args.test})")
    
    try:
        # Load configuration (skip in test mode)
        if not args.test:
            config = load_config(config_path)
            logger.debug(f"Configuration loaded from {config_path}")
            
            # Get log level from config
            config_log_level = config.get('logging', {}).get('level', 'INFO')
            if config_log_level.upper() != log_level.upper():
                log_level = config_log_level
                logger = setup_logging(log_path, log_level)
                logger.info(f"Log level changed to {log_level}")
            
            # Get log path from config
            config_log_path = config.get('logging', {}).get('path', log_path)
            if config_log_path != log_path:
                log_path = config_log_path
                logger = setup_logging(log_path, log_level)
                logger.info(f"Log path changed to {log_path}")
            
            # Get webserver settings from config
            host = config.get('webserver', {}).get('host', '0.0.0.0')
            port = config.get('webserver', {}).get('port', DEFAULT_PORT)
            
            # Get database path from config
            config_db_path = config.get('database', {}).get('path')
            if config_db_path and config_db_path != db_path:
                db_path = config_db_path
                logger.info(f"Database path changed to {db_path}")
            
            logger.info(f"Configuration: host={host}, port={port}, db_path={db_path}, log_path={log_path}")
        else:
            logger.debug("Running in test mode - no config file loaded")
        
        # Connect to SQLite database
        sqlite_db_path = db_path
        sqlite_conn = connect_sqlite(sqlite_db_path)
        ensure_schema(sqlite_conn)
        
        # Start Flask app
        logger.info(f"Starting web server on {host}:{port}")
        logger.info(f"Using SQLite database: {sqlite_db_path}")
        app.run(host=host, port=port, debug=False, threaded=True)
    
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
