# PingIT Admin Dashboard

The Admin Dashboard provides comprehensive management and control of PingIT services through a web-based interface. Access it at `http://localhost:7030/admin` (development) or `https://your-server:7030/admin` (production).

## 🎯 Overview

The Admin Dashboard is designed for easy management of PingIT and WebServer services with an intuitive, compact layout organized by functionality.

## 📋 Features

### 🎯 Targets Management

**View and manage ping targets:**
- **Targets Table**: Display all configured targets with their host, name, and timeout settings
- **Remove Button**: Delete targets you no longer need (with confirmation)
- **Add New Target**: Quick form to add targets with:
  - Target name (e.g., `google_dns`)
  - Host/IP address
  - Timeout value in seconds

### 📝 Logging Control

**Independent logging configuration for both services:**
- **PingIT Logging**:
  - Change log level (DEBUG, INFO, WARNING, ERROR)
  - Set/view log file path
  - View recent log entries (last 20, 50, 100, or 200 lines)
  - Logs displayed in formatted table with timestamp, level, message, and function

- **WebServer Logging**:
  - Same controls as PingIT
  - Separate configuration for independent control

**Log Viewer Features:**
- Dropdown to select number of lines (20, 50, 100, 200)
- View button to display formatted log table
- Auto-detects most recent log file in test mode
- Color-coded log levels for quick scanning

### ⚙️ Services Control

**Manage PingIT service:**
- **Start**: Launch the PingIT service
- **Stop**: Stop the PingIT service
- **Restart**: Restart the service with automatic status check
- **Status**: Check current service status with live indicator
- **Auto Status Update**: Status automatically refreshes after 1-3 seconds following actions

**WebServer Control:**
- **Restart WebServer**: Gracefully reload Flask application without killing the process
- Cross-platform support (uses `os.execvp()` on Linux, subprocess spawn on Windows)

### 🔒 SSL Configuration

**Enable and manage HTTPS:**
- **SSL Toggle**: Enable/disable SSL mode
- **Certificate Path**: Set path to SSL certificate file
- **Private Key Path**: Set path to SSL private key
- **HTTPS Port**: Configure custom HTTPS port (default: 7443)
- **Get Status**: Load current SSL configuration
- **Update**: Save certificate and key paths
- **Reset**: Clear all SSL settings

**Features:**
- Non-SSL endpoint with automatic redirect when SSL enabled
- Redirect to new endpoint after disabling SSL
- Override existing settings or reset to defaults

### 📡 Prometheus Mode

**Control metrics collection:**
- **Toggle**: Enable/disable Prometheus metrics endpoint
- **Status Indicator**: Shows current mode (Enabled/Disabled)
- **Benefits**:
  - In-memory metrics storage for performance
  - Automatic clearing after Prometheus scrape (drain pattern)
  - Thread-safe concurrent access
  - Fresh data from live ping collection

### 🧪 Test Data Generation

**Create sample data for testing and validation:**
- **Days Input**: Specify how many days of test data to generate (default: 7)
- **Generate Button**: Create fake ping data with:
  - Realistic ping times
  - Random disconnects
  - Distributed across specified time period

### 💾 Database Operations

**Manage application database:**
- **Backup**: Create backup copy of the SQLite database
- **Reset**: Clear all ping statistics and disconnect records (requires confirmation)

### ✓ Config Verification

**Verify all configurations:**
- **Verify All Configs Button**: Validate:
  - Configuration file syntax
  - Target count and validity
  - Service connectivity
  - Database integrity
- Shows success/error messages with details

## 🎨 User Interface

### Layout

The dashboard is organized in logical sections from top to bottom:

1. **Header**: Title, verification button, and dashboard navigation
2. **Targets**: Table with add form
3. **Logging**: PingIT and WebServer log controls
4. **Services**: Service management (Start, Stop, Restart, Status)
5. **SSL Configuration**: HTTPS settings with override/reset options
6. **Prometheus**: Toggle for metrics mode
7. **Test Data**: Generate sample data
8. **Database**: Backup and reset operations

### Status Indicators

- **🟢 Running** (green): Service is active
- **🔴 Stopped** (red): Service is inactive
- **❓ Unknown** (gray): Status could not be determined

## 🔧 Technical Details

### Log File Detection (Test Mode)

In test mode, the log viewer automatically:
- Searches local directories (./logs, ., ./log, ../logs)
- Identifies service-specific log files by service name
- Selects the most recently modified file
- Falls back to any .log file if service-specific file not found

### Configuration Sources

Settings are read from:
- **Production**: `/etc/pingit/pingit-config.yaml` and `/etc/pingit/webserver-config.yaml`
- **Test Mode**: Built-in defaults (no files needed, but can be overridden via admin panel)
