#!/bin/bash
# Setup script for PingIT service on Linux
# Minimal setup for PingIT monitoring service with SQLite backend

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}PingIT Setup Script${NC}"
echo "===================="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}This script must be run as root (admin privileges required)${NC}"
    exit 1
fi

# Variables
INSTALL_DIR="/opt/pingit"
CONFIG_DIR="/etc/pingit"
DATA_DIR="/var/lib/pingit"
LOG_DIR="/var/log/pingit"
SERVICE_USER="pingit"
SERVICE_GROUP="pingit"

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to check if Python package is installed
python_package_installed() {
    python3 -c "import $1" >/dev/null 2>&1
}

echo -e "${YELLOW}Checking prerequisites...${NC}"
echo ""

# Check Python 3
if ! command_exists python3; then
    echo -e "${RED}âœ— Python 3 is not installed${NC}"
    exit 1
fi
echo -e "${GREEN}âœ“ Python 3 found${NC}"

# Install pip3 if not found
if ! command_exists pip3; then
    echo -e "${YELLOW}Installing pip3...${NC}"
    apt-get update
    apt-get install -y python3-pip
    echo -e "${GREEN}âœ“ pip3 installed${NC}"
else
    echo -e "${GREEN}âœ“ pip3 found${NC}"
fi

# Install minimal required system packages for icmplib and dependencies
echo -e "${YELLOW}Installing system dependencies...${NC}"
REQUIRED_PACKAGES="build-essential libffi-dev python3-dev"
apt-get update
apt-get install -y $REQUIRED_PACKAGES
echo -e "${GREEN}âœ“ System dependencies installed${NC}"

echo ""
echo "========================================" 
echo "Installation Progress Check"
echo "========================================" 

# Check which phases have been completed
SKIP_PHASES=()

if id "$SERVICE_USER" &>/dev/null; then
    echo -e "${GREEN}âœ“ User '$SERVICE_USER' already exists${NC}"
    SKIP_PHASES+=("user_creation")
else
    echo -e "${YELLOW}â—‹ User '$SERVICE_USER' needs to be created${NC}"
fi

if [ -f "$INSTALL_DIR/pingit.py" ] && [ -f "$INSTALL_DIR/webserver.py" ]; then
    echo -e "${GREEN}âœ“ Application files already installed${NC}"
    SKIP_PHASES+=("app_files")
else
    echo -e "${YELLOW}â—‹ Application files need to be installed${NC}"
fi

if [ -f "$CONFIG_DIR/pingit-config.yaml" ]; then
    echo -e "${GREEN}âœ“ PingIT configuration already exists${NC}"
    SKIP_PHASES+=("config_copy")
else
    echo -e "${YELLOW}â—‹ PingIT configuration needs to be copied${NC}"
fi

if [ -f "$CONFIG_DIR/webserver-config.yaml" ]; then
    echo -e "${GREEN}âœ“ Webserver configuration already exists${NC}"
    SKIP_PHASES+=("webserver_config")
else
    echo -e "${YELLOW}â—‹ Webserver configuration needs to be created${NC}"
fi

# Check for critical packages from requirements.txt
NEEDS_PYTHON_DEPS=false
for pkg in yaml flask requests; do
    if ! python_package_installed "$pkg"; then
        NEEDS_PYTHON_DEPS=true
        break
    fi
done

if [ "$NEEDS_PYTHON_DEPS" = false ]; then
    echo -e "${GREEN}âœ“ Python dependencies already installed${NC}"
    SKIP_PHASES+=("python_deps")
else
    echo -e "${YELLOW}â—‹ Python dependencies need to be installed${NC}"
fi

if [ -f "/etc/systemd/system/pingit.service" ]; then
    echo -e "${GREEN}âœ“ Systemd services already installed${NC}"
    SKIP_PHASES+=("systemd_services")
else
    echo -e "${YELLOW}â—‹ Systemd services need to be installed${NC}"
fi

