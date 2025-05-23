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
    device_id = "10"  # Default
    if IS_RPI5:
        if os.environ.get("cam1"):
            device_id = "11"
            logger.info("Using device ID 11 for Camera 1 on Pi 5")
        else:
            logger.info("Using device ID 10 for Camera 0 on Pi 5")
    
    # Try direct detection of video devices first
    try:
        v4l2_devices = []
        for dev in os.listdir('/dev'):
            if dev.startswith('video'):
                v4l2_devices.append(f"/dev/{dev}")
        logger.debug(f"Found video devices: {v4l2_devices}")
    except Exception as e:
        logger.debug(f"Error listing video devices: {e}")
        v4l2_devices = []
    
    # Try media devices 0-5
    for m in range(6):
        media_dev_path = f"/dev/media{m}"
        
        if not os.path.exists(media_dev_path):
            logger.debug(f"Skipping non-existent device {media_dev_path}")
            continue
        
        # First check if we have permission to access this device
        try:
            with open(media_dev_path, 'rb') as f:
                pass  # Just checking access
            has_permission = True
        except PermissionError:
            logger.debug(f"No permission to access {media_dev_path}")
            has_permission = False
        
        # Correct entity name format from bash script
        entity_name = f"'imx296 {device_id}-001a'"
        
        # Build command to check if this is the right media device
        test_cmd = ["media-ctl", "-d", media_dev_path, "-p"]
        try:
            if has_permission:
                result = subprocess.run(test_cmd, capture_output=True, text=True)
            else:
                # First try to fix permissions
                if ensure_device_permission(media_dev_path):
                    result = subprocess.run(test_cmd, capture_output=True, text=True)
                else:
                    # Try with elevated privileges as a last resort
                    logger.debug(f"Trying {media_dev_path} with elevated privileges")
                    result = run_elevated_command(test_cmd)
                
            if result.returncode != 0:
                continue
                
            if entity_name.strip("'") in result.stdout:
                logger.info(f"Found IMX296 camera on {media_dev_path}, entity: {entity_name}")
                return media_dev_path, entity_name
        except Exception as e:
            logger.warning(f"Error checking {media_dev_path}: {e}")
    
    # If we get here, we need to try a more aggressive approach
    logger.warning("Could not find IMX296 camera via standard method, trying alternative detection...")
    
    # Try to find device by executing v4l2-ctl --list-devices
    try:
        result = subprocess.run(["v4l2-ctl", "--list-devices"], capture_output=True, text=True)
        if result.returncode == 0:
            lines = result.stdout.split('\n')
            for i, line in enumerate(lines):
                if "imx296" in line.lower():
                    # Next line should have the device path
                    if i + 1 < len(lines) and lines[i+1].strip().startswith('/dev/'):
                        device_path = lines[i+1].strip()
                        logger.info(f"Found IMX296 camera on {device_path} via v4l2-ctl")
                        
                        # Try to convert video device to media device
                        if "video" in device_path:
                            for m in range(6):
                                media_dev_path = f"/dev/media{m}"
                                if os.path.exists(media_dev_path):
                                    return media_dev_path, entity_name
    except Exception as e:
        logger.warning(f"Error in alternative detection: {e}")
    
    logger.error("Could not find IMX296 camera media device")
    return None, None

