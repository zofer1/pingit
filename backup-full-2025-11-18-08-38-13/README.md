# PingIT - Linux Ping Service with Prometheus Monitoring

A production-ready Python service that continuously monitors network connectivity by pinging configured targets and exposing metrics to Prometheus. Runs as a systemd service on Linux.

## 🎯 Quick Start

```bash
# Install and configure (requires root/sudo)
sudo bash setup.sh

# Edit configuration (optional)
sudo nano /etc/pingit/config.yaml

# Start monitoring
sudo systemctl start pingit
sudo systemctl enable pingit

# View logs
sudo journalctl -u pingit -f

# Query results
python3 query_results.py --latest 10
```

## ✨ Features

- **Continuous Monitoring**: Ping multiple targets at configurable intervals (5s to 24h)
- **Prometheus Metrics**: Native Prometheus metrics export via HTTP endpoint
- **Systemd Integration**: Runs as managed Linux service with auto-restart
- **Comprehensive Logging**: File logs and syslog integration via journalctl
- **YAML Configuration**: Simple, readable configuration format
- **Response Time Tracking**: Measures and records latency per ping
- **Error Handling**: Graceful error handling with detailed error messages
- **Security**: Non-root user isolation, restricted file permissions
- **Metrics Export**: Real-time metrics via HTTP server (configurable port)

## 📋 Requirements

- **OS**: Linux (Ubuntu 18.04+, Debian 10+, CentOS 7+, etc.)
- **Python**: 3.7+
- **Root Access**: Required only for installation
- **Network**: Outbound ICMP ping capability

## 🚀 Installation

### Automated Setup (Recommended)

```bash
sudo bash setup.sh
```

This single command will:
1. Check system prerequisites (Python 3, pip3)
2. Auto-install missing system packages
3. Check all Python dependencies
4. Prompt to install missing Python packages
5. Create system user and directories
6. Install systemd service
7. Enable auto-start

### Prerequisites Check

Setup script verifies:
- ✅ Running as root
- ✅ Python 3 installed
- ✅ pip3 installed
- ✅ Python packages available (YAML, APScheduler, Prometheus Client, icmplib)

If any Python packages are missing, the script will:
1. List missing packages
2. Ask user for permission to install
3. Install via pip3 or fail with clear error

## ⚙️ Configuration

### Configuration File

Location: `/etc/pingit/config.yaml`

```yaml
# Logging configuration
logging:
  level: INFO
  path: /var/log/pingit

# Prometheus configuration
database:
  port: 8000  # Prometheus metrics HTTP server port

# Ping targets configuration
targets:
  - name: google_dns
    host: 8.8.8.8
    interval: 60        # Ping every 60 seconds
    timeout: 5          # 5 second timeout per ping
  
  - name: cloudflare_dns
    host: 1.1.1.1
    interval: 60
    timeout: 5
  
  - name: local_gateway
    host: 192.168.1.1
    interval: 30        # More frequent local pings
    timeout: 5
  
  - name: example_com
    host: example.com
    interval: 300       # Every 5 minutes
    timeout: 5
```

### Configuration Options

**Logging:**
- `level`: DEBUG, INFO, WARNING, ERROR (default: INFO)
- `path`: Log directory (default: /var/log/pingit)

**Database (Prometheus):**
- `port`: Prometheus metrics HTTP server port (default: 8000)

**Targets:**
- `name`: Display name for this target
- `host`: IP address or hostname to ping
- `interval`: Seconds between pings (default: 60)
- `timeout`: Seconds to wait for response (default: 5)

## 🔄 Service Management

### Start/Stop Services

```bash
# Start PingIT
sudo systemctl start pingit

# Stop PingIT
sudo systemctl stop pingit

# Restart PingIT
sudo systemctl restart pingit

# Check status
sudo systemctl status pingit

# Enable auto-start on boot
sudo systemctl enable pingit

# Disable auto-start
sudo systemctl disable pingit
```

### View Logs

Logs are output in **ECS (Elastic Common Schema)** JSON format for better integration with observability platforms.

```bash
# Follow logs in real-time
sudo journalctl -u pingit -f

# Show last 50 lines
sudo journalctl -u pingit -n 50

# Show since specific time
sudo journalctl -u pingit --since "1 hour ago"

# View app logs directly (ECS JSON format)
sudo tail -f /var/log/pingit/pingit.log

# Parse and view ECS logs nicely
sudo cat /var/log/pingit/pingit.log | jq '.'
```

### ECS Log Format

Logs are structured in ECS JSON format:

