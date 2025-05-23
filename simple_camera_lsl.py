#!/usr/bin/env python3
"""
Simplified IMX296 Camera Recorder with LSL
------------------------------------------
This script uses GScrop shell script to configure and record from an IMX296 global shutter camera
on Raspberry Pi, streams metadata via LSL, and saves video to a local file.
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
lsl_data = []  # Store LSL data
MARKERS_FILE = "/dev/shm/camera_markers.txt"

def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully"""
    logger.info(f"Received signal {sig}, shutting down...")
    stop_event.set()
    if camera_process and camera_process.poll() is None:
        camera_process.terminate()

def create_lsl_outlet(name="IMX296Camera", stream_type="Video", fps=100):
    """Create LSL outlet for camera metadata"""
    if not LSL_AVAILABLE:
        logger.warning("pylsl not available, skipping LSL outlet creation")
        return None
        
    try:
        logger.info(f"Creating LSL outlet: {name}")
        # Create stream info with only one channel for frame numbers
        info = pylsl.StreamInfo(
            name=name,
            type=stream_type,
            channel_count=1,  # Only frame number
            nominal_srate=fps,
            channel_format=pylsl.cf_double64,
            source_id='imx296_camera'
        )
        
        # Add channel descriptions
        channels = info.desc().append_child("channels")
        channels.append_child("channel").append_child_value("label", "FrameNumber")
        
        # Create and return the outlet
        outlet = pylsl.StreamOutlet(info, chunk_size=1, max_buffered=fps*2)
        logger.info(f"LSL outlet '{name}' created")
        return outlet
    except Exception as e:
        logger.error(f"Failed to create LSL outlet: {e}")
        return None

def push_lsl_sample(frame_number, timestamp=None):
    """Push a sample to LSL with only frame number"""
    global lsl_outlet, lsl_data
    
    if timestamp is None:
        timestamp = time.time()
    
    # Save data for debugging/analysis (still save timestamp internally for stats)
    lsl_data.append([timestamp, float(frame_number)])
    
    if lsl_outlet:
        try:
            # Only push frame number as the sample
            lsl_outlet.push_sample([float(frame_number)], timestamp)
        except Exception as e:
            logger.error(f"Error pushing LSL sample: {e}")

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

def check_even_dimensions(width, height):
    """Check if width and height are even numbers"""
    if width % 2 != 0:
        logger.error("Width must be an even number")
        return False
    if height % 2 != 0:
        logger.error("Height must be an even number")
        return False
    return True

