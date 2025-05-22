#!/bin/bash

# Setup script for Raspberry Pi LSL Camera Streamer System Dependencies
# 
# IMPORTANT:
# 1. Run this script with sudo:   sudo bash setup_pi.sh
# 2. Review the script before running.
# 3. A reboot might be required after running this script for camera changes.
# 4. This script installs SYSTEM packages. Python package installation
#    should be done AFTER this script, inside a virtual environment.

# --- Color Definitions ---
RED_TEXT='\033[0;31m'
GREEN_TEXT='\033[0;32m'
YELLOW_TEXT='\033[1;33m'
NC='\033[0m' # No Color

# --- Error Handling --- 
set -e # Exit immediately if a command exits with a non-zero status.
# set -x # Uncomment for xtrace debugging if needed

# --- Check if running as root --- 
if [ "$(id -u)" -ne 0 ]; then
  echo -e "${RED_TEXT}This script must be run as root (use sudo). Exiting.${NC}" >&2
  exit 1
fi

# Define critical variables
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
PROJECT_DIR="$SCRIPT_DIR"
CONFIG_FILE="$PROJECT_DIR/config.yaml"
VENV_DIR_NAME=".venv"
VENV_PATH="$PROJECT_DIR/$VENV_DIR_NAME"
SUDO_USER_NAME=${SUDO_USER:-$(logname 2>/dev/null || echo "pi")} # Get actual user if sudo, fallback to logname or 'pi'

ORIG_SWAPSIZE="" # Initialize for swap functions

echo -e "${GREEN_TEXT}=== Starting Raspberry Pi Camera Setup (Focus on PIP Stability) ===${NC}"
echo "Running as: $(whoami), Script Invoker (SUDO_USER): $SUDO_USER_NAME"
echo "Project Directory: $PROJECT_DIR"
echo "Virtual Environment Path: $VENV_PATH"

# --- Swap Management Functions ---
increase_swap() {
    echo -e "${YELLOW_TEXT}Attempting to increase swap space...${NC}"
    if [ -f /etc/dphys-swapfile ]; then
        SWAP_SIZE_MB=2048
        CONF_SWAPSIZE_LINE=$(grep -E "^CONF_SWAPSIZE=" /etc/dphys-swapfile)
        if [ -n "$CONF_SWAPSIZE_LINE" ]; then
            ORIG_SWAPSIZE=$(echo "$CONF_SWAPSIZE_LINE" | cut -d'=' -f2)
            echo "Original CONF_SWAPSIZE was $ORIG_SWAPSIZE MB"
            if [ "$ORIG_SWAPSIZE" != "$SWAP_SIZE_MB" ]; then
                sed -i "s/^CONF_SWAPSIZE=.*/CONF_SWAPSIZE=$SWAP_SIZE_MB/" /etc/dphys-swapfile
                echo "Set CONF_SWAPSIZE to $SWAP_SIZE_MB MB"
                echo "Restarting dphys-swapfile service..."
                systemctl stop dphys-swapfile || echo "Failed to stop dphys-swapfile, continuing..."
                systemctl start dphys-swapfile || echo "Failed to start dphys-swapfile, continuing..."
                echo "Swap space potentially increased. Current status:"
            else
                echo "CONF_SWAPSIZE is already $SWAP_SIZE_MB MB. No changes made."
            fi
        else
             echo "CONF_SWAPSIZE line not found in /etc/dphys-swapfile. Creating it."
             echo "CONF_SWAPSIZE=$SWAP_SIZE_MB" >> /etc/dphys-swapfile
             echo "Restarting dphys-swapfile service..."
             systemctl stop dphys-swapfile || echo "Failed to stop dphys-swapfile, continuing..."
             systemctl start dphys-swapfile || echo "Failed to start dphys-swapfile, continuing..."
        fi
        free -m
    else
        echo -e "${RED_TEXT}dphys-swapfile not found. Cannot manage swap automatically.${NC}"
    fi
}

