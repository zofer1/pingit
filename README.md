# PingIT - Network Monitoring Service with Web Dashboard

A production-ready Python service that continuously monitors network connectivity by pinging configured targets. Features a modern web dashboard for real-time status, statistical analysis, and historical data visualization. Runs as a systemd service on Linux and supports local testing on Windows/macOS.

## 🎯 Quick Start

**Development (Test Mode - Windows/macOS/Linux):**
```bash
# Activate virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# or
.\.venv\Scripts\Activate.ps1  # Windows PowerShell

# Install dependencies
pip install -r requirements.txt

# Terminal 1: Start web server
python webserver.py --test

# Terminal 2: Start ping service (after 3-4 seconds)
python pingit.py --test

# Access dashboard
open http://localhost:7030
```
> **Test Mode Files** (all in project directory - easily cleaned up):
>
> **Database & Config:**
> - `./pingit.db` - SQLite database with ping statistics and disconnect events
> - Config: Built-in defaults (no external config file needed in test mode)
>
> **Logs (auto-generated with timestamps):**
> - `./pingit-YYYY-MM-DD-HH-MM-SS.log` - PingIT service logs
> - `./webserver-YYYY-MM-DD-HH-MM-SS.log` - WebServer logs
>
> **Note:** No system configuration changes. Simply delete files to reset. In **production**, files are stored under `/etc/pingit/`, `/var/lib/pingit/`, and `/var/log/pingit/`.

**Production (Linux with Systemd):**
```bash
# Install and configure (requires root/sudo)
sudo bash setup.sh

# Edit PingIT configuration (optional)
sudo nano /etc/pingit/pingit-config.yaml

# Edit WebServer configuration (optional)
sudo nano /etc/pingit/webserver-config.yaml

# Start monitoring
sudo systemctl start pingit pingit-webserver
sudo systemctl enable pingit pingit-webserver

# View PingIT logs
sudo journalctl -u pingit -f

# View WebServer logs
sudo journalctl -u pingit-webserver -f
```

## ✨ Features

- **🎨 Web Dashboard**: Real-time monitoring with interactive graphs and statistics
- **📊 SQLite Database**: Persistent storage of ping statistics and disconnect events
- **📈 Historical Analytics**: Track response times, success rates, and uptime trends
- **🔔 Disconnect Detection**: Automatic detection and logging of network disconnects
- **📝 ECS Logging**: Structured JSON logs compatible with major observability platforms
- **⚙️ Flexible Configuration**: YAML-based configuration with multiple target support
- **🐧 Systemd Integration**: Runs as managed Linux service with auto-restart
- **🔐 Root Required**: Runs as root for ICMP socket creation (ping capability)
- **💻 Cross-Platform Testing**: Development mode supports Windows, macOS, and Linux
- **🔗 REST API**: Programmatic access to monitoring data via JSON API
- **📡 Prometheus Metrics**: Native Prometheus endpoint for Grafana, alerting, and time-series analysis

## 📋 Requirements

**Production (Linux):**
- **OS**: Linux with systemd (Ubuntu 18.04+, Debian 10+, CentOS 7+, Raspberry Pi OS, etc.)
  - Includes: Ubuntu, Debian, CentOS, Fedora, Raspberry Pi OS Trixie, and other systemd-based distributions
  - **Tested on**: Raspberry Pi 1 Model B Rev 2 with Raspberry Pi OS Trixie (Debian 13)
  - **Note**: Works on various architectures (ARM, x86_64, aarch64)
- **Systemd**: Required for service management and auto-restart
- **Python**: 3.8+
- **Root Access**: Required for installation and running (needed for ICMP socket creation)
- **Network**: Outbound ICMP ping capability
- **Ports**: 7030 (default web dashboard and API)

**Development (Any OS):**
- **OS**: Windows, macOS, or Linux
- **Python**: 3.8+
- **Network**: Outbound ICMP ping capability
- **Ports**: 7030 (for local testing)

## 🚀 Installation

### Linux with Systemd

Automated setup for production Linux deployments:

```bash
sudo bash setup.sh
```

