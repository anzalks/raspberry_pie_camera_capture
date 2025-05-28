#!/bin/bash
# Installation Script for IMX296 Camera Recorder with LSL
# Enhanced with robust LSL library installation

echo "==== IMX296 Camera Recorder with LSL - Installation ===="
echo "This script will install all necessary dependencies and build liblsl from source."
echo "Author: Anzal KS (anzal.ks@gmail.com)"

# Check if running as root
if [ "$EUID" -ne 0 ]; then
  echo "Please run as root (sudo $0)"
  exit 1
fi

# Get the actual user (not root when using sudo)
ACTUAL_USER="${SUDO_USER:-$(logname 2>/dev/null || echo $USER)}"
ACTUAL_HOME="/home/$ACTUAL_USER"

# Get project directory (where this script is located - keep everything in repo)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR"  # Keep everything in the same directory as the script

echo "Project directory: $PROJECT_DIR"
echo "Installing for user: $ACTUAL_USER"

# Detect Raspberry Pi OS version for camera package selection
OS_VERSION=""
if [ -f /etc/os-release ]; then
    OS_VERSION=$(grep VERSION_CODENAME /etc/os-release | cut -d= -f2)
fi

echo "Detected OS version: $OS_VERSION"

# Install system dependencies with enhanced error checking
echo ""
echo "==== Installing System Dependencies ===="
apt-get update || { echo "Failed to update package list"; exit 1; }

# Core dependencies for building LSL and camera tools
CORE_PACKAGES="python3 python3-pip python3-venv python3-dev git cmake g++ build-essential"
BOOST_PACKAGES="libboost-all-dev libboost-system-dev libboost-filesystem-dev libboost-thread-dev"
CAMERA_PACKAGES="v4l-utils media-ctl"

echo "Installing core packages..."
apt-get install -y $CORE_PACKAGES $BOOST_PACKAGES || { echo "Failed to install core packages"; exit 1; }

# Camera packages - install both for compatibility
echo "Installing camera packages..."

# For newer Pi OS (Bookworm+), use rpicam-apps
if [ "$OS_VERSION" = "bookworm" ] || [ "$OS_VERSION" = "bullseye" ]; then
    echo "Installing rpicam-apps for modern Raspberry Pi OS..."
    CAMERA_PACKAGES="$CAMERA_PACKAGES rpicam-apps"
fi

# Also try libcamera-apps for compatibility
echo "Installing libcamera-apps for compatibility..."
CAMERA_PACKAGES="$CAMERA_PACKAGES libcamera-apps"

# Install camera packages with error handling
apt-get install -y $CAMERA_PACKAGES || { 
    echo "Warning: Some camera packages failed to install. Continuing anyway..."
}

# Verify camera tools are available
echo ""
echo "==== Verifying Camera Tools ===="
CAMERA_CMD=""
if command -v rpicam-vid >/dev/null 2>&1; then
    echo "✅ rpicam-vid found"
    CAMERA_CMD="rpicam-vid"
elif command -v libcamera-vid >/dev/null 2>&1; then
    echo "✅ libcamera-vid found (legacy)"
    CAMERA_CMD="libcamera-vid"
else
    echo "❌ No camera video command found! Will attempt manual installation..."
fi

if command -v media-ctl >/dev/null 2>&1; then
    echo "✅ media-ctl found"
else
    echo "❌ media-ctl not found! Installing v4l-utils..."
    apt-get install -y v4l-utils
fi

# Create build directory in project
echo ""
echo "==== Building LSL Library ===="
cd "$PROJECT_DIR" || exit 1
mkdir -p build_temp  # Use temporary build directory within repo
cd build_temp || exit 1

# Clone and build liblsl from source with robust error handling
echo "Cloning liblsl from GitHub..."
if [ ! -d "liblsl" ]; then
    git clone https://github.com/sccn/liblsl.git || { echo "Failed to clone liblsl"; exit 1; }
fi

