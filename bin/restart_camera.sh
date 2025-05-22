#!/bin/bash
# IMX296 Camera Service Restart Tool
# Author: Anzal KS <anzal.ks@gmail.com>
# Date: May 22, 2025

set -e

# Get script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "==== IMX296 Camera Service Restart Tool ===="
echo "Project root: $PROJECT_ROOT"

# Function to kill processes by pattern
kill_processes() {
    local pattern=$1
    local pids=$(ps aux | grep -E "$pattern" | grep -v grep | awk '{print $2}')
    if [ -n "$pids" ]; then
        echo "Found processes matching '$pattern' with PIDs: $pids"
        echo "Stopping processes..."
        for pid in $pids; do
            sudo kill -9 $pid 2>/dev/null || true
            echo "  Killed process $pid"
        done
        # Verify they're gone
        pids=$(ps aux | grep -E "$pattern" | grep -v grep | awk '{print $2}')
        if [ -n "$pids" ]; then
            echo "WARNING: Some processes still exist: $pids"
        else
            echo "  All processes successfully terminated"
        fi
    else
        echo "No processes matching '$pattern' found."
    fi
}

# Kill any existing camera processes
echo "Checking for running camera processes..."
kill_processes "python3.*imx296.*capture"
kill_processes "libcamera-vid"
kill_processes "ffmpeg.*recording_"

# Clean up any temporary files
echo "Cleaning up temporary files..."
# Find and delete the PTS files
sudo find /tmp -name "camera_*.pts" -delete
# Delete tmp recording markers
sudo rm -f /tmp/camera_recording_*.tmp 2>/dev/null || true
sudo rm -f /tmp/test_capture.h264 2>/dev/null || true
sudo rm -f /tmp/test_stream.h264 2>/dev/null || true
echo "Temporary files cleaned up."

# Reset camera system
echo "Resetting camera system..."
# Reset V4L devices
echo "Resetting V4L devices..."
for i in {0..9}; do
    if [ -e "/dev/video$i" ]; then
        echo "Resetting /dev/video$i"
        v4l2-ctl -d /dev/video$i --all > /dev/null 2>&1 || true
        v4l2-ctl -d /dev/video$i -c timeout_value=3000 > /dev/null 2>&1 || true
        # Try to reset the video device
        v4l2-ctl -d /dev/video$i --set-ctrl=exposure=1000 > /dev/null 2>&1 || true
    fi
done

# Reset media devices
echo "Resetting media devices..."
for i in {0..9}; do
    if [ -e "/dev/media$i" ]; then
        echo "Checking media$i"
        media-ctl -d /dev/media$i -r > /dev/null 2>&1 || true
        
        # Try to detect IMX296 in this media device
        if media-ctl -d /dev/media$i -p 2>&1 | grep -q -i "imx296"; then
            echo "  Found IMX296 camera on media$i"
            export IMX296_MEDIA_DEVICE="/dev/media$i"
        fi
    fi
done

# Wait for devices to stabilize
echo "Waiting for camera devices to stabilize..."
sleep 2

# Check if the camera is visible to the system
echo "Testing camera hardware..."
if command -v vcgencmd &> /dev/null; then
    vcgencmd get_camera
fi

# Test camera with standard command
echo "Testing camera with libcamera-hello..."
if ! libcamera-hello --list-cameras; then
    echo "WARNING: libcamera-hello didn't detect any cameras"
    echo "Will try a direct v4l2 test instead..."
    
    # Try with v4l2-ctl
    v4l2-ctl --list-devices
fi

# Try a simple capture
echo "Testing direct streaming with libcamera-vid..."
# Test for 1 second and output to a test file
if ! libcamera-vid --timeout 1000 --width 400 --height 400 --nopreview --output /tmp/test_stream.h264; then
    echo "WARNING: Initial camera test with libcamera-vid failed"
    echo "Trying alternative method..."
    
    # Try a more basic approach
    libcamera-vid --timeout 1000 --output /tmp/test_stream.h264 --nopreview
fi

# Check if the file was created with non-zero size
if [ -s "/tmp/test_stream.h264" ]; then
    echo "✓ Camera streaming test PASSED: File created with $(du -h /tmp/test_stream.h264 | cut -f1) data"
else
    echo "✗ Camera streaming test FAILED: File empty or not created"
    echo "WARNING: Camera may not be functioning properly"
fi

# Clear system service status (if running as a service)
if command -v systemctl &> /dev/null; then
    if systemctl is-active --quiet imx296-camera.service; then
        echo "Stopping systemd service..."
        sudo systemctl stop imx296-camera.service
        sleep 2
        echo "Service stopped."
    fi
fi

# Ensure logs directory exists with proper permissions
echo "Setting up log directory..."
mkdir -p "$PROJECT_ROOT/logs"
sudo chmod -R 777 "$PROJECT_ROOT/logs" || echo "Warning: Could not set permissions on logs directory"

# Ensure recordings directory exists with proper permissions
echo "Setting up recordings directory..."
mkdir -p "$PROJECT_ROOT/recordings"
sudo chmod -R 777 "$PROJECT_ROOT/recordings" || echo "Warning: Could not set permissions on recordings directory"

# Check the config file exists
if [ ! -f "$PROJECT_ROOT/config/config.yaml" ]; then
    echo "Config file not found. Creating from example..."
    if [ -f "$PROJECT_ROOT/config/config.yaml.example" ]; then
        cp "$PROJECT_ROOT/config/config.yaml.example" "$PROJECT_ROOT/config/config.yaml"
    else
        echo "ERROR: No config example found. Cannot continue."
        exit 1
    fi
fi

# Make sure the script has execute permissions
chmod +x "$SCRIPT_DIR/run_imx296_capture.py"

# Start the camera capture script
echo "Starting camera capture..."
cd "$PROJECT_ROOT"

# Check if we're using a virtual environment
if [ -d ".venv" ]; then
    # Start with virtual environment
    echo "Using virtual environment..."
    .venv/bin/python3 -u bin/run_imx296_capture.py

    # Check return value
    if [ $? -ne 0 ]; then
        echo "Camera service failed to start. Check logs for details."
        exit 1
    fi
else
    # Start with system Python
    echo "Using system Python..."
    python3 -u bin/run_imx296_capture.py

    # Check return value
    if [ $? -ne 0 ]; then
        echo "Camera service failed to start. Check logs for details."
        exit 1
    fi
fi

echo "Camera service started successfully."
echo "To view status, run: bin/view-camera-status.sh" 