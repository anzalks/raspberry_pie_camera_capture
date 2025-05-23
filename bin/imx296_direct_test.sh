#!/bin/bash
# IMX296 Direct Test - Minimal test focusing only on exact native resolution
# By: Anzal KS <anzal.ks@gmail.com>
set -e

echo "===== IMX296 Direct Test (400x400 Native Resolution) ====="

# Check if running as root
if [ "$EUID" -ne 0 ]; then
  echo "Please run with sudo for camera access"
  exit 1
fi

# Test directory
TEST_DIR="/tmp/imx296_direct_test"
mkdir -p "$TEST_DIR"
chmod 777 "$TEST_DIR"
echo "Using test directory: $TEST_DIR"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Configure media pipeline first (critical step)
echo "Configuring media pipeline..."
MEDIA_DEV="/dev/media0"
if ! command -v media-ctl &>/dev/null; then
  echo "Error: media-ctl not found. Installing v4l-utils..."
  apt-get update && apt-get install -y v4l-utils
fi

# Show device info
media-ctl --list-devices || echo "No media devices found"
media-ctl -d $MEDIA_DEV -p || echo "Failed to print media topology"

# Configure with exact 400x400 resolution - this is crucial!
echo "Setting imx296 format to 400x400 SBGGR10_1X10..."
media-ctl -d $MEDIA_DEV --set-v4l2 '"imx296":0[fmt:SBGGR10_1X10/400x400]' || echo "Failed to set imx296 format"
media-ctl -d $MEDIA_DEV --set-v4l2 '"*rp1_csi2":0[fmt:SBGGR10_1X10/400x400]' || echo "Failed to set CSI-2 format"

# Find camera device
echo "Finding camera device..."
CAMERA_DEV=$(v4l2-ctl --list-devices | grep -A 1 "imx296" | grep "/dev/video" | head -1 | xargs)
if [ -z "$CAMERA_DEV" ]; then
  echo "IMX296 camera not found, using default /dev/video0"
  CAMERA_DEV="/dev/video0"
fi
echo "Using camera device: $CAMERA_DEV"

# Show device capabilities
echo "Camera device capabilities:"
v4l2-ctl -d $CAMERA_DEV --all | grep -E "Format|Width|Height|Pixel|Frame"

# Try direct v4l2 capture first
echo "Attempting direct v4l2 capture (10 frames)..."
OUT_RAW="$TEST_DIR/v4l2_raw_${TIMESTAMP}.data"
v4l2-ctl -d $CAMERA_DEV --set-fmt-video=width=400,height=400,pixelformat=SBGGR10 \
  --stream-mmap --stream-count=10 --stream-to="$OUT_RAW" || echo "Failed to capture with v4l2-ctl"

# Check raw file size
if [ -f "$OUT_RAW" ]; then
  size=$(stat -c%s "$OUT_RAW")
  echo "✓ Raw capture: $OUT_RAW ($size bytes)"
else
  echo "✗ Raw capture failed"
fi

# Try with ffmpeg
echo "Attempting ffmpeg capture (5 seconds)..."
OUT_MP4="$TEST_DIR/ffmpeg_${TIMESTAMP}.mp4"
ffmpeg -hide_banner -f v4l2 -s 400x400 -i $CAMERA_DEV -t 5 -vsync 0 \
  -c:v h264_omx -b:v 2M -pix_fmt yuv420p "$OUT_MP4" || echo "Failed to capture with ffmpeg"

# Check ffmpeg file size
if [ -f "$OUT_MP4" ]; then
  size=$(stat -c%s "$OUT_MP4")
  echo "✓ FFmpeg capture: $OUT_MP4 ($size bytes)"
else
  echo "✗ FFmpeg capture failed"
fi

# Try with libcamera
echo "Attempting libcamera capture (2 seconds)..."
OUT_H264="$TEST_DIR/libcamera_${TIMESTAMP}.h264"
libcamera-vid --timeout 2000 --width 400 --height 400 --codec h264 \
  --output "$OUT_H264" || echo "Failed to capture with libcamera-vid"

# Check libcamera file size
if [ -f "$OUT_H264" ]; then
  size=$(stat -c%s "$OUT_H264")
  echo "✓ libcamera capture: $OUT_H264 ($size bytes)"
else
  echo "✗ libcamera capture failed"
fi

echo ""
echo "Files created during testing:"
ls -lh "$TEST_DIR"

echo ""
echo "Direct test complete! Check the file sizes to see which methods worked."
echo "Any file larger than 4KB indicates successful video capture."
echo "Files that are exactly 4KB probably only contain headers with no actual video data." 