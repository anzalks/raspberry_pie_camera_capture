#!/bin/bash
# Configure IMX296 camera and integrate with recording service
# By: Anzal KS <anzal.ks@gmail.com>
set -e

echo "===== Configuring IMX296 Camera Service ====="

# Check if running as root
if [ "$EUID" -ne 0 ]; then
  echo "Please run with sudo for camera access"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CONFIG_DIR="$REPO_ROOT/config"

# Ensure config directory exists
mkdir -p "$CONFIG_DIR"

# Create camera configuration file
cat > "$CONFIG_DIR/camera_config.yaml" << EOL
# IMX296 Camera Configuration
camera:
  width: 400
  height: 400
  framerate: 30
  pixel_format: "SBGGR10_1X10"
  use_hardware_encoding: true
  codec: "h264"
  
  # Recording settings
  output_dir: "/tmp/recordings"
  create_output_dir: true
  
  # Permissions
  fix_permissions: true
  
  # Stream settings
  enable_lsl_stream: true
  lsl_stream_name: "camera"
  lsl_stream_type: "Video"
EOL

echo "Camera configuration file created at $CONFIG_DIR/camera_config.yaml"

# Create a service script to properly configure and start the camera
cat > "$SCRIPT_DIR/imx296_service_start.sh" << EOL
#!/bin/bash
# IMX296 Camera Service Starter
# By: Anzal KS <anzal.ks@gmail.com>
set -e

# Create output directory with proper permissions
OUTPUT_DIR="/tmp/recordings"
mkdir -p "\$OUTPUT_DIR"
chmod 777 "\$OUTPUT_DIR"

# Configure media pipeline
MEDIA_DEV="/dev/media0"
if [ -e "/dev/media1" ]; then
  # Use media1 for ISP if available
  media-ctl -d /dev/media1 -p
fi

# Set format on the sensor
media-ctl -d \$MEDIA_DEV --set-v4l2 '"imx296":0[fmt:SBGGR10_1X10/400x400]'

# Configure CSI-2 receiver
media-ctl -d \$MEDIA_DEV --set-v4l2 '"*rp1_csi2":0[fmt:SBGGR10_1X10/400x400]'

# Now start the camera service
cd "$REPO_ROOT"
python3 -m src.raspberry_pi_lsl_stream.camera_stream --width 400 --height 400 --framerate 30 --output-dir "\$OUTPUT_DIR" --ffmpeg-options "-vsync 0 -b:v 2M -vf format=yuv420p"
EOL

chmod +x "$SCRIPT_DIR/imx296_service_start.sh"
echo "Service start script created at $SCRIPT_DIR/imx296_service_start.sh"

# Create a simple test script
cat > "$SCRIPT_DIR/test_imx296_recording.sh" << EOL
#!/bin/bash
# Test IMX296 Camera Recording
# By: Anzal KS <anzal.ks@gmail.com>
set -e

echo "Testing IMX296 camera capture..."

# Test directory
OUTPUT_DIR="/tmp/imx296_test"
mkdir -p "\$OUTPUT_DIR"
chmod 777 "\$OUTPUT_DIR"

# Configure media pipeline
MEDIA_DEV="/dev/media0"
media-ctl -d \$MEDIA_DEV --set-v4l2 '"imx296":0[fmt:SBGGR10_1X10/400x400]'
media-ctl -d \$MEDIA_DEV --set-v4l2 '"*rp1_csi2":0[fmt:SBGGR10_1X10/400x400]'

# Test with direct capture
CAMERA_DEV=\$(v4l2-ctl --list-devices | grep -A 1 "imx296" | grep "/dev/video" | head -1 | xargs)
if [ -z "\$CAMERA_DEV" ]; then
  CAMERA_DEV="/dev/video0"
fi

echo "Testing direct h264 capture with ffmpeg..."
OUTPUT_FILE="\$OUTPUT_DIR/direct_test_\$(date +%Y%m%d_%H%M%S).h264"
# Use the configured device with its native resolution
ffmpeg -hide_banner -f v4l2 -s 400x400 -i \$CAMERA_DEV -t 5 -vsync 0 -c:v h264_omx -b:v 2M -pix_fmt yuv420p "\$OUTPUT_FILE"

echo ""
echo "Files created during testing:"
ls -lh "\$OUTPUT_DIR"
file "\$OUTPUT_DIR"/*.h264
EOL

chmod +x "$SCRIPT_DIR/test_imx296_recording.sh"
echo "Test recording script created at $SCRIPT_DIR/test_imx296_recording.sh"

# Create a systemd service file
cat > "$CONFIG_DIR/imx296_camera.service" << EOL
[Unit]
Description=IMX296 Camera Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$REPO_ROOT
ExecStart=$SCRIPT_DIR/imx296_service_start.sh
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
EOL

echo "Systemd service file created at $CONFIG_DIR/imx296_camera.service"

# Instructions
echo ""
echo "===== Installation Instructions ====="
echo "1. Copy the systemd service file to system directory:"
echo "   sudo cp $CONFIG_DIR/imx296_camera.service /etc/systemd/system/"
echo ""
echo "2. Enable and start the service:"
echo "   sudo systemctl daemon-reload"
echo "   sudo systemctl enable imx296_camera.service"
echo "   sudo systemctl start imx296_camera.service"
echo ""
echo "3. To test the camera directly, run:"
echo "   sudo $SCRIPT_DIR/test_imx296_recording.sh"
echo ""
echo "4. To check the service status:"
echo "   sudo systemctl status imx296_camera.service"
echo ""
echo "5. To view service logs:"
echo "   sudo journalctl -u imx296_camera.service -f" 