restore_swap() {
    echo -e "${YELLOW_TEXT}Attempting to restore original swap space...${NC}"
     if [ -f /etc/dphys-swapfile ] && [ -n "$ORIG_SWAPSIZE" ]; then
        CONF_SWAPSIZE_LINE_CURRENT=$(grep -E "^CONF_SWAPSIZE=" /etc/dphys-swapfile | cut -d'=' -f2)
        if [ "$CONF_SWAPSIZE_LINE_CURRENT" != "$ORIG_SWAPSIZE" ]; then
            echo "Restoring CONF_SWAPSIZE to $ORIG_SWAPSIZE MB"
            sed -i "s/^CONF_SWAPSIZE=.*/CONF_SWAPSIZE=$ORIG_SWAPSIZE/" /etc/dphys-swapfile
            echo "Restarting dphys-swapfile service..."
            systemctl stop dphys-swapfile || echo "Failed to stop dphys-swapfile, continuing..."
            systemctl start dphys-swapfile || echo "Failed to start dphys-swapfile, continuing..."
            echo "Swap space potentially restored. Current status:"
        else
            echo "CONF_SWAPSIZE is already at the original recorded value of $ORIG_SWAPSIZE MB."
        fi
        free -m
    elif [ -f /etc/dphys-swapfile ]; then
        echo "Original swap size not recorded or no change was made. Current CONF_SWAPSIZE will be kept."
        echo "If you manually changed it or want to revert, edit /etc/dphys-swapfile."
    else
        echo -e "${RED_TEXT}dphys-swapfile not found. Cannot manage swap automatically.${NC}"
    fi
}

# --- Increase Swap ---
increase_swap

echo -e "${YELLOW_TEXT}Updating package list (apt update)...${NC}"
apt update -qq

echo -e "${YELLOW_TEXT}Installing required system packages (including build tools, python3-dev, picamera2, and potentially useful extras)...${NC}"
# Install packages one by one to reduce memory usage
echo -e "${YELLOW_TEXT}Installing packages one by one to minimize memory usage...${NC}"
for pkg in build-essential python3-dev python3-pip python3-venv python3-opencv python3-picamera2 python3-yaml \
    libatlas-base-dev libhdf5-dev libhdf5-serial-dev libopenjp2-7 exfat-fuse exfatprogs ntfs-3g \
    libcamera-dev gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gstreamer1.0-libav curl \
    autoconf libtool pkg-config libbsd-dev libasound2-dev portaudio19-dev v4l-utils \
    python3-pyqt5 python3-opengl; do
    echo -e "Installing $pkg..."
    apt install -y --no-install-recommends $pkg
    # Sleep briefly to allow system to recover between installations
    sleep 2
done

# Separate numpy and scipy installation to prevent memory issues
echo -e "${YELLOW_TEXT}Installing python3-numpy...${NC}"
apt install -y --no-install-recommends python3-numpy
sleep 2
echo -e "${YELLOW_TEXT}Installing python3-scipy...${NC}"
apt install -y --no-install-recommends python3-scipy
sleep 2

echo -e "${YELLOW_TEXT}Attempting to install liblsl-dev (LabStreamingLayer library) via apt...${NC}"
if apt install -y --no-install-recommends liblsl-dev; then
  echo -e "${GREEN_TEXT}liblsl-dev installed successfully via apt.${NC}"
else
  echo -e "${YELLOW_TEXT}apt install liblsl-dev failed. Attempting to build from source...${NC}"
  apt install -y --no-install-recommends cmake
  ORIG_DIR_LSL=$(pwd)
  TEMP_LSL_DIR=$(mktemp -d); trap "echo 'Cleaning up $TEMP_LSL_DIR'; rm -rf $TEMP_LSL_DIR" EXIT
  echo "Cloning liblsl into $TEMP_LSL_DIR/liblsl..."
  git clone --depth 1 https://github.com/sccn/liblsl.git "$TEMP_LSL_DIR/liblsl"
  cd "$TEMP_LSL_DIR/liblsl"
  mkdir -p build && cd build
  cmake .. && make -j2 && make install && ldconfig # Reduced to -j2
  echo -e "${GREEN_TEXT}liblsl successfully built and installed from source.${NC}"
  cd "$ORIG_DIR_LSL"
  rm -rf "$TEMP_LSL_DIR"; trap - EXIT
fi

# --- Install other dependencies ---

echo -e "${YELLOW_TEXT}Installing libcap-dev (needed for python-prctl, a picamera2 dependency)...${NC}"
apt install -y libcap-dev

echo -e "${YELLOW_TEXT}Installing libcamera-apps (useful for testing and ensuring libcamera stack is present)...${NC}"
apt install -y libcamera-apps

# --- Install curlftpfs (Try apt first, fallback to source) ---
echo -e "${YELLOW_TEXT}Checking for curlftpfs...${NC}"

