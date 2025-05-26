#!/bin/bash
# Update camera_stream.py to work with IMX296 camera
# By: Anzal KS <anzal.ks@gmail.com>
set -e

echo "===== Updating camera_stream.py for IMX296 Camera ====="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SRC_DIR="$REPO_ROOT/src/raspberry_pi_lsl_stream"

# Create directory if it doesn't exist
mkdir -p "$SRC_DIR"

# Create/update camera_stream.py
cat > "$SRC_DIR/camera_stream.py" << 'EOL'
#!/usr/bin/env python3
"""
Camera stream module for IMX296 global shutter camera
By: Anzal KS <anzal.ks@gmail.com>
"""

import argparse
import os
import subprocess
import time
import threading
import logging
import numpy as np
import json
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("camera_stream")

# Try to import pylsl, but don't fail if not available
try:
    import pylsl
    has_pylsl = True
    logger.info("LSL support enabled")
except ImportError:
    has_pylsl = False
    logger.warning("LSL not available - continuing without streaming")


class IMX296CameraStream:
    """Stream from IMX296 global shutter camera with ROI configuration and LSL integration"""
    
    def __init__(self, width=400, height=400, framerate=30, output_dir="/tmp/recordings",
                 enable_lsl=True, lsl_stream_name="camera", lsl_stream_type="Video", 
                 ffmpeg_options=None, create_output_dir=True, fix_permissions=True):
        """Initialize camera stream with required parameters"""
        self.width = width
        self.height = height
        self.framerate = framerate
        self.output_dir = output_dir
        self.enable_lsl = enable_lsl and has_pylsl
        self.lsl_stream_name = lsl_stream_name
        self.lsl_stream_type = lsl_stream_type
        self.ffmpeg_options = ffmpeg_options or "-vsync 0 -c:v h264_omx -b:v 2M -pix_fmt yuv420p"
        self.process = None
        self.recording = False
        self.current_file = None
        self.lsl_outlet = None
        
        # Create output directory if needed
        if create_output_dir and not os.path.exists(output_dir):
            try:
                os.makedirs(output_dir, exist_ok=True)
                logger.info(f"Created output directory: {output_dir}")
                if fix_permissions:
                    os.chmod(output_dir, 0o777)
                    logger.info(f"Fixed permissions for {output_dir}")
            except Exception as e:
                logger.error(f"Failed to create output directory: {e}")
                self.output_dir = "/tmp/recordings"
                os.makedirs(self.output_dir, exist_ok=True)
                logger.info(f"Falling back to {self.output_dir}")

        # Set up LSL if enabled
        if self.enable_lsl:
            self._setup_lsl()

    def _setup_lsl(self):
        """Set up LSL outlet for streaming"""
        try:
            # Create LSL stream info - all data must be numeric
            lsl_has_string_support = False  # IMPORTANT: Set this to False to ensure numeric-only streaming
            
            # Use float64 type for all values to ensure compatibility
            info = pylsl.StreamInfo(
                name=self.lsl_stream_name,
                type=self.lsl_stream_type,
                channel_count=3,  # timestamp, frame_number, is_recording
                nominal_srate=self.framerate,
                channel_format=pylsl.cf_double,  # Use double precision float
                source_id=f"imx296_{os.getpid()}"
            )
            
            # Add metadata
            info.desc().append_child_value("manufacturer", "Sony")
            info.desc().append_child_value("model", "IMX296")
            info.desc().append_child_value("width", str(self.width))
            info.desc().append_child_value("height", str(self.height))
            info.desc().append_child_value("framerate", str(self.framerate))
            
            # Create outlet
            self.lsl_outlet = pylsl.StreamOutlet(info)
            logger.info(f"Created LSL outlet: {self.lsl_stream_name} ({self.lsl_stream_type})")
        except Exception as e:
            logger.error(f"Failed to set up LSL: {e}")
            self.enable_lsl = False
            self.lsl_outlet = None

    def _configure_media_pipeline(self):
        """Configure media pipeline for IMX296 camera using media-ctl"""
        try:
            # Find the media device
            media_dev = "/dev/media0"
            if os.path.exists("/dev/media1"):
                # Also check media1 for ISP
                subprocess.run(["media-ctl", "-d", "/dev/media1", "-p"], 
                              check=False, capture_output=True)
            
            # Configure sensor format
            subprocess.run(
                ["media-ctl", "-d", media_dev, "--set-v4l2", f'"imx296":0[fmt:SBGGR10_1X10/{self.width}x{self.height}]'],
                check=False, shell=True
            )
            
            # Configure CSI-2 receiver
            subprocess.run(
                ["media-ctl", "-d", media_dev, "--set-v4l2", f'"*rp1_csi2":0[fmt:SBGGR10_1X10/{self.width}x{self.height}]'],
                check=False, shell=True
            )
            
            logger.info(f"Configured media pipeline for {self.width}x{self.height} SBGGR10_1X10")
            return True
        except Exception as e:
            logger.error(f"Failed to configure media pipeline: {e}")
            return False

    def _find_camera_device(self):
        """Find the IMX296 camera device"""
        try:
            # Get list of camera devices
            result = subprocess.run(
                ["v4l2-ctl", "--list-devices"], 
                check=True, capture_output=True, text=True
            )
            
            # Parse output to find IMX296
            lines = result.stdout.split('\n')
            for i, line in enumerate(lines):
                if "imx296" in line.lower() and i + 1 < len(lines):
                    device = lines[i + 1].strip()
                    if device.startswith("/dev/video"):
                        logger.info(f"Found IMX296 camera at {device}")
                        return device
            
            # Default fallback
            logger.warning("IMX296 camera not found, using default /dev/video0")
            return "/dev/video0"
        except Exception as e:
            logger.error(f"Failed to find camera device: {e}")
            return "/dev/video0"

    def start_recording(self):
        """Start recording from the camera with proper configuration"""
        # First, configure the media pipeline
        self._configure_media_pipeline()
        
        # Find camera device
        camera_dev = self._find_camera_device()
        
        # Create output filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.current_file = os.path.join(self.output_dir, f"imx296_{timestamp}.mp4")
        
        # Check if output directory exists and is writable
        if not os.path.exists(self.output_dir):
            try:
                os.makedirs(self.output_dir, exist_ok=True)
                os.chmod(self.output_dir, 0o777)
            except Exception as e:
                logger.error(f"Failed to create output directory: {e}")
                self.output_dir = "/tmp"
                self.current_file = os.path.join(self.output_dir, f"imx296_{timestamp}.mp4")
        
        logger.info(f"Starting recording to {self.current_file}")
        
        # Construct ffmpeg command
        cmd = [
            "ffmpeg", "-hide_banner", 
            "-f", "v4l2", 
            "-s", f"{self.width}x{self.height}",
            "-i", camera_dev, 
        ]
        
        # Add ffmpeg options
        cmd.extend(self.ffmpeg_options.split())
        
        # Add output file
        cmd.append(self.current_file)
        
        logger.info(f"Command: {' '.join(cmd)}")
        
        try:
            # Start ffmpeg process
            self.process = subprocess.Popen(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE
            )
            
            # Start LSL streaming thread if enabled
            if self.enable_lsl and self.lsl_outlet:
                self.recording = True
                threading.Thread(target=self._stream_lsl, daemon=True).start()
                
            logger.info("Recording started")
            return True
        except Exception as e:
            logger.error(f"Failed to start recording: {e}")
            self.process = None
            return False

    def stop_recording(self):
        """Stop the current recording"""
        if self.process:
            logger.info("Stopping recording")
            self.recording = False
            
            # Send SIGTERM to ffmpeg
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                
            stdout, stderr = self.process.communicate()
            logger.info("Recording stopped")
            self.process = None
            
            # Check if file exists and has valid size
            if self.current_file and os.path.exists(self.current_file):
                file_size = os.path.getsize(self.current_file)
                if file_size > 4096:  # More than just headers
                    logger.info(f"Recording successful: {self.current_file} ({file_size} bytes)")
                    return True
                else:
                    logger.warning(f"Recording file too small: {file_size} bytes")
                    return False
        
        return False

    def _stream_lsl(self):
        """Stream data to LSL"""
        frame_number = 0
        while self.recording and self.lsl_outlet:
            try:
                # Create sample with timestamp, frame number, recording status
                # IMPORTANT: All values must be numeric (no strings)
                timestamp = pylsl.local_clock()
                sample = [float(timestamp), float(frame_number), 1.0 if self.recording else 0.0]
                
                # Push sample to LSL
                self.lsl_outlet.push_sample(sample)
                
                # Increment frame counter
                frame_number += 1
                
                # Sleep to match framerate
                time.sleep(1.0 / self.framerate)
            except Exception as e:
                logger.error(f"LSL streaming error: {e}")
                time.sleep(0.1)  # Prevent tight loop on error

    def get_status(self):
        """Get current camera status"""
        status = {
            "width": self.width,
            "height": self.height,
            "framerate": self.framerate,
            "recording": self.recording,
            "lsl_enabled": self.enable_lsl and self.lsl_outlet is not None,
            "output_dir": self.output_dir,
            "current_file": self.current_file,
            "timestamp": datetime.now().isoformat()
        }
        return status


