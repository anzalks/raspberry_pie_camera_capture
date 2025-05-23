#!/bin/bash
# Installation Script for IMX296 Camera Recorder with LSL

echo "==== IMX296 Camera Recorder with LSL - Installation ===="
echo "This script will install all necessary dependencies and build liblsl from source."

# Check if running as root
if [ "$EUID" -ne 0 ]; then
  echo "Please run as root (sudo $0)"
  exit 1
fi

# Install system dependencies
echo "Installing system dependencies..."
apt-get update
apt-get install -y python3 python3-pip python3-venv python3-dev libcamera-apps v4l-utils \
                   git cmake g++ build-essential

# Create directories
echo "Creating build directories..."
mkdir -p build
cd build || exit 1

# Clone and build liblsl from source
echo "Cloning and building liblsl from source..."
if [ ! -d "liblsl" ]; then
  git clone https://github.com/sccn/liblsl.git
fi

cd liblsl || exit 1
mkdir -p build
cd build || exit 1

# Configure and build liblsl
cmake -DCMAKE_BUILD_TYPE=Release -DLSL_BUNDLED_BOOST=ON -DLSL_PYTHON=ON ..
make -j4

# Install liblsl system-wide
make install
ldconfig

cd ../../.. || exit 1

# Create Python virtual environment
echo "Creating Python virtual environment..."
python3 -m venv venv

# Activate virtual environment and install Python dependencies
echo "Activating virtual environment and installing Python dependencies..."
source venv/bin/activate

# Install pylsl using the locally built liblsl
pip install pylsl

# Install other LSL utilities via pip
echo "Installing additional LSL utilities..."
pip install pyxdf # LSL data format handling
pip install scipy numpy # For data analysis

# Make script executable
echo "Making script executable..."
chmod +x simple_camera_lsl.py

echo "Installation complete!"
echo ""
echo "To use the camera recorder:"
echo "1. Activate the virtual environment: source venv/bin/activate"
echo "2. Run the script: ./simple_camera_lsl.py"
echo ""
echo "Usage examples:"
echo "  # Basic recording at 400x400 @ 100fps:"
echo "  ./simple_camera_lsl.py"
echo ""
echo "  # Custom resolution and framerate:"
echo "  ./simple_camera_lsl.py --width 320 --height 320 --fps 120"
echo ""
echo "  # Specific output file and exposure:"
echo "  ./simple_camera_lsl.py --output video.h264 --exposure 8000"
echo ""
echo "  # Set recording duration (in milliseconds):"
echo "  ./simple_camera_lsl.py --duration 10000"
echo ""
echo "  # Use second camera (if available):"
echo "  ./simple_camera_lsl.py --cam1"
echo "" 