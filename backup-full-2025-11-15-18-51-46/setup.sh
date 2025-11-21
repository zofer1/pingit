#!/bin/bash
# Setup script for PingIT service on Linux

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

# Check pip3
if ! command_exists pip3; then
    echo -e "${RED}âœ— pip3 is not installed${NC}"
    exit 1
fi
echo -e "${GREEN}âœ“ pip3 found${NC}"

# Check required system commands for InfluxDB setup
for cmd in wget gpg curl; do
    if ! command_exists "$cmd"; then
        echo -e "${YELLOW}Installing $cmd...${NC}"
        apt-get update
        apt-get install -y "$cmd"
    else
        echo -e "${GREEN}âœ“ $cmd found${NC}"
    fi
done

echo ""

echo -e "${YELLOW}Step 1: Creating directories...${NC}"
mkdir -p "$INSTALL_DIR"
mkdir -p "$CONFIG_DIR"
mkdir -p "$DATA_DIR"
mkdir -p "$LOG_DIR"
echo -e "${GREEN}âœ“ Directories created${NC}"

echo -e "${YELLOW}Step 2: Creating service user...${NC}"
if ! id "$SERVICE_USER" &>/dev/null; then
    useradd --system --no-create-home --shell /bin/false "$SERVICE_USER"
    echo -e "${GREEN}âœ“ User '$SERVICE_USER' created${NC}"
else
    echo -e "${GREEN}âœ“ User '$SERVICE_USER' already exists${NC}"
fi

echo -e "${YELLOW}Step 3: Copying application files...${NC}"
cp pingit.py "$INSTALL_DIR/"
chmod +x "$INSTALL_DIR/pingit.py"
echo -e "${GREEN}âœ“ Application files copied${NC}"

echo -e "${YELLOW}Step 4: Copying configuration file...${NC}"
if [ ! -f "$CONFIG_DIR/config.yaml" ]; then
    cp config.yaml "$CONFIG_DIR/config.yaml"
    echo -e "${GREEN}âœ“ Configuration file created${NC}"
else
    echo -e "${YELLOW}âš  Configuration file already exists, skipping${NC}"
fi

echo -e "${YELLOW}Step 5: Setting permissions...${NC}"
chown -R "$SERVICE_USER:$SERVICE_GROUP" "$CONFIG_DIR"
chown -R "$SERVICE_USER:$SERVICE_GROUP" "$DATA_DIR"
chown -R "$SERVICE_USER:$SERVICE_GROUP" "$LOG_DIR"
chmod 750 "$CONFIG_DIR"
chmod 750 "$DATA_DIR"
chmod 750 "$LOG_DIR"
chmod 644 "$CONFIG_DIR/config.yaml"
echo -e "${GREEN}âœ“ Permissions set${NC}"

echo -e "${YELLOW}Step 6: Checking Python dependencies...${NC}"

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
    read -p "Install missing Python packages? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo -e "${YELLOW}Installing missing packages...${NC}"
        pip3 install -r requirements.txt
        echo -e "${GREEN}âœ“ Dependencies installed${NC}"
    else
        echo -e "${RED}âœ— Missing packages required to continue${NC}"
        exit 1
    fi
else
    echo -e "${GREEN}âœ“ All dependencies already installed${NC}"
fi

echo ""

echo -e "${YELLOW}Step 7: Installing and configuring InfluxDB...${NC}"

echo -e "${YELLOW}Installing InfluxDB 2.x...${NC}"

# Add InfluxDB repository
wget -q https://repos.influxdata.com/influxdb.key -O /tmp/influxdb.key
cat /tmp/influxdb.key | gpg --dearmor | tee /etc/apt/trusted.gpg.d/influxdb.gpg > /dev/null
echo "deb [signed-by=/etc/apt/trusted.gpg.d/influxdb.gpg] https://repos.influxdata.com/debian stable main" | tee /etc/apt/sources.list.d/influxdb.list

# Update and install
apt-get update
apt-get install -y influxdb2

# Enable and start InfluxDB
systemctl enable influxdb
systemctl start influxdb

echo -e "${GREEN}âœ“ InfluxDB installed and started${NC}"

