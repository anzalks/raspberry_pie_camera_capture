# Main Executables

This directory contains the core executable files for the IMX296 camera capture system.

## Executables

### `run_imx296_capture.py`
- **Purpose**: Main launcher script for the IMX296 camera capture system
- **Features**:
  - System initialization and validation
  - Camera device detection and reset
  - GScrop script execution management
  - Environment setup and configuration loading
  - Graceful error handling and logging
- **Usage**: Primary entry point for running the camera system
- **Requirements**: Proper conda environment activation

### `GScrop`
- **Purpose**: Core camera capture script using GScrop (Global Shutter Crop) method
- **Features**:
  - Hardware-level cropping using media-ctl
  - High-speed frame capture (400x400@100fps)
  - Frame markers generation for precise timing
  - Raw video output with timestamp metadata
- **Usage**: Called by the main capture system (not typically run directly)
- **Requirements**: IMX296 camera hardware, proper media device configuration

## Usage

### Starting the Camera System
```bash
# Activate the conda environment and run
/path/to/conda/envs/dog_track/bin/python bin/run_imx296_capture.py

# Or from within the activated environment
python bin/run_imx296_capture.py
```

### Configuration
- Ensure `config/config.yaml` is properly configured
- Verify camera hardware is connected and detected
- Check that all dependencies are installed

### Output
- **Logs**: Written to `logs/` directory
- **Recordings**: Saved to `recordings/yyyy_mm_dd/video/` structure
- **Markers**: Frame timing data in `/dev/shm/camera_markers.txt`

## Integration

### Components Used
- **LSL Streaming**: 3-channel real-time data stream
- **ntfy.sh**: Remote control via smartphone notifications
- **Video Recording**: MKV format with organized folder structure
- **System Monitoring**: Real-time status and diagnostics

### Service Integration
- Can be run as systemd service for automatic startup
- Integrates with desktop dashboard for GUI control
- Supports remote monitoring and control

## Troubleshooting

### Common Issues
1. **Camera not detected**: Run `scripts/diagnose_camera.sh`
2. **Permission errors**: Check user groups and device permissions
3. **Import errors**: Verify conda environment and dependencies
4. **GScrop failures**: Check media device configuration

### Debug Mode
```bash
# Run with debug logging
DEBUG=1 python bin/run_imx296_capture.py
``` 