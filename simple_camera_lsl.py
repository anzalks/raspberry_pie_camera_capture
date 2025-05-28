#!/usr/bin/env python3
"""
Simplified IMX296 Camera Recorder with LSL
------------------------------------------
This script uses GScrop shell script to configure and record from an IMX296 global shutter camera
on Raspberry Pi, streams metadata via LSL, and saves video to a local file.
Author: Anzal KS (anzal.ks@gmail.com)
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
from queue import Queue, Empty

# Optional import of pylsl - we'll check this later
try:
    import pylsl
    LSL_AVAILABLE = True
except ImportError:
    LSL_AVAILABLE = False
    print("Warning: pylsl not installed. LSL streaming will be disabled.")
    print("HINT: Run 'source ./setup_lsl_env.sh' and ensure liblsl is properly installed")

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
total_frames_captured = 0  # Track actual frames captured by camera

# Dynamic markers file detection (no sudo required)
def get_markers_file():
    """Get the appropriate markers file path using local output directory"""
    import os
    
    # Use local output directory instead of system paths
    output_dir = "./output"
    os.makedirs(output_dir, exist_ok=True)
    return os.path.join(output_dir, "camera_markers.txt")

MARKERS_FILE = get_markers_file()

# Queue for frame data processing
frame_queue = Queue()  # Unlimited capacity queue - never drop frames

def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully"""
    logger.info(f"Received signal {sig}, shutting down...")
    stop_event.set()
    if camera_process and camera_process.poll() is None:
        camera_process.terminate()

def create_lsl_outlet(name="IMX296Camera", stream_type="Video", fps=100):
    """Create LSL outlet for camera metadata - sends only frame numbers with timestamps"""
    if not LSL_AVAILABLE:
        logger.warning("pylsl not available, skipping LSL outlet creation")
        return None
        
    try:
        logger.info(f"Creating LSL outlet: {name}")
        # Create stream info with frame number and precise timing
        info = pylsl.StreamInfo(
            name=name,
            type=stream_type,
            channel_count=1,  # Only frame number
            nominal_srate=fps,  # Match camera frame rate
            channel_format=pylsl.cf_double64,  # Use double precision for frame numbers
            source_id=f"IMX296_{name}_{int(time.time())}"  # Unique source ID
        )
        
        # Add channel description for LabRecorder compatibility
        channels = info.desc().append_child("channels")
        ch = channels.append_child("channel")
        ch.append_child_value("label", "FrameNumber")
        ch.append_child_value("unit", "count")
        ch.append_child_value("type", "Frame")
        
        # Add metadata for better identification in LabRecorder
        desc = info.desc()
        desc.append_child_value("manufacturer", "Anzal_KS")
        desc.append_child_value("model", "IMX296_GlobalShutter")
        desc.append_child_value("version", "1.0")
        
        # Create outlet with minimal buffering for real-time streaming
        outlet = pylsl.StreamOutlet(info, chunk_size=1, max_buffered=0)  # No buffering, real-time only
        logger.info(f"LSL outlet '{name}' created successfully")
        logger.info("IMPORTANT: LSL configured for REAL-TIME streaming - every frame will be sent immediately")
        
        # Log stream specifications for verification
        logger.info(f"LSL Stream Details:")
        logger.info(f"  - Stream name: {name}")
        logger.info(f"  - Stream type: {stream_type}")
        logger.info(f"  - Channels: 1 (FrameNumber)")
        logger.info(f"  - Sample rate: {fps} Hz")
        logger.info(f"  - Data format: float64")
        logger.info(f"  - Buffering: DISABLED (real-time only)")
        logger.info(f"  - Source ID: {info.source_id()}")
        logger.info(f"  - Unique UID: {info.uid()}")
        
        return outlet
    except Exception as e:
        logger.error(f"Failed to create LSL outlet: {e}")
        logger.error(f"Make sure liblsl is properly installed and PYLSL_LIB is set")
        return None

