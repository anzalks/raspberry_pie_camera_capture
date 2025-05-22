#!/bin/bash

# Setup script for Raspberry Pi LSL Camera Streamer System Dependencies
# 
# IMPORTANT:
# 1. Run this script with sudo:   sudo bash setup_pi.sh
# 2. Review the script before running.
# 3. A reboot might be required after running this script for camera changes.
# 4. This script installs SYSTEM packages. Python package installation
#    should be done AFTER this script, inside a virtual environment.

# --- Error Handling --- 
set -e # Exit immediately if a command exits with a non-zero status.

# --- Check if running as root --- 
if [ "$(id -u)" -ne 0 ]; then
  echo "This script must be run as root (use sudo). Exiting." >&2
  exit 1
fi

echo "Updating package list..."
apt update

echo "Installing required system packages (including build tools, python3-dev, picamera2, and potentially useful extras)..."
# Install packages one by one to reduce memory usage
echo "Installing packages one by one to minimize memory usage..."
for pkg in build-essential python3-dev python3-pip python3-venv python3-opencv python3-picamera2 python3-yaml \
    libatlas-base-dev libhdf5-dev libhdf5-serial-dev libopenjp2-7 exfat-fuse exfatprogs ntfs-3g \
    libcamera-dev gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gstreamer1.0-libav curl \
    autoconf libtool pkg-config libbsd-dev libasound2-dev portaudio19-dev; do
    echo "Installing $pkg..."
    apt install -y --no-install-recommends $pkg
    # Sleep briefly to allow system to recover between installations
    sleep 2
done

# Separate numpy and scipy installation to prevent memory issues
echo "Installing python3-numpy..."
apt install -y --no-install-recommends python3-numpy
sleep 2
echo "Installing python3-scipy..."
apt install -y --no-install-recommends python3-scipy
sleep 2

echo "Attempting to install liblsl-dev (LabStreamingLayer library) via apt..."
if apt install -y liblsl-dev; then
  echo "liblsl-dev installed successfully via apt."
else
  echo "apt install liblsl-dev failed. Attempting to build from source..."
  # Install build dependencies for liblsl
  echo "Installing build dependencies for liblsl (cmake, build-essential)..."
  apt install -y cmake build-essential
  
  echo "Cloning liblsl repository..."
  # Store current directory and go to home for cloning
  ORIG_DIR=$(pwd)
  cd ~
  # Remove existing directory if present
  if [ -d "liblsl" ]; then 
      echo "Removing existing liblsl directory..."
      rm -rf liblsl 
  fi
  git clone https://github.com/sccn/liblsl.git
  cd liblsl

  echo "Configuring liblsl build with CMake..."
  mkdir -p build # Ensure build directory exists
  cd build
  cmake ..

  echo "Compiling liblsl (this may take a while)..."
  make

  echo "Installing compiled liblsl..."
  make install

  echo "Updating shared library cache..."
  ldconfig

  echo "liblsl successfully built and installed from source."
  # Return to original directory
  cd "$ORIG_DIR"
fi

# --- Install other dependencies ---

echo "Installing libcap-dev (needed for python-prctl, a picamera2 dependency)..."
apt install -y libcap-dev

echo "Installing libcamera-apps (useful for testing and ensuring libcamera stack is present)..."
apt install -y libcamera-apps

# --- Install curlftpfs (Try apt first, fallback to source) ---
echo "Checking for curlftpfs..."

# Attempt to install via apt first
echo "Attempting to install curlftpfs via apt..."
if apt install -y curlftpfs; then
    echo "curlftpfs installed successfully via apt."
