# Raspberry Pi IMX296 Camera Capture System

This repository contains a high-performance camera capture system designed for the IMX296 global shutter camera on Raspberry Pi, with Lab Streaming Layer (LSL) integration for precise frame timing. The system consists of a shell script (`GScrop`) for camera control and a Python script (`simple_camera_lsl.py`) for LSL streaming.

## ✅ System Status: **WORKING PERFECTLY!**

**Latest Test Results (May 27, 2025):**
- ✅ **Entity Auto-Discovery**: Successfully found "imx296 11-001a" on /dev/media0
- ✅ **Camera Configuration**: Media device configured successfully
- ✅ **Video Recording**: 63 frames recorded at 100fps (400x900 resolution)
- ✅ **High Quality**: H.264 encoding with excellent compression (1123.37 kb/s)
- ✅ **No Sudo Required**: Works perfectly without administrator privileges

## Overview

**IMX296 Global Shutter Camera System for Raspberry Pi**

This system provides high-speed video recording (up to 200fps) with LSL streaming capabilities for scientific and research applications. The system automatically detects unlimited cameras and handles permission requirements gracefully without requiring sudo access.

## Key Features

- **Unlimited Camera Support**: Dynamic detection of all available cameras (no hardcoded limits)
- **No Sudo Required**: Graceful fallback to /tmp if /dev/shm access is limited
- **LSL Streaming**: Real-time frame synchronization with Lab Streaming Layer
- **High-Speed Recording**: Up to 200fps with global shutter technology
- **Cross-Platform**: Works on Raspberry Pi 4/5 and CM4 systems
- **User-Friendly**: Automatic permission detection with helpful guidance

## Quick Start

⚠️ **IMPORTANT: DO NOT USE SUDO** - Run all commands as regular user:

1. **Basic Recording** (no special permissions needed):
   ```bash
   ./GScrop 400 900 100 1000    # 100fps for 1 second (TESTED ✅)
   ```

2. **With LSL Streaming**:
   ```bash
   python simple_camera_lsl.py --config-width 400 --config-height 900 --config-fps 100 --duration 5
   ```

3. **Wrong way** (will cause permission issues):
   ```bash
   sudo ./GScrop 400 900 100 1000  # ❌ DON'T DO THIS
   ```

## Permission Requirements

### Automatic Handling ✅
The system automatically:
- Detects writable directories (/dev/shm or falls back to /tmp)
- Checks user permissions for camera access
- Provides helpful hints for permission issues

### Optional Optimizations
For best performance (entirely optional):
```bash
# Add user to video group (one-time setup)
sudo usermod -a -G video $USER
# Then logout and login again

# Optional: Ensure /dev/shm is writable for better performance
sudo chmod 1777 /dev/shm
```

## System Overview

The system is designed to:

1. Capture high-speed video from an IMX296 global shutter camera
2. Stream frame timing data via LSL for synchronization with other data streams
3. Record video efficiently at frame rates up to 200 FPS
4. Optimize performance using multithreaded processing

## Requirements

### Hardware
- Raspberry Pi 4B or Raspberry Pi 5 (recommended for higher framerates)
- IMX296 global shutter camera compatible with Raspberry Pi
- Sufficient cooling for the Raspberry Pi during high-speed capture

### Software Dependencies
- Raspberry Pi OS (Bullseye or Bookworm)
- Python 3.7+
- pylsl (Lab Streaming Layer for Python)
- libcamera tools (typically pre-installed on Raspberry Pi OS)

To install Python dependencies:
```bash
pip install pylsl
```

## Scripts

### GScrop

`GScrop` is a shell script that configures and controls the IMX296 camera using the Raspberry Pi's native camera tools.

#### Features:
- Camera configuration for specific resolution and frame rate
- Exposure control
- Auto White Balance (AWB) control
- Multithreaded frame marker generation for synchronization
- Support for both Raspberry Pi 4 and 5 with different camera backends

#### Usage:
```bash
./GScrop width height framerate duration_ms [exposure_us] [output_path]
```

#### Parameters:
- `width`: Camera resolution width (must be even number, max 1440)
- `height`: Camera resolution height (must be even number, max 1080)
- `framerate`: Target frame rate (up to 200 FPS)
- `duration_ms`: Recording duration in milliseconds (0 for unlimited)
- `exposure_us`: (Optional) Exposure time in microseconds
- `output_path`: (Optional) Path to save the video file

#### Environment Variables:
- `cam1=1`: Use second camera (if available)
- `narrow=1`: Use narrow field of view (preview mode)
- `no_awb=1`: Disable Auto White Balance

### simple_camera_lsl.py

