#!/bin/bash
# IMX296 Camera System Installation Script
# Author: Anzal KS <anzal.ks@gmail.com>
# Date: May 22, 2025

# Don't use set -e to prevent script from exiting on errors
# Instead check return values explicitly

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Define colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}==== IMX296 Camera System Installation Script ====${NC}"
echo "Project root: $PROJECT_ROOT"

# Check if running as root
if [ "$EUID" -ne 0 ]; then
  echo -e "${RED}Please run as root (using sudo) to install system packages${NC}"
  exit 1
fi

# Install system dependencies
echo -e "${YELLOW}----- Installing System Dependencies -----${NC}"
apt update
apt install -y python3 python3-pip python3-venv \
  libcamera-apps v4l-utils ffmpeg \
  git build-essential cmake pkg-config \
  libasio-dev libboost-dev libboost-thread-dev \
  libboost-filesystem-dev libboost-system-dev \
  libboost-regex-dev libboost-atomic-dev \
  libboost-chrono-dev libboost-date-time-dev \
  dialog  # For the dashboard UI

# Function to build liblsl from source (older version)
build_liblsl_from_source() {
  echo -e "${YELLOW}----- Building liblsl from source -----${NC}"
  
  # Define repository URL and version tag
  LIBLSL_REPO="https://github.com/sccn/liblsl.git"
  LIBLSL_VERSION="v1.13.0"  # Use the exact older version that's known to work well
  
  echo "Using liblsl version: $LIBLSL_VERSION"
  
  # Create temporary build directory
  BUILD_DIR="/tmp/liblsl_build_$(date +%s)"
  mkdir -p "$BUILD_DIR"
  cd "$BUILD_DIR"
  
  echo "Cloning liblsl repository..."
  if ! git clone --depth=1 --branch "$LIBLSL_VERSION" "$LIBLSL_REPO" liblsl; then
    echo -e "${RED}Failed to clone liblsl repository.${NC}"
    echo "Attempting to clone without specifying version..."
    
    # Try again without version specification
    if ! git clone --depth=1 "$LIBLSL_REPO" liblsl; then
      echo -e "${RED}Failed to clone liblsl repository. Check your internet connection.${NC}"
      cd "$PROJECT_ROOT"
      return 1
    fi
    
    # Try to checkout the specified version
    cd liblsl
    if ! git checkout "$LIBLSL_VERSION"; then
      echo -e "${YELLOW}Warning: Could not checkout version $LIBLSL_VERSION. Using default branch.${NC}"
    fi
    cd ..
  fi
  
  echo "Preparing to build liblsl..."
  cd liblsl
  mkdir -p build
  cd build
  
  # Configure and build with specific options to match original install
  echo "Configuring liblsl build..."
  if ! cmake .. -DCMAKE_INSTALL_PREFIX=/usr/local -DLSL_BUNDLED_BOOST=ON -DLSL_UNIXFOLDERS=ON -DLSL_NO_FANCY_LIBNAME=ON; then
    echo -e "${RED}Failed to configure liblsl build.${NC}"
    cd "$PROJECT_ROOT"
    return 1
  fi
  
  # Build with multiple cores for speed
  echo "Building liblsl (this may take a few minutes)..."
  if ! cmake --build . -j$(nproc); then
    echo -e "${RED}Failed to build liblsl.${NC}"
    cd "$PROJECT_ROOT"
    return 1
  fi
  
  # Install
  echo "Installing liblsl to system..."
  if ! make install; then
    echo -e "${RED}Failed to install liblsl.${NC}"
    cd "$PROJECT_ROOT"
    return 1
  fi
  
  # Update shared library cache
  echo "Updating shared library cache..."
  ldconfig
  
  # Return to original directory and cleanup
  cd "$PROJECT_ROOT"
  rm -rf "$BUILD_DIR"
  
  echo -e "${GREEN}✓ liblsl built and installed successfully.${NC}"
  return 0
}

# Build and install liblsl
echo -e "${YELLOW}Checking for liblsl library...${NC}"
if ldconfig -p | grep -q "liblsl\.so"; then
  echo -e "${GREEN}liblsl already installed in system libraries${NC}"
  INSTALLED_VER=$(ldconfig -p | grep liblsl | head -1)
  echo "Installed: $INSTALLED_VER"
  
  read -p "Do you want to reinstall liblsl anyway? (y/n): " reinstall_liblsl
  if [[ "$reinstall_liblsl" == "y" || "$reinstall_liblsl" == "Y" ]]; then
    build_liblsl_from_source
  else
    echo "Using existing liblsl installation."
  fi
elif [ -f "/usr/local/lib/liblsl.so" ]; then
  echo -e "${GREEN}liblsl already installed in /usr/local/lib${NC}"
  
  read -p "Do you want to reinstall liblsl anyway? (y/n): " reinstall_liblsl
  if [[ "$reinstall_liblsl" == "y" || "$reinstall_liblsl" == "Y" ]]; then
    build_liblsl_from_source
  else
    echo "Using existing liblsl installation."
  fi
else
  echo -e "${YELLOW}liblsl not found. Building from source...${NC}"
  build_liblsl_from_source