else
    echo "apt install curlftpfs failed or package not available."
    # Check if command exists anyway (might have been installed previously)
    if command -v curlftpfs >/dev/null 2>&1; then
        echo "curlftpfs command found, likely installed previously. Skipping build."
    else
        echo "curlftpfs command not found. Attempting to build from source..."
        
        # Install build dependencies for curlftpfs
        echo "Installing build dependencies for curlftpfs (check output for errors)..."
        # Added libglib2.0-dev as required by the fork's README/configure checks
        # Added libbsd-dev based on configure error
        apt install -y build-essential pkg-config autoconf automake libtool libfuse-dev libcurl4-openssl-dev libglib2.0-dev libbsd-dev
        # Note: libfuse-dev might be fuse3-dev on newer systems.
        # Note: libcurl4-openssl-dev might be libcurl4-gnutls-dev.
        # If the above fails, you may need to find the correct dev package names.

        # Define build directory and repo URL
        BUILD_DIR="/tmp/curlftpfs_build"
        REPO_URL="https://github.com/JackSlateur/curlftpfs.git"
        ORIG_DIR=$(pwd) # Remember where we started

        echo "Creating temporary build directory: ${BUILD_DIR}"
        rm -rf "${BUILD_DIR}" # Clean previous attempts
        mkdir -p "${BUILD_DIR}"
        cd "${BUILD_DIR}"

        echo "Cloning curlftpfs source from ${REPO_URL}..."
        if git clone "${REPO_URL}" curlftpfs_src; then
            cd curlftpfs_src
            echo "Running autoreconf to generate configure script..."
            if autoreconf -fi; then
                echo "Running configure script..."
                if ./configure; then
                    echo "Configuration successful. Compiling (make)..."
                    if make; then
                        echo "Compilation successful. Installing (make install)..."
                        # Run install as root since we are in a sudo script
                        if make install; then
                            echo "curlftpfs successfully built and installed from source."
                        else
                            echo "ERROR: 'make install' failed." >&2
                        fi
                    else
                        echo "ERROR: 'make' failed." >&2
                    fi
                else
                    echo "ERROR: './configure' failed. Check dependencies were installed correctly." >&2
                fi
            else
                 echo "ERROR: 'autoreconf -fi' failed. Check build dependencies." >&2
            fi
            # Go back to parent build dir before cleanup
            cd .. 
        else
            echo "ERROR: Failed to clone curlftpfs source from GitHub." >&2
        fi
        
        # Cleanup build directory
        echo "Cleaning up build directory: ${BUILD_DIR}"
        cd "${ORIG_DIR}" # Go back to original directory first
        rm -rf "${BUILD_DIR}"

        # Final check if command exists after build attempt
        if ! command -v curlftpfs >/dev/null 2>&1; then
            echo "WARNING: curlftpfs build attempt finished, but command is still not found." >&2
        fi
    fi
fi

# --- Python Virtual Environment and Project Installation ---

echo "Attempting to set up Python virtual environment and install project..."

# Check if running via sudo and get the original user
if [ -z "$SUDO_USER" ]; then
  echo "Warning: SUDO_USER variable not set. Cannot determine original user."
  echo "Python environment setup will be skipped. Please run Phase 2 manually (see README)."
else
  echo "Running Python setup steps as user: $SUDO_USER"
  
  # Define the virtual environment path relative to the script's assumed location
  # This assumes the script is run from the project root directory
  VENV_DIR=".venv"
  PROJECT_DIR=$(pwd) # Assuming the script is run from the project root

  echo "Creating virtual environment in '$PROJECT_DIR/$VENV_DIR'..."
  # Check if the venv directory already exists
  if [ -d "$VENV_DIR" ]; then
      echo "Virtual environment '$VENV_DIR' already exists. Skipping creation."
  else
      # Create the venv as the original user only if it doesn't exist
      sudo -u "$SUDO_USER" python3 -m venv --system-site-packages "$VENV_DIR"
      if [ $? -eq 0 ]; then
          echo "Virtual environment created successfully."
      else
          echo "ERROR: Failed to create virtual environment."
          # Exit or handle error appropriately if needed
          exit 1 # Exit if venv creation fails
      fi
  fi
  
  # Now proceed with checks and installation assuming venv exists or was just created
  if [ ! -f "$VENV_DIR/bin/activate" ]; then
      echo "ERROR: Virtual environment activation script not found at '$VENV_DIR/bin/activate'."
      echo "Cannot proceed with Python package installation."
  else
      # MEMORY-EFFICIENT APPROACH: Install packages one by one with pauses
      echo "Using memory-efficient approach to install packages..."
      
      # Upgrade pip separately
      echo "Upgrading pip..."
      sudo -u "$SUDO_USER" "$VENV_DIR/bin/pip" install --upgrade pip
      sleep 2
      
      # Upgrade setuptools separately
      echo "Upgrading setuptools..."
      sudo -u "$SUDO_USER" "$VENV_DIR/bin/pip" install --upgrade setuptools
      sleep 2
      
      # Upgrade wheel separately
      echo "Upgrading wheel..."
      sudo -u "$SUDO_USER" "$VENV_DIR/bin/pip" install --upgrade wheel
      sleep 2
      
      # Install PyYAML
      echo "Installing PyYAML..."
      sudo -u "$SUDO_USER" "$VENV_DIR/bin/pip" install pyyaml
      sleep 2
      
      # Install core dependencies one by one to minimize memory usage
      echo "Installing numpy..."
      sudo -u "$SUDO_USER" "$VENV_DIR/bin/pip" install numpy
      sleep 3
      
      echo "Installing OpenCV (headless version)..."
      sudo -u "$SUDO_USER" "$VENV_DIR/bin/pip" install opencv-python-headless
      sleep 3
      
      echo "Installing pylsl..."
      sudo -u "$SUDO_USER" "$VENV_DIR/bin/pip" install pylsl
      sleep 3
      
      echo "Installing additional dependencies..."
      sudo -u "$SUDO_USER" "$VENV_DIR/bin/pip" install requests
      sleep 2
      sudo -u "$SUDO_USER" "$VENV_DIR/bin/pip" install ntfy
      sleep 2
      sudo -u "$SUDO_USER" "$VENV_DIR/bin/pip" install psutil
      sleep 2
      
      echo "Installing project 'raspberry-pi-lsl-stream' in editable mode with reduced memory usage..."
      # Install the project itself as the original user
      # Use --no-build-isolation to reduce memory requirements
      cd "$PROJECT_DIR"
      sudo -u "$SUDO_USER" "$VENV_DIR/bin/pip" install -e . --no-build-isolation
      
      if [ $? -eq 0 ]; then
          echo "Project installed successfully into the virtual environment."
      else
          echo "ERROR: Failed to install project using pip."
          echo "If you're still experiencing memory issues, try installing dependencies manually one by one."
          echo "Example: .venv/bin/pip install numpy && .venv/bin/pip install opencv-python-headless && .venv/bin/pip install pylsl"
      fi
  fi