# Attempt to install via apt first
echo -e "${YELLOW_TEXT}Attempting to install curlftpfs via apt...${NC}"
if apt install -y curlftpfs; then
    echo -e "${GREEN_TEXT}curlftpfs installed successfully via apt.${NC}"
else
    echo -e "${YELLOW_TEXT}apt install curlftpfs failed or package not available.${NC}"
    # Check if command exists anyway (might have been installed previously)
    if command -v curlftpfs >/dev/null 2>&1; then
        echo -e "${YELLOW_TEXT}curlftpfs command found, likely installed previously. Skipping build.${NC}"
    else
        echo -e "${YELLOW_TEXT}curlftpfs command not found. Attempting to build from source...${NC}"
        
        # Install build dependencies for curlftpfs
        echo -e "${YELLOW_TEXT}Installing build dependencies for curlftpfs (check output for errors)...${NC}"
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

        echo -e "${YELLOW_TEXT}Creating temporary build directory: ${BUILD_DIR}${NC}"
        rm -rf "${BUILD_DIR}" # Clean previous attempts
        mkdir -p "${BUILD_DIR}"
        cd "${BUILD_DIR}"

        echo -e "${YELLOW_TEXT}Cloning curlftpfs source from ${REPO_URL}...${NC}"
        if git clone "${REPO_URL}" curlftpfs_src; then
            cd curlftpfs_src
            echo -e "${YELLOW_TEXT}Running autoreconf to generate configure script...${NC}"
            if autoreconf -fi; then
                echo -e "${YELLOW_TEXT}Running configure script...${NC}"
                if ./configure; then
                    echo -e "${YELLOW_TEXT}Configuration successful. Compiling (make)...${NC}"
                    if make; then
                        echo -e "${YELLOW_TEXT}Compilation successful. Installing (make install)...${NC}"
                        # Run install as root since we are in a sudo script
                        if make install; then
                            echo -e "${GREEN_TEXT}curlftpfs successfully built and installed from source.${NC}"
                        else
                            echo -e "${RED_TEXT}ERROR: 'make install' failed.${NC}" >&2
                        fi
                    else
                        echo -e "${RED_TEXT}ERROR: 'make' failed.${NC}" >&2
                    fi
                else
                    echo -e "${RED_TEXT}ERROR: './configure' failed. Check dependencies were installed correctly.${NC}" >&2
                fi
            else
                 echo -e "${RED_TEXT}ERROR: 'autoreconf -fi' failed. Check build dependencies.${NC}" >&2
            fi
            # Go back to parent build dir before cleanup
            cd .. 
        else
            echo -e "${RED_TEXT}ERROR: Failed to clone curlftpfs source from GitHub.${NC}" >&2
        fi
        
        # Cleanup build directory
        echo -e "${YELLOW_TEXT}Cleaning up build directory: ${BUILD_DIR}${NC}"
        cd "${ORIG_DIR}" # Go back to original directory first
        rm -rf "${BUILD_DIR}"

        # Final check if command exists after build attempt
        if ! command -v curlftpfs >/dev/null 2>&1; then
            echo -e "${YELLOW_TEXT}WARNING: curlftpfs build attempt finished, but command is still not found.${NC}" >&2
        fi
    fi
fi

# --- Python Virtual Environment and Project Installation ---

echo -e "${YELLOW_TEXT}Setting up Python virtual environment and project...${NC}"

# Create Python virtual environment
echo -e "${YELLOW_TEXT}Creating Python virtual environment at $PROJECT_DIR/$VENV_DIR_NAME...${NC}"
if [ -d "$VENV_PATH" ]; then
    echo "Virtual environment exists. Removing for a clean setup..."
    # Ensure correct ownership before removing if script re-run by root after user creation
    if [ "$(stat -c '%U' "$VENV_PATH")" != "$SUDO_USER_NAME" ]; then
        chown -R "$SUDO_USER_NAME:$(id -gn "$SUDO_USER_NAME")" "$VENV_PATH"
    fi
    rm -rf "$VENV_PATH"
fi
echo "Creating Python virtual environment as user '$SUDO_USER_NAME'..."
sudo -u "$SUDO_USER_NAME" python3 -m venv "$VENV_PATH"
echo "Virtual environment created."
# Explicitly ensure SUDO_USER_NAME owns the venv directory and its contents.
chown -R "$SUDO_USER_NAME:$(id -gn "$SUDO_USER_NAME")" "$VENV_PATH"

