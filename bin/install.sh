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
        git \
        build-essential \
        cmake \
        libasio-dev
    
    echo -e "${GREEN}System dependencies installed.${NC}"
}

# Function to build liblsl from source
build_liblsl_from_source() {
    echo -e "${YELLOW}Installing liblsl (LabStreamingLayer library)...${NC}"
    
    # First attempt to install via apt
    echo "Attempting to install liblsl-dev via apt..."
    if apt install -y liblsl-dev; then
        echo -e "${GREEN}liblsl-dev installed successfully via apt.${NC}"
        return 0
    fi
    
    echo "apt install liblsl-dev failed. Attempting to build from source..."
    
    # Get username of the user who ran sudo
    SUDO_USER_HOME=$(getent passwd "$SUDO_USER" | cut -d: -f6)
    
    # Store original directory
    ORIG_DIR=$(pwd)
    
    # Create build directory in a standard location
    BUILD_DIR="$SUDO_USER_HOME/liblsl_build"
    # Remove if it exists
    if [ -d "$BUILD_DIR" ]; then
        echo "Removing existing liblsl build directory..."
        rm -rf "$BUILD_DIR"
    fi
    
    # Create directory and set permissions
    mkdir -p "$BUILD_DIR"
    chown "$SUDO_USER":"$(id -gn "$SUDO_USER")" "$BUILD_DIR"
    
    echo "Using build directory: $BUILD_DIR"
    cd "$BUILD_DIR" || {
        echo -e "${RED}Failed to change to build directory.${NC}"
        cd "$ORIG_DIR"
        return 1
    }
    
    # Clone the LSL repository
    echo "Cloning LSL repository..."
    if ! su -c "git clone --depth=1 https://github.com/sccn/liblsl.git" "$SUDO_USER"; then
        echo -e "${RED}Failed to clone liblsl repository.${NC}"
        cd "$ORIG_DIR"
        rm -rf "$BUILD_DIR"
        return 1
    fi
    
    cd liblsl || {
        echo -e "${RED}Failed to change to liblsl directory.${NC}"
        cd "$ORIG_DIR"
        rm -rf "$BUILD_DIR"
        return 1
    }
    
    # Create build directory
    mkdir -p build
    cd build || {
        echo -e "${RED}Failed to create/enter build directory.${NC}"
        cd "$ORIG_DIR"
        rm -rf "$BUILD_DIR"
        return 1
    }
    
    # Configure and build
    echo "Configuring liblsl build with CMake..."
    if ! su -c "cmake .. -DCMAKE_INSTALL_PREFIX=/usr/local" "$SUDO_USER"; then
        echo -e "${RED}Failed to configure liblsl build.${NC}"
        cd "$ORIG_DIR"
        rm -rf "$BUILD_DIR"
        return 1
    fi
    
    echo "Compiling liblsl (this may take a while)..."
    if ! su -c "cmake --build . -j$(nproc)" "$SUDO_USER"; then
        echo -e "${RED}Failed to build liblsl.${NC}"
        cd "$ORIG_DIR"
        rm -rf "$BUILD_DIR"
        return 1
    fi
    
    # Install (this needs to be done as root)
    echo "Installing liblsl..."
    if ! make install; then
        echo -e "${RED}Failed to install liblsl.${NC}"
        cd "$ORIG_DIR"
        rm -rf "$BUILD_DIR"
        return 1
    fi
    
    echo "Updating shared library cache..."
    ldconfig
    
    # Clean up
    cd "$ORIG_DIR" || true
    rm -rf "$BUILD_DIR"
    
    echo -e "${GREEN}liblsl built and installed from source.${NC}"
    return 0
}

# Function to create Python virtual environment and install packages
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
    
    # Create new venv with system site packages (allows access to system-installed packages)
    echo "Creating new virtual environment..."
    sudo -u "$SUDO_USER" python3 -m venv --system-site-packages "$VENV_DIR"
    
    # Install required Python packages
    echo "Installing required Python packages..."
    sudo -u "$SUDO_USER" "${VENV_DIR}/bin/pip" install --upgrade pip setuptools wheel
    sudo -u "$SUDO_USER" "${VENV_DIR}/bin/pip" install pyyaml requests psutil
    
    # Install pylsl separately - this needs the liblsl library already installed
    echo "Installing pylsl (Python LSL bindings)..."
    sudo -u "$SUDO_USER" "${VENV_DIR}/bin/pip" install pylsl
    
    echo -e "${GREEN}Python virtual environment created and packages installed.${NC}"
}

# Function to detect IMX296 camera and update configuration
detect_camera_and_update_config() {
    echo -e "${YELLOW}Detecting IMX296 camera...${NC}"
    
    # Find the media device that contains the IMX296 camera
    CAMERA_DEVICE=""
    for i in {0..9}; do
        if [ -e "/dev/media$i" ]; then
            if media-ctl -d "/dev/media$i" -p 2>/dev/null | grep -q -i "imx296"; then
                CAMERA_DEVICE="/dev/media$i"
                echo -e "${GREEN}Found IMX296 camera on ${CAMERA_DEVICE}${NC}"
                break
            fi
        fi
    done
    
    if [ -z "$CAMERA_DEVICE" ]; then
        echo -e "${RED}Warning: IMX296 camera not detected on any media device.${NC}"
        echo -e "${YELLOW}The camera might be disconnected or not properly recognized.${NC}"
        echo -e "${YELLOW}The script will continue but camera detection might fail when running.${NC}"
        return
    fi
    
    # Update the config.yaml file with the detected device
    CONFIG_FILE="${PROJECT_ROOT}/config/config.yaml"
    
    # Make sure the config directory exists
    mkdir -p "${PROJECT_ROOT}/config"
    
    # Check if config file exists, if not create it
    if [ ! -f "$CONFIG_FILE" ]; then
        echo -e "${YELLOW}Config file not found, creating default config...${NC}"
        # Copy the default config file if it exists
        if [ -f "${PROJECT_ROOT}/config/config.yaml.example" ]; then
            cp "${PROJECT_ROOT}/config/config.yaml.example" "$CONFIG_FILE"
        fi
    fi
    
    # Update the device_pattern in the config file
    if [ -f "$CONFIG_FILE" ]; then
        # Create a unique ntfy topic based on hostname
        HOSTNAME=$(hostname)
        NTFY_TOPIC="raspie-camera-${HOSTNAME}-$(date +%s | head -c 6)"
        
        # Use sed to update the config file
        sed -i "s|device_pattern: \"/dev/media[0-9]*\"|device_pattern: \"$CAMERA_DEVICE\"|" "$CONFIG_FILE"
        sed -i "s|topic: \"raspie-camera\"|topic: \"$NTFY_TOPIC\"|" "$CONFIG_FILE"
        
        echo -e "${GREEN}Updated config with camera device: ${CAMERA_DEVICE}${NC}"
        echo -e "${GREEN}Updated ntfy.sh topic to: ${NTFY_TOPIC}${NC}"
    else
        echo -e "${RED}Error: Could not update config file. Config file not found.${NC}"
    fi
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

# Build and install liblsl (C/C++ library)
echo -e "${YELLOW}Setting up Lab Streaming Layer (LSL) support...${NC}"
if ! build_liblsl_from_source; then
    echo -e "${RED}Warning: Failed to install liblsl. LSL functionality may not work.${NC}"
    echo -e "${YELLOW}Continuing with installation, but you may need to install liblsl manually.${NC}"
fi

# Create Python virtual environment and install packages including pylsl
echo -e "${YELLOW}Setting up Python environment...${NC}"
create_virtual_env

# Detect camera and update configuration
detect_camera_and_update_config

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