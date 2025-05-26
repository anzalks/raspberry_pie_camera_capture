#!/bin/bash
# IMX296 Camera System Installation Script - Dynamic Path Compatible
# Author: Anzal KS <anzal.ks@gmail.com>
# Date: December 2024
#
# DYNAMIC PATH COMPATIBILITY:
# ==========================
# 
# All paths are now dynamically detected:
# - Project root: Auto-detected from script location
# - User home: Dynamic detection via getent/whoami
# - Installation paths: Relative to detected project root
# - Service files: Generated with dynamic paths at install time
# - Virtual environment: Created relative to project root
# - Configuration: Dynamic path substitution in all configs
#
# RASPBERRY PI BOOKWORM COMPATIBILITY FIXES:
# ==========================================
# 
# Package Installation Issues Fixed:
# - v4l2-utils → v4l-utils (Bookworm package name change)
# - Graceful fallback for missing packages
# - Enhanced error handling with apt-cache checks
# - Alternative package detection for different OS versions
#
# liblsl Build Issues Fixed:
# - Updated to use stable liblsl versions (v1.16.x)
# - Improved version checking and fallback logic
# - Fixed cmake configuration for Bookworm
# - Proper build directory cleanup
# - Enhanced error handling for git clone failures
#
# pylsl Installation Issues Fixed:
# - Dynamic Python version detection for symlinks
# - Architecture-specific library linking (liblsl64.so, etc.)
# - Proper virtual environment permissions
# - Post-installation symlink creation and verification
# - Fixed LSL functionality testing
#
# Permission and User Issues Fixed:
# - Dynamic SUDO_USER detection and handling
# - Virtual environment ownership corrections
# - Directory permission management
# - Real user home directory detection
#
# Missing Functions Fixed:
# - Added update_camera_config() function
# - Enhanced installation testing and verification
# - Comprehensive dependency installation
# - Systemd service configuration improvements
#
# System Integration Fixed:
# - Camera hardware detection with libcamera
# - Media device auto-detection improvements
# - Desktop shortcut creation for GUI environments
# - Configuration file generation with unique topics
# - Video device permission management

set -e  # Exit on error for better debugging

# Dynamic path detection - works regardless of installation location
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$(dirname "$SCRIPT_DIR")" && pwd)"

# Define colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}==== IMX296 Camera System Installation Script (Dynamic Path Compatible) ====${NC}"
echo "Script directory: $SCRIPT_DIR"
echo "Project root: $PROJECT_ROOT"

# Check if running as root
if [ "$EUID" -ne 0 ]; then
  echo -e "${RED}Please run as root (using sudo) to install system packages${NC}"
  exit 1
fi

# Get the real user who ran sudo - dynamic detection
if [ -n "$SUDO_USER" ]; then
    REAL_USER="$SUDO_USER"
    REAL_USER_HOME=$(getent passwd "$REAL_USER" | cut -d: -f6)
elif [ -n "$USER" ]; then
    REAL_USER="$USER"
    REAL_USER_HOME="$HOME"
else
    # Fallback: detect the user who owns the project directory
    REAL_USER=$(stat -c '%U' "$PROJECT_ROOT")
    REAL_USER_HOME=$(getent passwd "$REAL_USER" | cut -d: -f6)
fi

echo "Installing for user: $REAL_USER"
echo "User home: $REAL_USER_HOME"
echo "Project location: $PROJECT_ROOT"

# Update package list
echo -e "${YELLOW}----- Updating Package List -----${NC}"
apt update

# Install system dependencies with Bookworm-compatible package names
echo -e "${YELLOW}----- Installing System Dependencies -----${NC}"

# Check if v4l-utils (note: not v4l2-utils) is available
if apt-cache show v4l-utils >/dev/null 2>&1; then
    V4L_PACKAGE="v4l-utils"
elif apt-cache show v4l2-utils >/dev/null 2>&1; then
    V4L_PACKAGE="v4l2-utils"
else
    echo -e "${YELLOW}Warning: Neither v4l-utils nor v4l2-utils found. Continuing without it.${NC}"
    V4L_PACKAGE=""
fi

# Install basic packages that are definitely available
echo "Installing basic system packages..."
apt install -y \
  python3 \
  python3-pip \
  python3-venv \
  python3-dev \
  libcamera-apps \
  ffmpeg \
  git \
  build-essential \
  cmake \
  pkg-config \
  curl \
  wget

