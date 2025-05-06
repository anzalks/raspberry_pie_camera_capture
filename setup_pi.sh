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
# Add filesystem utils and hardware encoding deps here
apt install -y --no-install-recommends \
    build-essential \
    python3-dev \
    python3-pip \
    python3-venv \
    python3-opencv \
    python3-picamera2 \
    libatlas-base-dev \
    libhdf5-dev \
    libhdf5-serial-dev \
    libopenjp2-7 \
    exfat-fuse \
    exfatprogs \
    ntfs-3g \
    libcamera-dev \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-libav \
    curl \
    autoconf \
    libtool \
    pkg-config \
    libbsd-dev \
    libasound2-dev \
    portaudio19-dev \
    python3-numpy \
    python3-scipy # Added audio-related packages

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
      echo "Upgrading pip, setuptools, and wheel in the virtual environment..."
      # Run pip install as the original user using the venv's pip
      sudo -u "$SUDO_USER" "$VENV_DIR/bin/pip" install --upgrade pip setuptools wheel
      
      echo "Installing project 'raspberry-pi-lsl-stream' in editable mode..."
      # Install the project itself as the original user
      # Ensure we are in the correct directory before running pip install -e .
      cd "$PROJECT_DIR"
      sudo -u "$SUDO_USER" "$VENV_DIR/bin/pip" install -e .
      
      if [ $? -eq 0 ]; then
          echo "Project installed successfully into the virtual environment."
      else
          echo "ERROR: Failed to install project using pip."
      fi
  fi
fi

# --- Camera Enablement Reminder --- 
# Enabling the camera interface via script is complex and depends on OS version.
# It's often SAFER to do this manually via 'sudo raspi-config' -> Interface Options -> Camera.
# Ensure the LEGACY camera interface is DISABLED if using picamera2/libcamera.


echo "-----------------------------------------------------" 
echo "System dependency installation process finished."
echo ""
echo "Next Steps:"
echo "1. Ensure the camera is ENABLED using 'sudo raspi-config'" 
echo "   (Interface Options -> Camera -> Enable, and ensure Legacy Camera is DISABLED)."
echo "2. REBOOT the Raspberry Pi if you changed camera settings: sudo reboot"
echo "3. Activate the Python virtual environment created in this directory:"
echo "   source .venv/bin/activate"
echo "4. You can now run the command:"
echo "   rpi-lsl-stream --help"
echo "-----------------------------------------------------"

exit 0 