This single command will:
1. Check system prerequisites (Python 3, pip3)
2. Auto-install missing system packages (build-essential, libffi-dev, python3-dev)
3. Check all Python dependencies from requirements.txt
4. Auto-install missing Python packages
5. Create directories (/opt/pingit, /etc/pingit, /var/lib/pingit, /var/log/pingit)
6. Copy application files (pingit.py, webserver.py, dashboard files)
7. Copy and create configuration files (pingit-config.yaml, webserver-config.yaml)
8. Install systemd service files (pingit.service, pingit-webserver.service)
9. Setup web dashboard (HTML, CSS, JavaScript files)
10. Configure ICMP socket capabilities for ping functionality

### Prerequisites Check

Setup script verifies:
- ✅ Running as root
- ✅ Python 3 installed
- ✅ pip3 installed
- ✅ Python packages available (PyYAML, icmplib, ecs-logging, Flask)

If any Python packages are missing, the script will:
1. List missing packages
2. Ask user for permission to install
3. Install via pip3 or fail with clear error

## ⚙️ Configuration

### Production Configuration

Location: `/etc/pingit/pingit-config.yaml`

```yaml
# Logging configuration
logging:
  level: INFO
  path: /var/log/pingit

# Ping service configuration
ping:
  interval: 2          # Seconds between ping cycles
  
reporting:
  interval: 10         # Report stats every 10 ping cycles (20 seconds)

# Ping targets configuration
targets:
  - name: google_dns
    host: 8.8.8.8
    timeout: 0.5       # Timeout per ping in seconds
  
  - name: cloudflare_dns
    host: 1.1.1.1
    timeout: 0.5
  
  - name: local_gateway
    host: 192.168.1.1
    timeout: 0.5
  
  - name: corporate_vpn
    host: vpn.company.com
    timeout: 0.5
```

Location: `/etc/pingit/webserver-config.yaml`

```yaml
# Web server configuration
logging:
  level: INFO
  path: /var/log/pingit

server:
  host: 0.0.0.0
  port: 7030              # HTTP port (default)
  ssl:
    enabled: false        # Set to true to enable HTTPS
    cert: /etc/pingit/ssl/cert.pem    # Path to SSL certificate
    key: /etc/pingit/ssl/key.pem      # Path to SSL private key
    port: 7443            # HTTPS port (default)

database:
  path: /var/lib/pingit/pingit.db
```

### Configuration Options

**Logging:**
- `level`: DEBUG, INFO, WARNING, ERROR (default: INFO)
- `path`: Log directory (default: /var/log/pingit)

**Ping Service:**
- `interval`: Seconds between ping cycles (default: 2)
- `reporting.interval`: Number of cycles before reporting (default: 10)

**Web Server:**
- `host`: Listen address (default: 0.0.0.0)
- `port`: HTTP port (default: 7030)
- `ssl.enabled`: Enable HTTPS (default: false)
- `ssl.cert`: Path to SSL certificate (default: /etc/pingit/ssl/cert.pem)
- `ssl.key`: Path to SSL private key (default: /etc/pingit/ssl/key.pem)
- `ssl.port`: HTTPS port (default: 7443)

**Database:**
- `path`: SQLite database file location

**Targets:**
- `name`: Display name for this target
- `host`: IP address or hostname to ping
- `timeout`: Seconds to wait for response per ping

## 🔄 Service Management

### Production Mode (Linux Systemd)

```bash
# Start services
sudo systemctl start pingit
sudo systemctl start pingit-webserver

# Stop services
sudo systemctl stop pingit
sudo systemctl stop pingit-webserver

# Restart services
sudo systemctl restart pingit pingit-webserver

# Check status
sudo systemctl status pingit
sudo systemctl status pingit-webserver

# Enable auto-start on boot
sudo systemctl enable pingit
sudo systemctl enable pingit-webserver

# Disable auto-start
sudo systemctl disable pingit
sudo systemctl disable pingit-webserver
```

### Web Dashboard

Access the web dashboard at `http://localhost:7030` (default port) for:
- **Real-time Status**: Current ping status for all targets
- **Statistics**: Success rates, response times, uptime percentages
- **Historical Graphs**: Response time trends over time
- **Disconnect Events**: Log of all network disconnects with timestamps
- **Target Details**: Min/max/average response times per target

### 🛠️ Admin Dashboard

