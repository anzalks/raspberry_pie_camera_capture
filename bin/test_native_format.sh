#!/bin/bash
# Test IMX296 camera with native format (SBGGR10_1X10)
# By: Anzal KS <anzal.ks@gmail.com>
set -e

echo "===== IMX296 Camera Native Format Test ====="
echo "This will test the camera using its native SBGGR10_1X10 format"

# Check if running as root (needed for camera access)
if [ "$EUID" -ne 0 ]; then
  echo "Please run with sudo for camera access"
  exit 1
fi

# Test directory
TEST_DIR="/tmp/camera_native_test"
mkdir -p "$TEST_DIR"
chmod 777 "$TEST_DIR"
echo "Using test directory: $TEST_DIR"

# Output files
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RAW_FILE="$TEST_DIR/raw_${TIMESTAMP}.data"
YUV_FILE="$TEST_DIR/yuv_${TIMESTAMP}.yuv"
H264_FILE="$TEST_DIR/direct_${TIMESTAMP}.h264"
MKV_FILE="$TEST_DIR/final_${TIMESTAMP}.mkv"

# Check for v4l2-ctl
if ! command -v v4l2-ctl &>/dev/null; then
  echo "Error: v4l2-ctl command not found. Please install v4l-utils package."
  exit 1
fi

# Find camera device
echo "Searching for IMX296 camera..."
CAMERA_DEV=""
for dev in /dev/video*; do
  if v4l2-ctl --device=$dev --all 2>/dev/null | grep -q 'Driver name.*imx296\|RPi CSI-2'; then
    CAMERA_DEV="$dev"
    echo "Found IMX296 camera at $CAMERA_DEV"
    break
  fi
done

if [ -z "$CAMERA_DEV" ]; then
  echo "Warning: Could not identify IMX296 camera device"
  echo "Trying with the first available camera..."
  CAMERA_DEV=$(ls /dev/video* | head -1)
  if [ -z "$CAMERA_DEV" ]; then
    echo "Error: No camera devices found"
    exit 1
  fi
  echo "Using camera device: $CAMERA_DEV"
fi

# Get camera capabilities
echo "Camera capabilities:"
v4l2-ctl --device=$CAMERA_DEV --all | grep -A 20 "Format"

# Try with libcamera apps with raw formats
echo "Testing with different formats..."
# Method 1: Minimal settings
echo "Method 1: Using minimal settings..."
if command -v libcamera-vid &>/dev/null; then
  libcamera-vid --timeout 2000 --output "$H264_FILE" || echo "Failed with minimal settings"
  
  if [ -f "$H264_FILE" ]; then
    size=$(stat -c%s "$H264_FILE")
    echo "✓ File created: $H264_FILE ($size bytes)"
  else
    echo "✗ No file created"
  fi
fi

# Method 2: Using native format
echo "Method 2: Using default resolution..."
if command -v libcamera-vid &>/dev/null; then
  libcamera-vid --timeout 2000 --codec h264 --output "$TEST_DIR/default_res_${TIMESTAMP}.h264" || echo "Failed with default resolution"
  
  if [ -f "$TEST_DIR/default_res_${TIMESTAMP}.h264" ]; then
    size=$(stat -c%s "$TEST_DIR/default_res_${TIMESTAMP}.h264")
    echo "✓ File created: $TEST_DIR/default_res_${TIMESTAMP}.h264 ($size bytes)"
  else
    echo "✗ No file created"
  fi
fi

# Method 3: Using very low resolution
echo "Method 3: Using low resolution..."
if command -v libcamera-vid &>/dev/null; then
  libcamera-vid --timeout 2000 --codec h264 --width 160 --height 160 --output "$TEST_DIR/low_res_${TIMESTAMP}.h264" || echo "Failed with low resolution"
  
  if [ -f "$TEST_DIR/low_res_${TIMESTAMP}.h264" ]; then
    size=$(stat -c%s "$TEST_DIR/low_res_${TIMESTAMP}.h264")
    echo "✓ File created: $TEST_DIR/low_res_${TIMESTAMP}.h264 ($size bytes)"
  else
    echo "✗ No file created"
  fi
fi

# Method 4: Direct grab with v4l2
echo "Method 4: Using v4l2-ctl direct capture..."
if command -v v4l2-ctl &>/dev/null; then
  # Try to set a format it can handle
  v4l2-ctl --device=$CAMERA_DEV --set-fmt-video=width=400,height=400,pixelformat=GREY || echo "Failed to set format"
  
  # Capture a few frames
  v4l2-ctl --device=$CAMERA_DEV --stream-mmap --stream-count=10 --stream-to="$RAW_FILE" || echo "Failed to capture with v4l2-ctl"
  
  if [ -f "$RAW_FILE" ]; then
    size=$(stat -c%s "$RAW_FILE")
    echo "✓ File created: $RAW_FILE ($size bytes)"
  else
    echo "✗ No file created"
  fi
fi

# Method 5: Try with simple preview
echo "Method 5: Using libcamera preview only..."
if command -v libcamera-vid &>/dev/null; then
  timeout 3 libcamera-vid --timeout 3000 --preview || echo "Failed with preview"
  echo "Preview test complete (check if you saw any preview)"
fi

# Method 6: Try with rpicam-vid if available
echo "Method 6: Using rpicam-vid if available..."
if command -v rpicam-vid &>/dev/null; then
  rpicam-vid --timeout 2000 --codec h264 --output "$TEST_DIR/rpicam_${TIMESTAMP}.h264" || echo "Failed with rpicam-vid"
  
  if [ -f "$TEST_DIR/rpicam_${TIMESTAMP}.h264" ]; then
    size=$(stat -c%s "$TEST_DIR/rpicam_${TIMESTAMP}.h264")
    echo "✓ File created: $TEST_DIR/rpicam_${TIMESTAMP}.h264 ($size bytes)"
  else
    echo "✗ No file created with rpicam-vid"
  fi
fi

# Try v4l2-ctl to check for any format that works
echo "Testing various pixel formats with v4l2-ctl..."
for fmt in GREY YU12 YUYV UYVY RGBP RGBO MJPG; do
  echo "Testing pixel format: $fmt"
  out_file="$TEST_DIR/v4l2_${fmt}_${TIMESTAMP}.data"
  
  if v4l2-ctl --device=$CAMERA_DEV --set-fmt-video=width=400,height=400,pixelformat=$fmt 2>/dev/null; then
    echo "Format $fmt accepted by camera"
    
    # Try to capture
    v4l2-ctl --device=$CAMERA_DEV --stream-mmap --stream-count=10 --stream-to="$out_file" || echo "Failed to capture with format $fmt"
    
    if [ -f "$out_file" ]; then
      size=$(stat -c%s "$out_file")
      echo "✓ Captured with format $fmt: $out_file ($size bytes)"
    else
      echo "✗ Failed to capture with format $fmt"
    fi
  else
    echo "✗ Format $fmt not supported by camera"
  fi
done

# List all created files
echo ""
echo "Files created during testing:"
ls -lh "$TEST_DIR" | sort -k 9

echo ""
echo "Native format test complete!"
echo "If any of these methods worked, use the working settings in your configuration."
echo "Check the file sizes to identify successful captures (non-zero or significantly larger than 4KB)." 