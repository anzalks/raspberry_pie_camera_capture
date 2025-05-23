#!/bin/bash
# IMX296 Camera Installation Script
# Author: Anzal KS <anzal.ks@gmail.com>
# Date: May 23, 2025

set -e

echo "Installing IMX296 Camera Software..."

# Check if running as root
if [ "$EUID" -ne 0 ]; then
  echo "Please run as root (use sudo)"
  exit 1
fi

# Function to check if a command exists
command_exists() {
  command -v "$1" >/dev/null 2>&1
}

# Check for required tools
for cmd in python3 pip3 libcamera-vid ffmpeg media-ctl; do
  if ! command_exists "$cmd"; then
    echo "Error: Required command '$cmd' not found"
    echo "Please install it first with:"
    echo "  sudo apt update && sudo apt install -y python3-pip ffmpeg libcamera-apps v4l-utils"
    exit 1
  fi
fi

# Install Python dependencies
echo "Installing Python dependencies..."
python3 -m pip install --upgrade pip
python3 -m pip install pylsl pyyaml python-dateutil psutil ntfy pyzmq pydantic 

# Try to reinstall pylsl specifically (this fixes LSL issues)
echo "Ensuring pylsl is properly installed..."
python3 -m pip install --force-reinstall pylsl

# Verify pylsl installation
if python3 -c "import pylsl; print(f'PyLSL version: {pylsl.__version__}')" 2>/dev/null; then
  echo "✓ PyLSL installation verified"
else
  echo "⚠ PyLSL installation failed - will try once more"
  python3 -m pip install --no-cache-dir pylsl==1.16.2
fi

# Create config directory if it doesn't exist
echo "Setting up configuration..."
mkdir -p /etc/imx296-camera

# Copy config file to system location
echo "Copying config file to system location: /etc/imx296-camera/config.yaml"
cp -v config/config.yaml /etc/imx296-camera/

# Verify the config file was copied
if [ -f "/etc/imx296-camera/config.yaml" ]; then
  echo "✓ Config file successfully copied"
  cat /etc/imx296-camera/config.yaml | head -n 5  # Show first 5 lines to verify
else
  echo "⚠ Failed to copy config file! Creating it directly..."
  # Create a minimal config file directly
  cat > /etc/imx296-camera/config.yaml << 'EOF'
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
  width: 400
  height: 400
  fps: 30
  exposure_time_us: 5000
  pts_file_path: "/tmp/imx296_pts.txt"
  media_ctl:
    device_pattern: "/dev/media%d"
    entity_pattern: "imx296"
    bayer_format: "SBGGR10_1X10"

# Buffer settings
buffer:
  duration_seconds: 5
  max_frames: 300

# LSL stream configuration
lsl:
  name: "IMX296Camera"
  type: "VideoEvents"
  id: "cam1"

# Recording settings
recording:
  output_dir: "/home/dawg/recordings"
  video_format: "mkv"
  codec: "mjpeg"
  quality: 90

# ntfy.sh notifications
ntfy:
  server: "https://ntfy.sh"
  topic: "raspie-camera-dawg-123"
  poll_interval_sec: 2

# Logging configuration
logging:
  level: "DEBUG"
  console: true
  file: "logs/imx296_capture.log"
  max_size_mb: 10
  backup_count: 5
EOF
  echo "✓ Created config file directly"
fi

# Copy Python package
echo "Installing Python package..."
python3 -m pip install -e .

# Create service file
echo "Creating systemd service..."
cat > /etc/systemd/system/imx296-camera.service << 'EOF'
[Unit]
Description=IMX296 Global Shutter Camera Service
After=network.target

[Service]
ExecStart=/usr/bin/python3 -m imx296_gs_capture.imx296_capture
WorkingDirectory=/opt/imx296-camera
User=dawg
Group=video
Restart=on-failure
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

# Create directories
echo "Creating application directories..."
mkdir -p /opt/imx296-camera
mkdir -p /home/dawg/recordings
chown -R dawg:dawg /home/dawg/recordings
chmod -R 777 /home/dawg/recordings

# Copy application files
echo "Copying application files to /opt/imx296-camera..."
cp -r src /opt/imx296-camera/
cp -r bin /opt/imx296-camera/
cp -r config /opt/imx296-camera/
cp README.md /opt/imx296-camera/
cp install.sh /opt/imx296-camera/
cp setup.py /opt/imx296-camera/

# Set permissions
echo "Setting permissions..."
chown -R dawg:video /opt/imx296-camera
chmod -R 755 /opt/imx296-camera