```json
{
  "log.level": "info",
  "message": "Pinging google_dns (8.8.8.8)...",
  "ecs.version": "8.0.0",
  "@timestamp": "2024-01-15T10:05:42.123456Z",
  "log.logger": "pingit",
  "service": {
    "name": "pingit"
  }
}
```

This format is compatible with:
- **Elasticsearch** - Ingest via Filebeat
- **Datadog** - Log aggregation and analysis
- **Splunk** - Structured log parsing
- **New Relic** - Log management
- **CloudWatch** - AWS log insights
- Any ECS-compatible log aggregation system

## 📊 Prometheus Metrics

PingIT exposes metrics via Prometheus HTTP endpoint for scraping.

### Accessing Metrics

Metrics are available at:

```
http://localhost:8000/metrics
```

The port is configurable in the `database.port` setting in `config.yaml`.

### Available Metrics

PingIT exposes the following Prometheus metrics:

- **`pingit_ping_success_total`** - Counter of successful pings (cumulative)
  - Labels: `target_name`, `host`
  
- **`pingit_ping_failure_total`** - Counter of failed pings (cumulative)
  - Labels: `target_name`, `host`
  
- **`pingit_ping_response_time_ms`** - Histogram of ping response times in milliseconds
  - Labels: `target_name`, `host`
  - Buckets: 1, 5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000ms
  
- **`pingit_ping_status`** - Gauge of current ping status (1 = up, 0 = down)
  - Labels: `target_name`, `host`

### Example Prometheus Configuration

Add this to your `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: 'pingit'
    static_configs:
      - targets: ['localhost:8000']
    scrape_interval: 15s
    scrape_timeout: 10s
```

### Querying Metrics

Example PromQL queries:

```promql
# Current status of all targets
pingit_ping_status

# Success rate for a specific target (last 1 hour)
increase(pingit_ping_success_total{target_name="google_dns"}[1h]) / 
(increase(pingit_ping_success_total{target_name="google_dns"}[1h]) + 
 increase(pingit_ping_failure_total{target_name="google_dns"}[1h]))

# Average response time
avg(rate(pingit_ping_response_time_ms_sum{target_name="google_dns"}[5m]) / 
    rate(pingit_ping_response_time_ms_count{target_name="google_dns"}[5m]))

# Failure rate
increase(pingit_ping_failure_total[1h])
```

### Grafana Integration

1. Add Prometheus as data source in Grafana
2. Create dashboard using the PromQL queries above
3. Set up alerts based on metrics
4. Visualize response times and uptime

### Example Grafana Dashboard Panels

**Panel 1: Current Status**
```promql
pingit_ping_status{job="pingit"}
```

**Panel 2: Success Rate (24h)**
```promql
sum(rate(pingit_ping_success_total[24h])) / (sum(rate(pingit_ping_success_total[24h])) + sum(rate(pingit_ping_failure_total[24h]))) * 100
```

**Panel 3: Response Time (p95)**
```promql
histogram_quantile(0.95, pingit_ping_response_time_ms)
```

## 📈 Monitoring Examples

### Home Network Monitoring

```yaml
targets:
  - name: router
    host: 192.168.1.1
    interval: 30
    timeout: 5
  
  - name: gateway_dns
    host: 8.8.8.8
    interval: 60
    timeout: 5
  
  - name: nas
    host: 192.168.1.50
    interval: 60
    timeout: 5
```

### Data Center Monitoring

```yaml
targets:
  - name: core_switch_1
    host: 10.0.0.1
    interval: 10
    timeout: 3
  
  - name: core_switch_2
    host: 10.0.0.2
    interval: 10
    timeout: 3
  
  - name: firewall_primary
    host: 10.0.1.1
    interval: 10
    timeout: 3
  
  - name: external_provider
    host: 203.0.113.1
    interval: 60
    timeout: 10
```

### External Services Monitoring

```yaml
targets:
  - name: github
    host: github.com
    interval: 300
    timeout: 10
  
  - name: aws_dns
    host: 8.8.8.8
    interval: 300
    timeout: 10
  
  - name: azure_dns
    host: 1.1.1.1
    interval: 300
    timeout: 10
```

## 🔍 Monitoring with Prometheus and Grafana

### Prometheus Server

Configure Prometheus to scrape PingIT metrics from `http://localhost:8000/metrics`.