def push_lsl_sample(frame_number, timestamp=None):
    """Push a frame number sample to LSL with precise timestamps"""
    global lsl_outlet, lsl_data
    
    # Use current time for internal statistics only
    if timestamp is None:
        timestamp = time.time()
    
    # Save data internally for statistics (frame_number and our internal timestamp)
    lsl_data.append([timestamp, float(frame_number)])
    
    if lsl_outlet:
        try:
            # Push sample with LSL-generated timestamp for synchronization
            lsl_outlet.push_sample([float(frame_number)])
        except Exception as e:
            logger.error(f"Error pushing LSL sample: {e}")

def lsl_worker_thread():
    """Thread to process frames from the queue and send to LSL"""
    global frame_queue, stop_event
    
    logger.info("LSL worker thread started - processing EVERY frame captured")
    frames_processed = 0
    last_report_time = time.time()
    
    # Simple rolling window for frame rate calculation (last 100 frames)
    frame_window = []  # Store (timestamp, frame_num) tuples
    
    while not stop_event.is_set():
        try:
            # Get frame data from the queue with short timeout
            try:
                frame_data = frame_queue.get(timeout=0.1)
                frame_num, frame_time = frame_data
                
                # Add to rolling window
                frame_window.append((frame_time, frame_num))
                
                # Keep only last 100 frames
                if len(frame_window) > 100:
                    frame_window = frame_window[-100:]
                
                # Push the frame data to LSL
                push_lsl_sample(frame_num, frame_time)
                
                frames_processed += 1
                
                # Report frame rate every 5 seconds
                current_time = time.time()
                if current_time - last_report_time >= 10.0 and len(frame_window) >= 50:
                    # Calculate frame rate from rolling window
                    window_duration = frame_window[-1][0] - frame_window[0][0]
                    window_frames = len(frame_window)
                    
                    if window_duration > 0:
                        current_fps = (window_frames - 1) / window_duration
                        logger.debug(f"LSL processing: {current_fps:.1f} FPS (rolling window)")
                    
                    last_report_time = current_time
                
                # Mark task as done
                frame_queue.task_done()
                
            except Empty:
                # No data in queue, just continue
                pass
                
        except Exception as e:
            logger.error(f"Error in LSL worker thread: {e}")
    
    # Final frame rate calculation
    if len(frame_window) >= 2:
        total_duration = frame_window[-1][0] - frame_window[0][0]
        total_frames = len(frame_window)
        if total_duration > 0:
            final_fps = (total_frames - 1) / total_duration
            logger.debug(f"LSL worker finished: {frames_processed} frames processed, final rate: {final_fps:.1f} FPS")
        else:
            logger.debug(f"LSL worker finished: {frames_processed} frames processed")
    else:
        logger.debug(f"LSL worker finished: {frames_processed} frames processed")
    
    return True  # Always return success

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
    global stop_event, lsl_data, MARKERS_FILE, frame_queue, total_frames_captured
    
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
    
    # Start the LSL worker thread
    lsl_thread = threading.Thread(target=lsl_worker_thread, daemon=True)
    lsl_thread.start()
    
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
                            
                            # Check if file has actually grown
                            try:
                                file_size = os.path.getsize(MARKERS_FILE)
                                logger.debug(f"Markers file size: {file_size} bytes, current position: {current_pos}")
                            except Exception as e:
                                logger.debug(f"Error checking file size: {e}")
                            
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
                                            
                                            # Only process if this is a new frame and not a duplicate
                                            if frame_num > last_frame:
                                                # Add frame to queue - always capture every frame
                                                try:
                                                    queue_frame_data(frame_num, frame_time, source="markers_file")
                                                    last_frame = frame_num
                                                    processed_frames += 1
                                                    total_frames_captured += 1  # Count actual captured frames
                                                    
                                                    if processed_frames % 1000 == 0:
                                                        logger.debug(f"Added {processed_frames} frames to processing queue")
                                                except Exception as e:
                                                    logger.error(f"Failed to queue frame {frame_num}: {e}")
                                                    # Still count as captured since we tried
                                                    total_frames_captured += 1
                                                
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
            
            # Minimal sleep to reduce CPU usage but maintain high responsiveness
            time.sleep(0.001)
            
        except Exception as e:
            logger.warning(f"Error monitoring markers file: {e}")
            time.sleep(0.5)
    
    logger.info(f"Stopped monitoring markers file after processing {processed_frames} frames")
    
    # Wait for the queue to be fully processed
    logger.info("Waiting for LSL queue to be fully processed...")
    try:
        # Wait with timeout in case of very large queues
        frame_queue.join(timeout=5.0)
    except Exception:
        logger.warning(f"LSL queue still has approximately {frame_queue.qsize()} items remaining")

