# IMX296 Camera System Utility Scripts

This directory contains utility scripts for installing, running, and diagnosing the IMX296 camera system.

## Installation Scripts
- `install.sh`: Main installation script

## Diagnostic Scripts
- `diagnose_imx296.sh`: Comprehensive diagnostic for the IMX296 camera
- `diagnose_camera.sh`: General camera diagnostic
- `test_direct_capture.py`: Test direct camera capture without the service
- `check_recording.sh`: Check if recordings are working correctly

## Operational Scripts
- `view-camera-status.sh`: View camera status dashboard
- `restart_camera.sh`: Restart the camera service
- `run_imx296_capture.py`: Run the camera capture directly
- `dashboard.sh`: Launch the monitoring dashboard

## Usage
Most scripts should be run with sudo to ensure proper permissions:

```bash
sudo ./diagnose_imx296.sh
sudo ./test_direct_capture.py -d 5
./view-camera-status.sh
```
