#!/usr/bin/env python3

import os
import sys
import time
import json
import signal
import logging
import subprocess
import threading
import queue
import argparse
import datetime
import re
import atexit
from collections import deque
from pathlib import Path
import requests
import pylsl

# ====== Configuration ======
DEFAULT_CONFIG = {
    # Camera settings
    "TARGET_WIDTH": 400,
    "TARGET_HEIGHT": 400,
    "TARGET_FPS": 100,
    "EXPOSURE_TIME_US": 9000,  # Exposure time in microseconds
    
    # Media controller settings
    "IMX296_MEDIA_CONTROLLER_PATH_PATTERN": "/dev/media%d",
    "IMX296_FULL_WIDTH": 1440,  # Updated to match bash script
    "IMX296_FULL_HEIGHT": 1088,
    
    # Buffer settings
    "RAM_BUFFER_DURATION_SECONDS": 15,
    
    # NTFY settings
    "NTFY_SERVER": "https://ntfy.sh",
    "NTFY_TOPIC": "rpi_camera_trigger",
    
    # Recording settings
    "RECORDING_PATH": "recordings",
    
    # LSL settings
    "LSL_STREAM_NAME": "IMX296_Metadata",
    "LSL_STREAM_TYPE": "CameraEvents",
    
    # Temporary file paths
    "PTS_FILE_PATH": "/tmp/camera_live.pts"
}

# ====== Logging setup ======
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("IMX296Recorder")

# ====== Global variables ======
stop_event = threading.Event()
is_recording_active = False
frame_queue = queue.Queue(maxsize=300)  # Buffer for frames going to ffmpeg
current_session_frame_number = 0
lsl_outlet = None

class FrameData:
    """Container for frame data and metadata"""
    def __init__(self, timestamp_us, frame_data):
        self.timestamp_us = timestamp_us
        self.frame_data = frame_data
        self.unix_timestamp = timestamp_us / 1000000.0  # Convert to seconds

