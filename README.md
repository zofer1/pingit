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

### Development Mode (Local Testing)

Perfect for development, testing, and cross-platform use. **Test mode uses local files in the project directory - no system-wide installation needed.**

```bash
# Clone the repository
git clone https://github.com/yourusername/pingit.git
cd pingit

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate          # Linux/macOS
# or
.\.venv\Scripts\Activate.ps1      # Windows PowerShell

# Install dependencies
pip install -r requirements.txt

# Start services in two terminals
# Terminal 1: WebServer
python webserver.py --test

# Terminal 2: PingIT (wait 3-4 seconds)
python pingit.py --test

# Access dashboard at http://localhost:7030
```

**Test Mode Features:**
- 📁 **Local Database**: `./pingit.db` in project directory
- 📝 **Local Logs**: `pingit-YYYY-MM-DD-HH-MM-SS.log` in project directory
- ⚙️ **Hardcoded Config**: Uses default in-memory configuration (no config file needed)
- 🔄 **Default Targets**: Monitors 4 common targets (Google DNS, Cloudflare, etc.)
- 💾 **No System Changes**: All data stays in project folder
- 🗑️ **Easy Cleanup**: Just delete project folder or `rm pingit.db` to reset

### Production Installation (Linux with Systemd)

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

### Development Mode (Test)

Test mode uses **local files in the project directory** - no system-wide configuration needed!

**Locations (all in project root):**
- 📁 **Database**: `./pingit.db` (local SQLite file)
- 📝 **Logs**: `./pingit-YYYY-MM-DD-HH-MM-SS.log` and `./webserver-YYYY-MM-DD-HH-MM-SS.log`
- 🌐 **Web Server**: `http://localhost:7030`
- ⚙️ **Config**: Built-in defaults (no external file needed)

**Default Configuration:**
- Ping Interval: 2 seconds
- Default Targets: 4 targets (Google DNS, Cloudflare, etc.)
- Log Level: INFO
- Auto-refresh Dashboard: Every 60 seconds

**Running Test Mode:**
```bash
python webserver.py --test    # Uses local ./pingit.db
python pingit.py --test       # Writes to ./pingit-*.log
```

Everything stays in your project folder. No system changes, no installation required!

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

### Development Mode (Test)

```bash
# Terminal 1: Start web server
cd C:\projects\general\pingit
.\.venv\Scripts\Activate.ps1  # Windows, or use source for Linux/macOS
python webserver.py --test

# Terminal 2: Start ping service (after 3-4 seconds)
python pingit.py --test

# Stop all services
Get-Process python* | Stop-Process -Force  # Windows PowerShell
# or
pkill python  # Linux/macOS
```

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

**Logging Settings (in config files):**
```yaml
logging:
  level: INFO          # DEBUG, INFO, WARNING, ERROR
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
# View latest PingIT log (Windows PowerShell)
Get-ChildItem pingit-*.log | Sort-Object LastWriteTime -Descending | Select-Object -First 1 | ForEach-Object { Get-Content $_ }

# View latest WebServer log (Windows PowerShell)
Get-ChildItem webserver-*.log | Sort-Object LastWriteTime -Descending | Select-Object -First 1 | ForEach-Object { Get-Content $_ }

# Or on Linux/macOS
tail -f pingit-*.log
tail -f webserver-*.log
```

**Production Mode (Linux):**
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

# Parse and pretty-print ECS JSON logs
sudo cat /var/log/pingit/pingit-*.log | jq '.'
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

| Level | Use Case | Output |
|-------|----------|--------|
| **DEBUG** | Development & troubleshooting | Verbose output, every ping, detailed system info |
| **INFO** | Production (recommended) | Important events, service start/stop, disconnects |
| **WARNING** | Reduced logging | Only warnings and errors |
| **ERROR** | Minimal logging | Only errors |

**Set log level in config:**
```yaml
logging:
  level: DEBUG    # Change to DEBUG for development
```

## 📡 Data Storage & API

### SQLite Database

