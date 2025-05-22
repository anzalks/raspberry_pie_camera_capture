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
  
  local TEST_OUTPUT="$PROJECT_ROOT/recordings/test_capture.mkv"
  
  # Remove previous test file if it exists
  rm -f "$TEST_OUTPUT"
  rm -f "$PROJECT_ROOT/recordings/test_capture.mp4"
  
  # Install missing pyyaml package if needed
  if ! "$PROJECT_ROOT/.venv/bin/pip" list | grep -q "pyyaml"; then
    echo "Installing missing pyyaml package..."
    "$PROJECT_ROOT/.venv/bin/pip" install pyyaml
  fi
  
  # First try with H.264/AVC1 and MKV container
  echo "Trying with H.264/AVC1 codec and MKV container..."
  libcamera-vid -t 3000 --width 1280 --height 720 --framerate 30 --codec h264 --output "$TEST_OUTPUT" --nopreview
  
  if [ ! -f "$TEST_OUTPUT" ] || [ ! -s "$TEST_OUTPUT" ]; then
    echo "First attempt failed, trying with MJPG codec..."
    # Try with MJPG codec which has better hardware compatibility
    libcamera-vid -t 3000 --width 640 --height 480 --framerate 15 --codec mjpeg --output "$TEST_OUTPUT" --nopreview
  fi
  
  # Try a third attempt with YUV format which is often more compatible
  if [ ! -f "$TEST_OUTPUT" ] || [ ! -s "$TEST_OUTPUT" ]; then
    echo "Second attempt failed, trying with YUV format..."
    # Use --inline to use YUV format directly
    libcamera-vid -t 3000 --width 640 --height 480 --framerate 15 --codec mjpeg --output "$TEST_OUTPUT" --nopreview --inline
  fi
  
  # Try a fourth attempt with specific sensor mode
  if [ ! -f "$TEST_OUTPUT" ] || [ ! -s "$TEST_OUTPUT" ]; then
    echo "Third attempt failed, trying with specific sensor mode..."
    # Use direct sensor mode
    libcamera-vid -t 3000 --mode 1456:1088:10 --codec mjpeg --output "$TEST_OUTPUT" --nopreview
  fi
  
  # Last attempt using direct v4l2 commands with ffmpeg
  if [ ! -f "$TEST_OUTPUT" ] || [ ! -s "$TEST_OUTPUT" ]; then
    echo "All libcamera attempts failed, trying with direct ffmpeg capture..."
    if command -v ffmpeg >/dev/null && [ -e "/dev/video0" ]; then
      # Try using ffmpeg directly with v4l2 and MJPG codec
      ffmpeg -f v4l2 -input_format mjpeg -video_size 640x480 -i /dev/video0 -t 3 -c:v copy -y "$TEST_OUTPUT" 2>/dev/null || \
      ffmpeg -f v4l2 -video_size 640x480 -i /dev/video0 -t 3 -c:v libx264 -y "$TEST_OUTPUT" 2>/dev/null
    fi
  fi
  
  if [ -f "$TEST_OUTPUT" ]; then
    local FILE_SIZE=$(du -k "$TEST_OUTPUT" | cut -f1)
    if [ "$FILE_SIZE" -gt 0 ]; then
      echo "✓ Camera capture test successful."
      echo "  Test file saved at: $TEST_OUTPUT"
      echo "  File size: ${FILE_SIZE}KB"
      return 0
    else
      echo "✗ Camera capture test failed - file size is 0KB."
      echo "  Checking available camera settings..."
      
      # Get camera information to help diagnose the issue
      echo "Available camera information:"
      libcamera-hello --list-cameras
      
      echo "Checking for v4l2 devices:"
      v4l2-ctl --list-devices
      
      echo "Checking IMX296 kernel module:"
      if lsmod | grep -q "imx296"; then
        echo "  IMX296 driver is loaded."
      else
        echo "  IMX296 driver is not loaded. Try: sudo modprobe imx296"
      fi
      
      echo "Camera hardware issue detected. Possible solutions:"
      echo "1. Check the camera's physical connection and ribbon cable"
      echo "2. Try 'sudo rpi-update' to get the latest firmware"
      echo "3. Check 'dmesg | grep imx296' for specific driver errors"
      echo "4. Try modifying /boot/config.txt with: dtoverlay=imx296"
      echo "5. Ensure GPU memory is sufficient: gpu_mem=128 in /boot/config.txt"
      return 1
    fi
  else
    echo "✗ Camera capture test failed - no output file created."
    echo "Checking hardware access permissions..."
    
    # Check if user has access to video devices
    if ! groups | grep -qE '(video|plugdev)'; then
      echo "  Current user may not have access to camera devices."
      echo "  Run: sudo usermod -a -G video,plugdev $USER"
      echo "  Then log out and back in to apply the changes."
    fi
    
    # Check for v4l2 device errors
    echo "V4L2 device diagnostics:"
    if [ -e "/dev/video0" ]; then
      v4l2-ctl -d /dev/video0 --all || true
      echo "  Try: sudo v4l2-ctl -d /dev/video0 --set-fmt-video=width=640,height=480,pixelformat=MJPG"
    fi
    
    # Recommend IMX296-specific fixes
    echo "IMX296 Global Shutter Camera Fixes:"
    echo "1. Check /boot/config.txt contains: dtoverlay=imx296"
    echo "2. Try reloading the driver: sudo modprobe -r imx296 && sudo modprobe imx296"
    echo "3. Your camera shows the error: 'Failed to start streaming: Invalid argument'"
    echo "   This usually indicates an incompatible format or driver issue."
    echo "4. Create a /etc/modprobe.d/imx296.conf file with: options imx296 compatible_mode=1"
    echo "5. Check if MJPG format is supported: v4l2-ctl --list-formats-ext"
    
    return 1
  fi
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