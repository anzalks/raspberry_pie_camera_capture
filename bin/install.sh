#!/bin/bash
# IMX296 Camera System Installation Script
# Author: Anzal KS <anzal.ks@gmail.com>
# Date: May 22, 2025

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "==== IMX296 Camera System Installation Script ===="
echo "Project root: $PROJECT_ROOT"

# Check if running as root
if [ "$EUID" -ne 0 ]; then
  echo "Please run as root (using sudo) to install system packages"
  exit 1
fi

# Install system dependencies
echo "----- Installing System Dependencies -----"
apt update
apt install -y python3-pip python3-venv libcamera-apps ffmpeg v4l-utils \
  build-essential cmake pkg-config libasio-dev git

# Function to build liblsl from source with version control
build_liblsl_from_source() {
  echo "----- Building liblsl from source -----"
  
  # Define repository URL and version tag (using a specific older version)
  LIBLSL_REPO="https://github.com/sccn/liblsl.git"
  LIBLSL_VERSION="v1.14.0"  # Specify an older stable version
  
  # Create temporary build directory
  BUILD_DIR="/tmp/liblsl_build_$(date +%s)"
  mkdir -p "$BUILD_DIR"
  cd "$BUILD_DIR"
  
  echo "Cloning liblsl repository..."
  git clone --depth=1 --branch "$LIBLSL_VERSION" "$LIBLSL_REPO" liblsl || {
    echo "Failed to clone liblsl repository."
    cd - >/dev/null
    return 1
  }
  
  echo "Building liblsl version $LIBLSL_VERSION..."
  cd liblsl
  mkdir -p build
  cd build
  
  # Configure and build
  cmake .. -DCMAKE_INSTALL_PREFIX=/usr/local || {
    echo "Failed to configure liblsl build."
    cd - >/dev/null
    return 1
  }
  
  # Build with multiple cores for speed
  cmake --build . -j$(nproc) || {
    echo "Failed to build liblsl."
    cd - >/dev/null
    return 1
  }
  
  # Install
  make install || {
    echo "Failed to install liblsl."
    cd - >/dev/null
    return 1
  }
  
  # Update shared library cache
  ldconfig
  
  # Return to original directory and cleanup
  cd "$PROJECT_ROOT"
  rm -rf "$BUILD_DIR"
  
  echo "✓ liblsl built and installed successfully."
  return 0
}

# Build and install liblsl
echo "Checking for liblsl library..."
if [ -f "/usr/local/lib/liblsl.so" ] || [ -f "/usr/lib/liblsl.so" ]; then
  echo "liblsl already installed, checking version..."
  INSTALLED_VER=$(ldconfig -p | grep liblsl | head -1)
  echo "Installed: $INSTALLED_VER"
  
  read -p "Do you want to reinstall liblsl anyway? (y/n): " reinstall_liblsl
  if [[ "$reinstall_liblsl" == "y" || "$reinstall_liblsl" == "Y" ]]; then
    build_liblsl_from_source
  else
    echo "Using existing liblsl installation."
  fi
else
  echo "liblsl not found. Building from source..."
  build_liblsl_from_source
fi

# Setup Python virtual environment
echo "----- Setting up Python Environment -----"
cd "$PROJECT_ROOT"

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
  echo "Creating Python virtual environment..."
  python3 -m venv .venv
fi

# Install Python dependencies
echo "Installing Python dependencies..."
.venv/bin/pip install --upgrade pip
.venv/bin/pip install wheel setuptools

# Install correct version of pylsl
echo "Installing pylsl and other dependencies..."
# First try to install pylsl that matches the liblsl version
.venv/bin/pip install "pylsl==1.14.0" || {
  echo "Failed to install specific pylsl version, trying latest..."
  .venv/bin/pip install pylsl
}

# Install other required packages
.venv/bin/pip install pyyaml requests psutil numpy

# Create required directories
echo "----- Creating Required Directories -----"
mkdir -p "$PROJECT_ROOT/logs"
mkdir -p "$PROJECT_ROOT/recordings"
chmod -R 777 "$PROJECT_ROOT/logs"
chmod -R 777 "$PROJECT_ROOT/recordings"