def monitor_markers_file():
    """Monitor the markers file created by GScrop script to get frame information"""
    global stop_event, lsl_data, MARKERS_FILE
    
    # Wait a bit to let the GScrop script start
    time.sleep(0.5)
    
    logger.info(f"Looking for markers file at {MARKERS_FILE}")
    
    if not os.path.exists(MARKERS_FILE):
        logger.warning(f"Markers file {MARKERS_FILE} does not exist, waiting for it to be created...")
        
        # Wait for the file to be created with timeout
        start_time = time.time()
        while not stop_event.is_set() and not os.path.exists(MARKERS_FILE):
            time.sleep(0.1)
            if time.time() - start_time > 5.0:  # 5 second timeout
                logger.error(f"Timed out waiting for markers file: {MARKERS_FILE}")
                # Create an empty file to allow processing to continue
                try:
                    with open(MARKERS_FILE, 'w') as f:
                        f.write("Starting recording\n")
                    logger.info(f"Created empty markers file at {MARKERS_FILE}")
                except Exception as e:
                    logger.error(f"Failed to create empty markers file: {e}")
                    return
    
    if stop_event.is_set():
        return
    
    logger.info(f"Found markers file: {MARKERS_FILE}")
    
    # Check if file is readable
    try:
        with open(MARKERS_FILE, 'r') as f:
            first_line = f.readline().strip()
            logger.debug(f"First line of markers file: {first_line}")
    except Exception as e:
        logger.error(f"Error reading markers file: {e}")
        return
    
    # Keep track of the last read position
    last_pos = 0
    last_frame = 0
    check_count = 0
    last_check_time = time.time()
    processed_frames = 0
    
    logger.info("Starting to monitor markers file for frame data")
    
    while not stop_event.is_set():
        try:
            # Check if file exists
            if not os.path.exists(MARKERS_FILE):
                logger.warning("Markers file disappeared, waiting for it to reappear...")
                time.sleep(0.5)
                continue
                
            # Try to read new content with error handling
            try:
                with open(MARKERS_FILE, 'r') as f:
                    # Go to last read position
                    f.seek(last_pos)
                    
                    # Read new content
                    new_lines = f.readlines()
                    current_pos = f.tell()
                    
                    # If nothing new was read but it's been a while since we saw new data
                    if not new_lines and time.time() - last_check_time > 2.0:
                        check_count += 1
                        if check_count % 5 == 0:
                            logger.debug(f"No new lines in markers file for {int(time.time() - last_check_time)}s, checking file size: {current_pos} bytes")
                            
                            # Check file content from the beginning if needed
                            if len(lsl_data) == 0 and current_pos > 0:
                                logger.debug("No LSL data collected yet, reading file from beginning")
                                f.seek(0)
                                new_lines = f.readlines()
                                current_pos = f.tell()
                                last_pos = 0
                            # Check if file has grown but our position is incorrect
                            elif current_pos > last_pos + 100:
                                logger.warning(f"File has grown significantly but no new lines detected, resetting position")
                                last_pos = 0
                                continue
                    
                    # Update last position if we read anything
                    if new_lines:
                        last_pos = current_pos
                        last_check_time = time.time()
                        check_count = 0
                        
                        for line in new_lines:
                            line = line.strip()
                            if not line or line.startswith("Starting") or "Recording" in line:
                                continue
                                
                            # Parse frame number and timestamp
                            try:
                                parts = line.split()
                                if len(parts) >= 2:
                                    # Check if the first part looks like a frame number
                                    try:
                                        frame_num = int(parts[0])
                                        
                                        # Check if the second part looks like a timestamp
                                        try:
                                            frame_time = float(parts[1])
                                            
                                            # Only push if this is a new frame
                                            if frame_num > last_frame or frame_time > time.time() - 60:
                                                push_lsl_sample(frame_num, frame_time)
                                                last_frame = frame_num
                                                processed_frames += 1
                                                if processed_frames % 50 == 0:
                                                    logger.debug(f"Processed {processed_frames} frames, latest: Frame {frame_num}, Time {frame_time}")
                                        except ValueError:
                                            # Second part is not a float timestamp
                                            logger.debug(f"Invalid timestamp in line: {line}")
                                    except ValueError:
                                        # First part is not an integer - try other formats
                                        logger.debug(f"Non-numeric frame number in line: {line}")
                            except ValueError as e:
                                logger.debug(f"Error parsing line '{line}': {e}")
            except Exception as e:
                logger.warning(f"Error reading markers file: {e}")
                time.sleep(0.1)
                continue
            
            # Short sleep before checking for new lines
            time.sleep(0.01)
            
        except Exception as e:
            logger.warning(f"Error monitoring markers file: {e}")
            time.sleep(0.5)
    
    logger.info(f"Stopped monitoring markers file after processing {processed_frames} frames")