Access the admin dashboard at `http://localhost:7030/admin` to manage PingIT:
- **Target Management**: Add/remove ping targets
- **Logging Control**: Configure log levels and paths independently for each service
- **Service Control**: Start, stop, restart services with live status indicators
- **SSL Configuration**: Enable HTTPS and manage certificates
- **Prometheus Mode**: Toggle metrics collection
- **Test Data**: Generate sample data for testing
- **Database**: Backup or reset the database

For detailed admin dashboard documentation, see [ADMIN_DASHBOARD.md](ADMIN_DASHBOARD.md)

### 🔒 HTTPS/SSL Support

PingIT includes built-in support for HTTPS with self-signed SSL certificates.

**Setup SSL Certificates:**
```bash
# Generate self-signed SSL certificates (included scripts)
sudo bash /opt/pingit/raspberrypi-setup/setup-self-signed-ssl.sh
```

**What this script does:**
- ✅ Generates self-signed RSA 4096-bit certificate (365-day validity)
- ✅ Includes Subject Alternative Names (SANs) for:
  - Hostname: `raspberrypi` and `raspberrypi.local`
  - Localhost: `127.0.0.1`
  - IP Range: `10.10.0.0/24` subnet (all 256 IPs)
- ✅ Creates `/etc/pingit/ssl/` directory with:
  - `cert.pem` - SSL certificate
  - `key.pem` - Private key
  - `ca.pem` - CA certificate
- ✅ Automatically updates webserver configuration to use HTTPS

**Access Dashboard via HTTPS:**
```bash
# After SSL setup is complete (uses port 7443 by default)
https://localhost:7443
https://raspberrypi.local:7443
https://10.10.0.<your-ip>:7443
```

**Browser Certificate Warning:**
- Self-signed certificates will show a warning (expected)
- Click "Advanced" → "Proceed anyway" or add the certificate to your trust store
- For mobile devices: Export `ca.pem` and add to device's trusted certificates for green lock icon

**Manual HTTPS Configuration:**
Edit `/etc/pingit/webserver-config.yaml`:
```yaml
server:
  host: 0.0.0.0
  port: 7030              # HTTP port
  ssl:
    enabled: true         # Enable HTTPS
    cert: /etc/pingit/ssl/cert.pem
    key: /etc/pingit/ssl/key.pem
    port: 7443            # HTTPS port (standard)
```

Then restart the service:
```bash
sudo systemctl restart pingit-webserver
```

## 📝 Logging

### Logging Configuration

PingIT uses **ECS (Elastic Common Schema) JSON logging** for all output, making logs machine-readable and compatible with modern observability platforms.

**Logging Settings (in config files - both PingIT and WebServer):**
```yaml
logging:
  level: INFO          # DEBUG, INFO, WARNING, ERROR (configurable per service)
  path: /var/log/pingit  # Production: /var/log/pingit | Test: ./
```

### Log Locations

**Development Mode (Test):**
- 📁 Location: Current project directory
- 📄 Files: `pingit-YYYY-MM-DD.log`, `webserver-YYYY-MM-DD.log`
- 🔄 Rotation: Automatic when file reaches 10 MB
- 📦 Retention: Keeps up to 10 rotated log files

**Production Mode (Linux):**
- 📁 Location: `/var/log/pingit/`
- 📄 PingIT logs: `pingit-YYYY-MM-DD.log`
- 📄 WebServer logs: `webserver-YYYY-MM-DD.log`
- 🔄 Rotation: Automatic when file reaches 10 MB
- 📦 Retention: Keeps up to 10 rotated log files (7 days)
- 📊 SystemD: Also captured via `journalctl`

### Viewing Logs

**Development Mode:**
```bash
# Follow PingIT logs in real-time via systemd
sudo journalctl -u pingit -f

# Follow WebServer logs in real-time via systemd
sudo journalctl -u pingit-webserver -f

# Show last 50 lines
sudo journalctl -u pingit -n 50

# Show since specific time
sudo journalctl -u pingit --since "1 hour ago"

# View raw log files directly (ECS JSON format)
sudo tail -f /var/log/pingit/pingit-*.log
sudo tail -f /var/log/pingit/webserver-*.log

# Parse and pretty-print ECS JSON logs
sudo cat /var/log/pingit/pingit-*.log | jq '.'
sudo cat /var/log/pingit/webserver-*.log | jq '.'
```

### ECS Log Format

All logs are in **ECS (Elastic Common Schema) JSON format** for structured logging:

