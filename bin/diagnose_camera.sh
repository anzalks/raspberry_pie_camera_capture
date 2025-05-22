#!/bin/bash
# IMX296 Camera Diagnostic Script
# Author: Anzal KS <anzal.ks@gmail.com>

# Get script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "==== IMX296 Camera Diagnostic Tool ===="
echo "Project root: $PROJECT_ROOT"

# Check for v4l devices
echo -e "\n=== Checking for video devices ==="
if [ -d "/dev/v4l/by-path" ]; then
    echo "Video devices by path:"
    ls -la /dev/v4l/by-path
else
    echo "No video devices found in /dev/v4l/by-path"
fi

echo -e "\nVideo devices:"
ls -la /dev/video*

# Check for media devices
echo -e "\n=== Checking for media devices ==="
echo "Media devices:"
ls -la /dev/media*

# Check for media controller
echo -e "\n=== Media controller information ==="
for i in {0..5}; do
    if [ -e "/dev/media$i" ]; then
        echo -e "\nMedia device /dev/media$i:"
        media-ctl -d /dev/media$i -p
    fi
done

# Test libcamera-hello
echo -e "\n=== Testing libcamera-hello ==="
echo "Running libcamera-hello --list-cameras:"
libcamera-hello --list-cameras

# Test libcamera-vid
echo -e "\n=== Testing libcamera-vid ==="
echo "Running libcamera-vid --list-cameras:"
libcamera-vid --list-cameras

# Try a basic capture
echo -e "\n=== Testing basic image capture ==="
echo "Trying to capture a single frame..."
test_capture="/tmp/test_capture_$(date +%s).jpg"
echo "Saving to: $test_capture"
libcamera-still -t 1000 -o $test_capture --nopreview 2>&1

if [ -f "$test_capture" ]; then
    size=$(du -h "$test_capture" | cut -f1)
    echo "Capture successful! File size: $size"
else
    echo "Capture failed - no file created"
fi

# Check camera module via Raspberry Pi config
echo -e "\n=== Checking Raspberry Pi camera configuration ==="
if command -v vcgencmd &> /dev/null; then
    echo "Camera via vcgencmd:"
    vcgencmd get_camera
else
    echo "vcgencmd not available"
fi

if [ -f "/proc/device-tree/chosen/model" ]; then
    echo -e "\nRaspberry Pi model:"
    cat /proc/device-tree/chosen/model | tr -d '\0'
fi

if [ -f "/boot/config.txt" ]; then
    echo -e "\nCamera configuration in /boot/config.txt:"
    grep -i "camera\|csi\|imx" /boot/config.txt
fi

# Test ffmpeg
echo -e "\n=== Testing ffmpeg ==="
echo "FFmpeg version:"
ffmpeg -version | head -1

echo -e "\nCreating test video with ffmpeg..."
test_video="/tmp/ffmpeg_test_$(date +%s).mp4"
echo "Saving to: $test_video"
ffmpeg -f lavfi -i testsrc=duration=1:size=320x240:rate=30 -c:v libx264 $test_video -y 2>&1

if [ -f "$test_video" ]; then
    size=$(du -h "$test_video" | cut -f1)
    echo "FFmpeg test successful! File size: $size"
else
    echo "FFmpeg test failed - no file created"
fi

# Check if logs directory is writable
echo -e "\n=== Checking directory permissions ==="
echo "Logs directory:"
mkdir -p "$PROJECT_ROOT/logs"
touch "$PROJECT_ROOT/logs/test.txt" && echo "✓ Logs directory is writable" || echo "✗ Cannot write to logs directory"
ls -la "$PROJECT_ROOT/logs"

echo -e "\nRecordings directory:"
mkdir -p "$PROJECT_ROOT/recordings"
touch "$PROJECT_ROOT/recordings/test.txt" && echo "✓ Recordings directory is writable" || echo "✗ Cannot write to recordings directory"
ls -la "$PROJECT_ROOT/recordings"

echo -e "\n=== Diagnosis Complete ==="
echo "If you're still having issues, try rebooting the Raspberry Pi:"
echo "sudo reboot"
echo "Or check the camera cable connection and make sure the camera is enabled:"
echo "sudo raspi-config" 