def find_imx296_media_device():
    """Find the media device for the IMX296 camera"""
    logger.info("Searching for IMX296 camera media device...")
    
    # Determine device ID (different for Pi models)
    device_id = "10"  # Default
    try:
        with open('/proc/cpuinfo', 'r') as f:
            cpuinfo = f.read()
            # Check for revision indicating Pi 5
            if re.search(r'Revision.*: ...17.', cpuinfo):
                device_id = "10"  # Default for Pi 5 camera 0
                # Check if using camera 1
                if os.environ.get("cam1"):
                    device_id = "11"
    except Exception as e:
        logger.warning(f"Failed to check Raspberry Pi model: {e}")
    
    logger.info(f"Using device ID: {device_id}")
    
    # Try media devices 0-5
    for i in range(6):
        media_dev_path = DEFAULT_CONFIG["IMX296_MEDIA_CONTROLLER_PATH_PATTERN"] % i
        
        if not os.path.exists(media_dev_path):
            continue
            
        try:
            # Check if this media device has our camera
            entity_name = f"'imx296 {device_id}-001a'"
            
            # Try a media-ctl command to see if it succeeds
            test_cmd = ["media-ctl", "-d", media_dev_path, "-p"]
            result = subprocess.run(test_cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                continue
                
            if entity_name.strip("'") in result.stdout:
                logger.info(f"Found IMX296 camera on {media_dev_path}, entity: {entity_name}")
                return media_dev_path, entity_name
                
        except Exception as e:
            logger.warning(f"Error checking {media_dev_path}: {e}")
    
    logger.error("Could not find IMX296 camera media device")
    return None, None

def configure_media_ctl(media_dev_path, entity_name):
    """Configure the IMX296 sensor using media-ctl"""
    logger.info("Configuring IMX296 sensor with media-ctl...")
    
    # Calculate crop coordinates to center the crop on the sensor
    width = DEFAULT_CONFIG["TARGET_WIDTH"]
    height = DEFAULT_CONFIG["TARGET_HEIGHT"]
    x_offset = (DEFAULT_CONFIG["IMX296_FULL_WIDTH"] - width) // 2
    y_offset = (DEFAULT_CONFIG["IMX296_FULL_HEIGHT"] - height) // 2
    
    # Format string for media-ctl command (matching the bash script approach)
    format_str = f"fmt:SBGGR10_1X10/{width}x{height} crop:({x_offset},{y_offset})/{width}x{height}"
    
    # Execute media-ctl command with the format from the bash script
    cmd = ["sudo", "media-ctl", "-d", media_dev_path, "--set-v4l2", f"{entity_name}:0 [{format_str}]", "-v"]
    logger.info(f"Running command: {' '.join(cmd)}")
    
    result = subprocess.run(cmd, capture_output=True, text=True)
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
            logger.info(f"libcamera-hello output: {verify_result.stdout}")
        else:
            logger.warning(f"libcamera-hello verification failed: {verify_result.stderr}")
    except Exception as e:
        logger.warning(f"Could not verify with libcamera-hello: {e}")
    
    return True

def start_camera_capture():
    """Start the camera capture using libcamera-vid with improved command line options"""
    logger.info("Starting camera capture with libcamera-vid...")
    
    # Ensure PTS file directory exists
    pts_dir = os.path.dirname(DEFAULT_CONFIG["PTS_FILE_PATH"])
    os.makedirs(pts_dir, exist_ok=True)
    
    # Check if running on bookworm (OS version check)
    workaround = []
    try:
        with open('/etc/os-release', 'r') as f:
            if '=bookworm' in f.read():
                workaround = ["--no-raw"]
                logger.info("Detected Bookworm, adding --no-raw workaround")
    except Exception as e:
        logger.warning(f"Failed to check OS version: {e}")
    
    # Build libcamera-vid command
    cmd = [
        "libcamera-vid",
        *workaround,
        "--width", str(DEFAULT_CONFIG["TARGET_WIDTH"]),
        "--height", str(DEFAULT_CONFIG["TARGET_HEIGHT"]),
        "--framerate", str(DEFAULT_CONFIG["TARGET_FPS"]),
        "--global-shutter",  # Enable global shutter
        "--shutter", str(DEFAULT_CONFIG["EXPOSURE_TIME_US"]),
        "--denoise", "cdn_off",
        "--inline",
        "--flush",
        "--save-pts", DEFAULT_CONFIG["PTS_FILE_PATH"],
        "-o", "-"  # Output to stdout
    ]
    
    # Add camera selection if specified in environment
    if os.environ.get("cam1"):
        cmd.extend(["--camera", "1"])
        logger.info("Using camera 1 based on environment variable")
    
    logger.info(f"Running command: {' '.join(cmd)}")
    
    # Start libcamera-vid process with stdout piped
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0  # Unbuffered
    )
    
    # Start stderr reader thread to capture and log libcamera-vid messages
    def read_stderr():
        for line in process.stderr:
            logger.debug(f"libcamera-vid: {line.decode().strip()}")
    
    stderr_thread = threading.Thread(target=read_stderr, daemon=True)
    stderr_thread.start()
    
    return process

def create_lsl_outlet():
    """Create an LSL outlet for metadata streaming"""
    logger.info("Creating LSL outlet for metadata streaming...")
    
    # Define stream info with 3 channels
    info = pylsl.StreamInfo(
        name=DEFAULT_CONFIG["LSL_STREAM_NAME"],
        type=DEFAULT_CONFIG["LSL_STREAM_TYPE"],
        channel_count=3,
        nominal_srate=DEFAULT_CONFIG["TARGET_FPS"],
        channel_format=pylsl.cf_double64,
        source_id='imx296_rpi'
    )
    
    # Add channel descriptions
    channels = info.desc().append_child("channels")
    channels.append_child("channel").append_child_value("label", "CaptureTimeUnix")
    channels.append_child("channel").append_child_value("label", "ntfy_notification_active")
    channels.append_child("channel").append_child_value("label", "session_frame_no")
    
    # Create outlet
    outlet = pylsl.StreamOutlet(info, chunk_size=1, max_buffered=360)
    logger.info(f"LSL outlet '{DEFAULT_CONFIG['LSL_STREAM_NAME']}' created")
    
    return outlet

def push_lsl_sample(frame):
    """Push frame metadata to LSL stream"""
    global lsl_outlet, is_recording_active, current_session_frame_number
    
    if lsl_outlet and is_recording_active:
        # Prepare sample: [unix_timestamp, is_recording, frame_number]
        sample = [
            frame.unix_timestamp,
            1.0 if is_recording_active else 0.0,
            float(current_session_frame_number)
        ]
        
        # Push sample with the frame timestamp
        lsl_outlet.push_sample(sample, frame.unix_timestamp)