PIP_EXEC="$VENV_PATH/bin/pip"
PYTHON_EXEC="$VENV_PATH/bin/python"

echo -e "${YELLOW_TEXT}Attempting to upgrade pip in venv (as $SUDO_USER_NAME)...${NC}"
echo "Command: sudo -u \"$SUDO_USER_NAME\" \"$PIP_EXEC\" install --no-cache-dir --prefer-binary --upgrade pip"
if ! sudo -u "$SUDO_USER_NAME" "$PIP_EXEC" install --no-cache-dir --prefer-binary --upgrade pip; then
    echo -e "${RED_TEXT}ERROR: Failed to upgrade pip. This is a critical failure point.${NC}"
    echo -e "${YELLOW_TEXT}Your system might be running out of memory. Try increasing swap manually or ensure no other heavy processes are running.${NC}"
    exit 1
fi
echo -e "${GREEN_TEXT}pip upgraded successfully.${NC}"

echo -e "${YELLOW_TEXT}Attempting to upgrade setuptools and wheel in venv (as $SUDO_USER_NAME)...${NC}"
if ! sudo -u "$SUDO_USER_NAME" "$PIP_EXEC" install --no-cache-dir --prefer-binary --upgrade setuptools wheel; then
    echo -e "${RED_TEXT}ERROR: Failed to upgrade setuptools/wheel.${NC}"
    # Not exiting, but this is problematic
fi
echo -e "${GREEN_TEXT}setuptools and wheel upgrade attempt finished.${NC}"

echo -e "${YELLOW_TEXT}Installing core Python packages (pylsl, numpy, etc.) into venv (as $SUDO_USER_NAME)...${NC}"
PIP_CORE_PACKAGES=( "pylsl" "numpy" "scipy" "pyyaml" "requests" "psutil" "importlib-metadata" )
if ! sudo -u "$SUDO_USER_NAME" "$PIP_EXEC" install --prefer-binary --verbose ${PIP_CORE_PACKAGES[*]}; then
    echo -e "${RED_TEXT}ERROR: Failed to install one or more core Python packages. Check output.${NC}"
fi

echo -e "${YELLOW_TEXT}Attempting to install/reinstall 'picamera2' into venv (as $SUDO_USER_NAME)...${NC}"
echo "This uses --force-reinstall --no-cache-dir --no-binary=:all: for picamera2."
set -x # Enable command tracing for this specific pip command
if ! sudo -u "$SUDO_USER_NAME" "$PIP_EXEC" install --prefer-binary --force-reinstall --no-cache-dir --no-binary=:all: picamera2; then
    echo -e "${RED_TEXT}ERROR: Failed to install 'picamera2' using pip. This is critical!${NC}"
fi
set +x # Disable command tracing
echo "Finished 'picamera2' installation attempt."

echo -e "${YELLOW_TEXT}Performing internal import check for 'picamera2' in venv (as $SUDO_USER_NAME)...${NC}"
IMPORT_CHECK_SCRIPT="import sys; print(f'Python version: {sys.version}'); print(f'Sys.path: {sys.path}'); import picamera2; print('picamera2 imported. Version:', picamera2.__version__)"
if sudo -u "$SUDO_USER_NAME" "$PYTHON_EXEC" -c "$IMPORT_CHECK_SCRIPT"; then
    echo -e "${GREEN_TEXT}SUCCESS: 'picamera2' imported successfully within setup script by venv Python.${NC}"
else
    echo -e "${RED_TEXT}FAILURE: 'picamera2' FAILED to import by venv Python within setup script.${NC}"
    echo -e "${YELLOW_TEXT}This means 'picamera2' is not usable in the venv despite pip's attempt.${NC}"
fi

echo -e "${YELLOW_TEXT}Installing project in editable mode in venv (as $SUDO_USER_NAME)...${NC}"
if ! sudo -u "$SUDO_USER_NAME" "$PIP_EXEC" install -e "$PROJECT_DIR"; then
   echo -e "${RED_TEXT}ERROR: Failed to install project in editable mode. Check output.${NC}"
fi

echo -e "${GREEN_TEXT}Python virtual environment setup complete.${NC}"

# --- Setup Recordings Directory Structure ---
echo -e "${YELLOW_TEXT}Setting up recordings directory structure...${NC}"
RECORDINGS_DIR="$PROJECT_DIR/recordings"
TODAY_DIR="$RECORDINGS_DIR/$(date +%Y-%m-%d)"