# Setup InfluxDB on first run
echo -e "${YELLOW}Waiting for InfluxDB to be ready...${NC}"
sleep 3

# Check if setup is needed
if ! curl -s http://localhost:8086/api/v2/setup | grep -q '"allowed":false'; then
    echo -e "${YELLOW}Initializing InfluxDB...${NC}"
    
        INFLUX_SETUP_TOKEN=$(openssl rand -hex 16)
        INFLUX_ORG="pingit"
        INFLUX_BUCKET="pingit"
        INFLUX_USERNAME="admin"
        INFLUX_PASSWORD="admin123"
        INFLUX_RETENTION="365d"  # 1 year
    
    # Setup InfluxDB
    influx setup \
        --org "$INFLUX_ORG" \
        --bucket "$INFLUX_BUCKET" \
        --username "$INFLUX_USERNAME" \
        --password "$INFLUX_PASSWORD" \
        --token "$INFLUX_SETUP_TOKEN" \
        --retention "$INFLUX_RETENTION" \
        --force
    
    # Create API token for PingIT
    echo -e "${YELLOW}Creating PingIT API token...${NC}"
    INFLUX_TOKEN=$(influx auth create \
        --org "$INFLUX_ORG" \
        --description "PingIT Service Token" \
        --write-bucket "$INFLUX_BUCKET" \
        --read-bucket "$INFLUX_BUCKET" \
        --json | grep -o '"token":"[^"]*' | cut -d'"' -f4)
    
    echo -e "${GREEN}âœ“ InfluxDB initialized${NC}"
    echo -e "${YELLOW}InfluxDB API Token:${NC} ${INFLUX_TOKEN}"
    
    # Update config with InfluxDB token
    echo -e "${YELLOW}Updating PingIT configuration with InfluxDB token...${NC}"
    sed -i "s/YOUR_INFLUXDB_TOKEN_HERE/$INFLUX_TOKEN/" "$CONFIG_DIR/config.yaml"
    
    echo -e "${GREEN}âœ“ Configuration updated${NC}"
    echo -e "${YELLOW}InfluxDB Web UI: http://localhost:8086${NC}"
    echo -e "${YELLOW}Username: admin${NC}"
    echo -e "${YELLOW}Password: admin123${NC}"
else
    echo -e "${YELLOW}âš  InfluxDB already initialized, skipping setup${NC}"
fi

echo -e "${YELLOW}Step 8: Installing systemd services...${NC}"
cp pingit.service /etc/systemd/system/pingit.service
cp pingit-webserver.service /etc/systemd/system/pingit-webserver.service
systemctl daemon-reload
echo -e "${GREEN}âœ“ Systemd services installed${NC}"

echo -e "${YELLOW}Step 9: Setting up web dashboard...${NC}"
mkdir -p /opt/pingit/templates
mkdir -p /opt/pingit/static
cp webserver.py /opt/pingit/
cp templates/dashboard.html /opt/pingit/templates/
cp static/dashboard.css /opt/pingit/static/
cp static/dashboard.js /opt/pingit/static/
chmod +x /opt/pingit/webserver.py
echo -e "${GREEN}âœ“ Web dashboard installed${NC}"

echo ""
echo -e "${GREEN}Setup complete!${NC}"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "1. (Optional) Edit the configuration file:"
echo "   sudo nano $CONFIG_DIR/config.yaml"
echo ""
echo "2. Enable the services to start on boot:"
echo "   sudo systemctl enable pingit"
echo "   sudo systemctl enable pingit-webserver"
echo ""
echo "3. Start the services:"
echo "   sudo systemctl start pingit"
echo "   sudo systemctl start pingit-webserver"
echo ""
echo "4. Check service status:"
echo "   sudo systemctl status pingit"
echo "   sudo systemctl status pingit-webserver"
echo ""
echo "5. View logs:"
echo "   sudo journalctl -u pingit -f"
echo "   sudo journalctl -u pingit-webserver -f"
echo ""
echo -e "${YELLOW}Access dashboards:${NC}"
echo "   InfluxDB UI: http://localhost:8086"
echo "   PingIT Dashboard: http://localhost:5000"
echo ""

