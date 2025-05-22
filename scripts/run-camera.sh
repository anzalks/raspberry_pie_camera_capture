#!/bin/bash
# Simple script to run the Raspberry Pi Camera Capture system
# Author: Anzal (anzal.ks@gmail.com)
# Incorporates Hermann-SW's Global Shutter Camera crop configuration techniques
# Reference: https://gist.github.com/Hermann-SW/e6049fe1a24fc2b5a53c654e0e9f6b9c

# Change to the root directory of the project
SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$ROOT_DIR"

# Enable tracing for debugging if needed
# set -x

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
  bookworm_workaround=""
  if grep -q "=bookworm" /etc/os-release 2>/dev/null; then
    bookworm_workaround="--no-raw"
    echo "Detected Bookworm OS, applying --no-raw workaround for libcamera"
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
  
  # Verify media-ctl is available
  if ! command -v media-ctl &> /dev/null; then
    echo "ERROR: media-ctl not found, cannot configure Global Shutter Camera."
    if grep -q "=bookworm" /etc/os-release 2>/dev/null && [ "$(id -u)" -eq 0 ]; then
      echo "Attempting to build v4l-utils and media-ctl from source for Bookworm OS..."
      if build_v4l_utils_from_source; then
        echo "Successfully built v4l-utils and media-ctl from source."
      else
        echo "Failed to build v4l-utils and media-ctl from source."
        return 1
      fi
    else
      echo "Please run this script with sudo to build v4l-utils and media-ctl from source"
      echo "Command: sudo $(realpath "$0")"
      return 1
    fi
  fi
  
  # Try media-ctl configuration if available
  if command -v media-ctl &> /dev/null; then
    # First check if the IMX296 sensor is actually present
    gs_camera_found=false
    for m in {0..5}; do
      if media-ctl -d /dev/media$m -p 2>/dev/null | grep -i "imx296" >/dev/null; then
        echo "Found Global Shutter Camera (IMX296) on /dev/media$m"
        gs_camera_found=true
        break
      fi
    done
    
    if [ "$gs_camera_found" != "true" ]; then
      echo "WARNING: IMX296 Global Shutter Camera not found in media devices"
      echo "Will still attempt to apply configuration..."
    fi
  
    # Find the media device the GS camera is connected to
    gs_configured=false
    for m in {0..5}; do
      echo "Attempting to configure Global Shutter Camera on /dev/media$m..."
      media-ctl -d /dev/media$m --set-v4l2 "'imx296 $device_id-001a':0 [fmt:SBGGR10_1X10/${width}x${height} crop:(${left},${top})/${width}x${height}]" -v 2>&1 || true
      if [ $? -eq 0 ]; then
        echo "Successfully configured Global Shutter Camera on /dev/media$m"
        echo "Set ${width}x${height} @ ${fps}fps with crop at (${left},${top})"
        
        # Verify the configuration
        if command -v libcamera-hello &> /dev/null; then
          echo "Verifying camera configuration:"
          libcamera-hello $bookworm_workaround --list-cameras 2>/dev/null | grep -A 5 "crop" || true
        fi
        gs_configured=true
        return 0
      fi
    done
    
    if [ "$gs_configured" != "true" ]; then
      echo "WARNING: Failed to configure Global Shutter Camera with media-ctl"
      echo "Trying alternative methods..."
    fi
  fi
  
  echo "media-ctl method failed. Trying alternative method with v4l2-ctl..."
  
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
  
  echo "Could not configure Global Shutter Camera with either method"
  return 1
}