def main():
    """Main function to run camera stream"""
    parser = argparse.ArgumentParser(description="IMX296 Camera Stream")
    parser.add_argument("--width", type=int, default=400, help="Camera width (default: 400)")
    parser.add_argument("--height", type=int, default=400, help="Camera height (default: 400)")
    parser.add_argument("--framerate", type=int, default=30, help="Camera framerate (default: 30)")
    parser.add_argument("--output-dir", type=str, default="/tmp/recordings", 
                        help="Output directory for recordings (default: /tmp/recordings)")
    parser.add_argument("--enable-lsl", action="store_true", help="Enable LSL streaming")
    parser.add_argument("--lsl-stream-name", type=str, default="camera", 
                        help="LSL stream name (default: camera)")
    parser.add_argument("--lsl-stream-type", type=str, default="Video", 
                        help="LSL stream type (default: Video)")
    parser.add_argument("--ffmpeg-options", type=str, 
                        default="-vsync 0 -c:v h264_omx -b:v 2M -pix_fmt yuv420p",
                        help="FFmpeg options")
    parser.add_argument("--record-time", type=int, default=0, 
                        help="Recording time in seconds (0 = run until interrupted)")
    
    args = parser.parse_args()
    
    # Create camera stream
    camera = IMX296CameraStream(
        width=args.width,
        height=args.height,
        framerate=args.framerate,
        output_dir=args.output_dir,
        enable_lsl=args.enable_lsl,
        lsl_stream_name=args.lsl_stream_name,
        lsl_stream_type=args.lsl_stream_type,
        ffmpeg_options=args.ffmpeg_options,
        create_output_dir=True,
        fix_permissions=True
    )
    
    try:
        # Start recording
        camera.start_recording()
        
        # Run for specified time or until interrupted
        if args.record_time > 0:
            logger.info(f"Recording for {args.record_time} seconds")
            time.sleep(args.record_time)
            camera.stop_recording()
        else:
            logger.info("Recording until interrupted (Ctrl+C to stop)")
            while True:
                # Print status every 10 seconds
                status = camera.get_status()
                logger.info(f"Status: {json.dumps(status)}")
                time.sleep(10)
                
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        # Ensure recording is stopped
        camera.stop_recording()
        logger.info("Camera stream stopped")


