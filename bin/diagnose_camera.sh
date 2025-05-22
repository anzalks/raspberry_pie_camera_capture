#!/bin/bash
# IMX296 Camera Diagnostic and Reset Tool
# Author: Anzal KS <anzal.ks@gmail.com>
# Date: May 22, 2025

set -e
echo "==== IMX296 Camera Diagnostic Tool ===="

# Get script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
echo "Project root: $PROJECT_ROOT"

echo "----- System Information -----"
echo "Hostname: $(hostname)"
echo "Kernel: $(uname -r)"
echo "User: $(whoami)"
echo "Date: $(date)"

echo "----- Process Check -----"
echo "Checking for camera processes..."
ps aux | grep 'python3.*imx296.*capture' | grep -v grep
ps aux | grep 'libcamera-vid' | grep -v grep
ps aux | grep 'ffmpeg' | grep -v grep
ps aux | grep -E 'simulate|mock|fake' | grep -v grep

echo "----- Hardware Check -----"
echo "Checking camera hardware..."
if command -v vcgencmd &> /dev/null; then
    vcgencmd get_camera
fi

echo "Checking V4L2 devices..."
ls -la /dev/video*
v4l2-ctl --list-devices

echo "Checking media devices..."
ls -la /dev/media*
for i in {0..9}; do
    if [ -e "/dev/media$i" ]; then
        echo "Media device $i:"
        media-ctl -d /dev/media$i -p
    fi
done

echo "----- Camera Test -----"
echo "Testing camera with libcamera-hello..."
libcamera-hello --list-cameras

echo "----- Checking for Simulation Code -----"
echo "Searching for simulation code in the Python files..."
grep -r "simulate\|mock\|fake" --include="*.py" $PROJECT_ROOT/src

echo "----- Checking Log Files -----"
echo "Recent log entries:"
if [ -d "$PROJECT_ROOT/logs" ]; then
    find "$PROJECT_ROOT/logs" -type f -name "*.log" -exec ls -la {} \;
    for logfile in $(find "$PROJECT_ROOT/logs" -type f -name "*.log" -mtime -1); do
        echo "====== $logfile ======"
        tail -n 50 "$logfile" | grep -E "ERROR|WARN|simulate|zero|empty|file size"
    done
fi

echo "----- Checking Recording Files -----"
echo "Recent recordings:"
find "$PROJECT_ROOT/recordings" -type f -size 0 -name "*.mkv" -exec ls -la {} \;
echo "Total zero-byte recordings: $(find "$PROJECT_ROOT/recordings" -type f -size 0 -name "*.mkv" | wc -l)"
echo "Non-zero recordings: $(find "$PROJECT_ROOT/recordings" -type f -not -size 0 -name "*.mkv" | wc -l)"

echo "----- Camera Reset Procedure -----"
echo "Running camera reset procedure..."

# Kill any existing instances
echo "Stopping all related processes..."
sudo pkill -f "python3.*imx296.*capture" || echo "No python processes found"
sudo pkill -f "libcamera-vid" || echo "No libcamera-vid processes found"
sudo pkill -f "ffmpeg" || echo "No ffmpeg processes found"

# Clean up temporary files
echo "Cleaning up temporary files..."
sudo rm -f /tmp/camera_recording_*.tmp
sudo rm -f /tmp/test_capture.h264

# Reset V4L2 devices
echo "Resetting V4L2 devices..."
for i in {0..9}; do
    if [ -e "/dev/video$i" ]; then
        echo "  Resetting /dev/video$i"
        v4l2-ctl -d /dev/video$i --all > /dev/null 2>&1
        v4l2-ctl -d /dev/video$i -c timeout_value=3000 > /dev/null 2>&1
    fi
done

# Reset media devices
echo "Resetting media devices..."
for i in {0..9}; do
    if [ -e "/dev/media$i" ]; then
        echo "  Resetting media$i"
        media-ctl -d /dev/media$i -r > /dev/null 2>&1
    fi
done

# Wait for devices to stabilize
echo "Waiting for camera devices to stabilize..."
sleep 2

echo "----- Testing Camera Streaming -----"
echo "Testing direct streaming with libcamera-vid..."
# Test for 1 second and output to a test file
libcamera-vid --timeout 1000 --width 400 --height 400 --nopreview --output /tmp/test_stream.h264

# Check if the file was created with non-zero size
if [ -s "/tmp/test_stream.h264" ]; then
    echo "✓ Camera streaming test PASSED: File created with $(du -h /tmp/test_stream.h264 | cut -f1) data"
else
    echo "✗ Camera streaming test FAILED: File empty or not created"
fi

echo "----- Recommendations -----"
echo "Based on the diagnostics:"
echo "1. To fix simulation frames: Edit src/imx296_gs_capture/imx296_capture.py"
echo "2. To fix zero-sized files: Check for FFmpeg streaming issues"
echo "3. To restart the camera properly: Run bin/restart_camera.sh"
echo ""
echo "Done! Run bin/restart_camera.sh next to apply fixes." 