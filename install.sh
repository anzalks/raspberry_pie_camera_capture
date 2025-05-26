#!/bin/bash
# Installer for IMX296 Camera Capture System
# By: Anzal KS <anzal.ks@gmail.com>
set -e

echo "===== IMX296 Camera Capture Installer ====="

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Check if running as root
if [ "$EUID" -ne 0 ]; then
  echo "Please run with sudo for complete installation"
  exit 1
fi

# Create config directory
mkdir -p config

# Install dependencies
echo "Installing dependencies..."
apt-get update
apt-get install -y v4l-utils ffmpeg python3-pip python3-opencv libcamera-apps python3-venv

# Install Python dependencies
echo "Installing Python packages..."
pip3 install pylsl numpy opencv-python flask

# Check for camera
echo "Checking for camera devices..."
v4l2-ctl --list-devices || echo "No camera devices found"

# Set up directories for recordings
RECORDING_DIR="/tmp/recordings"
mkdir -p "$RECORDING_DIR"
chmod 777 "$RECORDING_DIR"

# Update camera stream module
echo "Updating camera stream module..."
bash scripts/update_camera_stream.sh

# Create dashboard
echo "Creating camera dashboard..."
bash desktop/create_dashboard.sh

# Configure the systemd service
if prompt_yes_no "Do you want to configure the IMX296 camera as a systemd service?"; then
    echo "Configuring systemd service..."
    bash setup/configure_imx296_service.sh
fi

# Install services
echo "Installing systemd services..."
cp config/imx296_camera.service /etc/systemd/system/
cp config/imx296_dashboard.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable imx296_camera.service
systemctl enable imx296_dashboard.service

echo ""
echo "Installation complete!"
echo ""
echo "===== Usage Instructions ====="
echo "1. Test the camera directly:"
echo "   sudo bin/imx296_direct_test.sh"
echo ""
echo "2. Start the camera and dashboard services:"
echo "   sudo systemctl start imx296_camera.service"
echo "   sudo systemctl start imx296_dashboard.service"
echo ""
echo "3. Check service status:"
echo "   sudo systemctl status imx296_camera.service"
echo "   sudo systemctl status imx296_dashboard.service"
echo ""
echo "4. View service logs:"
echo "   sudo journalctl -u imx296_camera.service -f"
echo ""
echo "5. Access the dashboard at:"
echo "   http://$(hostname -I | awk '{print $1}'):8080"
echo ""
echo "NOTE: This camera requires proper configuration of the ROI (Region of Interest)"
echo "      using media-ctl before streaming. This is now done automatically by the"
echo "      service and test scripts."
echo ""
echo "Configured for IMX296 camera at native 400x400 resolution with SBGGR10_1X10 format." 