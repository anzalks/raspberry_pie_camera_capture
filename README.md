# Raspberry Pi Camera Capture

A Python package for capturing video from Raspberry Pi cameras and streaming frame data over LabStreamingLayer (LSL).

## Features

> **Note:** This codebase has been streamlined by removing unnecessary utility scripts, making it more maintainable and focused on core functionality.

- **High-Performance Video Capture**: 400x400 resolution at 100fps
- **Optimized Video Format**: MJPG codec with MKV container for high frame rate recording
- **Pre-trigger Rolling Buffer**: Capture 20 seconds of footage before a trigger event
- **Remote Control**: Start/stop recording via ntfy.sh notifications from any device
- **Date-based Storage**: Organizes recordings by date with separate video and audio folders
- **Audio Capture**: Support for USB microphones with synchronized recording
- **Enhanced LSL Integration**: Stream frame metadata via LSL for synchronization with other data streams
- **Continuous Status Streams**: Dedicated LSL streams for recording status with timestamps 
- **Performance Optimization**: CPU core affinity control and threaded writing
- **Global Shutter Camera Support**: Custom cropping for Raspberry Pi Global Shutter Camera with high frame rates (up to 536fps)
- **Real-time Terminal Dashboard**: Live status display showing buffer, recording, and notification status
- **Unattended Operation**: Run as a system service or daily initialization script
- **Robust Error Handling**: Automatic recovery from recording errors
- **Configuration Validation**: Runtime validation of camera and encoding parameters
- **Environment Check**: Built-in system compatibility verification tool
- **Streamlined Codebase**: Lean implementation focused on core functionality

## Compliance with Requirements

This package is fully compliant with the notification-triggered video recorder requirements:

### Script Operation & Notification Handling
- ✅ **Execution Modes**:
  - Can run as a system service (through rpi-camera-service.sh)
  - Can be manually initiated with the camera-capture command
- ✅ **Notification Listening**: Continuously listens for ntfy.sh notifications
- ✅ **Notification Trigger**: Actions are primarily triggered by incoming ntfy notifications

### Pre-Notification Rolling Buffer
- ✅ **Rolling Buffer**: Continuously buffers camera frames
- ✅ **Buffer Duration**: Configurable 20-second buffer (default)
- ✅ **Buffer Storage**: All frames stored in RAM
- ✅ **Buffer Management**: Oldest frames automatically discarded as new ones arrive

### Notification-Triggered Recording
- ✅ **Buffer Persistence**: Buffer contents (preceding 20s) saved to SD card upon receiving "start" ntfy notification
- ✅ **Continuous Recording**: Live camera stream saved directly to SD card after buffer is saved
- ✅ **Recording Active Flag**: Boolean flag (ntfy_notification_active) set TRUE from "start" until "stop" notification

### LSL Integration
- ✅ **LSL Stream Creation**: Creates LSL stream for frame metadata
- ✅ **Data Inclusion**: Pushes metadata for all frames (buffered and live) to LSL stream on notification
- ✅ **Time Alignment**: All LSL data entries accurately time-aligned with corresponding frames
- ✅ **LSL Stream Columns**:
  - time: Standard LSL timestamp
  - ntfy_notification_active: Boolean (1.0/0.0) indicating if recording is active
  - camera_frame_no: Sequential frame number
  - is_keyframe: Keyframe indicator (1.0/0.0)

### Video Output
- ✅ **Video Format**: All videos saved in MKV (Matroska) format
- ✅ **Robustness**: MKV format ensures robustness against abrupt termination or power loss

### Notification-Stop Handling
- ✅ **Stopping Recording**: Recording stops on "stop" notification
- ✅ **File Finalization**: MKV file properly closed/finalized
- ✅ **Flag Reset**: ntfy_notification_active flag set to FALSE
- ✅ **LSL Indication**: All subsequent LSL samples show FALSE for ntfy_notification_active
- ✅ **Return to Buffering**: System returns to maintaining rolling buffer and listening for new notifications

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

### Global Shutter Camera with Cropping