PingIT uses a local SQLite database to store:
- **Ping Statistics**: Per-target statistics (success rate, response times, etc.)
- **Disconnect Events**: When each target went down and came back up
- **Response Time History**: All ping response times for trend analysis

Database location:
- **Development**: `./pingit.db`
- **Production**: `/var/lib/pingit/pingit.db`

### REST API

The web server exposes a REST API for programmatic access to monitoring data:

```
GET http://localhost:7030/api/data
```

Returns current statistics and dashboard data in JSON format. This can be used for:
- Custom dashboards
- Integration with other systems
- Data export
- Monitoring automation

### Prometheus Metrics Endpoint

PingIT exposes a **Prometheus-compatible metrics endpoint** for integration with Prometheus, Grafana, and other observability platforms. Metrics are held **in-memory** for performance, collected from live ping data, and cleared after each Prometheus scrape.

**Access Metrics:**
```
GET http://localhost:7030/metrics
```

**Available Metrics:**

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `pingit_ping_time_ms` | Gauge | `target_name`, `host` | Average ping response time in milliseconds |
| `pingit_disconnect_events_total` | Counter | `target_name`, `host` | Total disconnect events since last scrape |

**Key Features:**
- ✅ **In-Memory Storage** - No database queries, fast scraping
- ✅ **Auto-Clearing** - Metrics cleared after each Prometheus scrape (drain pattern)
- ✅ **Thread-Safe** - Safe concurrent access from multiple threads
- ✅ **Lightweight** - ~100 KB base + per-target overhead
- ✅ **Real-Time** - Fresh data from live ping collection

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

**Example Prometheus Queries:**

```promql
# Current ping time for all targets
pingit_ping_time_ms

# Ping time for specific target
pingit_ping_time_ms{target_name="google_dns"}

# Disconnect rate (events per minute)
rate(pingit_disconnect_events_total[1m])

# Total disconnects by target
pingit_disconnect_events_total

# Combine with other metrics
pingit_ping_time_ms * 2  # Highlight slow targets
```

**Benefits:**

- ✅ **Real-time Monitoring** - Scrape metrics every 15+ seconds
- ✅ **Grafana Integration** - Build custom dashboards
- ✅ **Alerting** - Set up alerts based on connectivity metrics
- ✅ **Time-series Data** - Historical trend analysis
- ✅ **Multi-target Support** - Monitor all targets in one place


## 🎯 Use Cases

### Home Network Monitoring

Monitor internet connectivity, local network devices, and gateways:

```yaml
targets:
  - name: router
    host: 192.168.1.1
    timeout: 0.5
  
  - name: internet_gateway
    host: 8.8.8.8
    timeout: 0.5
  
  - name: nas_server
    host: 192.168.1.50
    timeout: 0.5
```

### Corporate VPN/Network

Monitor critical infrastructure, VPN connectivity, and external services:

```yaml
targets:
  - name: corporate_vpn
    host: vpn.company.com
    timeout: 1.0
  
  - name: office_gateway
    host: 10.0.0.1
    timeout: 0.5
  
  - name: dns_primary
    host: 10.0.0.10
    timeout: 0.5
```

### Data Center/Cloud Monitoring

Track multiple regions and infrastructure components:

```yaml
targets:
  - name: core_switch_1
    host: 10.0.0.1
    timeout: 0.3
  
  - name: firewall_primary
    host: 10.0.1.1
    timeout: 0.3
  
  - name: aws_endpoint
    host: ec2.us-east-1.amazonaws.com
    timeout: 1.0
  
  - name: azure_endpoint
    host: management.azure.com
    timeout: 1.0
```


## 🐛 Troubleshooting

### Development Mode Issues

**Services Won't Start**
```bash
# Check Python is installed
python --version

# Check virtual environment
Test-Path .venv  # Windows PowerShell

# Activate and verify dependencies
.\.venv\Scripts\Activate.ps1
pip list
```

