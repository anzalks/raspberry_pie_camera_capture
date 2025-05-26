# IMX296 Global Shutter Camera Capture System

A high-performance camera capture system for the IMX296 Global Shutter camera on Raspberry Pi, designed for precise timestamping and LSL integration.

## Features

- **GScrop-based capture**: Hardware-accelerated frame capture with precise timing
- **LSL integration**: Real-time streaming of frame timing data via Lab Streaming Layer
- **ntfy.sh remote control**: Start/stop recording remotely via notifications
- **RAM buffering**: Pre-trigger storage for capturing events that happened before the trigger
- **Dashboard monitoring**: Web-based status monitoring and control
- **Service management**: Systemd integration for automatic startup and reliability

## Hardware Requirements

- Raspberry Pi (4 or 5)
- IMX296 Global Shutter Camera
- Sufficient RAM for buffering (recommended: 4GB+)

## Quick Start

1. **Installation**: Run the installation script:
   ```bash
   sudo bash bin/install.sh
   ```

2. **Configuration**: Edit `config/config.yaml` to match your setup

3. **Start the service**:
   ```bash
   sudo systemctl start imx296-camera
   sudo systemctl enable imx296-camera
   ```

4. **Monitor status**:
   ```bash
   bash bin/view-camera-status.sh
   ```

## Configuration

The system is configured via `config/config.yaml`. Key settings include:

- **Camera resolution**: 400x400 native IMX296 resolution
- **Frame rate**: Up to 100 FPS (adjustable)
- **Exposure time**: Configurable in microseconds  
- **Output directory**: Where recordings are saved
- **LSL settings**: Stream name and metadata
- **ntfy.sh topic**: For remote control

## Remote Control

Send notifications to your ntfy.sh topic:
- **Start recording**: Send "start_recording" message
- **Stop recording**: Send "stop_recording" message

## Author

Anzal KS <anzal.ks@gmail.com>
GitHub: https://github.com/anzalks/

## License

MIT License 