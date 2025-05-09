# Raspberry Pi Camera Capture

A Python package for capturing video from Raspberry Pi cameras and streaming frame data over LabStreamingLayer (LSL).

## Features

- **High-Performance Video Capture**: 400x400 resolution at 100fps
- **Optimized Video Format**: MJPG codec with MKV container for high frame rate recording
- **Pre-trigger Rolling Buffer**: Capture 20 seconds of footage before a trigger event
- **Remote Control**: Start/stop recording via ntfy.sh notifications from any device
- **Date-based Storage**: Organizes recordings by date with separate video and audio folders
- **Audio Capture**: Support for USB microphones with synchronized recording
- **LSL Integration**: Stream frame numbers via LSL for synchronization with other data streams
- **Performance Optimization**: CPU core affinity control and threaded writing
- **Unattended Operation**: Run as a system service or daily initialization script
- **Native BGR Format**: Uses native BGR format directly from the camera without conversion

## Quick Start

### Daily Recording Setup

Use the daily initialization script to set up the camera and audio recording system:

```bash
./start-daily-recording.sh
```

This will:
1. Create date-based directories for today (YYYY_MM_DD format)
2. Set up separate video and audio subdirectories
3. Start the camera capture with 400x400 resolution at 100fps using MJPG codec
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
  codec: "mjpg"  # Use MJPG for high frame rate recording
  container: "mkv"  # MKV container provides better support for MJPG
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
  --codec mjpg \
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

# Create virtual environment with system packages
python -m venv --system-site-packages .venv
source .venv/bin/activate

# Install dependencies
pip install -e .
```

## Technical Notes

- **Codec Selection**: MJPG (Motion JPEG) is recommended for high frame rates (100fps) at 400x400 resolution
- **Container Format**: MKV containers are used for better compatibility with MJPG codec
- **LSL Integration**: Only frame numbers are streamed over LSL to minimize bandwidth and CPU usage
- **Camera API**: Uses picamera2 with direct BGR format capture for best performance
- **Raspberry Pi ID**: Uses the Pi's unique serial number as the LSL source ID for better device tracking
- **Fallback Mechanisms**: Multiple fallback options for codec/container compatibility

## Requirements

- Raspberry Pi 4 or newer
- Raspberry Pi Camera Module (v2 or v3 recommended)
- USB microphone (optional)
- Python 3.9+
- Internet connection for ntfy.sh remote control
- System-level installation of picamera2 and libcamera packages

## Author

- Anzal
- Email: anzal.ks@gmail.com
- GitHub: https://github.com/anzalks/
