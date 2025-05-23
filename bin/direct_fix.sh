#!/bin/bash
# Direct fix for persistent IMX296 camera issues
# By: Anzal KS <anzal.ks@gmail.com>
set -e

echo "=== DIRECT FIX FOR IMX296 CAMERA ISSUES ==="
echo "This script addresses empty recordings and missing LSL stream issues"

# Stop the service first
echo "Stopping camera service..."
sudo systemctl stop imx296-camera.service
sleep 2

# Find the actual running code
INSTALL_PATHS=(
  "/opt/imx296-camera/src/imx296_gs_capture/imx296_capture.py"
  "/home/dawg/Downloads/insha_rpie/raspberry_pie_camera_capture/src/imx296_gs_capture/imx296_capture.py"
)

# Find which path exists
TARGET_PATH=""
for path in "${INSTALL_PATHS[@]}"; do
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

# Make a backup of the file
BACKUP_PATH="${TARGET_PATH}.bak.$(date +%Y%m%d%H%M%S)"
sudo cp "$TARGET_PATH" "$BACKUP_PATH"
echo "Created backup at: $BACKUP_PATH"

# Create a Python script to directly fix the issues
echo "Applying fixes..."

cat > /tmp/direct_fix.py << 'EOF'
#!/usr/bin/env python3
import sys
import os
import re

def fix_camera_code(filepath):
    """Direct fix for both empty recordings and LSL stream issues."""
    if not os.path.exists(filepath):
        print(f"Error: File not found: {filepath}")
        return False
    
    with open(filepath, 'r') as f:
        content = f.read()
    
    changes_made = []
    
    # 1. Fix LSL string support setting
    if re.search(r'lsl_has_string_support\s*=\s*True', content):
        content = re.sub(r'lsl_has_string_support\s*=\s*True', 'lsl_has_string_support = False', content)
        changes_made.append("- Set lsl_has_string_support = False")
    
    # 2. Fix LSL stream creation
    lsl_info_pattern = re.compile(r'(info\s*=\s*pylsl\.StreamInfo\s*\()([^)]*)\)', re.DOTALL)
    if lsl_info_pattern.search(content):
        # Update to use a supported format for all pylsl versions
        content = re.sub(
            r'(info\s*=\s*pylsl\.StreamInfo\s*\()([^)]*)(channel_format\s*=\s*)(pylsl\.cf_double|pylsl\.cf_double64)',
            r'\1\2\3pylsl.cf_float32',
            content
        )
        changes_made.append("- Changed LSL stream format to cf_float32 for compatibility")

    # 3. Fix LSL sample conversion to ensure all values are numeric
    if "get_trigger_source_string" in content:
        # Find all places where samples are pushed to LSL
        sample_push_pattern = re.compile(r'(sample\s*=\s*\[)(.*?)(\])', re.DOTALL)
        for match in sample_push_pattern.finditer(content):
            sample_content = match.group(2)
            if not all(('float(' in item) for item in sample_content.split(',') if 'time' not in item and len(item.strip()) > 0):
                # Add float() conversion to all items in the sample
                new_sample = []
                for item in sample_content.split(','):
                    item = item.strip()
                    if 'float(' not in item and len(item) > 0:
                        if 'time' in item:  # already a float usually
                            new_sample.append(item)
                        else:
                            new_sample.append(f"float({item})")
                    else:
                        new_sample.append(item)
                new_sample_text = ', '.join(new_sample)
                content = content.replace(match.group(0), f"sample = [{new_sample_text}]")
                changes_made.append("- Added float() conversion to all LSL sample values")
    
    # 4. Fix ffmpeg command for empty recordings
    if "-c:v copy" in content and not "-vsync 0" in content:
        content = re.sub(
            r'("-c:v",\s*"copy",)',
            r'\1\n            "-vsync", "0",  # Fix for empty recordings',
            content
        )
        changes_made.append("- Added -vsync 0 to ffmpeg command")
    
    # 5. Fix output file path issues that might cause empty files
    dir_check_code = """
        # Ensure output directory exists with proper permissions
        try:
            os.makedirs(output_dir, exist_ok=True)
            os.chmod(output_dir, 0o777)  # Full permissions
            logger.info(f"Ensured output directory exists: {output_dir}")
        except Exception as e:
            logger.error(f"Error creating output directory: {e}")
            # Fall back to /tmp
            output_dir = "/tmp"
            logger.warning(f"Using fallback directory: {output_dir}")
    """
    
    if "output_dir = " in content and dir_check_code not in content:
        # Find where to add the directory creation code
        output_dir_match = re.search(r'output_dir\s*=\s*.*?\n', content)
        if output_dir_match:
            insert_pos = output_dir_match.end()
            content = content[:insert_pos] + dir_check_code + content[insert_pos:]
            changes_made.append("- Added directory creation with proper permissions")
    
    # 6. Add file creation with proper permissions
    file_creation_code = """
        # Create empty file with proper permissions
        try:
            # Touch the file and ensure it has proper permissions
            with open(output_file, 'w') as f:
                pass
            os.chmod(output_file, 0o666)
            logger.info(f"Created output file with permissions: {output_file}")
        except Exception as e:
            logger.error(f"Error creating output file: {e}")
            # Try alternative location
            output_file = f"/tmp/recording_{int(time.time())}.{format_ext}"
            logger.warning(f"Using alternative output file: {output_file}")
            try:
                with open(output_file, 'w') as f:
                    pass
                os.chmod(output_file, 0o666)
            except Exception as e2:
                logger.error(f"Error creating alternative file: {e2}")
    """
    
    if "output_file = " in content and file_creation_code not in content:
        # Find where to add the file creation code
        output_file_match = re.search(r'output_file\s*=\s*.*?\n', content)
        if output_file_match:
            insert_pos = output_file_match.end()
            content = content[:insert_pos] + file_creation_code + content[insert_pos:]
            changes_made.append("- Added file creation with proper permissions")
    
    # 7. Add fix to use MJPEG codec and MKV format
    if "video_format = config" in content:
        content = re.sub(
            r'(format_ext\s*=\s*)video_format',
            r'\1"mkv"  # Force MKV format',
            content
        )
        changes_made.append("- Forced MKV format")
    
    if "codec = config" in content:
        content = re.sub(
            r'(codec\s*=\s*)([^"]*?)(["]*)',
            r'\1"mjpeg"  # Force MJPEG codec\3',
            content
        )
        changes_made.append("- Forced MJPEG codec")
    
    # 8. Fix popen arguments
    if "pipe = subprocess.Popen(" in content:
        if "shell=True" in content:
            content = re.sub(
                r'(pipe\s*=\s*subprocess\.Popen\([^,]*?,\s*)(shell=True)',
                r'\1shell=False',
                content
            )
            changes_made.append("- Changed shell=True to shell=False in Popen call")
    
    if len(changes_made) > 0:
        # Write the updated content
        with open(filepath, 'w') as f:
            f.write(content)
        print("Applied the following fixes:")
        for change in changes_made:
            print(f"  {change}")
        return True
    else:
        print("No issues found that need fixing.")
        return False

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: fix_camera_code.py <path_to_camera_py>")
        sys.exit(1)
    
    filepath = sys.argv[1]
    if fix_camera_code(filepath):
        print(f"Successfully fixed the camera code at {filepath}")
    else:
        print(f"No changes were needed for {filepath}")