**Port Already in Use**
```bash
# Check if port 7030 is available
netstat -ano | findstr :7030  # Windows
lsof -i :7030  # Linux/macOS

# Kill process using port or use a different port
python webserver.py --test 

**No Data Appearing**
- Wait 20-30 seconds for first data collection
- Check logs for errors: `Get-Content webserver-*.log -Tail 50`
- Ensure webserver started before pingit (3-4 second delay)

### Production Mode Issues

**Services Won't Start**

```bash
# Check status
sudo systemctl status pingit
sudo systemctl status pingit-webserver

# View recent logs
sudo journalctl -u pingit -n 50

# Check if port is available
sudo netstat -tlnp | grep 7030

# Test manually
sudo -u pingit python3 /opt/pingit/pingit.py --config /etc/pingit/pingit-config.yaml
```

**Permission Denied / ICMP Errors**

```bash
# Ensure all files are owned by root
sudo chown -R root:root /opt/pingit /etc/pingit /var/lib/pingit /var/log/pingit

# Set correct permissions
sudo chmod -R 755 /opt/pingit /etc/pingit /var/lib/pingit /var/log/pingit
sudo chmod 644 /etc/pingit/*.yaml
sudo chmod 644 /var/lib/pingit/pingit.db

# Restart services
sudo systemctl restart pingit pingit-webserver

# Verify running as root (should show User=root)
sudo systemctl show -p User pingit
```

**Web Dashboard Not Accessible**

```bash
# Check if WebServer is running
sudo systemctl status pingit-webserver

# Try to access dashboard
curl http://localhost:7030

# Check logs
sudo journalctl -u pingit-webserver -n 100
```

**No Data in Dashboard**

```bash
# Check both services are running
sudo systemctl status pingit pingit-webserver

# Verify database has data
sqlite3 /var/lib/pingit/pingit.db "SELECT COUNT(*) FROM ping_statistics;"

# Check logs for errors
sudo journalctl -u pingit -n 50
sudo journalctl -u pingit-webserver -n 50
```

**High CPU Usage**

```bash
# Check process and its CPU usage
ps aux | grep python

# Reduce ping frequency in config
sudo nano /etc/pingit/pingit-config.yaml
# Increase ping.interval value

# Restart service
sudo systemctl restart pingit
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
/opt/pingit/              755  (rwxr-xr-x)  root:root
/etc/pingit/              755  (rwxr-xr-x)  root:root
/var/lib/pingit/          755  (rwxr-xr-x)  root:root
/var/log/pingit/          755  (rwxr-xr-x)  root:root
/etc/pingit/config.yaml   644  (rw-r--r--)  root:root
```

All files are owned by root with appropriate read/write permissions.

### Web Dashboard Security

- Dashboard accessible via web interface
- Recommend restricting access via firewall or reverse proxy
- No sensitive data displayed (only counts and timings)
- Use HTTPS in production (see setup guides)

### Firewall Considerations

```bash
# Allow outbound ICMP (pings)
sudo ufw allow out proto icmp from any to any icmptype 8

# Allow web dashboard access (from your network)
sudo ufw allow from 192.168.1.0/24 to any port 7030
```

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

## 🚀 Performance

Typical resource usage (production with 4 targets):

- **CPU**: 1-3% (depends on ping frequency)
- **Memory**: 50-100MB (Flask ~20-30MB, Python runtime ~20-50MB)
- **Disk Growth**: 0.5-1MB per target per month (SQLite database)
- **Network**: ~100 bytes per ping (ICMP)
- **Dashboard**: ~2KB per data point
- **Query Performance**: Sub-second for all dashboard queries

**Scaling Guidelines:**
- For 10+ targets: Reduce log level to WARNING
- For 50+ targets: Consider separate monitoring for different groups
- For 100+ targets: Deploy multiple PingIT instances with dedicated configs

## 🔗 Integration

### Dashboard Integration

Access real-time data from PingIT through multiple interfaces:

1. **Web Dashboard** (built-in):
   - Access at `http://localhost:7030`
   - Real-time status and statistics
   - Historical graphs and trends
   - Disconnect events log

2. **REST API** (for custom integrations):
   - Endpoint: `http://localhost:7030/api/data`
   - Returns JSON formatted statistics
   - Can be used for custom dashboards or scripts

3. **Prometheus Metrics** (for observability platforms):
   - Endpoint: `http://localhost:7030/metrics`
   - Prometheus-compatible text format
   - Integration with Grafana for custom dashboards
   - Alert rules for automated notifications
   - Time-series data storage in Prometheus/VictoriaMetrics

### Grafana Integration Example

Create a Grafana dashboard to visualize PingIT metrics:

1. **Add Prometheus Data Source** in Grafana pointing to your Prometheus instance
2. **Create Panels** using these queries:
   - Success Rate: `pingit_ping_success_rate{target_name=~".*"}`
   - Response Time: `pingit_response_time_avg_ms{target_name=~".*"}`
   - Target Status: `pingit_target_status{target_name=~".*"}`
   - Disconnect Events: `rate(pingit_disconnect_events_total[5m])`

3. **Set Alerts** based on metrics:
   - Alert when target is down: `pingit_target_status == 0`
   - Alert on slow response: `pingit_response_time_avg_ms > 100`
   - Alert on low success: `pingit_ping_success_rate < 95`

## 📝 Version History

- **v1.0.0** - Initial release with web dashboard, SQLite backend, REST API, ECS logging, and disconnect detection

## 🆘 Getting Help

### Check Logs

```bash
sudo journalctl -u pingit -f
sudo tail -f /var/log/pingit/pingit.log
```

### Verify Setup

```bash
# Check PingIT service running
sudo systemctl status pingit

# Check WebServer service running
sudo systemctl status pingit-webserver

# Check dashboard access
curl http://localhost:7030

# Check API response
curl http://localhost:7030/api/data
```

### Common Issues

| Issue | Solution |
|-------|----------|
| Service won't start | Check logs, verify config syntax, ensure port 7030 available |
| Permission denied | Run `sudo chown -R pingit:pingit /etc/pingit /var/log/pingit` |
| Can't access dashboard | Verify both services running, check port 7030 is open |
| No data appearing | Wait 20+ seconds, check logs for errors |
| High memory usage | Reduce target count, increase ping intervals |

## 📜 License

MIT License - Free for personal and commercial use

**Attribution appreciated!** If you find PingIT useful, please consider supporting the project:
- 💝 **PayPal**: [Support via PayPal](https://paypal.me/zofer@hotmail.com)
- ⭐ **GitHub**: Star this repository to show your support
- 🐛 **Contribute**: Submit issues and pull requests to help improve the project

See LICENSE file for full license details.

## 👨‍💻 Development & Contributing

### Local Development

```bash
# Clone the repository
git clone https://github.com/yourusername/pingit.git
cd pingit

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
.\.venv\Scripts\Activate.ps1  # Windows

# Install in development mode
pip install -r requirements.txt

# Run tests
python -m pytest tests/  # If tests exist

# Start services in test mode
python webserver.py --test
python pingit.py --test
```

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

### Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

**Code Standards:**
- Follow PEP 8 for Python code
- Use type hints where appropriate
- Add docstrings to functions
- Test in both development and production modes

## 🎯 Getting Started

### Quick Start (Development)
```bash
git clone https://github.com/yourusername/pingit.git
cd pingit
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python webserver.py --test      # Terminal 1
python pingit.py --test          # Terminal 2 (after 3-4 seconds)
# Access http://localhost:7030
```

### Quick Start (Production Linux)
```bash
sudo bash setup.sh               # Automated installation
sudo systemctl start pingit pingit-webserver
sudo systemctl enable pingit pingit-webserver
# Access http://your-server:7030
```

## 📞 Support

- **Documentation**: See `OPERATION_GUIDE.md` for detailed operations
- **Issues**: Check GitHub Issues for known problems
- **Logs**: Check application logs for error details (see Troubleshooting section)

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
