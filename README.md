# IMX296 Global Shutter Camera Capture System

Complete high-performance camera capture system for IMX296 Global Shutter camera with automatic detection, independent streaming, and real-time data streaming.

## ✅ Features Completed

### Core Functionality (100% Complete)
- ✅ **IMX296 Global Shutter Camera Integration** - Complete GScrop-based capture system with automatic detection
- ✅ **LSL 3-Channel Streaming** - Real-time metadata streaming (frame_number, trigger_time, trigger_type)
  - Independent streaming that runs continuously regardless of recording state
- ✅ **ntfy.sh Remote Control** - Complete smartphone integration
- ✅ **Video Recording Pipeline** - MKV output with organized folder structure (independent operation)
- ✅ **Pre-Notification Rolling Buffer** - Continuous RAM buffer for pre-trigger frame storage

### Advanced Features (100% Complete)
- ✅ **Automatic Camera Detection** - Detects IMX296 camera and configures media pipeline automatically
- ✅ **Independent Operation** - Video recording, LSL streaming, and buffer operate independently of triggers
- ✅ **Trigger-to-Trigger Recording** - Records from start command to stop command (ntfy or keystroke)
- ✅ **Rolling Buffer Integration** - Automatically saves buffered frames when recording starts
- ✅ **Multi-format Output** - Raw markers + MKV video files
- ✅ **Comprehensive Testing** - 17/17 tests passing

## Features

### 🎥 **GScrop-Based Capture**
- Hardware-level cropping using media-ctl for optimal performance
- **900x600@100fps** capture with precise frame timing
- Automatic IMX296 camera detection and configuration
- Frame markers system for accurate timestamping

### 📡 **3-Channel LSL Streaming (Independent)**
- **frame_number**: Sequential frame counter
- **trigger_time**: Unix timestamp when trigger occurred  
- **trigger_type**: 0=none, 1=keyboard, 2=ntfy
- **Independent operation**: Streams continuously regardless of recording state

### 📱 **ntfy.sh Remote Control**
- Start/stop recording remotely via smartphone notifications
- Real-time status updates and error notifications
- Simple text commands or JSON API support

### 🎬 **Video Recording Pipeline (Independent)**
- **Independent operation**: Records continuously, not dependent on triggers
- Organized folder structure: `recordings/yyyy_mm_dd/video/`
- MKV format with MJPEG/H.264 codec support
- **900x600 resolution** at 100fps
- Automatic filename generation with timestamps

### 🔧 **Service Integration**
- Systemd service support for automatic startup
- Comprehensive logging and error handling
- Clean shutdown and resource management

### 🔄 **Pre-Trigger Rolling Buffer**
- **Continuous RAM buffer**: Always capturing frames in background
- **Configurable duration**: Default 15 seconds of pre-trigger frames
- **Instant trigger response**: Buffer saved immediately when recording starts
- **Frame metadata preservation**: Buffer frames saved as `filename_buffer.txt`

## Quick Start

### 1. Installation
```bash
# Clone repository
git clone https://github.com/anzalks/raspberry_pie_camera_capture.git
cd raspberry_pie_camera_capture

# Install dependencies
./install.sh

# Configure camera
sudo ./setup/configure_imx296_service.sh
```

### 2. Configuration
Edit `config/config.yaml`:
```yaml
camera:
  width: 900           # Updated resolution
  height: 600          # Updated resolution
  fps: 100
  exposure_time_us: 5000
  auto_detect: true    # Automatic camera detection

ntfy:
  topic: "your-unique-camera-topic"
  
recording:
  output_dir: "recordings"
  video_format: "mkv"
  codec: "mjpeg"
```

### 3. Run System
```bash
# Direct execution
python3 bin/run_imx296_capture.py

# Or as service
sudo systemctl start imx296-camera
sudo systemctl enable imx296-camera
```

## Remote Control via ntfy.sh

### Setup Mobile App
1. Install ntfy app on your phone
2. Subscribe to your camera topic
3. Send commands as notifications

### Commands

**Start Recording:**
```
start_recording
start_recording 30    # Record for 30 seconds
{"command": "start_recording", "duration": 60}
```

**Stop Recording:**
```
stop_recording
```

**Get Status:**
```
status
```

### Example Workflow
1. **Start System**: Camera boots and sends "🟢 Ready for commands"
2. **Independent Streaming**: LSL and video recording start automatically
3. **Remote Start**: Send "start_recording 30" from phone
4. **Confirmation**: Receive "🔴 Recording for 30s"
5. **Completion**: Receive "⏹️ Recording completed - 3000 frames"

## File Structure

```
recordings/
├── 2025_05_23/
│   └── video/
│       ├── 2025_05_23_14_30_45.mkv
│       └── 2025_05_23_15_22_10.mkv
└── 2025_05_24/
    └── video/
        └── 2025_05_24_09_15_30.mkv
```

## LSL Data Streaming (Independent)

The system streams real-time data via Lab Streaming Layer continuously:

