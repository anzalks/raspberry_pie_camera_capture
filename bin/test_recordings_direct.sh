#!/bin/bash
# Direct recording test for IMX296 camera
# By: Anzal KS <anzal.ks@gmail.com>
set -e

echo "===== IMX296 Camera Direct Recording Test ====="
echo "This will test direct recording from camera to verify proper functionality"

# Check if running as root (needed for camera access)
if [ "$EUID" -ne 0 ]; then
  echo "Please run with sudo for camera access"
  exit 1
fi

# Define recording directory
RECORDING_DIR="/home/dawg/recordings"
FALLBACK_DIR="/tmp"

# Ensure the recording directory exists
mkdir -p "$RECORDING_DIR"
chmod 777 "$RECORDING_DIR"
echo "✓ Recording directory ready: $RECORDING_DIR"

# Generate a test filename
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
TEST_FILE="$RECORDING_DIR/test_direct_$TIMESTAMP.mkv"
echo "Will record to: $TEST_FILE"

# Function to check if a command exists
command_exists() {
  command -v "$1" >/dev/null 2>&1
}

# Find the camera application
CAMERA_CMD=""
if command_exists libcamera-vid; then
  CAMERA_CMD="libcamera-vid"
  echo "Using libcamera-vid for capture"
elif command_exists rpicam-vid; then
  CAMERA_CMD="rpicam-vid"
  echo "Using rpicam-vid for capture"
else
  echo "Error: No camera capture command found"
  exit 1
fi

# Find ffmpeg
if ! command_exists ffmpeg; then
  echo "Error: ffmpeg not found"
  exit 1
fi

# Create an empty file with correct permissions first
touch "$TEST_FILE"
chmod 666 "$TEST_FILE"

echo "Starting recording (3 seconds)..."
# Use a pipe to connect camera output to ffmpeg
$CAMERA_CMD --timeout 3000 --codec mjpeg --inline --width 400 --height 400 --nopreview --output - | \
  ffmpeg -f mjpeg -i - -c:v copy -vsync 0 -an -y "$TEST_FILE"

# Check if the file was created and has content
if [ -f "$TEST_FILE" ]; then
  FILE_SIZE=$(stat -c%s "$TEST_FILE" 2>/dev/null || echo "0")
  if [ "$FILE_SIZE" -gt 5000 ]; then
    echo "✓ Recording successful! File size: $FILE_SIZE bytes"
    echo "File: $TEST_FILE"
  else
    echo "✗ Warning: File created but small size: $FILE_SIZE bytes"
    echo "This indicates a potential issue with the recording pipeline"
  fi
else
  echo "✗ Error: File was not created"
fi

# Try direct testing with ffmpeg source
echo "Testing ffmpeg with test source..."
TEST_FILE_2="$RECORDING_DIR/test_pattern_$TIMESTAMP.mkv"
touch "$TEST_FILE_2"
chmod 666 "$TEST_FILE_2"

ffmpeg -f lavfi -i testsrc=duration=1:size=400x400:rate=30 -c:v mjpeg -y "$TEST_FILE_2"

if [ -f "$TEST_FILE_2" ]; then
  FILE_SIZE=$(stat -c%s "$TEST_FILE_2" 2>/dev/null || echo "0")
  if [ "$FILE_SIZE" -gt 5000 ]; then
    echo "✓ Test pattern recording successful! File size: $FILE_SIZE bytes"
    echo "File: $TEST_FILE_2"
  else
    echo "✗ Warning: Test pattern file created but small size: $FILE_SIZE bytes"
  fi
else
  echo "✗ Error: Test pattern file was not created"
fi

# Print summary of recording directory
echo ""
echo "Recording directory contents:"
ls -lh "$RECORDING_DIR" | tail -5

echo ""
echo "Recording test complete!"
echo "If the direct test worked but the service creates empty files,"
echo "run the 'bin/direct_fix.sh' script to apply comprehensive fixes." 