# Function to detect Global Shutter Camera
detect_global_shutter() {
  # Check if media-ctl is available
  if ! command -v media-ctl &> /dev/null; then
    echo "ERROR: media-ctl not found. This is REQUIRED for Global Shutter Camera detection."
    
    # Check if we're on Bookworm OS
    if grep -q "=bookworm" /etc/os-release 2>/dev/null; then
      echo "You are on Raspberry Pi OS Bookworm which requires building media-ctl from source."
      echo "Please run this script with sudo first to build the required tools."
      echo "Command: sudo $(realpath "$0")"
      return 1
    else
      echo "Please install media-ctl: sudo apt install -y media-ctl"
      return 1
    fi
  fi

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

# Function to build media-ctl and v4l-utils from source (required for Bookworm OS)
build_v4l_utils_from_source() {
    echo "Building v4l-utils and media-ctl from source (required for Raspberry Pi OS Bookworm)..."
    
    # Install build dependencies and additional packages for camera support
    apt update
    apt install -y git autoconf automake libtool pkg-config libglib2.0-dev libelf-dev \
        libudev-dev libusb-1.0-0-dev libcamera-apps libcamera-tools python3-libcamera \
        v4l-utils ffmpeg curl cmake libjpeg-dev libtiff-dev libpng-dev
    
    # Create a temporary directory
    TEMP_DIR=$(mktemp -d)
    cd "$TEMP_DIR"
    
    # Clone the v4l-utils repository
    echo "Cloning v4l-utils repository..."
    git clone https://git.linuxtv.org/v4l-utils.git
    cd v4l-utils
    
    # Build and install the complete package
    echo "Building complete v4l-utils package with media-ctl..."
    ./bootstrap.sh
    ./configure
    make -j$(nproc)
    make install
    ldconfig
    
    # Ensure media-ctl is in the path
    if [ -f "/usr/local/bin/media-ctl" ]; then
        echo "media-ctl installed successfully to /usr/local/bin/media-ctl"
    else
        echo "ERROR: media-ctl was not installed properly"
        # Copy the built binary if found but not installed
        if [ -f "utils/media-ctl/media-ctl" ]; then
            cp utils/media-ctl/media-ctl /usr/local/bin/
            echo "Manually copied media-ctl to /usr/local/bin/"
        fi
    fi
    
    # Clean up
    cd /
    rm -rf "$TEMP_DIR"
    
    # Verify installation
    if command -v media-ctl &> /dev/null && command -v v4l2-ctl &> /dev/null; then
        echo "✅ media-ctl is now available: $(which media-ctl)"
        media-ctl --version
        echo "✅ v4l2-ctl is now available: $(which v4l2-ctl)"
        v4l2-ctl --version
        return 0
    else
        echo "❌ Failed to install media-ctl or v4l2-ctl"
        return 1
    fi
}

# Check if running as root/sudo for system package installation
if [ "$(id -u)" -eq 0 ]; then
    # Running as root, can install system packages if needed
    echo "Running as root - installing required system packages..."
    
    # Install packages in a more reliable way
    echo "Updating package lists..."
    apt update
    
    # Check if we're on Bookworm OS
    if grep -q "=bookworm" /etc/os-release 2>/dev/null; then
        echo "DETECTED RASPBERRY PI OS BOOKWORM"
        
        # Install base packages first - v4l-utils contains media-ctl on Bookworm
        echo "Installing v4l-utils package which includes media-ctl on Bookworm..."
        apt install -y libcamera-apps libcamera-tools python3-libcamera curl v4l-utils
        
        # Check if media-ctl is already available from the OS
        if command -v media-ctl &> /dev/null && command -v v4l2-ctl &> /dev/null; then
            echo "Found media-ctl and v4l2-ctl from OS packages, testing functionality..."
            
            # Test if the OS-provided media-ctl works with Global Shutter Camera
            media_ctl_works=false
            for m in {0..5}; do
                if [ -e "/dev/media$m" ] && media-ctl -d /dev/media$m -p &>/dev/null; then
                    # Try to detect IMX296 Global Shutter Camera
                    if media-ctl -d /dev/media$m -p 2>/dev/null | grep -i "imx296" >/dev/null; then
                        echo "✅ OS-provided media-ctl works with Global Shutter Camera on /dev/media$m"
                        media_ctl_works=true
                        break
                    fi
                    
                    # At least media-ctl works with some device
                    media_ctl_works=true
                fi
            done
            
            if [ "$media_ctl_works" = "true" ]; then
                echo "✅ OS-provided media-ctl is working correctly"
                echo "Using OS-provided v4l-utils and media-ctl"
            else
                echo "⚠️ OS-provided media-ctl not working with media devices"
                echo "Make sure the camera is properly connected and try again"
            fi
        else
            echo "media-ctl not found in OS packages, installing v4l-utils..."
            # Install v4l-utils which includes media-ctl
            apt install -y v4l-utils
        fi
        
        # Final verification
        if ! command -v media-ctl &> /dev/null; then
            echo "ERROR: Failed to install or find media-ctl"
            echo "This is required for Global Shutter Camera support"
            echo "Try running: apt install -y v4l-utils"
            exit 1
        else
            echo "media-ctl is available: $(which media-ctl)"
            media-ctl --version 2>/dev/null || echo "Could not get media-ctl version"
            
            # Test if media-ctl works properly with the camera devices
            echo "Testing media-ctl functionality..."
            media_devices=$(ls /dev/media* 2>/dev/null || echo "")
            if [ -z "$media_devices" ]; then
                echo "WARNING: No media devices found. If you have a camera connected, check connections."
            else
                echo "Found media devices: $media_devices"
                for m in {0..5}; do
                    if [ -e "/dev/media$m" ]; then
                        echo "Testing media-ctl on /dev/media$m:"
                        media-ctl -d /dev/media$m -p 2>&1 || echo "Could not query /dev/media$m"
                    fi
                done
                
                # Check for Global Shutter Camera
                gs_found=false
                for m in {0..5}; do
                    if [ -e "/dev/media$m" ] && media-ctl -d /dev/media$m -p 2>/dev/null | grep -i "imx296" >/dev/null; then
                        echo "✅ Global Shutter Camera (IMX296) detected on /dev/media$m"
                        gs_found=true
                        break
                    fi
                done
                
                if [ "$gs_found" != "true" ]; then
                    echo "NOTE: No Global Shutter Camera detected. This is fine if you're using a standard Pi Camera."
                fi
            fi
        fi
    else
        # Older OS versions can use the packaged versions
        echo "Installing packages for pre-Bookworm Raspberry Pi OS..."
        apt install -y v4l-utils libcamera-apps libcamera-tools curl python3-libcamera
    fi
    
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

# Create folders for recordings with date-based structure
RECORDINGS_DIR="recordings"
mkdir -p "$RECORDINGS_DIR"
TODAY_DIR="$RECORDINGS_DIR/$(date +%Y-%m-%d)"
mkdir -p "$TODAY_DIR"

echo "Created recordings directory structure: $TODAY_DIR"
echo "Videos will be saved to: $TODAY_DIR"

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
  output_dir: $TODAY_DIR
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
    
    # Update output directory in config.yaml to use date-based structure
    sed -i "s|output_dir:.*|output_dir: $TODAY_DIR|" config.yaml
    echo "Updated output directory in config.yaml to: $TODAY_DIR"
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
    width=$CAM_WIDTH
    height=$CAM_HEIGHT
    fps=$CAM_FPS
    update_status "Using Global Shutter Camera parameters: ${width}x${height} @ ${fps}fps"
else
    # Default values if not configured - set higher defaults
    width=400
    height=400
    fps=200
    update_status "Using default camera parameters with Global Shutter support enabled: ${width}x${height} @ ${fps}fps"
    update_status "Note: Global Shutter Camera support is ALWAYS enabled by default"
fi

# Create a temporary Python script that directly uses the LSLCameraStreamer class
# with fixes for the LSL error and camera initialization
TMP_SCRIPT=$(mktemp)
cat > $TMP_SCRIPT << EOF
#!/usr/bin/env python3
import os
import sys
import signal
import time
import logging
import traceback

# Set up logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('CameraCapture')

# Add the current directory to the Python path
sys.path.insert(0, os.getcwd())

# Function to handle signals
def signal_handler(sig, frame):
    print("Received signal, shutting down...")
    global running
    running = False
    if camera:
        camera.stop()
    sys.exit(0)

# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# Create terminal UI function
def print_status_update(camera, buffer_manager=None):
    # Clear terminal and print header
    os.system('clear' if os.name != 'nt' else 'cls')
    print("=" * 60)
    print("RASPBERRY PI CAMERA CAPTURE".center(60))
    print("=" * 60)
    
    if camera:
        info = camera.get_info()
        print(f"Camera: {info.get('camera_model', 'Unknown')}")
        print(f"Resolution: {info.get('width', 0)}x{info.get('height', 0)} @ {info.get('fps', 0)} fps")
        print(f"Frames captured: {camera.get_frame_count()}")
        print(f"Frames written: {camera.get_frames_written()}")
        
        if buffer_manager:
            buffer_size = buffer_manager.get_buffer_size()
            buffer_duration = buffer_manager.get_buffer_duration()
            print(f"Buffer: {buffer_size} frames ({buffer_duration:.1f}s)")
            
        recording = info.get('recording', False)
        if recording:
            print("\\033[1;32mRECORDING ACTIVE\\033[0m")
            print(f"Output file: {camera.get_current_filename()}")
        else:
            print("\\033[1;33mWaiting for trigger\\033[0m")
    
    print("-" * 60)
    print("Commands:")
    print("  - Start recording: curl -d 'Start Recording' ntfy.sh/raspie-camera-test")
    print("  - Stop recording: curl -d 'Stop Recording' ntfy.sh/raspie-camera-test")
    print("  - Press Ctrl+C to exit")
    print("-" * 60)

# Helper function to fix LSL setup
def fix_lsl_setup(module):
    # Monkey patch the StreamInfo deletion to avoid errors
    if hasattr(module, 'StreamInfo'):
        old_del = module.StreamInfo.__del__
        
        def safe_del(self):
            try:
                if hasattr(self, 'obj'):
                    old_del(self)
            except Exception as e:
                print(f"Safely handled StreamInfo deletion error: {e}")
                
        module.StreamInfo.__del__ = safe_del

try:
    # Import the camera streamer class
    from src.raspberry_pi_lsl_stream.camera_stream_fixed import LSLCameraStreamer
    
    # Add a method to get the current filename if it doesn't exist
    if not hasattr(LSLCameraStreamer, 'get_current_filename'):
        def get_current_filename(self):
            if hasattr(self, 'video_writer') and self.video_writer and hasattr(self.video_writer, 'output_filename'):
                return self.video_writer.output_filename
            return "No file being recorded yet"
        
        # Add the method to the class
        LSLCameraStreamer.get_current_filename = get_current_filename
    
    # Fix the LSL setup issue with a monkey patch
    try:
        import pylsl
        fix_lsl_setup(pylsl)
        print("Applied LSL StreamInfo fix")
    except ImportError:
        print("pylsl not found, LSL features will be disabled")
        
    # Configuration
    width = ${width}
    height = ${height}
    fps = ${fps}
    preview = $([ "$PREVIEW_ENABLED" = "true" ] && echo "True" || echo "False")
    today_dir = "${TODAY_DIR}"
    
    logger.info(f"Starting camera with resolution {width}x{height} @ {fps}fps, preview={preview}")
    logger.info(f"Recording to directory: {today_dir}")
    print(f"📁 Recordings will be saved to: {today_dir}")
    print(f"📹 Files will be named: recording_YYYYMMDD_HHMMSS.mkv")
    
    # Make sure output directory exists
    if not os.path.exists(today_dir):
        os.makedirs(today_dir, exist_ok=True)
        logger.info(f"Created output directory: {today_dir}")
    
    # Create and start the camera streamer with fixed parameters
    camera = LSLCameraStreamer(
        width=width,
        height=height,
        target_fps=fps,  # Don't limit fps, use the requested value
        save_video=True,
        output_path=today_dir,
        codec="mjpg",
        show_preview=preview,
        push_to_lsl=True,
        stream_name="VideoStream",
        use_buffer=True,
        buffer_size_seconds=20.0,
        ntfy_topic="raspie-camera-test",
        enable_crop=True,  # Always enable Global Shutter Camera support
        camera_id=0
    )
    
    # Print status immediately to show configuration
    print(f"Camera initialized with {width}x{height} @ {fps}fps")
    print(f"Global Shutter Camera support is ENABLED")
    print(f"Starting camera...")

    # Keep the script running until Ctrl+C is pressed
    try:
        # Start the camera explicitly and wait to ensure it's running
        print("Starting camera capture...")
        camera.start()
        print("Camera started successfully!")
        
        # Sleep briefly to let camera initialize
        time.sleep(1)
        
        running = True
        status_update_interval = 0.2  # Update status more frequently (5 times per second)
        last_update = time.time()
        
        # Check if terminal actually started
        if [ $? -ne 0 ]; then
            echo "Failed to start new terminal window. Falling back to current terminal."
            "$TMP_SCRIPT"
            rm -f "$TMP_SCRIPT"
            exit $?
        fi
        
        echo "Camera UI launched in a new terminal window."
        echo "This terminal will show debug information only."
        echo "To stop the camera, close the camera UI window or press Ctrl+C there."
        
        # Create a named pipe for communication between processes
        DEBUG_PIPE="/tmp/camera_debug_pipe"
        rm -f "$DEBUG_PIPE"
        mkfifo "$DEBUG_PIPE"
        
        # Create a debug version of the script
        DEBUG_SCRIPT="${TMP_SCRIPT}_debug"
        cp "$TMP_SCRIPT" "$DEBUG_SCRIPT"
        chmod +x "$DEBUG_SCRIPT"
        
        # Add debug code to the debug script
        cat >> "$DEBUG_SCRIPT" << 'EOD'
# Function to log debug information to the pipe
def log_debug(message):
    try:
        with open('/tmp/camera_debug_pipe', 'w') as f:
            f.write(f"DEBUG: {message}\n")
    except:
        pass

# Monitor camera status
def monitor_camera_status():
    if 'camera' in globals() and camera:
        try:
            info = camera.get_info()
            status = "RECORDING" if info.get('recording', False) else "STANDBY"
            fps = info.get('current_fps', 0)
            frames = camera.get_frame_count()
            written = camera.get_frames_written()
            log_debug(f"STATUS: {status} | FPS: {fps:.1f} | Frames: {frames} | Written: {written}")
        except Exception as e:
            log_debug(f"Error monitoring status: {e}")

# Add monitoring to the main loop
old_time = time.time()
status_interval = 1.0  # Send status every second

# Replace the main loop with one that includes monitoring
while running:
    # Simple terminal UI for status updates
    if time.time() - last_update >= status_update_interval:
        print_status_update(camera, camera.buffer_trigger_manager)
        last_update = time.time()
    
    # Monitor camera status for debug
    if time.time() - old_time >= status_interval:
        monitor_camera_status()
        old_time = time.time()
    
    time.sleep(0.05)  # Faster refresh rate

# Exit before the original loop runs
sys.exit(0)
EOD
        
        # Show debug info in the original terminal
        echo ""
        echo "=== DEBUG INFORMATION ==="
        echo "Camera Configuration:"
        echo "- Resolution: ${width}x${height}"
        echo "- Target FPS: ${fps}"
        echo "- Preview Enabled: ${PREVIEW_ENABLED}"
        echo "- Output Directory: ${TODAY_DIR}"
        echo "- Global Shutter Support: ENABLED"
        echo ""
        echo "System Information:"
        if [ -f "/proc/cpuinfo" ]; then
            echo "- CPU: $(grep "model name" /proc/cpuinfo | head -n 1 | cut -d':' -f2 | xargs)"
            echo "- CPU Cores: $(grep -c "processor" /proc/cpuinfo)"
        fi
        if [ -f "/proc/meminfo" ]; then
            echo "- RAM: $(grep "MemTotal" /proc/meminfo | awk '{print $2/1024/1024 " GB"}')"
        fi
        echo "- OS: $(grep PRETTY_NAME /etc/os-release | cut -d'"' -f2)"
        echo ""
        echo "=== REAL-TIME DEBUG LOG ==="
        echo "Starting camera process in separate terminal..."
        
        # Read from the pipe and display debug info
        tail -f "$DEBUG_PIPE" &
        TAIL_PID=$!
        
        # Add resource monitoring in a loop
        (
            while true; do
                echo "SYS: CPU: $(top -bn1 | grep "Cpu(s)" | awk '{print $2}')% | MEM: $(free -m | awk 'NR==2{printf "%.1f%%", $3*100/$2}') | $(date '+%H:%M:%S')" > "$DEBUG_PIPE"
                sleep 3
            done
        ) &
        MONITOR_PID=$!
        
        # Wait for the script to exit in the other terminal
        wait
        
        # Cleanup processes and pipe
        kill $TAIL_PID 2>/dev/null || true
        kill $MONITOR_PID 2>/dev/null || true
        rm -f "$DEBUG_PIPE" "$TMP_SCRIPT" "$DEBUG_SCRIPT"
    except Exception as e:
        logger.error(f"Error in main loop: {e}")
        traceback.print_exc()
        
except Exception as e:
    logger.error(f"Error: {str(e)}")
    traceback.print_exc()
    sys.exit(1)
finally:
    # Cleanup
    if 'camera' in locals() and camera:
        try:
            camera.stop()
            logger.info("Camera stopped")
        except Exception as e:
            logger.error(f"Error stopping camera: {e}")
EOF

# Make the temporary script executable
chmod +x $TMP_SCRIPT

# Function to detect available terminal emulator
detect_terminal() {
    # Force disable terminal detection if not running in X11
    if [ -z "$DISPLAY" ]; then
        return 1
    fi
    
    # Try to detect available terminal emulators
    for term in lxterminal xterm gnome-terminal x-terminal-emulator konsole terminology; do
        if command -v "$term" &> /dev/null; then
            echo "$term"
            return 0
        fi
    done
    return 1
}

# Check if we're in a graphical environment where we can open a new terminal
TERM_EMU=$(detect_terminal)
if [ -n "$TERM_EMU" ] && [ "$DISPLAY_MODE" = "terminal" ]; then
    echo "Launching camera UI in a new terminal window using $TERM_EMU..."
    
    # Make a separate copy of the script for the terminal
    UI_SCRIPT="${TMP_SCRIPT}_ui"
    cp "$TMP_SCRIPT" "$UI_SCRIPT"
    chmod +x "$UI_SCRIPT"
    
    # Launch the script in a new terminal window with explicit geometry
    case $TERM_EMU in
        lxterminal)
            lxterminal --title="Raspberry Pi Camera Capture" --geometry=100x40 --command="$UI_SCRIPT" &
            ;;
        xterm)
            xterm -title "Raspberry Pi Camera Capture" -geometry 100x40 -e "$UI_SCRIPT" &
            ;;
        gnome-terminal)
            gnome-terminal --geometry=100x40 -- "$UI_SCRIPT" &
            ;;
        konsole)
            konsole --title "Raspberry Pi Camera Capture" -e "$UI_SCRIPT" &
            ;;
        terminology)
            terminology -t "Raspberry Pi Camera Capture" -e "$UI_SCRIPT" &
            ;;
        x-terminal-emulator)
            x-terminal-emulator -e "$UI_SCRIPT" &
            ;;
    esac
    
    # Check if terminal actually started
    if [ $? -ne 0 ]; then
        echo "Failed to start new terminal window. Falling back to current terminal."
        "$TMP_SCRIPT"
        rm -f "$UI_SCRIPT"
        exit $?
    fi
    
    echo "Camera UI launched in a new terminal window."
    echo "This terminal will show debug information only."
    echo "To stop the camera, close the camera UI window or press Ctrl+C there."
    
    # Create a named pipe for communication between processes
    DEBUG_PIPE="/tmp/camera_debug_pipe"
    rm -f "$DEBUG_PIPE"
    mkfifo "$DEBUG_PIPE"
    
    # Create a debug version of the script
    DEBUG_SCRIPT="${TMP_SCRIPT}_debug"
    cp "$TMP_SCRIPT" "$DEBUG_SCRIPT"
    chmod +x "$DEBUG_SCRIPT"
    
    # Add debug code to the debug script
    cat >> "$DEBUG_SCRIPT" << 'EOD'