```python
import pylsl

# Find camera stream
streams = pylsl.resolve_stream('name', 'IMX296Camera')
inlet = pylsl.StreamInlet(streams[0])

# Receive data
while True:
    sample, timestamp = inlet.pull_sample()
    frame_number = sample[0]      # Sequential frame number
    trigger_time = sample[1]      # Unix timestamp when trigger occurred
    trigger_type = sample[2]      # 0=none, 1=keyboard, 2=ntfy
    # timestamp provided by LSL automatically
```

## System Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   ntfy.sh       │    │   IMX296 Camera  │    │   LSL Stream    │
│   Remote        │───▶│   GScrop         │───▶│   3 Channels    │
│   Control       │    │   Auto-Detect    │    │   Independent   │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                │                        
                                ▼                        
                       ┌──────────────────┐              
                       │   Rolling        │              
                       │   Buffer         │              
                       │   (RAM)          │              
                       └─────────┬────────┘              
                                │                        
                                ▼                        
                       ┌──────────────────┐              
                       │   Video          │              
                       │   Recording      │              
                       │   Independent    │              
                       └──────────────────┘              
```

## Hardware Requirements

- **Raspberry Pi 4/5** with IMX296 Global Shutter camera
- **8GB+ RAM** recommended for high-speed capture
- **Fast SD card** (Class 10 or better) or SSD
- **Network connection** for ntfy.sh remote control

## Performance

- **Capture Rate**: 900x600@100fps sustained
- **LSL Latency**: <10ms frame-to-stream
- **Remote Response**: <2s command-to-action
- **Storage**: ~75MB/min for MJPEG video (900x600)

## Troubleshooting

### Camera Not Detected
```bash
# Check camera connection
sudo bin/diagnose_imx296.sh

# Verify media device
ls /dev/media*

# Check auto-detection
media-ctl -d /dev/media0 -e imx296
```

### LSL Stream Issues
```bash
# Test LSL connectivity
python3 -c "import pylsl; print(pylsl.resolve_streams())"
```

### ntfy.sh Connection
```bash
# Test notification
curl -d "test message" https://ntfy.sh/your-topic
```

### Video Recording Problems
```bash
# Check ffmpeg
ffmpeg -version

# Test video device
ffmpeg -f v4l2 -i /dev/video0 -t 5 test.mkv
```

## Development

### Running Tests
```bash
# Simple integration test (5/5 tests)
python3 tests/test_simple_integration.py

# Full test suite (17/17 tests)  
python3 tests/test_integrated_system.py

# GScrop integration test (4/4 tests)
python3 tests/test_gscrop_integration.py
```

**Test Status: ✅ ALL TESTS PASSING (26/26 total tests)**

### Implementation Status

| Feature | Status | Details |
|---------|--------|---------|
| 3-Channel LSL Streaming | ✅ Complete | frame_number, trigger_time, trigger_type (independent) |
| Automatic Camera Detection | ✅ Complete | Auto-detects IMX296 and configures media pipeline |
| Independent Operation | ✅ Complete | Video, LSL, buffer operate independently of triggers |
| ntfy.sh Remote Control | ✅ Complete | Full smartphone integration with status notifications |
| Video Recording Pipeline | ✅ Complete | 900x600@100fps, organized structure |
| GScrop Camera Capture | ✅ Complete | Hardware-level cropping with frame markers |
| Testing Framework | ✅ Complete | Comprehensive test coverage with mocking |

### Adding Features
1. **New Commands**: Add to `ntfy_handler.py` supported_commands
2. **Video Codecs**: Extend `video_recorder.py` codec options
3. **LSL Channels**: Modify `imx296_capture.py` LSL setup

## License

MIT License - see LICENSE file for details.

## Author

**Anzal KS** <anzal.ks@gmail.com>  
GitHub: https://github.com/anzalks/

---

*Built for high-speed behavioral research and real-time monitoring applications.*

## Project Structure

```
├── bin/                    # Main executables
│   ├── GScrop             # Core camera capture script
│   └── run_imx296_capture.py  # Main launcher
├── config/                # Configuration files
│   ├── config.yaml        # Main configuration
│   └── imx296-camera.service  # Systemd service
├── desktop/               # Desktop integration
│   ├── Camera-Dashboard.desktop  # Desktop launcher
│   └── create_dashboard.sh      # Dashboard creation
├── scripts/               # Utility scripts
│   ├── diagnose_camera.sh      # System diagnostics
│   ├── check_recording.sh      # Status monitoring
│   └── restart_camera.sh       # System management
├── setup/                 # Installation scripts
│   ├── install.sh         # Main installer
│   └── configure_imx296_service.sh  # Service setup
├── src/                   # Source code
│   └── imx296_gs_capture/ # Main module
│       ├── imx296_capture.py   # Core capture system
│       ├── ntfy_handler.py     # Remote control
│       └── video_recorder.py   # Video pipeline
├── tests/                 # Test suite
│   ├── test_simple_integration.py    # Basic tests
│   ├── test_integrated_system.py     # Full system tests
│   └── test_gscrop_integration.py    # GScrop tests
├── logs/                  # Log files
└── recordings/            # Video recordings
    └── yyyy_mm_dd/video/  # Organized by date
```

## Development 