# Make scripts executable
echo "----- Setting Script Permissions -----"
chmod +x "$PROJECT_ROOT/bin/run_imx296_capture.py"
chmod +x "$PROJECT_ROOT/bin/restart_camera.sh"
chmod +x "$PROJECT_ROOT/bin/diagnose_camera.sh"
chmod +x "$PROJECT_ROOT/bin/view-camera-status.sh"
chmod +x "$PROJECT_ROOT/bin/check_recording.sh"

# Install systemd service if it doesn't exist
echo "----- Installing Systemd Service -----"
if [ ! -f "/etc/systemd/system/imx296-camera.service" ]; then
  echo "Installing systemd service..."
  cp "$PROJECT_ROOT/config/imx296-camera.service" /etc/systemd/system/
  systemctl daemon-reload
  
  # Ask user if they want to enable the service
  read -p "Do you want to enable the service to start on boot? (y/n): " enable_service
  if [[ "$enable_service" == "y" || "$enable_service" == "Y" ]]; then
    systemctl enable imx296-camera.service
    echo "Service enabled. It will start automatically on boot."
  else
    echo "Service installed but not enabled. Start manually with: sudo systemctl start imx296-camera.service"
  fi
else
  echo "Systemd service already installed."
  
  # Check if the service file needs to be updated
  diff -q "$PROJECT_ROOT/config/imx296-camera.service" /etc/systemd/system/imx296-camera.service >/dev/null 2>&1
  if [ $? -ne 0 ]; then
    read -p "Service file has changed. Update? (y/n): " update_service
    if [[ "$update_service" == "y" || "$update_service" == "Y" ]]; then
      cp "$PROJECT_ROOT/config/imx296-camera.service" /etc/systemd/system/
      systemctl daemon-reload
      echo "Service updated."
    fi
  fi
fi

# Create a simple desktop shortcut (if desktop environment detected)
if [ -d "$HOME/Desktop" ]; then
  echo "----- Creating Desktop Shortcut -----"
  cat > "$HOME/Desktop/IMX296-Camera.desktop" << EOF
[Desktop Entry]
Name=IMX296 Camera
Comment=IMX296 Camera Status Dashboard
Exec=x-terminal-emulator -e $PROJECT_ROOT/bin/view-camera-status.sh
Icon=camera
Terminal=false
Type=Application
Categories=Utility;
EOF
  chmod +x "$HOME/Desktop/IMX296-Camera.desktop"
  echo "Desktop shortcut created."
fi

# Test the camera
echo "----- Testing Camera -----"
echo "Checking for camera..."
if libcamera-hello --list-cameras | grep -i "imx296"; then
  echo "✓ IMX296 camera found!"
else
  echo "⚠ No IMX296 camera detected. Please check the hardware connection."
fi

# Test liblsl and pylsl
echo "----- Testing LSL Installation -----"
if [ -f "/usr/local/lib/liblsl.so" ] || [ -f "/usr/lib/liblsl.so" ]; then
  echo "✓ liblsl library found"
else
  echo "⚠ liblsl library not found. LSL functionality may not work."
fi

if "$PROJECT_ROOT/.venv/bin/pip" list | grep -q "pylsl"; then
  PYLSL_VERSION=$("$PROJECT_ROOT/.venv/bin/pip" show pylsl | grep "Version" | awk '{print $2}')
  echo "✓ pylsl package installed (version $PYLSL_VERSION)"
else
  echo "⚠ pylsl package not installed. LSL functionality will not work."
fi

echo ""
echo "Installation complete!"
echo ""
echo "To start the camera service:"
echo "  sudo systemctl start imx296-camera.service"
echo ""
echo "To view the camera dashboard:"
echo "  $PROJECT_ROOT/bin/view-camera-status.sh"
echo ""
echo "If you encounter any issues, run the diagnostic tool:"
echo "  $PROJECT_ROOT/bin/diagnose_camera.sh" 