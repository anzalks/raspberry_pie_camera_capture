# Desktop Integration

This directory contains desktop GUI and integration files for the IMX296 camera system.

## Desktop Files

### `Camera-Dashboard.desktop`
- **Purpose**: Desktop launcher for the camera dashboard
- **Features**: GUI application launcher with icon and description
- **Usage**: Install to desktop or applications menu for easy access
- **Location**: Can be copied to `~/.local/share/applications/` or `/usr/share/applications/`

### `dashboard.sh`
- **Purpose**: Simple launcher script for the camera dashboard
- **Features**: Basic shell script to start the dashboard
- **Usage**: Direct execution or integration with other scripts

### `create_dashboard.sh`
- **Purpose**: Comprehensive dashboard creation and management script
- **Features**: 
  - Dashboard window creation
  - Real-time status monitoring
  - System metrics display
  - GUI controls integration
- **Usage**: Creates and manages a graphical dashboard interface

## Installation

### Desktop Launcher
```bash
# Install desktop launcher for current user
cp desktop/Camera-Dashboard.desktop ~/.local/share/applications/

# Or install system-wide (requires sudo)
sudo cp desktop/Camera-Dashboard.desktop /usr/share/applications/
```

### Dashboard Setup
```bash
# Make scripts executable
chmod +x desktop/*.sh

# Run dashboard creation
./desktop/create_dashboard.sh
```

## Features

### Dashboard Components
- **Real-time Status**: Live camera and recording status
- **System Metrics**: CPU, memory, storage usage
- **Control Interface**: Start/stop recording buttons
- **Log Viewer**: Real-time log monitoring
- **Configuration**: Settings adjustment interface

### Integration
- Works with ntfy.sh remote control
- Integrates with LSL streaming status
- Monitors video recording pipeline
- Shows system health metrics

## Requirements
- X11 or Wayland display server
- Desktop environment (GNOME, KDE, XFCE, etc.)
- GUI toolkit dependencies (installed via setup scripts)

## Usage Notes
- Dashboard updates in real-time
- Can be minimized to system tray
- Supports multiple monitor setups
- Responsive design for different screen sizes 