def monitor_pts_file(pts_file="/dev/shm/tst.pts"):
    """Directly monitor the PTS file for frame timestamps"""
    global stop_event, lsl_data
    
    logger.info(f"Starting to monitor PTS file: {pts_file}")
    
    if not os.path.exists(pts_file):
        logger.warning(f"PTS file {pts_file} does not exist yet, waiting...")
        
    last_pos = 0
    last_frame = 0
    
    while not stop_event.is_set():
        # Check if file exists yet
        if not os.path.exists(pts_file):
            time.sleep(0.1)
            continue
            
        try:
            with open(pts_file, 'r') as f:
                f.seek(last_pos)
                new_lines = f.readlines()
                
                if new_lines:
                    last_pos = f.tell()
                    
                    for line in new_lines:
                        line = line.strip()
                        if not line:
                            continue
                            
                        # PTS files typically have format like: "42: 1684567890.123456"
                        if ':' in line:
                            try:
                                parts = line.split(':', 1)
                                frame_num = int(parts[0].strip())
                                timestamp = float(parts[1].strip())
                                
                                if frame_num > last_frame:
                                    push_lsl_sample(frame_num, timestamp)
                                    last_frame = frame_num
                                    logger.debug(f"Pushed LSL sample from PTS: Frame {frame_num}, Time {timestamp}")
                            except (ValueError, IndexError) as e:
                                logger.debug(f"Error parsing PTS line '{line}': {e}")
        except Exception as e:
            logger.warning(f"Error reading PTS file: {e}")
            
        time.sleep(0.01)
    
    logger.info("Stopped monitoring PTS file")

def run_gscrop_script(width, height, fps, duration_ms, exposure_us=None, output_path=None, preview=False, no_awb=False):
    """Run the GScrop shell script to capture video"""
    global camera_process, stop_event
    
    # Build command line arguments - use exact duration as requested
    cmd = ["./GScrop", str(width), str(height), str(fps), str(duration_ms)]
    
    # Add exposure if specified
    if exposure_us is not None:
        cmd.append(str(exposure_us))
    
    # Add output path if specified
    if output_path is not None:
        cmd.append(output_path)
    
    # Add environment variables for camera selection
    env = os.environ.copy()
    
    # Add cam1 if using second camera
    if os.environ.get("cam1"):
        env["cam1"] = "1"
    
    # Add narrow mode if requested
    if preview:
        env["narrow"] = "1"
        
    # Set no AWB flag if requested
    if no_awb:
        env["no_awb"] = "1"
    
    logger.info(f"Starting GScrop with command: {' '.join(cmd)}")
    
    try:
        # Start the GScrop script
        camera_process = subprocess.Popen(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0  # Unbuffered output
        )
        
        # Start threads to monitor stdout and stderr
        threading.Thread(target=monitor_process_output, args=(camera_process.stdout, "stdout"), daemon=True).start()
        threading.Thread(target=monitor_process_output, args=(camera_process.stderr, "stderr"), daemon=True).start()
        
        return camera_process
    except Exception as e:
        logger.error(f"Failed to start GScrop script: {e}")
        return None

def monitor_process_output(pipe, name):
    """Monitor a process output pipe and log the results"""
    if pipe is None:
        logger.warning(f"No {name} pipe to monitor")
        return
        
    for line in iter(pipe.readline, b''):
        if stop_event.is_set():
            break
        
        line_str = line.decode().strip()
        if not line_str:
            continue
        
        # Log the output based on content
        if "error" in line_str.lower() or "ERROR" in line_str:
            logger.error(f"GScrop {name}: {line_str}")
        elif "warning" in line_str.lower() or "WARNING" in line_str:
            logger.warning(f"GScrop {name}: {line_str}")
        else:
            logger.debug(f"GScrop {name}: {line_str}")
            
    logger.debug(f"End of {name} pipe monitoring")

