#!/bin/bash
# Fix video output issues for IMX296 camera
# Run this on the Raspberry Pi to diagnose and fix video output problems
# Author: Anzal KS <anzal.ks@gmail.com>

echo "===== IMX296 Camera Video Output Fix ====="

# Create recording directory with proper permissions
echo "Setting up recording directory..."
RECORDING_DIR="/home/dawg/recordings"
mkdir -p "$RECORDING_DIR"
sudo chmod -R 777 "$RECORDING_DIR"
sudo chown -R dawg:dawg "$RECORDING_DIR"
echo "Directory ready: $RECORDING_DIR"

# Test direct camera recording
echo "Testing direct camera recording..."
TEST_FILE="$RECORDING_DIR/direct_test_$(date +%Y%m%d_%H%M%S).mp4"
echo "Will save to: $TEST_FILE"

# Try rpicam-vid for Pi5
echo "Testing with rpicam-vid..."
rpicam-vid --no-raw --width 400 --height 400 --timeout 5000 --codec h264 --output "$TEST_FILE"

# Check file size
echo "Checking test file size..."
ls -lh "$TEST_FILE"
FILE_SIZE=$(stat -c%s "$TEST_FILE" 2>/dev/null || echo "0")
if [ "$FILE_SIZE" -gt 10000 ]; then
    echo "✅ Direct recording successful with file size: $(( FILE_SIZE / 1024 ))KB"
else
    echo "❌ Direct recording failed or created small file: $FILE_SIZE bytes"
    echo "Trying with mjpeg codec..."
    
    # Try with MJPEG codec
    TEST_FILE="$RECORDING_DIR/direct_test_mjpeg_$(date +%Y%m%d_%H%M%S).mkv"
    rpicam-vid --no-raw --width 400 --height 400 --timeout 5000 --codec mjpeg --output "$TEST_FILE"
    
    FILE_SIZE=$(stat -c%s "$TEST_FILE" 2>/dev/null || echo "0")
    if [ "$FILE_SIZE" -gt 10000 ]; then
        echo "✅ MJPEG recording successful with file size: $(( FILE_SIZE / 1024 ))KB"
    else
        echo "❌ MJPEG recording also failed: $FILE_SIZE bytes"
    fi
fi

# Check service status
echo "Checking camera service status..."
sudo systemctl status imx296-camera.service

# Check logs for permission issues
echo "Checking logs for permission issues..."
grep -i "permission denied" /var/log/syslog | tail -10

# Identify the user running the service
echo "Identifying service user..."
ps aux | grep imx296

# Grant permissions to video devices
echo "Setting video device permissions..."
sudo chmod 666 /dev/video* 2>/dev/null || true
sudo chmod 666 /dev/media* 2>/dev/null || true

# Restart the service
echo "Restarting camera service..."
sudo systemctl restart imx296-camera.service
echo "Service restarted"

# Check for issues in the logs
echo "Checking for errors in the service logs..."
sudo journalctl -u imx296-camera.service -n 20 | grep -i error

echo "Fix script complete. Check the dashboard for status updates."
echo "If recording still doesn't work, check /var/log/syslog for errors." 