# IMX296 Camera System File Structure

## Overview
This project captures video from an IMX296 global shutter camera on a Raspberry Pi at 100 FPS using 400x400 resolution. It includes LSL streaming for metadata and MKV file output with MJPEG encoding for robustness against abrupt stops.

## Directory Structure

```
.
├── bin/                      # Executable scripts for operations
│   ├── check_recording.sh    # Checks if recordings are being created properly
│   ├── dashboard.sh          # Launches the monitoring dashboard
│   ├── diagnose_camera.sh    # General camera diagnostic tool
│   ├── diagnose_imx296.sh    # IMX296-specific diagnostics
│   ├── install.sh            # System installation script
│   ├── restart_camera.sh     # Service restart script
│   ├── run_imx296_capture.py # Direct Python runner for the camera
│   ├── test_direct_capture.py # Test direct camera capture
│   └── view-camera-status.sh # Status dashboard script
├── config/                   # Configuration files
│   ├── config.yaml           # Main configuration
│   ├── config.yaml.example   # Example configuration
│   └── imx296-camera.service # Systemd service file
├── src/                      # Source code
│   ├── __init__.py           # Package initialization
│   └── imx296_gs_capture/    # Main camera module
│       ├── __init__.py       # Module initialization
│       └── imx296_capture.py # Core camera capture code
├── fix_camera_issues.sh      # Fix script for common issues
└── README.md                 # Project documentation
```

## Main Scripts

### Core Files
- `src/imx296_gs_capture/imx296_capture.py`: The main camera capture code that handles:
  - Capturing frames from the IMX296 camera
  - Storing frames in a RAM buffer
  - LSL streaming of metadata
  - Recording to MKV files
  - Remote control via ntfy.sh

### Installation
- `bin/install.sh`: System installation script that:
  - Installs required dependencies
  - Sets up directories and permissions
  - Configures the system for camera use
  - Installs the systemd service

### Diagnostics
- `bin/test_direct_capture.py`: Tests direct camera capture without the service to verify camera functionality
- `bin/diagnose_imx296.sh`: Comprehensive diagnostics for the IMX296 camera
- `fix_camera_issues.sh`: Fixes common issues like empty recording files and LSL stream configuration

### Operation
- `bin/view-camera-status.sh`: Dashboard to monitor camera status
- `bin/restart_camera.sh`: Script to restart the camera service
- `bin/check_recording.sh`: Checks if recordings are being created properly

## Known Issues and Solutions

1. **Empty Recording Files (4KB only)**
   - Cause: FFmpeg creates files with headers but no frames
   - Solution: Ensure recording directory exists with proper permissions and use MJPEG codec

2. **Missing LSL Stream Configuration**
   - Cause: LSL stream using string values instead of numeric values
   - Solution: Use numeric values in LSL stream and ensure pylsl is properly installed
   
3. **Performance Issues at High FPS**
   - Cause: System resource limitations on Raspberry Pi
   - Solution: Use 100 FPS with 400x400 resolution and ensure adequate cooling 