# Binary Scripts and Utilities

This directory contains executable scripts and utilities for the IMX296 camera system.

## 🧹 Cleanup and Startup Tools

### Clean Start System
- **`clean_start_camera.sh`** - Bash wrapper for comprehensive cleanup and startup
  - Simple, user-friendly interface with color-coded output
  - Automatically cleans up conflicts from previous installations
  - Multiple operational modes (cleanup, start, verify)

- **`cleanup_and_start.py`** - Python-based cleanup and launcher
  - Comprehensive cleanup of services, processes, and files
  - Detailed logging and verification of cleanup operations
  - Fine-grained control over cleanup operations

### Usage Examples

**Quick Clean Start (Recommended):**
```bash
# Clean start with monitor (most common)
./bin/clean_start_camera.sh -m

# Clean start service only
./bin/clean_start_camera.sh

# Cleanup only (no start)
./bin/clean_start_camera.sh -c

# Check system state
./bin/clean_start_camera.sh -v
```

**Python Script (Advanced Control):**
```bash
# Cleanup and start with monitor
python3 bin/cleanup_and_start.py --monitor

# Cleanup only
python3 bin/cleanup_and_start.py --cleanup-only

# Cleanup including logs
python3 bin/cleanup_and_start.py --cleanup-only --logs

# Skip cleanup, start directly
python3 bin/cleanup_and_start.py --no-cleanup --monitor
```

### What Gets Cleaned Up

The cleanup process removes:
- **🔴 Active Services**: Stops all camera-related systemd services
- **🗑️ Service Files**: Removes old systemd service files
- **💀 Processes**: Terminates running camera/LSL/video processes  
- **🧠 Shared Memory**: Cleans up `/dev/shm/` files (status, markers, locks)
- **⚙️ Old Configs**: Removes conflicting configuration files
- **📝 Log Files**: Optionally cleans up old log files
- **🐍 Python Cache**: Removes `__pycache__` directories

### Services Cleaned
- `imx296-camera`
- `imx296-camera-monitor`
- `raspberry-pi-camera`
- `camera-service`
- `lsl-camera`
- `gscrop-camera`

## Core Scripts

### Status Monitor
- **`status_monitor.py`** - Real-time terminal UI for monitoring camera service status
  - Shows LSL streaming status, buffer utilization, recording status, and system info
  - Minimal processor overhead using Python curses
  - Updates every second with live data

### Service Launcher
- **`start_camera_with_monitor.py`** - Launch camera service with optional status monitor
  - Multiple launch modes: service only, with monitor, or monitor only
  - Handles process management and cleanup
  - Integration with systemd services

## Usage Examples

### Start camera service only:
```bash
python bin/start_camera_with_monitor.py
```

### Start camera service with status monitor:
```bash
python bin/start_camera_with_monitor.py --monitor
```

### Start status monitor only (service must be running):
```bash
python bin/start_camera_with_monitor.py --monitor-only
# or directly:
python bin/status_monitor.py
```

## Status Monitor Display

The status monitor shows:
- **Service Status**: Running/stopped, uptime
- **LSL Streaming**: Connection status, sample rate, channel data
- **Rolling Buffer**: Current size, utilization percentage with progress bar
- **Recording Status**: Active/inactive, frames recorded, duration
- **Video Recording**: Status and file information
- **Trigger Status**: Last trigger type, time, total count
- **System Info**: CPU, memory, and disk usage

## Controls

In the status monitor:
- **'q'** - Quit
- **'r'** - Force refresh
- **'c'** - Clear screen

## Technical Details

- Status data is shared via `/dev/shm/imx296_status.json`
- Monitor updates every 1 second
- Service writes status every 2 seconds
- Minimal overhead design for production use

## Systemd Integration

Use the provided service file for automatic startup with status monitor:
```bash
sudo cp setup/imx296-camera-monitor.service /etc/systemd/system/
sudo systemctl enable imx296-camera-monitor
sudo systemctl start imx296-camera-monitor
``` 