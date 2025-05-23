# IMX296 Global Shutter Camera for Raspberry Pi

This repository contains the code for setting up and running an IMX296 global shutter camera on a Raspberry Pi.

## Features

- Captures from IMX296 global shutter camera at 400x400 resolution
- Supports 100fps native capture in raw SBGGR10_1X10 format
- Records video using H264 codec in MKV format (previously used MJPEG)
- Streams data to LSL (Lab Streaming Layer) with numeric values
- Web dashboard for monitoring camera status

## Installation

Run the installation script on your Raspberry Pi:

```bash
git clone https://github.com/anzalks/raspberry_pie_camera_capture.git
cd raspberry_pie_camera_capture
chmod +x install.sh
sudo ./install.sh
```

The script will:
1. Check for required dependencies
2. Install Python packages
3. Create necessary directories
4. Apply fixes for common issues
5. Set up a systemd service

## Configuration

Edit the `config.yaml` file to adjust settings:

```yaml
# IMX296 Camera Configuration
camera:
  width: 400
  height: 400
  fps: 100
  format: "SBGGR10_1X10"  # Native format for IMX296
  libcamera_path: "/usr/bin/libcamera-vid"
  ffmpeg_path: "/usr/bin/ffmpeg"

recording:
  enabled: true
  output_dir: "/home/dawg/recordings"  # Will be created if it doesn't exist
  codec: "h264"  # Using H264 for better compatibility
  format: "mkv"   # Use MKV for better recovery from crashes
  compression_level: 5
  
lsl:
  enabled: true
  stream_name: "IMX296Camera"
  stream_type: "VideoEvents"
  stream_id: "imx296_01"
  
web:
  enabled: true
  host: "0.0.0.0"
  port: 8080
  update_interval_ms: 500
```

## Troubleshooting

### Common Issues & Fixes

1. **Empty recording files (4KB only)**
   - Fix: Changed codec from MJPEG to H264 which works better with the IMX296 camera
   - Fix: Added `-vsync 0` to ffmpeg command
   - Fix: Added file creation with proper permissions
   - Fix: Ensured output directory exists with proper permissions
   - Solution: Run `sudo bin/fix_codec_h264.sh` to update codec configuration

2. **LSL Stream Not Found**
   - Fix: Ensured all LSL values are numeric (no strings)
   - Fix: Set `lsl_has_string_support = False`
   - Fix: Added explicit float conversion for all numeric values

3. **Missing Recordings Directory**
   - Fix: Auto-creates missing directories with proper permissions
   - Fix: Falls back to /tmp if unable to create specified directory

4. **Camera Codec Compatibility Issues**
   - Problem: MJPEG codec can fail with message "Failed to start streaming: Invalid argument"
   - Fix: Switch to H264 codec which has better compatibility with IMX296
   - Test: Use `sudo bin/test_recordings_fixed.sh` to verify H264 recording works
   - Solution: Run `sudo bin/fix_codec_h264.sh` to update all codec references

## Tools & Scripts

The `bin/` directory contains various helper scripts:

- `fix_camera_issues.sh`: Main script to fix common camera issues
- `fix_codec_h264.sh`: Updates codec configuration to use H264 instead of MJPEG
- `test_recordings_fixed.sh`: Tests H264 recording functionality
- `test_lsl_direct.py`: Tests LSL functionality with numeric values

## Checking Status

Check the status of the camera service:

```bash
sudo systemctl status imx296-camera
```

View logs:

```bash
sudo journalctl -u imx296-camera -f
```

The web dashboard is available at: http://[raspberry-pi-ip]:8080

## Author

Anzal KS <anzal.ks@gmail.com>
https://github.com/anzalks/ 