cd liblsl || exit 1

# Get latest stable version
echo "Checking out latest stable release..."
git fetch --tags
LATEST_TAG=$(git describe --tags `git rev-list --tags --max-count=1` 2>/dev/null || echo "v1.16.2")
echo "Using LSL version: $LATEST_TAG"
git checkout $LATEST_TAG 2>/dev/null || echo "Using current branch"

mkdir -p build
cd build || exit 1

# Configure liblsl with proper settings for Raspberry Pi
echo "Configuring liblsl build..."
cmake -DCMAKE_BUILD_TYPE=Release \
      -DLSL_BUNDLED_BOOST=ON \
      -DLSL_BUILD_STATIC=OFF \
      -DCMAKE_INSTALL_PREFIX=/usr/local \
      -DCMAKE_POSITION_INDEPENDENT_CODE=ON \
      .. || { echo "CMake configuration failed"; exit 1; }

# Build liblsl (use appropriate number of cores)
NPROC=$(nproc)
echo "Building liblsl using $NPROC cores..."
make -j$NPROC || { echo "Build failed"; exit 1; }

# Install liblsl system-wide
echo "Installing liblsl to system..."
make install || { echo "Installation failed"; exit 1; }

# Update library cache
ldconfig

# Verify installation
if [ -f "/usr/local/lib/liblsl.so" ] || [ -f "/usr/local/lib64/liblsl.so" ]; then
    echo "✅ liblsl installed successfully"
    LSL_LIB_PATH=$(find /usr/local -name "liblsl.so*" 2>/dev/null | head -1)
    echo "LSL library location: $LSL_LIB_PATH"
else
    echo "❌ liblsl installation verification failed"
    exit 1
fi

# Return to project directory
cd "$PROJECT_DIR" || exit 1

# Create Python virtual environment as actual user
echo ""
echo "==== Setting Up Python Environment ===="
echo "Creating virtual environment as user $ACTUAL_USER..."

# Remove old venv if it exists
if [ -d "venv" ]; then
    echo "Removing existing virtual environment..."
    rm -rf venv
fi

# Create venv as the actual user
sudo -u "$ACTUAL_USER" python3 -m venv venv || { echo "Failed to create virtual environment"; exit 1; }

# Activate virtual environment and install Python dependencies
echo "Installing Python dependencies..."

# Create a temporary script to run in the virtual environment
cat > "$PROJECT_DIR/temp_install.sh" << 'EOF'
#!/bin/bash
source venv/bin/activate

# Set environment variable to help pylsl find the library
export PYLSL_LIB="/usr/local/lib/liblsl.so:/usr/local/lib64/liblsl.so"

# Upgrade pip first
pip install --upgrade pip

# Install pylsl with specific version that works well on ARM
echo "Installing pylsl..."
pip install pylsl==1.16.1 || pip install pylsl

# Test pylsl installation
echo "Testing pylsl installation..."
python -c "
try:
    import pylsl
    print('✅ pylsl imported successfully')
    info = pylsl.StreamInfo('test', 'test', 1, 100, 'float32', 'test')
    print('✅ pylsl StreamInfo creation successful')
    print(f'LSL library version: {pylsl.library_version()}')
except Exception as e:
    print(f'❌ pylsl test failed: {e}')
    exit(1)
"

# Install other dependencies
echo "Installing additional Python packages..."
pip install pyxdf numpy scipy matplotlib

echo "Python package installation complete"
EOF

# Make the script executable and run it as the actual user
chmod +x "$PROJECT_DIR/temp_install.sh"
cd "$PROJECT_DIR" || exit 1
sudo -u "$ACTUAL_USER" ./temp_install.sh || { 
    echo "Python package installation failed"
    rm -f "$PROJECT_DIR/temp_install.sh"
    exit 1
}

# Clean up
rm -f "$PROJECT_DIR/temp_install.sh"

