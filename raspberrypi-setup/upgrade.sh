#!/bin/bash
#
# PingIT System Upgrade Script
# Upgrades PingIT and WebServer on a Linux system
# Must be run with sudo privileges
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Paths
INSTALL_DIR="/opt/pingit"
CONFIG_DIR="/etc/pingit"
LOG_DIR="/mnt/usb/log/pingit"
DATA_DIR="/mnt/usb/data/pingit"
USB_PINGIT_DIR="/mnt/usb/pingit"

echo -e "${BLUE}================================================${NC}"
echo -e "${BLUE}  PingIT System Upgrade Script${NC}"
echo -e "${BLUE}================================================${NC}\n"

# Parse command line arguments
MIGRATE_TIMESTAMPS=false
while [[ $# -gt 0 ]]; do
    case $1 in
        --migrate-timestamps)
            MIGRATE_TIMESTAMPS=true
            echo -e "${YELLOW}⚠️  Timestamp migration flag detected!${NC}"
            shift
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            echo "Usage: sudo ./upgrade.sh [--migrate-timestamps]"
            exit 1
            ;;
    esac
done

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo -e "${RED}✗ This script must be run as root (use sudo)${NC}"
   echo "Usage: sudo ./upgrade.sh [--migrate-timestamps]"
   exit 1
fi

echo -e "${GREEN}✓ Running with sudo privileges${NC}\n"

# Check if PingIT is installed
if [ ! -d "$INSTALL_DIR" ]; then
    echo -e "${RED}✗ PingIT not found at $INSTALL_DIR${NC}"
    echo "Please run setup.sh first to install PingIT"
    exit 1
fi

echo -e "${YELLOW}Step 1: Stopping services...${NC}"
sudo systemctl stop pingit-webserver 2>/dev/null || true
sudo systemctl stop pingit 2>/dev/null || true
echo -e "${GREEN}✓ Services stopped${NC}\n"

echo -e "${YELLOW}Step 2: Updating web UI files...${NC}"
rm -rf "$INSTALL_DIR/static"
rm -rf "$INSTALL_DIR/templates"
cp -r static "$INSTALL_DIR/"
cp -r templates "$INSTALL_DIR/"
chmod -R 644 "$INSTALL_DIR/static"
chmod -R 644 "$INSTALL_DIR/templates"
echo -e "${GREEN}✓ Web UI files updated${NC}\n"

echo -e "${YELLOW}Step 3: Copying configuration files...${NC}"

# Copy config files from local directory (maintained locally on Raspberry Pi)
cp pingit-config.yaml "$CONFIG_DIR/pingit-config.yaml"
cp webserver-config.yaml "$CONFIG_DIR/webserver-config.yaml"

# Set file permissions
chmod 644 "$CONFIG_DIR/pingit-config.yaml"
chmod 644 "$CONFIG_DIR/webserver-config.yaml"

echo -e "${GREEN}✓ Configuration files copied${NC}\n"

echo -e "${YELLOW}Step 4: Updating service files...${NC}"
cp pingit.service /etc/systemd/system/pingit.service
cp pingit-webserver.service /etc/systemd/system/pingit-webserver.service
chmod 644 /etc/systemd/system/pingit.service
chmod 644 /etc/systemd/system/pingit-webserver.service
sudo systemctl daemon-reload
echo -e "${GREEN}✓ Service files updated${NC}\n"

# Optional timestamp migration
if [ "$MIGRATE_TIMESTAMPS" = true ]; then
    echo -e "${YELLOW}Step 5: Migrating database timestamps (TEXT → INTEGER)...${NC}"
    echo -e "${BLUE}This may take a few moments depending on database size...${NC}\n"
    
    if python3 /opt/pingit/webserver.py --migrate-timestamps; then
        echo -e "${GREEN}✓ Timestamp migration completed successfully!${NC}"
        echo -e "${GREEN}  - ping_statistics: TEXT → INTEGER (Unix milliseconds)${NC}"
        echo -e "${GREEN}  - disconnect_times: TEXT → INTEGER (Unix milliseconds)${NC}"
        echo -e "${YELLOW}Performance improvement: ~50-100ms per dashboard request${NC}\n"
    else
        echo -e "${RED}✗ Timestamp migration failed!${NC}"
        echo -e "${YELLOW}The database may be in an inconsistent state.${NC}"
        echo -e "${YELLOW}Please review /var/log/syslog or run: journalctl -u pingit-webserver${NC}"
        exit 1
    fi
    NEXT_STEP=6
else
    NEXT_STEP=5
fi

# Adjust step numbers based on whether migration was run
if [ "$NEXT_STEP" = "6" ]; then
    echo -e "${YELLOW}Step 6: Starting services...${NC}"
else
    echo -e "${YELLOW}Step 5: Starting services...${NC}"
fi
sudo systemctl start pingit-webserver
sleep 2
sudo systemctl start pingit
echo -e "${GREEN}✓ Services started${NC}\n"

echo -e "${YELLOW}Step $((NEXT_STEP + 1)): Verifying service configuration...${NC}"
# Check that pingit service is configured to run as root
PINGIT_USER=$(systemctl cat pingit.service | grep "^User=" | cut -d= -f2)
if [ "$PINGIT_USER" = "root" ]; then
    echo -e "${GREEN}✓ PingIT service configured to run as root (ICMP permissions OK)${NC}"
else
    echo -e "${RED}✗ PingIT service not running as root - ICMP will fail!${NC}"
    echo -e "${YELLOW}  Fix: Edit /etc/systemd/system/pingit.service and set User=root${NC}"
fi

echo -e "${YELLOW}Step $((NEXT_STEP + 2)): Verifying services are running...${NC}"
sleep 3
if sudo systemctl is-active --quiet pingit-webserver; then
    echo -e "${GREEN}✓ WebServer is running${NC}"
else
    echo -e "${RED}✗ WebServer failed to start${NC}"
fi

if sudo systemctl is-active --quiet pingit; then
    echo -e "${GREEN}✓ PingIT is running as root (ICMP enabled)${NC}"
else
    echo -e "${RED}✗ PingIT failed to start${NC}"
fi

echo -e "\n${BLUE}================================================${NC}"
echo -e "${GREEN}✓ Upgrade completed successfully!${NC}"
echo -e "${BLUE}================================================${NC}\n"

echo -e "${YELLOW}Directory Structure:${NC}"
echo -e "  • Application: $INSTALL_DIR"
echo -e "  • Configuration: $CONFIG_DIR"
echo -e "  • Logs: $LOG_DIR"
echo -e "  • Database: $DATA_DIR/pingit.db"

echo -e "\n${YELLOW}Security & Permissions:${NC}"
echo -e "  • PingIT runs as: root (required for ICMP/ping)"
echo -e "  • WebServer runs as: root"
echo -e "  • ICMP permissions: ✓ Enabled"

echo -e "\n${YELLOW}Useful commands:${NC}"
echo -e "  • Check service status: sudo systemctl status pingit"
echo -e "  • Check service status: sudo systemctl status pingit-webserver"
echo -e "  • Check logs: sudo journalctl -u pingit -f"
echo -e "  • Check logs: sudo journalctl -u pingit-webserver -f"
echo -e "  • View log files: tail -f $LOG_DIR/pingit-*.log"
echo -e "  • View log files: tail -f $LOG_DIR/webserver-*.log"

# Extract dashboard URL from webserver config
if [ -f "$CONFIG_DIR/webserver-config.yaml" ]; then
    DASH_SCHEME=$(grep "^ *scheme:" "$CONFIG_DIR/webserver-config.yaml" | sed 's/.*scheme: *//' | tr -d ' ' | head -1)
    DASH_SCHEME=${DASH_SCHEME:-http}
    
    if [ "$DASH_SCHEME" = "https" ]; then
        DASH_PORT=$(grep "^ *https_port:" "$CONFIG_DIR/webserver-config.yaml" | sed 's/.*https_port: *//' | tr -d ' ')
        DASH_PORT=${DASH_PORT:-7443}
        DASH_URL="${DASH_SCHEME}://$(hostname -I | awk '{print $1}'):${DASH_PORT}"
    else
        DASH_PORT=$(grep "^ *port:" "$CONFIG_DIR/webserver-config.yaml" | sed 's/.*port: *//' | tr -d ' ' | head -1)
        DASH_PORT=${DASH_PORT:-7030}
        DASH_URL="http://$(hostname -I | awk '{print $1}'):${DASH_PORT}"
    fi
else
    DASH_URL="http://$(hostname -I | awk '{print $1}'):7030"
fi

echo -e "  • Dashboard: $DASH_URL\n"

exit 0
