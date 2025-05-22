#!/bin/bash
# Simple script to run the Raspberry Pi Camera Capture system
# Author: Anzal (anzal.ks@gmail.com)
# Incorporates Hermann-SW's Global Shutter Camera crop configuration techniques
# Reference: https://gist.github.com/Hermann-SW/e6049fe1a24fc2b5a53c654e0e9f6b9c

# Change to the directory containing this script
cd "$(dirname "$0")"

# Function to configure Global Shutter Camera using Hermann-SW's technique
configure_global_shutter() {
  local width=$1
  local height=$2
  local fps=$3
  
  # Check for even width/height (required for Global Shutter Camera)
  if [ $((width % 2)) -ne 0 ] || [ $((height % 2)) -ne 0 ]; then
    echo "Width and height must be even numbers for Global Shutter Camera"
    # Make them even if needed
    width=$((width - (width % 2)))
    height=$((height - (height % 2)))
    echo "Adjusted to ${width}x${height}"
  fi
  
  # Check for bookworm OS to apply workaround if needed
  workaround=""
  if grep -q "=bookworm" /etc/os-release 2>/dev/null; then
    workaround="--no-raw"
    echo "Detected Bookworm OS, applying --no-raw workaround"
  fi
  
  # Determine device ID based on Pi model and camera ID
  device_id=10  # Default for camera 0
  if grep -q "Revision.*: ...17." /proc/cpuinfo 2>/dev/null; then
    # Pi 5 detected
    device_id=10  # Use 11 for second camera
    echo "Raspberry Pi 5 detected, using device ID $device_id"
  fi
  
  # Calculate crop parameters (centered on the sensor)
  # Global Shutter Camera has a 1456×1088 sensor
  sensor_width=1456
  sensor_height=1088
  
  # Calculate the top-left corner for crop to center it
  left=$(( (sensor_width - width) / 2 ))
  top=$(( (sensor_height - height) / 2 ))
  
  # Make sure left and top are even numbers
  left=$((left - (left % 2)))
  top=$((top - (top % 2)))
  
  # Find the media device the GS camera is connected to
  for m in {0..5}; do
    media-ctl -d /dev/media$m --set-v4l2 "'imx296 $device_id-001a':0 [fmt:SBGGR10_1X10/${width}x${height} crop:(${left},${top})/${width}x${height}]" -v >/dev/null 2>&1
    if [ $? -eq 0 ]; then
      echo "Successfully configured Global Shutter Camera on /dev/media$m"
      echo "Set ${width}x${height} @ ${fps}fps with crop at (${left},${top})"
      
      # Verify the configuration
      libcamera-hello --list-cameras 2>/dev/null | grep -A 2 "crop"
      return 0
    fi
  done
  
  echo "Failed to configure Global Shutter Camera. Trying alternative method..."
  
  # Try with v4l2-ctl as fallback
  for dev in /dev/video*; do
    if v4l2-ctl -d $dev --all 2>/dev/null | grep -i "imx296" >/dev/null; then
      echo "Found IMX296 on $dev, applying fallback configuration"
      v4l2-ctl -d $dev --set-fmt-video=width=$width,height=$height,pixelformat=RGGB
      v4l2-ctl -d $dev --set-crop=top=$top,left=$left,width=$width,height=$height
      echo "Applied fallback configuration with v4l2-ctl"
      return 0
    fi
  done
  
  echo "Could not configure Global Shutter Camera"
  return 1
}

# Function to detect Global Shutter Camera
detect_global_shutter() {
  # Try media-ctl method
  for m in {0..5}; do
    if media-ctl -d /dev/media$m -p 2>/dev/null | grep -i "imx296" >/dev/null; then
      echo "Global Shutter Camera (IMX296) detected on /dev/media$m"
      return 0
    fi
  done
  
  # Try v4l2-ctl method
  if v4l2-ctl --list-devices 2>/dev/null | grep -i "imx296" >/dev/null; then
    echo "Global Shutter Camera (IMX296) detected in device list"
    return 0
  fi
  
  return 1
}

# Check if running as root/sudo for system package installation
if [ "$(id -u)" -eq 0 ]; then
    # Running as root, can install system packages if needed
    echo "Running as root - installing required system packages..."
    
    # Install packages in a more reliable way
    echo "Updating package lists..."
    apt update
    
    echo "Installing ALL essential camera packages..."
    apt install -y v4l-utils libcamera-apps libcamera-tools media-ctl curl python3-libcamera
    
    # Fix camera device permissions for ALL video devices
    echo "Setting permissions for ALL camera devices..."
    for dev in /dev/video*; do
        if [ -e "$dev" ]; then
            echo "Setting permissions for $dev"
            chmod 666 "$dev"
        fi
    done
    
    # Fix permissions for media devices (needed for Global Shutter Camera)
    for dev in /dev/media*; do
        if [ -e "$dev" ]; then
            echo "Setting permissions for $dev"
            chmod 666 "$dev"
        fi
    done
    
    # Ensure the user is in video and input groups
    echo "Adding user to video and input groups..."
    if [ -n "$SUDO_USER" ]; then
        usermod -a -G video "$SUDO_USER"
        usermod -a -G input "$SUDO_USER"
        echo "Added $SUDO_USER to video and input groups"
    else
        echo "WARNING: Could not determine user to add to groups (SUDO_USER not set)"
    fi
    
    # Setup camera lock file with proper permissions
    echo "Setting up camera lock file with proper permissions..."
    rm -f /tmp/raspie_camera.lock
    touch /tmp/raspie_camera.lock
    chmod 666 /tmp/raspie_camera.lock
    chown "$SUDO_USER:$SUDO_USER" /tmp/raspie_camera.lock 2>/dev/null || true
    echo "Camera lock file created with proper permissions"
    
    echo "Checking if camera modules are loaded..."
    if ! lsmod | grep -q "^videodev"; then
        echo "Loading camera modules..."
        modprobe videodev 2>/dev/null || true
        modprobe v4l2_common 2>/dev/null || true
    fi
    
    echo "System setup complete. Please run this script WITHOUT sudo now for interactive mode."
    echo "You may need to log out and log back in for group changes to take effect."
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