if [ -f "$INSTALL_DIR/templates/dashboard.html" ] && [ -f "$INSTALL_DIR/static/dashboard.js" ] && [ -f "$INSTALL_DIR/static/dashboard.css" ]; then
    echo -e "${GREEN}âœ“ Dashboard already installed${NC}"
    SKIP_PHASES+=("dashboard_files")
else
    echo -e "${YELLOW}â—‹ Dashboard files need to be installed${NC}"
fi

echo ""

echo -e "${YELLOW}Step 1: Reading configuration from YAML files...${NC}"

# Extract paths from pingit-config.yaml
if [ -f "pingit-config.yaml" ]; then
    # Extract logging path
    CONFIG_LOG_PATH=$(grep -A 1 "logging:" pingit-config.yaml | grep "path:" | sed 's/.*path: *//' | tr -d ' ')
    if [ -n "$CONFIG_LOG_PATH" ]; then
        LOG_DIR="$CONFIG_LOG_PATH"
        echo -e "${GREEN}âœ“ Log path from config: $LOG_DIR${NC}"
    fi
else
    echo -e "${YELLOW}âš  pingit-config.yaml not found, using defaults${NC}"
fi

echo ""
echo -e "${YELLOW}Step 2: Creating directories...${NC}"

# Create directories based on configuration
DIRS_TO_CREATE=(
    "$INSTALL_DIR"
    "$CONFIG_DIR"
    "$DATA_DIR"
    "$LOG_DIR"
)

