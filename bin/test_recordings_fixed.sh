#!/bin/bash
# Direct recording test for IMX296 camera with H264 codec
# By: Anzal KS <anzal.ks@gmail.com>
set -e

echo "===== IMX296 Camera Direct Recording Test (H264) ====="
echo "This will test direct recording from camera with H264 codec"

# Check if running as root (needed for camera access)
if [ "$EUID" -ne 0 ]; then
  echo "Please run with sudo for camera access"
  exit 1
fi

# Define recording directory
RECORDING_DIR="/home/dawg/recordings"
FALLBACK_DIR="/tmp"

# Ensure the recording directory exists
mkdir -p "$RECORDING_DIR"
chmod 777 "$RECORDING_DIR"
echo "✓ Recording directory ready: $RECORDING_DIR"

# Generate a test filename
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
TEST_FILE="$RECORDING_DIR/test_h264_$TIMESTAMP.mkv"
echo "Will record to: $TEST_FILE"

# Function to check if a command exists
command_exists() {
  command -v "$1" >/dev/null 2>&1
}

# Find the camera application
CAMERA_CMD=""
if command_exists libcamera-vid; then
  CAMERA_CMD="libcamera-vid"
  echo "Using libcamera-vid for capture"
elif command_exists rpicam-vid; then
  CAMERA_CMD="rpicam-vid"
  echo "Using rpicam-vid for capture"
else
  echo "Error: No camera capture command found"
  exit 1
fi

# Find ffmpeg
if ! command_exists ffmpeg; then
  echo "Error: ffmpeg not found"
  exit 1
fi

# Create an empty file with correct permissions first
touch "$TEST_FILE"
chmod 666 "$TEST_FILE"

# Method 1: Direct H264 recording with libcamera-vid
echo "Testing Method 1: Direct H264 recording with libcamera-vid..."
DIRECT_FILE="$RECORDING_DIR/direct_h264_$TIMESTAMP.h264"
$CAMERA_CMD --timeout 3000 --codec h264 --width 400 --height 400 --nopreview --output "$DIRECT_FILE"

# Check if direct file was created
if [ -f "$DIRECT_FILE" ]; then
  FILE_SIZE=$(stat -c%s "$DIRECT_FILE" 2>/dev/null || echo "0")
  if [ "$FILE_SIZE" -gt 5000 ]; then
    echo "✓ Direct H264 recording successful! File size: $FILE_SIZE bytes"
    
    # Convert H264 to MKV
    echo "Converting H264 to MKV with ffmpeg..."
    MKV_FILE="${DIRECT_FILE%.h264}.mkv"
    ffmpeg -f h264 -i "$DIRECT_FILE" -c:v copy -y "$MKV_FILE"
    
    if [ -f "$MKV_FILE" ]; then
      MKV_SIZE=$(stat -c%s "$MKV_FILE" 2>/dev/null || echo "0")
      echo "✓ Converted to MKV: $MKV_FILE ($MKV_SIZE bytes)"
    fi
  else
    echo "✗ Warning: H264 file too small: $FILE_SIZE bytes"
  fi
else
  echo "✗ Error: H264 file was not created"
fi

# Method 2: Piped H264 recording
echo "Testing Method 2: Piped H264 recording with ffmpeg..."
$CAMERA_CMD --timeout 3000 --codec h264 --width 400 --height 400 --nopreview --output - | \
  ffmpeg -f h264 -i - -c:v copy -y "$TEST_FILE"

# Check if the piped file was created
if [ -f "$TEST_FILE" ]; then
  FILE_SIZE=$(stat -c%s "$TEST_FILE" 2>/dev/null || echo "0")
  if [ "$FILE_SIZE" -gt 5000 ]; then
    echo "✓ Piped H264 recording successful! File size: $FILE_SIZE bytes"
    echo "This method works and should be used in the main service"
    
    # Create fix script to update config
    cat > "$RECORDING_DIR/update_config.py" << 'EOF'
#!/usr/bin/env python3
import yaml
import os
import sys

def update_config(config_path):
    if not os.path.exists(config_path):
        print(f"Error: Config file not found: {config_path}")
        return False
        
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
            
        # Update codec and format
        if 'recording' in config:
            config['recording']['codec'] = 'h264'
            config['recording']['format'] = 'mkv'
            print(f"Updated recording codec to h264 and format to mkv")
        else:
            print("Warning: recording section not found in config")
            
        # Write updated config
        with open(config_path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False)
            
        print(f"✓ Config updated successfully: {config_path}")
        return True
        
    except Exception as e:
        print(f"Error updating config: {e}")
        return False
        
if __name__ == "__main__":
    if len(sys.argv) > 1:
        update_config(sys.argv[1])
    else:
        for path in [
            "/etc/imx296-camera/config.yaml",
            "/opt/imx296-camera/config.yaml",
            "/home/dawg/Downloads/insha_rpie/raspberry_pie_camera_capture/config.yaml"
        ]:
            if os.path.exists(path):
                update_config(path)
EOF
    chmod +x "$RECORDING_DIR/update_config.py"
    echo "Created config update script: $RECORDING_DIR/update_config.py"
    
  else
    echo "✗ Warning: Piped file too small: $FILE_SIZE bytes"
  fi
else
  echo "✗ Error: Piped file was not created"
fi

# Print summary of recording directory
echo ""
echo "Recording directory contents:"
ls -lh "$RECORDING_DIR" | tail -5

echo ""
echo "Recording test complete!"
echo "If any test was successful, update your configuration to use H264 codec with MKV format"
echo "Run the config update script with: sudo python3 $RECORDING_DIR/update_config.py" 