#!/bin/bash
# Self-Signed SSL Certificate Setup for PingIT
# Creates a self-signed certificate and enables HTTPS
# Certificate can be added to phone's trust store for green lock icon
# Includes IP range 10.10.0.0/24 for local network access

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}========== PingIT Self-Signed SSL Setup ==========${NC}\n"

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}This script must be run as root${NC}"
    exit 1
fi

# Variables
SSL_DIR="/etc/pingit/ssl"
CERT_FILE="$SSL_DIR/cert.pem"
KEY_FILE="$SSL_DIR/key.pem"
CA_FILE="$SSL_DIR/ca.pem"
CONFIG_FILE="/etc/pingit/webserver-config.yaml"
SAN_CONFIG="/tmp/pingit-san.conf"
HOSTNAME=$(hostname)
LOCAL_IP=$(hostname -I | awk '{print $1}')

echo -e "${YELLOW}Hostname: $HOSTNAME${NC}"
echo -e "${YELLOW}Local IP: $LOCAL_IP${NC}"
echo -e "${YELLOW}SSL Directory: $SSL_DIR${NC}\n"

# Create SSL directory
echo -e "${YELLOW}Creating SSL directory...${NC}"
mkdir -p "$SSL_DIR"
chmod 755 "$SSL_DIR"

# Create SAN configuration file for certificate
echo -e "${YELLOW}Creating certificate with Subject Alternative Names (SANs)...${NC}"

# Generate all IPs in 10.10.0.0/24 range
SAN_IPS="DNS:raspberrypi, DNS:raspberrypi.local, IP:127.0.0.1"
for i in $(seq 0 255); do
    SAN_IPS="$SAN_IPS, IP:10.10.0.$i"
done

cat > "$SAN_CONFIG" << EOF
[req]
distinguished_name = req_distinguished_name
req_extensions = v3_req
prompt = no

[req_distinguished_name]
C = IL
ST = Local
L = Local
O = Local
CN = raspberrypi

[v3_req]
subjectAltName = $SAN_IPS
EOF

# Generate self-signed certificate with SANs
echo -e "${YELLOW}Generating self-signed certificate with IP range 10.10.0.0/24...${NC}"
openssl req -x509 -newkey rsa:4096 \
    -keyout "$KEY_FILE" \
    -out "$CERT_FILE" \
    -days 365 -nodes \
    -config "$SAN_CONFIG" \
    -extensions v3_req

# Create CA certificate (same as self-signed cert for self-signed scenarios)
cp "$CERT_FILE" "$CA_FILE"

# Set proper permissions
chmod 600 "$KEY_FILE"
chmod 644 "$CERT_FILE"
chmod 644 "$CA_FILE"

# Clean up temporary SAN config
rm -f "$SAN_CONFIG"

echo -e "${GREEN}âœ“ Certificates created successfully!${NC}"
echo -e "  Certificate: $CERT_FILE"
echo -e "  Private key: $KEY_FILE"
echo -e "  CA certificate: $CA_FILE"
echo -e "  Valid for: 365 days\n"

echo -e "${GREEN}âœ“ Certificate includes:${NC}"
echo -e "  DNS: raspberrypi"
echo -e "  DNS: raspberrypi.local"
echo -e "  IP: 127.0.0.1"
echo -e "  IP Range: 10.10.0.0 - 10.10.0.254"
echo -e "  (All IPs in 10.10.0.0/24 subnet)\n"

# Update webserver config
if [ -f "$CONFIG_FILE" ]; then
    echo -e "${YELLOW}Updating webserver configuration...${NC}"
    
    # Backup config
    cp "$CONFIG_FILE" "${CONFIG_FILE}.bak.$(date +%s)"
    
    # Update SSL paths in config
    sed -i "s|certificate:.*|certificate: $CERT_FILE|g" "$CONFIG_FILE"
    sed -i "s|private_key:.*|private_key: $KEY_FILE|g" "$CONFIG_FILE"
    sed -i "s|ca_certificate:.*|ca_certificate: $CA_FILE|g" "$CONFIG_FILE"
    sed -i "s|scheme:.*|scheme: https|g" "$CONFIG_FILE"
    
    echo -e "${GREEN}âœ“ SSL configuration updated in $CONFIG_FILE${NC}\n"
else
    echo -e "${YELLOW}Config file not found at $CONFIG_FILE${NC}"
    echo -e "${YELLOW}You'll need to manually add SSL settings${NC}\n"
fi

# Export certificate for phone installation
EXPORT_DIR="/tmp/pingit-cert"
mkdir -p "$EXPORT_DIR"
cp "$CERT_FILE" "$EXPORT_DIR/raspberrypi.pem"
chmod 644 "$EXPORT_DIR/raspberrypi.pem"

echo -e "${GREEN}Certificate exported for phone installation:${NC}"
echo -e "  ${EXPORT_DIR}/raspberrypi.pem\n"

echo -e "${BLUE}========== NEXT STEPS ==========${NC}\n"

echo -e "${YELLOW}1. Update webserver.py for SSL support${NC}"
echo -e "   (See SSL documentation for Flask integration)\n"

echo -e "${YELLOW}2. Restart webserver:${NC}"
echo -e "   sudo systemctl restart pingit-webserver\n"

echo -e "${YELLOW}3. Install certificate on your phone:${NC}"
echo -e "   - Transfer: ${EXPORT_DIR}/raspberrypi.pem"
echo -e "   - Android: Settings > Security > Install certificates"
echo -e "   - iOS: Email cert, then Settings > Install > Trust\n"

echo -e "${YELLOW}4. Access dashboard from any IP in 10.10.0.0/24:${NC}"
echo -e "   https://$HOSTNAME"
echo -e "   https://raspberrypi.local"
echo -e "   https://10.10.0.xxx (any IP in range)\n"

echo -e "${GREEN}Certificate valid for 365 days (expires: $(date -d '+365 days' '+%Y-%m-%d'))${NC}\n"

echo -e "${YELLOW}To renew certificate before expiration:${NC}"
echo -e "  sudo bash $0\n"