fi

# --- Create default configuration file ---
echo "Creating default configuration file..."
CONFIG_FILE="$PROJECT_DIR/config.yaml"

if [ -f "$CONFIG_FILE" ]; then
    echo "Configuration file already exists. Backing up existing file..."
    cp "$CONFIG_FILE" "$CONFIG_FILE.bak"
fi

# Create the default configuration file
cat << EOF > "$CONFIG_FILE"
# Raspberry Pi Camera Capture Configuration

# Camera settings
camera:
  width: 400
  height: 400
  fps: 100
  codec: mjpg
  container: mkv
  preview: true  # Changed to true to enable preview
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

# Audio settings
audio:
  sample_rate: 44100
  channels: 1
  bit_depth: 16
  save_audio: true
  audio_format: wav
  show_preview: false
EOF

# Set appropriate permissions
chown $SUDO_USER:$SUDO_USER "$CONFIG_FILE"
echo "Default configuration file created at $CONFIG_FILE"

# --- Setup Camera Permissions ---
echo "Setting up camera permissions and dependencies..."

# Ensure v4l-utils is installed for camera debugging
echo "Installing v4l-utils for camera debugging capabilities..."
apt install -y v4l-utils

# Ensure media-ctl and libcamera-apps are installed (critical for Global Shutter Camera)
echo "Installing media-ctl and libcamera-apps (required for camera operation)..."
apt install -y libcamera-apps libcamera-tools

# Set camera group permissions to allow non-root access
echo "Setting camera group permissions..."
if getent group video > /dev/null; then
    # Add user to the video group for camera access
    usermod -a -G video $SUDO_USER
    echo "Added $SUDO_USER to the video group for camera access"
fi

if getent group input > /dev/null; then
    # Add user to the input group for camera access
    usermod -a -G input $SUDO_USER
    echo "Added $SUDO_USER to the input group for camera access"
fi

# Create and set up camera lock file with proper permissions
echo "Setting up camera lock file with proper permissions..."
rm -f /tmp/raspie_camera.lock
touch /tmp/raspie_camera.lock
chmod 666 /tmp/raspie_camera.lock
echo "Camera lock file created with proper permissions"

# --- Automatic Service Installation ---
echo "Installing camera capture service to start automatically at boot..."

# Check if the service file already exists
if [ -f "/etc/systemd/system/raspie-capture.service" ]; then
    echo "Service file already exists. Reinstalling..."
    # Stop the service if it's running
    systemctl stop raspie-capture.service 2>/dev/null || true
fi

