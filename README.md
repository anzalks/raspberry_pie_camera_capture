# IMX296 Camera Recorder with LSL

A comprehensive solution for recording from IMX296 global shutter cameras on Raspberry Pi with Lab Streaming Layer (LSL) integration for real-time frame synchronization.

## Features

- **Real-time LSL Streaming**: Frame timestamps are streamed live during recording
- **Automatic Camera Detection**: Finds IMX296 entities across all media devices
- **Permission-free Operation**: Uses local directories, no sudo required
- **Flexible Camera Support**: Works with single or dual camera setups
- **High-performance Recording**: Optimized for high frame rates and resolutions
- **Cross-platform LSL**: Compatible with LSL ecosystem for multi-modal data collection

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

## Usage

### Quick Start

Activate the virtual environment:
```bash
source venv/bin/activate
```

Basic recording with real-time LSL:
```bash
python simple_camera_lsl.py --width 400 --height 400 --fps 100 --duration 30
```

Direct camera testing:
```bash
./GScrop 400 400 100 10000  # width height fps duration_ms
```

### Advanced Usage

High-speed recording:
```bash
python simple_camera_lsl.py --width 320 --height 240 --fps 200 --duration 15
```

Custom exposure:
```bash
python simple_camera_lsl.py --width 400 --height 400 --fps 100 --exposure 5000 --duration 30
```

Dual camera setup:
```bash
python simple_camera_lsl.py --cam1 --width 400 --height 400 --fps 100
```

## Real-time LSL Streaming

The system now provides **real-time frame synchronization** by:

1. **GScrop script** captures video and streams frame timestamps to stdout
2. **Python script** reads timestamps in real-time and immediately streams to LSL
3. **No file delays** - frame data is processed as it's captured
4. **Low latency** - minimal delay between frame capture and LSL transmission

### LSL Stream Format

- **Stream Name**: `IMX296Camera` (configurable)
- **Stream Type**: `Video`
- **Channel Count**: 1 (frame numbers)
- **Sample Rate**: Matches camera FPS
- **Data Format**: Frame numbers as double64

## Supported Configurations

| Resolution | Max FPS | Use Case |
|------------|---------|----------|
| 400x400    | 100     | Balanced performance |
| 640x480    | 90      | Standard VGA |
| 320x240    | 200     | High-speed capture |
| 800x600    | 60      | High resolution |

## Output Files

All files are saved to local directories:

- **Videos**: `./output/tst.mp4` (or `tst.h264` for older systems)
- **Recordings**: `./recordings/YYYY-MM-DD/` (when using Python script)
- **Markers**: `./output/camera_markers.txt` (debugging)
- **Plots**: `./output/timestamp_plot.png` (if available)

## Troubleshooting

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

## Technical Details

### Camera Entity Detection
The system automatically scans all `/dev/media*` devices to find IMX296 entities, supporting configurations like:
- `imx296 10-001a` 
- `imx296 11-001a`
- And others without hardcoded limits

### Real-time Processing Pipeline
1. `rpicam-vid` captures video + PTS timestamps
2. `tail -f` monitors PTS file in real-time  
3. Frame data streamed via stdout: `FRAME_DATA:frame_num:timestamp`
4. Python script parses stdout and pushes to LSL immediately
5. LSL worker thread handles high-throughput streaming

### Frame Synchronization
- Frame numbers start from 1
- Timestamps in seconds (converted from microseconds)
- LSL timestamps use system time for synchronization
- Minimal latency between capture and LSL transmission

## Author

**Anzal KS**  
Email: anzal.ks@gmail.com  
GitHub: https://github.com/anzalks/

## License

This project is open source. Please maintain attribution when using or modifying. 