if __name__ == "__main__":
    main()
EOL

# Make camera_stream.py executable
chmod +x "$SRC_DIR/camera_stream.py"

# Create __init__.py to make it a proper module
touch "$SRC_DIR/__init__.py"

echo "Updated camera_stream.py for IMX296 Camera"
echo "Added proper pipeline configuration and LSL integration"

# Create a simple test script
cat > "$SCRIPT_DIR/test_camera_stream.sh" << 'EOL'
#!/bin/bash
# Test the updated camera_stream.py
# By: Anzal KS <anzal.ks@gmail.com>
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Create test directory
TEST_DIR="/tmp/camera_stream_test"
mkdir -p "$TEST_DIR"
chmod 777 "$TEST_DIR"

echo "Testing camera_stream.py with native 400x400 resolution..."
echo "Output will be saved to $TEST_DIR"

# Run camera stream for 10 seconds
cd "$REPO_ROOT"
sudo python3 -m src.raspberry_pi_lsl_stream.camera_stream \
  --width 400 \
  --height 400 \
  --framerate 30 \
  --output-dir "$TEST_DIR" \
  --enable-lsl \
  --record-time 10

echo ""
echo "Test complete. Check output files:"
ls -lh "$TEST_DIR"
EOL

chmod +x "$SCRIPT_DIR/test_camera_stream.sh"
echo "Created test script at $SCRIPT_DIR/test_camera_stream.sh"

echo ""
echo "===== Instructions ====="
echo "To test the camera stream module, run:"
echo "  sudo $SCRIPT_DIR/test_camera_stream.sh"
echo ""
echo "To use in your own scripts:"
echo "  from src.raspberry_pi_lsl_stream.camera_stream import IMX296CameraStream"
echo "  camera = IMX296CameraStream(width=400, height=400)"
echo "  camera.start_recording()"
echo "  # ... do other things ..."
echo "  camera.stop_recording()"
</rewritten_file> 