def monitor_pts_file(pts_file=None):
    """Monitor the PTS file created by libcamera for older Pi versions"""
    global stop_event, lsl_data, frame_queue
    
    # Auto-detect PTS file location using local output directory
    if pts_file is None:
        pts_file = "./output/tst.pts"
    
    logger.info(f"Monitoring PTS file: {pts_file}")
    
    # Wait for the PTS file to be created
    start_time = time.time()
    while not stop_event.is_set() and not os.path.exists(pts_file):
        time.sleep(0.1)
        if time.time() - start_time > 10.0:  # 10 second timeout
            logger.warning(f"PTS file {pts_file} not created within timeout")
            return
    
    if stop_event.is_set():
        return
    
    logger.info(f"Found PTS file: {pts_file}")
    
    processed_frames = 0
    
    try:
        with open(pts_file, 'r') as f:
            while not stop_event.is_set():
                line = f.readline()
                if not line:
                    time.sleep(0.001)  # Very short sleep to avoid busy waiting
                    continue
                
                # Parse PTS line format: frame_number timestamp
                parts = line.strip().split()
                if len(parts) >= 2:
                    try:
                        frame_num = int(parts[0])
                        timestamp = float(parts[1])
                        
                        # Add to queue for LSL processing
                        try:
                            queue_frame_data(frame_num, timestamp, source="pts_file")
                            processed_frames += 1
                            
                            if processed_frames % 100 == 0:
                                logger.debug(f"PTS monitor processed {processed_frames} frames")
                        except:
                            # Queue is full, skip this frame
                            pass
                    except (ValueError, IndexError):
                        # Skip invalid lines
                        continue
                
                # Small delay to prevent excessive CPU usage
                time.sleep(0.001)
    
    except Exception as e:
        logger.error(f"Error monitoring PTS file: {e}")
    
    logger.info(f"Stopped monitoring PTS file after processing {processed_frames} frames")