def read_pts_file(pts_path):
    """Read timestamps from PTS file"""
    timestamps = []
    
    try:
        with open(pts_path, 'r') as f:
            for line in f:
                parts = line.strip().split(' ')
                if len(parts) >= 2:
                    frame_num = int(parts[0])
                    timestamp_us = int(float(parts[1]) * 1000000)  # Convert to microseconds
                    timestamps.append((frame_num, timestamp_us))
    except Exception as e:
        logger.error(f"Error reading PTS file: {e}")
        
    return timestamps

def camera_buffer_thread(camera_process):
    """Thread to read camera output, maintain RAM buffer, and queue frames for recording"""
    global stop_event, frame_queue, is_recording_active, current_session_frame_number
    
    logger.info("Starting camera buffer thread...")
    
    # Initialize RAM buffer as deque with max size based on FPS and buffer duration
    buffer_size = DEFAULT_CONFIG["TARGET_FPS"] * DEFAULT_CONFIG["RAM_BUFFER_DURATION_SECONDS"]
    ram_buffer = deque(maxlen=buffer_size)
    logger.info(f"Initializing rolling buffer with {buffer_size} frame capacity (~{DEFAULT_CONFIG['RAM_BUFFER_DURATION_SECONDS']}s at {DEFAULT_CONFIG['TARGET_FPS']}fps)")
    
    # Track frame numbers for PTS matching
    frame_counter = 0
    pts_data = []
    last_pts_read_time = 0
    
    # Buffer for frame data collection (H.264 NAL units)
    current_frame = bytearray()
    nal_start_code = b'\x00\x00\x00\x01'
    
    while not stop_event.is_set():
        try:
            # Read data from camera process
            data = camera_process.stdout.read(4096)
            if not data:
                logger.warning("End of camera stream detected")
                break
                
            # Process data to identify complete frames
            current_frame.extend(data)
            
            # Look for NAL unit boundaries (0x00000001)
            start_idx = 0
            while True:
                idx = current_frame.find(nal_start_code, start_idx + 4)
                if idx == -1:
                    break
                    
                # Extract complete NAL unit
                nal_unit = bytes(current_frame[start_idx:idx])
                
                # Process NAL unit if it's a VCL NAL (contains picture data)
                nal_type = (nal_unit[4] & 0x1F) if len(nal_unit) > 4 else 0
                if nal_type in [1, 5]:  # Non-IDR or IDR picture
                    frame_counter += 1
                    
                    # Read PTS file periodically to get timestamps
                    if time.time() - last_pts_read_time > 0.5:  # Read every 0.5 seconds
                        pts_data = read_pts_file(DEFAULT_CONFIG["PTS_FILE_PATH"])
                        last_pts_read_time = time.time()
                        
                    # Find matching timestamp for current frame
                    frame_timestamp_us = None
                    for pts_frame, timestamp in pts_data:
                        if pts_frame == frame_counter:
                            frame_timestamp_us = timestamp
                            break
                            
                    # If no matching timestamp, use current time
                    if frame_timestamp_us is None:
                        frame_timestamp_us = int(time.time() * 1000000)
                        
                    # Create frame object
                    frame = FrameData(frame_timestamp_us, nal_unit)
                    
                    # Add to RAM buffer
                    ram_buffer.append(frame)
                    
                    # If recording is active, add to frame queue for ffmpeg
                    if is_recording_active:
                        frame_queue.put(frame)
                        current_session_frame_number += 1
                        
                        # Push metadata to LSL
                        push_lsl_sample(frame)
                
                # Move to next potential NAL unit
                start_idx = idx
                
            # Keep only the last incomplete chunk
            current_frame = current_frame[start_idx:]
            
        except Exception as e:
            logger.error(f"Error in camera buffer thread: {e}")
            if stop_event.is_set():
                break
                
    logger.info("Camera buffer thread ended")

