#!/bin/bash
# Installation Script for IMX296 Camera Recorder with LSL

echo "==== IMX296 Camera Recorder with LSL - Installation ===="
echo "This script will install all necessary dependencies and build liblsl from source."

# Check if running as root
if [ "$EUID" -ne 0 ]; then
  echo "Please run as root (sudo $0)"
  exit 1
fi

# Detect Raspberry Pi OS version for camera package selection
OS_VERSION=""
if [ -f /etc/os-release ]; then
    OS_VERSION=$(grep VERSION_CODENAME /etc/os-release | cut -d= -f2)
fi

echo "Detected OS version: $OS_VERSION"

# Install system dependencies
echo "Installing system dependencies..."
apt-get update

# Camera packages - install both for compatibility
echo "Installing camera packages..."
CAMERA_PACKAGES="v4l-utils media-ctl"

# For newer Pi OS (Bookworm+), use rpicam-apps
if [ "$OS_VERSION" = "bookworm" ] || [ "$OS_VERSION" = "bullseye" ]; then
    echo "Installing rpicam-apps for modern Raspberry Pi OS..."
    CAMERA_PACKAGES="$CAMERA_PACKAGES rpicam-apps"
fi

# Also try libcamera-apps for compatibility
echo "Installing libcamera-apps for compatibility..."
CAMERA_PACKAGES="$CAMERA_PACKAGES libcamera-apps"

# Install all packages
apt-get install -y python3 python3-pip python3-venv python3-dev \
                   git cmake g++ build-essential \
                   $CAMERA_PACKAGES

# Verify camera tools are available
echo "Verifying camera tools installation..."
CAMERA_CMD=""
if command -v rpicam-vid >/dev/null 2>&1; then
    echo "✅ rpicam-vid found"
    CAMERA_CMD="rpicam-vid"
elif command -v libcamera-vid >/dev/null 2>&1; then
    echo "✅ libcamera-vid found (legacy)"
    CAMERA_CMD="libcamera-vid"
else
    echo "❌ No camera video command found! Manual installation may be required."
    echo "Try: sudo apt install rpicam-apps or sudo apt install libcamera-apps"
fi

if command -v media-ctl >/dev/null 2>&1; then
    echo "✅ media-ctl found"
else
    echo "❌ media-ctl not found! Installing v4l-utils..."
    apt-get install -y v4l-utils
fi

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
echo "Building liblsl..."
cmake -DCMAKE_BUILD_TYPE=Release -DLSL_BUNDLED_BOOST=ON -DLSL_PYTHON=ON ..
make -j4

# Install liblsl system-wide
echo "Installing liblsl system-wide..."
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
echo "Installing pylsl..."
pip install pylsl

# Install other LSL utilities via pip
echo "Installing additional LSL utilities..."
pip install pyxdf # LSL data format handling
pip install scipy numpy # For data analysis

# Make scripts executable
echo "Making scripts executable..."
chmod +x simple_camera_lsl.py
chmod +x GScrop

# Test camera tools
echo ""
echo "==== Testing Camera Tools ===="
if [ -n "$CAMERA_CMD" ]; then
    echo "Testing camera command: $CAMERA_CMD --list-cameras"
    $CAMERA_CMD --list-cameras 2>/dev/null || echo "Camera test failed (normal if no camera connected)"
else
    echo "⚠️  No camera command available for testing"
fi

echo ""
echo "Installation complete!"
echo ""
echo "📋 **NEXT STEPS:**"
echo "1. Activate the virtual environment: source venv/bin/activate"
echo "2. Test camera: ./GScrop 400 400 100 1000"
echo "3. Run with LSL: python simple_camera_lsl.py"
echo ""
echo "🎥 **Usage examples:**"
echo "  # Basic recording at 400x400 @ 100fps:"
echo "  ./GScrop 400 400 100 1000"
echo ""
echo "  # With LSL streaming:"
echo "  python simple_camera_lsl.py --width 400 --height 400 --fps 100"
echo ""
echo "  # Custom resolution and framerate:"
echo "  python simple_camera_lsl.py --width 320 --height 320 --fps 120"
echo ""
echo "  # High-speed recording:"
echo "  python simple_camera_lsl.py --width 320 --height 240 --fps 200"
echo ""
echo "🔧 **Camera Tools Installed:**"
if command -v rpicam-vid >/dev/null 2>&1; then
    echo "  ✅ rpicam-vid (modern)"
fi
if command -v libcamera-vid >/dev/null 2>&1; then
    echo "  ✅ libcamera-vid (legacy)"
fi
if command -v media-ctl >/dev/null 2>&1; then
    echo "  ✅ media-ctl (device control)"
fi
echo "" 