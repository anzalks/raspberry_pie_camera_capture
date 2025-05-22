#!/bin/bash
# IMX296 Camera Diagnostic and Reset Tool
# Author: Anzal KS <anzal.ks@gmail.com>
# Date: May 22, 2025

# Remove set -e to prevent script from exiting on errors
# set -e
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
ps aux | grep 'python3.*imx296.*capture' | grep -v grep || echo "No python capture processes found"
ps aux | grep 'libcamera-vid' | grep -v grep || echo "No libcamera-vid processes found"
ps aux | grep 'ffmpeg' | grep -v grep || echo "No ffmpeg processes found"
ps aux | grep -E 'simulate|mock|fake' | grep -v grep || echo "No simulation processes found"

echo "----- Hardware Check -----"
echo "Checking camera hardware..."
if command -v vcgencmd &> /dev/null; then
    vcgencmd get_camera || echo "Failed to check camera with vcgencmd"
fi

echo "Checking V4L2 devices..."
ls -la /dev/video* 2>/dev/null || echo "No video devices found"
command -v v4l2-ctl >/dev/null && v4l2-ctl --list-devices || echo "v4l2-ctl not found or failed"

echo "Checking media devices..."
ls -la /dev/media* 2>/dev/null || echo "No media devices found"
for i in {0..9}; do
    if [ -e "/dev/media$i" ]; then
        echo "Media device $i:"
        media-ctl -d /dev/media$i -p || echo "Failed to get media device info"
    fi
done

echo "----- Camera Test -----"
echo "Testing camera with libcamera-hello..."
command -v libcamera-hello >/dev/null && libcamera-hello --list-cameras || echo "libcamera-hello not found or failed"

echo "----- Checking for Simulation Code -----"
echo "Searching for simulation code in the Python files..."
grep -r "simulate\|mock\|fake" --include="*.py" $PROJECT_ROOT/src || echo "No simulation code found"

echo "----- Checking Log Files -----"
echo "Recent log entries:"
if [ -d "$PROJECT_ROOT/logs" ]; then
    find "$PROJECT_ROOT/logs" -type f -name "*.log" -exec ls -la {} \; || echo "Failed to list log files"
    for logfile in $(find "$PROJECT_ROOT/logs" -type f -name "*.log" -mtime -1 2>/dev/null); do
        echo "====== $logfile ======"
        tail -n 50 "$logfile" | grep -E "ERROR|WARN|simulate|zero|empty|file size" || echo "No error/warning entries found"
    done
else
    echo "No logs directory found"
    mkdir -p "$PROJECT_ROOT/logs"
fi

echo "----- Checking Recording Files -----"
echo "Recent recordings:"
find "$PROJECT_ROOT/recordings" -type f -size 0 -name "*.mkv" -exec ls -la {} \; 2>/dev/null || echo "No zero-byte recordings found"
echo "Total zero-byte recordings: $(find "$PROJECT_ROOT/recordings" -type f -size 0 -name "*.mkv" 2>/dev/null | wc -l)"
echo "Non-zero recordings: $(find "$PROJECT_ROOT/recordings" -type f -not -size 0 -name "*.mkv" 2>/dev/null | wc -l)"

echo "----- File Permissions Check -----"
echo "Checking directory permissions..."
mkdir -p "$PROJECT_ROOT/logs" "$PROJECT_ROOT/recordings"
touch "$PROJECT_ROOT/logs/test.txt" 2>/dev/null && echo "✓ Logs directory is writable" && rm "$PROJECT_ROOT/logs/test.txt" || echo "✗ Cannot write to logs directory"
touch "$PROJECT_ROOT/recordings/test.txt" 2>/dev/null && echo "✓ Recordings directory is writable" && rm "$PROJECT_ROOT/recordings/test.txt" || echo "✗ Cannot write to recordings directory"

echo "----- Camera Reset Procedure -----"
echo "Running camera reset procedure..."

# Kill any existing instances
echo "Stopping all related processes..."
sudo pkill -f "python3.*imx296.*capture" 2>/dev/null || echo "No python processes found"
sudo pkill -f "libcamera-vid" 2>/dev/null || echo "No libcamera-vid processes found"
sudo pkill -f "ffmpeg" 2>/dev/null || echo "No ffmpeg processes found"

# Clean up temporary files
echo "Cleaning up temporary files..."
sudo rm -f /tmp/camera_recording_*.tmp 2>/dev/null || true
sudo rm -f /tmp/test_capture.h264 2>/dev/null || true
sudo rm -f /tmp/test_stream.h264 2>/dev/null || true

# Reset V4L2 devices
echo "Resetting V4L2 devices..."
for i in {0..9}; do
    if [ -e "/dev/video$i" ]; then
        echo "  Resetting /dev/video$i"
        v4l2-ctl -d /dev/video$i --all > /dev/null 2>&1 || echo "Failed to reset video$i"
        v4l2-ctl -d /dev/video$i -c timeout_value=3000 > /dev/null 2>&1 || echo "Failed to set timeout on video$i"
    fi
done

# Reset media devices
echo "Resetting media devices..."
for i in {0..9}; do
    if [ -e "/dev/media$i" ]; then
        echo "  Resetting media$i"
        media-ctl -d /dev/media$i -r > /dev/null 2>&1 || echo "Failed to reset media$i"
    fi
done

# Wait for devices to stabilize
echo "Waiting for camera devices to stabilize..."
sleep 2

echo "----- Testing Camera Streaming -----"
echo "Testing direct streaming with libcamera-vid..."
# Test for 1 second and output to a test file
TEST_FILE="/tmp/test_stream_$(date +%s).h264"
if command -v libcamera-vid >/dev/null; then
    if ! libcamera-vid --timeout 1000 --width 400 --height 400 --nopreview --output "$TEST_FILE" 2>/dev/null; then
        echo "First attempt failed, trying with default settings..."
        libcamera-vid --timeout 1000 --nopreview --output "$TEST_FILE" 2>/dev/null || echo "Camera streaming test failed"
    fi
else
    echo "libcamera-vid not found"
fi

# Check if the file was created with non-zero size
if [ -f "$TEST_FILE" ]; then
    if [ -s "$TEST_FILE" ]; then
        size=$(du -h "$TEST_FILE" 2>/dev/null | cut -f1)
        echo "✓ Camera streaming test PASSED: File created with $size data"
    else
        echo "✗ Camera streaming test FAILED: File empty"
    fi
    rm "$TEST_FILE" 2>/dev/null || true
else
    echo "✗ Camera streaming test FAILED: File not created"
fi

echo "----- Recommendations -----"
echo "Based on the diagnostics:"
echo "1. To fix simulation frames: Edit src/imx296_gs_capture/imx296_capture.py"
echo "2. To fix zero-sized files: Check for FFmpeg streaming issues"
echo "3. To restart the camera properly: Run bin/restart_camera.sh"
echo ""
echo "Done! Run bin/restart_camera.sh next to apply fixes." 