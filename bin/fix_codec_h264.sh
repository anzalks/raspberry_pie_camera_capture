#!/bin/bash
# Fix codec to use H264 for IMX296 camera
# By: Anzal KS <anzal.ks@gmail.com>
set -e

echo "===== IMX296 Camera H264 Codec Fix ====="
echo "This script will update the codec configuration to use H264"

# Check if running as root (needed for file access)
if [ "$EUID" -ne 0 ]; then
  echo "Please run with sudo for proper file access"
  exit 1
fi

# Find the camera code file
CODE_PATHS=(
  "/opt/imx296-camera/src/imx296_gs_capture/imx296_capture.py"
  "/home/dawg/Downloads/insha_rpie/raspberry_pie_camera_capture/src/imx296_gs_capture/imx296_capture.py"
)

# Find which path exists
TARGET_PATH=""
for path in "${CODE_PATHS[@]}"; do
  if [ -f "$path" ]; then
    TARGET_PATH="$path"
    echo "Found camera code at: $TARGET_PATH"
    break
  fi
done

if [ -z "$TARGET_PATH" ]; then
  echo "Error: Cannot find camera code. Please specify the correct path."
  exit 1
fi

# Check for config files
CONFIG_PATHS=(
  "/etc/imx296-camera/config.yaml"
  "/opt/imx296-camera/config.yaml"
  "/home/dawg/Downloads/insha_rpie/raspberry_pie_camera_capture/config.yaml"
)

# Create Python script to update the code and config
cat > /tmp/fix_codec_h264.py << 'EOF'
#!/usr/bin/env python3
import sys
import os
import re
import yaml

def fix_codec_in_code(filepath):
    """Update the codec in the camera code to use H264."""
    if not os.path.exists(filepath):
        print(f"Error: File not found: {filepath}")
        return False
    
    with open(filepath, 'r') as f:
        content = f.read()
    
    changes_made = []
    
    # Create backup
    backup_path = f"{filepath}.bak.codec"
    with open(backup_path, 'w') as f:
        f.write(content)
    print(f"Created backup at: {backup_path}")
    
    # 1. Find and replace mjpeg codec with h264
    if 'codec = "mjpeg"' in content or "codec = 'mjpeg'" in content:
        content = re.sub(r'codec\s*=\s*[\'"]mjpeg[\'"]', 'codec = "h264"', content)
        changes_made.append("- Changed codec from mjpeg to h264")
    
    # 2. Update ffmpeg command if using mjpeg format
    if '-f mjpeg' in content:
        content = re.sub(r'-f\s+mjpeg', '-f h264', content)
        changes_made.append("- Changed ffmpeg input format from mjpeg to h264")
    
    # 3. Update libcamera command if using mjpeg codec
    if '--codec mjpeg' in content:
        content = re.sub(r'--codec\s+mjpeg', '--codec h264', content)
        changes_made.append("- Changed libcamera codec parameter from mjpeg to h264")
    
    # 4. Force MKV format output
    if 'format_ext = ' in content and 'format_ext = "mkv"' not in content:
        content = re.sub(r'format_ext\s*=\s*[^"]*', 'format_ext = "mkv"', content)
        changes_made.append("- Forced output format to mkv")
    
    # Write the updated content
    if changes_made:
        with open(filepath, 'w') as f:
            f.write(content)
        print("Applied the following changes to code:")
        for change in changes_made:
            print(f"  {change}")
        return True
    else:
        print("No codec changes needed in code")
        return False

def update_config(config_path):
    """Update the codec in the config file to use H264."""
    if not os.path.exists(config_path):
        print(f"Config file not found: {config_path}")
        return False
    
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        # Create backup
        backup_path = f"{config_path}.bak.codec"
        with open(backup_path, 'w') as f:
            yaml.dump(config, f)
        print(f"Created config backup at: {backup_path}")
        
        # Update recording section
        if 'recording' in config:
            changed = False
            
            if 'codec' in config['recording'] and config['recording']['codec'] != 'h264':
                config['recording']['codec'] = 'h264'
                changed = True
                print("  - Changed config codec to h264")
            
            if 'format' in config['recording'] and config['recording']['format'] != 'mkv':
                config['recording']['format'] = 'mkv'
                changed = True
                print("  - Changed config format to mkv")
            
            if changed:
                with open(config_path, 'w') as f:
                    yaml.dump(config, f, default_flow_style=False)
                print(f"✓ Updated config: {config_path}")
                return True
            else:
                print(f"No changes needed in config: {config_path}")
                return False
        else:
            print(f"Warning: 'recording' section not found in {config_path}")
            return False
            
    except Exception as e:
        print(f"Error updating config {config_path}: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: fix_codec_h264.py <code_path> [config_path1] [config_path2] ...")
        sys.exit(1)
    
    code_path = sys.argv[1]
    fix_codec_in_code(code_path)
    
    # Update any config files provided
    if len(sys.argv) > 2:
        for config_path in sys.argv[2:]:
            update_config(config_path)
EOF

# Make it executable
chmod +x /tmp/fix_codec_h264.py

# Run the fix script on the target file and configs
echo "Updating camera code and configs to use H264..."
CONFIG_ARGS=""
for config_path in "${CONFIG_PATHS[@]}"; do
  if [ -f "$config_path" ]; then
    CONFIG_ARGS="$CONFIG_ARGS $config_path"
  fi
done

python3 /tmp/fix_codec_h264.py "$TARGET_PATH" $CONFIG_ARGS

# Ensure recording directory exists
mkdir -p /home/dawg/recordings
chmod 777 /home/dawg/recordings
echo "✓ Recording directory ready: /home/dawg/recordings"

# Restart the service
if systemctl is-active --quiet imx296-camera.service; then
  echo "Restarting camera service..."
  systemctl restart imx296-camera.service
  sleep 2
  
  if systemctl is-active --quiet imx296-camera.service; then
    echo "✓ Camera service restarted successfully"
  else
    echo "⚠ Camera service failed to restart, check logs"
  fi
else
  echo "Camera service is not active. Starting it..."
  systemctl start imx296-camera.service
  sleep 2
  
  if systemctl is-active --quiet imx296-camera.service; then
    echo "✓ Camera service started successfully"
  else
    echo "⚠ Camera service failed to start, check logs"
  fi
fi

echo ""
echo "===== H264 CODEC FIX COMPLETE ====="
echo ""
echo "The camera is now configured to use H264 codec with MKV container."
echo "To verify the change worked, run the following commands:"
echo ""
echo "1. Check the service status: sudo systemctl status imx296-camera"
echo "2. Check recordings in: /home/dawg/recordings"
echo "3. Try test recording: sudo bin/test_recordings_fixed.sh"
echo ""
echo "If you still have issues, check the logs with:"
echo "sudo journalctl -u imx296-camera -f" 