# Create directories with proper permissions
echo -e "${YELLOW_TEXT}Creating recordings directories: $TODAY_DIR${NC}"
mkdir -p "$TODAY_DIR"

# Set proper ownership and permissions
if [ -n "$SUDO_USER_NAME" ]; then
  echo -e "${YELLOW_TEXT}Setting ownership to $SUDO_USER_NAME for recordings directory${NC}"
  chown -R "$SUDO_USER_NAME:$SUDO_USER_NAME" "$RECORDINGS_DIR"
fi
chmod -R 755 "$RECORDINGS_DIR"
echo -e "${GREEN_TEXT}Set proper permissions for recordings directory${NC}"

# --- Create default configuration file ---
echo -e "${YELLOW_TEXT}Creating default configuration file...${NC}"

# Ensure PROJECT_DIR is set to the current directory first
if [ -z "$PROJECT_DIR" ]; then
    PROJECT_DIR=$(pwd)
fi
CONFIG_FILE="$PROJECT_DIR/config.yaml"

if [ -f "$CONFIG_FILE" ]; then
    echo -e "${YELLOW_TEXT}Configuration file already exists. Backing up existing file...${NC}"
    # Backup the existing file
    mv "$CONFIG_FILE" "$CONFIG_FILE.bak"
fi

echo -e "${YELLOW_TEXT}Updating config to enable preview...${NC}"
if [ -f "$CONFIG_FILE" ]; then
    sed -i 's/preview: false/preview: true/' "$CONFIG_FILE"
    echo -e "${GREEN_TEXT}Updated preview setting in config file${NC}"
else
    echo -e "${YELLOW_TEXT}WARNING: Config file not found at $CONFIG_FILE, creating it...${NC}"
    # Create a basic config file
    cat > "$CONFIG_FILE" << EOCFG
# Basic configuration file for Raspberry Pi Camera Capture
camera:
  preview: true
  resolution: [1280, 720]
  framerate: 30
  rotation: 0
  enable_crop: true  # Enable Global Shutter Camera support
recording:
  enabled: true
  format: h264
  output_dir: ~/raspie_recordings
remote:
  ntfy_topic: raspie-camera-test
EOCFG
    if [ -n "$SUDO_USER_NAME" ]; then
        chown $SUDO_USER_NAME:$SUDO_USER_NAME "$CONFIG_FILE"
    fi
    echo -e "${GREEN_TEXT}Created basic config file at $CONFIG_FILE${NC}"
fi

# --- Setup Camera Permissions ---
echo -e "${YELLOW_TEXT}Setting up camera permissions and dependencies...${NC}"

# Ensure v4l-utils is installed for camera debugging
echo -e "${YELLOW_TEXT}Installing v4l-utils for camera debugging capabilities...${NC}"
apt install -y v4l-utils

# Ensure v4l-utils and libcamera-apps are installed (critical for Global Shutter Camera)
echo -e "${YELLOW_TEXT}Installing camera utilities and tools...${NC}"
# Install v4l-utils (which includes v4l2-ctl), libcamera-apps, and python3-libcamera
# media-ctl is part of v4l-utils on newer systems (like Bookworm)
# python3-opencv is usually needed for image processing
# Ensure GStreamer plugins for libcamera are installed if needed for other apps
# sudo apt install -y v4l-utils libcamera-apps libcamera-tools media-ctl python3-libcamera
sudo apt install -y v4l-utils libcamera-apps libcamera-tools python3-libcamera python3-opencv gstreamer1.0-libcamera

# Check if installation was successful (basic check)
if ! command -v v4l2-ctl &> /dev/null || ! command -v libcamera-hello &> /dev/null; then
    echo -e "${YELLOW_TEXT}WARNING: v4l-utils or libcamera-hello not found. Camera utilities might be incomplete.${NC}" >&2
fi

# Set proper permissions for camera access
echo -e "${YELLOW_TEXT}Setting camera group permissions...${NC}"
usermod -a -G video $SUDO_USER_NAME
usermod -a -G input $SUDO_USER_NAME
echo -e "${GREEN_TEXT}Added $SUDO_USER_NAME to video and input groups${NC}"

