# IMX296 Global Shutter Camera Capture System

**Author**: Anzal KS <anzal.ks@gmail.com>  
**Repository**: https://github.com/anzalks/raspberry_pie_camera_capture  
**License**: MIT

A comprehensive high-performance camera capture system for IMX296 Global Shutter cameras with automatic detection, independent LSL streaming, remote control, and advanced cleanup capabilities.

## 🎯 Overview

This system provides a complete solution for IMX296 Global Shutter camera capture with:
- **900x600@100fps** real-time capture using GScrop
- **3-channel LSL streaming** with independent operation
- **Remote smartphone control** via ntfy.sh
- **Rolling buffer system** for pre-trigger frame storage
- **Professional video recording** with MKV output
- **Real-time status monitoring** with terminal UI
- **Comprehensive cleanup system** for conflict-free deployment

**Total codebase**: 9,577 lines across Python, Shell, and configuration files  
**Test coverage**: 38/38 tests passing (100% success rate)

## ✅ Features

### 🎥 Core Camera System
- **IMX296 Global Shutter Integration**: Hardware-level cropping via media-ctl
- **Automatic Detection**: Zero-configuration camera setup
- **High-Speed Capture**: 900x600@100fps with precise timing
- **Exposure Control**: Configurable exposure time (default 5ms)
- **Frame Markers**: Accurate timestamping and metadata tracking

### 📡 LSL Streaming (Independent Operation)
- **3-Channel Stream**: Real-time metadata streaming
  - Channel 1: `frame_number` (sequential counter)
  - Channel 2: `trigger_time` (Unix timestamp)
  - Channel 3: `trigger_type` (0=none, 1=keyboard, 2=ntfy)
- **Continuous Operation**: Streams regardless of recording state
- **Low Latency**: <10ms frame-to-stream performance
- **Persistent Connection**: Maintains stream through service restarts

### 🎬 Video Recording Pipeline
- **Independent Operation**: Records continuously, trigger-independent
- **Professional Format**: MKV output with MJPEG/H.264 codec
- **Organized Storage**: `recordings/yyyy_mm_dd/video/` hierarchy
- **Trigger-Based Control**: Start/stop via ntfy or keyboard
- **Automatic Naming**: Timestamp-based filenames

### 📱 Remote Control System
- **ntfy.sh Integration**: Complete smartphone control
- **Text Command Support**: Simple text-based commands
- **Real-time Feedback**: Instant notifications and status updates
- **Duration Control**: Timed recording capabilities

### 🔄 Rolling Buffer System
- **Pre-Trigger Storage**: Continuous 15-second RAM buffer
- **Instant Response**: Buffer saved when recording starts
- **Frame Preservation**: Complete metadata retention
- **Memory Management**: Efficient circular buffer (1500 frames max)

### 📊 Real-Time Status Monitor
- **Terminal UI**: Python curses-based real-time display
- **Minimal Overhead**: <2% CPU usage for monitoring
- **Comprehensive Data**: Service, LSL, buffer, recording status
- **System Metrics**: CPU, memory, disk usage tracking
- **Visual Indicators**: Progress bars and status colors

### 🧹 Cleanup System (Advanced)
- **Conflict Resolution**: Removes old installations automatically
- **Service Management**: Stops and removes 6 types of camera services
- **Process Cleanup**: Terminates conflicting camera/LSL processes
- **File Management**: Cleans shared memory, configs, cache files
- **Multi-Mode Operation**: Cleanup-only, verify-only, combined modes

## 🚀 Installation

### Quick Install (Raspberry Pi Bookworm Compatible)

```bash
# Clone repository
git clone https://github.com/anzalks/raspberry_pie_camera_capture.git
cd raspberry_pie_camera_capture

# Run Bookworm-compatible installation script
sudo ./setup/install.sh
```

### Installation Features

**✅ Bookworm Compatibility**:
- Fixed package names (`v4l-utils` vs `v4l2-utils`)
- Proper liblsl build from source with cmake error handling
- Fixed pylsl symlink creation for all architectures
- Enhanced error handling with graceful fallbacks

**✅ Automatic Detection**:
- Camera hardware detection with libcamera
- Python version compatibility (3.9+)
- Architecture-specific library linking
- Missing package graceful handling

**✅ Complete Setup**:
- Virtual environment with proper permissions
- Systemd service installation
- Desktop shortcut creation
- Configuration file setup with unique ntfy topics

### Manual Installation (Alternative)

If the automated script fails:

