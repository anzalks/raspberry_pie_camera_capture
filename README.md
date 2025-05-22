# IMX296 Global Shutter Camera Capture System

A high-speed, buffer-based camera capture system for Sony IMX296 global shutter cameras on Raspberry Pi. This system is designed for high frame rate (100fps), hardware-cropped capture with LSL integration for synchronization with other data streams.

## Features

- 100fps capture at 400x400 resolution with hardware cropping via media-ctl
- RAM buffer for pre-trigger storage (up to 15 seconds)
- Remote triggering via ntfy.sh notifications
- Keyboard triggering for local control
- LSL stream for metadata and synchronization
- MKV output via ffmpeg for robust recording
- Detailed status information via dashboard

## Installation

1. Clone this repository:
   ```
   git clone https://github.com/anzalks/raspberry_pie_camera_capture.git
   cd raspberry_pie_camera_capture
   ```

2. Install dependencies:
   ```
   sudo apt update
   sudo apt install -y python3-pip python3-venv libcamera-apps ffmpeg v4l-utils

   # Create virtual environment
   python3 -m venv .venv
   source .venv/bin/activate
   
   # Install Python dependencies
   pip install pyyaml pylsl requests psutil
   ```

3. Install as a service (optional):
   ```
   sudo cp config/imx296-camera.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable imx296-camera.service
   ```

## Usage

### Starting the system

```bash
# Manual start
bin/restart_camera.sh

# Or using systemd
sudo systemctl start imx296-camera.service
```

### Starting/stopping recording

1. Via ntfy.sh:
   ```
   # Start recording
   curl -d "start" https://ntfy.sh/raspie-camera-dawg-123
   
   # Stop recording
   curl -d "stop" https://ntfy.sh/raspie-camera-dawg-123
   ```

2. Via keyboard in the dashboard:
   - Press `S` to start recording
   - Press `P` to stop recording

### Viewing status

```bash
bin/view-camera-status.sh
```

## Troubleshooting

### Common Issues

#### Zero-byte recording files

If your recordings are empty (0 byte files), try the following:

1. Run the diagnostic tool:
   ```
   bin/diagnose_camera.sh
   ```

2. Check recording functionality:
   ```
   bin/check_recording.sh
   ```

3. Make sure you don't have multiple instances of the camera capture running:
   ```
   ps aux | grep 'python3.*imx296.*capture'
   ```

4. If needed, completely reset the camera:
   ```
   bin/restart_camera.sh
   ```

#### Simulated frames in dashboard

If the dashboard shows "simulated frames" instead of actual camera data:

1. Ensure there are no old processes running:
   ```
   ps aux | grep 'simulate\|mock\|fake'
   ```

2. Reset the camera system:
   ```
   bin/restart_camera.sh
   ```

#### LSL errors

If you see LSL errors ("must be real number, not str"), it's due to compatibility issues with older pylsl versions. The system now automatically detects and adapts to string capability.

#### V4L2 streaming errors

If you see "Failed to start streaming: Invalid argument" errors:

1. Try resetting the camera:
   ```
   bin/restart_camera.sh
   ```

2. If that doesn't work, reboot the Raspberry Pi:
   ```
   sudo reboot
   ```

## Configuration

Edit `config/config.yaml` to customize:

- Camera settings (resolution, fps, exposure)
- Buffer settings (duration, max frames)
- Recording format and location
- ntfy.sh topic for remote control
- LSL stream parameters

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Author

Anzal KS <anzal.ks@gmail.com>
https://github.com/anzalks/ 