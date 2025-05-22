#!/bin/bash
# Fix recording issues on Raspberry Pi
# Run this script on the Raspberry Pi to fix recording and LSL issues
# Author: Anzal KS <anzal.ks@gmail.com>

echo "===== IMX296 Camera Recording Fix Script ====="

# 1. Create recording directory with proper permissions
echo "Creating recording directory with proper permissions..."
mkdir -p ~/recordings
chmod 777 ~/recordings

# 2. Test direct recording to confirm camera works
echo "Testing direct camera recording (5 seconds)..."
rpicam-vid --no-raw --width 400 --height 400 --timeout 5000 --output ~/recordings/test_direct.mp4 || {
  echo "Error: Direct camera recording failed"
  # Try alternative method
  echo "Trying alternative recording method..."
  rpicam-vid --no-raw --width 400 --height 400 --codec mjpeg --timeout 5000 --output ~/recordings/test_direct.mkv
}

# Check test recording file size
echo "Checking test recording file..."
ls -lh ~/recordings/test_direct.*

# 3. Fix LSL configuration
echo "Creating LSL test file to verify implementation..."
cat > ~/lsl_test.py << 'EOF'
#!/usr/bin/env python3
import sys
import pylsl
import time

def create_test_stream():
    try:
        # Create LSL stream with 4 channels
        info = pylsl.StreamInfo(
            name="IMX296Camera",
            type="VideoEvents",
            channel_count=4,
            nominal_srate=30,
            channel_format=pylsl.cf_double,
            source_id="cam1"
        )
        
        # Add metadata
        channels = info.desc().append_child("channels")
        channels.append_child("channel").append_child_value("label", "timestamp")
        channels.append_child("channel").append_child_value("label", "recording")
        channels.append_child("channel").append_child_value("label", "frame")
        channels.append_child("channel").append_child_value("label", "trigger")
        
        # Create outlet
        outlet = pylsl.StreamOutlet(info)
        
        # Send test data
        sample = [time.time(), 0.0, 0.0, 0.0]
        outlet.push_sample(sample)
        print("LSL Test: Successfully created stream and sent sample")
        return True
    except Exception as e:
        print(f"LSL Test Error: {e}")
        return False

if __name__ == "__main__":
    if create_test_stream():
        print("LSL stream creation successful!")
        sys.exit(0)
    else:
        print("LSL stream creation failed!")
        sys.exit(1)
EOF

chmod +x ~/lsl_test.py

# Run the LSL test
echo "Testing LSL stream creation..."
source ~/.venv/bin/activate || source ~/venv/bin/activate || echo "Error: Could not activate Python virtual environment"
python ~/lsl_test.py

# 4. Restart the service
echo "Restarting camera service..."
sudo systemctl restart imx296-camera.service

# 5. Check service logs
echo "Checking service logs (last 10 lines)..."
sudo journalctl -u imx296-camera.service -n 10

echo "Fix script complete. Check the dashboard for updated status."
echo "If issues persist, check full logs with: sudo journalctl -u imx296-camera.service" 