```bash
# Install system dependencies manually
sudo apt update
sudo apt install -y python3 python3-pip python3-venv python3-dev \
  libcamera-apps ffmpeg git build-essential cmake pkg-config \
  libboost-dev libboost-thread-dev

# Build liblsl from source
cd /tmp
git clone https://github.com/sccn/liblsl.git
cd liblsl
mkdir build && cd build
cmake .. -DCMAKE_INSTALL_PREFIX=/usr/local -DLSL_BUNDLED_BOOST=ON
make -j$(nproc) && sudo make install
sudo ldconfig

# Setup Python environment
cd raspberry_pie_camera_capture
python3 -m venv --system-site-packages .venv
.venv/bin/pip install pylsl>=1.16.0 pyyaml>=6.0 requests>=2.28.0 psutil>=5.9.0
```

### Troubleshooting Installation

**LSL Library Issues**:
```bash
# Verify liblsl installation
ldconfig -p | grep liblsl

# Fix pylsl symlinks manually
PYLSL_DIR=.venv/lib/python3.*/site-packages/pylsl
mkdir -p $PYLSL_DIR/lib
ln -sf /usr/local/lib/liblsl.so $PYLSL_DIR/liblsl64.so
```

**Package Installation Failures**:
```bash
# Check available package names
apt-cache search v4l-utils
apt-cache search libboost

# Alternative V4L tools
sudo apt install -y media-ctl-tools  # If v4l-utils unavailable
```

### Post-Installation

After successful installation:

```bash
# Reboot to load camera drivers
sudo reboot

# Test installation
libcamera-hello --list-cameras
python3 -c "import pylsl; print('LSL working')"
```

### 2. Clean Start (Recommended)

For new installations or after system updates:

```bash
# Clean start with status monitor (recommended)
./bin/clean_start_camera.sh -m

# Clean start without monitor
./bin/clean_start_camera.sh

# Cleanup only (don't start)
./bin/clean_start_camera.sh -c

# Verify system state
./bin/clean_start_camera.sh -v
```

### 3. Traditional Start

```bash
# Direct execution
python3 bin/run_imx296_capture.py

# With status monitor
python3 bin/start_camera_with_monitor.py --monitor

# As systemd service
sudo systemctl start imx296-camera
```

## ⚙️ Configuration

Edit `config/config.yaml`:

```yaml
# Camera settings
camera:
  width: 900                    # Capture width
  height: 600                   # Capture height  
  fps: 100                      # Frame rate
  exposure_time_us: 5000        # 5ms exposure
  auto_detect: true             # Automatic camera detection
  script_path: "bin/GScrop"     # GScrop script location

# Rolling buffer
buffer:
  duration_seconds: 15          # Buffer duration
  max_frames: 1500             # Maximum frames in buffer

# LSL streaming (3 channels)
lsl:
  name: "IMX296Camera"         # Stream name
  type: "VideoEvents"          # Stream type
  channel_count: 3             # frame_number, trigger_time, trigger_type

# Video recording
recording:
  output_dir: "recordings"     # Output directory
  video_format: "mkv"         # Container format
  codec: "mjpeg"              # Video codec
  quality: 90                 # JPEG quality (0-100)

# Remote control
ntfy:
  server: "https://ntfy.sh"   # ntfy.sh server
  topic: "your-camera-topic"  # Unique topic name
  poll_interval_sec: 2        # Polling interval

# System paths
system:
  media_ctl_path: "/usr/bin/media-ctl"
  ffmpeg_path: "/usr/bin/ffmpeg"
```

## 🧹 Cleanup System

### Why Use Cleanup?

The cleanup system resolves conflicts from:
- Previous camera installations
- Old systemd services
- Conflicting processes
- Shared memory files
- Configuration conflicts

### Cleanup Tools

**Bash Wrapper (Simple)**:
```bash
./bin/clean_start_camera.sh [options]

Options:
  -m    Start with status monitor
  -c    Cleanup only (don't start)
  -v    Verify system state only
```

**Python Script (Advanced)**:
```bash
python3 bin/cleanup_and_start.py [options]

Options:
  --monitor          Start with status monitor
  --cleanup-only     Only perform cleanup
  --no-cleanup       Skip cleanup, start directly
  --logs            Include log file cleanup
  --verify-only     Only verify system state
```

### What Gets Cleaned

- **Services**: `imx296-camera`, `imx296-camera-monitor`, `raspberry-pi-camera`, `camera-service`, `lsl-camera`, `gscrop-camera`
- **Processes**: `imx296_capture`, `status_monitor`, `camera_stream`, `GScrop`, `ffmpeg`
- **Shared Memory**: `/dev/shm/imx296_status.json`, `/dev/shm/camera_markers.txt`, etc.
- **Config Files**: Old configuration files and Python cache
- **Service Files**: Removes systemd service files from `/etc/systemd/system/`

## 📊 Status Monitor

