# IMX296 Global Shutter Camera Capture System

A specialized system for Raspberry Pi to capture high-speed, cropped video from an IMX296 global shutter camera with 
pre-trigger buffering, remote control via ntfy.sh, and LSL metadata streaming.

Author: Anzal KS <anzal.ks@gmail.com>

## Features

- **Hardware Cropping**: Uses `media-ctl` to configure a 400x400 pixel hardware crop on the IMX296 sensor
- **High Frame Rate**: Captures at 100 FPS with global shutter mode
- **RAM Buffer**: Maintains a 10-20 second rolling buffer of frames in RAM
- **Remote Trigger**: Control recording via ntfy.sh notifications
- **LSL Integration**: Streams metadata with timestamps and recording status
- **MKV Output**: Records to robust Matroska format video files via FFmpeg
- **Detailed Status**: Verbose status output via tmux for monitoring
- **Service Integration**: Runs as a systemd service with auto-restart capability

## Requirements

### Hardware

- Raspberry Pi (4 or 5 recommended)
- IMX296 global shutter camera (connected via MIPI CSI-2)
- At least 2GB of RAM (4GB+ recommended)

### Software

- Raspberry Pi OS Bookworm or later
- Python 3.7+
- libcamera-apps (for libcamera-vid and libcamera-hello)
- v4l-utils (for media-ctl)
- ffmpeg
- tmux
- Python packages: requests, pylsl, pyyaml, psutil

## Installation

1. Clone this repository:
   ```bash
   git clone https://github.com/anzalks/raspberry_pie_camera_capture.git
   cd raspberry_pie_camera_capture
   ```

2. Run the installation script:
   ```bash
   sudo bin/install.sh
   ```

3. Edit the configuration file:
   ```bash
   nano config/config.yaml
   ```
   
   Be sure to customize:
   - `ntfy.topic` - Set a unique ntfy.sh topic name
   - `camera.exposure_time_us` - Adjust if needed for your lighting conditions
   - `recording.output_dir` - Change recording location if desired

4. Start the service:
   ```bash
   sudo systemctl start imx296-camera.service
   ```

5. Enable the service to start on boot:
   ```bash
   sudo systemctl enable imx296-camera.service
   ```

## Usage

### Viewing Camera Status

The system provides a comprehensive dashboard for monitoring camera status:

```bash
bin/view-camera-status.sh
```

This will directly launch the dashboard interface that shows:
- Service status and uptime
- Frame buffer statistics and fullness
- Recording status and file information
- Recent recordings list
- LSL stream data
- Remote control commands

#### Dashboard Options

You can use the following command-line options:

- Default (no options): Directly launch the dashboard
- `--menu`: Show the traditional menu instead of launching the dashboard directly
- `--auto`: Auto-start mode (attempts to start the service if not running)
- `--help`: Display help information

#### Auto-Launch Setup

To configure the dashboard to automatically launch when the camera service starts:

```bash
sudo bin/view-camera-status.sh --setup-auto-launch
```

This creates a systemd hook that will open a terminal window with the dashboard whenever the camera service starts.

#### Quick Launch Options

For easier access, the system provides:

1. **Simple launcher script**:
   ```bash
   bin/dashboard.sh
   ```
   This checks if the service is running, offers to start it if needed, and launches the dashboard.

2. **Desktop shortcut**:
   During installation, you can choose to install a desktop shortcut that opens the dashboard directly.

### Controlling Recording

The system listens for commands via ntfy.sh. To control recording:

- **Start Recording**:
  ```bash
  curl -d "start" https://ntfy.sh/YOUR_TOPIC
  ```

- **Stop Recording**:
  ```bash
  curl -d "stop" https://ntfy.sh/YOUR_TOPIC
  ```

- **Shutdown Script**:
  ```bash
  curl -d "shutdown_script" https://ntfy.sh/YOUR_TOPIC
  ```

### Recordings Location

Recordings are saved to the `recordings` directory by default, in MKV format with timestamps in the filename.

### LSL Stream

The system creates an LSL stream named "IMX296_Metadata" with the following channels:

1. `CaptureTimeUnix`: Unix timestamp of frame capture
2. `ntfy_notification_active`: 1.0 when recording, 0.0 when not recording
3. `session_frame_no`: Sequential frame number within the current recording session

## Configuration

The configuration file is located at `config/config.yaml`. Here are the key configuration options:

### Camera Settings

```yaml
camera:
  width: 400                    # Target width in pixels
  height: 400                   # Target height in pixels
  fps: 100                      # Target frame rate
  exposure_time_us: 9000        # Exposure time in microseconds
```

### Buffer Settings

```yaml
buffer:
  duration_seconds: 15          # RAM buffer duration in seconds
  max_frames: 1500              # Maximum frames in buffer
```

### NTFY Settings

```yaml
ntfy:
  server: "https://ntfy.sh"     # NTFY server URL
  topic: "raspie-camera"        # NTFY topic (CHANGE THIS!)
```

### LSL Settings

```yaml
lsl:
  stream_name: "IMX296_Metadata"   # LSL stream name
  stream_type: "CameraEvents"      # LSL stream type
```

## Troubleshooting

### Camera Not Found

If the camera is not detected, check the connections and try running:

```bash
sudo media-ctl -d /dev/media0 -p
```

This should list all the devices on the media bus. Look for an entry containing "imx296".

### Permission Issues

If you encounter permission issues with the camera devices, run:

```bash
sudo bin/install.sh
```

This will set up the correct permissions for the camera devices.

### Service Not Running

If the service is not running, check its status:

```bash
sudo systemctl status imx296-camera.service
```

### Manual Execution

To run the script manually for testing:

```bash
sudo python3 bin/run_imx296_capture.py --sudo
```

## License

This project is licensed under the MIT License - see the LICENSE file for details. 