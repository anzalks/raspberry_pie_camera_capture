# IMX296 Camera Recorder with LSL

A high-performance camera recording system for IMX296 global shutter cameras on Raspberry Pi, with real-time Lab Streaming Layer (LSL) integration for precise frame timing synchronization.

## Features

- **Real-time LSL Streaming**: Frame timestamps are streamed live during recording
- **Automatic Camera Detection**: Finds IMX296 entities across all media devices
- **Permission-free Operation**: Uses local directories, no sudo required
- **Flexible Camera Support**: Works with single or dual camera setups
- **High-performance Recording**: Optimized for high frame rates and resolutions
- **Cross-platform LSL**: Compatible with LSL ecosystem for multi-modal data collection
- **Optional Visualization**: Frame timing plots when enabled with `--plot` flag

## Dependencies

### System packages (auto-installed):
- `rpicam-apps` or `libcamera-apps` (camera control)
- `media-ctl` and `v4l-utils` (media device management)
- `cmake`, `build-essential` (for building liblsl)

### Python packages (auto-installed):
- `pylsl` (LSL streaming)
- `pyxdf` (LSL data format)
- `numpy`, `scipy` (data processing)
- `matplotlib` (plotting and visualization)

## Installation

Run the installation script as root:

```bash
sudo ./install.sh
```

This automatically:
- Installs system dependencies (camera tools, build tools)
- Builds liblsl from source
- Creates Python virtual environment
- Installs Python dependencies including matplotlib
- Makes scripts executable
- Verifies camera tool availability

## Video Format & Reliability Options

### 🎥 Container Formats

The system now supports multiple video container formats optimized for different use cases:

| Format | Reliability | Speed | Compatibility | Use Case |
|--------|-------------|-------|---------------|----------|
| **MKV** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | **Recommended for critical recordings** |
| **MP4** | ⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | Standard compatibility |
| **Fragmented MP4** | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | **Best balance of reliability & compatibility** |
| **H.264 Raw** | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ | Maximum speed, minimal overhead |

### 🔧 Encoder Options

| Encoder | Speed | Quality | CPU Usage | Description |
|---------|-------|---------|-----------|-------------|
| **hardware** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | **GPU accelerated H.264 (recommended)** |
| **fast** | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | CPU encoding with speed optimizations |
| **software** | ⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ | Highest quality CPU encoding |
| **auto** | - | - | - | Automatically selects best option |

### 💡 Quick Format Recommendations

```bash
# Maximum reliability for critical recordings
python3 simple_camera_lsl.py --container mkv --encoder hardware

# High FPS recording (>100 FPS)
python3 simple_camera_lsl.py --container mkv --encoder hardware --fps 150

# Maximum compatibility
python3 simple_camera_lsl.py --container mp4 --fragmented --encoder hardware

# Maximum speed (minimal processing)
python3 simple_camera_lsl.py --container h264 --encoder hardware

# Long duration recordings (>30 seconds)
python3 simple_camera_lsl.py --container mkv --duration 120

# Auto-optimization (recommended for most users)
python3 simple_camera_lsl.py --container auto --encoder auto
```

### 🛡️ Reliability Features

#### **Interruption Recovery**
- **MKV**: Streams metadata throughout recording → **recoverable even if interrupted**
- **Fragmented MP4**: Writes metadata during recording → **much more reliable than standard MP4**
- **Standard MP4**: Writes metadata at end → **can be corrupted if interrupted**

#### **Performance Monitoring**
- Real-time frame rate reporting every 5 seconds
- Final performance assessment with target comparison
- Automatic detection of frame drops or timing issues

#### **Error Recovery**
- Automatic fallback between frame sources (real-time vs file-based)
- Robust file detection across multiple possible extensions
- Comprehensive error logging and troubleshooting guidance

### 📊 Format Selection Logic

The system automatically recommends optimal formats based on your recording parameters:

- **High FPS (>120)**: MKV + hardware encoding for reliability
- **Long recordings (>30s)**: MKV for interruption resilience  
- **Short recordings (<30s)**: Fragmented MP4 for compatibility
- **Maximum speed needed**: Raw H.264 + hardware encoding

## Basic Usage

```bash
# Standard recording with auto-optimization
python3 simple_camera_lsl.py --width 400 --height 400 --fps 100 --duration 30

# High-speed recording with MKV reliability
python3 simple_camera_lsl.py --width 320 --height 240 --fps 200 --container mkv

# Long recording with maximum reliability
python3 simple_camera_lsl.py --duration 300 --container mkv --encoder hardware
```

## Advanced Options

### Command Line Arguments

```bash
python3 simple_camera_lsl.py [options]

Recording Options:
  --width WIDTH         Camera width (default: 400)
  --height HEIGHT       Camera height (default: 400)  
  --fps FPS            Target frame rate (default: 100)
  --duration DURATION   Recording duration in seconds (default: 10)
  --exposure EXPOSURE   Exposure time in microseconds (optional)

Video Format Options:
  --container {mkv,mp4,h264,auto}    Container format (default: auto)
  --encoder {hardware,software,fast,auto}  Encoder type (default: auto)
  --fragmented         Use fragmented MP4 for better reliability

LSL Options:
  --lsl-name NAME      LSL stream name (default: IMX296Camera)
  --lsl-type TYPE      LSL stream type (default: Video)

System Options:
  --cam1               Use camera 1 instead of camera 0
  --preview            Show camera preview during recording
  --debug              Enable debug logging
  --plot               Generate timing analysis plots
```

## Technical Details

### Frame Timing Accuracy
- **Hardware timestamps**: Direct from camera sensor
- **Microsecond precision**: LSL timestamps synchronized with system clock
- **Real-time streaming**: Every frame sent immediately to LSL
- **Gap detection**: Automatic detection and reporting of dropped frames

### Performance Characteristics
- **Hardware encoding**: ~95% GPU utilization, minimal CPU load
- **Memory usage**: <100MB for typical recordings
- **Disk I/O**: Optimized for continuous high-speed writing
- **Network**: LSL streaming adds <1ms latency per frame

## Troubleshooting

### Video File Issues
```bash
# Check what video files were created
ls -la recordings/*/recording_*

# Convert H.264 to MP4 if needed
ffmpeg -i recording.h264 -c copy recording.mp4

# Repair corrupted MP4
ffmpeg -i broken.mp4 -c copy fixed.mp4
```

### Frame Rate Issues
```bash
# Enable debug logging to see frame processing details
python3 simple_camera_lsl.py --debug --fps 100

# Use faster format for high FPS
python3 simple_camera_lsl.py --container h264 --encoder hardware --fps 200
```

### LSL Connection Issues
```bash
# Check LSL setup
source ./setup_lsl_env.sh
python3 simple_camera_lsl.py --test-markers
```

### Camera Not Found
```bash
# Check camera connection
lsmod | grep imx296

# List media devices  
ls /dev/media*

# Test camera directly
rpicam-vid --list-cameras
```

### Permission Issues
The system automatically uses local directories to avoid permission problems. If issues persist:

```bash
# Ensure user is in video group
sudo usermod -a -G video $USER
# Logout and login again
```

### No LSL Data
- Ensure `pylsl` is installed in the virtual environment
- Check that `STREAM_LSL=1` environment variable is set
- Verify camera is actually recording (check video file size)

## Author

**Anzal KS**  
Email: anzal.ks@gmail.com  
GitHub: https://github.com/anzalks/

## License

This project is open source. Please maintain attribution when using or modifying. 