### Features
- **Real-time Updates**: Every 1 second with live data
- **Service Status**: Running state, uptime, health
- **LSL Analytics**: Stream rate, channel data, samples sent
- **Buffer Monitoring**: Utilization with visual progress bars
- **Recording Tracking**: Active state, frame count, duration
- **System Info**: CPU, memory, disk usage percentages
- **Trigger Analytics**: Last trigger type, timing, count

### Usage
```bash
# Monitor with camera service
python3 bin/start_camera_with_monitor.py --monitor

# Monitor only (service running separately)
python3 bin/status_monitor.py

# As systemd service with monitor
sudo systemctl start imx296-camera-monitor
```

### Controls
- **'q'** - Quit monitor
- **'r'** - Force refresh
- **'c'** - Clear screen

## 📱 Remote Control

### Setup ntfy.sh
1. Install ntfy app on smartphone
2. Subscribe to your unique topic
3. Send commands as text notifications

### Commands

**Recording Control (Primary Method)**:
```
start_recording
start_recording 30              # Record for 30 seconds
start_recording 120             # Record for 2 minutes
stop_recording
```

**System Status**:
```
status                          # Get current system status
get_stats                       # Get detailed statistics
```

### Example ntfy Workflow
1. **Boot**: Camera starts → "🟢 Ready for commands"
2. **Stream**: LSL and video recording active independently
3. **Remote Trigger**: Send "start_recording 30" via ntfy → "🔴 Recording for 30s"
4. **Complete**: Recording ends → "⏹️ Recording completed - 3000 frames"

### Trigger Types in LSL Stream
- **Type 0**: No trigger (continuous streaming)
- **Type 1**: Local keyboard trigger (development/testing)
- **Type 2**: ntfy remote trigger (primary method)

### Usage Example
```python
import pylsl

# Find camera stream
streams = pylsl.resolve_stream('name', 'IMX296Camera')
inlet = pylsl.StreamInlet(streams[0])

# Receive real-time data
while True:
    sample, timestamp = inlet.pull_sample()
    frame_number = int(sample[0])     # Sequential frame counter
    trigger_time = sample[1]          # Unix timestamp
    trigger_type = int(sample[2])     # 0=none, 1=keyboard, 2=ntfy
    
    if trigger_type == 2:  # ntfy trigger (primary method)
        print(f"Frame {frame_number}: ntfy trigger at {trigger_time}")
    elif trigger_type == 1:  # keyboard trigger  
        print(f"Frame {frame_number}: keyboard trigger at {trigger_time}")
```

## 🗂️ File Organization

```
recordings/
├── 2025_05_23/
│   └── video/
│       ├── 2025_05_23_14_30_45.mkv
│       ├── 2025_05_23_14_30_45_buffer.txt
│       └── 2025_05_23_15_22_10.mkv
└── 2025_05_24/
    └── video/
        └── 2025_05_24_09_15_30.mkv

logs/
├── imx296_capture.log
└── status_monitor.log

config/
└── config.yaml
```

## 📡 LSL Data Streaming

### Stream Format
- **Name**: IMX296Camera
- **Type**: VideoEvents
- **Channels**: 3 (frame_number, trigger_time, trigger_type)
- **Rate**: ~100 Hz (matches camera FPS)

### Usage Example
```python
import pylsl

# Find camera stream
streams = pylsl.resolve_stream('name', 'IMX296Camera')
inlet = pylsl.StreamInlet(streams[0])

# Receive real-time data
while True:
    sample, timestamp = inlet.pull_sample()
    frame_number = int(sample[0])     # Sequential frame counter
    trigger_time = sample[1]          # Unix timestamp
    trigger_type = int(sample[2])     # 0=none, 1=keyboard, 2=ntfy
    
    if trigger_type == 2:  # ntfy trigger (primary method)
        print(f"Frame {frame_number}: ntfy trigger at {trigger_time}")
    elif trigger_type == 1:  # keyboard trigger  
        print(f"Frame {frame_number}: keyboard trigger at {trigger_time}")
```

## 🏗️ System Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   ntfy.sh       │    │   IMX296 Camera  │    │   LSL Stream    │
│   Remote        │───▶│   GScrop + medial│───▶│   3 Channels    │
│   Control       │    │   Auto-Detect    │    │   Independent   │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                │                        │
                                ▼                        ▼
                       ┌──────────────────┐    ┌─────────────────┐
                       │   Rolling        │    │   Status        │
                       │   Buffer         │    │   Monitor       │
                       │   (15s RAM)      │    │   Real-time UI  │
                       └─────────┬────────┘    └─────────────────┘
                                │                        ▲
                                ▼                        │
                       ┌──────────────────┐              │
                       │   Video          │              │
                       │   Recording      │──────────────┘
                       │   (MKV/MJPEG)    │   Status Data
                       └──────────────────┘   (/dev/shm)
