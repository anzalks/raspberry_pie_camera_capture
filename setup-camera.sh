#!/bin/bash
# All-in-one setup script for Raspberry Pi Camera Capture System
# Author: Anzal (anzal.ks@gmail.com)

# Print header
echo "============================================="
echo "Raspberry Pi Camera System - Setup Script"
echo "============================================="

# Check if running as root for system package installation
if [ "$(id -u)" -ne 0 ]; then
  echo "This script must be run with sudo for system package installation."
  echo "Please run: sudo bash setup-camera.sh"
  exit 1
fi

echo "Step 1: Installing system dependencies..."
apt update
apt install -y v4l-utils libcamera-apps python3-yaml curl python3-pip

echo "Checking libcamera installation..."
if [ ! -f "/usr/lib/libcamera.so" ] && [ ! -f "/usr/lib/arm-linux-gnueabihf/libcamera.so" ]; then
  echo "Installing additional libcamera dependencies..."
  apt install -y libcamera0 libcamera-dev libcamera-apps-lite
fi

echo "Step 2: Setting up Python environment..."
# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
  echo "Creating Python virtual environment..."
  python3 -m venv .venv
fi

# Activate virtual environment and install packages
echo "Installing Python dependencies..."
source .venv/bin/activate
pip install --upgrade pip
pip install pyyaml pylsl opencv-python numpy requests psutil sounddevice

# Check if we need to install picamera2 via pip
if ! python -c "import picamera2" &>/dev/null; then
  echo "Installing picamera2 via pip (fallback)..."
  pip install picamera2
fi

echo "Step 3: Setting up permissions..."
# Add user to video group
username=$(logname || whoami)
usermod -a -G video $username
echo "Added user $username to video group"

echo "Step 4: Creating configuration file..."
# Create config.yaml if it doesn't exist
if [ ! -f "config.yaml" ]; then
  echo "Creating default config.yaml..."
  cat > config.yaml << EOF
# Raspberry Pi Camera Capture Configuration

# Camera settings
camera:
  width: 400
  height: 400
  fps: 100
  codec: mjpg
  container: mkv
  preview: false
  enable_crop: auto  # Can be true, false, or auto (detect Global Shutter Camera)

# Storage settings
storage:
  save_video: true
  output_dir: recordings
  create_date_folders: true

# Buffer settings
buffer:
  size: 20.0  # seconds
  enabled: true

# Remote control
remote:
  ntfy_topic: raspie-camera-test
  
# LSL settings
lsl:
  stream_name: VideoStream

# Performance settings
performance:
  capture_cpu_core: null  # null means no specific core assignment
  writer_cpu_core: null
  lsl_cpu_core: null
  ntfy_cpu_core: null

# Terminal UI settings
terminal:
  colors_enabled: true
  use_unicode: false  # Set to false for better compatibility
  update_frequency: 0.5
EOF
  echo "Created default config.yaml"
fi

echo "Step 5: Creating storage directories..."
# Create recordings directory
mkdir -p recordings
chown $username:$username recordings

echo "Step 6: Making scripts executable..."
chmod +x run-camera.sh

echo "Step 7: Running environment check..."
# Run environment check script
source .venv/bin/activate
python check-camera-env.py

echo "============================================="
echo "Setup complete!"
echo "============================================="
echo "To run the camera capture system:"
echo "1. Log out and back in for group changes to take effect"
echo "2. Run: ./run-camera.sh"
echo ""
echo "For more options and documentation, see README.md"
echo "=============================================" 