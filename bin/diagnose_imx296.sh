#!/bin/bash
# IMX296 Global Shutter Camera Diagnostic Script
# Author: Anzal KS <anzal.ks@gmail.com>
# Date: May 23, 2025

set -e

# Check if running as root
if [ "$EUID" -ne 0 ]; then
  echo "Please run as root (use sudo)"
  exit 1
fi

echo "===== IMX296 Camera Diagnostic Script ====="
echo "This script will run diagnostics on your IMX296 camera setup."
echo ""

# Function to highlight output
highlight() {
  echo -e "\e[1;33m$1\e[0m"
}

highlight "1. Checking system requirements..."
# Check for required tools
for cmd in python3 pip3 libcamera-vid ffmpeg media-ctl; do
  if command -v "$cmd" > /dev/null 2>&1; then
    echo "✓ $cmd found: $(command -v "$cmd")"
    
    # Check version of important tools
    if [ "$cmd" = "libcamera-vid" ]; then
      VERSION=$($cmd --version 2>&1 | head -n 1)
      echo "  Version: $VERSION"
    elif [ "$cmd" = "ffmpeg" ]; then
      VERSION=$($cmd -version 2>&1 | head -n 1)
      echo "  Version: $VERSION"
    elif [ "$cmd" = "python3" ]; then
      VERSION=$($cmd --version 2>&1)
      echo "  Version: $VERSION"
    fi
  else
    echo "✗ $cmd not found!"
    echo "  Please install with: sudo apt install -y python3-pip ffmpeg libcamera-apps v4l-utils"
  fi
done

highlight "2. Checking camera hardware..."
# List available cameras
echo "Available cameras:"
libcamera-vid --list-cameras

# Check for IMX296
if libcamera-vid --list-cameras 2>&1 | grep -i 'imx296\|global\|shutter'; then
  echo "✓ IMX296 camera detected"
else
  echo "⚠ IMX296 camera not found by name in libcamera output"
  echo "  This could mean the camera is not connected properly or has a different identifier"
fi

# Check v4l2 device
highlight "3. Checking v4l2 devices..."
for i in {0..10}; do
  if [ -e "/dev/video$i" ]; then
    echo "Device /dev/video$i:"
    v4l2-ctl -d /dev/video$i --all 2>/dev/null || echo "  Cannot read device info"
  fi
done

highlight "4. Testing basic camera capture..."
# Try a direct capture
echo "Attempting direct camera capture (3 seconds)..."
TEST_FILE="/tmp/test_capture_$(date +%s).mkv"
if timeout 10 libcamera-vid --codec mjpeg --width 400 --height 400 --framerate 30 --output "$TEST_FILE" --timeout 3000 2>/dev/null; then
  echo "✓ Direct camera capture succeeded"
  
  # Check file size
  if [ -f "$TEST_FILE" ]; then
    FILE_SIZE=$(stat -c%s "$TEST_FILE" 2>/dev/null || stat -f%z "$TEST_FILE")
    echo "  Test file size: $FILE_SIZE bytes"
    
    if [ "$FILE_SIZE" -gt 5000 ]; then
      echo "✓ File size looks good (> 5KB)"
    else
      echo "⚠ File seems empty or contains only headers (< 5KB)"
    fi
    
    # Check file with ffprobe
    echo "  File details:"
    ffprobe -v error -show_format -show_streams "$TEST_FILE" || echo "  Cannot read file details"
  else
    echo "✗ Test file not created"
  fi
else
  echo "✗ Direct camera capture failed"
fi

highlight "5. Testing direct capture to ffmpeg pipe..."
# Try direct piping to ffmpeg
echo "Attempting direct piping from camera to ffmpeg (3 seconds)..."
TEST_PIPE_FILE="/tmp/test_pipe_$(date +%s).mkv"
if timeout 15 bash -c "libcamera-vid --codec mjpeg --width 400 --height 400 --framerate 30 -o - --timeout 3000 2>/dev/null | ffmpeg -y -f mjpeg -i - -c:v copy -an '$TEST_PIPE_FILE' 2>/dev/null"; then
  echo "✓ Direct piping to ffmpeg succeeded"
  
  # Check pipe file size
  if [ -f "$TEST_PIPE_FILE" ]; then
    FILE_SIZE=$(stat -c%s "$TEST_PIPE_FILE" 2>/dev/null || stat -f%z "$TEST_PIPE_FILE")
    echo "  Test pipe file size: $FILE_SIZE bytes"
    
    if [ "$FILE_SIZE" -gt 5000 ]; then
      echo "✓ Pipe file size looks good (> 5KB)"
    else
      echo "⚠ Pipe file seems empty or contains only headers (< 5KB)"
    fi
  else
    echo "✗ Test pipe file not created"
  fi
