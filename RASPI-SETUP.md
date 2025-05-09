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

## Additional Information

For more information on testing and verification, see [TESTING.md](TESTING.md).

# Raspberry Pi Setup Guide

This guide will walk you through setting up your Raspberry Pi to use the camera capture system.

## Prerequisites

- Raspberry Pi (tested on Raspberry Pi 4 Model B)
- Raspberry Pi OS (tested on Bullseye)
- USB Camera or Raspberry Pi Camera Module
- Internet connection for the Raspberry Pi

## Setup Instructions

### 1. Clone the repository

```bash
git clone https://github.com/anzalks/raspberry_pie_camera_capture.git
cd raspberry_pie_camera_capture
```

### 2. Run the setup script

```bash
chmod +x setup_pi.sh
./setup_pi.sh
```

The setup script will:
- Create a Python virtual environment
- Install all required dependencies
- Set up LSL library
- Configure the camera
- Run basic tests

### 3. Install the service

```bash
sudo bash raspie-camera-service.sh
```

This will set up the camera capture service to start automatically on boot.

### 4. Testing

Run the test script to verify that everything is working:

```bash
chmod +x test-installation.sh
./test-installation.sh
```

### 5. Using the Camera Service

The camera service will automatically start on boot. The camera will continuously capture frames and store them in a rolling buffer. When triggered (via ntfy notification), the system will save the buffered frames to a video file.

#### Control the service

You can control the service using the service manager script:

```bash
# Start the service
./raspie-service-manager.sh start

# Stop the service
./raspie-service-manager.sh stop

# Restart the service
./raspie-service-manager.sh restart

# Check status
./raspie-service-manager.sh status

# View logs
./raspie-service-manager.sh logs
```

#### Trigger a recording

You can trigger a recording by sending a notification to the ntfy topic:

```bash
curl -d "Save recording" ntfy.sh/raspicamera-trigger
```

Or use the service manager:

```bash
./raspie-service-manager.sh trigger
```

## Environment Management

### Automatic Virtual Environment Activation

To make development easier, we've provided a script that automatically activates the virtual environment when you navigate to the project directory:

```bash
# Install auto-activation
./auto-activate.sh
```

After running this script, whenever you cd into the `raspberry_pie_camera_capture` directory, the virtual environment will be automatically activated. You can also use the alias `raspi-camera` to quickly navigate to the project directory with the environment activated.

### Environment Check

To verify your environment is properly set up for camera capture:

```bash
./check-camera-env.py
```

This will check that all required libraries are installed and the camera is accessible.

### Quick Run Script

For manual testing, use the run-camera.sh wrapper script which ensures the correct environment:

```bash
# Run with default options
./run-camera.sh

# Run with specific options
./run-camera.sh --camera-id 0 --save-video --output-dir recordings
```

## Troubleshooting

### Camera Not Detected

1. Check that the camera is properly connected
2. Make sure your user is in the `video` group: `sudo usermod -a -G video $USER`
3. For Raspberry Pi Camera Module, ensure it's enabled: `sudo raspi-config`
4. Check camera is working with: `v4l2-ctl --list-devices`

### Dependencies Issues

If you're experiencing import errors:

1. Make sure the virtual environment is activated: `source .venv/bin/activate`
2. Try reinstalling the required packages: `pip install -r requirements.txt`
3. For system-level packages like picamera2, you may need to install them system-wide: `sudo apt-get install python3-picamera2`

### Service Not Starting

1. Check the service status: `sudo systemctl status raspie-camera`
2. View the logs: `sudo journalctl -u raspie-camera`
3. Ensure all permissions are correct: `sudo chown -R $USER:$USER ~/raspberry_pie_camera_capture`

## Additional Information

For more information on testing and verification, see [TESTING.md](TESTING.md).