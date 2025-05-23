#!/usr/bin/env python3
"""
Simplified IMX296 Camera Recorder with LSL
------------------------------------------
This script configures an IMX296 global shutter camera on Raspberry Pi,
streams metadata via LSL, and saves video to a local file.
"""

import os
import sys
import time
import subprocess
import threading
import argparse
import logging
import re
import datetime
import signal
import shutil
import csv
from pathlib import Path

# Optional import of pylsl - we'll check this later
try:
    import pylsl
    LSL_AVAILABLE = True
except ImportError:
    LSL_AVAILABLE = False
    print("Warning: pylsl not installed. LSL streaming will be disabled.")

# ====== Logging setup ======
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("IMX296Camera")

# Global variables
stop_event = threading.Event()
camera_process = None
lsl_outlet = None
fps_counter = 0
last_fps_time = time.time()
IS_RPI5 = False  # Will be set based on detection
PTS_FILE_PATH = "/dev/shm/camera.pts"
lsl_data = []  # Store LSL data for CSV export

def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully"""
    logger.info(f"Received signal {sig}, shutting down...")
    stop_event.set()
    if camera_process and camera_process.poll() is None:
        camera_process.terminate()

def is_raspberry_pi5():
    """Check if running on Raspberry Pi 5"""
    try:
        with open('/proc/cpuinfo', 'r') as f:
            cpuinfo = f.read()
            if re.search(r'Revision.*: ...17.', cpuinfo):
                logger.info("Detected Raspberry Pi 5")
                return True
    except Exception as e:
        logger.warning(f"Could not check Raspberry Pi version: {e}")
    
    logger.info("Not detected as Raspberry Pi 5, assuming older model")
    return False

def is_on_bookworm():
    """Check if running on Bookworm OS"""
    try:
        with open('/etc/os-release', 'r') as f:
            if '=bookworm' in f.read():
                logger.info("Detected Bookworm OS")
                return True
    except Exception as e:
        logger.warning(f"Could not check OS version: {e}")
    
    return False

def run_elevated_command(cmd):
    """Run a command with elevated privileges using pkexec or sudo"""
    # First try pkexec, which will prompt for password if needed
    if shutil.which('pkexec'):
        elevated_cmd = ['pkexec'] + cmd
    else:
        # Fallback to sudo if pkexec is not available
        elevated_cmd = ['sudo'] + cmd
    
    logger.debug(f"Running elevated command: {' '.join(elevated_cmd)}")
    return subprocess.run(elevated_cmd, capture_output=True, text=True)

def find_imx296_media_device():
    """Find the media device for the IMX296 camera using thorough search"""
    logger.info("Searching for IMX296 camera media device...")
    
    # Determine device ID (different for Pi models)
    # For Pi 5, it's 10 for camera 0 and 11 for camera 1
    device_id = "10"  # Default
    if IS_RPI5:
        if os.environ.get("cam1"):
            device_id = "11"
            logger.info("Using device ID 11 for Camera 1 on Pi 5")
        else:
            logger.info("Using device ID 10 for Camera 0 on Pi 5")
    
    # Try media devices 0-5
    for m in range(6):
        media_dev_path = f"/dev/media{m}"
        
        if not os.path.exists(media_dev_path):
            logger.debug(f"Skipping non-existent device {media_dev_path}")
            continue
        
        # Correct entity name format from bash script
        entity_name = f"'imx296 {device_id}-001a'"
        
        # Build command to check if this is the right media device
        test_cmd = ["media-ctl", "-d", media_dev_path, "-p"]
        try:
            # Make sure user has access to media device
            try:
                result = subprocess.run(test_cmd, capture_output=True, text=True)
            except PermissionError:
                logger.info(f"Permission error, trying with elevated privileges")
                result = run_elevated_command(test_cmd)
                
            if result.returncode != 0:
                continue
                
            if entity_name.strip("'") in result.stdout:
                logger.info(f"Found IMX296 camera on {media_dev_path}, entity: {entity_name}")
                return media_dev_path, entity_name
        except Exception as e:
            logger.warning(f"Error checking {media_dev_path}: {e}")
    
    logger.error("Could not find IMX296 camera media device")
    return None, None

def ensure_device_permission(media_dev_path):
    """Ensure the current user has read/write access to the media device"""
    try:
        # Check if we can access the device
        with open(media_dev_path, 'rb') as f:
            pass  # Just checking if we can open it
        return True
    except PermissionError:
        logger.warning(f"No permission to access {media_dev_path}, attempting to fix...")
        
        # Try to fix permissions
        try:
            # Get current user
            user = os.environ.get('USER', os.environ.get('USERNAME'))
            if not user:
                logger.warning("Could not determine current user")
                return False
                
            # Use pkexec/sudo to adjust permissions
            cmd = ["chgrp", "video", media_dev_path]
            result = run_elevated_command(cmd)
            if result.returncode != 0:
                logger.warning(f"Failed to change group: {result.stderr}")
                return False
                
            cmd = ["chmod", "g+rw", media_dev_path]
            result = run_elevated_command(cmd)
            if result.returncode != 0:
                logger.warning(f"Failed to change permissions: {result.stderr}")
                return False
                
            # Add user to video group if needed
            cmd = ["usermod", "-aG", "video", user]
            result = run_elevated_command(cmd)
            if result.returncode != 0:
                logger.warning(f"Failed to add user to video group: {result.stderr}")
                return False
                
            logger.info(f"Permission fixed for {media_dev_path}")
            logger.info("You may need to log out and log back in for group changes to take effect")
            return True
        except Exception as e:
            logger.error(f"Error fixing permissions: {e}")
            return False

def configure_media_ctl(media_dev_path, entity_name, width, height):
    """Configure the IMX296 sensor using media-ctl for hardware cropping"""
    logger.info(f"Configuring IMX296 sensor with media-ctl for {width}x{height}...")
    
    # Standard sensor dimensions
    full_width = 1440  # From the bash script
    full_height = 1088
    
    # Calculate crop coordinates to center the crop on the sensor
    x_offset = (full_width - width) // 2
    y_offset = (full_height - height) // 2
    
    # Format string for media-ctl command - exact format from the bash script
    format_str = f"fmt:SBGGR10_1X10/{width}x{height} crop:({x_offset},{y_offset})/{width}x{height}"
    
    # Execute media-ctl command with the exact format from the bash script
    # Use pkexec or sudo for elevation
    cmd = ["media-ctl", "-d", media_dev_path, "--set-v4l2", f"{entity_name}:0 [{format_str}]", "-v"]
    logger.info(f"Running media-ctl command with elevation...")
    
    result = run_elevated_command(cmd)
    if result.returncode != 0:
        logger.error(f"Failed to configure media-ctl: {result.stderr}")
        return False
        
    logger.info(f"Successfully configured IMX296 sensor crop: {format_str}")
    
    # Verify configuration using libcamera-hello
    try:
        logger.info("Verifying camera configuration with libcamera-hello...")
        verify_cmd = ["libcamera-hello", "--list-cameras"]
        verify_result = subprocess.run(verify_cmd, capture_output=True, text=True)
        if verify_result.returncode == 0:
            logger.info(f"Camera configuration verification complete")
        else:
            logger.warning(f"Camera verification failed: {verify_result.stderr}")
    except Exception as e:
        logger.warning(f"Could not verify with libcamera-hello: {e}")
    
    return True

def create_lsl_outlet(name="IMX296Camera", stream_type="Video", fps=60):
    """Create LSL outlet for camera metadata"""
    if not LSL_AVAILABLE:
        logger.warning("pylsl not available, skipping LSL outlet creation")
        return None
        
    try:
        logger.info(f"Creating LSL outlet: {name}")
        # Create stream info
        info = pylsl.StreamInfo(
            name=name,
            type=stream_type,
            channel_count=2,  # Timestamp and frame number
            nominal_srate=fps,
            channel_format=pylsl.cf_double64,
            source_id='imx296_camera'
        )
        
        # Add channel descriptions
        channels = info.desc().append_child("channels")
        channels.append_child("channel").append_child_value("label", "UnixTimestamp")
        channels.append_child("channel").append_child_value("label", "FrameNumber")
        
        # Create and return the outlet
        outlet = pylsl.StreamOutlet(info, chunk_size=1, max_buffered=fps*2)
        logger.info(f"LSL outlet '{name}' created")
        return outlet
    except Exception as e:
        logger.error(f"Failed to create LSL outlet: {e}")
        return None

def push_lsl_sample(frame_number, timestamp=None):
    """Push a sample to LSL with timestamp and frame number"""
    global lsl_outlet, lsl_data
    
    if timestamp is None:
        timestamp = time.time()
    
    # Save data for CSV export
    lsl_data.append([timestamp, frame_number])
    
    if lsl_outlet:
        try:
            lsl_outlet.push_sample([timestamp, float(frame_number)], timestamp)
        except Exception as e:
            logger.error(f"Error pushing LSL sample: {e}")

def save_lsl_data_to_csv(csv_path):
    """Save collected LSL data to a CSV file"""
    global lsl_data
    
    try:
        logger.info(f"Saving LSL data to {csv_path}")
        with open(csv_path, 'w', newline='') as csvfile:
            csv_writer = csv.writer(csvfile)
            csv_writer.writerow(['UnixTimestamp', 'FrameNumber'])
            csv_writer.writerows(lsl_data)
        logger.info(f"Saved {len(lsl_data)} LSL data points to CSV")
    except Exception as e:
        logger.error(f"Error saving LSL data to CSV: {e}")

def create_output_directory():
    """Create a dated directory structure for recordings"""
    # Create main recordings directory
    recordings_dir = Path("recordings")
    recordings_dir.mkdir(exist_ok=True)
    
    # Create dated subdirectory (YYYY-MM-DD)
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    date_dir = recordings_dir / today
    date_dir.mkdir(exist_ok=True)
    
    return date_dir

def parse_pts_file(pts_file_path):
    """Parse the PTS file to get frame timestamps"""
    timestamps = []
    try:
        with open(pts_file_path, 'r') as f:
            for line in f:
                parts = line.strip().split(' ')
                if len(parts) >= 2:
                    frame_num = int(parts[0])
                    frame_time = float(parts[1])
                    timestamps.append((frame_num, frame_time))
        return timestamps
    except Exception as e:
        logger.error(f"Error parsing PTS file: {e}")
        return []

def start_camera_recording(width, height, fps, output_path, duration_ms=0, exposure_us=None, preview=False):
    """Start camera recording using appropriate command based on Pi version"""
    global camera_process, IS_RPI5, PTS_FILE_PATH
    
    # Clear any existing PTS file
    if os.path.exists(PTS_FILE_PATH):
        try:
            os.unlink(PTS_FILE_PATH)
        except Exception as e:
            logger.warning(f"Failed to remove existing PTS file: {e}")
    
    # Check for bookworm and add workaround if needed
    workaround = []
    if is_on_bookworm():
        workaround = ["--no-raw"]
    
    # Make sure output directory exists
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    
    # Determine duration argument
    duration_arg = []
    if duration_ms > 0:
        duration_arg = ["-t", str(duration_ms)]
    
    # Determine exposure argument
    exposure_arg = []
    if exposure_us is not None:
        exposure_arg = ["--shutter", str(exposure_us)]
    
    # Determine camera selection
    camera_arg = []
    if os.environ.get("cam1"):
        camera_arg = ["--camera", "1"]
    
    # Determine preview option
    preview_arg = []
    if preview:
        preview_arg = ["--preview"] if not IS_RPI5 else ["--display"]
    
    # Build appropriate command based on Pi version
    if IS_RPI5:
        # For Pi 5, use rpicam-vid
        cmd = [
            "rpicam-vid",
            *workaround,
            *camera_arg,
            "--width", str(width),
            "--height", str(height),
            "--denoise", "cdn_off",
            "--framerate", str(fps),
            *duration_arg,
            *exposure_arg,
            *preview_arg,
            "-o", output_path
        ]
    else:
        # For older Pi models, use libcamera-vid with PTS file
        cmd = [
            "libcamera-vid",
            *workaround,
            "--width", str(width),
            "--height", str(height),
            "--denoise", "cdn_off",
            "--framerate", str(fps),
            "--save-pts", PTS_FILE_PATH,
            *duration_arg,
            *exposure_arg,
            *preview_arg,
            "--codec", "h264",
            "-o", output_path
        ]
    
    logger.info(f"Starting camera recording with command: {' '.join(cmd)}")
    
    # Start camera process
    camera_process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    # Start thread to monitor process output and push LSL samples
    threading.Thread(target=monitor_camera_process, daemon=True).start()
    
    return camera_process

def read_timestamps_from_pts():
    """Read frame timestamps from PTS file"""
    if not os.path.exists(PTS_FILE_PATH):
        return []
    
    try:
        return parse_pts_file(PTS_FILE_PATH)
    except Exception as e:
        logger.error(f"Error reading PTS file: {e}")
        return []

def monitor_camera_process():
    """Monitor camera process output and push LSL samples"""
    global camera_process, fps_counter, last_fps_time, stop_event, IS_RPI5
    
    if not camera_process:
        return
    
    frame_number = 0
    last_pts_read_time = 0
    pts_data = []
    
    # Read stderr for frame information
    for line in camera_process.stderr:
        if stop_event.is_set():
            break
            
        line_str = line.decode().strip()
        
        # Log camera output
        if "error" in line_str.lower() or "warning" in line_str.lower():
            logger.warning(f"Camera: {line_str}")
        else:
            logger.debug(f"Camera: {line_str}")
            
        # Look for frame indications in the output
        if "Frame" in line_str or "frame" in line_str:
            frame_number += 1
            fps_counter += 1
            
            # For non-Pi5, read PTS file periodically to get timestamps
            if not IS_RPI5 and time.time() - last_pts_read_time > 1.0:
                pts_data = read_timestamps_from_pts()
                last_pts_read_time = time.time()
                
            # Find frame timestamp if available
            frame_timestamp = None
            for pts_frame, pts_time in pts_data:
                if pts_frame == frame_number:
                    frame_timestamp = pts_time
                    break
                    
            # Push frame data to LSL
            if frame_timestamp:
                push_lsl_sample(frame_number, frame_timestamp)
            else:
                push_lsl_sample(frame_number)
            
            # Report FPS periodically
            current_time = time.time()
            if current_time - last_fps_time >= 5.0:
                elapsed = current_time - last_fps_time
                fps_rate = fps_counter / elapsed if elapsed > 0 else 0
                logger.info(f"Current frame rate: {fps_rate:.1f} FPS ({fps_counter} frames in {elapsed:.1f}s)")
                fps_counter = 0
                last_fps_time = current_time

def analyze_pts_file():
    """Analyze the PTS file using ptsanalyze tool if available"""
    if IS_RPI5 or not os.path.exists(PTS_FILE_PATH):
        return
        
    # Check if ptsanalyze tool exists
    ptsanalyze_path = shutil.which("ptsanalyze")
    if not ptsanalyze_path:
        logger.warning("ptsanalyze tool not found, skipping PTS analysis")
        return
        
    try:
        # Remove existing tstamps.csv if it exists
        if os.path.exists("tstamps.csv"):
            os.unlink("tstamps.csv")
            
        # Run ptsanalyze
        cmd = [ptsanalyze_path, PTS_FILE_PATH]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            logger.info("PTS file analysis complete")
        else:
            logger.warning(f"PTS analysis failed: {result.stderr}")
    except Exception as e:
        logger.error(f"Error analyzing PTS file: {e}")

def check_even_dimensions(width, height):
    """Check if width and height are even numbers"""
    if width % 2 != 0:
        logger.error("Width must be an even number")
        return False
    if height % 2 != 0:
        logger.error("Height must be an even number")
        return False
    return True

def setup_device_permissions():
    """Set up device permissions for the current user"""
    # Try to add current user to the video group
    try:
        # Get current user
        user = os.environ.get('USER', os.environ.get('USERNAME'))
        if not user:
            logger.warning("Could not determine current user")
            return False
            
        # Check if the user is already in the video group
        cmd = ["groups", user]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if "video" in result.stdout:
            logger.info(f"User {user} is already in the video group")
            return True
            
        # Add user to video group
        logger.info(f"Adding user {user} to video group...")
        cmd = ["usermod", "-aG", "video", user]
        result = run_elevated_command(cmd)
        if result.returncode != 0:
            logger.warning(f"Failed to add user to video group: {result.stderr}")
            logger.warning("You may need to run as sudo or ensure the user has video group access")
            return False
        
        logger.info(f"Added user {user} to video group")
        logger.info("You may need to log out and log back in for group changes to take effect")
        return True
    except Exception as e:
        logger.error(f"Error setting up device permissions: {e}")
        return False

def main():
    """Main function"""
    global lsl_outlet, stop_event, IS_RPI5, lsl_data

    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Simplified IMX296 Camera Recorder with LSL')
    parser.add_argument('--width', type=int, default=400, help='Camera width (default: 400)')
    parser.add_argument('--height', type=int, default=400, help='Camera height (default: 400)')
    parser.add_argument('--fps', type=int, default=100, help='Target frame rate (default: 100)')
    parser.add_argument('--exposure', type=int, default=None, help='Exposure time in microseconds (optional)')
    parser.add_argument('--duration', type=int, default=0, help='Recording duration in milliseconds (0 for infinite)')
    parser.add_argument('--output', type=str, default='', help='Output video file path (default: auto-generated)')
    parser.add_argument('--lsl-name', type=str, default='IMX296Camera', help='LSL stream name (default: IMX296Camera)')
    parser.add_argument('--lsl-type', type=str, default='Video', help='LSL stream type (default: Video)')
    parser.add_argument('--cam1', action='store_true', help='Use camera 1 instead of camera 0')
    parser.add_argument('--preview', action='store_true', help='Show camera preview during recording')
    parser.add_argument('--setup-permissions', action='store_true', help='Set up device permissions for the current user')
    args = parser.parse_args()

    # Set up device permissions if requested
    if args.setup_permissions:
        if setup_device_permissions():
            logger.info("Device permissions set up successfully. Please log out and log back in.")
        else:
            logger.error("Failed to set up device permissions")
        return 0
    
    # Check if width and height are even numbers
    if not check_even_dimensions(args.width, args.height):
        return 1
    
    # Set camera selection environment variable if needed
    if args.cam1:
        os.environ["cam1"] = "1"
        logger.info("Using camera 1")
    
    # Detect Raspberry Pi version
    IS_RPI5 = is_raspberry_pi5()
    
    # Find camera media device
    media_dev_path, entity_name = find_imx296_media_device()
    if not media_dev_path or not entity_name:
        logger.error("Camera not found. Exiting.")
        return 1
    
    # Ensure we have access to the media device
    if not ensure_device_permission(media_dev_path):
        logger.warning("Could not ensure permission to media device.")
        logger.warning("You might need to run with --setup-permissions once, then log out and back in.")
    
    # Configure camera cropping
    if not configure_media_ctl(media_dev_path, entity_name, args.width, args.height):
        logger.error("Failed to configure camera. Exiting.")
        return 1
    
    # Create LSL outlet
    if LSL_AVAILABLE:
        lsl_outlet = create_lsl_outlet(name=args.lsl_name, stream_type=args.lsl_type, fps=args.fps)
    
    # Create dated output directory
    output_dir = create_output_directory()
    
    # Generate output filenames if not specified
    if not args.output:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        suffix = ".mp4" if IS_RPI5 else ".h264"
        cam_suffix = "1" if args.cam1 else ""
        filename_base = f"recording{cam_suffix}_{args.width}x{args.height}_{args.fps}fps_{timestamp}"
        video_path = output_dir / f"{filename_base}{suffix}"
        csv_path = output_dir / f"{filename_base}.csv"
    else:
        # Use the provided output path but still keep it in our directory structure
        video_filename = os.path.basename(args.output)
        video_path = output_dir / video_filename
        csv_path = output_dir / f"{os.path.splitext(video_filename)[0]}.csv"
    
    # Start camera recording
    logger.info(f"Starting recording to {video_path}")
    try:
        # Reset LSL data collector
        lsl_data = []
        
        camera_proc = start_camera_recording(
            args.width, args.height, args.fps, 
            str(video_path), args.duration, args.exposure,
            preview=args.preview
        )
        
        # Wait for camera process to finish or Ctrl+C
        logger.info("Recording started. Press Ctrl+C to stop.")
        while camera_proc.poll() is None and not stop_event.is_set():
            time.sleep(0.5)
            
    except KeyboardInterrupt:
        logger.info("Recording stopped by user")
    finally:
        # Cleanup
        if camera_process and camera_process.poll() is None:
            logger.info("Terminating camera process...")
            camera_process.terminate()
            try:
                camera_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                camera_process.kill()
        
        # Save LSL data to CSV
        if lsl_data:
            save_lsl_data_to_csv(csv_path)
        
        # Analyze PTS file if not on Pi 5
        if not IS_RPI5:
            analyze_pts_file()
    
    logger.info("Recording complete")
    return 0

if __name__ == "__main__":
    sys.exit(main()) 