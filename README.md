# IMX296 Global Shutter Camera for Raspberry Pi

This repository contains the code for setting up and running an IMX296 global shutter camera on a Raspberry Pi.

## Features

- Captures from IMX296 global shutter camera at 400x400 resolution
- Supports 100fps native capture in raw SBGGR10_1X10 format
- Records video using MJPEG codec in MKV format
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
  format: "SBGGR10_1X10"
  libcamera_path: "/usr/bin/libcamera-vid"
  ffmpeg_path: "/usr/bin/ffmpeg"

recording:
  enabled: true
  output_dir: "/home/dawg/recordings"
  codec: "mjpeg"
  format: "mkv"
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
   - Fix: Added `-vsync 0` to ffmpeg command
   - Fix: Added file creation with proper permissions
   - Fix: Ensured output directory exists with proper permissions

2. **LSL Stream Not Found**
   - Fix: Ensured all LSL values are numeric (no strings)
   - Fix: Set `lsl_has_string_support = False`
   - Fix: Added explicit float conversion for all numeric values

3. **Missing Recordings Directory**
   - Fix: Auto-creates missing directories with proper permissions
   - Fix: Falls back to /tmp if unable to create specified directory

## Tools & Scripts

The `bin/` directory contains various helper scripts:

- `fix_camera_issues.sh`: Main script to fix common camera issues
- Diagnostic tools for testing camera and LSL functionality

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