# Install V4L package if available
if [ -n "$V4L_PACKAGE" ]; then
    echo "Installing $V4L_PACKAGE..."
    apt install -y "$V4L_PACKAGE"
else
    echo -e "${YELLOW}Skipping V4L utilities installation${NC}"
fi

# Install boost libraries for LSL
echo "Installing Boost libraries for LSL..."
apt install -y \
  libboost-dev \
  libboost-thread-dev \
  libboost-filesystem-dev \
  libboost-system-dev \
  libboost-regex-dev \
  libboost-atomic-dev \
  libboost-chrono-dev \
  libboost-date-time-dev \
  libasio-dev || echo -e "${YELLOW}Some boost packages not available, continuing...${NC}"

# Install additional useful packages
echo "Installing additional packages..."
apt install -y \
  dialog \
  libssl-dev \
  libffi-dev || echo -e "${YELLOW}Some additional packages not available, continuing...${NC}"

# Function to build liblsl from source with proper version checking
build_liblsl_from_source() {
  echo -e "${YELLOW}----- Building liblsl from source -----${NC}"
  
  # Define repository URL
  LIBLSL_REPO="https://github.com/sccn/liblsl.git"
  
  # Create temporary build directory
  BUILD_DIR="/tmp/liblsl_build_$(date +%s)"
  mkdir -p "$BUILD_DIR"
  cd "$BUILD_DIR"
  
  echo "Cloning liblsl repository..."
  if ! git clone "$LIBLSL_REPO" liblsl; then
    echo -e "${RED}Failed to clone liblsl repository. Check your internet connection.${NC}"
    cd "$PROJECT_ROOT"
    return 1
  fi
  
  cd liblsl
  
  # Check available tags and use a stable one
  echo "Checking available versions..."
  git fetch --tags
  
  # Try to use a stable version (v1.16.2 is more recent and stable)
  LIBLSL_VERSION=""
  if git tag | grep -q "v1.16.2"; then
    LIBLSL_VERSION="v1.16.2"
  elif git tag | grep -q "v1.16.1"; then
    LIBLSL_VERSION="v1.16.1"
  elif git tag | grep -q "v1.16.0"; then
    LIBLSL_VERSION="v1.16.0"
  elif git tag | grep -q "v1.15"; then
    LIBLSL_VERSION=$(git tag | grep "v1.15" | sort -V | tail -1)
  fi
  
  if [ -n "$LIBLSL_VERSION" ]; then
    echo "Using liblsl version: $LIBLSL_VERSION"
    git checkout "$LIBLSL_VERSION"
  else
    echo -e "${YELLOW}Using default branch (latest)${NC}"
  fi
  
  echo "Preparing to build liblsl..."
  mkdir -p build
  cd build
  
  # Configure and build with specific options
  echo "Configuring liblsl build..."
  cmake .. \
    -DCMAKE_INSTALL_PREFIX=/usr/local \
    -DLSL_BUNDLED_BOOST=ON \
    -DLSL_UNIXFOLDERS=ON \
    -DLSL_NO_FANCY_LIBNAME=ON \
    -DCMAKE_BUILD_TYPE=Release
  
  # Build with multiple cores for speed
  echo "Building liblsl (this may take a few minutes)..."
  make -j$(nproc)
  
  # Install
  echo "Installing liblsl to system..."
  make install
  
  # Update shared library cache
  echo "Updating shared library cache..."
  ldconfig
  
  # Return to original directory and cleanup
  cd "$PROJECT_ROOT"
  rm -rf "$BUILD_DIR"
  
  echo -e "${GREEN}✓ liblsl built and installed successfully.${NC}"
  return 0
}

# Check for existing liblsl installation
echo -e "${YELLOW}Checking for liblsl library...${NC}"
if ldconfig -p | grep -q "liblsl\.so"; then
  echo -e "${GREEN}liblsl already installed in system libraries${NC}"
  INSTALLED_VER=$(ldconfig -p | grep liblsl | head -1)
  echo "Installed: $INSTALLED_VER"
elif [ -f "/usr/local/lib/liblsl.so" ]; then
  echo -e "${GREEN}liblsl already installed in /usr/local/lib${NC}"
  ldconfig  # Make sure it's in the cache
else
  echo -e "${YELLOW}liblsl not found. Building from source...${NC}"
  build_liblsl_from_source
fi

