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

# After the LSL package installation, add a more specific fix for LSL stream numeric values
echo "Fixing LSL stream numeric values issue..."
# Create a Python script to test and fix the LSL issue
cat > /tmp/fix_lsl_numeric.py << 'EOF'
#!/usr/bin/env python3
import sys
import os
import re

def fix_lsl_in_file(filepath):
    """Fix LSL string values in the IMX296 capture code."""
    print(f"Examining file: {filepath}")
    
    if not os.path.exists(filepath):
        print(f"Error: File not found: {filepath}")
        return False
    
    with open(filepath, 'r') as f:
        content = f.read()
    
    # Check if lsl_has_string_support is True anywhere
    if re.search(r'lsl_has_string_support\s*=\s*True', content):
        print("Found lsl_has_string_support = True, fixing to False")
        content = re.sub(r'lsl_has_string_support\s*=\s*True', 'lsl_has_string_support = False', content)
        modified = True
    else:
        modified = False
    
    # Find instances of string values in LSL samples
    if "get_trigger_source_string" in content and "if lsl_has_string_support:" in content:
        print("Found string values in LSL sample pushing, fixing...")
        
        # Fix the problematic section where trigger_source might be a string
        string_pattern = re.compile(r'if lsl_has_string_support:.*?else:.*?sample = \[(.*?)\]', re.DOTALL)
        match = string_pattern.search(content)
        
        if match:
            # Replace the entire conditional block with just the numeric version
            fixed_block = (
                "# Always use numeric values for LSL\n"
                "                    sample = [float(current_time), float(recording_event.is_set()), -1.0, float(last_trigger_source)]"
            )
            content = re.sub(r'if lsl_has_string_support:.*?else:.*?# All numeric version', fixed_block, content, flags=re.DOTALL)
            modified = True
    
    # Look for any place where string values might be used
    if "trigger_str" in content and "lsl_outlet.push_sample" in content:
        # Find and fix any places where trigger_str might be used in sample data
        triggers_pattern = re.compile(r'sample = \[(.*?)trigger_str(.*?)\]')
        if triggers_pattern.search(content):
            print("Found potential string in LSL sample, fixing...")
            # Replace with numeric version
            content = re.sub(r'sample = \[(.*?)trigger_str(.*?)\]', 
                            r'sample = [\1float(last_trigger_source)\2]', 
                            content)
            modified = True
    
    if modified:
        # Backup the original file
        backup_path = filepath + ".bak"
        with open(backup_path, 'w') as f:
            f.write(content)
        print(f"Created backup at {backup_path}")
        
        # Write the fixed content
        with open(filepath, 'w') as f:
            f.write(content)
        print("✓ LSL numeric values fixed in file")
        return True
    else:
        print("No LSL string issues found in the file")
        return False

# Find all possible imx296_capture.py files
for path in [
    "/home/dawg/Downloads/insha_rpie/raspberry_pie_camera_capture/src/imx296_gs_capture/imx296_capture.py",
    "/opt/imx296-camera/src/imx296_gs_capture/imx296_capture.py",
    "./src/imx296_gs_capture/imx296_capture.py"
]:
    if os.path.exists(path):
        fix_lsl_in_file(path)

print("LSL numeric value check complete!")
EOF

# Make it executable
chmod +x /tmp/fix_lsl_numeric.py

# Run the fix script
echo "Running LSL numeric values fix..."
python3 /tmp/fix_lsl_numeric.py

# Additionally create a test LSL stream to verify numeric values work
echo "Creating test LSL stream to verify functionality..."
cat > /tmp/test_lsl_numeric.py << 'EOF'
#!/usr/bin/env python3
import time
import sys

