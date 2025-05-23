# Raspberry Pi IMX296 High-FPS Camera Recorder

This Python script enables high-speed camera recording with an IMX296 global shutter camera on Raspberry Pi, featuring RAM buffering, remote control via ntfy.sh notifications, and LSL metadata streaming.

## Features

- **High-FPS Recording**: Captures 400x400 pixel video at 100 FPS from an IMX296 global shutter camera
- **Hardware Cropping**: Uses media-ctl to configure the sensor's V4L2 subdevice before libcamera interaction
- **RAM Buffer**: Stores the most recent 10-20 seconds of video in RAM
- **Remote Control**: Uses ntfy.sh notifications to start and stop recording
- **LSL Integration**: Streams frame metadata via Lab Streaming Layer
- **MKV Output**: Records to MKV via ffmpeg
- **Detailed Status**: Provides comprehensive status output in terminal

## Prerequisites

Install the required system packages:

```bash
# Update package list
sudo apt update

# Install system dependencies
sudo apt install -y python3-pip python3-venv libcamera-apps v4l-utils ffmpeg tmux

# Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install requests pylsl psutil
```

## Configuration

The script can be configured using a JSON configuration file. Create a file named `config.json` with the following structure:

```json
{
  "TARGET_WIDTH": 400,
  "TARGET_HEIGHT": 400,
  "TARGET_FPS": 100,
  "EXPOSURE_TIME_US": 9000,
  "RAM_BUFFER_DURATION_SECONDS": 15,
  "NTFY_SERVER": "https://ntfy.sh",
  "NTFY_TOPIC": "rpi_camera_trigger",
  "RECORDING_PATH": "recordings",
  "LSL_STREAM_NAME": "IMX296_Metadata",
  "LSL_STREAM_TYPE": "CameraEvents"
}
```

## Usage

### Running the Script

```bash
# Run with default settings
python high_fps_camera_recorder.py

# Run with custom configuration
python high_fps_camera_recorder.py --config config.json
```

### Remote Control Commands

Send notifications to the ntfy.sh topic to control the recording:

```bash
# Start recording
curl -d "start recording" ntfy.sh/rpi_camera_trigger

# Stop recording
curl -d "stop recording" ntfy.sh/rpi_camera_trigger

# Shutdown script
curl -d "shutdown_script" ntfy.sh/rpi_camera_trigger
```

### Running as a Service

Create a systemd service file at `/etc/systemd/system/camera-recorder.service`:

```
[Unit]
Description=IMX296 High-FPS Camera Recorder
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/path/to/script/directory
ExecStartPre=/usr/bin/tmux new-session -d -s camera_recorder
ExecStart=/usr/bin/tmux send-keys -t camera_recorder "cd /path/to/script/directory && source venv/bin/activate && python high_fps_camera_recorder.py --config config.json" C-m
ExecStop=/usr/bin/tmux send-keys -t camera_recorder C-c
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
```

Enable and start the service:

```bash
sudo systemctl enable camera-recorder.service
sudo systemctl start camera-recorder.service
```

View the tmux session:

```bash
tmux attach -t camera_recorder
```

## LSL Metadata Stream

The script creates an LSL outlet with the following channels:

1. `CaptureTimeUnix`: Frame capture timestamp in Unix epoch time (seconds)
2. `ntfy_notification_active`: Recording status (1.0 for active, 0.0 for inactive)
3. `session_frame_no`: Sequential frame number within the current recording session

## Troubleshooting

- **Camera not found**: Verify the IMX296 camera is properly connected and recognized by the system
- **media-ctl errors**: Ensure you have the correct permissions (the script uses sudo for media-ctl)
- **Memory issues**: Adjust RAM_BUFFER_DURATION_SECONDS if you experience memory pressure

## License

This project is licensed under the MIT License - see the LICENSE file for details. 