```json
{
  "@timestamp": "2025-01-15T10:05:42.123456Z",
  "log.level": "info",
  "log.logger": "pingit",
  "message": "Pinging google_dns (8.8.8.8)...",
  "ecs.version": "8.0.0",
  "service": {
    "name": "pingit"
  }
}
```

**Benefits:**
- ✅ **Machine-readable** - Easily parsed and filtered
- ✅ **Structured data** - All fields consistently named
- ✅ **Searchable** - Query by timestamp, level, logger, message

### Log Levels

Log levels can be configured independently for both PingIT and WebServer services:

| Level | Use Case | Output |
|-------|----------|--------|
| **DEBUG** | Development & troubleshooting | Verbose output, every ping, detailed system info |
| **INFO** | Production (recommended) | Important events, service start/stop, disconnects |
| **WARNING** | Reduced logging | Only warnings and errors |
| **ERROR** | Minimal logging | Only errors |

**Set log level in PingIT config** (`pingit-config.yaml`):
```yaml
logging:
  level: DEBUG    # Change to DEBUG for development
```

**Set log level in WebServer config** (`webserver-config.yaml`):
```yaml
logging:
  level: INFO     # Separate control for WebServer
```

## 📡 Data Storage

### SQLite Database

PingIT uses a local SQLite database to store:
- **Ping Statistics**: Per-target statistics (success rate, response times, etc.)
- **Disconnect Events**: When each target went down and came back up
- **Response Time History**: All ping response times for trend analysis

Database location:
- **Development**: `./pingit.db`
- **Production**: `/var/lib/pingit/pingit.db`

### Prometheus Metrics Endpoint

PingIT exposes a **Prometheus-compatible metrics endpoint** for integration with Prometheus, Grafana, and other observability platforms.

**Access Metrics:**
```
GET http://localhost:7030/metrics
```

**Available Metrics:**

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `pingit_ping_time_ms` | Gauge | `target_name`, `host` | Average ping response time in milliseconds |
| `pingit_disconnect_events_total` | Counter | `target_name`, `host` | Total disconnect events since last scrape |

**Example Prometheus Configuration:**

Add to your `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: 'pingit'
    static_configs:
      - targets: ['localhost:7030']
    scrape_interval: 15s      # Scrape every 15 seconds
    metrics_path: '/metrics'   # Prometheus metrics endpoint
```

## 🔐 Security

### Root Privileges

**Why Root is Required:**
- 🔐 **ICMP Socket Creation**: Creating raw ICMP sockets for ping functionality requires root privileges
- PingIT must run with root to send and receive ICMP echo packets
- This is a fundamental requirement of the underlying `icmplib` library

**Production Mode (Linux):**
- ⚠️ Runs as `root` (required for ICMP)
- `systemctl start pingit` automatically runs with root privileges
- All operations have system-wide access

**Test Mode (Development):**
- Must run with `sudo` to enable ICMP functionality
- Without sudo: `python pingit.py --test` will fail on ping operations
- With sudo: `sudo python pingit.py --test` works correctly
- **Note**: Test mode will only work when sudo is used

### File Permissions

```
/opt/pingit/                      755  (rwxr-xr-x)  root:root
/etc/pingit/                      755  (rwxr-xr-x)  root:root
/var/lib/pingit/                  755  (rwxr-xr-x)  root:root
/var/log/pingit/                  755  (rwxr-xr-x)  root:root
/etc/pingit/pingit-config.yaml    644  (rw-r--r--)  root:root
/etc/pingit/webserver-config.yaml 644  (rw-r--r--)  root:root
/var/lib/pingit/pingit.db         644  (rw-r--r--)  root:root
```

All files are owned by root with appropriate read/write permissions.

## 📁 File Structure

```
/opt/pingit/
  └── pingit.py              # Main application

/etc/pingit/
  └── config.yaml            # Configuration file

/var/log/pingit/
  └── pingit.log             # Application logs

/etc/systemd/system/
  └── pingit.service         # systemd service

Service runs as:
  └── root                   # Required for ICMP socket access
```

## 📦 Dependencies

All dependencies are listed in `requirements.txt` and automatically installed during setup.

**Backend Dependencies (Python):**

