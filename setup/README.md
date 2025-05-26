# Setup and Installation

This directory contains installation and system configuration scripts.

## Installation Scripts

### `install.sh`
- **Purpose**: Main installation script for the IMX296 camera capture system
- **Features**: 
  - Dependency installation (Python packages, system packages)
  - Virtual environment setup
  - System configuration
  - Service installation
  - Permission configuration
- **Usage**: Run once during initial system setup
- **Requirements**: sudo privileges

### `configure_imx296_service.sh`
- **Purpose**: Configure and install the systemd service for automatic startup
- **Features**:
  - Service file installation
  - User permissions setup
  - Service enabling and starting
  - Validation checks
- **Usage**: Run after initial installation to enable service mode
- **Requirements**: sudo privileges

## Installation Process

1. **Initial Setup**:
   ```bash
   # Run the main installation script
   sudo ./setup/install.sh
   ```

2. **Service Configuration** (optional):
   ```bash
   # Configure systemd service for automatic startup
   sudo ./setup/configure_imx296_service.sh
   ```

3. **Verification**:
   ```bash
   # Test the installation
   /path/to/conda/envs/dog_track/bin/python tests/test_simple_integration.py
   ```

## What Gets Installed

### Python Dependencies
- pylsl (Lab Streaming Layer)
- requests (ntfy.sh integration)
- yaml (configuration)
- Standard Python libraries

### System Dependencies
- ffmpeg (video recording)
- v4l-utils (camera utilities)
- media-ctl (hardware configuration)

### Configuration
- Systemd service files
- Configuration templates
- Log directories
- Recording directories

## Notes
- Installation requires internet connection for package downloads
- Backup existing configurations before running
- Check logs if installation fails: `logs/install.log` 