EOF

# Make the fix script executable
chmod +x /tmp/direct_fix.py

# Run the fix script on the target file
sudo python3 /tmp/direct_fix.py "$TARGET_PATH"

# Update config file
CONFIG_PATHS=(
  "/etc/imx296-camera/config.yaml"
  "/opt/imx296-camera/config.yaml"
  "/home/dawg/Downloads/insha_rpie/raspberry_pie_camera_capture/config.yaml"
)

for config_path in "${CONFIG_PATHS[@]}"; do
  if [ -f "$config_path" ]; then
    echo "Updating config file: $config_path"
    sudo cp "$config_path" "${config_path}.bak.$(date +%Y%m%d%H%M%S)"
    
    # Create updated config
    cat > /tmp/fixed_config.yaml << 'EOF'
# IMX296 Camera Configuration (Fixed)
# By: Anzal KS <anzal.ks@gmail.com>

camera:
  width: 400
  height: 400
  fps: 100
  format: "SBGGR10_1X10"  # Native format for IMX296
  libcamera_path: "/usr/bin/libcamera-vid"
  ffmpeg_path: "/usr/bin/ffmpeg"

recording:
  enabled: true
  output_dir: "/home/dawg/recordings"  # Will be created if it doesn't exist
  codec: "mjpeg"  # Use MJPEG for better compatibility
  format: "mkv"   # Use MKV for better recovery from crashes
  compression_level: 5
  