def run_gscrop_script(width, height, fps, duration_ms, exposure_us=None, output_path=None, preview=False, no_awb=False, enable_plot=False):
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
    
    # Enable real-time LSL streaming
    env["STREAM_LSL"] = "1"
    
    # Enable plotting if requested
    if enable_plot:
        env["ENABLE_PLOT"] = "1"
    
    # Add cam1 if using second camera
    if os.environ.get("cam1"):
        env["cam1"] = "1"
    
    # Enable preview if requested
    if preview:
        env["PREVIEW"] = "1"
        
    # Set no AWB flag if requested
    if no_awb:
        env["no_awb"] = "1"
    
    logger.info(f"Starting GScrop with command: {' '.join(cmd)}")
    if enable_plot:
        logger.info("Plot generation enabled")
    
    # Debug output
    logger.debug(f"Environment variables for GScrop:")
    for key, value in env.items():
        if key.startswith(('STREAM_', 'ENABLE_', 'cam', 'PREVIEW', 'no_awb')):
            logger.debug(f"  {key}={value}")
    
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
    """Monitor a process output pipe and log the results, parsing frame data for LSL"""
    global frame_queue, total_frames_captured
    
    if pipe is None:
        logger.warning(f"No {name} pipe to monitor")
        return
    
    frames_processed = 0
    
    for line in iter(pipe.readline, b''):
        if stop_event.is_set():
            break
        
        line_str = line.decode().strip()
        if not line_str:
            continue
        
        # Check for frame data from GScrop
        if line_str.startswith("FRAME_DATA:") and name == "stdout":
            try:
                # Parse FRAME_DATA:frame_num:timestamp format
                parts = line_str.split(":")
                if len(parts) == 3:
                    frame_num = int(parts[1])
                    timestamp = float(parts[2])
                    
                    # Add to queue for LSL processing
                    try:
                        queue_frame_data(frame_num, timestamp, source="process_output")
                        frames_processed += 1
                        total_frames_captured += 1
                        
                        # Remove the frequent debug message
                        # if frames_processed % 100 == 0:
                        #     logger.debug(f"Real-time LSL: processed {frames_processed} frames")
                    except Exception as e:
                        # Log any queue errors but don't drop the frame
                        logger.error(f"Failed to queue frame {frame_num}: {e}")
                        # Still count as captured since we tried
                        total_frames_captured += 1
                        
            except (ValueError, IndexError) as e:
                logger.debug(f"Error parsing frame data: {line_str} - {e}")
            continue
        
        # Log the output based on content (non-frame data)
        if "error" in line_str.lower() or "ERROR" in line_str:
            logger.error(f"GScrop {name}: {line_str}")
        elif "warning" in line_str.lower() or "WARNING" in line_str:
            logger.warning(f"GScrop {name}: {line_str}")
        elif "FRAME_DATA:" not in line_str:  # Don't log frame data as regular output
            logger.debug(f"GScrop {name}: {line_str}")
            
    if frames_processed > 0:
        logger.debug(f"Real-time LSL monitoring finished: processed {frames_processed} frames")
    
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

def check_system_requirements():
    """
    Check system requirements for camera operation (no sudo required)
    Provides helpful guidance if permissions are lacking
    """
    logger.info("Checking system requirements...")
    
    # Check LSL setup first
    check_lsl_setup()
    
    # Check if markers file location is accessible
    markers_dir = os.path.dirname(MARKERS_FILE)
    if os.path.exists(markers_dir) and os.access(markers_dir, os.W_OK):
        logger.debug(f"Markers directory {markers_dir} is accessible and writable")
    else:
        logger.warning(f"Markers directory {markers_dir} may not be accessible")
        logger.info("HINT: All output files are now saved to local './output' directory")
        logger.info("HINT: This avoids permission issues with system directories")
    
    # Test file creation/deletion without sudo
    try:
        test_file = os.path.join(markers_dir, 'test_file_' + str(os.getpid()))
        with open(test_file, 'w') as f:
            f.write('test')
        os.remove(test_file)
        logger.debug(f"Successfully tested file operations in {markers_dir}")
    except Exception as e:
        logger.warning(f"Cannot perform file operations in {markers_dir}: {e}")
        logger.info("HINT: Check directory permissions or disk space")
    
    # Check user groups for camera access
    try:
        import grp
        user_groups = [g.gr_name for g in grp.getgrall() if os.getenv('USER', 'unknown') in g.gr_mem]
        if 'video' in user_groups or 'camera' in user_groups:
            logger.debug("User is in video/camera group - camera access should work")
        else:
            logger.warning("User not in 'video' or 'camera' group - camera access may fail")
            logger.info("HINT: Add user to video group: sudo usermod -a -G video $USER")
            logger.info("HINT: Then logout and login again for changes to take effect")
    except Exception:
        logger.debug("Could not check user groups")
    
    # Check for camera devices (no special permissions needed for listing)
    try:
        video_devices = [f"/dev/video{i}" for i in range(10) if os.path.exists(f"/dev/video{i}")]
        media_devices = [f"/dev/media{i}" for i in range(10) if os.path.exists(f"/dev/media{i}")]
        
        if video_devices:
            logger.debug(f"Found video devices: {video_devices}")
        else:
            logger.warning("No video devices found")
            
        if media_devices:
            logger.debug(f"Found media devices: {media_devices}")
        else:
            logger.warning("No media devices found")
            logger.info("HINT: Ensure camera is connected and drivers loaded")
    except Exception as e:
        logger.warning(f"Could not check for camera devices: {e}")
    
    logger.info("System requirements check completed")

