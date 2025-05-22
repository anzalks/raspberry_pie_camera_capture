#!/bin/bash
# Simple script to run the Raspberry Pi Camera Capture system
# Author: Anzal (anzal.ks@gmail.com)

# Change to the directory containing this script
cd "$(dirname "$0")"

# Check if running as root/sudo for system package installation
if [ "$(id -u)" -eq 0 ]; then
    # Running as root, can install system packages if needed
    echo "Checking for required system packages..."
    packages_to_install=""
    
    # Check for v4l-utils
    if ! dpkg -s v4l-utils >/dev/null 2>&1; then
        packages_to_install="$packages_to_install v4l-utils"
    fi
    
    # Check for libcamera-apps
    if ! dpkg -s libcamera-apps >/dev/null 2>&1; then
        packages_to_install="$packages_to_install libcamera-apps"
    fi
    
    # Install missing packages
    if [ -n "$packages_to_install" ]; then
        echo "Installing missing packages:$packages_to_install"
        apt update && apt install -y $packages_to_install
    fi
fi

# Check if a Python virtual environment exists and activate it
if [ -d ".venv" ]; then
    echo "Activating virtual environment..."
    source .venv/bin/activate
fi

# Check if config.yaml exists
if [ ! -f "config.yaml" ]; then
    echo "Warning: config.yaml not found. Creating a default one..."
    cat > config.yaml << EOF
# Raspberry Pi Camera Capture Configuration

# Camera settings
camera:
  width: 400
  height: 400
  fps: 100
  codec: mjpg
  container: mkv
  preview: false
  enable_crop: auto  # Can be true, false, or auto (detect Global Shutter Camera)

# Storage settings
storage:
  save_video: true
  output_dir: recordings
  create_date_folders: true

# Buffer settings
buffer:
  size: 20.0  # seconds
  enabled: true

# Remote control
remote:
  ntfy_topic: raspie-camera-test
  
# LSL settings
lsl:
  stream_name: VideoStream

# Performance settings
performance:
  capture_cpu_core: null  # null means no specific core assignment
  writer_cpu_core: null
  lsl_cpu_core: null
  ntfy_cpu_core: null

# Terminal UI settings
terminal:
  colors_enabled: true
  use_unicode: false  # Set to false for better compatibility
  update_frequency: 0.5
EOF
    echo "Created default config.yaml"
fi

# Force unbuffered Python output
export PYTHONUNBUFFERED=1

# Run environment check
echo "Running environment check..."
python check-camera-env.py

# Ask if user wants to continue
read -p "Continue with camera capture? (y/n): " continue_capture
if [[ $continue_capture != "y" && $continue_capture != "Y" ]]; then
    echo "Exiting."
    exit 0
fi

# Run camera capture
echo "Starting camera capture with default settings from config.yaml..."
python -m src.raspberry_pi_lsl_stream.camera_capture &
CAMERA_PID=$!

# Check if camera process is running
if ! ps -p $CAMERA_PID > /dev/null; then
    echo "Error: Camera process failed to start."
    exit 1
fi

# Wait a moment for startup
sleep 2

# Monitor process and display fallback status if needed
trap "kill $CAMERA_PID 2>/dev/null; exit" INT TERM

# Loop to check if process is still running and display fallback status
echo "Camera process running with PID: $CAMERA_PID"
echo "Press Ctrl+C to stop"

while ps -p $CAMERA_PID > /dev/null; do
    # Check if fallback status file exists (indicates UI problems)
    if [ -f "/tmp/raspie_camera_status" ]; then
        echo ""
        echo "===== Status Update $(date +%H:%M:%S) ====="
        cat /tmp/raspie_camera_status
    fi
    sleep 5
done

echo "Camera process has exited."

# Exit with the same status as the camera capture
wait $CAMERA_PID
exit $? 