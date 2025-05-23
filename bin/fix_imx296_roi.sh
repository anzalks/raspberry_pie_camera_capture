#!/bin/bash
# Fix IMX296 camera using media-ctl to configure ROI
# By: Anzal KS <anzal.ks@gmail.com>
set -e

echo "===== Fixing IMX296 Camera ROI with media-ctl ====="

# Check if running as root
if [ "$EUID" -ne 0 ]; then
  echo "Please run with sudo for camera access"
  exit 1
fi

# Find media devices
echo "Finding media devices..."
if ! command -v media-ctl &>/dev/null; then
  echo "Error: media-ctl not found. Installing v4l-utils..."
  apt-get update && apt-get install -y v4l-utils
fi

# List media devices
media-ctl --list-devices

# Test output directory
TEST_DIR="/tmp/imx296_test"
mkdir -p "$TEST_DIR"
chmod 777 "$TEST_DIR"

# Get the media device for the IMX296 camera
MEDIA_DEV=$(media-ctl --list-devices | grep -A 1 "imx296" | grep "dev" | awk '{print $1}')
if [ -z "$MEDIA_DEV" ]; then
  MEDIA_DEV="/dev/media0"  # Default if not found
  echo "Using default media device: $MEDIA_DEV"
else
  echo "Found IMX296 media device: $MEDIA_DEV"
fi

# Get entity information
echo "Media device entities:"
media-ctl -d $MEDIA_DEV -p

# Configure the camera with its native resolution (400x400)
echo "Configuring camera with native 400x400 resolution..."
# Set format on the sensor output
media-ctl -d $MEDIA_DEV --set-v4l2 '"imx296":0[fmt:SBGGR10_1X10/400x400]'

# Find the CSI-2 receiver and configure it
media-ctl -d $MEDIA_DEV --set-v4l2 '"*rp1_csi2":0[fmt:SBGGR10_1X10/400x400]'

# Find ISP entity and configure it
media-ctl -d $MEDIA_DEV --set-v4l2 '"*pisp_be":0[fmt:SBGGR10_1X10/400x400]'

echo "Camera configuration complete. Testing capture..."

# Test with direct v4l2 capture
CAMERA_DEV=$(v4l2-ctl --list-devices | grep -A 1 "imx296" | grep "/dev/video" | head -1 | xargs)
if [ -z "$CAMERA_DEV" ]; then
  CAMERA_DEV="/dev/video0"  # Default if not found
  echo "Using default camera device: $CAMERA_DEV"
else
  echo "Found IMX296 camera device: $CAMERA_DEV"
fi

# Get supported formats
echo "Supported formats on $CAMERA_DEV:"
v4l2-ctl -d $CAMERA_DEV --list-formats-ext

# Try capture with v4l2-ctl
echo "Attempting direct capture with v4l2-ctl..."
OUTPUT_FILE="$TEST_DIR/v4l2_capture_$(date +%Y%m%d_%H%M%S).raw"
v4l2-ctl -d $CAMERA_DEV --set-fmt-video=width=400,height=400,pixelformat=SBGGR10 --stream-mmap --stream-count=30 --stream-to="$OUTPUT_FILE" || echo "v4l2-ctl capture failed"

if [ -f "$OUTPUT_FILE" ]; then
  size=$(stat -c%s "$OUTPUT_FILE")
  echo "✓ Raw capture successful: $OUTPUT_FILE ($size bytes)"
else
  echo "✗ Raw capture failed"
fi

# Test with libcamera
echo "Testing with libcamera-vid using native resolution..."
OUTPUT_H264="$TEST_DIR/libcamera_$(date +%Y%m%d_%H%M%S).h264"
libcamera-vid --timeout 2000 --width 400 --height 400 --codec h264 --output "$OUTPUT_H264" || echo "libcamera-vid capture failed"

if [ -f "$OUTPUT_H264" ]; then
  size=$(stat -c%s "$OUTPUT_H264")
  echo "✓ libcamera capture successful: $OUTPUT_H264 ($size bytes)"
else
  echo "✗ libcamera capture failed"
fi

# Try with a simple preview
echo "Testing with preview (check if you can see the camera feed)..."
timeout 5 libcamera-vid --timeout 5000 --width 400 --height 400 --preview || echo "Preview failed"

echo ""
echo "Files created during testing:"
ls -lh "$TEST_DIR"

echo ""
echo "If any of these tests worked, use the working settings in your configuration."
echo "The IMX296 camera's native resolution is 400x400 with the SBGGR10_1X10 format." 