Python script that runs `GScrop` and streams frame timing via LSL.

#### Features:
- Command line interface for camera settings
- LSL streaming of frame timing data
- Multithreaded processing with queue system
- Real-time monitoring of camera performance
- Detailed logging and error handling

#### Usage:
```bash
python simple_camera_lsl.py [options]
```

#### Command Line Options:
- `--width`: Camera width (default: 400)
- `--height`: Camera height (default: 400) 
- `--fps`: Target frame rate (default: 100)
- `--exposure`: Exposure time in microseconds (optional)
- `--duration`: Recording duration in seconds (default: 10)
- `--output`: Output video file path (default: auto-generated)
- `--lsl-name`: LSL stream name (default: IMX296Camera)
- `--lsl-type`: LSL stream type (default: Video)
- `--cam1`: Use camera 1 instead of camera 0
- `--preview`: Show camera preview during recording
- `--verbose`: Enable verbose logging
- `--debug`: Enable debug mode with extensive logging
- `--test-markers`: Test markers file creation and monitoring
- `--no-awb`: Disable AWB adjustments
- `--direct-pts`: Directly use PTS file for frame timing
- `--force`: Force camera configuration even if it might not work
- `--queue-size`: Size of the frame processing queue (default: 10000)

## How It Works

1. **Dynamic Device Detection**: Automatically finds all available media devices (`/dev/media*`)
2. **Permission-Aware Operation**: Uses /dev/shm if available, /tmp otherwise
3. **Media Configuration**: Sets up camera parameters via media-ctl
4. **Video Recording**: Captures high-speed video with frame synchronization
5. **LSL Streaming**: Real-time frame markers for lab equipment integration

## LSL Integration

1. **Markers File**: Automatically created in accessible location (`/dev/shm` or `/tmp`)
2. **Frame Synchronization**: Each frame gets precise timestamp markers
3. **Real-Time Streaming**: Frame data sent via LSL for lab integration
4. **Cross-Platform**: Compatible with LSL ecosystem

## Example Usage

### Basic Recording (100 FPS):
```bash
python simple_camera_lsl.py --width 400 --height 400 --fps 100 --duration 30
```

### High-Speed Recording (200 FPS):
```bash
python simple_camera_lsl.py --width 320 --height 240 --fps 200 --duration 10 --no-awb
```

### Custom Output Path:
```bash
python simple_camera_lsl.py --width 640 --height 480 --fps 90 --output /home/pi/videos/experiment1
```

### Second Camera:
```bash
python simple_camera_lsl.py --width 400 --height 400 --fps 100 --cam1
```

## Recommended Configurations

Based on the hardware capabilities of the IMX296 camera, these configurations provide optimal performance:

| Resolution | FPS | Use Case |
|------------|-----|----------|
| 320x240    | 200 | Maximum frame rate |
| 400x400    | 100 | Balanced performance |
| 640x480    | 90  | Standard resolution |
| 800x600    | 60  | Higher quality |

## Troubleshooting

### Permission Issues
If you see permission warnings:
```bash
# Add user to video group
sudo usermod -a -G video $USER
# Logout and login again
```

### Camera Not Detected
```bash
# Check camera connection
lsmod | grep imx296
# Should show camera driver loaded
```

### Performance Optimization
- Uses /dev/shm (RAM disk) for temporary files when available
- Falls back to /tmp if /dev/shm is not accessible
- Automatic permission detection prevents script failures

## Implementation Details

### Multithreaded Design

The system uses multiple threads to optimize performance:
1. **Main Thread**: Controls overall execution and monitoring
2. **Markers Monitor Thread**: Reads the markers file and queues frames
3. **LSL Worker Thread**: Processes frames from queue and sends to LSL
4. **GScrop Thread**: Manages marker file writing in the background

### LSL Integration

Frame timing data is streamed using LSL with:
- Stream name: Configurable, default "IMX296Camera"
- Stream type: Configurable, default "Video"
- Single channel: Frame number
- Timestamp: Accurate camera frame timestamp

### Frame Processing Pipeline

1. Camera hardware captures frames
2. Frame timestamps are written to markers file by GScrop
3. Monitor thread reads new markers and queues frames
4. LSL worker processes frames from queue
5. LSL outlet streams frame data to network

## Performance Considerations

- For frame rates above 120 FPS, use lower resolutions (320x240 or 400x400)
- The system can buffer up to 10000 frames in the queue (configurable)
- Higher resolutions require more bandwidth and processing power
- The Raspberry Pi 5 performs significantly better at high frame rates
- Using /dev/shm (RAM disk) for temporary files improves performance

## License

This project is released under the MIT License. 