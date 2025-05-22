#!/bin/bash
# IMX296 Camera Diagnostic Script
# Author: Anzal KS <anzal.ks@gmail.com>
# Date: May 22, 2025

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "===== IMX296 Camera Diagnostic Tool ====="
echo "Project root: $PROJECT_ROOT"

# Check if Python venv exists
check_venv() {
  echo "Checking Python virtual environment..."
  if [ -d "$PROJECT_ROOT/.venv" ]; then
    echo "✓ Python virtual environment found."
  else
    echo "✗ Python virtual environment not found."
    echo "  Run the install.sh script to create it."
    return 1
  fi
  return 0
}

# Check required Python packages
check_python_packages() {
  echo "Checking Python packages..."
  if [ ! -d "$PROJECT_ROOT/.venv" ]; then
    echo "✗ Cannot check packages: venv not found"
    return 1
  fi
  
  local REQUIRED_PACKAGES="pylsl pyyaml requests psutil"
  local MISSING_PACKAGES=""
  
  for pkg in $REQUIRED_PACKAGES; do
    if ! "$PROJECT_ROOT/.venv/bin/pip" list | grep -q "$pkg"; then
      MISSING_PACKAGES="$MISSING_PACKAGES $pkg"
    fi
  done
  
  if [ -n "$MISSING_PACKAGES" ]; then
    echo "✗ Missing Python packages:$MISSING_PACKAGES"
    echo "  Run: $PROJECT_ROOT/.venv/bin/pip install$MISSING_PACKAGES"
    return 1
  else
    echo "✓ All required Python packages are installed."
  fi
  return 0
}

# Check liblsl installation
check_liblsl() {
  echo "Checking liblsl installation..."
  
  # Check if liblsl.so exists in system library paths
  if ldconfig -p | grep -q "liblsl.so"; then
    echo "✓ liblsl library is installed in system path."
    echo "  $(ldconfig -p | grep "liblsl.so" | head -1)"
    return 0
  elif [ -f "/usr/local/lib/liblsl.so" ]; then
    echo "✓ liblsl library found in /usr/local/lib/"
    return 0
  elif [ -f "/usr/lib/liblsl.so" ]; then
    echo "✓ liblsl library found in /usr/lib/"
    return 0
  else
    echo "✗ liblsl library not found in system paths."
    echo "  This is required for LSL functionality."
    echo "  Run: sudo bin/install.sh to build and install liblsl"
    return 1
  fi
}

