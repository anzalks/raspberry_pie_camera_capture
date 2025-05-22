#!/bin/bash
# Installation script for IMX296 Global Shutter Camera Capture System
# Author: Anzal KS <anzal.ks@gmail.com>

# Define colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Get the directory of this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo -e "${GREEN}=== IMX296 Global Shutter Camera Capture System Installer ===${NC}"
echo -e "Project root: ${PROJECT_ROOT}"
echo

# Check if running as root
if [ "$(id -u)" -ne 0 ]; then
    echo -e "${RED}Error: This script must be run as root (sudo).${NC}"
    exit 1
fi

# Function to install system dependencies
install_system_dependencies() {
    echo -e "${YELLOW}Installing system dependencies...${NC}"
    
    apt update
    
    # Install required packages
    apt install -y \
        python3 python3-pip python3-venv \
        v4l-utils \
        libcamera-apps \
        ffmpeg \
        tmux \
        git
    
    echo -e "${GREEN}System dependencies installed.${NC}"
}

# Function to create Python virtual environment
create_virtual_env() {
    echo -e "${YELLOW}Creating Python virtual environment...${NC}"
    
    # Get username of the user who ran sudo
    SUDO_USER_HOME=$(getent passwd "$SUDO_USER" | cut -d: -f6)
    
    # Create venv directory
    VENV_DIR="${PROJECT_ROOT}/.venv"
    
    # Remove existing venv if it exists
    if [ -d "$VENV_DIR" ]; then
        echo "Removing existing virtual environment..."
        rm -rf "$VENV_DIR"
    fi
    
    # Create new venv
    sudo -u "$SUDO_USER" python3 -m venv "$VENV_DIR"
    
    # Install required Python packages
    echo "Installing required Python packages..."
    sudo -u "$SUDO_USER" "${VENV_DIR}/bin/pip" install \
        pyyaml \
        requests \
        pylsl \
        psutil
    
    echo -e "${GREEN}Python virtual environment created and packages installed.${NC}"
}

# Function to create and register systemd service
setup_systemd_service() {
    echo -e "${YELLOW}Setting up systemd service...${NC}"
    
    # Copy service file to systemd directory
    cp "${PROJECT_ROOT}/bin/imx296-camera.service" /etc/systemd/system/
    
    # Update service file with correct paths
    sed -i "s|/home/pi/raspberry_pie_camera_capture|${PROJECT_ROOT}|g" /etc/systemd/system/imx296-camera.service
    
    # Update user and group in service file
    sed -i "s|User=pi|User=${SUDO_USER}|g" /etc/systemd/system/imx296-camera.service
    sed -i "s|Group=pi|Group=$(id -gn "$SUDO_USER")|g" /etc/systemd/system/imx296-camera.service
    
    # Reload systemd
    systemctl daemon-reload
    
    echo -e "${GREEN}Systemd service set up.${NC}"
    echo -e "To start the service: ${YELLOW}sudo systemctl start imx296-camera.service${NC}"
    echo -e "To enable autostart: ${YELLOW}sudo systemctl enable imx296-camera.service${NC}"
}

# Function to setup the camera permissions
setup_camera_permissions() {
    echo -e "${YELLOW}Setting up camera permissions...${NC}"
    
    # Add user to video and input groups
    usermod -a -G video "$SUDO_USER"
    usermod -a -G input "$SUDO_USER"
    
    # Set permissions for video devices
    for dev in /dev/video*; do
        if [ -e "$dev" ]; then
            chmod 666 "$dev"
        fi
    done
    
    # Set permissions for media devices
    for dev in /dev/media*; do
        if [ -e "$dev" ]; then
            chmod 666 "$dev"
        fi
    done
    
    echo -e "${GREEN}Camera permissions set up.${NC}"
}

# Function to make scripts executable
make_scripts_executable() {
    echo -e "${YELLOW}Making scripts executable...${NC}"
    
    chmod +x "${PROJECT_ROOT}/bin/run_imx296_capture.py"
    chmod +x "${PROJECT_ROOT}/bin/view-camera-status.sh"
    
    echo -e "${GREEN}Scripts are now executable.${NC}"
}

# Main installation process
echo -e "${YELLOW}Starting installation...${NC}"

# Install system dependencies
install_system_dependencies

# Create Python virtual environment
create_virtual_env

# Setup camera permissions
setup_camera_permissions

# Setup systemd service
setup_systemd_service

# Make scripts executable
make_scripts_executable

echo -e "${GREEN}Installation complete!${NC}"
echo
echo -e "${YELLOW}Next steps:${NC}"
echo "1. Check camera connection with: sudo media-ctl -d /dev/media0 -p"
echo "2. Start the service with: sudo systemctl start imx296-camera.service"
echo "3. View camera status with: ${PROJECT_ROOT}/bin/view-camera-status.sh"
echo "4. Enable autostart with: sudo systemctl enable imx296-camera.service"
echo
echo -e "${YELLOW}Control the camera with ntfy.sh:${NC}"
echo "- To start recording: curl -d \"start\" https://ntfy.sh/YOUR_TOPIC"
echo "- To stop recording: curl -d \"stop\" https://ntfy.sh/YOUR_TOPIC"
echo
echo -e "${YELLOW}Configuration:${NC}"
echo "- Edit config file at: ${PROJECT_ROOT}/config/config.yaml"
echo "- Recordings will be saved to: ${PROJECT_ROOT}/recordings"
echo

exit 0 