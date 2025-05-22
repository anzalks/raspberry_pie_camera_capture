# Raspberry Pi Camera Capture System

A sophisticated system for Raspberry Pi that captures video and audio triggered by ntfy.sh notifications, with pre-event buffering and Lab Streaming Layer (LSL) integration. The system includes specialized support for the Raspberry Pi Global Shutter Camera, automatically configuring it for high frame rates.

## Key Features

### Modular Design
- **LSLCameraStreamer**: Core class for video capture, processing, and streaming
- **LSLAudioStreamer**: Core class for audio capture, processing, and streaming
- **BufferTriggerManager**: Manages ntfy.sh notifications and pre-event buffering
- **StatusDisplay**: Real-time terminal dashboard for system monitoring

### Video Capture
- Built on the **Picamera2** library for optimal Raspberry Pi camera performance
- **Automatic Global Shutter Camera Support**: 
  - Detects the IMX296 sensor used in the Raspberry Pi Global Shutter Camera
  - Automatically configures sensor cropping (based on Hermann-SW's research) for high frame rates
  - Optimizes dimensions based on requested frame rate (up to 536fps)
  - Users simply specify desired resolution and FPS, and the system handles the low-level configuration
- **MKV** video container format with **MJPG** codec preferred for high frame rates (H264/H265 supported as alternatives)
- Threaded video writing for improved performance
- Optional OpenCV preview window with keyboard controls (start/stop recording, quit)

### Audio Capture
- Support for USB microphones via the **sounddevice** library
- **WAV** audio format with configurable sample rate, bit depth, and channels
- Threaded audio writing for improved performance
- Optional real-time audio visualizer showing waveform and spectrogram

### Notification-Triggered Recording with Pre-Event Buffer
- **Rolling RAM Buffer**: Continuously stores recent video frames and audio samples
- **ntfy.sh Integration**: Listens for "start" or "stop" notifications on a configurable topic
- On "start" trigger, the system:
  1. Saves the buffered content (typically 10-20 seconds) to the beginning of the output file
  2. Continues saving the live stream until a "stop" notification is received
- Supports both automated (via ntfy.sh) and manual triggering (via keyboard in preview)

### LSL (Lab Streaming Layer) Integration
- **Video Primary Stream**: `[frame_number, timestamp, is_keyframe, ntfy_notification_active]`
  - The `ntfy_notification_active` flag directly reflects the recording state (1 when recording, 0 when not)
- **Video Status Stream**: `[recording_status, timestamp]` at ~10Hz
  - Status values: 0=idle, 1=recording, 2=buffering
- **Audio Primary Stream**: `[chunk_index, timestamp]`
- **Audio Status Stream**: `[recording_status, timestamp]` at ~10Hz
  - Status values: 0=not_recording, 1=recording

### Configuration System
- **YAML-based Configuration**: All settings can be stored in a simple YAML file
- **Command-line Override**: Any config setting can be overridden via command-line arguments
- **Sensible Defaults**: The system provides reasonable defaults for all settings
- **Auto-detection**: Automatically detects and configures hardware-specific settings

### Additional Features
- **Real-time Terminal Dashboard**: Shows system status, buffer fill, FPS, frame counts, and notifications
- **Status File Fallback**: Writes status to a file (/tmp/raspie_camera_status) for monitoring when fancy terminal UI fails
- **CPU Core Affinity**: Specify cores for capture, writer, LSL, and ntfy threads to optimize performance
- **Single Instance Operation**: Camera locking prevents multiple instances accessing the camera
- **Date-based Organization**: Recordings are stored in YYYY_MM_DD/video/ and YYYY_MM_DD/audio/ folders

## Installation and Setup

### Prerequisites
- Raspberry Pi (recommended: Pi 4 or newer for best performance)
- Raspberry Pi Camera Module (standard or Global Shutter Camera)
- Python 3.7+
- USB microphone (for audio capture)

### One-step Installation
For a complete system setup, use the provided installation script:
```bash
# Clone the repository
git clone https://github.com/anzalks/raspberry_pie_camera_capture.git
cd raspberry_pie_camera_capture

# Run the setup script with sudo
sudo bash setup_pi.sh
```

This script will:
1. Install all required system dependencies
2. Set up Python virtual environment
3. Install Python dependencies including PyYAML for configuration
4. Create a default configuration file
5. Set up systemd service for auto-start on boot
6. Configure storage directories

### Manual Python Dependencies
If you prefer to install dependencies manually:
```bash
pip install picamera2 opencv-python numpy pylsl requests psutil sounddevice pyyaml
```

### System Dependencies (Raspberry Pi / Linux)
```bash
sudo apt update
sudo apt install -y v4l-utils libcamera-apps curl python3-yaml
```

### Permissions
- Ensure your user is in the 'video' group:
```bash
sudo usermod -a -G video $USER
```
- Log out and back in for the group change to take effect

## Usage

### Configuration File
The system uses a YAML configuration file (`config.yaml` in the project root by default) to define settings:

```yaml
# Raspberry Pi Camera Capture Configuration

# Camera settings
camera:
  width: 400
  height: 400
  fps: 100
  codec: mjpg
  container: mkv
  preview: false
  enable_crop: auto  # Can be true, false, or auto (detect Global Shutter Camera)

# Storage settings
storage:
  save_video: true
  output_dir: recordings
  create_date_folders: true

# Buffer settings
buffer:
  size: 20.0  # seconds
  enabled: true

# Remote control
remote:
  ntfy_topic: raspie-camera-test

# Terminal settings
terminal:
  colors_enabled: true
  use_unicode: false  # Set to false for better compatibility
  update_frequency: 0.5
```

You can create your own configuration file and specify it with the `--config` parameter:

```bash
python -m src.raspberry_pi_lsl_stream.camera_capture --config my_custom_config.yaml
```

### Quick Start
To start with default settings from the config file:

```bash
python -m src.raspberry_pi_lsl_stream.camera_capture
```

This will:
1. Load settings from `config.yaml`
2. Set up the camera with 400x400 resolution at 100fps
3. Configure a 20-second rolling buffer
4. Listen for notifications on the ntfy.sh topic
5. Start capturing frames and displaying the status dashboard

### Running on Raspberry Pi (Recommended Method)
For the best experience on Raspberry Pi, use the provided run script which ensures both preview and status display are visible:

```bash
# Run with a single command (recommended)
./run-camera.sh
```

This script will:
1. Activate the virtual environment automatically
2. Check that all required packages are installed
3. Run a diagnostic check of your camera system
4. Allow you to customize resolution and frame rate interactively
5. Show both the video preview window AND the terminal status display
6. Handle Ctrl+C gracefully for clean shutdown

For Global Shutter Camera users, simply select "y" when asked to customize parameters, then enter your desired dimensions and frame rate:

```
Use custom resolution and FPS? (y/n): y
Enter width (default: 640): 688
Enter height (default: 136): 
Enter FPS (default: 30): 400
```

### Environment Check
Always run the diagnostic script first to verify your setup:
```bash
python check-camera-env.py
```
This will check for required dependencies, detect camera hardware, and provide guidance specific to your setup.

### Camera Recording with Command-line Arguments
You can override any configuration file settings using command-line arguments:

```bash
# Override resolution and frame rate
python -m src.raspberry_pi_lsl_stream.camera_capture --width 640 --height 480 --fps 30

# Enable video preview window
python -m src.raspberry_pi_lsl_stream.camera_capture --preview

# Run with both custom resolution and preview enabled
python -m src.raspberry_pi_lsl_stream.camera_capture --width 800 --height 600 --fps 30 --preview

# Override ntfy topic for remote triggering
python -m src.raspberry_pi_lsl_stream.camera_capture --ntfy-topic your-topic-name
```

### Using the Preview Window
When preview is enabled (either via `--preview` flag or in config.yaml), a window will open showing the live camera feed. The preview window supports these keyboard controls:
- **S**: Start recording manually
- **P** or **Space**: Stop recording
- **Q** or **ESC**: Quit the application

This is especially useful for testing the camera setup without needing remote triggers.

#### Global Shutter Camera Examples
The system will automatically detect and configure the Global Shutter Camera. Just specify your desired dimensions and frame rate:

```bash
# Balanced size/speed (400fps)
python -m src.raspberry_pi_lsl_stream.camera_capture --width 688 --height 136 --fps 400

# Maximum frame rate (536fps)
python -m src.raspberry_pi_lsl_stream.camera_capture --width 1456 --height 96 --fps 536

# Square crop for general use (200fps)
python -m src.raspberry_pi_lsl_stream.camera_capture --width 600 --height 600 --fps 200

# Small ROI for high speed (500fps)
python -m src.raspberry_pi_lsl_stream.camera_capture --width 224 --height 96 --fps 500
```

#### Global Shutter Camera Implementation Details
This system uses advanced media-ctl techniques (based on Hermann-SW's research) to configure the Raspberry Pi Global Shutter Camera for optimal performance:

1. **Automatic Detection**: The system detects the IMX296 sensor used in the Global Shutter Camera
2. **Intelligent Cropping**: Configures the sensor's crop region based on requested dimensions and frame rate
3. **Low-level Configuration**: Uses media-ctl commands to directly configure the camera sensor
4. **Optimized Settings**: Automatically adjusts settings for the best balance between resolution and frame rate

When using a Global Shutter Camera, the best way to run is through the interactive script:
```bash
./run-camera.sh
```

Select "y" when asked to customize parameters, and specify your desired width, height, and FPS. The system will automatically optimize the configuration for your camera.

### Audio Recording
```bash
# Basic usage
python -m src.raspberry_pi_lsl_stream.cli audio --save-audio

# With custom settings
python -m src.raspberry_pi_lsl_stream.cli audio --sample-rate 48000 --channels 2 --save-audio

# With visualization
python -m src.raspberry_pi_lsl_stream.cli audio --save-audio --show-preview
```

### Service Management
If you used the setup_pi.sh script, you can manage the service with:

```bash
# Check status
./raspie-service.sh status

# Start/stop service
./raspie-service.sh start
./raspie-service.sh stop

# View logs
./raspie-service.sh logs

# Send trigger notifications
./raspie-service.sh trigger       # Start recording
./raspie-service.sh stop-recording # Stop recording
```

### Monitoring the Camera
When running as a service, you can monitor the camera status with:

```bash
# Full live monitoring with status display
./watch-raspie.sh
```

This shows the real-time status of the camera, including:
- Current recording state 
- Buffer fill level
- Frame rates
- Error messages
- Recording statistics

Use this to verify your camera is working correctly when running as a background service.

### Triggering Recording via ntfy.sh
Send notifications to start/stop recording:

```bash
# Start recording
curl -d "start recording" ntfy.sh/your-topic-name

# Stop recording
curl -d "stop recording" ntfy.sh/your-topic-name
```

You can also send these notifications from any device or application that can make HTTP requests.

## Project Structure
- **src/raspberry_pi_lsl_stream/**
  - **camera_stream_fixed.py**: Core video capture and processing class
  - **audio_stream.py**: Core audio capture and processing class
  - **buffer_trigger.py**: Notification handling and pre-event buffering
  - **camera_capture.py**: Main application for camera capture
  - **cli.py**: Command-line interface with subcommands for audio and video
  - **status_display.py**: Terminal-based dashboard
  - **camera_lock.py**: Ensures single-instance camera operation
  - **config_loader.py**: Loads and merges configuration from YAML and command-line
- **check-camera-env.py**: Diagnostic script to verify the environment
- **config.yaml**: Default configuration file
- **setup_pi.sh**: One-step installation script for Raspberry Pi
- **run-camera.sh**: Simple script to run with default configuration
- **raspie-service.sh**: Service management script (created by setup_pi.sh)

## Author
- **Anzal**: [GitHub](https://github.com/anzalks/)

## License
This project is licensed under the MIT License - see the LICENSE file for details.