```

## 🧪 Testing

### Test Coverage
```bash
# Run all tests
python3 -m unittest discover tests/ -v

# Test categories:
# - Integrated System Tests: 17/17 ✅
# - Status Monitor Tests: 8/8 ✅  
# - Cleanup System Tests: 13/13 ✅
# Total: 38/38 tests passing (100%)
```

### Test Categories
- **Core System**: Configuration, camera initialization, LSL setup
- **Recording Pipeline**: Video recording, buffer integration
- **Remote Control**: ntfy command parsing, message handling
- **Status Monitor**: UI components, data formatting, integration
- **Cleanup System**: Service stopping, file cleanup, verification
- **Performance**: Frame queue performance, system integration

## 💻 Hardware Requirements

### Recommended Setup
- **Raspberry Pi 4/5** (8GB RAM recommended)
- **IMX296 Global Shutter Camera** with proper mounting
- **Fast Storage**: Class 10 SD card or SSD
- **Network**: For ntfy.sh remote control
- **Power**: Adequate power supply for high-speed operation

### Performance Specifications
- **Capture Rate**: 900x600@100fps sustained
- **LSL Latency**: <10ms frame-to-stream
- **Storage Rate**: ~75MB/min (MJPEG @ 900x600)
- **CPU Usage**: <5% for capture, <2% for monitoring
- **RAM Usage**: ~500MB (including 15s buffer)

## 🔧 Systemd Integration

### Service Installation
```bash
# Basic service
sudo cp setup/imx296-camera.service /etc/systemd/system/
sudo systemctl enable imx296-camera

# Service with monitor
sudo cp setup/imx296-camera-monitor.service /etc/systemd/system/
sudo systemctl enable imx296-camera-monitor
sudo systemctl start imx296-camera-monitor
```

### Service Management
```bash
# Start service
sudo systemctl start imx296-camera

# Check status
sudo systemctl status imx296-camera

# View logs
sudo journalctl -u imx296-camera -f

# Stop service
sudo systemctl stop imx296-camera
```

## 🛠️ Troubleshooting

### Camera Detection Issues
```bash
# Check camera connection
libcamera-hello --list-cameras

# Verify media devices
ls /dev/media*

# Test GScrop script
./bin/GScrop 900 600 100 1000
```

### LSL Stream Problems
```bash
# Test LSL installation
python3 -c "import pylsl; print('LSL OK')"

# Find active streams
python3 -c "import pylsl; print(pylsl.resolve_streams())"
```

### Service Issues
```bash
# Check service status
sudo systemctl status imx296-camera

# View detailed logs
sudo journalctl -u imx296-camera -n 50

# Clean restart
./bin/clean_start_camera.sh
```

### Performance Issues
```bash
# Check system resources
python3 bin/status_monitor.py

# Verify frame rate
tail -f /dev/shm/camera_markers.txt

# Test without recording
python3 bin/run_imx296_capture.py --no-recording
```

## 📚 Documentation

- **[Setup Guide](setup/README.md)**: Detailed installation instructions
- **[Binary Tools](bin/README.md)**: Command-line utilities documentation
- **[Implementation Status](docs/IMPLEMENTATION_STATUS.md)**: Feature completion tracking
- **[Test Documentation](tests/README.md)**: Testing procedures and coverage

## 🔄 Development

### Project Structure
```
├── src/imx296_gs_capture/          # Core Python modules
│   ├── imx296_capture.py           # Main capture system (1,247 lines)
│   ├── video_recorder.py           # Video recording pipeline (472 lines)
│   └── ntfy_handler.py             # Remote control system (290 lines)
├── bin/                            # Command-line tools
│   ├── GScrop                      # Camera capture script (384 lines)
│   ├── cleanup_and_start.py        # Cleanup system (421 lines)
│   ├── status_monitor.py           # Real-time monitor (409 lines)
│   └── run_imx296_capture.py       # Main runner (208 lines)
├── tests/                          # Test suite (38 tests)
├── config/                         # Configuration files
├── setup/                          # Installation scripts
└── docs/                           # Documentation
```

### Contributing
1. Fork repository
2. Create feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit pull request

### Key Design Principles
- **Independent Operation**: Components work independently
- **Real-time Performance**: <10ms latencies maintained
- **Comprehensive Testing**: 100% test coverage for critical paths
- **Production Ready**: Service integration and monitoring
- **User-Friendly**: Simple commands and clear feedback

## 📄 License

MIT License - see [LICENSE](LICENSE) file for details.

---

**IMX296 Global Shutter Camera Capture System**  
Complete production-ready solution with 9,577 lines of code  
38/38 tests passing • Real-time performance • Enterprise features

*Built by Anzal KS • Camera systems that just work™*