# Check if the script is running in a terminal or as a service
if [ -t 1 ]; then
    # Running in interactive terminal
    export DISPLAY_MODE="terminal"
else
    # Running as a service - ensure display is available
    export DISPLAY_MODE="service"
    
    # Force DISPLAY to :0 if running as a service
    if [ -z "$DISPLAY" ]; then
        export DISPLAY=:0
    fi
    
    # Create status file for service mode
    rm -f /tmp/raspie_camera_status
    touch /tmp/raspie_camera_status
    chmod 666 /tmp/raspie_camera_status
    echo "Camera starting..." > /tmp/raspie_camera_status
fi

# Define status update function for both terminal and service modes
update_status() {
    msg="$1"
    if [ "$DISPLAY_MODE" = "terminal" ]; then
        echo "$msg"
    fi
    echo "$msg" > /tmp/raspie_camera_status
}

# Always enable preview by default
export PREVIEW_ENABLED=true

# Always run in foreground mode (better for systemd service and terminal)
export FOREGROUND=true

# Check for Global Shutter Camera
if command -v v4l2-ctl >/dev/null && command -v media-ctl >/dev/null; then
    if detect_global_shutter; then
        update_status "Global Shutter Camera detected"
        
        # Ask user if they want to use high frame rate configuration
        if [ "$DISPLAY_MODE" = "terminal" ]; then
            echo "Would you like to use a high frame rate configuration for the Global Shutter Camera?"
            echo "1) 1456x96 @ 536fps (full width, maximum fps)"
            echo "2) 688x136 @ 400fps (medium crop, high fps)"
            echo "3) 224x96 @ 500fps (small ROI, very high fps)"
            echo "4) 600x600 @ 200fps (square crop, moderate fps)"
            echo "5) Custom resolution"
            echo "6) Use default configuration"
            read -p "Enter selection (1-6): " gs_selection
            
            case $gs_selection in
                1)
                    width=1456
                    height=96
                    fps=536
                    ;;
                2)
                    width=688
                    height=136
                    fps=400
                    ;;
                3)
                    width=224
                    height=96
                    fps=500
                    ;;
                4)
                    width=600
                    height=600
                    fps=200
                    ;;
                5)
                    read -p "Enter width (must be even): " width
                    read -p "Enter height (must be even): " height
                    read -p "Enter fps: " fps
                    ;;
                *)
                    width=400
                    height=400
                    fps=100
                    ;;
            esac
            
            if [ "$gs_selection" != "6" ]; then
                update_status "Configuring Global Shutter Camera for ${width}x${height} @ ${fps}fps"
                if configure_global_shutter $width $height $fps; then
                    update_status "Global Shutter Camera configured successfully"
                    export CAM_WIDTH=$width
                    export CAM_HEIGHT=$height
                    export CAM_FPS=$fps
                    export GS_CAMERA_CONFIGURED=true
                else
                    update_status "Warning: Failed to configure Global Shutter Camera"
                fi
            fi
        elif [ "$GS_CAMERA_AUTO_CONFIG" = "true" ]; then
            # When running as a service, use a default high-fps configuration
            width=688
            height=136
            fps=400
            update_status "Auto-configuring Global Shutter Camera for ${width}x${height} @ ${fps}fps"
            if configure_global_shutter $width $height $fps; then
                update_status "Global Shutter Camera configured successfully"
                export CAM_WIDTH=$width
                export CAM_HEIGHT=$height
                export CAM_FPS=$fps
                export GS_CAMERA_CONFIGURED=true
            fi
        fi
    fi
fi

# Main execution section
update_status "Starting camera capture system..."

# Set parameters for command line if Global Shutter Camera was configured
GS_PARAMS=""
if [ "$GS_CAMERA_CONFIGURED" = "true" ]; then
    GS_PARAMS="--width $CAM_WIDTH --height $CAM_HEIGHT --fps $CAM_FPS"
    update_status "Using Global Shutter Camera parameters: $GS_PARAMS"
fi

# Check if we're running Python directly or using a Python module
if [ -f "camera_stream_fixed.py" ]; then
    update_status "Running camera_stream_fixed.py directly..."
    python3 camera_stream_fixed.py --preview=$PREVIEW_ENABLED $GS_PARAMS
elif [ -d "src/raspberry_pi_lsl_stream" ]; then
    update_status "Running as module..."
    # Set PYTHONPATH to ensure module imports work
    export PYTHONPATH="$PWD:$PYTHONPATH"
    python3 -m src.raspberry_pi_lsl_stream.camera_stream_fixed --preview=$PREVIEW_ENABLED $GS_PARAMS
else
    update_status "ERROR: Could not find camera_stream_fixed.py"
    exit 1
fi

# Exit with the same status as the camera capture
exit $? 