# Set proper ownership for the entire project
echo "Setting proper file ownership..."
chown -R "$ACTUAL_USER:$ACTUAL_USER" "$PROJECT_DIR"

# Make scripts executable
echo "Making scripts executable..."
chmod +x simple_camera_lsl.py GScrop

# Clean up temporary build directory
echo "Cleaning up temporary build files..."
if [ -d "$PROJECT_DIR/build_temp" ]; then
    rm -rf "$PROJECT_DIR/build_temp"
    echo "Removed temporary build directory"
fi

# Create LSL environment setup script within the repo
echo "Creating LSL environment setup..."
cat > "$PROJECT_DIR/setup_lsl_env.sh" << 'EOF'
#!/bin/bash
# LSL Environment Setup
# Add this to your ~/.bashrc or run before using LSL

# Help pylsl find the liblsl library
export PYLSL_LIB="/usr/local/lib/liblsl.so:/usr/local/lib64/liblsl.so"

# Add to LD_LIBRARY_PATH
export LD_LIBRARY_PATH="/usr/local/lib:/usr/local/lib64:$LD_LIBRARY_PATH"

echo "LSL environment variables set"
EOF

chmod +x "$PROJECT_DIR/setup_lsl_env.sh"
chown "$ACTUAL_USER:$ACTUAL_USER" "$PROJECT_DIR/setup_lsl_env.sh"

# Test camera detection
echo ""
echo "==== Testing Camera Detection ===="
if [ -n "$CAMERA_CMD" ]; then
    echo "Testing camera detection with: $CAMERA_CMD --list-cameras"
    sudo -u "$ACTUAL_USER" $CAMERA_CMD --list-cameras 2>/dev/null || echo "No cameras detected (normal if camera not connected)"
else
    echo "⚠️  No camera command available for testing"
fi

# Check for IMX296 devices
echo "Checking for IMX296 devices..."
if ls /dev/media* >/dev/null 2>&1; then
    for media_dev in /dev/media*; do
        echo "Checking $media_dev..."
        if media-ctl -d "$media_dev" -p 2>/dev/null | grep -q "imx296"; then
            echo "✅ Found IMX296 on $media_dev"
        fi
    done
else
    echo "No media devices found (/dev/media*)"
fi

echo ""
echo "===== INSTALLATION COMPLETE ====="
echo ""
echo "📋 **NEXT STEPS:**"
echo "1. Set up LSL environment:"
echo "   source ./setup_lsl_env.sh"
echo ""
echo "2. Activate virtual environment:"
echo "   source venv/bin/activate"
echo ""
echo "3. Test basic camera recording:"
echo "   ./GScrop 400 400 100 5000"
echo ""
echo "4. Test with LSL streaming:"
echo "   python simple_camera_lsl.py --width 400 --height 400 --fps 100 --duration 10"
echo ""
echo "🎥 **Usage Examples:**"
echo "  # Basic recording:"
echo "  ./GScrop 400 400 100 5000"
echo ""
echo "  # LSL streaming with preview:"
echo "  python simple_camera_lsl.py --width 400 --height 400 --fps 100 --preview"
echo ""
echo "  # High-speed capture:"
echo "  python simple_camera_lsl.py --width 320 --height 240 --fps 200"
echo ""
echo "🔧 **Installed Components:**"
if command -v rpicam-vid >/dev/null 2>&1; then
    echo "  ✅ rpicam-vid (modern)"
fi
if command -v libcamera-vid >/dev/null 2>&1; then
    echo "  ✅ libcamera-vid (legacy)"
fi
if command -v media-ctl >/dev/null 2>&1; then
    echo "  ✅ media-ctl (device control)"
fi
echo "  ✅ liblsl (Lab Streaming Layer)"
echo "  ✅ pylsl (Python LSL bindings)"
echo ""
echo "⚠️  **Important:** Run 'source ./setup_lsl_env.sh' before using LSL features"
echo ""
echo "📝 For troubleshooting, check the install log and ensure camera is connected."
echo "" 