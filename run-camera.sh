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
    
    # Check for media-ctl (required for Global Shutter Camera)
    if ! command -v media-ctl &> /dev/null; then
        packages_to_install="$packages_to_install libcamera-tools"
    fi
    
    # Install missing packages
    if [ -n "$packages_to_install" ]; then
        echo "Installing missing packages:$packages_to_install"
        apt update && apt install -y $packages_to_install
    fi
    
    # Setup camera lock file with proper permissions
    echo "Setting up camera lock file with proper permissions..."
    rm -f /tmp/raspie_camera.lock
    touch /tmp/raspie_camera.lock
    chmod 666 /tmp/raspie_camera.lock
    echo "Camera lock file created with proper permissions"
    
    # Tell user they should run this script as normal user
    echo "Please run this script as a normal user (without sudo) for interactive mode."
    exit 0
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
  preview: true  # Enable preview window by default
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
  use_unicode: true  # Enable unicode characters for better display
  update_frequency: 0.5
EOF
    echo "Created default config.yaml with preview enabled"
else
    # Make sure preview is enabled in the config
    if grep -q "preview: false" config.yaml; then
        echo "Enabling preview in config.yaml..."
        sed -i 's/preview: false/preview: true/' config.yaml
    fi
fi

# Force terminal settings for proper display
export TERM=xterm-256color
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

# Set extra parameters
EXTRA_PARAMS=""

# Ask if user wants to customize parameters
read -p "Use custom resolution and FPS? (y/n): " custom_params
if [[ $custom_params == "y" || $custom_params == "Y" ]]; then
    read -p "Enter width (default: 640): " width
    read -p "Enter height (default: 480): " height
    read -p "Enter FPS (default: 30): " fps
    
    # Use defaults if empty
    width=${width:-640}
    height=${height:-480}
    fps=${fps:-30}
    
    EXTRA_PARAMS="--width $width --height $height --fps $fps"
    echo "Using custom parameters: $EXTRA_PARAMS"
fi

# Run camera capture
echo "Starting camera capture with default settings from config.yaml..."
echo "Press Ctrl+C to stop"
echo "============================================================"

# Run with parameters, ensuring preview is enabled
python -m src.raspberry_pi_lsl_stream.camera_capture $EXTRA_PARAMS --preview

# Exit with the same status as the camera capture
exit $? 