fi

# Setup Python virtual environment
echo -e "${YELLOW}----- Setting up Python Environment -----${NC}"
cd "$PROJECT_ROOT"

# Get username of the user who ran sudo
SUDO_USER_HOME=$(getent passwd "$SUDO_USER" | cut -d: -f6)

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
  echo "Creating Python virtual environment..."
  python3 -m venv --system-site-packages .venv
else
  echo "Using existing Python virtual environment."
fi

# Make sure the venv is owned by the correct user
if [ -n "$SUDO_USER" ]; then
  echo "Setting correct ownership for virtual environment..."
  chown -R "$SUDO_USER:$(id -g $SUDO_USER)" .venv
fi

# Function to run pip in the virtual environment as the sudo user
pip_install_as_user() {
  sudo -u "$SUDO_USER" .venv/bin/pip "$@"
}

# Install Python dependencies
echo "Installing Python dependencies..."
pip_install_as_user install --upgrade pip setuptools wheel

# Install pylsl with appropriate version
echo "Installing pylsl (compatible with older liblsl)..."
# Try several older versions of pylsl that are actually available in PyPI
# If these fail, fall back to the latest version
if ! pip_install_as_user install pylsl==1.12.2; then
  echo -e "${YELLOW}Failed to install pylsl 1.12.2, trying version 1.15.0...${NC}"
  if ! pip_install_as_user install pylsl==1.15.0; then
    echo -e "${YELLOW}Failed to install pylsl 1.15.0, trying version 1.16.1...${NC}"
    if ! pip_install_as_user install pylsl==1.16.1; then
      echo -e "${YELLOW}Failed to install specific pylsl versions, trying latest version...${NC}"
      if ! pip_install_as_user install pylsl; then
        echo -e "${RED}ERROR: Failed to install pylsl. LSL functionality will not work.${NC}"
      else
        echo -e "${GREEN}Installed latest pylsl version.${NC}"
        echo -e "${YELLOW}Note: Using the latest pylsl with an older liblsl may cause compatibility issues.${NC}"
      fi
    else
      echo -e "${GREEN}Successfully installed pylsl 1.16.1${NC}"
    fi
  else
    echo -e "${GREEN}Successfully installed pylsl 1.15.0${NC}"
  fi
else
  echo -e "${GREEN}Successfully installed pylsl 1.12.2${NC}"
fi

# Install additional Python dependencies from requirements
echo "Installing additional Python packages..."
pip_install_as_user install numpy scipy matplotlib
pip_install_as_user install pyyaml requests psutil
pip_install_as_user install pyserial pyzmq
pip_install_as_user install pytest pytest-cov mypy black flake8

# Ensure directories exist with proper permissions
echo -e "${YELLOW}----- Creating Required Directories -----${NC}"
mkdir -p "$PROJECT_ROOT/logs"
mkdir -p "$PROJECT_ROOT/recordings"
mkdir -p "$PROJECT_ROOT/config"

# Set permissions
chmod -R 777 "$PROJECT_ROOT/logs"
chmod -R 777 "$PROJECT_ROOT/recordings"

# Make scripts executable
echo -e "${YELLOW}----- Setting Script Permissions -----${NC}"
find "$PROJECT_ROOT/bin" -name "*.py" -exec chmod +x {} \;
find "$PROJECT_ROOT/bin" -name "*.sh" -exec chmod +x {} \;

# Copy config file example if needed
if [ ! -f "$PROJECT_ROOT/config/config.yaml" ] && [ -f "$PROJECT_ROOT/config/config.yaml.example" ]; then
  echo "Creating config.yaml from example..."
  cp "$PROJECT_ROOT/config/config.yaml.example" "$PROJECT_ROOT/config/config.yaml"
  
  # Detect the actual media device for the IMX296 camera
  echo "Detecting IMX296 camera media device..."
  MEDIA_DEVICE=""
  for i in {0..9}; do
    if [ -e "/dev/media$i" ]; then
      if media-ctl -d "/dev/media$i" -p 2>/dev/null | grep -q -i "imx296"; then
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
  
  # Create a unique ntfy topic
  NTFY_TOPIC="raspie-camera-$(hostname)-$(date +%s | head -c 6)"
  sed -i "s|topic: \"raspie-camera\"|topic: \"$NTFY_TOPIC\"|" "$PROJECT_ROOT/config/config.yaml"
  echo "Set ntfy.sh topic to: $NTFY_TOPIC"
fi

# Install systemd service if it doesn't exist
echo -e "${YELLOW}----- Installing Systemd Service -----${NC}"
if [ ! -f "/etc/systemd/system/imx296-camera.service" ]; then
  echo "Installing systemd service..."
  
  # Create the service file
  cat > /etc/systemd/system/imx296-camera.service << EOF
[Unit]
Description=IMX296 Global Shutter Camera Service
After=network.target

[Service]
Type=simple
User=$SUDO_USER
Group=$(id -gn $SUDO_USER)
WorkingDirectory=$PROJECT_ROOT
ExecStart=$PROJECT_ROOT/bin/restart_camera.sh
Restart=on-failure
RestartSec=10s

