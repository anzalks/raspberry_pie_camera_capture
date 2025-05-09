# Testing the Raspberry Pi Camera Capture System

This document outlines the steps to test the camera capture system after installation.

## 1. Basic Functionality Test

```bash
# Navigate to the project directory
cd ~/Downloads/raspberry_pie_camera_capture

# Activate the virtual environment
source .venv/bin/activate

# Run the camera capture with basic options
python -m src.raspberry_pi_lsl_stream.camera_capture --save-video --output-dir recordings
```

Verify that:
- The camera is detected
- The status display shows correctly in the terminal
- The buffer size increases as frames are captured

## 2. Testing ntfy Integration

With the camera capture running, open a new terminal and execute:

```bash
# Send a start recording trigger
curl -d "Start Recording" ntfy.sh/raspie-camera-test
```

Verify that:
- The status display changes to "RECORDING"
- The notification is shown in the status display
- A recording file is created in the recordings directory

Then stop the recording:

```bash
# Send a stop recording trigger
curl -d "Stop Recording" ntfy.sh/raspie-camera-test
```

Verify that:
- The status display changes back to "WAITING FOR TRIGGER"
- The recording file is properly saved
- The buffer starts filling up again

## 3. Testing the Auto-Start Service

After installing the service:

```bash
# Reboot the Raspberry Pi
sudo reboot
```

After the reboot, verify that:
- The camera capture is running automatically
- The service is active in systemctl:
  ```bash
  systemctl status raspie-camera
  ```
- You can control it with the manager script:
  ```bash
  # Check status
  ./raspie-service-manager.sh status
  
  # Trigger recording
  ./raspie-service-manager.sh trigger
  
  # Stop recording
  ./raspie-service-manager.sh stop-recording
  ```

## 4. Verify Recordings

```bash
# List the recordings directory
ls -la ~/Downloads/raspberry_pie_camera_capture/recordings

# Play a recording (if you have a display)
vlc recordings/recording_YYYYMMDD_HHMMSS.mp4
```

Verify that:
- The recording file exists
- The timestamp in the filename corresponds to when you started recording
- The video contains the intended footage

## 5. VNC Monitoring Test

1. Connect to your Raspberry Pi using VNC Viewer

2. Open a terminal and run:
   ```bash
   cd ~/Downloads/raspberry_pie_camera_capture
   source .venv/bin/activate
   python -m src.raspberry_pi_lsl_stream.camera_capture --save-video --output-dir recordings --no-preview
   ```

3. Verify that:
   - The status display is visible and updating
   - You can monitor the system remotely

4. Send recording commands from your local machine and verify they work:
   ```bash
   curl -d "Start Recording" ntfy.sh/raspie-camera-test
   # Wait a few seconds
   curl -d "Stop Recording" ntfy.sh/raspie-camera-test
   ```

## 6. Long Duration Test

1. Start the camera capture:
   ```bash
   python -m src.raspberry_pi_lsl_stream.camera_capture --save-video --output-dir recordings --no-preview
   ```

2. Send a start recording command:
   ```bash
   curl -d "Start Recording" ntfy.sh/raspie-camera-test
   ```

3. Let it record for at least 10 minutes

4. Stop the recording:
   ```bash
   curl -d "Stop Recording" ntfy.sh/raspie-camera-test
   ```

5. Verify that:
   - The system remained stable for the duration
   - The recording file is intact and contains all the footage
   - No frames were dropped (check the status display)

## 7. Error Recovery Test

With the service running:

1. Forcibly kill the process:
   ```bash
   sudo systemctl kill raspie-camera
   ```

2. Wait for the service to restart automatically (should be within 10 seconds)

3. Verify that:
   - The service recovers and restarts
   - The camera is re-initialized
   - The buffer starts filling again

## Additional Tests

### Testing Multiple Start/Stop Cycles

1. Start recording:
   ```bash
   curl -d "Start Recording" ntfy.sh/raspie-camera-test
   ```

2. Wait 30 seconds

3. Stop recording:
   ```bash
   curl -d "Stop Recording" ntfy.sh/raspie-camera-test
   ```

4. Repeat steps 1-3 several times

5. Verify that:
   - Each recording cycle creates a new file
   - No errors occur during repeated start/stop cycles
   - The system remains stable

### Testing with Camera Preview

Run the camera capture with preview enabled (requires display):
```bash
python -m src.raspberry_pi_lsl_stream.camera_capture --save-video --output-dir recordings
```

Verify that:
- The camera preview window appears
- The preview updates in real-time
- The status display still functions correctly 