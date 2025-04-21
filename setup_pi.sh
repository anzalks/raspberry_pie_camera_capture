#!/bin/bash

# Setup script for Raspberry Pi LSL Camera Streamer System Dependencies
# 
# IMPORTANT:
# 1. Run this script with sudo:   sudo bash setup_pi.sh
# 2. Review the script before running.
# 3. A reboot might be required after running this script for camera changes.
# 4. This script installs SYSTEM packages. Python package installation
#    should be done AFTER this script, inside a virtual environment.

# --- Error Handling --- 
set -e # Exit immediately if a command exits with a non-zero status.

# --- Check if running as root --- 
if [ "$(id -u)" -ne 0 ]; then
  echo "This script must be run as root (use sudo). Exiting." >&2
  exit 1
fi

echo "Updating package list..."
apt update

echo "Installing essential tools (python3-pip, python3-venv, git)..."
# Ensure git is installed early as it might be needed for liblsl build
apt install -y python3-pip python3-venv git

echo "Attempting to install liblsl-dev (LabStreamingLayer library) via apt..."
if apt install -y liblsl-dev; then
  echo "liblsl-dev installed successfully via apt."
else
  echo "apt install liblsl-dev failed. Attempting to build from source..."
  # Install build dependencies for liblsl
  echo "Installing build dependencies for liblsl (cmake, build-essential)..."
  apt install -y cmake build-essential
  
  echo "Cloning liblsl repository..."
  # Store current directory and go to home for cloning
  ORIG_DIR=$(pwd)
  cd ~
  # Remove existing directory if present
  if [ -d "liblsl" ]; then 
      echo "Removing existing liblsl directory..."
      rm -rf liblsl 
  fi
  git clone https://github.com/sccn/liblsl.git
  cd liblsl

  echo "Configuring liblsl build with CMake..."
  mkdir -p build # Ensure build directory exists
  cd build
  cmake ..

  echo "Compiling liblsl (this may take a while)..."
  make

  echo "Installing compiled liblsl..."
  make install

  echo "Updating shared library cache..."
  ldconfig

  echo "liblsl successfully built and installed from source."
  # Return to original directory
  cd "$ORIG_DIR"
fi

# --- Install other dependencies ---

echo "Installing libcap-dev (needed for python-prctl, a picamera2 dependency)..."
apt install -y libcap-dev

echo "Installing libcamera-apps (useful for testing and ensuring libcamera stack is present)..."
apt install -y libcamera-apps

# --- Install python3-picamera2 using APT (Recommended Method) --- 
echo "Installing python3-picamera2 (Recommended method via apt)..."
apt install -y python3-picamera2

# --- Camera Enablement Reminder --- 
# Enabling the camera interface via script is complex and depends on OS version.
# It's often SAFER to do this manually via 'sudo raspi-config' -> Interface Options -> Camera.
# Ensure the LEGACY camera interface is DISABLED if using picamera2/libcamera.


echo "-----------------------------------------------------" 
echo "System dependency installation process finished."
echo ""
echo "Next Steps:"
echo "1. Ensure the camera is ENABLED using 'sudo raspi-config'" 
echo "   (Interface Options -> Camera -> Enable, and ensure Legacy Camera is DISABLED)."
echo "2. REBOOT the Raspberry Pi if you changed camera settings: sudo reboot"
echo "3. Create and activate a Python virtual environment:"
echo "   python3 -m venv --system-site-packages ~/.virtualenvs/dognosis  # Or your preferred location"
echo "   source ~/.virtualenvs/dognosis/bin/activate"
echo "4. Navigate to the project directory:"
echo "   cd /path/to/your/raspberry_pie_camera_capture" 
echo "5. Install Python packages within the activated environment:"
echo "   pip install --upgrade pip"
echo "   pip install -e ." 
echo "   (Note: picamera2 should already be available from the system install)"
echo "-----------------------------------------------------"

exit 0 