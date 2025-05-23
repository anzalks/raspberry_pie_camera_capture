# Raspberry Pi Camera Capture

## IMX296 Global Shutter Camera Configuration

This repository contains scripts and configuration to work with the IMX296 global shutter camera on Raspberry Pi.

### Issue and Solution

The IMX296 camera requires proper ROI (Region of Interest) configuration via the media control interface before streaming. All attempts to directly use libcamera-vid or similar tools with various resolutions will fail with the error:

```
ERROR V4L2 v4l2_videodevice.cpp:2049 /dev/video4[16:cap]: Failed to start streaming: Invalid argument
```

This is because the camera's native resolution is 400x400 with the SBGGR10_1X10 pixel format, which must be configured properly in the media pipeline.

### Setup Instructions

1. **Install Dependencies**

```bash
sudo apt-get update
sudo apt-get install -y v4l-utils ffmpeg python3-pip python3-venv python3-opencv libcamera-apps
pip3 install pylsl numpy opencv-python flask
```

2. **Quick Install (All Components)**

```bash
git clone https://github.com/anzalks/raspberry_pie_camera_capture.git
cd raspberry_pie_camera_capture
sudo ./install.sh
```

3. **Manual Installation**

If you prefer to install components individually:

```bash
# Test camera configuration first
sudo bin/fix_imx296_roi.sh

# Configure camera service
sudo bin/configure_imx296_service.sh

# Create dashboard
sudo bin/create_dashboard.sh

# Install services
sudo cp config/imx296_camera.service /etc/systemd/system/
sudo cp config/imx296_dashboard.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable imx296_camera.service imx296_dashboard.service
sudo systemctl start imx296_camera.service imx296_dashboard.service
```

4. **Verify Operation**

```bash
# Check service status
sudo systemctl status imx296_camera.service
sudo systemctl status imx296_dashboard.service

# View service logs
sudo journalctl -u imx296_camera.service -f

# Test direct recording (without service)
sudo bin/test_imx296_recording.sh
```

5. **Access the Dashboard**

Open a web browser and navigate to:
```
http://[raspberry-pi-ip]:8080
```

The dashboard provides real-time monitoring of:
- Camera connection status
- Media pipeline configuration
- Recording status and file size
- LSL stream availability
- Frame rate and frame count

### Camera Configuration Details

- Native resolution: 400x400
- Pixel format: SBGGR10_1X10 (10-bit Bayer pattern)
- Pipeline setup:
  - Configure IMX296 sensor format
  - Configure CSI-2 receiver format
  - Configure ISP format (if applicable)

### Components

- **Camera Stream Module**: Handles camera capture and LSL streaming
- **Web Dashboard**: Provides real-time monitoring of camera status
- **Diagnostic Scripts**: Test and configure the camera
- **Systemd Services**: Ensure camera and dashboard run automatically at startup

### Troubleshooting

If you continue to experience issues:

1. Check if the camera is properly connected and detected:
```bash
v4l2-ctl --list-devices
```

2. View camera capabilities:
```bash
v4l2-ctl --device=/dev/videoX --all
```

3. Check media entities:
```bash
media-ctl --device=/dev/media0 --print-topology
```

4. Try direct capture with minimal options:
```bash
# After running the ROI configuration script
sudo bin/imx296_direct_test.sh
```

5. Use the dashboard to monitor camera status and configure the pipeline:
```bash
sudo bin/start_dashboard.sh
```

## Additional Information

- Author: Anzal KS <anzal.ks@gmail.com>
- Repository: https://github.com/anzalks/raspberry_pie_camera_capture 