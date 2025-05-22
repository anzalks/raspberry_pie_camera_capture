# IMX296 Global Shutter Camera System

This repository contains scripts and utilities for capturing video from an IMX296 global shutter camera on Raspberry Pi.

## Features

- High-frame-rate video capture with IMX296 global shutter camera
- Real-time video streaming and recording
- Lab Streaming Layer (LSL) integration for synchronization with other data streams
- Status dashboard and monitoring tools
- Systemd service for automatic startup

## Hardware Requirements

- Raspberry Pi 4 or newer (tested on Raspberry Pi 4B 4GB/8GB)
- IMX296 Global Shutter Camera (connected via CSI interface)
- Adequate power supply (5V/3A recommended)

## Software Requirements

- Raspberry Pi OS Bullseye or newer
- Python 3.9+
- libcamera and v4l2 utilities
- FFmpeg for video encoding
- liblsl and pylsl for Lab Streaming Layer support

## Installation

### Automatic Installation

1. Clone this repository:
   ```bash
   git clone https://github.com/anzalks/raspberry_pie_camera_capture.git
   cd raspberry_pie_camera_capture
   ```

2. Run the installation script (requires sudo):
   ```bash
   sudo bash bin/install.sh
   ```

   This script will:
   - Install system dependencies
   - Build and install liblsl from source (v1.14.0)
   - Set up Python virtual environment with required packages
   - Install pylsl matching the liblsl version
   - Configure file permissions
   - Install systemd service
   - Test the camera and LSL functionality

### Manual Installation

If you prefer to install manually, follow these steps:

1. Install system dependencies:
   ```bash
   sudo apt update
   sudo apt install -y python3-pip python3-venv libcamera-apps ffmpeg v4l-utils build-essential cmake pkg-config libasio-dev git
   ```

2. Build and install liblsl from source:
   ```bash
   # Clone liblsl repository (specific version)
   git clone --branch v1.14.0 https://github.com/sccn/liblsl.git
   cd liblsl
   mkdir build && cd build
   
   # Build and install
   cmake ..
   cmake --build . -j$(nproc)
   sudo make install
   sudo ldconfig
   cd ../..
   ```

3. Create Python virtual environment and install dependencies:
   ```bash
   python3 -m venv .venv
   .venv/bin/pip install --upgrade pip wheel setuptools
   .venv/bin/pip install "pylsl==1.14.0" pyyaml requests psutil numpy
   ```

4. Create directories and set permissions:
   ```bash
   mkdir -p logs recordings
   chmod -R 777 logs recordings
   ```

5. Make scripts executable:
   ```bash
   chmod +x bin/run_imx296_capture.py
   chmod +x bin/restart_camera.sh
   chmod +x bin/view-camera-status.sh
   chmod +x bin/diagnose_camera.sh
   chmod +x bin/check_recording.sh
   ```

6. Install systemd service:
   ```bash
   sudo cp config/imx296-camera.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable imx296-camera.service
   sudo systemctl start imx296-camera.service
   ```

## Usage

### Starting and Stopping the Service

Start the camera service:
```bash
sudo systemctl start imx296-camera.service
```

Stop the camera service:
```bash
sudo systemctl stop imx296-camera.service
```

Check service status:
```bash
sudo systemctl status imx296-camera.service
```

### Monitoring the Camera

To view the camera status dashboard:
```bash
bin/view-camera-status.sh
```

### Diagnostics and Troubleshooting

If you encounter issues, run the diagnostic script:
```bash
sudo bin/diagnose_camera.sh
```

For more targeted diagnostics, you can run specific checks:
```bash
sudo bin/diagnose_camera.sh --camera     # Check only camera hardware
sudo bin/diagnose_camera.sh --venv       # Check Python environment
sudo bin/diagnose_camera.sh --liblsl     # Check liblsl installation
sudo bin/diagnose_camera.sh --lsl-compat # Test LSL compatibility
sudo bin/diagnose_camera.sh --test       # Run a camera test capture
```

If you need to restart the camera system:
```bash
sudo bin/restart_camera.sh
```

