#!/bin/bash
# IMX296 Camera System Restart Script
# Author: Anzal KS <anzal.ks@gmail.com>
# Date: May 22, 2025

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "===== IMX296 Camera System Restart Tool ====="
echo "Project root: $PROJECT_ROOT"

# Check if running as root
if [ "$EUID" -ne 0 ]; then
  echo "Please run as root (using sudo) to ensure proper camera reset"
  exit 1
fi

# Stop any running camera processes
echo "Stopping camera processes..."
systemctl stop imx296-camera.service 2>/dev/null || true
pkill -f "libcamera-vid" 2>/dev/null || true
pkill -f "run_imx296_capture.py" 2>/dev/null || true
pkill -f "ffmpeg" 2>/dev/null || true
sleep 1

# Force kill any stuck processes
echo "Forcing kill of any remaining processes..."
pkill -9 -f "libcamera-vid" 2>/dev/null || true
pkill -9 -f "run_imx296_capture.py" 2>/dev/null || true
pkill -9 -f "ffmpeg" 2>/dev/null || true
sleep 1

# Reset media and video devices
echo "Resetting media devices..."
for i in {0..9}; do
  if [ -e "/dev/media$i" ]; then
    echo "  Resetting /dev/media$i"
    media-ctl -d /dev/media$i -r >/dev/null 2>&1 || echo "  Failed to reset media$i"
  fi
done

echo "Resetting video devices..."
for i in {0..9}; do
  if [ -e "/dev/video$i" ]; then
    echo "  Resetting /dev/video$i"
    v4l2-ctl -d /dev/video$i --set-ctrl timeout_value=3000 >/dev/null 2>&1 || true
  fi
done

# Clean up temporary files
echo "Cleaning up temporary files..."
rm -f /tmp/camera_recording_*.tmp 2>/dev/null || true
rm -f /tmp/camera_stream.* 2>/dev/null || true
rm -f /tmp/test_*.h264 2>/dev/null || true

# Check Python dependencies
echo "Checking Python dependencies..."
if [ -d "$PROJECT_ROOT/.venv" ]; then
  # Check for pylsl
  if ! "$PROJECT_ROOT/.venv/bin/pip" list | grep -q "pylsl"; then
    echo "pylsl not found in virtual environment."
    read -p "Do you want to install it now? (y/n): " install_pylsl
    if [[ "$install_pylsl" == "y" || "$install_pylsl" == "Y" ]]; then
      # Try multiple versions of pylsl in case earlier ones fail
      if ! "$PROJECT_ROOT/.venv/bin/pip" install pylsl==1.12.2; then
        echo "Trying alternate version..."
        if ! "$PROJECT_ROOT/.venv/bin/pip" install pylsl==1.15.0; then
          echo "Trying alternate version..."
          if ! "$PROJECT_ROOT/.venv/bin/pip" install pylsl==1.16.1; then
            echo "Trying latest version..."
            "$PROJECT_ROOT/.venv/bin/pip" install pylsl
          fi
        fi
      fi
      echo "pylsl installed successfully."
    else
      echo "Warning: pylsl is required for LSL streaming functionality."
    fi
  else
    PYLSL_VERSION=$("$PROJECT_ROOT/.venv/bin/pip" show pylsl | grep "Version" | awk '{print $2}')
    echo "✓ pylsl is properly installed (version $PYLSL_VERSION)"
  fi
else
  echo "Warning: Python virtual environment not found at $PROJECT_ROOT/.venv"
  echo "Run install.sh to set up the environment properly."
fi

# Wait for devices to stabilize
echo "Waiting for camera system to stabilize..."
sleep 2

# Test camera with a quick capture
echo "Testing camera with a quick capture..."
TEST_FILE="$PROJECT_ROOT/recordings/test_restart_$(date +%s).mp4"
if libcamera-vid -t 2000 --width 1440 --height 1080 --framerate 30 --codec h264 --output "$TEST_FILE" >/dev/null 2>&1; then
  if [ -f "$TEST_FILE" ] && [ -s "$TEST_FILE" ]; then
    echo "✓ Camera test successful!"
    echo "  Test file: $TEST_FILE"
    echo "  Size: $(du -h "$TEST_FILE" | cut -f1)"
  else
    echo "✗ Camera test failed: Output file is empty or not created."
  fi
else
  echo "✗ Camera test failed: libcamera-vid command failed."
fi

# Restart the camera service
echo "Restarting camera service..."
systemctl restart imx296-camera.service || {
  echo "Failed to restart camera service. Check logs with 'journalctl -u imx296-camera.service'"
  exit 1
}

# Wait for service to start
echo "Waiting for service to start..."
sleep 3

# Check if service is running
if systemctl is-active --quiet imx296-camera.service; then
  echo "✅ Camera service started successfully!"
else
  echo "❌ Failed to start camera service."
  echo "Check logs with: journalctl -u imx296-camera.service -n 50"
  exit 1
fi

echo ""
echo "Camera system has been restarted successfully."
echo "Use 'bin/view-camera-status.sh' to monitor the camera status." 