# Install diagnostic tools
echo "Installing diagnostic tools..."
cp bin/test_direct_capture.py /usr/local/bin/
chmod +x /usr/local/bin/test_direct_capture.py

# Configure logging directory
mkdir -p /var/log/imx296-camera
chown -R dawg:dawg /var/log/imx296-camera
chmod -R 777 /var/log/imx296-camera

# Test camera if available
echo "Running camera test..."
if command_exists libcamera-vid; then
  echo "Testing camera with libcamera-vid..."
  # Try to run a quick camera test
  timeout 3 libcamera-vid --list-cameras || true
  
  # Test if we can access the IMX296 camera
  if timeout 5 libcamera-vid --codec mjpeg --width 400 --height 400 --framerate 30 --output /tmp/test_capture.mkv --timeout 1000; then
    echo "Camera test succeeded!"
    ls -lh /tmp/test_capture.mkv
    file_size=$(stat -c%s "/tmp/test_capture.mkv" 2>/dev/null || stat -f%z "/tmp/test_capture.mkv")
    echo "Test file size: $file_size bytes"
    
    # Run our diagnostic script
    echo "Running diagnostic capture test..."
    /usr/local/bin/test_direct_capture.py -d 3 || true
  else
    echo "Basic camera test failed. Will try again during service startup."
  fi
else
  echo "libcamera-vid not available for testing."
fi

# Reload systemd daemon
echo "Reloading systemd daemon..."
systemctl daemon-reload

# Enable and start service
echo "Enabling and starting service..."
systemctl enable imx296-camera.service
systemctl restart imx296-camera.service

# Wait for service to start
sleep 3

# Check if service is running
if systemctl is-active --quiet imx296-camera.service; then
  echo "Service is running!"
else
  echo "Service failed to start. Check logs with: journalctl -u imx296-camera.service"
fi

# Fix common issues
echo "Fixing common issues..."

# Fix recording directory permissions
mkdir -p /home/dawg/recordings
chown -R dawg:dawg /home/dawg/recordings
chmod -R 777 /home/dawg/recordings

# Fix ffmpeg by making sure the codec matches in the config and code
config_codec=$(grep -E "^\s*codec:" /etc/imx296-camera/config.yaml | awk '{print $2}' | tr -d '"' | tr -d "'")
echo "Detected codec in config: $config_codec"

# Check LSL configuration
if python3 -c "import pylsl; print('LSL version:', pylsl.__version__)"; then
  echo "LSL installation verified"
else
  echo "WARNING: LSL not properly installed. Installing again..."
  python3 -m pip install --force-reinstall pylsl
fi

# Additional diagnostics and fixes
echo ""
echo "Running additional diagnostics..."

# Check if test_direct_capture.py works
if [ -f "/usr/local/bin/test_direct_capture.py" ]; then
  echo "Testing camera with direct capture script..."
  /usr/local/bin/test_direct_capture.py -d 3 || true
  
  # Check output file size
  TEST_FILE=$(ls -t /tmp/test_capture_*.mkv 2>/dev/null | head -n 1)
  if [ -n "$TEST_FILE" ]; then
    FILE_SIZE=$(stat -c%s "$TEST_FILE" 2>/dev/null || stat -f%z "$TEST_FILE" 2>/dev/null)
    echo "Test file: $TEST_FILE - Size: $FILE_SIZE bytes"
    
    if [ "$FILE_SIZE" -gt 5000 ]; then
      echo "✓ Direct capture works correctly!"
    else
      echo "⚠ Direct capture creates empty files. Check camera connection."
    fi
  else
    echo "⚠ No test file created. Direct capture may have failed."
  fi
fi

# Fix permissions again on service restart
systemctl restart imx296-camera.service
sleep 3

# Check service status and configuration
if systemctl is-active --quiet imx296-camera.service; then
  echo "✓ Service is running"
  
  # Check what config file the service is using
  CONFIG_PATH=$(journalctl -u imx296-camera.service -n 50 | grep -o "Trying to load config from: [^ ]*" | tail -n 1 | awk '{print $NF}')
  if [ -n "$CONFIG_PATH" ]; then
    echo "Service is using config from: $CONFIG_PATH"
  else
    echo "⚠ Could not determine which config file the service is using"
  fi
else
  echo "⚠ Service is not running. Check logs with: journalctl -u imx296-camera.service"
fi

echo ""
echo "Installation complete!"
echo "Check service status: systemctl status imx296-camera.service"
echo "View logs: journalctl -u imx296-camera.service"
echo "Manual testing: /usr/local/bin/test_direct_capture.py"
echo "Configuration: /etc/imx296-camera/config.yaml"
echo "" 