def validate_camera_config(width, height, fps):
    """
    Validate if the requested camera configuration is likely to work
    Returns a tuple of (is_valid, message)
    """
    # Known limitations of IMX296 global shutter camera
    max_res_product = 1440 * 1080  # Maximum pixel count
    max_data_rate = 1920 * 1080 * 60  # Approx maximum data rate (1080p @ 60fps)
    max_high_fps = 120  # Maximum FPS for standard operation
    
    # Current configuration's metrics
    res_product = width * height
    data_rate = width * height * fps
    
    # Valid resolution check (must be <= max supported by IMX296)
    if width > 1440 or height > 1080:
        return False, f"Resolution {width}x{height} exceeds camera maximum dimensions (1440x1080)"
    
    # Valid resolution product check
    if res_product > max_res_product:
        return False, f"Resolution {width}x{height} exceeds camera capability ({res_product} > {max_res_product} pixels)"
    
    # Check if data rate is excessive
    if data_rate > max_data_rate:
        if fps > max_high_fps:
            # If FPS is very high, suggest lower resolution
            suggested_width = int(((max_data_rate / fps) ** 0.5) // 2) * 2  # Even number
            suggested_height = suggested_width
            return False, (f"Resolution {width}x{height} at {fps}fps exceeds camera data rate capability. "
                          f"For {fps}fps, try {suggested_width}x{suggested_height} or lower.")
        else:
            # If resolution is very high, suggest lower FPS
            suggested_fps = max(30, int(max_data_rate / res_product))
            return False, (f"Resolution {width}x{height} at {fps}fps exceeds camera data rate capability. "
                          f"For this resolution, try {suggested_fps}fps or lower.")
    
    # Check for extreme high-speed modes
    if fps > 200:
        max_res_for_fps = int(((max_data_rate / fps) ** 0.5) // 2) * 2
        return False, f"FPS {fps} is too high. Maximum supported is ~200fps at low resolutions (try {max_res_for_fps}x{max_res_for_fps} or lower)."
    
    # Specific validation for common issues
    if width > 640 and fps > 120:
        suggested_fps = 120
        suggested_width = 640 if width > 640 else width
        suggested_height = 640 if height > 640 else height
        return False, f"Resolution {width}x{height} at {fps}fps may be unstable. Try {suggested_width}x{suggested_height} at {suggested_fps}fps."
    
    # Recommended configurations based on experience
    recommended_configs = [
        (400, 400, 100),  # Good balance for 100fps
        (640, 480, 90),   # Standard VGA
        (800, 600, 60),   # SVGA
        (320, 240, 200),  # Low-res high speed
    ]
    
    return True, "Configuration appears to be within camera capabilities"

def main():
    """Main function"""
    global lsl_outlet, stop_event, lsl_data, MARKERS_FILE

    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Parse command line arguments
    parser = argparse.ArgumentParser(description='IMX296 Camera Recorder with LSL using GScrop script')
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
    parser.add_argument('--verbose', action='store_true', help='Enable verbose logging')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode with extensive logging')
    parser.add_argument('--test-markers', action='store_true', help='Test markers file creation and monitoring')
    parser.add_argument('--no-awb', action='store_true', help='Disable AWB (Auto White Balance) adjustments')
    parser.add_argument('--direct-pts', action='store_true', help='Directly use PTS file for frame timing if available')
    parser.add_argument('--force', action='store_true', help='Force camera configuration even if it might not work')
    args = parser.parse_args()
    
    # Convert duration from seconds to milliseconds
    duration_ms = int(args.duration * 1000) if args.duration > 0 else 0
    
    # Set up logging level
    if args.debug:
        logger.setLevel(logging.DEBUG)
        logger.info("Debug logging enabled")
    elif args.verbose:
        logger.setLevel(logging.INFO)
        logger.info("Verbose logging enabled")
    
    # Check if running on Windows or Linux
    is_windows = sys.platform.startswith('win')
    if is_windows:
        logger.warning("Running on Windows - some features may not work properly")
    
    # Check file system permissions
    if not is_windows:
        try:
            # Check if /dev/shm exists and is writable
            if not os.path.exists('/dev/shm'):
                logger.error("/dev/shm directory not found - may be missing or not mounted")
            elif not os.access('/dev/shm', os.W_OK):
                logger.error("/dev/shm directory is not writable - check permissions")
            else:
                logger.debug("/dev/shm directory exists and is writable")
                
            # Try to create and remove a test file
            test_file = '/dev/shm/test_file'
            with open(test_file, 'w') as f:
                f.write('test')
            os.unlink(test_file)
            logger.debug("Successfully created and removed test file in /dev/shm")
        except Exception as e:
            logger.warning(f"File system permission check failed: {e}")
    
    # Test markers file if requested
    if args.test_markers:
        logger.info("Testing markers file creation and monitoring")
        try:
            with open(MARKERS_FILE, 'w') as f:
                f.write("Starting recording\n")
                f.write("1 1684567890.123456\n")
                f.write("2 1684567890.234567\n")
            logger.info(f"Created test markers file at {MARKERS_FILE}")
            
            # Start monitoring in a thread
            monitor_thread = threading.Thread(target=monitor_markers_file, daemon=True)
            monitor_thread.start()
            
            # Append more data to the file
            time.sleep(1)
            with open(MARKERS_FILE, 'a') as f:
                f.write("3 1684567890.345678\n")
            
            # Wait for monitoring to process
            time.sleep(1)
            stop_event.set()
            monitor_thread.join(timeout=2)
            
            logger.info(f"Test complete, collected {len(lsl_data)} LSL data points")
            return 0
        except Exception as e:
            logger.error(f"Test failed: {e}")
            return 1
    
    # Log all arguments
    logger.debug(f"Command line arguments: {vars(args)}")
    logger.debug(f"Duration in milliseconds: {duration_ms}")

    # Check if width and height are even numbers
    if not check_even_dimensions(args.width, args.height):
        return 1
    
    # Validate camera configuration
    if not args.force:
        is_valid, message = validate_camera_config(args.width, args.height, args.fps)
        if not is_valid:
            logger.error(f"Invalid camera configuration: {message}")
            logger.error("Use --force to try anyway, or adjust settings to a supported configuration")
            logger.info("Recommended configurations:")
            logger.info("  400x400 @ 100fps (balanced)")
            logger.info("  640x480 @ 90fps (standard)")
            logger.info("  320x240 @ 200fps (high speed)")
            return 1
        else:
            logger.info(message)
         
    # Validate recording duration
    if duration_ms <= 0:
        logger.info("No duration specified, will record until interrupted")
    elif duration_ms < 1000:
        logger.warning(f"Very short duration specified ({args.duration} seconds). Consider increasing for better results.")
    
    # Check if FPS is reasonable
    if args.fps > 120:
        logger.warning(f"High FPS requested ({args.fps}). The camera might not achieve this rate.")
        logger.warning("Consider reducing resolution for better high-FPS performance.")
    
    # Set camera selection environment variable if needed
    if args.cam1:
        os.environ["cam1"] = "1"
        logger.info("Using camera 1")
    
    # Check if GScrop script exists and is executable
    if not os.path.isfile("./GScrop"):
        logger.error("GScrop script not found in current directory")
        return 1
    
    if not os.access("./GScrop", os.X_OK):
        logger.warning("GScrop script is not executable, trying to make it executable")
        try:
            os.chmod("./GScrop", 0o755)
            logger.info("Made GScrop executable")
        except Exception as e:
            logger.error(f"Could not make GScrop executable: {e}")
            return 1
    
    # Create LSL outlet
    if LSL_AVAILABLE:
        lsl_outlet = create_lsl_outlet(name=args.lsl_name, stream_type=args.lsl_type, fps=args.fps)
    
    # Create dated output directory
    output_dir = create_output_directory()
    logger.info(f"Using output directory: {output_dir}")
    
    # Generate output filenames
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    cam_suffix = "1" if args.cam1 else ""
    
    # Determine video output path (used by GScrop)
    output_base = f"recording{cam_suffix}_{args.width}x{args.height}_{args.fps}fps_{timestamp}"
    video_path = str(output_dir / output_base)
    
    # If user specified an output path, use that instead
    if args.output:
        video_path = args.output
    
    # Reset LSL data collector
    lsl_data = []
    
    # Calculate appropriate exposure time if not specified
    exposure = args.exposure
    if exposure is None:
        # Default exposure: try to balance frame rate and exposure
        if args.fps > 60:
            # For high FPS, use shorter exposure
            exposure = int(min(1000000 / args.fps * 0.8, 10000))
            if args.fps > 100:
                # For very high FPS, need even shorter exposure
                exposure = int(min(1000000 / args.fps * 0.5, 5000))
            logger.info(f"Automatically setting exposure to {exposure}µs for high FPS")
        else:
            exposure = 10000  # Default exposure for lower FPS
    
    recording_successful = False
    try:
        # Start camera using GScrop script
        logger.info(f"Starting recording to {video_path}")
        
        camera_proc = run_gscrop_script(
            args.width, args.height, args.fps,
            duration_ms, exposure, video_path,
            preview=args.preview,
            no_awb=args.no_awb
        )
        
        if not camera_proc:
            logger.error("Failed to start GScrop script")
            return 1
            
        # Start markers file monitoring thread - EXPLICITLY ON NEW THREAD
        logger.info("Starting markers file monitoring on separate thread")
        markers_thread = threading.Thread(target=monitor_markers_file, daemon=True)
        markers_thread.start()
        
        # Start PTS monitoring if requested - also on separate thread
        pts_thread = None
        if args.direct_pts:
            logger.info("Starting PTS file monitoring on separate thread")
            pts_thread = threading.Thread(target=monitor_pts_file, daemon=True)
            pts_thread.start()
            logger.info("Started direct PTS file monitoring")
        
        # Wait for camera process to finish or Ctrl+C
        logger.info(f"Recording started with duration: {args.duration} seconds. Press Ctrl+C to stop earlier.")
        
        # Monitor LSL data collection
        frames_count = 0
        last_report_time = time.time()
        start_time = time.time()
        
        # Give the threads more time to establish and start collecting data
        time.sleep(1.0)
        
        # Wait for recording to complete
        while camera_proc.poll() is None and not stop_event.is_set():
            current_time = time.time()
            
            # Sleep briefly
            time.sleep(0.1)
            
            # Periodically report frame count
            if current_time - last_report_time >= 2.0:
                current_frames = len(lsl_data)
                new_frames = current_frames - frames_count
                elapsed = current_time - last_report_time
                fps_rate = new_frames / elapsed if elapsed > 0 else 0
                
                # Calculate expected frames vs actual
                total_elapsed = current_time - start_time
                expected_frames = int(total_elapsed * args.fps)
                
                logger.info(f"Current frame rate: {fps_rate:.1f} FPS ({new_frames} frames in {elapsed:.1f}s)")
                
                if expected_frames > 0 and current_frames > 0:
                    capture_ratio = current_frames / expected_frames
                    logger.info(f"Capture ratio: {capture_ratio:.2f} ({current_frames}/{expected_frames} frames)")
                    
                    # Alert if we're capturing too few frames
                    if capture_ratio < 0.5 and current_time - start_time > 3:
                        logger.warning(f"Low capture ratio detected: {capture_ratio:.2f}. Check system performance.")
                
                if args.debug and new_frames == 0 and current_frames == 0:
                    logger.debug("No frames detected, checking markers file...")
                    if os.path.exists(MARKERS_FILE):
                        try:
                            with open(MARKERS_FILE, 'r') as f:
                                content = f.read()
                                logger.debug(f"Markers file content ({len(content)} bytes):\n{content[:500]}...")
                        except Exception as e:
                            logger.debug(f"Error reading markers file: {e}")
                    
                    # Also check PTS file
                    pts_file = "/dev/shm/tst.pts"
                    if os.path.exists(pts_file):
                        try:
                            with open(pts_file, 'r') as f:
                                content = f.read()
                                logger.debug(f"PTS file content ({len(content)} bytes):\n{content[:500]}...")
                        except Exception as e:
                            logger.debug(f"Error reading PTS file: {e}")
                
                frames_count = current_frames
                last_report_time = current_time
        
        # Check exit code
        exit_code = camera_proc.returncode if camera_proc.poll() is not None else 0
        if exit_code == 0:
            logger.info("GScrop script completed successfully")
            recording_successful = True
        else:
            logger.error(f"GScrop script exited with error code: {exit_code}")
            
    except KeyboardInterrupt:
        logger.info("Recording stopped by user")
    except Exception as e:
        logger.error(f"Error during recording: {e}")
    finally:
        # Cleanup
        stop_event.set()
        
        if camera_process and camera_process.poll() is None:
            logger.info("Terminating camera process...")
            camera_process.terminate()
            try:
                camera_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                camera_process.kill()
                
        # Wait for threads to finish
        logger.info("Waiting for monitoring threads to finish...")
        time.sleep(1)
        
        # Report data collection statistics
        if lsl_data:
            logger.info(f"Frames captured: {len(lsl_data)}")
            
            # Check frame numbers
            if len(lsl_data) > 1:
                first_frame = int(lsl_data[0][1])
                last_frame = int(lsl_data[-1][1])
                frame_count = len(lsl_data)
                logger.info(f"Frame range: {first_frame} to {last_frame} ({frame_count} frames)")
                
                # Analyze frame timestamps
                first_ts = float(lsl_data[0][0])
                last_ts = float(lsl_data[-1][0])
                captured_duration = last_ts - first_ts
                logger.info(f"Captured duration: {captured_duration:.3f}s")
                
                if captured_duration > 0:
                    actual_fps = frame_count / captured_duration
                    expected_fps = args.fps
                    logger.info(f"Actual FPS: {actual_fps:.2f} (target: {expected_fps})")
            
            # Check for expected video files
            try:
                expected_video = f"{video_path}.mp4" if os.environ.get("cam1") or (os.path.exists("/proc/cpuinfo") and "Revision.*: ...17.$" in open("/proc/cpuinfo").read()) else f"{video_path}.h264"
                if os.path.exists(expected_video):
                    video_size = os.path.getsize(expected_video)
                    logger.info(f"Video file created: {expected_video} ({video_size} bytes)")
                    if video_size < 1000:
                        logger.warning("Video file is very small! Recording may have failed.")
                else:
                    # Try the other extension
                    alt_video = f"{video_path}.h264" if os.environ.get("cam1") or (os.path.exists("/proc/cpuinfo") and "Revision.*: ...17.$" in open("/proc/cpuinfo").read()) else f"{video_path}.mp4"
                    if os.path.exists(alt_video):
                        video_size = os.path.getsize(alt_video)
                        logger.info(f"Video file created: {alt_video} ({video_size} bytes)")
                    else:
                        logger.warning(f"No video file was created at {video_path}.[mp4/h264]")
            except Exception as e:
                logger.warning(f"Error checking video file: {e}")
        else:
            logger.warning("No LSL data was collected during recording")
            
            # Check if markers file exists and has content
            if os.path.exists(MARKERS_FILE):
                try:
                    with open(MARKERS_FILE, 'r') as f:
                        content = f.read().strip()
                        if content:
                            logger.info(f"Markers file exists with {len(content.splitlines())} lines but no LSL data was processed")
                        else:
                            logger.warning("Markers file exists but is empty")
                except Exception as e:
                    logger.error(f"Error reading markers file: {e}")
            else:
                logger.error("Markers file was not created")
    
    if recording_successful:
        logger.info("Recording completed successfully")
    else:
        logger.warning("Recording may not have completed successfully")
        
    return 0 if recording_successful else 1

if __name__ == "__main__":
    sys.exit(main()) 