# Create and set up camera lock file with proper permissions
echo -e "${YELLOW_TEXT}Setting up camera lock file with proper permissions...${NC}"
rm -f /tmp/raspie_camera.lock
touch /tmp/raspie_camera.lock
chmod 666 /tmp/raspie_camera.lock
chown $SUDO_USER_NAME:$SUDO_USER_NAME /tmp/raspie_camera.lock
echo -e "${GREEN_TEXT}Camera lock file created with proper permissions${NC}"

# Fix permissions for camera device nodes if they exist
echo -e "${YELLOW_TEXT}Setting permissions for ALL camera devices...${NC}"
for dev in /dev/video*; do
    if [ -e "$dev" ]; then
        echo -e "${YELLOW_TEXT}Setting permissions for $dev${NC}"
        chmod 666 "$dev"
    fi
done

# Ensure camera modules are loaded
echo -e "${YELLOW_TEXT}Checking if camera modules are loaded...${NC}"
if ! lsmod | grep -q "^videodev"; then
    echo -e "${YELLOW_TEXT}Loading camera modules...${NC}"
    modprobe videodev 2>/dev/null || true
    modprobe v4l2_common 2>/dev/null || true
fi

# Ensure camera is enabled in config
echo -e "${YELLOW_TEXT}Checking if camera is enabled in raspi-config...${NC}"
if command -v raspi-config > /dev/null; then
    echo -e "${YELLOW_TEXT}Enabling camera interface via raspi-config...${NC}"
    raspi-config nonint do_camera 0
    echo -e "${GREEN_TEXT}Camera interface enabled${NC}"
fi

# Enable preview in config
echo -e "${YELLOW_TEXT}Updating config to enable preview...${NC}"
if [ -f "$CONFIG_FILE" ]; then
    sed -i 's/preview: false/preview: true/' "$CONFIG_FILE"
    echo -e "${GREEN_TEXT}Updated preview setting in config file${NC}"
else
    echo -e "${YELLOW_TEXT}WARNING: Config file not found at $CONFIG_FILE, creating it...${NC}"
    # Create a basic config file
    cat > "$CONFIG_FILE" << EOCFG
# Basic configuration file for Raspberry Pi Camera Capture
camera:
  preview: true
  resolution: [1280, 720]
  framerate: 30
  rotation: 0
  enable_crop: true  # Enable Global Shutter Camera support
recording:
  enabled: true
  format: h264
  output_dir: ~/raspie_recordings
remote:
  ntfy_topic: raspie-camera-test
EOCFG
    if [ -n "$SUDO_USER_NAME" ]; then
        chown $SUDO_USER_NAME:$SUDO_USER_NAME "$CONFIG_FILE"
    fi
    echo -e "${GREEN_TEXT}Created basic config file at $CONFIG_FILE${NC}"
fi

echo -e "${GREEN_TEXT}Camera setup complete. A reboot is recommended to ensure camera detection.${NC}"

# --- Automatic Service Installation ---
echo -e "${YELLOW_TEXT}Installing camera capture service to start automatically at boot...${NC}"

# Define PROJECT_DIR absolutely for the service file
ABS_PROJECT_DIR=$(readlink -f "$PROJECT_DIR")
ABS_VENV_PATH=$(readlink -f "$VENV_PATH")
ABS_CONFIG_FILE=$(readlink -f "$CONFIG_FILE")
# Define the ExecStart command carefully
EXEC_START_COMMAND="$ABS_VENV_PATH/bin/python $ABS_PROJECT_DIR/src/raspberry_pi_lsl_stream/camera_capture.py --config $ABS_CONFIG_FILE"


# Check if the service file already exists
if [ -f "/etc/systemd/system/raspie-capture.service" ]; then
    echo -e "${YELLOW_TEXT}Service file already exists. Reinstalling...${NC}"
    systemctl stop raspie-capture.service 2>/dev/null || true
    systemctl disable raspie-capture.service 2>/dev/null || true # Ensure it's disabled before re-creating
fi

echo -e "${YELLOW_TEXT}Creating systemd service file: /etc/systemd/system/raspie-capture.service${NC}"
    # Create the systemd service file
    cat << EOF > "/etc/systemd/system/raspie-capture.service"
[Unit]
Description=Raspberry Pi LSL Camera Capture Service
After=network-online.target multi-user.target
Wants=network-online.target