For more details on setting up Prometheus, see the [Prometheus Configuration](#example-prometheus-configuration) section above.

### Grafana Dashboard

Create dashboards in Grafana using Prometheus as a data source:

1. **Uptime Dashboard**:
   - Current status for all targets
   - Success rate trends
   - Alert states

2. **Performance Dashboard**:
   - Response time distribution
   - P95/P99 latencies
   - Trend analysis

3. **Alerting**:
   - Set threshold alerts for down hosts
   - Alert on high response times
   - Slack/email notifications

## 🐛 Troubleshooting

### Service Won't Start

```bash
# Check status
sudo systemctl status pingit

# View recent logs
sudo journalctl -u pingit -n 50

# Test manually
sudo -u pingit python3 /opt/pingit/pingit.py --config /etc/pingit/config.yaml
```

### Permission Denied

```bash
# Fix ownership
sudo chown -R pingit:pingit /etc/pingit /var/log/pingit

# Fix permissions
sudo chmod 750 /etc/pingit /var/log/pingit
sudo chmod 644 /etc/pingit/config.yaml

# Restart
sudo systemctl restart pingit
```

### Metrics Not Available

```bash
# Check if PingIT is running
sudo systemctl status pingit

# Try to access metrics endpoint
curl http://localhost:8000/metrics

# Check config port setting
cat /etc/pingit/config.yaml | grep port

# Check logs for errors
sudo journalctl -u pingit -n 100
```

### No Data in Prometheus

```bash
# Check PingIT service is running
sudo systemctl status pingit

# Verify metrics are being exported
curl http://localhost:8000/metrics | head -20

# Check Prometheus scrape config
cat /etc/prometheus/prometheus.yml

# Check Prometheus logs
sudo systemctl status prometheus
```

### High CPU Usage

```bash
# Check process
ps aux | grep pingit

# Reduce ping frequency
sudo nano /etc/pingit/config.yaml
# Increase interval values

# Restart service
sudo systemctl restart pingit
```

## 📊 Metrics Information

### Prometheus Metric Retention

- **Retention**: Configured in Prometheus server (typically 15 days)
- **Scrape Interval**: 15 seconds (configurable)
- **Storage**: Time-series database (Prometheus server)
- **Real-time Export**: PingIT exposes metrics in real-time at `/metrics` endpoint

### Metric Structure

Each metric includes:
- **Metric Name**: `pingit_ping_*`
- **Labels**: `target_name`, `host`
- **Value**: Counter/Gauge/Histogram value
- **Timestamp**: Generated at scrape time

### Example PromQL Queries

```promql
# Get all metrics for a target
{target_name="google_dns"}

# Calculate success rate
rate(pingit_ping_success_total[1h]) / (rate(pingit_ping_success_total[1h]) + rate(pingit_ping_failure_total[1h]))

# Get response time percentile
histogram_quantile(0.95, pingit_ping_response_time_ms)
```

## 🔐 Security

### Service User

- Runs as non-root `pingit` user
- Dedicated directories with restricted permissions
- Cannot access other system files

### File Permissions

```
/etc/pingit/            750  (rwxr-x---)  pingit:pingit
/var/log/pingit/        750  (rwxr-x---)  pingit:pingit
/etc/pingit/config.yaml 644  (rw-r--r--)  pingit:pingit
```

### Prometheus Metrics Security

- Metrics endpoint is accessible on configured port
- Recommend restricting via firewall or reverse proxy
- No sensitive data in metrics (only counts and timings)

### Firewall Considerations

```bash
# Allow outbound ICMP (pings)
sudo ufw allow out proto icmp from any to any icmptype 8

# Allow Prometheus scrape (local only recommended)
sudo ufw allow from 127.0.0.1 to any port 8000
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

System user:
  └── pingit:pingit          # Service user
```

## 📦 Dependencies

All automatically installed by setup.sh:

- **PyYAML** (6.0+) - Configuration file parsing
- **APScheduler** (3.10.0+) - Job scheduling and interval management
- **prometheus-client** (0.14.0+) - Prometheus metrics export
- **icmplib** (3.0.0+) - Pure Python ICMP pinging (required)
- **ecs-logging** (2.0.0+) - ECS (Elastic Common Schema) structured logging

See `requirements.txt` for version details.

### ECS Logging

PingIT uses ECS (Elastic Common Schema) logging format for all log output. This provides:
- Structured JSON logs
- Standard field naming
- Easy integration with log aggregation platforms
- Better parsing and analysis capabilities

## 🧹 Uninstallation

```bash
# Stop services
sudo systemctl stop pingit
sudo systemctl stop influxdb

# Uninstall (prompts for what to remove)
sudo bash uninstall.sh

# Or manual uninstall:
sudo rm -rf /opt/pingit /etc/pingit
sudo rm -f /etc/systemd/system/pingit.service
sudo systemctl daemon-reload
```

## 🚀 Performance

Typical resource usage:

- **CPU**: 2-5% (depends on ping frequency and target count)
- **Memory**: 100-150MB (InfluxDB ~50-100MB, PingIT ~5-10MB)
- **Disk Growth**: 1-5MB per target per month
- **Query Performance**: Sub-second for standard queries

## 🔄 Monitoring at Scale

For high-frequency monitoring (100+ targets):

```yaml
logging:
  level: WARNING          # Reduce log verbosity

targets:
  # Critical services (5s interval)
  - name: critical_api
    host: 10.0.0.1
    interval: 5
    timeout: 2
  
  # Standard services (60s interval)
  - name: standard_service
    host: 10.0.0.2
    interval: 60
    timeout: 5
  
  # External services (5m interval)
  - name: external
    host: example.com
    interval: 300
    timeout: 10
```

## 🔗 Integration

### Grafana Dashboard

Create visualizations from InfluxDB data:
1. Add InfluxDB as data source in Grafana
2. Query `ping_result` measurement
3. Create panels for success rate, response time, etc.
4. Set up alerts based on thresholds

### Prometheus Export

Data stored in InfluxDB can be:
- Queried via Flux language
- Exported to Prometheus
- Used in Grafana dashboards
- Integrated with other monitoring tools

### Log Integration

ECS logs can be sent to observability platforms:

**Filebeat to Elasticsearch:**
```yaml
filebeat.inputs:
  - type: log
    enabled: true
    paths:
      - /var/log/pingit/pingit.log

output.elasticsearch:
  hosts: ["elasticsearch:9200"]
  index: "pingit-logs-%{+yyyy.MM.dd}"
```

**Datadog Agent:**
```yaml
logs:
  - type: file
    path: /var/log/pingit/pingit.log
    service: pingit
    source: python
```

**Splunk Universal Forwarder:**
```ini
[monitor:///var/log/pingit/pingit.log]
sourcetype = _json
index = pingit
```

**AWS CloudWatch:**
```bash
# Install CloudWatch agent and configure to read pingit logs
/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
  -a fetch-config \
  -m ec2 \
  -s
```

## 📝 Version History

- **v2.0.0** - Prometheus metrics export, replaced InfluxDB with Prometheus backend
- **v1.4.0** - Web dashboard with disconnects monitoring, time-range selection
- **v1.3.0** - ECS logging integration, improved observability
- **v1.2.0** - Improved setup with dependency checks, removed fallback modes
- **v1.1.0** - InfluxDB-only release, removed SQLite support
- **v1.0.0** - Initial release

## 🆘 Getting Help

### Check Logs

```bash
sudo journalctl -u pingit -f
sudo tail -f /var/log/pingit/pingit.log
```

### Verify Setup

```bash
# Check service running
sudo systemctl status pingit

# Check Prometheus scrape running
sudo systemctl status prometheus

# Check metrics endpoint
curl http://localhost:8000/metrics

# List metrics
curl http://localhost:8000/metrics | grep pingit
```

### Common Issues

| Issue | Solution |
|-------|----------|
| Service won't start | Check logs, verify config syntax, ensure port is available |
| Permission denied | Run `sudo chown -R pingit:pingit /etc/pingit /var/log/pingit` |
| Metrics not exported | Verify PingIT is running, check metrics port in config |
| Prometheus can't scrape | Check PingIT service running, verify firewall allows port 8000 |
| High memory usage | Reduce target count, increase ping intervals |

## 📜 License

MIT License - Free for personal and commercial use

## 👨‍💻 Development

### Running Locally (Testing)

```bash
# Clone/download and enter directory
cd pingit

# Create local config
cp config.yaml config_local.yaml

# Edit for local paths
# Run manually
python3 pingit.py --config config_local.yaml
```

### Code Structure

- `pingit.py` - Main service (≈250 lines)
- `query_results.py` - Query tool (≈310 lines)
- `setup.sh` - Installation script (≈250 lines)
- `config.yaml` - Configuration template (≈40 lines)
- `pingit.service` - systemd service file

## 🎯 Next Steps

1. **Install**: `sudo bash setup.sh`
2. **Configure**: Edit `/etc/pingit/config.yaml`
3. **Start**: `sudo systemctl start pingit`
4. **Monitor**: `sudo journalctl -u pingit -f`
5. **Query**: `python3 query_results.py --latest 10`

---

**Status**: Production Ready ✅  
**Platform**: Linux (Ubuntu, Debian, CentOS, etc.)  
**Python**: 3.7+  
**Metrics**: Prometheus  
**License**: MIT
