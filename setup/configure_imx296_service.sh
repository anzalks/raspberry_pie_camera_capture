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

# Auto-detect media device with IMX296 camera
auto_detect_media_device() {
    local detected_device=""
    local available_devices=($(ls /dev/media* 2>/dev/null | sort -V))
    
    if [ ${#available_devices[@]} -eq 0 ]; then
        echo "WARNING: No media devices found" >&2
        return 1
    fi
    
    echo "Scanning ${#available_devices[@]} media devices for IMX296 camera..." >&2
    
    for device in "${available_devices[@]}"; do
        if [ -e "$device" ]; then
            if media-ctl -d "$device" -p 2>/dev/null | grep -qi "imx296"; then
                detected_device="$device"
                echo "Found IMX296 camera on: $detected_device" >&2
                break
            fi
        fi
    done
    
    if [ -n "$detected_device" ]; then
        echo "$detected_device"
        return 0
    else
        echo "ERROR: No IMX296 camera found on any media device" >&2
        echo "Available devices were: ${available_devices[*]}" >&2
        return 1
    fi
}

# Try to auto-detect media device, fallback to default
MEDIA_DEV=$(auto_detect_media_device)
if [ $? -ne 0 ]; then
    echo "Falling back to default media device..." >&2
    MEDIA_DEV="/dev/media0"
fi

# Check if media1 exists for additional ISP configuration
if [ -e "/dev/media1" ]; then
    echo "Additional media device found: /dev/media1 (for ISP)" >&2
    # Use media1 for ISP if available
    media-ctl -d /dev/media1 -p 2>/dev/null || echo "media1 not accessible"
fi

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

# Auto-detect media device
auto_detect_media_device() {
    local detected_device=""
    local available_devices=(\$(ls /dev/media* 2>/dev/null | sort -V))
    
    if [ \${#available_devices[@]} -eq 0 ]; then
        echo "WARNING: No media devices found" >&2
        return 1
    fi
    
    for device in "\${available_devices[@]}"; do
        if [ -e "\$device" ]; then
            if media-ctl -d "\$device" -p 2>/dev/null | grep -qi "imx296"; then
                detected_device="\$device"
                echo "Found IMX296 camera on: \$detected_device" >&2
                break
            fi
        fi
    done
    
    if [ -n "\$detected_device" ]; then
        echo "\$detected_device"
        return 0
    else
        echo "ERROR: No IMX296 camera found" >&2
        return 1
    fi
}

# Configure media pipeline with detected device
MEDIA_DEV=\$(auto_detect_media_device)
if [ \$? -ne 0 ]; then
    echo "Falling back to default media device..." >&2
    MEDIA_DEV="/dev/media0"
fi

echo "Using media device: \$MEDIA_DEV"

# Check for additional ISP device
if [ -e "/dev/media1" ] && [ "\$MEDIA_DEV" != "/dev/media1" ]; then
  echo "Using additional ISP device: /dev/media1"
  media-ctl -d /dev/media1 -p 2>/dev/null || true
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

# Auto-detect media device with IMX296
auto_detect_media_device() {
    local detected_device=""
    local available_devices=(\$(ls /dev/media* 2>/dev/null | sort -V))
    
    if [ \${#available_devices[@]} -eq 0 ]; then
        echo "WARNING: No media devices found" >&2
        return 1
    fi
    
    echo "Scanning \${#available_devices[@]} media devices for IMX296..."
    
    for device in "\${available_devices[@]}"; do
        if [ -e "\$device" ]; then
            if media-ctl -d "\$device" -p 2>/dev/null | grep -qi "imx296"; then
                detected_device="\$device"
                echo "Found IMX296 camera on: \$detected_device"
                break
            fi
        fi
    done
    
    if [ -n "\$detected_device" ]; then
        echo "\$detected_device"
        return 0
    else
        echo "ERROR: No IMX296 camera found on any media device" >&2
        return 1
    fi
}

# Configure media pipeline with dynamic detection
MEDIA_DEV=\$(auto_detect_media_device)
if [ \$? -ne 0 ]; then
    echo "Falling back to default media device..." >&2
    MEDIA_DEV="/dev/media0"
fi

echo "Using media device: \$MEDIA_DEV"

# Configure the camera
media-ctl -d \$MEDIA_DEV --set-v4l2 '"imx296":0[fmt:SBGGR10_1X10/400x400]'
media-ctl -d \$MEDIA_DEV --set-v4l2 '"*rp1_csi2":0[fmt:SBGGR10_1X10/400x400]'

# Test with direct capture
CAMERA_DEV=\$(v4l2-ctl --list-devices | grep -A 1 "imx296" | grep "/dev/video" | head -1 | xargs)
if [ -z "\$CAMERA_DEV" ]; then
  echo "No specific IMX296 video device found, using /dev/video0"
  CAMERA_DEV="/dev/video0"
else
  echo "Found IMX296 video device: \$CAMERA_DEV"
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