else
  echo "✗ Direct piping to ffmpeg failed"
  
  # Try an ultra simple test with minimal options
  echo "  Trying simplified capture with minimal options..."
  SIMPLE_TEST_FILE="/tmp/simple_test_$(date +%s).mkv"
  if timeout 10 bash -c "libcamera-vid --codec mjpeg -o - --timeout 3000 2>/dev/null | ffmpeg -y -f mjpeg -i - -c:v copy -an '$SIMPLE_TEST_FILE' 2>/dev/null"; then
    echo "✓ Simplified piping to ffmpeg succeeded"
    
    if [ -f "$SIMPLE_TEST_FILE" ]; then
      FILE_SIZE=$(stat -c%s "$SIMPLE_TEST_FILE" 2>/dev/null || stat -f%z "$SIMPLE_TEST_FILE")
      echo "  Simple test file size: $FILE_SIZE bytes"
      
      if [ "$FILE_SIZE" -gt 5000 ]; then
        echo "✓ Simple test produced valid video!"
        echo "  This proves the basic capture pipeline works with default settings."
        echo "  The problem is likely with specific camera parameters."
      fi
    fi
  else
    echo "✗ Even simplified piping failed. This indicates a fundamental issue."
    echo "  Capturing straight to file without ffmpeg..."
    
    # Try direct capture without ffmpeg
    DIRECT_FILE="/tmp/direct_test_$(date +%s).mjpeg"
    if timeout 5 libcamera-vid --codec mjpeg --output "$DIRECT_FILE" --timeout 3000; then
      if [ -f "$DIRECT_FILE" ]; then
        FILE_SIZE=$(stat -c%s "$DIRECT_FILE" 2>/dev/null || stat -f%z "$DIRECT_FILE")
        echo "  Direct file size: $FILE_SIZE bytes"
        
        if [ "$FILE_SIZE" -gt 5000 ]; then
          echo "✓ Direct camera capture works, but ffmpeg piping fails."
          echo "  Issue is likely in the pipe connection between camera and ffmpeg."
          
          # Try to fix with an explicit format for the files
          echo "  Testing with explicit output format..."
          FORMAT_TEST_FILE="/tmp/format_test_$(date +%s).h264"
          if timeout 5 libcamera-vid --codec h264 --output "$FORMAT_TEST_FILE" --timeout 3000; then
            echo "  H264 direct test completed"
          fi
        fi
      fi
    else
      echo "✗ Even direct camera capture without ffmpeg failed."
      echo "  This suggests a hardware or driver issue with the camera."
    fi
  fi
fi

highlight "6. Checking LSL installation..."
# Check pylsl
if python3 -c "import pylsl; print('LSL version:', pylsl.__version__)" 2>/dev/null; then
  echo "✓ LSL installation verified"
else
  echo "✗ LSL not properly installed or importable"
  echo "  Try reinstalling: python3 -m pip install --force-reinstall pylsl"
fi

highlight "7. Checking directory permissions..."
# Check recording directory
RECORDING_DIR="/home/dawg/recordings"
if [ -d "$RECORDING_DIR" ]; then
  echo "✓ Recording directory exists: $RECORDING_DIR"
  
  # Check permissions
  PERMISSIONS=$(stat -c "%a" "$RECORDING_DIR" 2>/dev/null || stat -f "%p" "$RECORDING_DIR" 2>/dev/null)
  OWNER=$(stat -c "%U" "$RECORDING_DIR" 2>/dev/null || stat -f "%Su" "$RECORDING_DIR" 2>/dev/null)
  GROUP=$(stat -c "%G" "$RECORDING_DIR" 2>/dev/null || stat -f "%Sg" "$RECORDING_DIR" 2>/dev/null)
  
  echo "  Permissions: $PERMISSIONS"
  echo "  Owner: $OWNER"
  echo "  Group: $GROUP"
  
  # Check if writable by dawg user
  if su -c "touch $RECORDING_DIR/test_write.tmp" dawg 2>/dev/null; then
    echo "✓ Directory is writable by dawg user"
    rm -f "$RECORDING_DIR/test_write.tmp"
  else
    echo "✗ Directory is NOT writable by dawg user"
    echo "  Fix with: sudo chown -R dawg:dawg $RECORDING_DIR && sudo chmod -R 777 $RECORDING_DIR"
  fi
else
  echo "✗ Recording directory does not exist: $RECORDING_DIR"
  echo "  Creating directory and setting permissions..."
  mkdir -p "$RECORDING_DIR"
  chown -R dawg:dawg "$RECORDING_DIR"
  chmod -R 777 "$RECORDING_DIR"
  echo "✓ Created recording directory with proper permissions"
fi