try:
    import pylsl
    
    # Create a test stream with numeric values only
    info = pylsl.StreamInfo(
        name="IMX296Camera",
        type="VideoEvents",
        channel_count=4,
        nominal_srate=100.0,
        channel_format=pylsl.cf_double,
        source_id="cam1"
    )
    
    # Add metadata
    channels = info.desc().append_child("channels")
    channels.append_child("channel").append_child_value("label", "timestamp").append_child_value("type", "time").append_child_value("unit", "s")
    channels.append_child("channel").append_child_value("label", "recording").append_child_value("type", "status").append_child_value("unit", "bool")
    channels.append_child("channel").append_child_value("label", "frame").append_child_value("type", "index").append_child_value("unit", "count")
    channels.append_child("channel").append_child_value("label", "trigger").append_child_value("type", "code").append_child_value("unit", "id")
    
    # Create outlet
    outlet = pylsl.StreamOutlet(info)
    
    print("Created LSL stream 'IMX296Camera'")
    
    # Send a test sample with only numeric values
    sample = [time.time(), 1.0, 0.0, 1.0]  # timestamp, recording, frame, trigger
    outlet.push_sample(sample)
    print(f"Sent test sample: {sample}")
    
    # Check resolver
    streams = pylsl.resolve_streams(1.0)
    found = False
    for stream in streams:
        if stream.name() == "IMX296Camera":
            found = True
            print(f"Found stream in resolver: {stream.name()}, type: {stream.type()}, channels: {stream.channel_count()}")
    
    if found:
        print("✓ LSL numeric stream test PASSED")
        sys.exit(0)
    else:
        print("✗ LSL stream not found in resolver")
        sys.exit(1)
except Exception as e:
    print(f"Error in LSL test: {e}")
    sys.exit(1)
EOF

# Make it executable
chmod +x /tmp/test_lsl_numeric.py

# Run the LSL test
echo "Testing LSL stream with numeric values..."
python3 /tmp/test_lsl_numeric.py

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

# Add a fix for empty recording files (4KB only)
echo "Fixing empty recording files issue..."
cat > /tmp/fix_empty_recordings.py << 'EOF'
#!/usr/bin/env python3
import sys
import os
import re
import subprocess

def fix_recording_in_file(filepath):
    """Fix empty recording files issue in the IMX296 capture code."""
    print(f"Examining file for recording issues: {filepath}")
    
    if not os.path.exists(filepath):
        print(f"Error: File not found: {filepath}")
        return False
    
    with open(filepath, 'r') as f:
        content = f.read()
    
    modified = False
    
    # Check for ffmpeg command construction
    ffmpeg_section = re.search(r'cmd = \[(.*?)ffmpeg_path(.*?)]', content, re.DOTALL)
    if ffmpeg_section:
        # Ensure the ffmpeg command is correctly formed
        if "-c:v copy" in content and not "-vsync 0" in content:
            print("Found ffmpeg command without -vsync 0, adding it...")
            # Add -vsync 0 after the copy command
            content = re.sub(
                r'("-c:v", "copy",)',
                r'\1\n        "-vsync", "0",  # Add frame sync option to prevent empty files',
                content
            )
            modified = True
    
    # Ensure output directory exists and has correct permissions
    if 'output_dir = config' in content:
        # Add code to ensure output directory exists
        dir_check_code = """
        # Ensure output directory exists with proper permissions
        try:
            output_dir = os.path.abspath(os.path.expanduser(output_dir))
            os.makedirs(output_dir, exist_ok=True)
            os.chmod(output_dir, 0o777)  # Full permissions
            logger.info(f"Ensured output directory exists with permissions: {output_dir}")
        except Exception as e:
            logger.error(f"Error ensuring output directory: {e}")
            # Try using /tmp as fallback
            output_dir = "/tmp"
            logger.warning(f"Using fallback directory: {output_dir}")
        """
        
        # Find where to insert the code
        dir_setup_match = re.search(r'output_dir = .*?\n', content)
        if dir_setup_match and dir_check_code not in content:
            print("Adding directory permission check code...")
            insert_pos = dir_setup_match.end()
            content = content[:insert_pos] + dir_check_code + content[insert_pos:]
            modified = True
    
    # Fix the output file creation to ensure it can be written by ffmpeg
    if 'output_file = ' in content and "os.open" not in content:
        # Add file creation code with proper permissions
        file_create_code = """
        # Create empty file with proper permissions first
        try:
            # Use low-level os.open to ensure file exists with correct permissions
            fd = os.open(output_file, os.O_CREAT | os.O_WRONLY, 0o666)
            os.close(fd)
            logger.info(f"Created empty file with permissions: {output_file}")
        except Exception as e:
            logger.error(f"Error creating output file: {e}")
            # Try alternative location
            output_file = f"/tmp/recording_{timestamp}.{format_ext}"
            logger.warning(f"Using alternative path: {output_file}")
            try:
                fd = os.open(output_file, os.O_CREAT | os.O_WRONLY, 0o666)
                os.close(fd)
            except Exception as e2:
                logger.error(f"Error creating alternative file: {e2}")
        """
        
        output_file_match = re.search(r'output_file = .*?\n', content)
        if output_file_match and file_create_code not in content:
            print("Adding file creation with proper permissions...")
            insert_pos = output_file_match.end()
            content = content[:insert_pos] + file_create_code + content[insert_pos:]
            modified = True
    
    if modified:
        # Backup the original file
        backup_path = filepath + ".rec_fix.bak"
        with open(backup_path, 'w') as f:
            f.write(content)
        print(f"Created backup at {backup_path}")
        
        # Write the fixed content
        with open(filepath, 'w') as f:
            f.write(content)
        print("✓ Empty recording files issue fixed")
        return True
    else:
        print("No recording issues found that need fixing")
        return False