lsl:
  enabled: true
  stream_name: "IMX296Camera"
  stream_type: "VideoEvents"
  stream_id: "imx296_01"
  
web:
  enabled: true
  host: "0.0.0.0"
  port: 8080
  update_interval_ms: 500
EOF
    
    # Copy updated config
    sudo cp /tmp/fixed_config.yaml "$config_path"
  fi
done

# Ensure recording directory exists and has proper permissions
echo "Ensuring recording directory exists with proper permissions..."
sudo mkdir -p /home/dawg/recordings
sudo chmod 777 /home/dawg/recordings

# Test LSL directly to ensure it works
echo "Testing LSL directly..."
cat > /tmp/test_lsl.py << 'EOF'
#!/usr/bin/env python3
import time
import sys

try:
    import pylsl
    print(f"Using pylsl version: {pylsl.__version__}")
    
    # Figure out the right channel format for this pylsl version
    channel_format = None
    for cf_name in ['cf_float32', 'cf_float', 'cf_double']:
        if hasattr(pylsl, cf_name):
            channel_format = getattr(pylsl, cf_name)
            print(f"Using channel format: {cf_name}")
            break
    
    if channel_format is None:
        print("Error: Could not find a supported pylsl channel format")
        sys.exit(1)
    
    # Create a test stream
    info = pylsl.StreamInfo(
        name="IMX296Camera", 
        type="VideoEvents",
        channel_count=4,
        nominal_srate=100.0,
        channel_format=channel_format,
        source_id="imx296_01"
    )
    
    # Add metadata
    channels = info.desc().append_child("channels")
    channels.append_child("channel").append_child_value("label", "timestamp")
    channels.append_child("channel").append_child_value("label", "recording")
    channels.append_child("channel").append_child_value("label", "frame")
    channels.append_child("channel").append_child_value("label", "trigger")
    
    # Create an outlet
    outlet = pylsl.StreamOutlet(info)
    print("Created LSL outlet")
    
    # Send a test sample
    sample = [float(time.time()), 1.0, 0.0, 1.0]
    outlet.push_sample(sample)
    print(f"Pushed test sample: {sample}")
    
    # Wait briefly and check for the stream
    time.sleep(0.5)
    streams = pylsl.resolve_streams(1.0)
    found = False
    for stream in streams:
        if stream.name() == "IMX296Camera":
            print(f"Found stream: {stream.name()}, type: {stream.type()}")
            found = True
    
    if found:
        print("✓ LSL stream test passed")
        sys.exit(0)
    else:
        print("✗ LSL stream not found")
        sys.exit(1)
except Exception as e:
    print(f"Error testing LSL: {e}")
    sys.exit(1)
EOF

# Make test script executable
chmod +x /tmp/test_lsl.py

# Run the LSL test
sudo python3 /tmp/test_lsl.py

# Test direct camera capture
echo "Testing direct camera capture..."
TEST_FILE="/tmp/direct_test.mkv"
sudo /usr/bin/libcamera-vid --timeout 2000 --codec mjpeg --inline --width 400 --height 400 --nopreview --output - | \
  sudo /usr/bin/ffmpeg -f mjpeg -i - -c:v copy -vsync 0 -an -y "$TEST_FILE"

# Check the test file
if [ -f "$TEST_FILE" ]; then
  FILE_SIZE=$(stat -c%s "$TEST_FILE" 2>/dev/null || echo "0")
  if [ "$FILE_SIZE" -gt 5000 ]; then
    echo "✓ Direct test recording successful ($FILE_SIZE bytes)"
  else
    echo "✗ Direct test recording failed (file too small: $FILE_SIZE bytes)"
  fi
else
  echo "✗ Direct test recording failed (file not created)"
fi

# Restart the service
echo "Restarting camera service..."
sudo systemctl start imx296-camera.service
sleep 3

# Check if the service started
if sudo systemctl is-active --quiet imx296-camera.service; then
  echo "✓ Camera service is running"
else
  echo "✗ Camera service failed to start"
  echo "Checking logs:"
  sudo journalctl -u imx296-camera.service -n 20
fi

echo ""
echo "==== DIRECT FIX COMPLETE ===="
echo "The camera service has been restarted with fixes applied."
echo "To check the status, run: sudo systemctl status imx296-camera.service"
echo "To view logs, run: sudo journalctl -u imx296-camera.service -f"
echo "To test if the fixes worked, open the dashboard or check new recordings" 