def ensure_device_permission(media_dev_path):
    """Ensure the current user has read/write access to the media device"""
    try:
        # Check if we can access the device
        with open(media_dev_path, 'rb') as f:
            pass  # Just checking if we can open it
        logger.debug(f"Already have permission to access {media_dev_path}")
        return True
    except PermissionError:
        logger.warning(f"No permission to access {media_dev_path}, attempting to fix...")
        
        # Try different approaches to fix permissions
        
        # 1. Try to get user and group information
        user = os.environ.get('USER', os.environ.get('USERNAME', 'pi'))
        
        # 2. Check if device belongs to video group
        try:
            import stat
            import pwd
            import grp
            
            device_stat = os.stat(media_dev_path)
            device_group = grp.getgrgid(device_stat.st_gid).gr_name
            
            logger.debug(f"Device {media_dev_path} belongs to group: {device_group}")
            
            # Check if user is in the device group
            user_info = pwd.getpwnam(user)
            user_groups = [grp.getgrgid(g).gr_name for g in os.getgroups()]
            
            if device_group in user_groups:
                logger.debug(f"User {user} is in the {device_group} group but still can't access device")
                
                # The permissions must be wrong on the device
                if not (device_stat.st_mode & stat.S_IRGRP and device_stat.st_mode & stat.S_IWGRP):
                    logger.debug(f"Device {media_dev_path} doesn't have read/write permissions for group")
                    
                    # Fix permissions
                    cmd = ["chmod", "g+rw", media_dev_path]
                    result = run_elevated_command(cmd)
                    if result.returncode == 0:
                        logger.info(f"Fixed permissions for {media_dev_path}")
                        return True
            else:
                logger.debug(f"User {user} is not in the {device_group} group")
                
                # Try to add user to the video group
                cmd = ["usermod", "-a", "-G", device_group, user]
                result = run_elevated_command(cmd)
                if result.returncode == 0:
                    logger.info(f"Added user {user} to group {device_group}")
                    logger.info("You need to log out and log back in for this change to take effect")
                    
                    # As a temporary fix, also change device permissions directly
                    cmd = ["chmod", "a+rw", media_dev_path] 
                    result = run_elevated_command(cmd)
                    if result.returncode == 0:
                        logger.info(f"Temporarily granted universal access to {media_dev_path}")
                        return True
        except ImportError as e:
            logger.debug(f"Could not import necessary modules for group checking: {e}")
        except Exception as e:
            logger.debug(f"Error checking group membership: {e}")
        
        # 3. Last resort - try direct permission change 
        try:
            cmd = ["chmod", "a+rw", media_dev_path]
            result = run_elevated_command(cmd)
            if result.returncode == 0:
                logger.info(f"Granted everyone access to {media_dev_path} as a fallback")
                
                # Check if it worked
                try:
                    with open(media_dev_path, 'rb') as f:
                        pass
                    return True
                except PermissionError:
                    pass
        except Exception as e:
            logger.debug(f"Error in fallback permission fix: {e}")
                
        logger.warning(f"Could not fix permissions for {media_dev_path}")
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

