#!/bin/bash
#
# Fix PingIT USB Directory Permissions
# Run this if log/data folders have wrong ownership or permissions
#

set -e

LOG_DIR="/mnt/usb/log/pingit"
DATA_DIR="/mnt/usb/data/pingit"

echo "Fixing PingIT directory permissions..."

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo "This script must be run as root (use sudo)"
   exit 1
fi

echo "Stopping services..."
sudo systemctl stop pingit-webserver 2>/dev/null || true
sudo systemctl stop pingit 2>/dev/null || true

echo "Fixing log directory..."
mkdir -p "$LOG_DIR"
chmod 755 "$LOG_DIR"
chown -R root:root "$LOG_DIR"
ls -ld "$LOG_DIR"

echo ""
echo "Fixing data directory..."
mkdir -p "$DATA_DIR"
chmod 755 "$DATA_DIR"
chown -R root:root "$DATA_DIR"
ls -ld "$DATA_DIR"

echo ""
echo "Starting services..."
sudo systemctl start pingit-webserver
sleep 2
sudo systemctl start pingit

echo ""
echo "Verifying services..."
sudo systemctl status pingit-webserver --no-pager | grep -E "Active|loaded"
sudo systemctl status pingit --no-pager | grep -E "Active|loaded"

echo ""
echo "Checking log files..."
ls -lh "$LOG_DIR"/*.log 2>/dev/null | tail -3 || echo "No log files yet"

echo ""
echo "Done! Permissions fixed."

