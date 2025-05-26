# Utility Scripts

This directory contains utility and management scripts for the IMX296 camera system.

## Diagnostic Scripts

### `diagnose_camera.sh`
- **Purpose**: Comprehensive camera system diagnostics
- **Features**: Hardware detection, driver status, device permissions, configuration validation
- **Usage**: Run when troubleshooting camera issues

### `diagnose_imx296.sh`
- **Purpose**: Specific IMX296 camera diagnostics and configuration
- **Features**: IMX296-specific checks, media device configuration, capture pipeline validation
- **Usage**: IMX296-focused troubleshooting

## Monitoring Scripts

### `check_recording.sh`
- **Purpose**: Check current recording status and system health
- **Features**: Recording status, disk space, process monitoring
- **Usage**: Quick status check for recording operations

### `view-camera-status.sh`
- **Purpose**: Comprehensive system status viewer with real-time monitoring
- **Features**: Live status updates, LSL stream monitoring, system metrics
- **Usage**: Real-time system monitoring

## Management Scripts

### `restart_camera.sh`
- **Purpose**: Gracefully restart the camera capture system
- **Features**: Safe shutdown, service restart, validation
- **Usage**: System restart without manual intervention

### `update_camera_stream.sh`
- **Purpose**: Update camera streaming configuration and restart services
- **Features**: Configuration updates, service management, validation
- **Usage**: Apply configuration changes dynamically

## Usage

All scripts should be run from the project root directory:

```bash
# Example usage
./scripts/diagnose_camera.sh
./scripts/check_recording.sh
./scripts/restart_camera.sh
```

## Notes
- Scripts may require sudo privileges for some operations
- Ensure proper permissions: `chmod +x scripts/*.sh`
- Check individual script headers for specific requirements 