- **PyYAML** (6.0+) - YAML configuration file parsing
- **icmplib** (3.0.0+) - Pure Python ICMP pinging library
- **Flask** (2.0+) - Web framework for dashboard and API
- **ecs-logging** (2.0.0+) - ECS structured logging
- **requests** (2.28.0+) - HTTP client for service communication
- **prometheus-client** (0.16.0+) - Prometheus metrics exposition library

**Frontend Dependencies (Dashboard):**

- **Chart.js** (3.9.1+) - Interactive charts and graphs for data visualization
  - Loaded from CDN: `https://cdn.jsdelivr.net/npm/chart.js`
  - Used for: Response time trends, custom disconnect markers
  - Pure JavaScript library, no additional frontend build tools needed

**Automatic Installation:**
- Linux Production: `sudo bash setup.sh` installs all dependencies
- Development: `pip install -r requirements.txt` installs all dependencies

### ECS Structured Logging

PingIT uses ECS (Elastic Common Schema) logging format for all output. This provides:
- **Structured JSON logs** - Machine-readable log format
- **Standard field naming** - Compatible with log aggregation tools
- **Easy integration** - Works with Elasticsearch, Datadog, Splunk, CloudWatch
- **Better analysis** - Queryable fields enable advanced filtering and visualization

Example log entry:
```json
{
  "@timestamp": "2025-01-15T10:05:42.123456Z",
  "log.level": "info",
  "message": "Pinging target: google_dns (8.8.8.8)",
  "log.logger": "pingit",
  "service": {
    "name": "pingit",
    "version": "2.0.0"
  }
}
```

## 🧹 Uninstallation

**Development Mode (Remove local files):**
```bash
# Remove database and logs
rm -f pingit.db
rm -f pingit-*.log webserver-*.log

# Remove virtual environment (optional)
rm -rf .venv
```

**Production Mode (Linux):**
```bash
# Stop services
sudo systemctl stop pingit pingit-webserver
sudo systemctl disable pingit pingit-webserver

# Uninstall (prompts for what to remove)
sudo bash uninstall.sh

# Or manual uninstall:
sudo rm -rf /opt/pingit /etc/pingit /var/lib/pingit /var/log/pingit
sudo rm -f /etc/systemd/system/pingit.service /etc/systemd/system/pingit-webserver.service
sudo userdel -r pingit  # Remove system user
sudo systemctl daemon-reload
```

## 📜 License

MIT License - Free for personal and commercial use

**Attribution appreciated!** If you find PingIT useful, please consider supporting the project:
- 💝 **PayPal**: [Support via PayPal](https://paypal.me/zofer@hotmail.com)
- ⭐ **GitHub**: Star this repository to show your support
- 🐛 **Contribute**: Submit issues and pull requests to help improve the project

See LICENSE file for full license details.

### Code Structure

**Main Components:**
- `pingit.py` - Ping service daemon (~430 lines)
  - Ping execution in threads
  - Statistics tracking
  - Disconnect detection
  - ECS logging

- `webserver.py` - Web server and API (~874 lines)
  - Flask web server
  - Dashboard serving
  - REST API endpoints
  - SQLite database interaction

**Configuration & Setup:**
- `setup.sh` - Linux installation script
- `uninstall.sh` - Linux uninstallation script
- `pingit-config.yaml` - Ping service configuration
- `webserver-config.yaml` - Web server configuration

**Frontend:**
- `templates/dashboard.html` - Dashboard HTML template
- `static/dashboard.css` - Dashboard styles
- `static/dashboard.js` - Dashboard JavaScript

**Documentation:**
- `README.md` - This file
- `OPERATION_GUIDE.md` - Operations and troubleshooting
- `LICENSE` - MIT License

## 🙏 Acknowledgments

This project uses excellent open-source libraries:
- [Flask](https://flask.palletsprojects.com/) - Web framework
- [Chart.js](https://www.chartjs.org/) - Interactive charting library
- [icmplib](https://github.com/ValvaSoft/icmplib) - ICMP ping library
- [ecs-logging](https://github.com/elastic/ecs-logging-python) - Structured logging

---

**Project Status**: ✅ Production Ready  
**Latest Version**: 1.0.0  
**Platform**: Linux (production) | Windows/macOS/Linux (development)  
**Python**: 3.8+  
**Database**: SQLite  
**Web Framework**: Flask  
**API**: REST JSON API  
**Log Format**: ECS (Elastic Common Schema)
