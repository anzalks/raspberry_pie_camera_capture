# Raspberry Pi Camera Capture

A Python package for capturing video from Raspberry Pi cameras and streaming frame data over LabStreamingLayer (LSL).

## Features

- **High-Performance Video Capture**: 400x400 resolution at 100fps
- **Pre-trigger Rolling Buffer**: Capture 20 seconds of footage before a trigger event
- **Remote Control**: Start/stop recording via ntfy.sh notifications from any device
- **Date-based Storage**: Organizes recordings by date with separate video and audio folders
- **Audio Capture**: Support for USB microphones with synchronized recording
- **LSL Integration**: Stream video and audio data for research applications
- **Performance Optimization**: CPU core affinity control and threaded writing
- **Unattended Operation**: Run as a system service or daily initialization script

## Quick Start

### Daily Recording Setup

Use the daily initialization script to set up the camera and audio recording system:

```bash
./start-daily-recording.sh
```

This will:
1. Create date-based directories for today (YYYY_MM_DD format)
2. Set up separate video and audio subdirectories
3. Start the camera capture with 400x400 resolution at 100fps
4. Start audio capture from the default USB microphone
5. Configure remote control via ntfy.sh

### Remote Control

Control recording from any device using ntfy.sh:

```bash
# Start recording
curl -d "Start Recording" ntfy.sh/raspie-camera-test

# Stop recording
curl -d "Stop Recording" ntfy.sh/raspie-camera-test
```

You can also use the ntfy.sh mobile app or web interface to send these commands.

### Configuration

Edit `config.yaml` to customize settings:

```yaml
camera:
  resolution:
    width: 400
    height: 400
  fps: 100
  codec: "h264"
  quality: "ultrafast"
  bitrate: 2000000  # 2 Mbps

buffer:
  enabled: true
  duration: 20  # seconds of pre-trigger buffer

# ... other settings ...
```

## Advanced Usage

### Manual Camera Control

```bash
python -m src.raspberry_pi_lsl_stream.camera_capture \
  --width 400 \
  --height 400 \
  --fps 100 \
  --save-video \
  --codec h264 \
  --buffer-size 20 \
  --ntfy-topic raspie-camera-test
```

### Manual Audio Control

```bash
python -m src.raspberry_pi_lsl_stream.cli audio \
  --device default \
  --save-audio \
  --buffer-size 20 \
  --ntfy-topic raspie-camera-test
```

## Installation

```bash
# Clone the repository
git clone https://github.com/anzalks/raspberry_pie_camera_capture.git
cd raspberry_pie_camera_capture

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e .
```

## Requirements

- Raspberry Pi 4 or newer
- Raspberry Pi Camera Module or USB webcam
- USB microphone (optional)
- Python 3.9+
- Internet connection for ntfy.sh remote control

## Author

- Anzal
- Email: anzal.ks@gmail.com
- GitHub: https://github.com/anzalks/
