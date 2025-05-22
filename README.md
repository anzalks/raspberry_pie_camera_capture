# Raspberry Pi Camera Capture System

A camera capture system for Raspberry Pi that supports both standard and Global Shutter cameras.

## Features

- Supports standard Raspberry Pi Camera Module
- Supports Global Shutter Camera (IMX296 sensor) with high frame rates (up to 536fps)
- Real-time video capture and streaming
- LSL marker stream integration
- Video encoding with timestamp overlay
- Status monitoring via interactive terminal UI
- Automatic date-based recording folder structure
- Trigger recording via ntfy notifications

## Prerequisites

- Raspberry Pi 4 or newer (8GB RAM recommended)
- Raspberry Pi OS Bullseye or newer (including Bookworm)
- Connected camera (Standard Pi Camera or Global Shutter Camera)
- Python 3.7 or newer

## Raspberry Pi OS Bookworm Compatibility

This system has been updated to fully support Raspberry Pi OS Bookworm. The following changes were made:

- Automatic detection of Bookworm OS and adjustments to dependencies
- Support for the `--no-raw` workaround needed for Global Shutter Camera on Bookworm
- Handling of `media-ctl` package changes (now included in `v4l-utils`)
- Smart detection of OS-provided tools with automatic fallback to building from source if needed

When running on Bookworm, the system will automatically:
1. Check if the OS-provided `v4l-utils` and `media-ctl` are available and working properly
2. Use the OS-provided tools if they work correctly with the camera
3. Only build from source if the OS-provided tools aren't available or don't work with the camera
4. Apply the `--no-raw` workaround for libcamera

**Important Note:** To run on Raspberry Pi OS Bookworm, you should first run the setup script with sudo:
```bash
sudo ./scripts/run-camera.sh
```
This will check the system, install required packages, and build tools from source only if needed. The script will exit after setup is complete, and you can then run it normally.

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
./scripts/run-camera.sh
```

This script:
- Checks your environment and camera setup
- Configures camera permissions if needed
- Automatically detects Global Shutter Camera if present
- Offers optimal crop configurations for high frame rates
- Creates date-based folders for recordings (`recordings/YYYY-MM-DD/`)
- Starts the camera capture with interactive terminal UI

### Interactive Terminal UI

The system now includes an interactive terminal UI that displays:
- Camera model and resolution
- Current frame rate
- Frames captured and written
- Buffer status
- Recording status
- Available commands

You can use the following commands to control recording:
```bash
# Start recording
curl -d "Start Recording" ntfy.sh/raspie-camera-test

# Stop recording
curl -d "Stop Recording" ntfy.sh/raspie-camera-test
```

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

To run the camera capture as a service, use our helper script:

```bash
# Install the service
./scripts/camera-service.sh install

# Enable to start at boot
./scripts/camera-service.sh enable

# Start the service
./scripts/camera-service.sh start
```

The service management script provides several commands:

```bash
./scripts/camera-service.sh {start|stop|restart|status|enable|disable|recordings|logs|install|check}
```

- **start**: Start the camera service
- **stop**: Stop the camera service
- **restart**: Restart the camera service
- **status**: Check service status and recording path
- **enable**: Enable service to start at boot
- **disable**: Disable service from starting at boot
- **recordings**: Show recent recordings with paths
- **logs**: Show service logs
- **install**: Install the service file
- **check**: Run camera environment check

## Recordings and Storage

The system automatically creates a date-based folder structure for recordings:

```
recordings/
└── YYYY-MM-DD/
    └── recording_YYYYMMDD_HHMMSS.mkv
```

Each recording session uses the MKV container format with MJPG codec for compatibility and high frame rate support. 

The system utilizes a 20-second rolling buffer by default, which allows you to capture events that have already happened when you trigger a recording.

To view your recordings, use:

```bash
# Show today's recordings with details
./scripts/camera-service.sh recordings
```

## Troubleshooting

### Camera Not Detected

If your camera is not detected:

1. Run the environment check tool:
   ```bash
   ./bin/check-camera-env.py
   # or
   ./scripts/camera-service.sh check
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
   If this returns a result, you're on Bookworm OS and the `--no-raw` flag will be applied automatically.

3. If you're on Bookworm OS, make sure you've built v4l-utils from source:
   ```bash
   # Run the script with sudo first to build the tools
   sudo ./scripts/run-camera.sh
   
   # Then verify the installation
   media-ctl --version
   v4l2-ctl --version
   ```
   
   Both tools should show that they are installed and working. The tools must be built from source on Bookworm OS.

4. If media-ctl reports errors like "Cannot find entity" or similar:
   ```bash
   # Check if the devices have proper permissions
   ls -la /dev/media*
   
   # Fix permissions
   sudo chmod 666 /dev/media*
   
   # Check if the camera is properly connected
   vcgencmd get_camera
   ```

5. Try a known working configuration manually:
   ```bash
   # For 400fps:
   media-ctl -d /dev/media0 --set-v4l2 "'imx296 10-001a':0 [fmt:SBGGR10_1X10/688x136 crop:(384,476)/688x136]" -v
   ```

6. If using libcamera-hello to verify the configuration on Bookworm OS:
   ```bash
   libcamera-hello --no-raw --list-cameras
   ```

### LSL Stream Issues

If you encounter LSL stream errors:

1. The system now includes automatic fixes for common LSL issues
2. If you still see "StreamInfo deletion triggered error", this is now handled automatically
3. You can check LSL stream status with:
   ```bash
   python3 -c "from pylsl import resolve_streams; print(resolve_streams())"
   ```

### Common Errors

- **Failed to open camera**: Ensure camera is properly connected and enabled in raspi-config
- **Permission denied**: Run `sudo chmod 666 /dev/video*` and `sudo chmod 666 /dev/media*` to fix permissions
- **Preview not showing**: Ensure X server is running and DISPLAY environment variable is set
- **Lock file issues**: Run `sudo rm -f /tmp/raspie_camera.lock` and then `sudo touch /tmp/raspie_camera.lock && sudo chmod 666 /tmp/raspie_camera.lock`
- **media-ctl command failing**: Check the device ID (10 for RPi 4, 10/11 for RPi 5 cameras)
- **ntfy subscription timeout**: This is normal and will auto-reconnect - the system is designed to handle these
- **No recordings directory**: The system automatically creates `recordings/YYYY-MM-DD/` folders. If missing, run `mkdir -p recordings/$(date +%Y-%m-%d)`

## Acknowledgments

- [Hermann-SW](https://github.com/Hermann-SW) for the Global Shutter Camera cropping technique that enables high frame rates ([reference gist](https://gist.github.com/Hermann-SW/e6049fe1a24fc2b5a53c654e0e9f6b9c))