[Service]
Type=simple
User=$SUDO_USER_NAME
Group=$(id -gn $SUDO_USER_NAME)
WorkingDirectory=$ABS_PROJECT_DIR
ExecStart=$EXEC_START_COMMAND
Environment="PATH=$ABS_VENV_PATH/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
Environment="PYTHONUNBUFFERED=1"
Environment="PYTHONPATH=$ABS_PROJECT_DIR"
Environment="DISPLAY=:0" # May be needed if picamera2 preview is on and service runs headless
StandardOutput=journal+console
StandardError=journal+console
Restart=on-failure
RestartSec=15s
TimeoutStopSec=30s
Nice=-5 # Give it a bit more priority if needed

[Install]
WantedBy=multi-user.target
EOF

# Set appropriate permissions for the service file
    chmod 644 "/etc/systemd/system/raspie-capture.service"

echo -e "${YELLOW_TEXT}Reloading systemd daemon...${NC}"
systemctl daemon-reload

echo -e "${YELLOW_TEXT}Enabling the raspie-capture service to start on boot...${NC}"
systemctl enable raspie-capture.service

echo -e "${YELLOW_TEXT}Attempting to start the raspie-capture service...${NC}"
systemctl start raspie-capture.service

# Give it a moment and check status
sleep 15
echo -e "${GREEN_TEXT}--- Current status of raspie-capture.service: ---${NC}"
systemctl status raspie-capture.service --no-pager || echo -e "${YELLOW_TEXT}Service might still be initializing or failed.${NC}"

# --- Camera Enablement Reminder --- 
echo -e "${GREEN_TEXT}-----------------------------------------------------$NC" 
echo -e "${GREEN_TEXT}Installation Complete! System is now configured to:$NC"
echo -e "${GREEN_TEXT}1. Stream video from your Raspberry Pi camera$NC"
echo -e "${GREEN_TEXT}2. Start automatically on boot$NC"
echo -e "${GREEN_TEXT}3. Accept recording triggers via ntfy.sh$NC"
echo -e "${GREEN_TEXT}4. Use configuration from config.yaml$NC"
echo -e "${GREEN_TEXT}Current Service Status:$NC"
systemctl status raspie-capture.service --no-pager
echo -e "${GREEN_TEXT}IMPORTANT: Ensure the camera is ENABLED using 'sudo raspi-config'$NC" 
echo -e "${GREEN_TEXT}(Interface Options -> Camera -> Enable, and ensure Legacy Camera is DISABLED.)"
echo -e "${GREEN_TEXT}Control Commands:$NC"
echo -e "- Start recording:   ./raspie-service.sh trigger$NC"
echo -e "- Stop recording:    ./raspie-service.sh stop-recording$NC"
echo -e "- Check status:      ./raspie-service.sh status$NC"
echo -e "- View logs:         ./raspie-service.sh logs$NC"
echo -e "- Live monitoring:   ./watch-raspie.sh$NC"
echo -e "${GREEN_TEXT}Configuration:$NC"
echo -e "- Edit settings in:  $PROJECT_DIR/config.yaml$NC"
echo -e "${GREEN_TEXT}File Storage:$NC"
echo -e "- All recordings are automatically organized by date$NC"
echo -e "- Videos saved to: ~/raspie_recordings/YYYY-MM-DD/videos/$NC"
echo -e "- Audio saved to:  ~/raspie_recordings/YYYY-MM-DD/audio/$NC"
echo -e "${GREEN_TEXT}Remote Trigger (from any device):$NC"
if command -v python3 > /dev/null && [ -f "$PROJECT_DIR/config.yaml" ]; then
    ntfy_topic=$(python3 -c "import yaml; print(yaml.safe_load(open('$PROJECT_DIR/config.yaml', 'r'))['remote']['ntfy_topic'])")
    echo -e "curl -d \"start recording\" ntfy.sh/$ntfy_topic$NC"
    echo -e "curl -d \"stop recording\" ntfy.sh/$ntfy_topic$NC"
else
    echo -e "curl -d \"start recording\" ntfy.sh/raspie-camera-test$NC"
    echo -e "curl -d \"stop recording\" ntfy.sh/raspie-camera-test$NC"
fi
echo -e "${GREEN_TEXT}A system reboot is recommended if you changed camera settings:$NC"
echo -e "sudo reboot$NC"
echo -e "${GREEN_TEXT}-----------------------------------------------------$NC"

# Create a convenience script for viewing live output
cat << 'EOF' > "$PROJECT_DIR/watch-raspie.sh"
#!/bin/bash
# Script to monitor Raspie Capture service in real-time

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Set terminal to support color and unicode
export TERM=xterm-256color

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