The Raspberry Pi Global Shutter Camera (IMX296) is now fully supported with automatic detection and configuration. The implementation uses the cropping technique developed by Hermann-SW (https://gist.github.com/Hermann-SW/e6049fe1a24fc2b5a53c654e0e9f6b9c) to achieve high frame rates.

#### Automatic Detection and Configuration

When using the Global Shutter Camera, the system:

1. **Automatically detects** the IMX296 sensor used in the Raspberry Pi Global Shutter Camera
2. **Configures optimal cropping** based on the requested dimensions and frame rate
3. **Adjusts dimensions** if necessary to achieve the target frame rate
4. **Applies the appropriate media-ctl commands** to set up the hardware-level cropping

You don't need to specify any special flags - just request the dimensions and frame rate you want, and the system will automatically configure the camera appropriately. The `--enable-crop` flag is available but is automatically set based on the camera type and requested frame rate.

#### How It Works

The implementation uses the media-ctl tool to configure the sensor at a hardware level, applying custom cropping to enable high frame rates. This is based on research by Hermann-SW, who discovered that by cropping the sensor output, the Global Shutter Camera can achieve frame rates much higher than its official specifications:

1. For frame rates above 500fps, a height of 96 pixels is required
2. For balanced performance around 400fps, a 688x136 crop works well
3. For general usage with higher resolution, a 600x600 square crop at 200fps provides good results
4. The full width of the sensor (1456 pixels) can be used with a height of 96 pixels to achieve 536fps

The system includes fallback mechanisms and multiple detection methods to ensure reliable operation across different Raspberry Pi models.

#### Global Shutter Camera Capabilities

The Raspberry Pi Global Shutter Camera uses the Sony IMX296 sensor, which provides:

- No rolling shutter distortion
- Excellent low-light performance
- Global synchronization of all pixels
- High frame rates with cropping (up to 536fps)

This makes it ideal for high-speed capture of fast-moving objects without distortion.

#### Optimal Crop Configurations

The system automatically optimizes cropping based on your requested resolution and frame rate:

| Resolution | Frame Rate | Description |
|------------|------------|-------------|
| 1456x96    | 536 fps    | Full width, minimal height |
| 688x136    | 400 fps    | Balanced crop region |
| 224x96     | 500 fps    | Small region of interest |
| 600x600    | 200 fps    | Square crop for general usage |

No additional flags are required - the system automatically detects the Global Shutter Camera and applies the appropriate crop configuration based on your requested dimensions and frame rate.

Example commands:

```bash
# Maximum frame rate (536fps)
python -m src.raspberry_pi_lsl_stream.camera_capture --width 1456 --height 96 --fps 536 --save-video

# Square crop for general use (200fps)
python -m src.raspberry_pi_lsl_stream.camera_capture --width 600 --height 600 --fps 200 --save-video

# Balanced size/speed (400fps)
python -m src.raspberry_pi_lsl_stream.camera_capture --width 688 --height 136 --fps 400 --save-video

# Small ROI for maximum speed (500fps)
python -m src.raspberry_pi_lsl_stream.camera_capture --width 224 --height 96 --fps 500 --save-video
```

#### Checking for the Global Shutter Camera

You can check if your system has a Global Shutter Camera with:

```bash
python check-camera-env.py --global-shutter
```

This will detect the camera and provide guidance on optimal configurations.

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
- **Container Format**: MKV containers are used for better compatibility with MJPG codec and increased robustness
- **LSL Integration**: Comprehensive frame metadata is streamed over LSL including frame numbers, timestamps, keyframe markers, and notification status
- **LSL Status Streams**: Continuous 10Hz status updates with timestamps for both camera and audio (0=idle, 1=recording, 2=buffering) 
- **Camera API**: Uses picamera2 with direct BGR format capture for best performance
- **Global Shutter Camera**: Uses media-ctl to configure sensor cropping for high frame rates
- **Raspberry Pi ID**: Uses the Pi's unique serial number as the LSL source ID for better device tracking
- **Fallback Mechanisms**: Multiple fallback options for codec/container compatibility with automatic recovery
- **Error Handling**: Robust error recovery if video writer initialization fails or frames can't be written

## Codebase Structure

The codebase consists of the following main components:

- **camera_stream_fixed.py**: Core implementation of camera capture and LSL streaming
- **buffer_trigger.py**: Implementation of rolling buffer and ntfy notification handling
- **status_display.py**: Real-time terminal dashboard for monitoring system status
- **camera_capture.py**: Command-line interface and main script for camera capture
- **audio_stream.py**: Audio capture and streaming implementation
- **camera_lock.py**: Ensures only one camera instance runs at a time
- **check-camera-env.py**: Environment check tool to verify system compatibility

These modules work together to provide a complete, streamlined solution for high-performance camera capture on Raspberry Pi with LSL integration and remote control capabilities.

## LSL Stream Configuration

The system now provides enhanced LSL streams for synchronization and data integration:

1. **Camera Frame Metadata**: Stream name: `VideoStream` (configurable)
   - Channel 1: Frame numbers (as floating-point values)
   - Channel 2: Frame timestamps (in seconds since epoch)
   - Channel 3: Keyframe indicators (1.0 for keyframes, 0.0 for regular frames)
   - Channel 4: Notification active status (1.0 when recording active, 0.0 when inactive)
   - Stream type: 'Markers', format: 'double'

2. **Camera Status**: Stream name: `VideoStream_Status`
   - Channel 1: Recording status values (0=idle, 1=recording, 2=buffering)
   - Channel 2: Status update timestamps (in seconds since epoch)
   - Updates continuously at 10Hz
   - Stream type: 'RecordingStatus', format: 'double'

3. **Audio Chunk Markers**: Stream name: `RaspieAudio` (configurable)
   - Sends audio chunk indices and timestamps 
   - Frequency depends on the audio chunk size

4. **Audio Status**: Stream name: `RaspieAudio_Status`  
   - Channel 1: Recording status values (0=idle, 1=recording)
   - Channel 2: Status update timestamps (in seconds since epoch)
   - Updates continuously at 10Hz
   - Stream type: 'RecordingStatus', format: 'double'

These enhanced streams provide more precise temporal alignment and synchronization between video frames, audio samples, and other data sources.

## Environment Check Tool

To verify your system is properly configured for the camera capture system, run the environment check tool:

```bash
python check-camera-env.py
```

This tool will check:
- Required Python packages
- System packages and libraries
- Camera device availability and permissions
- LSL configuration and stream creation
- Storage space for recordings
- Network connectivity to ntfy.sh
- Video codec support

## Real-time Terminal Dashboard

The system includes a real-time terminal dashboard that displays the current status of the camera capture system:

```
╔════════════════════════════════════════════════════════════════════════════╗
║                   Pi Camera Capture - Status Dashboard                     ║
╠════════════════════════════════════════════════════════════════════════════╣
║ System Status                                                              ║
║ • Uptime: 00:05:32                                                         ║
║ • Camera: Raspberry Pi Camera (400x400)                                    ║
║ • Codec: mjpg                                                              ║
║ • Status: BUFFERING                                                        ║
╠════════════════════════════════════════════════════════════════════════════╣
║ Buffer Status                                                              ║
║ • Frames in buffer: 1498                                                   ║
║ • Buffer duration: 15.2s / 20.0s                                           ║
║ • Buffer fill: [███████████████░░░░░] 76%                                  ║
╠════════════════════════════════════════════════════════════════════════════╣
║ Frame Statistics                                                           ║
║ • Target FPS: 100.0                                                        ║
║ • Current FPS: 98.2                                                        ║
║ • Frames captured: 32154                                                   ║
║ • Frames written: 0                                                        ║
║ • Frames dropped: 0                                                        ║
╠════════════════════════════════════════════════════════════════════════════╣
║ Notification Status                                                        ║
║ • NTFY Topic: raspie-camera-test                                           ║
║ • Last notification: None                                                  ║
╠════════════════════════════════════════════════════════════════════════════╣
║ Keyboard Controls                                                          ║
║ • [S] Start Recording  • [X] Stop Recording  • [Q] Quit                    ║
╚════════════════════════════════════════════════════════════════════════════╝
```

This dashboard updates in real-time and provides:

- **System Status**: Camera information, codec, and current recording state
- **Buffer Status**: Number of frames in the rolling buffer, buffer duration, and visual fill indicator 
- **Frame Statistics**: Target and current frame rates, frame counts, and dropped frame metrics
- **Notification Status**: Last ntfy notification received with timestamp
- **Keyboard Controls**: Keyboard shortcuts for manual control

The dashboard automatically adjusts to terminal window size and provides instant visual feedback when notifications are received or recording starts/stops.

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

## Camera Configuration

### Standard Raspberry Pi Camera Module

The standard Raspberry Pi Camera Modules (v2, v3, HQ) work out of the box with no special configuration.

### Global Shutter Camera

The Raspberry Pi Global Shutter Camera (based on Sony IMX296) is automatically detected and configured:

- Full sensor resolution: 1456×1088 pixels
- Higher frame rates can be achieved with smaller crop regions
- Example crop configurations (automatically applied):
  - 688x136 pixels @ ~400fps
  - 224x96 pixels @ ~500fps
  - 1456x96 pixels @ ~536fps (full width, very thin height)

The system automatically:
1. Detects if a Global Shutter Camera is connected
2. Determines the optimal crop mode based on requested resolution and frame rate
3. Configures the proper cropping parameters
4. Centers the crop region on the sensor
5. Applies the settings using the media-ctl command

When requesting high frame rates (>120fps), the system will automatically enable and optimize crop settings for the Global Shutter Camera.

Requirements for Global Shutter Camera:
- Linux-based system (Raspberry Pi OS)
- media-ctl utility installed
- Both width and height will be adjusted to even numbers if needed
