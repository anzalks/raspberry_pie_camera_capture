#!/bin/bash
#
# Installation script for Raspberry Pi Camera and Audio Capture Service
#
# Author: Anzal
# Email: anzal.ks@gmail.com
# GitHub: https://github.com/anzalks/
#

# Set error handling
set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Please run as root (use sudo)${NC}"
    exit 1
fi

# Get the script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

# Function to print header
print_header() {
    echo -e "${BLUE}=======================================================${NC}"
    echo -e "${BLUE}= $1${NC}"
    echo -e "${BLUE}=======================================================${NC}"
}

# Function to print success message
print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

# Function to print error message
print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_header "Installing Raspberry Pi Camera and Audio Capture Service"

# Make scripts executable
chmod +x "$SCRIPT_DIR/start-daily-recording.sh"
print_success "Made start-daily-recording.sh executable"

# Copy service file to systemd directory
cp "$SCRIPT_DIR/raspie-camera.service" /etc/systemd/system/
print_success "Copied service file to /etc/systemd/system/"

# Reload systemd
systemctl daemon-reload
print_success "Reloaded systemd daemon"

# Enable the service
systemctl enable raspie-camera.service
print_success "Enabled raspie-camera service"

# Start the service
systemctl start raspie-camera.service
print_success "Started raspie-camera service"

# Check service status
echo -e "\n${YELLOW}Service Status:${NC}"
systemctl status raspie-camera.service

print_header "Installation Complete"
echo -e "The camera service is now installed and will start automatically on boot."
echo -e "You can control it with the following commands:"
echo -e "  ${YELLOW}sudo systemctl start raspie-camera${NC} - Start the service"
echo -e "  ${YELLOW}sudo systemctl stop raspie-camera${NC} - Stop the service"
echo -e "  ${YELLOW}sudo systemctl restart raspie-camera${NC} - Restart the service"
echo -e "  ${YELLOW}sudo systemctl status raspie-camera${NC} - Check service status"
echo -e "\nRemote control via ntfy.sh is also available:"
echo -e "  ${YELLOW}curl -d \"Start Recording\" ntfy.sh/raspie-camera-test${NC} - Start recording"
echo -e "  ${YELLOW}curl -d \"Stop Recording\" ntfy.sh/raspie-camera-test${NC} - Stop recording" 