# Test pylsl installation with specific guidance
check_lsl_compatibility() {
  echo "Checking LSL compatibility..."
  
  # Only check if both prerequisites are installed
  if ! ldconfig -p | grep -q "liblsl\.so" && [ ! -f "/usr/local/lib/liblsl.so" ] && [ ! -f "/usr/lib/liblsl.so" ]; then
    echo "✗ Cannot check LSL compatibility: liblsl not installed"
    return 1
  fi
  
  if [ ! -d "$PROJECT_ROOT/.venv" ]; then
    echo "✗ Cannot check LSL compatibility: venv not found"
    return 1
  fi
  
  if ! "$PROJECT_ROOT/.venv/bin/pip" list | grep -q "pylsl"; then
    echo "✗ Cannot check LSL compatibility: pylsl not installed"
    echo "  Try installing it with: $PROJECT_ROOT/.venv/bin/pip install pylsl==1.12.2"
    return 1
  fi
  
  # Check the installed pylsl version
  PYLSL_VERSION=$("$PROJECT_ROOT/.venv/bin/pip" show pylsl | grep "Version" | awk '{print $2}')
  echo "Detected pylsl version: $PYLSL_VERSION"
  
  # Create a simple test script
  local TEST_SCRIPT="/tmp/test_lsl_$$.py"
  cat > "$TEST_SCRIPT" << 'EOF'
#!/usr/bin/env python3
import sys

def test_pylsl():
    try:
        import pylsl
        print("pylsl successfully imported")
        
        # Create test stream
        info = pylsl.StreamInfo("TestStream", "Markers", 1, 100, pylsl.cf_float32, "test_uid")
        print("Created StreamInfo object")
        
        # Create outlet
        outlet = pylsl.StreamOutlet(info)
        print("Created StreamOutlet object")
        
        # Push sample
        outlet.push_sample([1.0])
        print("Successfully pushed sample through LSL")
        return True
    except ImportError:
        print("ERROR: Failed to import pylsl module")
        return False
    except Exception as e:
        print(f"ERROR: {str(e)}")
        return False

if test_pylsl():
    print("LSL TEST PASSED: All functionality works correctly")
    sys.exit(0)
else:
    print("LSL TEST FAILED: Could not complete LSL test")
    sys.exit(1)
EOF
  
  # Ensure test script has correct permissions
  chmod 755 "$TEST_SCRIPT"
  # If running as root, make sure the current user can access it
  if [ "$EUID" -eq 0 ] && [ -n "$SUDO_USER" ]; then
    chown "$SUDO_USER:$(id -g $SUDO_USER)" "$TEST_SCRIPT"
  fi
  
  # Run the test script
  echo "Running LSL compatibility test..."
  # Run as current user or sudo user if appropriate
  if [ "$EUID" -eq 0 ] && [ -n "$SUDO_USER" ]; then
    if sudo -u "$SUDO_USER" "$PROJECT_ROOT/.venv/bin/python" "$TEST_SCRIPT"; then
      echo "✓ LSL compatibility test passed."
      rm -f "$TEST_SCRIPT"
      return 0
    fi
  else
    if "$PROJECT_ROOT/.venv/bin/python" "$TEST_SCRIPT"; then
      echo "✓ LSL compatibility test passed."
      rm -f "$TEST_SCRIPT"
      return 0
    fi
  fi
  
  echo "✗ LSL compatibility test failed. Attempting auto-fix..."
  
  # Auto-fix: Try creating symlinks
  LIBLSL_PATH=""
  if [ -f "/usr/local/lib/liblsl.so" ]; then
    LIBLSL_PATH="/usr/local/lib/liblsl.so"
  elif ldconfig -p | grep -q "liblsl\.so"; then
    LIBLSL_PATH=$(ldconfig -p | grep "liblsl\.so" | head -1 | awk '{print $4}')
  fi
  
  if [ -n "$LIBLSL_PATH" ]; then
    echo "Found liblsl at: $LIBLSL_PATH"
    
    # Find Python packages directory
    PYTHON_VERSION=$(ls "$PROJECT_ROOT/.venv/lib/" | grep "python3" | head -1)
    if [ -n "$PYTHON_VERSION" ]; then
      SITE_PKG_DIR="$PROJECT_ROOT/.venv/lib/$PYTHON_VERSION/site-packages"
      PYLSL_DIR="$SITE_PKG_DIR/pylsl"
      
      if [ -d "$PYLSL_DIR" ]; then
        echo "Creating symlinks for liblsl in pylsl directory..."
        mkdir -p "$PYLSL_DIR/lib"
        ln -sf "$LIBLSL_PATH" "$PYLSL_DIR/liblsl.so"
        ln -sf "$LIBLSL_PATH" "$PYLSL_DIR/liblsl32.so"
        ln -sf "$LIBLSL_PATH" "$PYLSL_DIR/liblsl64.so"
        ln -sf "$LIBLSL_PATH" "$PYLSL_DIR/lib/liblsl.so"
        ln -sf "$LIBLSL_PATH" "$PYLSL_DIR/lib/liblsl32.so"
        ln -sf "$LIBLSL_PATH" "$PYLSL_DIR/lib/liblsl64.so"
        
        # Set permissions
        if [ "$EUID" -eq 0 ] && [ -n "$SUDO_USER" ]; then
          chown -R "$SUDO_USER:$(id -g $SUDO_USER)" "$PYLSL_DIR"
        fi
        
        echo "Symlinks created. Running test again..."
        if [ "$EUID" -eq 0 ] && [ -n "$SUDO_USER" ]; then
          if sudo -u "$SUDO_USER" "$PROJECT_ROOT/.venv/bin/python" "$TEST_SCRIPT"; then
            echo "✓ LSL now working with created symlinks."
            rm -f "$TEST_SCRIPT"
            return 0
          fi
        else
          if "$PROJECT_ROOT/.venv/bin/python" "$TEST_SCRIPT"; then
            echo "✓ LSL now working with created symlinks."
            rm -f "$TEST_SCRIPT"
            return 0
          fi
        fi
      fi
    fi
  fi
  
  echo "✗ LSL compatibility test failed after auto-fix attempt."
  echo "  Try reinstalling pylsl with a compatible version:"
  echo "  $PROJECT_ROOT/.venv/bin/pip install pylsl==1.12.2"
  echo "  If that fails, try: $PROJECT_ROOT/.venv/bin/pip install pylsl==1.15.0"
  echo "  Or: $PROJECT_ROOT/.venv/bin/pip install pylsl==1.16.1"
  echo "  You may also need to reinstall the libboost dependencies:"
  echo "  sudo apt install -y libboost-all-dev"
  rm -f "$TEST_SCRIPT"
  return 1
}