# Use the raspie-capture-service.sh script if it exists
if [ -f "$PROJECT_DIR/raspie-capture-service.sh" ]; then
    echo "Running service installation script..."
    bash "$PROJECT_DIR/raspie-capture-service.sh"
else
    echo "WARNING: raspie-capture-service.sh not found. Creating service directly..."
    
    # Create the systemd service file
    cat << EOF > "/etc/systemd/system/raspie-capture.service"
[Unit]
Description=Raspberry Pi Audio/Video Capture Service
After=network.target

[Service]
Type=simple
User=$SUDO_USER
WorkingDirectory=$PROJECT_DIR
ExecStart=$PROJECT_DIR/$VENV_DIR/bin/python -m src.raspberry_pi_lsl_stream.camera_capture --config $CONFIG_FILE
Environment="PATH=$PROJECT_DIR/$VENV_DIR/bin:/usr/local/bin:/usr/bin:/bin"
StandardOutput=journal+console
StandardError=journal+console
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
EOF

    # Set appropriate permissions
    chmod 644 "/etc/systemd/system/raspie-capture.service"

    # Create management script
    cat << 'EOF' > "$PROJECT_DIR/raspie-service.sh"
#!/bin/bash

# Define colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Function to check if the service is running
check_status() {
    status=$(systemctl is-active raspie-capture.service)
    if [ "$status" = "active" ]; then
        echo -e "${GREEN}Capture service is running.${NC}"
    else
        echo -e "${RED}Capture service is not running.${NC}"
    fi
    
    # Show detailed status
    echo -e "${YELLOW}Detailed status:${NC}"
    systemctl status raspie-capture.service
}

# Main command processing
case "$1" in
    start)
        echo -e "${GREEN}Starting capture service...${NC}"
        sudo systemctl start raspie-capture.service
        check_status
        ;;
    stop)
        echo -e "${YELLOW}Stopping capture service...${NC}"
        sudo systemctl stop raspie-capture.service
        check_status
        ;;
    restart)
        echo -e "${YELLOW}Restarting capture service...${NC}"
        sudo systemctl restart raspie-capture.service
        check_status
        ;;
    status)
        check_status
        ;;
    logs)
        echo -e "${GREEN}Showing logs:${NC}"
        sudo journalctl -u raspie-capture.service -f
        ;;
    enable)
        echo -e "${GREEN}Enabling capture service to start on boot...${NC}"
        sudo systemctl enable raspie-capture.service
        echo -e "${GREEN}Service will now start automatically on boot.${NC}"
        ;;
    disable)
        echo -e "${YELLOW}Disabling capture service from starting on boot...${NC}"
        sudo systemctl disable raspie-capture.service
        echo -e "${YELLOW}Service will no longer start automatically on boot.${NC}"
        ;;
    trigger)
        echo -e "${GREEN}Sending start trigger notification...${NC}"
        # Read topic from config.yaml if possible
        if command -v python3 > /dev/null && [ -f "$PROJECT_DIR/config.yaml" ]; then
            ntfy_topic=$(python3 -c "import yaml; print(yaml.safe_load(open('$PROJECT_DIR/config.yaml', 'r'))['remote']['ntfy_topic'])")
        else
            ntfy_topic="raspie-camera-test"
        fi
        curl -d "start recording" ntfy.sh/$ntfy_topic
        echo -e "${GREEN}Trigger sent to topic '$ntfy_topic'. Audio/video capture should start recording.${NC}"
        ;;
    stop-recording)
        echo -e "${YELLOW}Sending stop recording notification...${NC}"
        # Read topic from config.yaml if possible
        if command -v python3 > /dev/null && [ -f "$PROJECT_DIR/config.yaml" ]; then
            ntfy_topic=$(python3 -c "import yaml; print(yaml.safe_load(open('$PROJECT_DIR/config.yaml', 'r'))['remote']['ntfy_topic'])")
        else
            ntfy_topic="raspie-camera-test"
        fi
        curl -d "stop recording" ntfy.sh/$ntfy_topic
        echo -e "${YELLOW}Stop signal sent to topic '$ntfy_topic'. Audio/video capture should stop recording.${NC}"
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|logs|enable|disable|trigger|stop-recording}"
        exit 1
        ;;
esac

exit 0
EOF

    # Make management script executable
    chmod +x "$PROJECT_DIR/raspie-service.sh"
    chown $SUDO_USER:$SUDO_USER "$PROJECT_DIR/raspie-service.sh"
    
    # Enable and start the service
    echo "Enabling the service to start at boot..."
    systemctl daemon-reload
    systemctl enable raspie-capture.service
