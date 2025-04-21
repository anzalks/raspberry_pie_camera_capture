#!/bin/bash

# Setup script for Raspberry Pi LSL Camera Streamer System Dependencies
# 
# IMPORTANT:
# 1. Run this script with sudo:   sudo bash setup_pi.sh
# 2. Review the script before running.
# 3. A reboot is likely required after running this script.

# --- Check if running as root --- 
if [ \"$(id -u)\" -ne 0 ]; then
  echo \"This script must be run as root (use sudo). Exiting.\" >&2
  exit 1
fi

echo \"Updating package list...\"
apt update

if [ $? -ne 0 ]; then
  echo \"apt update failed. Please check your internet connection and apt sources. Exiting.\" >&2
  exit 1
fi

echo \"Installing liblsl-dev (LabStreamingLayer library)...\"
apt install -y liblsl-dev

if [ $? -ne 0 ]; then
  echo \"Failed to install liblsl-dev. Exiting.\" >&2
  exit 1
fi

echo \"Installing libcamera-apps (useful for testing and ensuring libcamera stack is present)...\"
apt install -y libcamera-apps

if [ $? -ne 0 ]; then
  echo \"Failed to install libcamera-apps. Installation might still work if libcamera is already present.\"
  # Don't exit here, as libcamera might be built-in
fi

# --- Camera Enablement --- 
# Enabling the camera interface via script is complex and depends on OS version.
# It's often SAFER to do this manually via 'sudo raspi-config' -> Interface Options -> Camera.
# Ensure the LEGACY camera interface is DISABLED if using picamera2/libcamera.
#
# Uncomment ONE of the following methods carefully if you want to try scripting it:
#
# Method 1: Using raspi-config non-interactive (May work on some OS versions)
# echo \"Attempting to enable camera via raspi-config nonint...\"
# raspi-config nonint do_camera 0 # 0 enables the camera, ensure legacy is off separately if needed.
# if [ $? -ne 0 ]; then
#   echo \"raspi-config nonint command failed. Please enable the camera manually using 'sudo raspi-config'.\"
# fi
#
# Method 2: Editing /boot/config.txt or /boot/firmware/config.txt (More direct, more dangerous)
# CONFIG_FILE=\"/boot/config.txt\" # Check if /boot/firmware/config.txt exists on newer OS and use that instead
# echo \"Checking $CONFIG_FILE for camera settings...\"
# if [ -f \"$CONFIG_FILE\" ]; then
#   # Ensure start_x=1 and gpu_mem=128 (often recommended for camera)
#   grep -q '^start_x=1' \"$CONFIG_FILE\" || echo 'start_x=1' >> \"$CONFIG_FILE\"
#   grep -q '^gpu_mem=128' \"$CONFIG_FILE\" || echo 'gpu_mem=128' >> \"$CONFIG_FILE\"
#   # Add other necessary dtoverlays if needed, ensure not commented out
#   echo \"Modified $CONFIG_FILE. Manual review recommended.\"
# else
#   echo \"Warning: Could not find $CONFIG_FILE. Cannot automatically configure camera settings.\"
# fi

echo \"-----------------------------------------------------\" 
echo \"System dependency installation process finished.\"
echo \"Camera Interface: Please ensure the camera is enabled\"
echo \"using 'sudo raspi-config' (Interface Options -> Camera).\";
echo \"Make sure the LEGACY camera interface is DISABLED.\"
echo \"\";
echo \"IMPORTANT: A REBOOT is likely required for changes\"
echo \"(especially camera settings) to take effect.\"
echo \"Please run 'sudo reboot' now if you made changes.\"
echo \"-----------------------------------------------------\"

exit 0 