# Check camera hardware
check_camera_hardware() {
  echo "Checking camera hardware..."
  
  # Check for media devices
  if ! ls /dev/media* &>/dev/null; then
    echo "✗ No media devices found."
    echo "  Check that the camera is connected properly."
    return 1
  fi
  
  # Look for IMX296 in media devices
  CAMERA_FOUND=false
  for i in {0..9}; do
    if [ -e "/dev/media$i" ]; then
      if media-ctl -d "/dev/media$i" -p 2>/dev/null | grep -q -i "imx296"; then
        echo "✓ IMX296 camera found on /dev/media$i"
        CAMERA_FOUND=true
        break
      fi
    fi
  done
  
  if [ "$CAMERA_FOUND" = false ]; then
    echo "✗ IMX296 camera not detected on any media device."
    return 1
  fi
  
  return 0
}

# Check file permissions
check_permissions() {
  echo "Checking file permissions..."
  
  # Check if recordings directory exists
  if [ ! -d "$PROJECT_ROOT/recordings" ]; then
    echo "✗ Recordings directory not found."
    echo "  Run: mkdir -p $PROJECT_ROOT/recordings"
    PERMISSION_ISSUES=true
  fi
  
  # Check if logs directory exists
  if [ ! -d "$PROJECT_ROOT/logs" ]; then
    echo "✗ Logs directory not found."
    echo "  Run: mkdir -p $PROJECT_ROOT/logs"
    PERMISSION_ISSUES=true
  fi
  
  # Check script permissions
  SCRIPTS=(
    "$PROJECT_ROOT/bin/run_imx296_capture.py"
    "$PROJECT_ROOT/bin/restart_camera.sh"
    "$PROJECT_ROOT/bin/view-camera-status.sh"
    "$PROJECT_ROOT/bin/check_recording.sh"
  )
  
  for script in "${SCRIPTS[@]}"; do
    if [ -f "$script" ] && [ ! -x "$script" ]; then
      echo "✗ Script $script is not executable."
      echo "  Run: chmod +x $script"
      PERMISSION_ISSUES=true
    fi
  done
  
  if [ "$PERMISSION_ISSUES" = true ]; then
    return 1
  else
    echo "✓ All file permissions look good."
  fi
  return 0
}

# Check if the systemd service is properly configured
check_systemd_service() {
  echo "Checking systemd service..."
  
  if [ ! -f "/etc/systemd/system/imx296-camera.service" ]; then
    echo "✗ Systemd service file not found."
    echo "  Run the install.sh script to configure it."
    return 1
  fi
  
  if systemctl is-active --quiet imx296-camera.service; then
    echo "✓ IMX296 camera service is running."
  else
    echo "✗ IMX296 camera service is not running."
    echo "  Run: sudo systemctl start imx296-camera.service"
    return 1
  fi
  
  return 0
}

