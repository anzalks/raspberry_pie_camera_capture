# Raspberry Pi Camera and Audio Capture

Camera and audio capture system for Raspberry Pi with LSL integration and ntfy notifications.

## Features

- Camera auto-detection (PiCamera or webcam)
- Audio capture from USB microphones
- Real-time preview for both audio and video
- Video and audio recording with pre-trigger buffer
- LSL streaming
- ntfy notifications for remote control
- Status display in terminal
- CPU core affinity management for performance optimization

## Installation

1. Clone the repository:
```bash
git clone https://github.com/anzalks/raspberry_pie_camera_capture.git
cd raspberry_pie_camera_capture
```

2. Create and activate a virtual environment:
```bash
python3 -m venv .venv
source .venv/bin/activate
```

3. Install the package:
```bash
pip install -e .
```

4. For CPU core affinity management, ensure psutil is installed:
```bash
pip install psutil
```

## Usage

### Combined Camera and Audio Capture

Run the combined camera and audio capture script:
```bash
./run-camera-recorder.sh
```

This script:
- Activates the virtual environment
- Cleans up any existing camera/audio processes
- Runs both camera and audio capture with proper CPU core assignments
- Handles graceful shutdown

### Camera Capture (Standalone)

Run the camera capture script:
```bash
camera-capture [options]
```

Options:
- `--camera-id`: Camera index or ID to use (default: 0)
- `--width`: Frame width (default: 640)
- `--height`: Frame height (default: 480)
- `--fps`: Target frame rate (default: 30.0)
- `--save-video`: Save video files
- `--output-dir`: Directory to save recordings (default: recordings)
- `--codec`: Video codec to use (auto, h264, h265, mjpg)
- `--no-preview`: Disable preview window
- `--no-lsl`: Disable LSL streaming
- `--stream-name`: LSL stream name (default: camera_stream)
- `--no-buffer`: Disable buffer trigger system
- `--buffer-size`: Buffer size in seconds (default: 5.0)
- `--ntfy-topic`: Topic for ntfy notifications (default: raspie-camera-test)
- `--capture-cpu-core`: CPU core to use for capture thread
- `--writer-cpu-core`: CPU core to use for writer thread
- `--lsl-cpu-core`: CPU core to use for LSL thread
- `--ntfy-cpu-core`: CPU core to use for ntfy subscriber thread

### Audio Capture (Standalone)

Run the audio capture script:
```bash
audio-stream [options]
```

Options:
- `--device-index`: Audio device index or name (default: 0)
- `--sample-rate`: Sample rate in Hz (default: 48000)
- `--channels`: Number of audio channels (default: 1)
- `--save-audio`: Save audio files
- `--output-dir`: Directory to save recordings (default: recordings)
- `--no-lsl`: Disable LSL streaming
- `--stream-name`: LSL stream name (default: RaspieAudio)
- `--buffer-size`: Buffer size in seconds (default: 5.0)
- `--ntfy-topic`: Topic for ntfy notifications (default: raspie-camera-test)
- `--capture-cpu-core`: CPU core to use for capture thread
- `--writer-cpu-core`: CPU core to use for writer thread

### Remote Control

Start recording:
```bash
curl -d "Start Recording" ntfy.sh/raspie-camera-trigger
```

Stop recording:
```bash
curl -d "Stop Recording" ntfy.sh/raspie-camera-trigger
```

## CPU Core Optimization

For Raspberry Pi 4 (with 4 cores), we recommend:
- Video capture: Core 0
- Video writing: Core 1
- Audio capture: Core 2
- Audio writing: Core 3
- LSL streaming and ntfy monitoring: Core 0/3 (less resource-intensive)

## Development

1. Create a development environment:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

2. Run tests:
```bash
pytest tests/
```

## License

MIT License