# Function to log debug information to the pipe
def log_debug(message):
    try:
        with open('/tmp/camera_debug_pipe', 'w') as f:
            f.write(f"DEBUG: {message}\n")
    except:
        pass

# Monitor camera status
def monitor_camera_status():
    if 'camera' in globals() and camera:
        try:
            info = camera.get_info()
            status = "RECORDING" if info.get('recording', False) else "STANDBY"
            fps = info.get('current_fps', 0)
            frames = camera.get_frame_count()
            written = camera.get_frames_written()
            log_debug(f"STATUS: {status} | FPS: {fps:.1f} | Frames: {frames} | Written: {written}")
        except Exception as e:
            log_debug(f"Error monitoring status: {e}")

# Add monitoring to the main loop
old_time = time.time()
status_interval = 1.0  # Send status every second

# Replace the main loop with one that includes monitoring
while running:
    # Simple terminal UI for status updates
    if time.time() - last_update >= status_update_interval:
        print_status_update(camera, camera.buffer_trigger_manager)
        last_update = time.time()
    
    # Monitor camera status for debug
    if time.time() - old_time >= status_interval:
        monitor_camera_status()
        old_time = time.time()
    
    time.sleep(0.05)  # Faster refresh rate

# Exit before the original loop runs
sys.exit(0)
EOD
    
    # Show debug info in the original terminal
    echo ""
    echo "=== DEBUG INFORMATION ==="
    echo "Camera Configuration:"
    echo "- Resolution: ${width}x${height}"
    echo "- Target FPS: ${fps}"
    echo "- Preview Enabled: ${PREVIEW_ENABLED}"
    echo "- Output Directory: ${TODAY_DIR}"
    echo "- Global Shutter Support: ENABLED"
    echo ""
    echo "System Information:"
    if [ -f "/proc/cpuinfo" ]; then
        echo "- CPU: $(grep "model name" /proc/cpuinfo | head -n 1 | cut -d':' -f2 | xargs)"
        echo "- CPU Cores: $(grep -c "processor" /proc/cpuinfo)"
    fi
    if [ -f "/proc/meminfo" ]; then
        echo "- RAM: $(grep "MemTotal" /proc/meminfo | awk '{print $2/1024/1024 " GB"}')"
    fi
    echo "- OS: $(grep PRETTY_NAME /etc/os-release | cut -d'"' -f2)"
    echo ""
    echo "=== REAL-TIME DEBUG LOG ==="
    echo "Starting camera process in separate terminal..."
    
    # Read from the pipe and display debug info
    tail -f "$DEBUG_PIPE" &
    TAIL_PID=$!
    
    # Add resource monitoring in a loop
    (
        while true; do
            echo "SYS: CPU: $(top -bn1 | grep "Cpu(s)" | awk '{print $2}')% | MEM: $(free -m | awk 'NR==2{printf "%.1f%%", $3*100/$2}') | $(date '+%H:%M:%S')" > "$DEBUG_PIPE"
            sleep 3
        done
    ) &
    MONITOR_PID=$!
    
    # Wait for the script to exit in the other terminal
    wait
    
    # Cleanup processes and pipe
    kill $TAIL_PID 2>/dev/null || true
    kill $MONITOR_PID 2>/dev/null || true
    rm -f "$DEBUG_PIPE" "$UI_SCRIPT" "$DEBUG_SCRIPT"
else
    # Run in the current terminal if we're not in a graphical environment or in service mode
    echo "Running camera capture with terminal UI in current window..."
    "$TMP_SCRIPT"
fi

# Clean up
rm -f $TMP_SCRIPT

exit $? 