# Check if camera is running as a service
if systemctl is-active --quiet raspie-capture.service; then
    echo -e "${GREEN}Camera is running as a service${NC}"
    
    # Start showing live logs with timestamps
    echo -e "${GREEN}Live service output:${NC}"
    sudo journalctl -u raspie-capture.service -f -o cat
else
    # If not running as a service, check for direct process
    CAMERA_PID=$(pgrep -f "python.*camera_capture")
    
    if [ -n "$CAMERA_PID" ]; then
        echo -e "${GREEN}Camera is running directly (PID: $CAMERA_PID)${NC}"
        echo -e "${YELLOW}The status display should be visible in the terminal where it was started.${NC}"
        
        # Check if there is a status file for fallback
        if [ -f "/tmp/raspie_camera_status" ]; then
            echo -e "${CYAN}Status information:${NC}"
            cat /tmp/raspie_camera_status
            
            # Offer to attach to the process if tmux is available
            if command -v tmux &> /dev/null; then
                echo -e "${YELLOW}To view the actual terminal where the camera is running, use:${NC}"
                echo -e "${CYAN}ps -ef | grep camera_capture${NC}"
            fi
        else
            echo -e "${RED}No status information available.${NC}"
        fi
    else
        echo -e "${RED}No camera process is currently running.${NC}"
        echo -e "${YELLOW}To start the camera:$NC"
        echo -e "${CYAN}1. As a service: sudo systemctl start raspie-capture.service$NC"
        echo -e "${CYAN}2. Interactively: ./run-camera.sh$NC"
    fi
fi

EOF

# Make the script executable
chmod +x "$PROJECT_DIR/watch-raspie.sh"
chown $SUDO_USER_NAME:$SUDO_USER_NAME "$PROJECT_DIR/watch-raspie.sh"

# Create a simple run script for manual starting
echo -e "${YELLOW_TEXT}Creating run-camera.sh script for easy manual starting...${NC}"
cat << 'EOF' > "$PROJECT_DIR/run-camera.sh"
#!/bin/bash
# Simple script to run the Raspberry Pi Camera Capture system
# Author: Anzal (anzal.ks@gmail.com)

# Change to the directory containing this script
cd "$(dirname "$0")"

# Check if a Python virtual environment exists and activate it
if [ -d ".venv" ]; then
    echo -e "${YELLOW_TEXT}Activating virtual environment...${NC}"
    source .venv/bin/activate
fi

# Check if config.yaml exists
if [ ! -f "config.yaml" ]; then
    echo -e "${RED_TEXT}Error: config.yaml not found. Please run setup_pi.sh first.${NC}"
    exit 1
fi

# Run environment check
echo -e "${YELLOW_TEXT}Running environment check...${NC}"
python check-camera-env.py

# Ask if user wants to continue
read -p "Continue with camera capture? (y/n): " continue_capture
if [[ $continue_capture != "y" && $continue_capture != "Y" ]]; then
    echo -e "${YELLOW_TEXT}Exiting.${NC}"
    exit 0
fi

# Run camera capture
echo -e "${YELLOW_TEXT}Starting camera capture with default settings from config.yaml...${NC}"
python -m src.raspberry_pi_lsl_stream.camera_capture

# Exit with the same status as the camera capture
exit $?
EOF

# Make the run script executable
chmod +x "$PROJECT_DIR/run-camera.sh"
chown $SUDO_USER_NAME:$SUDO_USER_NAME "$PROJECT_DIR/run-camera.sh"
echo -e "${GREEN_TEXT}Created run-camera.sh script for easy manual starting${NC}" 

echo -e "${GREEN_TEXT}-----------------------------------------------------$NC" 
echo -e "${GREEN_TEXT}Installation script finished.$NC"
echo -e "${YELLOW_TEXT}IMPORTANT: A REBOOT IS HIGHLY RECOMMENDED (sudo reboot)$NC"
echo -e "${GREEN_TEXT}especially if this is a fresh install or camera settings were changed.$NC"
echo -e "After reboot, check service status: sudo systemctl status raspie-capture.service$NC"
echo -e "And check logs: sudo journalctl -fu raspie-capture.service$NC"
echo -e "${GREEN_TEXT}-----------------------------------------------------$NC" 

# --- Restore Swap ---
restore_swap

exit 0 