# Setup Python virtual environment
echo -e "${YELLOW}----- Setting up Python Environment -----${NC}"
cd "$PROJECT_ROOT"

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
  echo "Creating Python virtual environment..."
  sudo -u "$REAL_USER" python3 -m venv --system-site-packages .venv
else
  echo "Using existing Python virtual environment."
fi

# Make sure the venv is owned by the correct user
chown -R "$REAL_USER:$(id -g $REAL_USER)" .venv

# Function to run pip in the virtual environment as the real user
pip_install_as_user() {
  sudo -u "$REAL_USER" "$PROJECT_ROOT/.venv/bin/pip" "$@"
}

# Install Python dependencies
echo "Installing Python dependencies..."
pip_install_as_user install --upgrade pip setuptools wheel

# Install pylsl with compatibility for liblsl
echo "Installing pylsl (Lab Streaming Layer)..."
pip_install_as_user install pylsl>=1.16.0

# Create symlinks to the liblsl library for pylsl compatibility
echo -e "${YELLOW}Creating architecture-specific symlinks for liblsl...${NC}"
LIBLSL_PATH=""
if [ -f "/usr/local/lib/liblsl.so" ]; then
  LIBLSL_PATH="/usr/local/lib/liblsl.so"
elif ldconfig -p | grep -q "liblsl\.so"; then
  LIBLSL_PATH=$(ldconfig -p | grep "liblsl\.so" | head -1 | awk '{print $4}')
fi