## Common Issues

### LSL Installation Issues

If you encounter errors with LSL functionality:

1. Check if liblsl is properly installed:
   ```bash
   sudo ldconfig -p | grep liblsl
   ```

2. Check pylsl and its version:
   ```bash
   .venv/bin/pip show pylsl
   ```

3. If you need to reinstall pylsl with a compatible version, try these commands in order:
   ```bash
   # Try these versions in sequence until one works
   .venv/bin/pip install pylsl==1.12.2
   .venv/bin/pip install pylsl==1.15.0
   .venv/bin/pip install pylsl==1.16.1
   
   # As a last resort, try the latest version
   .venv/bin/pip install pylsl
   ```

4. Test compatibility:
   ```bash
   sudo bin/diagnose_camera.sh --lsl-compat
   ```

### Missing pylsl Package

If you encounter errors about the `pylsl` package:
```
ImportError: No module named 'pylsl'
```

Install it using:
```bash
.venv/bin/pip install pylsl
```

### Zero-byte Recording Files

If your recordings are 0 bytes in size, try:
1. Run the diagnostic tool: `sudo bin/diagnose_camera.sh`
2. Restart the camera: `sudo bin/restart_camera.sh`
3. Check the system logs: `journalctl -u imx296-camera.service -n 50`

### Camera Not Detected

If the camera is not detected:
1. Check the physical connection
2. Run `libcamera-hello --list-cameras` to verify system detection
3. Ensure the camera ribbon cable is properly seated in both the camera and Raspberry Pi

## Configuration

Edit the configuration file at `config/config.yaml` to customize:
- Camera settings (resolution, framerate)
- Recording parameters
- LSL stream configuration
- Notification settings

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Author

Anzal KS <anzal.ks@gmail.com>

## Acknowledgments

- Raspberry Pi Foundation for libcamera
- Lab Streaming Layer (LSL) community

## IMX296 Global Shutter Camera Support

This project provides scripts to capture video from the IMX296 global shutter camera on Raspberry Pi.

### Setup and Troubleshooting

The IMX296 camera requires specific configuration to work properly. We've created two scripts to help:

1. **Fix IMX296 Camera Configuration**:
   ```bash
   sudo bin/fix_imx296_camera.sh
   ```
   This script:
   - Configures the IMX296 camera module with compatible_mode=1
   - Sets up the correct 400x400 pixel ROI that the camera natively supports
   - Creates proper udev rules and permissions
   - Ensures proper device tree overlay in /boot/config.txt

2. **Capture Video**:
   ```bash
   sudo bin/capture_imx296.sh [width] [height] [framerate] [duration_ms] [shutter_us]
   ```
   
   Example for 10-second capture at 400x400 resolution with 30fps:
   ```bash
   sudo bin/capture_imx296.sh 400 400 30 10000
   ```
   
   The script automatically:
   - Detects if you're running Debian Bullseye or Bookworm and adjusts format accordingly
   - Uses RAM disk (/dev/shm) for fast recording
   - Handles the appropriate format for your system (MKV/MJPEG for Bookworm, MP4/H264 for Bullseye)
   - Copies completed recordings to ~/recordings directory

### Common IMX296 Camera Issues and Solutions

1. **Invalid Argument Error**: If you see "Failed to start streaming: Invalid argument", it means the camera configuration doesn't match its native capabilities. Run the fix script.

2. **Zero-byte Files**: If your recordings result in 0-byte files, this is usually a format/resolution mismatch. The IMX296 reports a native 400x400-SBGGR10_1X10 format, which is what our scripts configure.

3. **Black Frames**: If you get video files with black frames, try adjusting exposure with the shutter parameter: `capture_imx296.sh 400 400 30 5000 8000`

4. **Incompatible Format**: On newer Debian Bookworm, use MKV/MJPEG format instead of MP4/H264 (our scripts detect this automatically).

### Additional Tools

- `bin/diagnose_camera.sh` - Comprehensive diagnostic tool
- `bin/install.sh` - Complete installation script 