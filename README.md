# Raspberry Pi Camera Capture System

A camera capture system for Raspberry Pi that supports both standard and Global Shutter cameras.

## Features

- Supports standard Raspberry Pi Camera Module
- Supports Global Shutter Camera (IMX296 sensor) with high frame rates (up to 536fps)
- Real-time video capture and streaming
- LSL marker stream integration
- Video encoding with timestamp overlay
- Status monitoring via terminal or GUI

## Prerequisites

- Raspberry Pi 4 or newer (8GB RAM recommended)
- Raspberry Pi OS Bullseye or newer
- Connected camera (Standard Pi Camera or Global Shutter Camera)
- Python 3.7 or newer

## Installation

Run the setup script with sudo to install all dependencies:

```bash
sudo ./setup_pi.sh
```

This script will:
1. Install all required system packages
2. Install Python dependencies
3. Set up proper camera permissions
4. Configure the environment for camera access

**Note**: During installation, you might see warnings about "Error parsing dependencies of send2trash" - these are harmless and can be ignored.

## Camera Setup

### Standard Raspberry Pi Camera

For standard Raspberry Pi Camera modules:
1. Connect the camera to the CSI port
2. Enable the camera interface using `sudo raspi-config`
3. Reboot the Raspberry Pi

### Global Shutter Camera

For Global Shutter Camera (IMX296):
1. Connect the camera to the CSI port
2. No additional configuration is needed - the system will automatically detect and configure the Global Shutter Camera

## Usage

### Running the Camera Capture

Use the provided run script:

```bash
./run-camera.sh
```

This script:
- Checks your environment and camera setup
- Configures camera permissions if needed
- Automatically detects Global Shutter Camera if present
- Offers optimal crop configurations for high frame rates
- Starts the camera capture with preview enabled

### Global Shutter Camera High Frame Rate Configurations

The system implements Hermann-SW's technique ([reference](https://gist.github.com/Hermann-SW/e6049fe1a24fc2b5a53c654e0e9f6b9c)) for configuring the Global Shutter Camera to achieve high frame rates. When running the script, you can choose from these optimized configurations:

1. **Maximum Frame Rate (536fps)**: 1456x96 (full width, minimum height)
2. **Balanced Performance (400fps)**: 688x136 (medium crop)
3. **Small ROI (500fps)**: 224x96 (small region of interest)
4. **Square Crop (200fps)**: 600x600 (square, moderate fps)

The cropping technique works by:
1. Calculating a centered crop region on the 1456×1088 sensor
2. Using the `media-ctl` command to configure the crop
3. Ensuring width, height, and crop coordinates are even numbers

### Running as a Service

To run the camera capture as a service:

1. Copy the service file to systemd:
   ```bash
   sudo cp rpi-camera.service /etc/systemd/system/
   ```

2. Enable and start the service:
   ```bash
   sudo systemctl enable rpi-camera.service
   sudo systemctl start rpi-camera.service
   ```

3. Check service status:
   ```bash
   sudo systemctl status rpi-camera.service
   ```

## Troubleshooting

### Camera Not Detected

If your camera is not detected:

1. Run the environment check tool:
   ```bash
   python3 check-camera-env.py
   ```

2. Ensure proper permissions:
   ```bash
   sudo chmod 666 /dev/video*
   sudo chmod 666 /dev/media*  # Important for Global Shutter Camera
   ```

3. Add your user to video group:
   ```bash
   sudo usermod -a -G video $USER
   sudo usermod -a -G input $USER
   ```
   Log out and log back in for the group changes to take effect.

4. For Global Shutter Camera, ensure media-ctl is installed:
   ```bash
   sudo apt install -y libcamera-tools media-ctl
   ```

### Global Shutter Camera Issues

If you have issues with the Global Shutter Camera:

1. Make sure the IMX296 sensor is properly detected:
   ```bash
   for m in {0..5}; do media-ctl -d /dev/media$m -p 2>/dev/null | grep -i "imx296"; done
   ```

2. Check if you need the bookworm OS workaround (--no-raw flag):
   ```bash
   grep "=bookworm" /etc/os-release
   ```

3. Ensure media device permissions are correct:
   ```bash
   sudo chmod 666 /dev/media*
   ```

4. Try a known working configuration manually:
   ```bash
   # For 400fps:
   media-ctl -d /dev/media0 --set-v4l2 "'imx296 10-001a':0 [fmt:SBGGR10_1X10/688x136 crop:(384,476)/688x136]" -v
   ```

### Common Errors

- **Failed to open camera**: Ensure camera is properly connected and enabled in raspi-config
- **Permission denied**: Run `sudo chmod 666 /dev/video*` and `sudo chmod 666 /dev/media*` to fix permissions
- **Preview not showing**: Ensure X server is running and DISPLAY environment variable is set
- **Lock file issues**: Run `sudo rm -f /tmp/raspie_camera.lock` and then `sudo touch /tmp/raspie_camera.lock && sudo chmod 666 /tmp/raspie_camera.lock`
- **media-ctl command failing**: Check the device ID (10 for RPi 4, 10/11 for RPi 5 cameras)

## Acknowledgments

- [Hermann-SW](https://github.com/Hermann-SW) for the Global Shutter Camera cropping technique that enables high frame rates ([reference gist](https://gist.github.com/Hermann-SW/e6049fe1a24fc2b5a53c654e0e9f6b9c))
