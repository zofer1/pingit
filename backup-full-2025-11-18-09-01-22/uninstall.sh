#!/bin/bash
# Uninstall script for PingIT service

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}PingIT Uninstall Script${NC}"
echo "========================"
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}This script must be run as root${NC}"
    exit 1
fi

# Variables
INSTALL_DIR="/opt/pingit"
CONFIG_DIR="/etc/pingit"
DATA_DIR="/var/lib/pingit"
LOG_DIR="/var/log/pingit"
SERVICE_USER="pingit"

echo -e "${YELLOW}This will remove PingIT service and optionally its data.${NC}"
echo ""

# Stop service
echo -e "${YELLOW}Stopping service...${NC}"
systemctl stop pingit || true
systemctl disable pingit || true

# Remove systemd service
echo -e "${YELLOW}Removing systemd service...${NC}"
rm -f /etc/systemd/system/pingit.service
systemctl daemon-reload

# Remove application
echo -e "${YELLOW}Removing application files...${NC}"
rm -rf "$INSTALL_DIR"

# Ask about config
read -p "Remove configuration directory ($CONFIG_DIR)? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    rm -rf "$CONFIG_DIR"
    echo -e "${GREEN}âœ“ Configuration removed${NC}"
else
    echo -e "${YELLOW}âš  Configuration preserved${NC}"
fi

# Ask about data
read -p "Remove database and logs ($DATA_DIR, $LOG_DIR)? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    rm -rf "$DATA_DIR" "$LOG_DIR"
    echo -e "${GREEN}âœ“ Database and logs removed${NC}"
else
    echo -e "${YELLOW}âš  Database and logs preserved${NC}"
fi

# Ask about user
read -p "Remove service user ($SERVICE_USER)? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    userdel "$SERVICE_USER" || true
    echo -e "${GREEN}âœ“ Service user removed${NC}"
else
    echo -e "${YELLOW}âš  Service user preserved${NC}"
fi

echo ""
echo -e "${GREEN}Uninstall complete!${NC}"

