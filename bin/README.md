# Binary Scripts and Utilities

This directory contains executable scripts and utilities for the IMX296 camera system.

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