# Test camera capture
test_camera_capture() {
  echo "Testing camera capture (will capture 3 seconds of video)..."
  
  # First, try to fix media-ctl ROI configuration
  fix_media_ctl_roi
  
  local TEST_OUTPUT="$PROJECT_ROOT/recordings/test_capture.mkv"
  local PTS_FILE="/dev/shm/tst.pts"
  
  # Remove previous test files
  rm -f "$TEST_OUTPUT"
  rm -f "$PROJECT_ROOT/recordings/test_capture.mp4"
  rm -f "$PTS_FILE"
  
  # Install missing pyyaml package if needed
  if ! "$PROJECT_ROOT/.venv/bin/pip" list | grep -q "pyyaml"; then
    echo "Installing missing pyyaml package..."
    "$PROJECT_ROOT/.venv/bin/pip" install pyyaml
  fi
  
  # Check for Bookworm OS and set workaround
  WORKAROUND=""
  if [ "" != "$(grep '=bookworm' /etc/os-release 2>/dev/null)" ]; then
    echo "Detected Debian Bookworm, using --no-raw workaround"
    WORKAROUND="--no-raw"
  fi
  
  # Set width, height, and other parameters
  WIDTH=400
  HEIGHT=400
  FRAMERATE=30
  DURATION=3000
  
  # Use similar approach to working script
  echo "Trying capture with matched approach from working script..."
  
  # Check if this is a Pi5 (revision ending with 17 or similar)
  if [ "" != "$(grep "Revision.*: ...17.$" /proc/cpuinfo)" ]; then
    echo "Detected Raspberry Pi 5, using rpicam-vid for capture..."
    
    # Use rpicam-vid for Pi5
    rpicam-vid $WORKAROUND --width $WIDTH --height $HEIGHT --denoise cdn_off --framerate $FRAMERATE -t $DURATION -o /tmp/test_capture.mp4 -n
    
    if [ -f "/tmp/test_capture.mp4" ] && [ -s "/tmp/test_capture.mp4" ]; then
      echo "✅ Capture successful with rpicam-vid"
      # Copy to recordings directory
      cp /tmp/test_capture.mp4 "$TEST_OUTPUT"
      echo "Copied to $TEST_OUTPUT"
    else
      echo "❌ rpicam-vid capture failed, trying with mjpeg codec..."
      rpicam-vid $WORKAROUND --width $WIDTH --height $HEIGHT --denoise cdn_off --framerate $FRAMERATE --codec mjpeg -t $DURATION -o /dev/shm/test_capture.mkv -n
      
      if [ -f "/dev/shm/test_capture.mkv" ] && [ -s "/dev/shm/test_capture.mkv" ]; then
        echo "✅ Capture successful with rpicam-vid and mjpeg codec"
        # Copy to recordings directory
        cp /dev/shm/test_capture.mkv "$TEST_OUTPUT"
        echo "Copied to $TEST_OUTPUT"
      fi
    fi
  else
    echo "Using libcamera-vid for capture..."
    # Use libcamera-vid for older Pi models
    libcamera-vid $WORKAROUND --width $WIDTH --height $HEIGHT --denoise cdn_off --framerate $FRAMERATE --save-pts $PTS_FILE -t $DURATION -o /dev/shm/test_capture.h264 -n
    
    if [ -f "/dev/shm/test_capture.h264" ] && [ -s "/dev/shm/test_capture.h264" ]; then
      echo "✅ Capture successful with libcamera-vid"
      # Convert to mkv for better compatibility
      ffmpeg -f h264 -i /dev/shm/test_capture.h264 -c:v copy -y "$TEST_OUTPUT" &>/dev/null || true
      echo "Converted to $TEST_OUTPUT"
      
      # Analyze PTS file
      if [ -f "$PTS_FILE" ]; then
        echo "Analyzing timestamps..."
        if command -v ptsanalyze &>/dev/null; then
          ptsanalyze "$PTS_FILE"
        else
          echo "First 5 lines of PTS file:"
          head -5 "$PTS_FILE"
        fi
      fi
    else
      echo "❌ libcamera-vid h264 capture failed, trying with mjpeg codec..."
      libcamera-vid $WORKAROUND --width $WIDTH --height $HEIGHT --denoise cdn_off --framerate $FRAMERATE --codec mjpeg -t $DURATION -o /dev/shm/test_capture.mkv -n
      
      if [ -f "/dev/shm/test_capture.mkv" ] && [ -s "/dev/shm/test_capture.mkv" ]; then
        echo "✅ Capture successful with libcamera-vid and mjpeg codec"
        # Copy to recordings directory
        cp /dev/shm/test_capture.mkv "$TEST_OUTPUT"
        echo "Copied to $TEST_OUTPUT"
      fi
    fi
  fi
  
  # Check if any capture succeeded
  if [ -f "$TEST_OUTPUT" ] && [ -s "$TEST_OUTPUT" ]; then
    local FILE_SIZE=$(du -k "$TEST_OUTPUT" | cut -f1)
    echo "✅ Camera capture test successful."
    echo "  Test file saved at: $TEST_OUTPUT"
    echo "  File size: ${FILE_SIZE}KB"
    return 0
  else
    echo "✗ Camera capture test failed."
    echo "Checking more device information..."
    
    # Check GPU memory
    if [ -f "/boot/config.txt" ]; then
      GPU_MEM=$(grep "gpu_mem" /boot/config.txt || echo "Not found")
      echo "GPU memory setting: $GPU_MEM"
      if [ "$GPU_MEM" = "Not found" ]; then
        echo "Recommend adding 'gpu_mem=128' to /boot/config.txt"
      fi
    fi
    
    # Show IMX296 device info
    IMX_INFO=$(dmesg | grep -i "imx296" || echo "No IMX296 info in dmesg")
    echo "IMX296 device info from dmesg:"
    echo "$IMX_INFO"
    
    # Check v4l2 capabilities
    echo "Video device capabilities:"
    for v in /dev/video*; do
      if [ -e "$v" ]; then
        echo "Device: $v"
        v4l2-ctl -d "$v" --list-formats-ext 2>/dev/null || true
      fi
    done
    
    echo "Camera hardware issue detected. Possible solutions:"
    echo "1. Check the camera's physical connection and ribbon cable"
    echo "2. Try 'sudo rpi-update' to get the latest firmware"
    echo "3. Run 'sudo modprobe -r imx296 && sudo modprobe imx296 compatible_mode=1'"
    echo "4. Make sure /etc/modprobe.d/imx296.conf contains: options imx296 compatible_mode=1"
    echo "5. Make sure /boot/config.txt contains: dtoverlay=imx296"
    return 1
  fi
}