def start_recording(ram_buffer):
    """Start recording to file with ffmpeg"""
    global is_recording_active, current_session_frame_number, frame_queue
    
    # Reset frame counter for new recording session
    current_session_frame_number = 0
    
    # Create recording directory if it doesn't exist
    os.makedirs(DEFAULT_CONFIG["RECORDING_PATH"], exist_ok=True)
    
    # Generate output filename with timestamp
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = os.path.join(DEFAULT_CONFIG["RECORDING_PATH"], f"recording_{timestamp}.mkv")
    
    logger.info(f"Starting recording to {output_file}")
    
    # Start ffmpeg process
    ffmpeg_cmd = [
        "ffmpeg",
        "-f", "h264",
        "-i", "-",  # Input from stdin
        "-c:v", "copy",  # Copy video codec (no re-encoding)
        "-an",  # No audio
        output_file
    ]
    
    logger.info(f"Running command: {' '.join(ffmpeg_cmd)}")
    
    ffmpeg_process = subprocess.Popen(
        ffmpeg_cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    # Start ffmpeg stderr reader thread
    def read_ffmpeg_stderr():
        for line in ffmpeg_process.stderr:
            logger.debug(f"ffmpeg: {line.decode().strip()}")
            
    stderr_thread = threading.Thread(target=read_ffmpeg_stderr, daemon=True)
    stderr_thread.start()
    
    # Set recording flag
    is_recording_active = True
    
    # Copy RAM buffer to ffmpeg
    logger.info(f"Writing {len(ram_buffer)} buffered frames to recording")
    for frame in ram_buffer:
        ffmpeg_process.stdin.write(frame.frame_data)
        current_session_frame_number += 1
        push_lsl_sample(frame)
    
    # Start thread to write frames from queue to ffmpeg
    def write_frames_to_ffmpeg():
        while is_recording_active and not stop_event.is_set():
            try:
                frame = frame_queue.get(timeout=1.0)
                ffmpeg_process.stdin.write(frame.frame_data)
                ffmpeg_process.stdin.flush()
            except queue.Empty:
                continue
            except BrokenPipeError:
                logger.error("Broken pipe to ffmpeg")
                break
            except Exception as e:
                logger.error(f"Error writing to ffmpeg: {e}")
                break
                
        # Close ffmpeg stdin when done
        try:
            if ffmpeg_process.stdin:
                ffmpeg_process.stdin.close()
        except:
            pass
            
        logger.info("Waiting for ffmpeg to finish...")
        ffmpeg_process.wait()
        logger.info(f"Recording completed: {output_file}")
        
    writer_thread = threading.Thread(target=write_frames_to_ffmpeg, daemon=True)
    writer_thread.start()
    
    return ffmpeg_process, writer_thread, output_file

def stop_recording(ffmpeg_process=None):
    """Stop active recording"""
    global is_recording_active
    
    if not is_recording_active:
        logger.info("No active recording to stop")
        return
        
    logger.info("Stopping recording...")
    is_recording_active = False
    
    # ffmpeg process will be closed by the writer thread

def ntfy_listener_thread():
    """Thread to listen for ntfy.sh notifications"""
    global stop_event, is_recording_active
    
    logger.info(f"Connecting to ntfy topic: {DEFAULT_CONFIG['NTFY_TOPIC']}")
    
    ntfy_url = f"{DEFAULT_CONFIG['NTFY_SERVER']}/{DEFAULT_CONFIG['NTFY_TOPIC']}/json"
    
    # Track active recording resources
    active_ffmpeg_process = None
    active_writer_thread = None
    active_output_file = None
    
    while not stop_event.is_set():
        try:
            logger.info(f"Started ntfy subscription to topic: {DEFAULT_CONFIG['NTFY_TOPIC']}")
            
            # Long-polling request
            response = requests.get(ntfy_url, stream=True, timeout=300)
            
            for line in response.iter_lines():
                if stop_event.is_set():
                    break
                    
                if not line:
                    continue
                    
                try:
                    # Parse JSON notification
                    notification = json.loads(line)
                    message = notification.get("message", "").lower()
                    
                    logger.info(f"Received ntfy message: {message}")
                    
                    if "start" in message and not is_recording_active:
                        # Get current RAM buffer from main buffer thread
                        ram_buffer = list(main_buffer_thread.ram_buffer)
                        
                        # Start recording
                        active_ffmpeg_process, active_writer_thread, active_output_file = start_recording(ram_buffer)
                        
                    elif "stop" in message and is_recording_active:
                        # Stop recording
                        stop_recording(active_ffmpeg_process)
                        
                        # Wait for writer thread to complete
                        if active_writer_thread and active_writer_thread.is_alive():
                            active_writer_thread.join(timeout=10)
                            
                        # Reset active recording resources
                        active_ffmpeg_process = None
                        active_writer_thread = None
                        active_output_file = None
                        
                    elif "shutdown_script" in message:
                        logger.info("Received shutdown request via ntfy")
                        stop_event.set()
                        break
                        
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse ntfy message: {line}")
                except Exception as e:
                    logger.error(f"Error processing ntfy notification: {e}")
                    
        except requests.exceptions.Timeout:
            # Timeout is expected for long polling, just reconnect
            logger.debug("ntfy connection timed out, reconnecting...")
            
        except requests.exceptions.RequestException as e:
            logger.error(f"ntfy connection error: {e}")
            time.sleep(5)  # Wait before reconnecting
            
        except Exception as e:
            logger.error(f"Unexpected error in ntfy listener: {e}")
            time.sleep(5)  # Wait before reconnecting
            
    logger.info("ntfy listener thread ended")

def signal_handler(sig, frame):
    """Handle termination signals"""
    logger.info(f"Received signal {sig}, shutting down gracefully...")
    stop_event.set()

def cleanup():
    """Clean up resources on exit"""
    global is_recording_active
    
    # Stop recording if active
    if is_recording_active:
        stop_recording()
        
    # Clean up temporary files
    try:
        if os.path.exists(DEFAULT_CONFIG["PTS_FILE_PATH"]):
            os.unlink(DEFAULT_CONFIG["PTS_FILE_PATH"])
    except Exception as e:
        logger.warning(f"Failed to clean up temporary files: {e}")
        
    logger.info("Cleanup completed")

def main():
    global lsl_outlet, main_buffer_thread
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Raspberry Pi IMX296 Camera Recorder')
    parser.add_argument('--config', type=str, help='Path to configuration JSON file')
    args = parser.parse_args()
    
    # Load configuration from file if provided
    if args.config:
        try:
            with open(args.config, 'r') as f:
                config = json.load(f)
                for key, value in config.items():
                    if key in DEFAULT_CONFIG:
                        DEFAULT_CONFIG[key] = value
                logger.info(f"Loaded configuration from {args.config}")
        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            return 1
    
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    atexit.register(cleanup)
    
    # Print banner
    print("\n" + "="*50)
    print(f"IMX296 Camera Recorder v1.0")
    print(f"Target: {DEFAULT_CONFIG['TARGET_WIDTH']}x{DEFAULT_CONFIG['TARGET_HEIGHT']} @ {DEFAULT_CONFIG['TARGET_FPS']} FPS")
    print(f"Buffer: {DEFAULT_CONFIG['RAM_BUFFER_DURATION_SECONDS']} seconds")
    print(f"NTFY Topic: {DEFAULT_CONFIG['NTFY_TOPIC']}")
    print("="*50 + "\n")
    
    # Find and configure IMX296 camera
    media_dev_path, entity_name = find_imx296_media_device()
    if not media_dev_path or not entity_name:
        logger.error("Failed to find IMX296 camera, exiting")
        return 1
        
    if not configure_media_ctl(media_dev_path, entity_name):
        logger.error("Failed to configure camera with media-ctl, exiting")
        return 1
        
    logger.info("Camera configured successfully")
    
    # Create LSL outlet
    lsl_outlet = create_lsl_outlet()
    
    # Start camera capture
    camera_process = start_camera_capture()
    if not camera_process:
        logger.error("Failed to start camera capture, exiting")
        return 1
        
    # Start buffer thread
    buffer_thread = threading.Thread(target=camera_buffer_thread, args=(camera_process,), daemon=True)
    buffer_thread.start()
    main_buffer_thread = buffer_thread
    
    # Start ntfy listener thread
    ntfy_thread = threading.Thread(target=ntfy_listener_thread, daemon=True)
    ntfy_thread.start()
    
    # Print instructions
    print("\nCamera ready and waiting for trigger notifications")
    print(f"To start recording: curl -d \"start recording\" {DEFAULT_CONFIG['NTFY_SERVER']}/{DEFAULT_CONFIG['NTFY_TOPIC']}")
    print(f"To stop recording: curl -d \"stop recording\" {DEFAULT_CONFIG['NTFY_SERVER']}/{DEFAULT_CONFIG['NTFY_TOPIC']}")
    print(f"To shutdown script: curl -d \"shutdown_script\" {DEFAULT_CONFIG['NTFY_SERVER']}/{DEFAULT_CONFIG['NTFY_TOPIC']}\n")
    
    # Main thread waits for stop event
    try:
        while not stop_event.is_set():
            time.sleep(0.5)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received, shutting down")
        stop_event.set()
        
    # Shutdown and cleanup
    logger.info("Shutting down...")
    
    # Terminate camera process
    if camera_process.poll() is None:
        camera_process.terminate()
        try:
            camera_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            camera_process.kill()
            
    # Wait for threads to finish
    buffer_thread.join(timeout=5)
    ntfy_thread.join(timeout=5)
    
    logger.info("Shutdown complete")
    return 0

if __name__ == "__main__":
    sys.exit(main()) 