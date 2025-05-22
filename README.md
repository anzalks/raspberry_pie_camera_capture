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
- pylsl for Lab Streaming Layer support

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
   - Set up Python virtual environment with required packages
   - Install pylsl for Lab Streaming Layer support
   - Configure file permissions
   - Install systemd service
   - Test the camera

### Manual Installation

If you prefer to install manually, follow these steps:

1. Install system dependencies:
   ```bash
   sudo apt update
   sudo apt install -y python3-pip python3-venv libcamera-apps ffmpeg v4l-utils
   ```

2. Create a Python virtual environment:
   ```bash
   python3 -m venv .venv
   .venv/bin/pip install --upgrade pip
   .venv/bin/pip install pylsl pyyaml requests psutil
   ```

3. Create directories and set permissions:
   ```bash
   mkdir -p logs recordings
   chmod -R 777 logs recordings
   ```

4. Make scripts executable:
   ```bash
   chmod +x bin/run_imx296_capture.py
   chmod +x bin/restart_camera.sh
   chmod +x bin/view-camera-status.sh
   chmod +x bin/diagnose_camera.sh
   chmod +x bin/check_recording.sh
   ```

5. Install systemd service:
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
sudo bin/diagnose_camera.sh --camera  # Check only camera hardware
sudo bin/diagnose_camera.sh --venv    # Check Python environment
sudo bin/diagnose_camera.sh --test    # Run a camera test capture
```

If you need to restart the camera system:
```bash
sudo bin/restart_camera.sh
```

## Common Issues

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