# Function to diagnose and fix media-ctl ROI configuration
fix_media_ctl_roi() {
  echo "Checking and fixing media-ctl ROI configuration..."
  
  # Find the media device for IMX296
  local MEDIA_DEVICE=""
  for i in {0..9}; do
    if [ -e "/dev/media$i" ]; then
      if media-ctl -d "/dev/media$i" -p 2>/dev/null | grep -q -i "imx296"; then
        MEDIA_DEVICE="/dev/media$i"
        echo "Found IMX296 camera on $MEDIA_DEVICE"
        break
      fi
    fi
  done
  
  if [ -z "$MEDIA_DEVICE" ]; then
    echo "❌ Could not find IMX296 camera device."
    return 1
  fi
  
  # Get current configuration
  echo "Current media-ctl configuration:"
  media-ctl -d "$MEDIA_DEVICE" -p
  
  # Determine the device ID based on Raspberry Pi revision
  local DEVICE_ID="10"
  if [ "" != "$(grep "Revision.*: ...17.$" /proc/cpuinfo)" ]; then
    DEVICE_ID="10"  # Default to 10 for first camera
    if [ -n "$CAM1" ]; then  # Check for CAM1 env var that may be set
      DEVICE_ID="11"
    fi
  fi
  
  echo "Using device ID: $DEVICE_ID for entity search"
  
  # Use the exact entity format from the working script
  ENTITY_NAME="imx296 $DEVICE_ID-001a"
  echo "Using entity name: $ENTITY_NAME"
  
  # Configure proper 400x400 ROI centered in the sensor using working script approach
  # Calculate crop position to center it in the sensor (using 1440x1088 as reference dimensions)
  WIDTH=400
  HEIGHT=400
  
  # Calculate crop position
  CROP_X=$(( (1440 - WIDTH) / 2 ))
  CROP_Y=$(( (1088 - HEIGHT) / 2 ))
  
  echo "Setting media-ctl with centered crop: crop:($CROP_X,$CROP_Y)/${WIDTH}x${HEIGHT}"
  
  # Try the exact command format from the working script
  for m in {0..5}; do
    if [ -e "/dev/media$m" ]; then
      echo "Trying on /dev/media$m with exact working script format..."
      media-ctl -d "/dev/media$m" --set-v4l2 "'imx296 $DEVICE_ID-001a':0 [fmt:SBGGR10_1X10/${WIDTH}x${HEIGHT} crop:(${CROP_X},${CROP_Y})/${WIDTH}x${HEIGHT}]" -v && {
        echo "✅ Successfully configured media$m with exact script format"
        break
      }
    fi
  done
  
  # Verify the configuration
  echo "Updated media-ctl configuration:"
  media-ctl -d "$MEDIA_DEVICE" -p
  
  # Verify formats with v4l2-ctl
  echo "Available formats on video devices:"
  for v in /dev/video*; do
    if [ -e "$v" ]; then
      echo "Device: $v"
      v4l2-ctl -d "$v" --list-formats-ext 2>/dev/null || true
    fi
  done
  
  # Create modprobe configuration if it doesn't exist
  if [ ! -f "/etc/modprobe.d/imx296.conf" ]; then
    echo "Creating IMX296 compatible_mode configuration..."
    echo "options imx296 compatible_mode=1" | sudo tee /etc/modprobe.d/imx296.conf
  fi
  
  # Check if dtoverlay exists in config.txt
  if [ -f "/boot/config.txt" ] && ! grep -q "dtoverlay=imx296" "/boot/config.txt"; then
    echo "Adding IMX296 device tree overlay to /boot/config.txt"
    echo "dtoverlay=imx296" | sudo tee -a /boot/config.txt
  fi
  
  # Ensure video devices have proper permissions
  echo "Setting video device permissions..."
  sudo chmod 666 /dev/video* 2>/dev/null || true
  sudo chmod 666 /dev/media* 2>/dev/null || true
  
  echo "Media-ctl ROI configuration complete"
}