# Extract any custom paths from config files and add them
if [ -f "pingit-config.yaml" ]; then
    # Check if there are any custom paths in the config
    while IFS= read -r line; do
        if [[ $line =~ path:\ * ]]; then
            CUSTOM_PATH=$(echo "$line" | sed 's/.*path: *//' | tr -d ' ')
            if [[ "$CUSTOM_PATH" != /* ]]; then
                CUSTOM_PATH="/$CUSTOM_PATH"
            fi
            # Only add if not already in list
            if [[ ! " ${DIRS_TO_CREATE[@]} " =~ " ${CUSTOM_PATH} " ]]; then
                DIRS_TO_CREATE+=("$CUSTOM_PATH")
            fi
        fi
    done < pingit-config.yaml
fi

# Create all directories
for dir in "${DIRS_TO_CREATE[@]}"; do
    if mkdir -p "$dir" 2>/dev/null; then
        echo -e "${GREEN}âœ“ Created: $dir${NC}"
    else
        echo -e "${YELLOW}âš  Could not create: $dir (may already exist or permission issue)${NC}"
    fi
done

echo -e "${GREEN}âœ“ All directories created${NC}"

echo -e "${YELLOW}Step 3: Creating service user...${NC}"
if [[ " ${SKIP_PHASES[@]} " =~ " user_creation " ]]; then
    echo -e "${GREEN}âœ“ Skipping (already completed)${NC}"
else
    if ! id "$SERVICE_USER" &>/dev/null; then
        useradd --system --no-create-home --shell /bin/false "$SERVICE_USER"
        echo -e "${GREEN}âœ“ User '$SERVICE_USER' created${NC}"
    else
        echo -e "${GREEN}âœ“ User '$SERVICE_USER' already exists${NC}"
    fi
fi

echo -e "${YELLOW}Step 4: Copying application files...${NC}"
if [[ " ${SKIP_PHASES[@]} " =~ " app_files " ]]; then
    echo -e "${GREEN}âœ“ Skipping (already completed)${NC}"
else
    cp pingit.py "$INSTALL_DIR/"
    cp webserver.py "$INSTALL_DIR/"
    chmod +x "$INSTALL_DIR/pingit.py"
    chmod +x "$INSTALL_DIR/webserver.py"
    echo -e "${GREEN}âœ“ Application files copied${NC}"
fi

echo -e "${YELLOW}Step 5: Copying configuration file...${NC}"
if [[ " ${SKIP_PHASES[@]} " =~ " config_copy " ]]; then
    echo -e "${GREEN}âœ“ Skipping (already exists)${NC}"
else
    if [ -f "pingit-config.yaml" ]; then
        cp pingit-config.yaml "$CONFIG_DIR/pingit-config.yaml"
        echo -e "${GREEN}âœ“ Configuration file created${NC}"
    elif [ -f "config.yaml" ]; then
        cp config.yaml "$CONFIG_DIR/pingit-config.yaml"
        echo -e "${GREEN}âœ“ Configuration file created${NC}"
    else
        echo -e "${RED}âœ— No configuration file found (pingit-config.yaml or config.yaml)${NC}"
        exit 1
    fi
fi

echo -e "${YELLOW}Step 6: Setting permissions...${NC}"
chown -R "$SERVICE_USER:$SERVICE_GROUP" "$CONFIG_DIR" 2>/dev/null || true
chown -R "$SERVICE_USER:$SERVICE_GROUP" "$DATA_DIR" 2>/dev/null || true
chown -R "$SERVICE_USER:$SERVICE_GROUP" "$LOG_DIR" 2>/dev/null || true
chmod 750 "$CONFIG_DIR" 2>/dev/null || true
chmod 750 "$DATA_DIR" 2>/dev/null || true
chmod 750 "$LOG_DIR" 2>/dev/null || true
chmod 644 "$CONFIG_DIR/pingit-config.yaml" 2>/dev/null || true
chmod 644 "$CONFIG_DIR/webserver-config.yaml" 2>/dev/null || true
echo -e "${GREEN}âœ“ Permissions set${NC}"

echo -e "${YELLOW}Step 7: Checking Python dependencies...${NC}"

if [[ " ${SKIP_PHASES[@]} " =~ " python_deps " ]]; then
    echo -e "${GREEN}âœ“ Skipping (already installed)${NC}"
else
    # Check if requirements.txt exists
    if [ ! -f "requirements.txt" ]; then
        echo -e "${RED}âœ— requirements.txt not found${NC}"
        exit 1
    fi

    # Check each required package
    MISSING_PACKAGES=()
    while IFS= read -r package; do
        # Skip comments and empty lines
        [[ "$package" =~ ^#.*$ ]] && continue
        [[ -z "$package" ]] && continue
        
        # Extract package name (handle version specs like package>=1.0)
        pkg_name=$(echo "$package" | sed 's/[>=!].*//')
        
        if python_package_installed "$pkg_name"; then
            echo -e "${GREEN}âœ“ $pkg_name installed${NC}"
        else
            echo -e "${YELLOW}âš  $pkg_name not found${NC}"
            MISSING_PACKAGES+=("$package")
        fi
    done < requirements.txt

    # Install missing packages if any
    if [ ${#MISSING_PACKAGES[@]} -gt 0 ]; then
        echo ""
        echo -e "${YELLOW}Missing packages detected:${NC}"
        for pkg in "${MISSING_PACKAGES[@]}"; do
            echo "  - $pkg"
        done
        echo ""
        echo -e "${YELLOW}Installing missing packages...${NC}"
        # Try normal install first, then with --break-system-packages if needed (Debian 12+)
        if pip3 install -r requirements.txt 2>&1 | grep -q "externally-managed-environment"; then
            echo -e "${YELLOW}Using --break-system-packages for Debian 12+ compatibility...${NC}"
            pip3 install --break-system-packages -r requirements.txt
        fi
        echo -e "${GREEN}âœ“ Dependencies installed${NC}"
    else
        echo -e "${GREEN}âœ“ All dependencies already installed${NC}"
    fi
fi

echo ""

echo -e "${YELLOW}Step 8: Creating webserver configuration file...${NC}"
if [[ " ${SKIP_PHASES[@]} " =~ " webserver_config " ]]; then
    echo -e "${GREEN}âœ“ Skipping (already exists)${NC}"
else
    cat > "$CONFIG_DIR/webserver-config.yaml" << 'EOF'
# PingIT WebServer Configuration
logging:
  level: INFO
  path: /var/log/pingit

webserver:
  host: 0.0.0.0
  port: 5000
  debug: false
EOF
    chmod 644 "$CONFIG_DIR/webserver-config.yaml"
    chown "$SERVICE_USER:$SERVICE_GROUP" "$CONFIG_DIR/webserver-config.yaml"
    echo -e "${GREEN}âœ“ Webserver configuration created${NC}"
fi

echo -e "${YELLOW}Step 9: Installing systemd services...${NC}"
if [[ " ${SKIP_PHASES[@]} " =~ " systemd_services " ]]; then
    echo -e "${GREEN}âœ“ Skipping (already installed)${NC}"
else
    cp pingit.service /etc/systemd/system/pingit.service
    cp pingit-webserver.service /etc/systemd/system/pingit-webserver.service
    systemctl daemon-reload
    echo -e "${GREEN}âœ“ Systemd services installed${NC}"
fi

echo -e "${YELLOW}Step 10: Setting up web dashboard...${NC}"
if [[ " ${SKIP_PHASES[@]} " =~ " dashboard_files " ]]; then
    echo -e "${GREEN}âœ“ Skipping (already installed)${NC}"
else
    mkdir -p "$INSTALL_DIR/templates"
    mkdir -p "$INSTALL_DIR/static"
    cp templates/dashboard.html "$INSTALL_DIR/templates/"
    cp static/dashboard.css "$INSTALL_DIR/static/"
    cp static/dashboard.js "$INSTALL_DIR/static/"
    chmod +x "$INSTALL_DIR/webserver.py" 2>/dev/null || true
    echo -e "${GREEN}âœ“ Web dashboard installed${NC}"
fi

echo -e "${YELLOW}Step 11: Setting up ICMP socket capabilities...${NC}"
# Allow Python to create raw ICMP sockets without full root privileges
PYTHON_PATH=$(which python3)
if [ -n "$PYTHON_PATH" ]; then
    sudo setcap cap_net_raw=ep "$PYTHON_PATH" 2>/dev/null || true
    echo -e "${GREEN}âœ“ ICMP capabilities configured${NC}"
else
    echo -e "${YELLOW}âš  Could not find python3 path${NC}"
fi

echo -e "${YELLOW}Step 12: Initializing database...${NC}"
# Database will be created automatically by pingit service on first run
chown "$SERVICE_USER:$SERVICE_GROUP" "$DATA_DIR" 2>/dev/null || true
chmod 750 "$DATA_DIR" 2>/dev/null || true
echo -e "${GREEN}âœ“ Data directory configured${NC}"

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Setup complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

echo -e "${YELLOW}System Information:${NC}"
echo "  Install Directory:  $INSTALL_DIR"
echo "  Config Directory:   $CONFIG_DIR"
echo "  Data Directory:     $DATA_DIR"
echo "  Log Directory:      $LOG_DIR"
echo "  Service User:       $SERVICE_USER"
echo "  Dashboard Port:     5000"
echo ""

echo -e "${YELLOW}Next steps:${NC}"
echo ""
echo "1. (Optional) Edit the PingIT configuration:"
echo "   sudo nano $CONFIG_DIR/config.yaml"
echo ""
echo "2. (Optional) Edit the webserver configuration:"
echo "   sudo nano $CONFIG_DIR/webserver-config.yaml"
echo ""
echo "3. Enable services to start on boot:"
echo "   sudo systemctl enable pingit"
echo "   sudo systemctl enable pingit-webserver"
echo ""
echo "4. Start the services:"
echo "   sudo systemctl start pingit"
echo "   sudo systemctl start pingit-webserver"
echo ""
echo "5. Check service status:"
echo "   sudo systemctl status pingit"
echo "   sudo systemctl status pingit-webserver"
echo ""
echo "6. View logs (pingit service):"
echo "   sudo journalctl -u pingit -f"
echo ""
echo "7. View logs (webserver service):"
echo "   sudo journalctl -u pingit-webserver -f"
echo ""
echo -e "${YELLOW}Access the dashboard:${NC}"
echo "   PingIT Dashboard: http://localhost:5000"
echo "   (or http://<server-ip>:5000)"
echo ""