def create_lsl_outlet(name="IMX296Camera", stream_type="Video", fps=100):
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
        # rpicam-vid and libcamera-vid both use milliseconds for the -t parameter
        duration_arg = ["-t", str(duration_ms)]
        logger.debug(f"Setting recording duration to {duration_ms} milliseconds")
    
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
        # For Pi 5, use rpicam-vid with optimized parameters for high FPS
        cmd = [
            "rpicam-vid",
            *workaround,
            *camera_arg,
            "--width", str(width),
            "--height", str(height),
            "--denoise", "cdn_off",
            "--framerate", str(fps),
            "--flush", "1",  # Flush frames to output immediately
            "--inline",     # Use inline headers for better compatibility
            "--output-buffer", "2",  # Increase output buffer
            "--timeout", "0",  # No timeout
            "--awb", "off",    # Disable auto white balance to reduce processing
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
            "--flush", "1",
            "--inline",
            "--timeout", "0",
            "--awb", "off",
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
        stderr=subprocess.PIPE,
        bufsize=0  # Unbuffered output for faster processing
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
    start_time = time.time()
    last_update_time = start_time
    camera_started = False
    
    # Check function for real-time output inspection
    def check_for_frame_indicators(line):
        # Many different patterns we might see in output depending on camera version
        frame_patterns = [
            "frame", "Frame",
            "snapshot", "Snapshot",
            "image", "Image",
            "picture", "Picture",
            "camera_buffer", "buffer",
            "encoding"
        ]
        
        for pattern in frame_patterns:
            if pattern in line:
                return True
        return False
    
    logger.debug(f"Started monitoring camera process output")
    
    # Read both stdout and stderr for frame information (combine streams)
    for pipe in [camera_process.stdout, camera_process.stderr]:
        if pipe:
            threading.Thread(target=read_pipe, args=(pipe,), daemon=True).start()
    
    # Keep the monitoring thread alive as long as the camera process is running
    while camera_process.poll() is None and not stop_event.is_set():
        # Even if we're not seeing explicit frame indicators, we can use
        # time-based updates for low-rate cameras
        current_time = time.time()
        time_since_start = current_time - start_time
        
        if not camera_started and time_since_start > 2.0:
            logger.debug("Camera process has been running for 2 seconds, assuming it's started")
            camera_started = True
        
        # For slow cameras, try to update based on time as a fallback
        if camera_started and current_time - last_update_time > 0.5:
            frame_number += 1
            fps_counter += 1
            push_lsl_sample(frame_number)
            last_update_time = current_time
            
            # Report status periodically
            if current_time - last_fps_time >= 2.0:
                elapsed = current_time - last_fps_time
                fps_rate = fps_counter / elapsed if elapsed > 0 else 0
                logger.info(f"Current frame rate: {fps_rate:.1f} FPS ({fps_counter} frames in {elapsed:.1f}s)")
                fps_counter = 0
                last_fps_time = current_time
        
        time.sleep(0.01)  # Short sleep to prevent CPU hogging

def read_pipe(pipe):
    """Read from a pipe (stdout or stderr) and process lines"""
    global fps_counter, last_fps_time, lsl_data
    
    frame_number = 0
    last_line_time = time.time()
    
    for line in iter(pipe.readline, b''):
        if stop_event.is_set():
            break
            
        line_str = line.decode().strip()
        if not line_str:
            continue
        
        # Log camera output
        if "error" in line_str.lower() or "warning" in line_str.lower():
            logger.warning(f"Camera: {line_str}")
        elif "frame" in line_str.lower():
            logger.debug(f"Camera frame: {line_str}")
        else:
            logger.debug(f"Camera: {line_str}")
            
        # Detect frames using multiple patterns
        is_frame = False
        
        # Frame-specific patterns
        frame_patterns = [
            "frame", "Frame", 
            "snapshot", "Snapshot",
            "image", "Image", 
            "picture", "Picture",
            "camera_buffer", "buffer"
        ]
        
        for pattern in frame_patterns:
            if pattern in line_str:
                is_frame = True
                break
        
        # Process frame data
        if is_frame:
            frame_number += 1
            fps_counter += 1
            
            # Extract timestamp if available in the output
            timestamp = None
            time_patterns = [
                r"time(?:stamp)?\s*(?::|\s)\s*(\d+\.\d+)",  # time: 123.456
                r"pts\s*(?::|\s)\s*(\d+\.\d+)",            # pts: 123.456
                r"timestamp\s*=\s*(\d+\.\d+)"              # timestamp=123.456
            ]
            
            for pattern in time_patterns:
                match = re.search(pattern, line_str)
                if match:
                    try:
                        timestamp = float(match.group(1))
                        break
                    except ValueError:
                        pass
            
            # Push frame data to LSL
            push_lsl_sample(frame_number, timestamp)
            
            # Update last line time
            last_line_time = time.time()

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
    parser.add_argument('--duration', type=float, default=10, help='Recording duration in seconds (default: 10)')
    parser.add_argument('--output', type=str, default='', help='Output video file path (default: auto-generated)')
    parser.add_argument('--lsl-name', type=str, default='IMX296Camera', help='LSL stream name (default: IMX296Camera)')
    parser.add_argument('--lsl-type', type=str, default='Video', help='LSL stream type (default: Video)')
    parser.add_argument('--cam1', action='store_true', help='Use camera 1 instead of camera 0')
    parser.add_argument('--preview', action='store_true', help='Show camera preview during recording')
    parser.add_argument('--setup-permissions', action='store_true', help='Set up device permissions for the current user')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose logging')
    parser.add_argument('--check-camera', action='store_true', help='Check camera capabilities and exit')
    args = parser.parse_args()
    
    # Convert duration from seconds to milliseconds
    duration_ms = int(args.duration * 1000) if args.duration > 0 else 0
    
    # Set up logging level
    if args.verbose:
        logger.setLevel(logging.DEBUG)
        logger.info("Verbose logging enabled")
    
    # Log all arguments
    logger.debug(f"Command line arguments: {vars(args)}")
    logger.debug(f"Duration in milliseconds: {duration_ms}")

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
         
    # Validate recording duration
    if duration_ms <= 0:
        logger.info("No duration specified, will record until interrupted")
    elif duration_ms < 1000:
        logger.warning(f"Very short duration specified ({args.duration} seconds). Consider increasing for better results.")
    
    # Check if FPS is reasonable
    if args.fps > 120:
        logger.warning(f"Very high FPS requested ({args.fps}). The camera might not achieve this rate.")
        logger.warning("Consider reducing resolution for better high-FPS performance.")
    
    # Set camera selection environment variable if needed
    if args.cam1:
        os.environ["cam1"] = "1"
        logger.info("Using camera 1")
    
    # Detect Raspberry Pi version
    IS_RPI5 = is_raspberry_pi5()
    logger.info(f"Detected platform: {'Raspberry Pi 5' if IS_RPI5 else 'Older Raspberry Pi'}")
    
    # Check for camera and software
    try:
        if IS_RPI5:
            cmd = ["which", "rpicam-vid"]
        else:
            cmd = ["which", "libcamera-vid"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            camera_bin = result.stdout.strip()
            logger.info(f"Found camera software: {camera_bin}")
        else:
            logger.warning(f"Camera software not found! Please install the Raspberry Pi camera software.")
            logger.warning("For Pi 5: sudo apt install rpicam-apps")
            logger.warning("For older Pi: sudo apt install libcamera-apps")
            return 1
    except Exception as e:
        logger.warning(f"Error checking for camera software: {e}")
    
    # Check if camera is detected
    try:
        if IS_RPI5:
            cmd = ["rpicam-hello", "--list-cameras"]
        else:
            cmd = ["libcamera-hello", "--list-cameras"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            if "No cameras available" in result.stdout:
                logger.error("No cameras detected by the system!")
                return 1
            else:
                logger.info(f"Camera detected: {result.stdout.strip()}")
        else:
            logger.warning(f"Could not check for cameras: {result.stderr}")
    except Exception as e:
        logger.warning(f"Error checking for cameras: {e}")
    
    # Check camera mode if requested
    if args.check_camera:
        logger.info("Camera check requested, running camera hello app...")
        try:
            if IS_RPI5:
                cmd = ["rpicam-hello", "--list-cameras"]
            else:
                cmd = ["libcamera-hello", "--list-cameras"]
            subprocess.run(cmd)
            return 0
        except Exception as e:
            logger.error(f"Error checking camera: {e}")
            return 1
    
    # Find camera media device
    media_dev_path, entity_name = find_imx296_media_device()
    if not media_dev_path or not entity_name:
        logger.error("Camera not found. Exiting.")
        return 1
    
    # Ensure we have access to the media device
    if not ensure_device_permission(media_dev_path):
        logger.warning("Could not ensure permission to media device.")
        logger.warning("You might need to run with --setup-permissions once, then log out and back in.")
        
        # Try running with temporary privileges for this session
        logger.info("Attempting to continue with elevated privileges for media-ctl...")
    
    # Configure camera cropping
    if not configure_media_ctl(media_dev_path, entity_name, args.width, args.height):
        logger.error("Failed to configure camera. Exiting.")
        return 1
    
    # Create LSL outlet
    if LSL_AVAILABLE:
        lsl_outlet = create_lsl_outlet(name=args.lsl_name, stream_type=args.lsl_type, fps=args.fps)
    
    # Create dated output directory
    output_dir = create_output_directory()
    logger.info(f"Using output directory: {output_dir}")
    
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
        
        # Calculate appropriate exposure time if not specified
        exposure = args.exposure
        if exposure is None:
            # Default exposure: try to balance frame rate and exposure
            # For high FPS, we need shorter exposure
            if args.fps > 60:
                exposure = int(min(1000000 / args.fps * 0.8, 10000))
                logger.info(f"Automatically setting exposure to {exposure}µs for high FPS")
            else:
                exposure = 10000  # Default exposure for lower FPS
        
        camera_proc = start_camera_recording(
            args.width, args.height, args.fps, 
            str(video_path), duration_ms, exposure,
            preview=args.preview
        )
        
        # Wait for camera process to finish or Ctrl+C
        logger.info(f"Recording started with duration: {args.duration} seconds. Press Ctrl+C to stop earlier.")
        while camera_proc.poll() is None and not stop_event.is_set():
            time.sleep(0.1)  # Check more frequently
            
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
            if os.path.exists(str(video_path)):
                video_size = os.path.getsize(str(video_path))
                logger.info(f"Video size: {video_size} bytes")
                if video_size < 1000:
                    logger.warning("Video file is very small! Recording may have failed.")
            else:
                logger.error(f"Video file was not created: {video_path}")
            
            logger.info(f"Frames captured: {len(lsl_data)}")
            if len(lsl_data) < 5 and args.duration > 1:
                logger.warning(f"Only {len(lsl_data)} frames were captured. Camera may not be working properly.")
        else:
            logger.warning("No LSL data was collected during recording")
        
        # Analyze PTS file if not on Pi 5
        if not IS_RPI5:
            analyze_pts_file()
    
    logger.info("Recording complete")
    return 0

if __name__ == "__main__":
    sys.exit(main()) 