# Check liblsl and pylsl symlinks 
check_pylsl_symlinks() {
  echo "Checking pylsl library symlinks..."
  
  if [ ! -d "$PROJECT_ROOT/.venv" ]; then
    echo "✗ Cannot check symlinks: venv not found"
    return 1
  fi
  
  if ! "$PROJECT_ROOT/.venv/bin/pip" list | grep -q "pylsl"; then
    echo "✗ Cannot check symlinks: pylsl not installed"
    return 1
  fi
  
  # Find Python packages directory
  PYTHON_VERSION=$(ls "$PROJECT_ROOT/.venv/lib/" | grep "python3" | head -1)
  if [ -z "$PYTHON_VERSION" ]; then
    echo "✗ Could not determine Python version directory"
    return 1
  fi
  
  SITE_PKG_DIR="$PROJECT_ROOT/.venv/lib/$PYTHON_VERSION/site-packages"
  PYLSL_DIR="$SITE_PKG_DIR/pylsl"
  
  if [ ! -d "$PYLSL_DIR" ]; then
    echo "✗ Could not find pylsl directory at $PYLSL_DIR"
    return 1
  fi
  
  # Check for liblsl library
  LIBLSL_PATH=""
  if [ -f "/usr/local/lib/liblsl.so" ]; then
    LIBLSL_PATH="/usr/local/lib/liblsl.so"
  elif ldconfig -p | grep -q "liblsl\.so"; then
    LIBLSL_PATH=$(ldconfig -p | grep "liblsl\.so" | head -1 | awk '{print $4}')
  fi
  
  if [ -z "$LIBLSL_PATH" ]; then
    echo "✗ Could not find liblsl library. Cannot check symlinks."
    return 1
  fi
  
  echo "Found liblsl at: $LIBLSL_PATH"
  echo "Found pylsl at: $PYLSL_DIR"
  
  # Check if symlinks exist and point to the correct library
  SYMLINKS_OK=true
  NEEDED_SYMLINKS=(
    "$PYLSL_DIR/liblsl.so"
    "$PYLSL_DIR/liblsl32.so"
    "$PYLSL_DIR/liblsl64.so"
  )
  
  for symlink in "${NEEDED_SYMLINKS[@]}"; do
    if [ ! -L "$symlink" ] || [ ! -e "$symlink" ]; then
      echo "✗ Missing or broken symlink: $symlink"
      SYMLINKS_OK=false
    else
      echo "✓ Symlink exists: $symlink"
    fi
  done
  
  if [ "$SYMLINKS_OK" = false ]; then
    echo "Attempting to fix pylsl symlinks..."
    
    # Create lib directory if it doesn't exist
    mkdir -p "$PYLSL_DIR/lib"
    
    # Create symlinks for all architectures
    ln -sf "$LIBLSL_PATH" "$PYLSL_DIR/liblsl.so" || true
    ln -sf "$LIBLSL_PATH" "$PYLSL_DIR/liblsl32.so" || true
    ln -sf "$LIBLSL_PATH" "$PYLSL_DIR/liblsl64.so" || true
    ln -sf "$LIBLSL_PATH" "$PYLSL_DIR/lib/liblsl.so" || true
    ln -sf "$LIBLSL_PATH" "$PYLSL_DIR/lib/liblsl32.so" || true
    ln -sf "$LIBLSL_PATH" "$PYLSL_DIR/lib/liblsl64.so" || true
    
    # Set proper permissions
    if [ "$EUID" -eq 0 ] && [ -n "$SUDO_USER" ]; then
      chown -R "$SUDO_USER:$(id -g $SUDO_USER)" "$PYLSL_DIR"
    fi
    
    echo "✓ Created symlinks for liblsl library in pylsl directory"
    return 0
  else
    echo "✓ pylsl symlinks are correctly configured"
    return 0
  fi
}

