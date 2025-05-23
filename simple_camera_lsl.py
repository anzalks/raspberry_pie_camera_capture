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
lsl_data = []  # Store LSL data for CSV export
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
    global stop_event, lsl_data
    
    if not os.path.exists(MARKERS_FILE):
        logger.warning(f"Markers file {MARKERS_FILE} does not exist, waiting for it to be created...")
    
    # Wait until the file exists and has content
    while not stop_event.is_set():
        if os.path.exists(MARKERS_FILE):
            break
        time.sleep(0.1)
    
    if stop_event.is_set():
        return
    
    logger.debug(f"Monitoring markers file: {MARKERS_FILE}")
    
    # Keep track of the last read position
    last_pos = 0
    
    # Initial delay to let the script start creating markers
    time.sleep(0.5)
    
    while not stop_event.is_set():
        try:
            # Check if file exists
            if not os.path.exists(MARKERS_FILE):
                logger.debug("Markers file disappeared, waiting for it to reappear...")
                time.sleep(0.5)
                continue
                
            # Open the file and read new lines
            with open(MARKERS_FILE, 'r') as f:
                f.seek(last_pos)
                new_lines = f.readlines()
                if new_lines:
                    last_pos = f.tell()
                    
                    for line in new_lines:
                        line = line.strip()
                        if not line or line.startswith("Starting"):
                            continue
                            
                        # Parse frame number and timestamp
                        try:
                            parts = line.split()
                            if len(parts) >= 2:
                                frame_num = int(parts[0])
                                frame_time = float(parts[1])
                                push_lsl_sample(frame_num, frame_time)
                                logger.debug(f"Pushed LSL sample: Frame {frame_num}, Time {frame_time}")
                        except ValueError as e:
                            logger.debug(f"Error parsing line '{line}': {e}")
            
            # Short sleep before checking for new lines
            time.sleep(0.01)
            
        except Exception as e:
            logger.warning(f"Error monitoring markers file: {e}")
            time.sleep(0.5)

def run_gscrop_script(width, height, fps, duration_ms, exposure_us=None, output_path=None, preview=False):
    """Run the GScrop shell script to capture video"""
    global camera_process, stop_event
    
    # Build command line arguments
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
    
    # Add preview mode if requested
    if preview:
        env["preview"] = "1"
    
    logger.info(f"Starting GScrop with command: {' '.join(cmd)}")
    
    try:
        # Start the GScrop script
        camera_process = subprocess.Popen(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # Start threads to monitor stdout and stderr
        threading.Thread(target=monitor_process_output, args=(camera_process.stdout, "stdout"), daemon=True).start()
        threading.Thread(target=monitor_process_output, args=(camera_process.stderr, "stderr"), daemon=True).start()
        
        # Start thread to monitor the markers file
        threading.Thread(target=monitor_markers_file, daemon=True).start()
        
        return camera_process
    except Exception as e:
        logger.error(f"Failed to start GScrop script: {e}")
        return None

def monitor_process_output(pipe, name):
    """Monitor a process output pipe and log the results"""
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

def main():
    """Main function"""
    global lsl_outlet, stop_event, lsl_data

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
    
    # Check if GScrop script exists and is executable
    if not os.path.isfile("./GScrop"):
        logger.error("GScrop script not found in current directory")
        return 1
    
    if not os.access("./GScrop", os.X_OK):
        logger.warning("GScrop script is not executable, trying to make it executable")
        try:
            os.chmod("./GScrop", 0o755)
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
    
    # CSV output path (used by this script)
    csv_path = output_dir / f"{output_base}.csv"
    
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
            exposure = int(min(1000000 / args.fps * 0.8, 10000))
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
            preview=args.preview
        )
        
        if not camera_proc:
            logger.error("Failed to start GScrop script")
            return 1
        
        # Wait for camera process to finish or Ctrl+C
        logger.info(f"Recording started with duration: {args.duration} seconds. Press Ctrl+C to stop earlier.")
        
        # Monitor LSL data collection
        frames_count = 0
        last_report_time = time.time()
        
        while camera_proc.poll() is None and not stop_event.is_set():
            # Sleep briefly
            time.sleep(0.1)
            
            # Periodically report frame count
            current_time = time.time()
            if current_time - last_report_time >= 2.0:
                current_frames = len(lsl_data)
                new_frames = current_frames - frames_count
                elapsed = current_time - last_report_time
                fps_rate = new_frames / elapsed if elapsed > 0 else 0
                logger.info(f"Current frame rate: {fps_rate:.1f} FPS ({new_frames} frames in {elapsed:.1f}s)")
                frames_count = current_frames
                last_report_time = current_time
        
        # Check exit code
        exit_code = camera_proc.returncode if camera_proc.returncode is not None else 0
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
        
        # Save LSL data to CSV
        if lsl_data:
            save_lsl_data_to_csv(csv_path)
            logger.info(f"Frames captured: {len(lsl_data)}")
            
            # Check for expected video files
            expected_video = f"{video_path}.mp4" if os.environ.get("cam1") else f"{video_path}.h264"
            if os.path.exists(expected_video):
                video_size = os.path.getsize(expected_video)
                logger.info(f"Video file created: {expected_video} ({video_size} bytes)")
                if video_size < 1000:
                    logger.warning("Video file is very small! Recording may have failed.")
            else:
                # Try the other extension
                alt_video = f"{video_path}.h264" if os.environ.get("cam1") else f"{video_path}.mp4"
                if os.path.exists(alt_video):
                    video_size = os.path.getsize(alt_video)
                    logger.info(f"Video file created: {alt_video} ({video_size} bytes)")
                else:
                    logger.warning(f"No video file was created at {video_path}.[mp4/h264]")
        else:
            logger.warning("No LSL data was collected during recording")
    
    if recording_successful:
        logger.info("Recording completed successfully")
    else:
        logger.warning("Recording may not have completed successfully")
        
    return 0 if recording_successful else 1

if __name__ == "__main__":
    sys.exit(main()) 