[Install]
WantedBy=multi-user.target
EOF
  
  systemctl daemon-reload
  
  # Ask user if they want to enable the service
  read -p "Do you want to enable the service to start on boot? (y/n): " enable_service
  if [[ "$enable_service" == "y" || "$enable_service" == "Y" ]]; then
    systemctl enable imx296-camera.service
    echo -e "${GREEN}Service enabled. It will start automatically on boot.${NC}"
  else
    echo "Service installed but not enabled. Start manually with: sudo systemctl start imx296-camera.service"
  fi
fi

# Create desktop shortcut if running in desktop environment
if [ -d "/home/$SUDO_USER/Desktop" ]; then
  echo -e "${YELLOW}----- Creating Desktop Shortcut -----${NC}"
  DESKTOP_FILE="/home/$SUDO_USER/Desktop/Camera-Dashboard.desktop"
  
  cat > "$DESKTOP_FILE" << EOF
[Desktop Entry]
Name=IMX296 Camera Dashboard
Comment=IMX296 Camera Status Dashboard
Exec=x-terminal-emulator -e $PROJECT_ROOT/bin/view-camera-status.sh
Icon=camera
Terminal=false
Type=Application
Categories=Utility;
EOF
  
  chmod +x "$DESKTOP_FILE"
  chown "$SUDO_USER:$(id -g $SUDO_USER)" "$DESKTOP_FILE"
  echo -e "${GREEN}Desktop shortcut created at $DESKTOP_FILE${NC}"
fi

# Test the camera
echo -e "${YELLOW}----- Testing Camera Hardware -----${NC}"
if command -v libcamera-hello >/dev/null; then
  echo "Checking for cameras with libcamera-hello..."
  if libcamera-hello --list-cameras | grep -i "imx296"; then
    echo -e "${GREEN}✓ IMX296 camera found!${NC}"
  else
    echo -e "${YELLOW}⚠ No IMX296 camera detected. Please check the hardware connection.${NC}"
    echo "This is normal if you're running on a development machine without the camera."
  fi
else
  echo -e "${YELLOW}libcamera-hello not found. Cannot check camera hardware.${NC}"
fi

# Test liblsl installation
echo -e "${YELLOW}----- Testing LSL Installation -----${NC}"
if ldconfig -p | grep -q "liblsl\.so" || [ -f "/usr/local/lib/liblsl.so" ]; then
  echo -e "${GREEN}✓ liblsl library found${NC}"
else
  echo -e "${RED}⚠ liblsl library not found. LSL functionality may not work.${NC}"
fi

# Test pylsl installation
echo -e "${YELLOW}----- Testing pylsl Installation -----${NC}"
# Create temporary script with proper permissions
TEST_SCRIPT="/tmp/pylsl_test_$$.py"
cat > "$TEST_SCRIPT" << 'EOF'
#!/usr/bin/env python3
try:
    import pylsl
    import sys
    print(f"pylsl version: {pylsl.__version__}")
    # Test creating a stream to verify functionality
    info = pylsl.StreamInfo("TestStream", "Markers", 1, 100, pylsl.cf_float32, "test_uid")
    outlet = pylsl.StreamOutlet(info)
    outlet.push_sample([1.0])
    print("LSL test successful: created stream and pushed sample")
    sys.exit(0)
except Exception as e:
    import sys
    print(f"Error testing pylsl: {str(e)}")
    sys.exit(1)
EOF

if [ -d "$PROJECT_ROOT/.venv" ]; then
  # Ensure test script has correct permissions and ownership
  chmod 755 "$TEST_SCRIPT"
  if [ -n "$SUDO_USER" ]; then
    chown "$SUDO_USER:$(id -g $SUDO_USER)" "$TEST_SCRIPT"
  fi
  
  echo "Testing pylsl functionality..."
  if sudo -u "$SUDO_USER" "$PROJECT_ROOT/.venv/bin/python" "$TEST_SCRIPT"; then
    echo -e "${GREEN}✓ pylsl package installed and working correctly${NC}"
  else
    echo -e "${RED}⚠ pylsl package test failed. LSL functionality will not work.${NC}"
    echo "Try reinstalling with:"
    echo "  cd $PROJECT_ROOT && .venv/bin/pip install pylsl==1.12.2"
  fi
fi

# Clean up
rm -f "$TEST_SCRIPT"

echo ""
echo -e "${GREEN}Installation complete!${NC}"
echo ""
echo -e "${YELLOW}To start the camera service:${NC}"
echo "  sudo systemctl start imx296-camera.service"
echo ""
echo -e "${YELLOW}To view the camera dashboard:${NC}"
echo "  $PROJECT_ROOT/bin/view-camera-status.sh"
echo ""
echo -e "${YELLOW}If you encounter any issues, run the diagnostic tool:${NC}"
echo "  sudo $PROJECT_ROOT/bin/diagnose_camera.sh"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "1. Edit config/config.yaml to customize camera settings"
echo "2. Start the service with: sudo systemctl start imx296-camera.service"
echo "3. Check status with: $PROJECT_ROOT/bin/view-camera-status.sh" 