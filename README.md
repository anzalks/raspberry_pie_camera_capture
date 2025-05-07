# Raspberry Pi Camera Capture

Camera capture and streaming for Raspberry Pi with LSL integration and ntfy notifications.

## Features

- Camera auto-detection (PiCamera or webcam)
- Real-time preview
- Video recording with pre-trigger buffer
- LSL streaming
- ntfy notifications for remote control
- Status display in terminal

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

## Usage

### Camera Capture

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

### Camera Test

Run the camera test script:
```bash
test-camera [options]
```

Options:
- `--camera-id`: Camera index or ID to use (default: 0)
- `--width`: Frame width (default: 640)
- `--height`: Frame height (default: 480)
- `--fps`: Target frame rate (default: 30.0)
- `--test-duration`: Test duration in seconds (default: 30.0)
- `--trigger-delay`: Delay before triggering recording (default: 5.0)
- `--record-duration`: Recording duration in seconds (default: 10.0)
- `--no-preview`: Disable preview window

### Remote Control

Start recording:
```bash
curl -d "Start Recording" ntfy.sh/raspie-camera-test
```

Stop recording:
```bash
curl -d "Stop Recording" ntfy.sh/raspie-camera-test
```

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
