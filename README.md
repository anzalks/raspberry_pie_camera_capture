# IMX296 Global Shutter Camera for Raspberry Pi

This repository contains code for capturing video from the IMX296 global shutter camera on a Raspberry Pi. It includes systemd services for automatic startup, LSL integration, and advanced camera controls.

**Author:** Anzal KS <anzal.ks@gmail.com>  
**GitHub:** https://github.com/anzalks/raspberry_pie_camera_capture  
**Date:** May 23, 2025

## Features

- 400x400 global shutter video capture at 30fps
- Low-latency encoding with MJPEG codec
- Real-time video streaming via LSL
- Automatic recording to MKV files
- Remote control via ntfy.sh notifications
- Dashboard for camera monitoring
- Diagnostic tools for troubleshooting

## Hardware Requirements

- Raspberry Pi 4 or newer
- IMX296 Global Shutter Camera (400x400 max resolution)
- Sufficient storage for recordings

## Quick Start (No Installation)

Run the camera directly from the repository without system-wide installation:

```bash
# Clone the repository
git clone https://github.com/anzalks/raspberry_pie_camera_capture.git
cd raspberry_pie_camera_capture

# Set up a virtual environment (recommended)
python3 -m venv .venv
source .venv/bin/activate
pip install pylsl pyyaml python-dateutil psutil ntfy

# Run locally (automatically tests camera first)
./install.sh local

# Run in background if needed
./install.sh local --background
```

This will:
1. Create local directories (recordings, logs)
2. Verify the camera works by running a test capture
3. Run the camera software, saving recordings to the local directory

### Running Without Virtual Environment

If you don't want to use a virtual environment, you'll need to install the required packages with your system package manager:

```bash
# Install system packages
sudo apt install python3-pylsl python3-yaml python3-dateutil python3-psutil python3-ntfy

# Then run locally (without sudo)
./install.sh local
```

**Important:** Do not use `sudo` with the local mode, as it may cause Python package installation issues on Debian-based systems due to PEP 668 restrictions.

## System Installation (Optional)

For a complete system installation with systemd services:

```bash
# Clone the repository
git clone https://github.com/anzalks/raspberry_pie_camera_capture.git
cd raspberry_pie_camera_capture

# Install with root privileges
sudo ./install.sh
```

The installation script:
1. Installs required dependencies
2. Sets up the systemd service
3. Configures directories and permissions
4. Performs a basic camera test
5. Starts the service

## Configuration

Edit the config.yaml file to customize camera settings:

```bash
nano config/config.yaml
```

Key configuration options:
- `camera.width` and `camera.height`: Camera resolution (IMX296 native is 400x400)
- `camera.fps`: Frame rate (default: 30fps)
- `camera.exposure_time_us`: Exposure time in microseconds
- `recording.codec`: Video codec (mjpeg or h264)
- `recording.output_dir`: Where to save recordings

After changing the configuration, restart the service or the local instance.

## Troubleshooting

If you encounter issues, use the included diagnostic script:

```bash
sudo ./bin/diagnose_imx296.sh
```

### Common Issues

1. **Empty 4KB video files**
   - Problem: FFmpeg creates empty files containing only headers
   - Solution: Make sure the codec is set to 'mjpeg' in config.yaml

2. **Missing LSL Stream**
   - Problem: "No LSL stream configuration found" in dashboard
   - Solution: Install pylsl with `pip install pylsl`

### Test Individual Components

Test the camera directly:

```bash
sudo ./bin/test_direct_capture.py -d 5
```

This will create a test recording and verify if the camera is working properly.

## License

MIT License. See LICENSE file for details. 