if [ -n "$LIBLSL_PATH" ]; then
  echo "Found liblsl at: $LIBLSL_PATH"
  
  # Find the correct python version in venv
  PYTHON_VERSION=$(sudo -u "$REAL_USER" "$PROJECT_ROOT/.venv/bin/python3" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
  PYLSL_DIR="$PROJECT_ROOT/.venv/lib/python${PYTHON_VERSION}/site-packages/pylsl"
  
  # Create necessary directory structure if it exists
  if [ -d "$PYLSL_DIR" ]; then
    sudo -u "$REAL_USER" mkdir -p "$PYLSL_DIR/lib"
    
    # Create symlinks for various architectures
    sudo -u "$REAL_USER" ln -sf "$LIBLSL_PATH" "$PYLSL_DIR/liblsl.so" || true
    sudo -u "$REAL_USER" ln -sf "$LIBLSL_PATH" "$PYLSL_DIR/liblsl32.so" || true
    sudo -u "$REAL_USER" ln -sf "$LIBLSL_PATH" "$PYLSL_DIR/liblsl64.so" || true
    sudo -u "$REAL_USER" ln -sf "$LIBLSL_PATH" "$PYLSL_DIR/lib/liblsl.so" || true
    sudo -u "$REAL_USER" ln -sf "$LIBLSL_PATH" "$PYLSL_DIR/lib/liblsl32.so" || true
    sudo -u "$REAL_USER" ln -sf "$LIBLSL_PATH" "$PYLSL_DIR/lib/liblsl64.so" || true
    
    echo -e "${GREEN}Created symlinks for liblsl library${NC}"
  else
    echo -e "${YELLOW}pylsl directory not found yet, will create symlinks after installation${NC}"
  fi
else
  echo -e "${RED}Could not find liblsl library path${NC}"
fi

# Install other Python dependencies
echo "Installing other Python packages..."
pip_install_as_user install \
  pyyaml>=6.0 \
  requests>=2.28.0 \
  psutil>=5.9.0 \
  numpy \
  scipy \
  matplotlib

# Create required directories with dynamic paths
echo -e "${YELLOW}----- Creating Required Directories -----${NC}"
sudo -u "$REAL_USER" mkdir -p "$PROJECT_ROOT/logs"
sudo -u "$REAL_USER" mkdir -p "$PROJECT_ROOT/recordings"
sudo -u "$REAL_USER" mkdir -p "$REAL_USER_HOME/recordings"

# Set script permissions
echo -e "${YELLOW}----- Setting Script Permissions -----${NC}"
chmod +x "$PROJECT_ROOT/bin/"*.py || true
chmod +x "$PROJECT_ROOT/bin/"*.sh || true
chmod +x "$PROJECT_ROOT/setup/"*.sh || true

# Function to update camera config (this was missing in the original)
update_camera_config() {
  echo "Updating camera configuration with dynamic paths..."
  CONFIG_FILE="$PROJECT_ROOT/config/config.yaml"
  if [ -f "$CONFIG_FILE" ]; then
    # Ensure the config has proper video format settings
    if ! grep -q "video_format.*mkv" "$CONFIG_FILE"; then
      echo "  video_format: \"mkv\"" >> "$CONFIG_FILE"
    fi
    if ! grep -q "codec.*mjpeg" "$CONFIG_FILE"; then
      echo "  codec: \"mjpeg\"" >> "$CONFIG_FILE"
    fi
    
    # Update any hardcoded paths to be relative to project root
    sed -i "s|script_path: \"/.*GScrop\"|script_path: \"bin/GScrop\"|" "$CONFIG_FILE"
    sed -i "s|output_dir: \"/.*recordings\"|output_dir: \"recordings\"|" "$CONFIG_FILE"
    
    echo -e "${GREEN}✓ Camera configuration updated with dynamic paths${NC}"
  else
    echo -e "${YELLOW}Config file not found, will be created on first run${NC}"
  fi
}

# Copy config file example if needed and configure dynamic paths
if [ ! -f "$PROJECT_ROOT/config/config.yaml" ] && [ -f "$PROJECT_ROOT/config/config.yaml.example" ]; then
  echo "Creating config.yaml from example with dynamic paths..."
  sudo -u "$REAL_USER" cp "$PROJECT_ROOT/config/config.yaml.example" "$PROJECT_ROOT/config/config.yaml"
  
  # Detect the actual media device for the IMX296 camera
  echo "Detecting IMX296 camera media device..."
  MEDIA_DEVICE=""
  for i in {0..9}; do
    if [ -e "/dev/media$i" ]; then
      if command -v media-ctl >/dev/null && media-ctl -d "/dev/media$i" -p 2>/dev/null | grep -q -i "imx296"; then
        MEDIA_DEVICE="/dev/media$i"
        echo "Found IMX296 camera on $MEDIA_DEVICE"
        break
      fi
    fi
  done
  
  if [ -n "$MEDIA_DEVICE" ]; then
    # Update the config file with the detected device
    sed -i "s|device_pattern: \"/dev/media0\"|device_pattern: \"$MEDIA_DEVICE\"|" "$PROJECT_ROOT/config/config.yaml"
    echo "Updated config with camera device: $MEDIA_DEVICE"
  fi
  
  # Create a unique ntfy topic based on hostname and project location
  NTFY_TOPIC="$(hostname)-camera-$(basename "$PROJECT_ROOT")-$(date +%s | tail -c 6)"
  sed -i "s|topic: \"raspie-camera\"|topic: \"$NTFY_TOPIC\"|" "$PROJECT_ROOT/config/config.yaml"
  echo "Set ntfy.sh topic to: $NTFY_TOPIC"
fi

# Update camera config with dynamic paths
update_camera_config

# Test installations
echo -e "${YELLOW}----- Testing Installations -----${NC}"

# Test Python dependencies
echo "Testing Python dependencies..."
if sudo -u "$REAL_USER" "$PROJECT_ROOT/.venv/bin/python3" -c "import yaml, requests, psutil; print('✓ Basic Python dependencies OK')"; then
  echo -e "${GREEN}✓ Python dependencies installed successfully${NC}"
else
  echo -e "${RED}✗ Python dependencies test failed${NC}"
fi

# Test LSL installation
echo "Testing LSL installation..."
if sudo -u "$REAL_USER" "$PROJECT_ROOT/.venv/bin/python3" -c "import pylsl; print(f'✓ pylsl version: {pylsl.version.__version__}')"; then
  echo -e "${GREEN}✓ LSL installation successful${NC}"
  
  # Test LSL functionality
  echo "Testing LSL stream creation..."
  if sudo -u "$REAL_USER" "$PROJECT_ROOT/.venv/bin/python3" -c "
import pylsl
info = pylsl.StreamInfo('test', 'Test', 1, 100, 'float32', 'test')
outlet = pylsl.StreamOutlet(info)
print('✓ LSL stream creation successful')
"; then
    echo -e "${GREEN}✓ LSL functionality test passed${NC}"
  else
    echo -e "${YELLOW}⚠ LSL stream creation test failed, but pylsl is installed${NC}"
  fi
else
  echo -e "${RED}✗ LSL installation test failed${NC}"
  echo "Trying to fix pylsl installation..."
  
  # Re-create symlinks after pylsl installation
  if [ -n "$LIBLSL_PATH" ]; then
    PYTHON_VERSION=$(sudo -u "$REAL_USER" "$PROJECT_ROOT/.venv/bin/python3" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    PYLSL_DIR="$PROJECT_ROOT/.venv/lib/python${PYTHON_VERSION}/site-packages/pylsl"
    
    if [ -d "$PYLSL_DIR" ]; then
      sudo -u "$REAL_USER" mkdir -p "$PYLSL_DIR/lib"
      sudo -u "$REAL_USER" ln -sf "$LIBLSL_PATH" "$PYLSL_DIR/liblsl64.so"
      echo "Re-created pylsl symlinks"
      
      # Test again
      if sudo -u "$REAL_USER" "$PROJECT_ROOT/.venv/bin/python3" -c "import pylsl; print('✓ pylsl working after symlink fix')"; then
        echo -e "${GREEN}✓ LSL fixed and working${NC}"
      else
        echo -e "${YELLOW}⚠ LSL still not working, may need manual intervention${NC}"
      fi
    fi
  fi
fi

# Test camera hardware
echo -e "${YELLOW}----- Testing Camera Hardware -----${NC}"
echo "Checking for cameras with libcamera-hello..."
if libcamera-hello --list-cameras 2>/dev/null | grep -i imx296; then
  echo -e "${GREEN}✓ IMX296 camera detected${NC}"
elif libcamera-hello --list-cameras 2>/dev/null | grep -q "Available cameras"; then
  echo -e "${YELLOW}⚠ Cameras detected but no IMX296 found${NC}"
  libcamera-hello --list-cameras
else
  echo -e "${YELLOW}⚠ No cameras detected or libcamera not working${NC}"
  echo "This is normal if you're running on a development machine without the camera."
fi

# Generate systemd service with dynamic paths
echo -e "${YELLOW}----- Installing Systemd Service with Dynamic Paths -----${NC}"
SERVICE_FILE="/etc/systemd/system/imx296-camera.service"

if [ ! -f "$SERVICE_FILE" ]; then
  echo "Installing systemd service with dynamic paths..."
  
  cat > "$SERVICE_FILE" << EOF
[Unit]
Description=IMX296 Global Shutter Camera Service
After=network.target

[Service]
Type=simple
User=$REAL_USER
Group=$(id -gn $REAL_USER)
WorkingDirectory=$PROJECT_ROOT
ExecStart=$PROJECT_ROOT/.venv/bin/python $PROJECT_ROOT/bin/run_imx296_capture.py
Restart=on-failure
RestartSec=10s
Environment=PATH=$PROJECT_ROOT/.venv/bin:/usr/local/bin:/usr/bin:/bin
Environment=PYTHONPATH=$PROJECT_ROOT

[Install]
WantedBy=multi-user.target
EOF
  
  systemctl daemon-reload
  
  echo -e "${GREEN}✓ Systemd service installed with dynamic paths${NC}"
  echo "To start: sudo systemctl start imx296-camera"
  echo "To enable on boot: sudo systemctl enable imx296-camera"
else
  echo "Systemd service already exists"
fi

# Generate systemd service with monitor and dynamic paths
SERVICE_MONITOR_FILE="/etc/systemd/system/imx296-camera-monitor.service"

if [ ! -f "$SERVICE_MONITOR_FILE" ]; then
  echo "Installing systemd service with monitor and dynamic paths..."
  
  cat > "$SERVICE_MONITOR_FILE" << EOF
[Unit]
Description=IMX296 Camera Service with Status Monitor
After=network.target
Wants=network.target

[Service]
Type=simple
User=$REAL_USER
Group=$(id -gn $REAL_USER)
WorkingDirectory=$PROJECT_ROOT
ExecStart=$PROJECT_ROOT/.venv/bin/python $PROJECT_ROOT/bin/start_camera_with_monitor.py --monitor --no-output
Environment=PYTHONPATH=$PROJECT_ROOT
Environment=PATH=$PROJECT_ROOT/.venv/bin:/usr/local/bin:/usr/bin:/bin
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

# Service management
KillMode=mixed
TimeoutStopSec=10

[Install]
WantedBy=multi-user.target
EOF
  
  systemctl daemon-reload
  
  echo -e "${GREEN}✓ Systemd monitor service installed with dynamic paths${NC}"
  echo "To start: sudo systemctl start imx296-camera-monitor"
  echo "To enable on boot: sudo systemctl enable imx296-camera-monitor"
else
  echo "Systemd monitor service already exists"
fi

# Create desktop shortcut if desktop environment exists
if [ -d "$REAL_USER_HOME/Desktop" ]; then
  echo -e "${YELLOW}----- Creating Desktop Shortcut with Dynamic Paths -----${NC}"
  DESKTOP_FILE="$REAL_USER_HOME/Desktop/IMX296-Camera.desktop"
  
  sudo -u "$REAL_USER" cat > "$DESKTOP_FILE" << EOF
[Desktop Entry]
Name=IMX296 Camera System
Comment=IMX296 Camera Status Monitor
Exec=x-terminal-emulator -e '$PROJECT_ROOT/.venv/bin/python $PROJECT_ROOT/bin/status_monitor.py'
Icon=camera
Terminal=true
Type=Application
Categories=Utility;
Path=$PROJECT_ROOT
EOF
  
  sudo -u "$REAL_USER" chmod +x "$DESKTOP_FILE"
  echo -e "${GREEN}✓ Desktop shortcut created with dynamic paths${NC}"
fi

# Configure IMX296 camera module
configure_imx296_camera() {
  echo -e "${YELLOW}----- Configuring IMX296 Camera -----${NC}"
  
  # Check if the imx296 module is loaded
  if ! lsmod | grep -q "imx296"; then
    echo "Loading IMX296 camera module..."
    modprobe imx296 || true
  fi
  
  # Create modprobe configuration file for IMX296
  echo "Creating modprobe configuration for IMX296..."
  cat > /etc/modprobe.d/imx296.conf << EOF
# IMX296 camera module configuration
# This enables compatibility mode which may help with streaming issues
options imx296 compatible_mode=1
EOF
  
  # Check for dtoverlay in config.txt
  if [ -f "/boot/config.txt" ]; then
    if ! grep -q "dtoverlay=imx296" "/boot/config.txt"; then
      echo "Adding IMX296 device tree overlay to /boot/config.txt..."
      echo "# IMX296 Global Shutter Camera" >> /boot/config.txt
      echo "dtoverlay=imx296" >> /boot/config.txt
      echo "gpu_mem=128" >> /boot/config.txt
    else
      echo "IMX296 device tree overlay already configured."
    fi
  fi
  
  # Set correct permissions for video devices
  echo "Setting video device permissions..."
  if [ -e "/dev/video0" ]; then
    chmod a+rw /dev/video* || true
  fi
  
  # Create udev rule for persistent permissions
  echo "Creating udev rule for IMX296 camera..."
  cat > /etc/udev/rules.d/99-imx296-camera.rules << EOF
# IMX296 Camera udev rules
KERNEL=="video*", SUBSYSTEM=="video4linux", GROUP="video", MODE="0666"
KERNEL=="media*", SUBSYSTEM=="media", GROUP="video", MODE="0666"
EOF

  # Reload udev rules
  udevadm control --reload-rules || true
  udevadm trigger || true
  
  echo -e "${GREEN}IMX296 camera configuration complete.${NC}"
}

# Configure camera if detected
if libcamera-hello --list-cameras 2>/dev/null | grep -i imx296; then
  configure_imx296_camera
fi

# Final recommendations with dynamic paths
echo -e "${GREEN}==== Installation Complete ====${NC}"
echo ""
echo -e "${YELLOW}Installation Summary:${NC}"
echo "Project root: $PROJECT_ROOT"
echo "User: $REAL_USER"
echo "User home: $REAL_USER_HOME"
echo "Virtual environment: $PROJECT_ROOT/.venv"
echo ""
echo -e "${YELLOW}Next Steps:${NC}"
echo "1. Connect your IMX296 camera to the Raspberry Pi"
echo "2. Reboot the system to ensure all drivers are loaded:"
echo "   sudo reboot"
echo ""
echo "3. After reboot, test the system:"
echo "   cd $PROJECT_ROOT"
echo "   ./bin/clean_start_camera.sh -m"
echo ""
echo "4. Or run individual components:"
echo "   # Test camera: libcamera-hello --list-cameras"
echo "   # Run system: $PROJECT_ROOT/.venv/bin/python $PROJECT_ROOT/bin/run_imx296_capture.py"
echo "   # Monitor: $PROJECT_ROOT/.venv/bin/python $PROJECT_ROOT/bin/status_monitor.py"
echo ""
echo "5. For smartphone control, configure ntfy topic in $PROJECT_ROOT/config/config.yaml"
echo ""
echo -e "${GREEN}Installation log completed successfully with dynamic path support!${NC}"

exit 0 