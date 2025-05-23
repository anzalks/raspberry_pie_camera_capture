#!/bin/bash
# Cleanup script for IMX296 camera system
# Author: Anzal KS <anzal.ks@gmail.com>
# Date: May 23, 2025

# Define colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}==== IMX296 Camera System Cleanup Script ====${NC}"

# Validate the fix_camera_issues.sh script is properly executable
# if [ -f "fix_camera_issues.sh" ]; then
#   echo -e "${YELLOW}Making fix_camera_issues.sh executable...${NC}"
#   chmod +x fix_camera_issues.sh
#   echo -e "${GREEN}✓ fix_camera_issues.sh is now executable${NC}"
# fi

# Identify redundant scripts outside of bin directory
echo -e "${YELLOW}Identifying redundant scripts...${NC}"

redundant_scripts=(
  "fix_recording.sh"
  "fix_video_output.sh"
)

# Create fix_camera_issues.sh in bin directory
echo -e "${YELLOW}Creating fix_camera_issues.sh in bin directory...${NC}"
cat > bin/fix_camera_issues.sh << 'EOF'
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
EOF
chmod +x bin/fix_camera_issues.sh
echo -e "${GREEN}✓ Created bin/fix_camera_issues.sh${NC}"

for script in "${redundant_scripts[@]}"; do
  if [ -f "$script" ]; then
    echo -e "${YELLOW}Found redundant script: $script${NC}"
    
    # Check if the script has unique content that might need to be preserved
    echo -e "${YELLOW}Checking if $script contains unique content...${NC}"
    
    if [ -f "bin/$script" ]; then
      # If there's a copy in bin, see if they're identical
      if cmp -s "$script" "bin/$script"; then
        echo -e "${GREEN}$script is identical to bin/$script, safe to remove${NC}"
      else
        echo -e "${YELLOW}$script differs from bin/$script, backing up first${NC}"
        cp "$script" "bin/${script}.bak"
        echo -e "${GREEN}Backed up to bin/${script}.bak${NC}"
      fi
    else
      # If no copy in bin, back it up first
      echo -e "${YELLOW}No copy in bin directory, backing up first${NC}"
      cp "$script" "bin/${script}.bak"
      echo -e "${GREEN}Backed up to bin/${script}.bak${NC}"
    fi
    
    # Ask for confirmation before removing
    read -p "Remove $script? (y/n): " confirm
    if [[ "$confirm" == "y" || "$confirm" == "Y" ]]; then
      rm "$script"
      echo -e "${GREEN}✓ Removed $script${NC}"
    else
      echo -e "${YELLOW}Skipped removal of $script${NC}"
    fi
  fi
done

# Ensure proper executable permissions on scripts in bin directory
echo -e "${YELLOW}Setting proper permissions on bin scripts...${NC}"
chmod +x bin/*.sh bin/*.py
echo -e "${GREEN}✓ Set executable permissions on bin scripts${NC}"

# Create organizational README
if [ ! -f "bin/README.md" ]; then
  echo -e "${YELLOW}Creating bin/README.md for organization...${NC}"
  cat > bin/README.md << 'EOF'
# IMX296 Camera System Utility Scripts

This directory contains utility scripts for installing, running, and diagnosing the IMX296 camera system.

## Installation Scripts
- `install.sh`: Main installation script

## Diagnostic Scripts
- `diagnose_imx296.sh`: Comprehensive diagnostic for the IMX296 camera
- `diagnose_camera.sh`: General camera diagnostic
- `test_direct_capture.py`: Test direct camera capture without the service
- `check_recording.sh`: Check if recordings are working correctly

## Operational Scripts
- `view-camera-status.sh`: View camera status dashboard
- `restart_camera.sh`: Restart the camera service
- `run_imx296_capture.py`: Run the camera capture directly
- `dashboard.sh`: Launch the monitoring dashboard

## Usage
Most scripts should be run with sudo to ensure proper permissions:

```bash
sudo ./diagnose_imx296.sh
sudo ./test_direct_capture.py -d 5
./view-camera-status.sh
```
EOF
  echo -e "${GREEN}✓ Created bin/README.md${NC}"
fi

echo ""
echo -e "${GREEN}Cleanup complete!${NC}"
echo "You can now use the scripts in the bin directory for all operations."
echo "See FILE_STRUCTURE.md for the full project organization." 