# Raspie Capture Quick-Start Guide

This guide provides a quick overview of how to set up Raspie Capture to start automatically at boot and control recordings remotely using ntfy.sh notifications.

## 1. Installation

First, install the package and its dependencies:

```bash
# Clone the repository
git clone https://github.com/Dognosis/raspberry_pie_camera_capture.git
cd raspberry_pie_camera_capture

# Run the setup script (requires sudo)
sudo bash setup_pi.sh

# Activate the virtual environment
source .venv/bin/activate
```

## 2. Auto-Start on Boot

To configure Raspie Capture to start automatically when your Raspberry Pi boots:

```bash
# Install the service (requires sudo)
sudo bash raspi-capture-service.sh

# (Optional) Optimize Raspberry Pi performance
sudo bash raspie-optimize.sh

# Reboot to apply all changes
sudo reboot
```

After reboot, the service will start automatically with:
- Rolling buffer mode (20 seconds)
- Ntfy.sh triggering on topic "raspie_trigger"
- Audio and video capture enabled
- H.264 hardware encoding

## 3. Remote Trigger via ntfy.sh

Control recordings from any device with internet access:

### Start Recording

```bash
# Send start trigger
curl -d "start recording" ntfy.sh/raspie_trigger
```

### Stop Recording

```bash
# Send stop trigger
curl -d "stop recording" ntfy.sh/raspie_trigger
```

You can also use the ntfy.sh mobile app or any HTTP client that can send POST requests.

## 4. Service Management

The installation creates a convenient management script:

```bash
# Check service status
./raspie-service.sh status

# View logs in real-time
./raspie-service.sh logs

# Start service manually (if not already running)
./raspie-service.sh start

# Stop service
./raspie-service.sh stop

# Send start/stop triggers
./raspie-service.sh trigger
./raspie-service.sh stop-recording
```

## 5. Viewing Recorded Files

Recordings are saved in the project directory by default:
- Video: `raspie_video_TIMESTAMP.mkv`
- Audio: `raspie_audio_TIMESTAMP.wav`

When using the RAM disk optimization, files are temporarily stored in `/mnt/ramdisk` and should be copied to permanent storage after recording.

## 6. Troubleshooting

If the service fails to start:

```bash
# Check service status for errors
sudo systemctl status raspie-capture.service

# View detailed logs
sudo journalctl -u raspie-capture.service

# Restart the service
sudo systemctl restart raspie-capture.service
```

Common issues:
- Camera not enabled in raspi-config
- Missing permissions
- No internet connection for ntfy.sh

## 7. Testing with Visualizers

For testing and debugging, you can use the visualization tools:

```bash
# Activate the environment
source .venv/bin/activate

# Run with visualizers
bash examples/run_visualizers.sh
```

This will show audio and video preview windows and still support ntfy.sh triggering. 