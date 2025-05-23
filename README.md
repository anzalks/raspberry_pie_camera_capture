# Raspberry Pi IMX296 Camera Capture System

This repository contains a high-performance camera capture system designed for the IMX296 global shutter camera on Raspberry Pi, with Lab Streaming Layer (LSL) integration for precise frame timing. The system consists of a shell script (`GScrop`) for camera control and a Python script (`simple_camera_lsl.py`) for LSL streaming.

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

### Capture Process

1. `simple_camera_lsl.py` parses command line arguments and validates camera settings
2. It launches `GScrop` as a subprocess with the requested parameters
3. `GScrop` configures the camera hardware via media-ctl and libcamera/rpicam tools
4. Video recording starts while frame markers are written to `/dev/shm/camera_markers.txt`
5. Multithreaded processing monitors the markers file and queues frames for LSL streaming
6. The LSL worker thread processes frames from the queue and sends them to the LSL outlet
7. Video is saved to the specified output path or auto-generated location
8. Statistics on frame capture performance are reported on completion

### Frame Synchronization

The system uses two methods for frame timing:
1. **Markers File**: `/dev/shm/camera_markers.txt` contains frame numbers and timestamps
2. **PTS File**: Presentation timestamps directly from the camera (when available)

Frame timing data is streamed via LSL with a single channel containing frame numbers.

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

### Common Issues

#### Low Frame Capture Rate
- Reduce resolution or frame rate
- Ensure proper cooling of the Raspberry Pi
- Make sure no other processes are using the camera
- Try disabling AWB with `--no-awb`

#### No LSL Data
- Check if pylsl is installed correctly
- Verify LSL receiver is configured to match the stream name
- Check logs for errors in marker file creation

#### "Media device not found" Error
- Verify camera connection
- Check if camera is recognized: `libcamera-hello --list-cameras`
- Try rebooting the Raspberry Pi

#### Permission Issues
- Ensure scripts are executable: `chmod +x GScrop`
- Check permissions on /dev/shm: `sudo chmod 777 /dev/shm`

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