fi

# Start the service immediately
echo "Starting the service now..."

# Create the base recordings directory
echo "Creating base recordings directory..."
RECORDINGS_DIR="/home/$SUDO_USER/raspie_recordings"
mkdir -p "$RECORDINGS_DIR"
chown $SUDO_USER:$SUDO_USER "$RECORDINGS_DIR"
echo "Recordings will be saved to $RECORDINGS_DIR/YYYY-MM-DD/{videos|audio}/"

systemctl start raspie-capture.service

# Apply optional performance optimizations
echo "Applying performance optimizations..."
if [ -f "$PROJECT_DIR/raspie-optimize.sh" ]; then
    bash "$PROJECT_DIR/raspie-optimize.sh"
else
    echo "WARNING: Performance optimization script not found. Skipping optimizations."
fi

# --- Camera Enablement Reminder --- 
echo "-----------------------------------------------------" 
echo "Installation Complete! System is now configured to:"
echo ""
echo "1. Stream video from your Raspberry Pi camera"
echo "2. Start automatically on boot"
echo "3. Accept recording triggers via ntfy.sh"
echo "4. Use configuration from config.yaml"
echo ""
echo "Current Service Status:"
systemctl status raspie-capture.service --no-pager
echo ""
echo "IMPORTANT: Ensure the camera is ENABLED using 'sudo raspi-config'" 
echo "(Interface Options -> Camera -> Enable, and ensure Legacy Camera is DISABLED)."
echo ""
echo "Control Commands:"
echo "- Start recording:   ./raspie-service.sh trigger"
echo "- Stop recording:    ./raspie-service.sh stop-recording"
echo "- Check status:      ./raspie-service.sh status"
echo "- View logs:         ./raspie-service.sh logs"
echo "- Live monitoring:   ./watch-raspie.sh"
echo ""
echo "Configuration:"
echo "- Edit settings in:  $PROJECT_DIR/config.yaml"
echo ""
echo "File Storage:"
echo "- All recordings are automatically organized by date"
echo "- Videos saved to: ~/raspie_recordings/YYYY-MM-DD/videos/"
echo "- Audio saved to:  ~/raspie_recordings/YYYY-MM-DD/audio/"
echo ""
echo "Remote Trigger (from any device):"
if command -v python3 > /dev/null && [ -f "$PROJECT_DIR/config.yaml" ]; then
    ntfy_topic=$(python3 -c "import yaml; print(yaml.safe_load(open('$PROJECT_DIR/config.yaml', 'r'))['remote']['ntfy_topic'])")
    echo "curl -d \"start recording\" ntfy.sh/$ntfy_topic"
    echo "curl -d \"stop recording\" ntfy.sh/$ntfy_topic"
else
    echo "curl -d \"start recording\" ntfy.sh/raspie-camera-test"
    echo "curl -d \"stop recording\" ntfy.sh/raspie-camera-test"
fi
echo ""
echo "A system reboot is recommended if you changed camera settings:"
echo "sudo reboot"
echo "-----------------------------------------------------"

# Create a convenience script for viewing live output
cat << 'EOF' > "$PROJECT_DIR/watch-raspie.sh"
#!/bin/bash
# Script to monitor Raspie Capture service in real-time

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== Raspie Capture Live Monitor ===${NC}"
echo -e "${YELLOW}Press Ctrl+C to exit${NC}"
echo

# Show current recording folders
TODAY=$(date +%Y-%m-%d)
RECORDINGS_DIR="$HOME/raspie_recordings/$TODAY"
if [ -d "$RECORDINGS_DIR" ]; then
    echo -e "${CYAN}Today's recordings (${TODAY}):${NC}"
    find "$RECORDINGS_DIR" -type f | sort
    echo
else
    echo -e "${YELLOW}No recordings yet today.${NC}"
    echo
fi

# Start showing live logs with timestamps
echo -e "${GREEN}Live service output:${NC}"
sudo journalctl -u raspie-capture.service -f -o cat --output-fields=MESSAGE

EOF

# Make the script executable
chmod +x "$PROJECT_DIR/watch-raspie.sh"
chown $SUDO_USER:$SUDO_USER "$PROJECT_DIR/watch-raspie.sh"

