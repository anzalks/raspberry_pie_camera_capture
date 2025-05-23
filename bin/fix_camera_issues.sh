#!/bin/bash
# Script to fix IMX296 camera issues: empty recording files and LSL stream problems
# Author: Anzal KS <anzal.ks@gmail.com>
# Date: May 23, 2025

set -e
echo "===== IMX296 Camera Issues Fix Script ====="

# Check if running as root
if [ "$EUID" -ne 0 ]; then
  echo "Please run with sudo to fix system-wide issues"
  exit 1
fi

# Create recordings directory with proper permissions
echo "Fixing recording directory permissions..."
mkdir -p /home/dawg/recordings
chown -R dawg:dawg /home/dawg/recordings
chmod -R 777 /home/dawg/recordings
echo "✓ Recording directory fixed"

# Install correct LSL package to fix the numeric value issues
echo "Fixing LSL stream configuration..."
python3 -m pip install --break-system-packages pylsl==1.16.2
python3 -c 'import pylsl; print(f"PyLSL version: {pylsl.__version__}")' || echo "Warning: PyLSL not properly installed"

# Test numeric LSL values
echo "Testing numeric LSL values..."
python3 -c 'import pylsl; info = pylsl.StreamInfo("Test", "Markers", 1, 0, "float32", "test"); outlet = pylsl.StreamOutlet(info); outlet.push_sample([123.456]); print("✓ Numeric LSL values work")'

# Update config file to ensure MKV format and MJPEG codec
echo "Updating configuration file..."
cat > /etc/imx296-camera/config.yaml << 'EOCFG'
# IMX296 Global Shutter Camera Configuration
# Author: Anzal KS <anzal.ks@gmail.com>
# Date: May 23, 2025

# System paths and tools
system:
  libcamera_vid_path: "/usr/bin/libcamera-vid"
  libcamera_hello_path: "/usr/bin/libcamera-hello"
  media_ctl_path: "/usr/bin/media-ctl"
  ffmpeg_path: "/usr/bin/ffmpeg"

# Camera settings
camera:
  # IMX296 camera is 400x400 native resolution in global shutter mode
  width: 400
  height: 400
  fps: 100  # High-speed capture
  exposure_time_us: 5000  # 5ms exposure 
  pts_file_path: "/tmp/imx296_pts.txt"
  media_ctl:
    device_pattern: "/dev/media%d"
    entity_pattern: "imx296"
    bayer_format: "SBGGR10_1X10"  # Raw Bayer format for IMX296

# RAM buffer settings for pre-trigger storage
buffer:
  duration_seconds: 5
  max_frames: 500  # Increased for higher frame rate

# LSL stream configuration
lsl:
  name: "IMX296Camera"  # Stream name
  type: "VideoEvents"   # Stream type
  id: "cam1"           # Unique identifier

# Recording settings
recording:
  output_dir: "/home/dawg/recordings"  # System path for recordings
  video_format: "mkv"      # Container format (robust against abrupt stops)
  codec: "mjpeg"          # Use MJPEG codec for better compatibility
  quality: 90             # JPEG quality 0-100

# ntfy.sh notifications for remote control
ntfy:
  server: "https://ntfy.sh"
  topic: "raspie-camera-dawg-123"
  poll_interval_sec: 2

# Logging configuration
logging:
  level: "DEBUG"  # Set to DEBUG for more verbose output
  console: true
  file: "/var/log/imx296-camera/imx296_capture.log"
  max_size_mb: 10
  backup_count: 5
EOCFG
echo "✓ Configuration updated"

# Ensure log directory exists with proper permissions
echo "Setting up log directory..."
mkdir -p /var/log/imx296-camera
chown -R dawg:dawg /var/log/imx296-camera
chmod -R 777 /var/log/imx296-camera
echo "✓ Log directory fixed"

# Test camera capture directly to verify it works
echo "Testing direct camera capture..."
if ! python3 -c "
import subprocess
import os
import time

# Test if we can capture directly with libcamera-vid to ffmpeg
try:
    # Start libcamera-vid process
    camera_cmd = [
        '/usr/bin/libcamera-vid',
        '--width', '400',
        '--height', '400',
        '--framerate', '100',
        '--codec', 'mjpeg',
        '--inline',
        '--nopreview',
        '--timeout', '3000',
        '--output', '-'
    ]
    
    # Start ffmpeg process
    ffmpeg_cmd = [
        '/usr/bin/ffmpeg',
        '-f', 'mjpeg',
        '-i', '-',
        '-c:v', 'copy',
        '-an',
        '-y',
        '/tmp/test_capture.mkv'
    ]
    
    # Run the command
    camera_process = subprocess.Popen(camera_cmd, stdout=subprocess.PIPE)
    ffmpeg_process = subprocess.Popen(ffmpeg_cmd, stdin=camera_process.stdout)
    
    # Wait for 3 seconds
    time.sleep(3)
    
    # Terminate processes
    camera_process.terminate()
    ffmpeg_process.terminate()
    camera_process.wait(timeout=5)
    ffmpeg_process.wait(timeout=5)
    
    # Check file size
    file_size = os.path.getsize('/tmp/test_capture.mkv')
    print(f'Test capture complete. File size: {file_size} bytes')
    
    if file_size > 5000:
        print('Success: Test capture created a valid file')
        exit(0)
    else:
        print('Error: Test capture created empty file')
        exit(1)
        
except Exception as e:
    print(f'Error during test capture: {e}')
    exit(1)
"; then
    echo "✗ Direct capture test failed! Please check camera connection"
    # Continue anyway
else
    echo "✓ Direct capture test successful!"
fi

# Restart the service
echo "Restarting camera service..."
systemctl restart imx296-camera.service
sleep 2

# Check service status
if systemctl is-active --quiet imx296-camera.service; then
    echo "✓ Service is running"
else
    echo "✗ Service failed to start"
    echo "Check logs: journalctl -u imx296-camera.service"
fi

echo ""
echo "Fixes applied! Please check the camera status with:"
echo "/home/dawg/Downloads/insha_rpie/raspberry_pie_camera_capture/bin/view-camera-status.sh"
echo ""
echo "If issues persist, check the logs:"
echo "tail -f /var/log/imx296-camera/imx296_capture.log"
