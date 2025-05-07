# Raspberry Pi Camera Capture - Setup Guide

This guide will walk you through setting up the camera capture system on your Raspberry Pi.

## Prerequisites

- Raspberry Pi (tested with Pi 4/5) running Raspberry Pi OS Bookworm or later
- Raspberry Pi Camera Module or USB webcam
- Internet connection for ntfy integration
- Optional: VNC Server for remote monitoring

## 1. Clone the Repository

```bash
# Navigate to the Downloads directory (or your preferred location)
cd ~/Downloads

# Clone the repository
git clone https://github.com/anzalks/raspberry_pie_camera_capture.git

# Navigate to the project directory
cd raspberry_pie_camera_capture

# Check out the fix-indentation branch
git checkout fix-indentation
```

## 2. Run the Test Installation Script

```bash
# Make the test script executable
chmod +x test-installation.sh

# Run the test script
./test-installation.sh
```

This will:
- Create a virtual environment
- Install the required dependencies
- Check for camera presence
- Test the ntfy integration
- Verify that everything is working correctly

## 3. Configure Auto-Start Service

The service will start the camera capture system automatically when the Raspberry Pi boots.

```bash
# Make the service installation script executable
chmod +x raspie-camera-service.sh

# Install the service (requires sudo)
sudo bash raspie-camera-service.sh
```

The service will now start automatically on boot. You can manage it using the provided script:

```bash
# Check the service status
./raspie-service-manager.sh status

# View the service logs
./raspie-service-manager.sh logs

# Manually start the service
./raspie-service-manager.sh start

# Manually stop the service
./raspie-service-manager.sh stop
```

## 4. Remote Control via ntfy

You can control the recording remotely using ntfy.sh:

```bash
# Start recording
curl -d "Start Recording" ntfy.sh/raspie-camera-test

# Stop recording
curl -d "Stop Recording" ntfy.sh/raspie-camera-test
```

You can use the management script for convenience:

```bash
# Start recording
./raspie-service-manager.sh trigger

# Stop recording
./raspie-service-manager.sh stop-recording
```

## 5. Monitoring via VNC

To monitor the camera capture system remotely:

1. Enable VNC Server on your Raspberry Pi
   ```bash
   sudo raspi-config
   # Navigate to Interface Options > VNC > Enable
   ```

2. Connect to your Raspberry Pi using a VNC viewer

3. The status display will show:
   - Camera details (model, resolution)
   - Recording status
   - Buffer statistics
   - Frame counts (captured, written, dropped)
   - ntfy topic and last message received

## 6. Recorded Videos

The recorded videos are saved in the `recordings` directory by default. Each recording is timestamped with the start time:

```bash
# List recorded videos
ls -la ~/Downloads/raspberry_pie_camera_capture/recordings
```

## Troubleshooting

### Camera Not Detected

1. Check if the camera is properly connected
2. For Pi Camera: Ensure it's enabled in raspi-config
3. Check the available video devices:
   ```bash
   ls -la /dev/video*
   ```
4. Test the camera with a basic command:
   ```bash
   libcamera-hello
   ```

### Service Not Starting

1. Check the service status:
   ```bash
   systemctl status raspie-camera
   ```
2. Check the logs:
   ```bash
   journalctl -u raspie-camera
   ```

### ntfy Commands Not Working

1. Check your internet connection
2. Verify the ntfy topic is correct
3. Test with a direct curl command:
   ```bash
   curl -d "Test message" ntfy.sh/raspie-camera-test
   ```

## Customization

You can customize the service by editing the systemd service file:

```bash
sudo nano /etc/systemd/system/raspie-camera.service
```

After making changes, reload the daemon and restart the service:

```bash
sudo systemctl daemon-reload
sudo systemctl restart raspie-camera
``` 