def check_lsl_setup():
    """
    Comprehensive check of LSL installation and setup
    Verifies all components installed by the install script
    """
    logger.info("Checking LSL setup and configuration...")
    
    issues_found = []
    
    # 1. Check if setup_lsl_env.sh exists
    setup_script = "./setup_lsl_env.sh"
    if os.path.exists(setup_script):
        logger.info(f"LSL environment setup script found: {setup_script}")
    else:
        issues_found.append("setup_lsl_env.sh script not found")
        logger.error("LSL environment setup script missing")
        logger.info("HINT: Run the install script: sudo ./install.sh")
    
    # 2. Check PYLSL_LIB environment variable
    pylsl_lib = os.environ.get('PYLSL_LIB')
    if pylsl_lib:
        logger.info(f"PYLSL_LIB environment variable set: {pylsl_lib}")
        # Verify the paths exist
        lib_paths = pylsl_lib.split(':')
        found_libs = []
        for path in lib_paths:
            if os.path.exists(path):
                found_libs.append(path)
        
        if found_libs:
            logger.info(f"Found liblsl libraries: {found_libs}")
        else:
            issues_found.append("PYLSL_LIB paths do not exist")
            logger.warning("PYLSL_LIB set but no libraries found at specified paths")
    else:
        issues_found.append("PYLSL_LIB environment variable not set")
        logger.warning("PYLSL_LIB environment variable not set")
        logger.info("HINT: Run 'source ./setup_lsl_env.sh' before using LSL")
    
    # 3. Check LD_LIBRARY_PATH
    ld_lib_path = os.environ.get('LD_LIBRARY_PATH', '')
    if '/usr/local/lib' in ld_lib_path:
        logger.info("LD_LIBRARY_PATH includes /usr/local/lib")
    else:
        issues_found.append("LD_LIBRARY_PATH missing /usr/local/lib")
        logger.warning("LD_LIBRARY_PATH does not include /usr/local/lib")
        logger.info("HINT: Run 'source ./setup_lsl_env.sh' to set library paths")
    
    # 4. Check for liblsl library files
    lib_locations = [
        "/usr/local/lib/liblsl.so",
        "/usr/local/lib64/liblsl.so",
        "/usr/local/lib/liblsl.so.1.16",
        "/usr/local/lib64/liblsl.so.1.16"
    ]
    
    found_liblsl = []
    for lib_path in lib_locations:
        if os.path.exists(lib_path):
            found_liblsl.append(lib_path)
    
    if found_liblsl:
        logger.info(f"Found liblsl libraries: {found_liblsl}")
    else:
        issues_found.append("liblsl library not found")
        logger.error("liblsl library not found in standard locations")
        logger.info("HINT: Run install script to build liblsl: sudo ./install.sh")
    
    # 5. Check pylsl import
    if LSL_AVAILABLE:
        logger.info("pylsl module imported successfully")
        
        # Test basic LSL functionality
        try:
            # Test library version
            version = pylsl.library_version()
            logger.info(f"LSL library version: {version}")
            
            # Test creating a basic stream info
            test_info = pylsl.StreamInfo("test", "test", 1, 100, pylsl.cf_float32, "test")
            logger.info("LSL StreamInfo creation test: PASSED")
            
            # Test creating an outlet (don't keep it)
            test_outlet = pylsl.StreamOutlet(test_info)
            del test_outlet  # Clean up immediately
            logger.info("LSL StreamOutlet creation test: PASSED")
            
        except Exception as e:
            issues_found.append(f"LSL functionality test failed: {e}")
            logger.error(f"LSL functionality test failed: {e}")
    else:
        issues_found.append("pylsl module not available")
        logger.error("pylsl module not available")
        if found_liblsl:
            logger.info("HINT: liblsl found but pylsl import failed - check virtual environment")
            logger.info("HINT: Activate venv and reinstall: pip install pylsl")
        else:
            logger.info("HINT: Run install script first: sudo ./install.sh")
    
    # 6. Check virtual environment
    venv_path = "./venv"
    if os.path.exists(venv_path):
        logger.info(f"Virtual environment found: {venv_path}")
        
        # Check if we're in the virtual environment
        if sys.prefix != sys.base_prefix:
            logger.info("Currently running in virtual environment")
        else:
            issues_found.append("Not running in virtual environment")
            logger.warning("Not running in virtual environment")
            logger.info("HINT: Activate with: source venv/bin/activate")
    else:
        issues_found.append("Virtual environment not found")
        logger.error("Virtual environment not found")
        logger.info("HINT: Run install script: sudo ./install.sh")
    
    # Summary
    if issues_found:
        logger.warning(f"LSL setup issues found ({len(issues_found)}):")
        for i, issue in enumerate(issues_found, 1):
            logger.warning(f"  {i}. {issue}")
        logger.warning("LSL streaming may not work properly")
        logger.info("Recommended fix steps:")
        logger.info("  1. Run: sudo ./install.sh")
        logger.info("  2. Run: source ./setup_lsl_env.sh")
        logger.info("  3. Run: source venv/bin/activate")
    else:
        logger.info("LSL setup verification: ALL CHECKS PASSED")
        logger.info("LSL streaming should work properly")
    
    return len(issues_found) == 0

