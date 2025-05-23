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

## Installation

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

## Basic Usage

The camera service starts automatically on boot. You can control it with:

```bash
# Check service status
sudo systemctl status imx296-camera.service

# Start/stop/restart service
sudo systemctl start imx296-camera.service
sudo systemctl stop imx296-camera.service
sudo systemctl restart imx296-camera.service

# View logs
sudo journalctl -u imx296-camera.service
```

## Recordings

Recordings are stored in `/home/dawg/recordings` by default, using the MKV container format. Each file is named with a timestamp.

## Configuration

Edit the configuration file to customize camera settings:

```bash
sudo nano /etc/imx296-camera/config.yaml
```

Key configuration options:
- `camera.width` and `camera.height`: Camera resolution (IMX296 native is 400x400)
- `camera.fps`: Frame rate (default: 30fps)
- `camera.exposure_time_us`: Exposure time in microseconds
- `recording.codec`: Video codec (mjpeg or h264)
- `recording.output_dir`: Where to save recordings

After changing the configuration, restart the service:

```bash
sudo systemctl restart imx296-camera.service
```

## Troubleshooting

### Common Issues

1. **Empty 4KB video files**
   - Problem: FFmpeg creates empty files containing only headers
   - Solution: Make sure the correct codec is specified in config (mjpeg or h264) and that it matches in both the camera and ffmpeg commands
   - Run the diagnostic script: `test_direct_capture.py`

2. **Missing Recording Directory**
   - Problem: "Recording directory does not exist" errors in logs
   - Solution: Create the directory and set permissions
   ```bash
   sudo mkdir -p /home/dawg/recordings
   sudo chown -R dawg:dawg /home/dawg/recordings
   sudo chmod -R 777 /home/dawg/recordings
   ```

3. **LSL Stream Configuration**
   - Problem: "No LSL stream configuration found" in dashboard
   - Solution: Check LSL configuration in the YAML file and restart the service

4. **Permission Errors**
   - Problem: Cannot access camera or write to output directory
   - Solution: Ensure the user is in the 'video' group and has write access to the output directory
   ```bash
   sudo usermod -a -G video dawg
   ```

### Diagnostic Tools

Use the included diagnostic script to test the camera directly:

```bash
# Test direct camera capture
sudo /usr/local/bin/test_direct_capture.py -d 5 -o /tmp/test.mkv

# Check the file size to verify content
ls -lh /tmp/test.mkv
```

If the diagnostic script creates a file larger than 5KB but the service still creates empty files, check the service logs for detailed error messages.

### Advanced Troubleshooting

1. **Verify camera works directly:**
   ```bash
   libcamera-vid --codec mjpeg --width 400 --height 400 --output test.mkv --timeout 2000
   ```

2. **Check ffmpeg pipe functionality:**
   ```bash
   libcamera-vid --codec mjpeg --width 400 --height 400 -o - --timeout 3000 | ffmpeg -f mjpeg -i - -c:v copy test.mkv
   ```

3. **Check system log for libcamera errors:**
   ```bash
   dmesg | grep -i camera
   ```

4. **Verify file permissions:**
   ```bash
   ls -la /home/dawg/recordings/
   ```

## License

MIT License. See LICENSE file for details. 