# Create a simple run script for manual starting
echo "Creating run-camera.sh script for easy manual starting..."
cat << 'EOF' > "$PROJECT_DIR/run-camera.sh"
#!/bin/bash
# Simple script to run the Raspberry Pi Camera Capture system
# Author: Anzal (anzal.ks@gmail.com)

# Change to the directory containing this script
cd "$(dirname "$0")"

# Check if a Python virtual environment exists and activate it
if [ -d ".venv" ]; then
    echo "Activating virtual environment..."
    source .venv/bin/activate
fi

# Check if config.yaml exists
if [ ! -f "config.yaml" ]; then
    echo "Error: config.yaml not found. Please run setup_pi.sh first."
    exit 1
fi

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
python -m src.raspberry_pi_lsl_stream.camera_capture

# Exit with the same status as the camera capture
exit $?
EOF

# Make the run script executable
chmod +x "$PROJECT_DIR/run-camera.sh"
chown $SUDO_USER:$SUDO_USER "$PROJECT_DIR/run-camera.sh"
echo "Created run-camera.sh script for easy manual starting" 

# --- Camera Permissions Setup ---
echo "Setting up camera permissions and dependencies..."

# Install necessary camera-related packages if not already installed
echo "Installing camera utilities and tools..."
apt install -y v4l-utils libcamera-apps libcamera-tools media-ctl

# Set proper permissions for camera access
echo "Setting camera group permissions..."
usermod -a -G video $SUDO_USER
usermod -a -G input $SUDO_USER
echo "Added $SUDO_USER to video and input groups"

# Create and set up camera lock file with proper permissions
echo "Setting up camera lock file with proper permissions..."
rm -f /tmp/raspie_camera.lock
touch /tmp/raspie_camera.lock
chmod 666 /tmp/raspie_camera.lock
chown $SUDO_USER:$SUDO_USER /tmp/raspie_camera.lock
echo "Camera lock file created with proper permissions"

# Fix permissions for camera device nodes if they exist
echo "Setting permissions for camera devices..."
if [ -e "/dev/video0" ]; then
  chmod 666 /dev/video0
fi

# Enable preview in config
echo "Updating config to enable preview..."
sed -i 's/preview: false/preview: true/' "$CONFIG_FILE"

# --- Camera Enablement Reminder --- 
echo "-----------------------------------------------------" 
echo "Installation Complete! System is now configured to:"
echo ""
echo "1. Stream video from your Raspberry Pi camera"
echo "2. Start automatically on boot"
echo "3. Accept recording triggers via ntfy.sh"
echo "4. Use configuration from config.yaml"
echo ""
echo "Current Service Status:"
systemctl status raspie-capture.service --no-pager
echo ""
echo "IMPORTANT: Ensure the camera is ENABLED using 'sudo raspi-config'" 
echo "(Interface Options -> Camera -> Enable, and ensure Legacy Camera is DISABLED)."
echo ""
echo "Control Commands:"
echo "- Start recording:   ./raspie-service.sh trigger"
echo "- Stop recording:    ./raspie-service.sh stop-recording"
echo "- Check status:      ./raspie-service.sh status"
echo "- View logs:         ./raspie-service.sh logs"
echo "- Live monitoring:   ./watch-raspie.sh"
echo ""
echo "Configuration:"
echo "- Edit settings in:  $PROJECT_DIR/config.yaml"
echo ""
echo "File Storage:"
echo "- All recordings are automatically organized by date"
echo "- Videos saved to: ~/raspie_recordings/YYYY-MM-DD/videos/"
echo "- Audio saved to:  ~/raspie_recordings/YYYY-MM-DD/audio/"
echo ""
echo "Remote Trigger (from any device):"
if command -v python3 > /dev/null && [ -f "$PROJECT_DIR/config.yaml" ]; then
    ntfy_topic=$(python3 -c "import yaml; print(yaml.safe_load(open('$PROJECT_DIR/config.yaml', 'r'))['remote']['ntfy_topic'])")
    echo "curl -d \"start recording\" ntfy.sh/$ntfy_topic"
    echo "curl -d \"stop recording\" ntfy.sh/$ntfy_topic"
else
    echo "curl -d \"start recording\" ntfy.sh/raspie-camera-test"
    echo "curl -d \"stop recording\" ntfy.sh/raspie-camera-test"
fi
echo ""
echo "A system reboot is recommended if you changed camera settings:"
echo "sudo reboot"
echo "-----------------------------------------------------" 