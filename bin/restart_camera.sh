#!/bin/bash
# Script to properly restart the IMX296 camera service
# Author: Anzal KS <anzal.ks@gmail.com>

# Get script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "==== IMX296 Camera Service Restart Tool ===="
echo "Project root: $PROJECT_ROOT"

# Kill any existing instances (including zombie processes)
echo "Checking for running camera processes..."
python_pids=$(ps aux | grep 'python3.*imx296.*capture' | grep -v grep | awk '{print $2}')
if [ -n "$python_pids" ]; then
    echo "Found camera processes with PIDs: $python_pids"
    echo "Stopping processes..."
    for pid in $python_pids; do
        sudo kill -9 $pid 2>/dev/null
        echo "Killed process $pid"
    done
else
    echo "No running camera processes found."
fi

# Clean up any temporary files
echo "Cleaning up temporary files..."
sudo rm -f /tmp/camera_recording_*.tmp 2>/dev/null
sudo rm -f /tmp/test_capture.h264 2>/dev/null
echo "Temporary files cleaned up."

# Clear system service status (if running as a service)
if systemctl is-active --quiet imx296-camera.service; then
    echo "Stopping systemd service..."
    sudo systemctl stop imx296-camera.service
    sleep 2
    echo "Service stopped."
fi

# Ensure logs directory exists with proper permissions
echo "Setting up log directory..."
mkdir -p "$PROJECT_ROOT/logs"
sudo chmod -R 777 "$PROJECT_ROOT/logs"

# Ensure recordings directory exists with proper permissions
echo "Setting up recordings directory..."
mkdir -p "$PROJECT_ROOT/recordings"
sudo chmod -R 777 "$PROJECT_ROOT/recordings"

# Make sure the script has execute permissions
sudo chmod +x "$SCRIPT_DIR/run_imx296_capture.py"

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