def queue_frame_data(frame_num, frame_time, source="unknown"):
    """Queue frame data for LSL processing"""
    global frame_queue
    
    if not frame_queue:
        logger.debug(f"No frame queue available - frame {frame_num} from {source} not queued")
        return
    
    try:
        # Simply queue the frame data
        frame_queue.put((frame_num, frame_time), block=True)
        
        # Periodic debug logging (every 100 frames) to avoid spam
        if frame_num % 100 == 0:
            logger.debug(f"Queued frame {frame_num} from {source} (queue size: {frame_queue.qsize()})")
    except Exception as e:
        logger.error(f"Failed to queue frame {frame_num} from {source}: {e}")

def generate_post_recording_plot(video_path, lsl_data):
    """Generate frame timing plot after recording is complete"""
    try:
        import matplotlib.pyplot as plt
        import numpy as np
        
        if not lsl_data or len(lsl_data) < 2:
            logger.warning("Insufficient data for plot generation")
            return False
        
        # Extract timestamps and frame numbers
        timestamps = [float(data[0]) for data in lsl_data]
        frame_numbers = [int(data[1]) for data in lsl_data]
        
        # Calculate frame intervals
        intervals = []
        for i in range(1, len(timestamps)):
            interval = timestamps[i] - timestamps[i-1]
            intervals.append(interval * 1000)  # Convert to milliseconds
        
        # Create plot filename using same base as video
        plot_path = f"{video_path}_timing.png"
        
        # Create the plot
        plt.figure(figsize=(12, 8))
        
        # Plot 1: Frame intervals over time
        plt.subplot(2, 1, 1)
        plt.plot(frame_numbers[1:], intervals, 'b-', alpha=0.7, linewidth=1)
        plt.ylabel('Frame Interval (ms)')
        plt.title(f'Frame Timing Analysis - {len(lsl_data)} frames captured')
        plt.grid(True, alpha=0.3)
        
        # Add statistics
        if intervals:
            mean_interval = np.mean(intervals)
            std_interval = np.std(intervals)
            min_interval = np.min(intervals)
            max_interval = np.max(intervals)
            
            plt.axhline(y=mean_interval, color='r', linestyle='--', alpha=0.7, 
                       label=f'Mean: {mean_interval:.2f}ms')
            plt.legend()
        
        # Plot 2: Histogram of frame intervals
        plt.subplot(2, 1, 2)
        if intervals:
            plt.hist(intervals, bins=50, alpha=0.7, color='green', edgecolor='black')
            plt.xlabel('Frame Interval (ms)')
            plt.ylabel('Count')
            plt.title('Frame Interval Distribution')
            plt.grid(True, alpha=0.3)
            
            # Add statistics text
            stats_text = f'Mean: {mean_interval:.2f}ms\nStd: {std_interval:.2f}ms\nMin: {min_interval:.2f}ms\nMax: {max_interval:.2f}ms'
            plt.text(0.02, 0.98, stats_text, transform=plt.gca().transAxes, 
                    verticalalignment='top', bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
        
        plt.tight_layout()
        
        # Save the plot
        plt.savefig(plot_path, dpi=300, bbox_inches='tight')
        plt.close()  # Close to free memory
        
        logger.info(f"Timing plot saved: {plot_path}")
        return True
        
    except ImportError:
        logger.error("matplotlib not available for plot generation")
        return False
    except Exception as e:
        logger.error(f"Error generating plot: {e}")
        return False

def main():
    """Main function"""
    global lsl_outlet, stop_event, lsl_data, MARKERS_FILE, frame_queue

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
    parser.add_argument('--queue-size', type=int, default=10000, help='Size of the frame processing queue (default: 10000)')
    parser.add_argument('--plot', action='store_true', help='Enable plotting of frame data')
    args = parser.parse_args()
    
    # Update queue size if specified
    if args.queue_size > 0:
        frame_queue = Queue(maxsize=args.queue_size)
    
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
    
    # Check system requirements
    check_system_requirements()
    
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
        logger.info(f"High FPS requested ({args.fps}). Using multithreaded processing for best performance.")
    
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
    
    # Ensure the output directory exists
    output_parent_dir = os.path.dirname(video_path)
    if output_parent_dir and not os.path.exists(output_parent_dir):
        os.makedirs(output_parent_dir, exist_ok=True)
        logger.info(f"Created output directory: {output_parent_dir}")
    
    # Reset LSL data collector
    lsl_data = []
    total_frames_captured = 0  # Reset frame counter
    
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
            no_awb=args.no_awb,
            enable_plot=args.plot
        )
        
        if not camera_proc:
            logger.error("Failed to start GScrop script")
            return 1
            
        # Store the camera process globally for signal handling
        global camera_process
        camera_process = camera_proc
            
        # Start LSL worker thread for real-time processing
        if LSL_AVAILABLE and lsl_outlet:
            logger.info("LSL worker thread for real-time frame processing")
            lsl_thread = threading.Thread(target=lsl_worker_thread, daemon=True)
            lsl_thread.start()
        else:
            logger.warning("LSL not available - frame data will not be streamed")
        
        # IMPORTANT: Start markers file monitoring thread for traditional mode support
        # This acts as a fallback for when STREAM_LSL mode doesn't work properly
        markers_thread = None
        if not args.direct_pts:  # Only start if not using PTS monitoring
            logger.info("Starting markers file monitoring thread (fallback mode)")
            markers_thread = threading.Thread(target=monitor_markers_file, daemon=True)
            markers_thread.start()
        
        # Start PTS monitoring if requested (legacy support)
        pts_thread = None
        if args.direct_pts:
            logger.info("Starting PTS file monitoring on separate thread")
            pts_thread = threading.Thread(target=monitor_pts_file, daemon=True)
            pts_thread.start()
            logger.info("Started direct PTS file monitoring")
        
        # Wait for camera process to finish or Ctrl+C
        logger.info(f"Recording started with duration: {args.duration} seconds. Press Ctrl+C to stop earlier.")
        if LSL_AVAILABLE and lsl_outlet:
            logger.info("Real-time LSL streaming enabled - frame data will be streamed as it's captured")
        else:
            logger.warning("LSL streaming not available - only video recording")
        
        # Monitor LSL data collection
        last_report_time = time.time()
        start_time = time.time()
        last_frame_count = 0
        
        # Wait for recording to complete
        while camera_proc.poll() is None and not stop_event.is_set():
            current_time = time.time()
            
            # Sleep briefly
            time.sleep(0.1)
            
            # Report capture frame rate every 5 seconds
            if current_time - last_report_time >= 5.0:
                # Use LSL data length as the most reliable frame counter
                current_frames = len(lsl_data)  # Frames actually processed and sent to LSL
                new_frames = current_frames - last_frame_count
                elapsed = current_time - last_report_time
                total_elapsed = current_time - start_time
                
                # Debug: Check different frame counters
                lsl_frames = len(lsl_data)
                queue_size = frame_queue.qsize()
                logger.debug(f"Frame counters - LSL: {lsl_frames}, Queue: {queue_size}, total_frames_captured: {total_frames_captured}")
                
                if new_frames > 0 and elapsed > 0:
                    # Show instantaneous rate for this 5-second window
                    capture_fps = new_frames / elapsed
                    logger.info(f"Capture rate: {capture_fps:.1f} FPS")
                elif total_elapsed > 0 and current_frames > 0:
                    # Show average rate if no frames in this window
                    avg_fps = current_frames / total_elapsed
                    logger.info(f"Capture rate: {avg_fps:.1f} FPS (average)")
                else:
                    # Show that we're still waiting for frames
                    logger.info(f"Capture rate: waiting for frames... ({current_frames} total)")
                
                last_frame_count = current_frames
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
                    logger.info(f"Final capture rate: {actual_fps:.2f} FPS (target: {expected_fps} FPS)")
                    
                    # Show performance summary
                    if actual_fps < expected_fps * 0.8:
                        logger.warning(f"Capture rate significantly below target: {actual_fps:.1f} < {expected_fps} FPS")
                    elif actual_fps > expected_fps * 1.2:
                        logger.info(f"Capture rate above target: {actual_fps:.1f} > {expected_fps} FPS") 
                    else:
                        logger.info(f"Capture rate within target range: {actual_fps:.1f} FPS")
            
            # Check for expected video files
            try:
                # Determine file extension based on camera type
                is_newer_pi = os.path.exists("/proc/cpuinfo") and "Revision.*: ...17.$" in open("/proc/cpuinfo").read()
                expected_extension = ".mp4" if is_newer_pi else ".h264"
                expected_video = f"{video_path}{expected_extension}"
                
                logger.debug(f"Looking for video file: {expected_video}")
                
                if os.path.exists(expected_video):
                    video_size = os.path.getsize(expected_video)
                    logger.info(f"Video file created: {expected_video} ({video_size} bytes)")
                    if video_size < 1000:
                        logger.warning("Video file is very small! Recording may have failed.")
                    else:
                        # Generate plot if requested, using actual video path without extension
                        if args.plot and lsl_data:
                            generate_post_recording_plot(video_path, lsl_data)
                else:
                    # Try the other extension
                    alt_extension = ".h264" if is_newer_pi else ".mp4"
                    alt_video = f"{video_path}{alt_extension}"
                    logger.debug(f"Primary video file not found, trying: {alt_video}")
                    
                    if os.path.exists(alt_video):
                        video_size = os.path.getsize(alt_video)
                        logger.info(f"Video file created: {alt_video} ({video_size} bytes)")
                        # Generate plot if requested, using actual video path without extension
                        if args.plot and lsl_data:
                            generate_post_recording_plot(video_path, lsl_data)
                    else:
                        logger.warning(f"No video file was created at {video_path}.[mp4/h264]")
                        
                        # List files in output directory for debugging
                        output_dir = os.path.dirname(video_path) if os.path.dirname(video_path) else "./output"
                        if os.path.exists(output_dir):
                            files = os.listdir(output_dir)
                            logger.debug(f"Files in {output_dir}: {files}")
                        else:
                            logger.debug(f"Output directory {output_dir} does not exist")
                            
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