# Test ffmpeg command directly to verify it can create non-empty files
def test_ffmpeg_recording():
    """Test ffmpeg with a simple command to verify it creates non-empty files."""
    print("Testing ffmpeg recording directly...")
    
    test_file = "/tmp/ffmpeg_test.mkv"
    if os.path.exists(test_file):
        os.remove(test_file)
    
    # Generate a simple test video (color bars) for 1 second
    cmd = [
        "/usr/bin/ffmpeg",
        "-f", "lavfi",
        "-i", "testsrc=duration=1:size=400x400:rate=30", 
        "-c:v", "mjpeg",
        "-y",
        test_file
    ]
    
    try:
        print(f"Running command: {' '.join(cmd)}")
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        if os.path.exists(test_file):
            size = os.path.getsize(test_file)
            print(f"Created test file with size: {size} bytes")
            
            if size > 5000:
                print("✓ FFmpeg can create valid video files")
                return True
            else:
                print("✗ FFmpeg created an empty file, something is wrong with ffmpeg")
                return False
        else:
            print("✗ FFmpeg failed to create a test file")
            return False
    except Exception as e:
        print(f"Error testing ffmpeg: {e}")
        return False

# Find all possible imx296_capture.py files
for path in [
    "/home/dawg/Downloads/insha_rpie/raspberry_pie_camera_capture/src/imx296_gs_capture/imx296_capture.py",
    "/opt/imx296-camera/src/imx296_gs_capture/imx296_capture.py",
    "./src/imx296_gs_capture/imx296_capture.py"
]:
    if os.path.exists(path):
        fix_recording_in_file(path)

# Test ffmpeg directly
test_ffmpeg_recording()

print("Empty recording files fix complete!")
EOF

# Make it executable
chmod +x /tmp/fix_empty_recordings.py

# Run the fix script
echo "Running empty recording files fix..."
python3 /tmp/fix_empty_recordings.py

# Now test direct camera capture to verify all fixes
echo "Testing full camera pipeline with all fixes applied..."
# Create a test recording directly
/usr/bin/libcamera-vid --timeout 3000 --codec mjpeg --inline --width 400 --height 400 --nopreview --output - | \
  /usr/bin/ffmpeg -f mjpeg -i - -c:v copy -vsync 0 -an -y /tmp/test_after_fixes.mkv

# Check if the test file exists and has content
if [ -f "/tmp/test_after_fixes.mkv" ]; then
  FILE_SIZE=$(stat -c%s "/tmp/test_after_fixes.mkv" 2>/dev/null || echo "0")
  if [ "$FILE_SIZE" -gt 5000 ]; then
    echo "✓ Test recording successful! File size: $FILE_SIZE bytes"
  else
    echo "⚠ Test recording created small file: $FILE_SIZE bytes"
  fi
else
  echo "⚠ Test recording failed to create file"
fi