highlight "8. Checking service status..."
# Check service status
if systemctl is-active --quiet imx296-camera.service; then
  echo "✓ Service is running"
  
  # Check service logs
  echo "  Last 5 log lines:"
  journalctl -u imx296-camera.service -n 5 --no-pager
  
  # Extract the actual ffmpeg command from service logs
  echo "  Extracting ffmpeg command from service logs..."
  FFMPEG_CMD=$(journalctl -u imx296-camera.service | grep "Starting ffmpeg with command:" | tail -n 1 | sed 's/.*Starting ffmpeg with command: //')
  
  if [ -n "$FFMPEG_CMD" ]; then
    echo "  Found ffmpeg command: $FFMPEG_CMD"
    
    # Check for input format flag
    if echo "$FFMPEG_CMD" | grep -q -- "-f mjpeg"; then
      echo "✓ Service is using mjpeg input format correctly"
    elif echo "$FFMPEG_CMD" | grep -q -- "-f h264"; then
      echo "✓ Service is using h264 input format"
    else
      echo "⚠ Service ffmpeg command doesn't specify input format with -f flag"
    fi
    
    # Try to reproduce the command with a test
    echo "  Testing service's ffmpeg command directly..."
    TEST_CMD="libcamera-vid --codec mjpeg --width 400 --height 400 -o - --timeout 3000 | $FFMPEG_CMD"
    echo "  $TEST_CMD"
    
    # Run the test in background and capture PID
    TEMP_OUTPUT=$(mktemp)
    echo "  Running test in background for 3 seconds..."
    bash -c "$TEST_CMD" > "$TEMP_OUTPUT" 2>&1 &
    TEST_PID=$!
    
    # Wait 3 seconds then kill the test
    sleep 3
    kill -TERM $TEST_PID 2>/dev/null || true
    wait $TEST_PID 2>/dev/null || true
    
    # Check for any output file created
    CREATED_FILE=$(echo "$FFMPEG_CMD" | grep -o "[^ ]*\.mkv" | head -n 1)
    if [ -n "$CREATED_FILE" ] && [ -f "$CREATED_FILE" ]; then
      FILE_SIZE=$(stat -c%s "$CREATED_FILE" 2>/dev/null || stat -f%z "$CREATED_FILE" 2>/dev/null)
      echo "  Test produced file: $CREATED_FILE ($FILE_SIZE bytes)"
      
      if [ "$FILE_SIZE" -gt 5000 ]; then
        echo "✓ Service command test produced valid file!"
        echo "  This suggests the service configuration is correct but there may be"
        echo "  an issue with how libcamera-vid is launched or how its output is processed."
      else
        echo "⚠ Service command test produced an empty file"
        echo "  This might indicate an issue with the codec or format settings"
      fi
    else
      echo "⚠ Could not find output file from test command"
      echo "  Check the test output for errors:"
      cat "$TEMP_OUTPUT"
    fi
    
    # Clean up temp file
    rm -f "$TEMP_OUTPUT"
  else
    echo "⚠ Could not find ffmpeg command in service logs"
  fi
else
  echo "✗ Service is not running"
  echo "  Service status:"
  systemctl status imx296-camera.service --no-pager
fi

# Run our diagnostic Python script
highlight "9. Running Python diagnostic script..."
if [ -x /usr/local/bin/test_direct_capture.py ]; then
  echo "Running test_direct_capture.py..."
  /usr/local/bin/test_direct_capture.py -d 3 || echo "Script failed with error code $?"
else
  echo "✗ Diagnostic script not found or not executable"
  echo "  Installing diagnostic script..."
  
  # Find the script in repository
  SCRIPT_PATH=$(find /opt/imx296-camera -name test_direct_capture.py 2>/dev/null || find . -name test_direct_capture.py 2>/dev/null || echo "")
  
  if [ -n "$SCRIPT_PATH" ]; then
    cp "$SCRIPT_PATH" /usr/local/bin/
    chmod +x /usr/local/bin/test_direct_capture.py
    echo "✓ Installed diagnostic script: /usr/local/bin/test_direct_capture.py"
    
    # Run the script
    echo "Running test_direct_capture.py..."
    /usr/local/bin/test_direct_capture.py -d 3 || echo "Script failed with error code $?"
  else
    echo "✗ Cannot find diagnostic script in repository"
  fi
fi

highlight "10. Config File Check..."
CONFIG_FILE="/etc/imx296-camera/config.yaml"
if [ -f "$CONFIG_FILE" ]; then
  echo "✓ Config file exists: $CONFIG_FILE"
  
  # Check codec setting
  CODEC=$(grep -E "^\s*codec:" "$CONFIG_FILE" | awk '{print $2}' | tr -d '"' | tr -d "'")
  echo "  Codec setting: $CODEC"
  
  # Check output directory
  OUTPUT_DIR=$(grep -E "^\s*output_dir:" "$CONFIG_FILE" | awk '{print $2}' | tr -d '"' | tr -d "'")
  echo "  Output directory: $OUTPUT_DIR"
else
  echo "✗ Config file not found: $CONFIG_FILE"
fi

echo ""
highlight "===== Diagnostic Summary ====="
echo "Please check the messages above for any '✗' or '⚠' symbols indicating problems."
echo "If you need assistance, please provide the full output of this script."
echo ""
echo "Quick Fixes:"
echo "  1. Reset recording directory: sudo mkdir -p /home/dawg/recordings && sudo chown -R dawg:dawg /home/dawg/recordings && sudo chmod -R 777 /home/dawg/recordings"
echo "  2. Restart service: sudo systemctl restart imx296-camera.service"
echo "  3. Reinstall pylsl: python3 -m pip install --force-reinstall pylsl"
echo "  4. Run direct capture test: sudo /usr/local/bin/test_direct_capture.py"
echo ""
echo "Diagnostic complete!" 