# Run all checks
run_all_checks() {
  local ALL_PASSED=true
  
  if ! check_venv; then
    ALL_PASSED=false
  fi
  
  if ! check_python_packages; then
    ALL_PASSED=false
  fi
  
  if ! check_liblsl; then
    ALL_PASSED=false
  fi
  
  if ! check_pylsl_symlinks; then
    ALL_PASSED=false
  fi
  
  if ! check_lsl_compatibility; then
    ALL_PASSED=false
  fi
  
  if ! check_camera_hardware; then
    ALL_PASSED=false
  fi
  
  if ! check_permissions; then
    ALL_PASSED=false
  fi
  
  # Only check systemd if we're root
  if [ "$EUID" -eq 0 ]; then
    if ! check_systemd_service; then
      ALL_PASSED=false
    fi
  else
    echo "Skipping systemd service check (requires root)"
  fi
  
  echo "Running camera test..."
  if ! test_camera_capture; then
    ALL_PASSED=false
  fi
  
  echo ""
  if [ "$ALL_PASSED" = true ]; then
    echo "✅ All diagnostics passed! Camera system should be fully operational."
  else
    echo "❌ Some diagnostics failed. Please check the issues listed above."
  fi
}

# Parse command line arguments
case "$1" in
  --venv)
    check_venv
    ;;
  --packages)
    check_python_packages
    ;;
  --liblsl)
    check_liblsl
    ;;
  --lsl-compat)
    check_lsl_compatibility
    ;;
  --fix-symlinks)
    check_pylsl_symlinks
    ;;
  --camera)
    check_camera_hardware
    ;;
  --permissions)
    check_permissions
    ;;
  --service)
    check_systemd_service
    ;;
  --test)
    test_camera_capture
    ;;
  *)
    run_all_checks
    ;;
esac 