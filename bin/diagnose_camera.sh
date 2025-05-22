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

# Check pylsl and liblsl compatibility
check_lsl_compatibility() {
  echo "Checking LSL compatibility..."
  
  # Only check if both prerequisites are installed
  if ! ldconfig -p | grep -q "liblsl.so" && [ ! -f "/usr/local/lib/liblsl.so" ] && [ ! -f "/usr/lib/liblsl.so" ]; then
    echo "✗ Cannot check LSL compatibility: liblsl not installed"
    return 1
  fi
  
  if [ ! -d "$PROJECT_ROOT/.venv" ]; then
    echo "✗ Cannot check LSL compatibility: venv not found"
    return 1
  fi
  
  if ! "$PROJECT_ROOT/.venv/bin/pip" list | grep -q "pylsl"; then
    echo "✗ Cannot check LSL compatibility: pylsl not installed"
    return 1
  fi
  
  # Create a simple test script
  local TEST_SCRIPT="/tmp/test_lsl_$$.py"
  cat > "$TEST_SCRIPT" << EOF
import sys
try:
    import pylsl
    print(f"pylsl version: {pylsl.__version__}")
    print("Creating test stream...")
    info = pylsl.StreamInfo("TestStream", "Markers", 1, 100, pylsl.cf_float32, "test_uid")
    outlet = pylsl.StreamOutlet(info)
    outlet.push_sample([1.0])
    print("LSL test successful")
    sys.exit(0)
except Exception as e:
    print(f"LSL test failed: {str(e)}")
    sys.exit(1)
EOF
  
  # Run the test script
  echo "Running LSL compatibility test..."
  if "$PROJECT_ROOT/.venv/bin/python" "$TEST_SCRIPT"; then
    echo "✓ LSL compatibility test passed."
    rm -f "$TEST_SCRIPT"
    return 0
  else
    echo "✗ LSL compatibility test failed."
    echo "  This may indicate version incompatibility between liblsl and pylsl."
    echo "  Try reinstalling both with: sudo bin/install.sh"
    rm -f "$TEST_SCRIPT"
    return 1
  fi
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
  
  local TEST_OUTPUT="$PROJECT_ROOT/recordings/test_capture.mp4"
  
  # Remove previous test file if it exists
  rm -f "$TEST_OUTPUT"
  
  libcamera-vid -t 3000 --width 1440 --height 1080 --framerate 30 --codec h264 --output "$TEST_OUTPUT"
  
  if [ -f "$TEST_OUTPUT" ]; then
    local FILE_SIZE=$(du -k "$TEST_OUTPUT" | cut -f1)
    if [ "$FILE_SIZE" -gt 0 ]; then
      echo "✓ Camera capture test successful."
      echo "  Test file saved at: $TEST_OUTPUT"
      echo "  File size: ${FILE_SIZE}KB"
      return 0
    else
      echo "✗ Camera capture test failed - file size is 0KB."
      return 1
    fi
  else
    echo "✗ Camera capture test failed - no output file created."
    return 1
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