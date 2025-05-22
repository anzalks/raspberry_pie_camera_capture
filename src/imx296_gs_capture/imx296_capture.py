#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IMX296 Global Shutter Camera Capture System

This script captures video from an IMX296 global shutter camera on a Raspberry Pi
with specific high-FPS and cropped settings. It integrates:
- Hardware cropping via media-ctl
- RAM buffer for pre-trigger storage
- ntfy.sh notifications for remote control
- LSL streaming for metadata
- MKV output via ffmpeg
- Detailed status output for tmux monitoring

Author: Anzal KS <anzal.ks@gmail.com>
Date: May 22, 2025
"""

import os
import sys
import time
import json
import yaml
import signal
import logging
import subprocess
import threading
import re
import queue
import datetime
import collections
import tempfile
import shutil
import requests
import pylsl
from pathlib import Path
from logging.handlers import RotatingFileHandler
import psutil  # Optional, for system monitoring

# Global variables for threading coordination
stop_event = threading.Event()
recording_event = threading.Event()
is_recording_active = False
frame_queue = queue.Queue(maxsize=1000)  # Queue for passing frames from buffer to ffmpeg
lsl_outlet = None  # LSL outlet for metadata
session_frame_counter = 0  # Frame counter for the current recording session
libcamera_vid_process = None
ffmpeg_process = None

# =============================================================================
# Configuration Management
# =============================================================================

def load_config(config_file="config/config.yaml"):
    """Load configuration from YAML file."""
    try:
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)
        return config
    except Exception as e:
        print(f"Error loading config file {config_file}: {e}")
        sys.exit(1)

def setup_logging(config):
    """Configure logging based on configuration."""
    log_config = config.get('logging', {})
    log_level = getattr(logging, log_config.get('level', 'INFO'))
    log_format = log_config.get('format', '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    log_file = log_config.get('file', 'logs/imx296_capture.log')
    
    # Ensure log directory exists
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    
    # Create a logger
    logger = logging.getLogger('imx296_capture')
    logger.setLevel(log_level)
    
    # Create handlers
    if log_config.get('console', True):
        console_handler = logging.StreamHandler()
        console_handler.setLevel(log_level)
        console_handler.setFormatter(logging.Formatter(log_format))
        logger.addHandler(console_handler)
    
    if log_file:
        max_size = log_config.get('max_size_mb', 10) * 1024 * 1024  # Convert to bytes
        backup_count = log_config.get('backup_count', 5)
        file_handler = RotatingFileHandler(
            log_file, maxBytes=max_size, backupCount=backup_count
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(logging.Formatter(log_format))
        logger.addHandler(file_handler)
    
    return logger

# =============================================================================
# Media Controller Setup (Pre-libcamera)
# =============================================================================

def find_imx296_media_device(config):
    """Find the media device for the IMX296 camera."""
    logger = logging.getLogger('imx296_capture')
    media_ctl_path = config['system']['media_ctl_path']
    device_pattern = config['camera']['media_ctl']['device_pattern']
    entity_pattern = config['camera']['media_ctl']['entity_pattern']
    
    # Try various media devices
    for i in range(10):  # Check media0 through media9
        media_dev = device_pattern % i
        if not os.path.exists(media_dev):
            continue
        
        logger.info(f"Checking media device: {media_dev}")
        
        # Run media-ctl to list entities
        try:
            cmd = [media_ctl_path, "-d", media_dev, "-p"]
            output = subprocess.check_output(cmd, universal_newlines=True)
            
            # Look for IMX296 entity in the output
            entity_match = None
            for line in output.splitlines():
                # This regex looks for IMX296 in different formats
                match = re.search(r'entity\s+\d+:\s+(imx296\s+[a-z0-9\-]+)', line, re.IGNORECASE)
                if match:
                    entity_match = match.group(1)
                    logger.info(f"Found IMX296 entity: {entity_match}")
                    return media_dev, entity_match
            
            # If no explicit match, try a fallback pattern search
            if "imx296" in output.lower():
                # Try to extract the entity from another line
                for line in output.splitlines():
                    if "imx296" in line.lower():
                        parts = line.split(":")
                        if len(parts) >= 2:
                            entity_name = parts[1].strip()
                            logger.info(f"Found IMX296 entity using fallback method: {entity_name}")
                            return media_dev, entity_name
                
                logger.warning(f"IMX296 found in {media_dev} but couldn't identify entity name")
                
        except subprocess.CalledProcessError as e:
            logger.warning(f"Error running media-ctl on {media_dev}: {e}")
            continue
    
    logger.error("Could not find IMX296 camera. Is it connected and powered on?")
    return None, None

def configure_media_ctl(config):
    """Configure the IMX296 sensor using media-ctl for hardware cropping."""
    logger = logging.getLogger('imx296_capture')
    media_ctl_path = config['system']['media_ctl_path']
    
    # Find the IMX296 media device and entity
    media_dev, entity_name = find_imx296_media_device(config)
    if not media_dev or not entity_name:
        logger.error("Cannot configure media-ctl without a valid device and entity")
        return False
    
    # Calculate crop coordinates to center the 400x400 window in the sensor
    sensor_width = config['camera']['sensor_width']
    sensor_height = config['camera']['sensor_height']
    target_width = config['camera']['width']
    target_height = config['camera']['height']
    
    crop_x = (sensor_width - target_width) // 2
    crop_y = (sensor_height - target_height) // 2
    
    bayer_format = config['camera']['media_ctl']['bayer_format']
    
    # Construct and execute the media-ctl command
    try:
        # Format the command with the calculated crop coordinates
        cmd = [
            media_ctl_path, "-d", media_dev,
            "--set-v4l2", f'"{entity_name}":0[fmt:{bayer_format}/{target_width}x{target_height} crop:({crop_x},{crop_y})/{target_width}x{target_height}]'
        ]
        
        logger.info(f"Executing media-ctl command: {' '.join(cmd)}")
        output = subprocess.check_output(cmd, universal_newlines=True, stderr=subprocess.STDOUT)
        logger.info(f"media-ctl output: {output}")
        
        # Verify the configuration
        cmd_verify = [media_ctl_path, "-d", media_dev, "-p"]
        verify_output = subprocess.check_output(cmd_verify, universal_newlines=True)
        logger.debug(f"media-ctl verification output: {verify_output}")
        
        # Optional: Run libcamera-hello to verify the crop
        verify_with_libcamera_hello(config)
        
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to configure media-ctl: {e}")
        logger.error(f"Command output: {e.output if hasattr(e, 'output') else 'No output'}")
        return False

def verify_with_libcamera_hello(config):
    """Verify the camera configuration using libcamera-hello --list-cameras."""
    logger = logging.getLogger('imx296_capture')
    libcamera_hello_path = config['system']['libcamera_hello_path']
    
    try:
        cmd = [libcamera_hello_path, "--list-cameras"]
        logger.info(f"Verifying camera configuration with: {' '.join(cmd)}")
        output = subprocess.check_output(cmd, universal_newlines=True, stderr=subprocess.STDOUT)
        logger.info(f"libcamera-hello output:\n{output}")
        
        # Check if the output shows the expected crop dimensions
        target_width = config['camera']['width']
        target_height = config['camera']['height']
        
        if f"{target_width}x{target_height}" in output:
            logger.info(f"Verified: Camera is configured for {target_width}x{target_height}")
            return True
        else:
            logger.warning(f"Could not verify {target_width}x{target_height} in libcamera-hello output")
            return False
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to run libcamera-hello: {e}")
        logger.error(f"Command output: {e.output if hasattr(e, 'output') else 'No output'}")
        return False

# =============================================================================
# LSL Stream Setup
# =============================================================================

def setup_lsl_stream(config):
    """Set up the LSL stream for camera metadata."""
    global lsl_outlet
    
    logger = logging.getLogger('imx296_capture')
    lsl_config = config.get('lsl', {})
    
    stream_name = lsl_config.get('stream_name', 'IMX296_Metadata')
    stream_type = lsl_config.get('stream_type', 'CameraEvents')
    channel_count = lsl_config.get('channel_count', 3)
    nominal_srate = lsl_config.get('nominal_srate', 100)
    
    # Create channel format
    channel_format = pylsl.cf_double64  # Use double precision for all channels
    
    # Create channel names
    channel_names = ["CaptureTimeUnix", "ntfy_notification_active", "session_frame_no"]
    
    try:
        # Create LSL StreamInfo
        info = pylsl.StreamInfo(
            name=stream_name,
            type=stream_type,
            channel_count=channel_count,
            nominal_srate=nominal_srate,
            channel_format=channel_format,
            source_id=f"imx296_{os.getpid()}"
        )
        
        # Add channel metadata
        channels = info.desc().append_child("channels")
        for name in channel_names:
            channels.append_child("channel").append_child_value("label", name)
        
        # Add some acquisition metadata
        info.desc().append_child("acquisition").append_child_value("manufacturer", "Sony")
        info.desc().append_child("acquisition").append_child_value("model", "IMX296")
        info.desc().append_child("acquisition").append_child_value("fps", str(config['camera']['fps']))
        info.desc().append_child("acquisition").append_child_value("resolution", f"{config['camera']['width']}x{config['camera']['height']}")
        
        # Create outlet
        lsl_outlet = pylsl.StreamOutlet(info)
        logger.info(f"Created LSL stream '{stream_name}' with {channel_count} channels at {nominal_srate} Hz")
        return True
    except Exception as e:
        logger.error(f"Failed to create LSL stream: {e}")
        return False

# =============================================================================
# Camera Capture Thread
# =============================================================================

def read_pts_file(pts_file_path, start_time=None):
    """Read timestamps from the PTS file generated by libcamera-vid."""
    if not os.path.exists(pts_file_path):
        return []
    
    timestamps = []
    with open(pts_file_path, 'r') as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) >= 2:
                try:
                    frame_num = int(parts[0])
                    pts_us = int(float(parts[1]) * 1000000)  # Convert to microseconds
                    
                    # If start_time provided, calculate wall-clock time
                    if start_time is not None:
                        wall_time = start_time + (pts_us / 1000000.0)  # Convert back to seconds
                    else:
                        wall_time = pts_us / 1000000.0  # Just use PTS as seconds
                    
                    timestamps.append((frame_num, pts_us, wall_time))
                except (ValueError, IndexError):
                    pass
    
    return timestamps

def camera_thread(config):
    """Thread to manage camera capture, buffer, and frame processing."""
    global libcamera_vid_process, session_frame_counter, is_recording_active
    
    logger = logging.getLogger('imx296_capture')
    
    # Configure libcamera-vid command
    libcamera_vid_path = config['system']['libcamera_vid_path']
    width = config['camera']['width']
    height = config['camera']['height']
    fps = config['camera']['fps']
    exposure_time_us = config['camera']['exposure_time_us']
    pts_file_path = config['camera']['pts_file_path']
    
    # Create RAM buffer using deque
    buffer_duration_sec = config['buffer']['duration_seconds']
    max_frames = config['buffer']['max_frames']
    frame_buffer = collections.deque(maxlen=max_frames)
    
    # Build libcamera-vid command
    cmd = [
        libcamera_vid_path,
        "--width", str(width),
        "--height", str(height),
        "--framerate", str(fps),
        "--global-shutter",  # Essential for IMX296
        "--shutter", str(exposure_time_us),
        "--denoise", "cdn_off",
        "--save-pts", pts_file_path,
        "--inline",
        "--flush",
        "-o", "-"  # Output to stdout
    ]
    
    logger.info(f"Starting libcamera-vid with command: {' '.join(cmd)}")
    logger.info(f"Using RAM buffer of {buffer_duration_sec} seconds (max {max_frames} frames)")
    
    try:
        # Start libcamera-vid process
        libcamera_vid_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0  # Unbuffered
        )
        
        # Start stderr reader thread to capture log messages
        stderr_thread = threading.Thread(
            target=log_stderr_output,
            args=(libcamera_vid_process.stderr, "libcamera-vid"),
            daemon=True
        )
        stderr_thread.start()
        
        # Record start time for timestamp calculation
        start_time = time.time()
        
        # Initialize variables for frame collection
        current_frame = bytearray()
        frame_start_marker = b'\x00\x00\x00\x01'  # H.264 NAL unit start code
        frame_count = 0
        last_pts_read_time = 0
        pts_data = []
        
        # Main loop for reading frames
        logger.info("Camera capture started, buffering frames to RAM")
        
        while not stop_event.is_set():
            # Read a chunk of data
            chunk = libcamera_vid_process.stdout.read(4096)
            if not chunk:
                logger.error("libcamera-vid output ended unexpectedly")
                break
            
            # Check for frame boundaries in the chunk
            if frame_start_marker in chunk:
                # If we have data from a previous frame, complete it and process
                if current_frame:
                    # Find position of start marker in the chunk
                    marker_pos = chunk.find(frame_start_marker)
                    
                    # Add data before the marker to the current frame
                    current_frame.extend(chunk[:marker_pos])
                    
                    # Process the completed frame
                    process_frame(current_frame, frame_count, start_time, frame_buffer, pts_data)
                    frame_count += 1
                    
                    # Start a new frame with remaining data
                    current_frame = bytearray(chunk[marker_pos:])
                else:
                    # This is the first frame, just store the data
                    current_frame.extend(chunk)
            else:
                # No frame boundary in this chunk, just add to current frame
                current_frame.extend(chunk)
            
            # Read PTS file periodically (not every frame to reduce I/O)
            current_time = time.time()
            if current_time - last_pts_read_time > 1.0:  # Read PTS every second
                pts_data = read_pts_file(pts_file_path, start_time)
                last_pts_read_time = current_time
            
            # Periodically log status
            if frame_count % 100 == 0:
                buffer_size = len(frame_buffer)
                logger.info(f"Captured {frame_count} frames, buffer contains {buffer_size} frames")
        
        logger.info("Camera thread stopping...")
        
    except Exception as e:
        logger.error(f"Error in camera thread: {e}")
    finally:
        # Clean up
        if libcamera_vid_process:
            try:
                libcamera_vid_process.terminate()
                libcamera_vid_process.wait(timeout=5)
            except:
                libcamera_vid_process.kill()
            libcamera_vid_process = None
        
        logger.info("Camera thread exited")

def process_frame(frame_data, frame_num, start_time, frame_buffer, pts_data):
    """Process a captured frame - store in buffer and handle recording if active."""
    global session_frame_counter, is_recording_active
    
    # Find timestamp for this frame from PTS data
    frame_timestamp = find_timestamp_for_frame(frame_num, pts_data, start_time)
    
    # Add frame to the circular buffer
    frame_buffer.append((frame_timestamp, bytes(frame_data)))
    
    # If recording is active, send to ffmpeg and push to LSL
    if is_recording_active:
        # Put frame in queue for ffmpeg
        try:
            frame_queue.put((frame_timestamp, bytes(frame_data)), block=False)
        except queue.Full:
            logging.warning("Frame queue full, dropping frame")
        
        # Send metadata to LSL
        if lsl_outlet:
            # Prepare sample: [unix_timestamp, recording_active, frame_number]
            sample = [frame_timestamp, 1.0, float(session_frame_counter)]
            lsl_outlet.push_sample(sample, frame_timestamp)
            session_frame_counter += 1

def find_timestamp_for_frame(frame_num, pts_data, start_time):
    """Find the timestamp for a given frame from PTS data."""
    # If we have PTS data, use it
    for pts_frame_num, pts_us, wall_time in pts_data:
        if pts_frame_num == frame_num:
            return wall_time
    
    # Fallback: use current time
    return time.time()

def log_stderr_output(stderr, process_name):
    """Thread function to log stderr output from a subprocess."""
    logger = logging.getLogger(f'imx296_capture.{process_name}')
    for line in stderr:
        line = line.decode('utf-8', errors='replace').strip()
        if line:
            logger.debug(f"{process_name}: {line}")

# =============================================================================
# NTFY Notification Thread
# =============================================================================

def ntfy_thread(config):
    """Thread to listen for ntfy.sh notifications and trigger actions."""
    logger = logging.getLogger('imx296_capture')
    
    ntfy_server = config['ntfy']['server']
    ntfy_topic = config['ntfy']['topic']
    poll_interval = config['ntfy']['poll_interval_sec']
    
    ntfy_url = f"{ntfy_server}/{ntfy_topic}/json"
    
    logger.info(f"Starting ntfy.sh listener on topic: {ntfy_topic}")
    logger.info(f"To start recording: curl -d \"start\" {ntfy_server}/{ntfy_topic}")
    logger.info(f"To stop recording: curl -d \"stop\" {ntfy_server}/{ntfy_topic}")
    
    # Track last event ID to avoid duplicate processing
    last_event_id = None
    
    while not stop_event.is_set():
        try:
            # Set up headers for long polling
            headers = {"Cache-Control": "no-cache"}
            if last_event_id:
                headers["If-None-Match"] = last_event_id
            
            logger.debug(f"Polling ntfy.sh with timeout: {poll_interval}s")
            
            # Make the request with timeout
            response = requests.get(
                ntfy_url,
                headers=headers,
                timeout=poll_interval
            )
            
            if response.status_code == 200:
                try:
                    # Parse JSON response
                    notifications = response.json()
                    
                    # Process each notification (usually just one)
                    for notification in notifications:
                        event_id = notification.get("id")
                        if event_id != last_event_id:  # Avoid duplicates
                            message = notification.get("message", "").strip().lower()
                            
                            logger.info(f"Received ntfy notification: {message}")
                            
                            if message == "start":
                                handle_start_notification(config)
                            elif message == "stop":
                                handle_stop_notification()
                            elif message == "shutdown_script":
                                logger.info("Received shutdown request via ntfy")
                                stop_event.set()
                                break
                            
                            last_event_id = event_id
                except ValueError:
                    logger.warning("Received invalid JSON from ntfy.sh")
            elif response.status_code == 304:
                # No new notifications
                logger.debug("No new notifications from ntfy.sh")
            else:
                logger.warning(f"Unexpected status code from ntfy.sh: {response.status_code}")
                
        except requests.RequestException as e:
            logger.warning(f"Error polling ntfy.sh: {e}")
        
        # Sleep briefly before next poll attempt
        time.sleep(1)
    
    logger.info("ntfy thread exited")

def handle_start_notification(config):
    """Handle a 'start' notification from ntfy.sh."""
    global is_recording_active, session_frame_counter, frame_queue
    
    logger = logging.getLogger('imx296_capture')
    
    # If already recording, ignore
    if is_recording_active:
        logger.info("Already recording, ignoring start notification")
        return
    
    logger.info("Handling 'start' notification - beginning recording")
    
    # Reset session frame counter
    session_frame_counter = 0
    
    # Clear frame queue to ensure we start fresh
    while not frame_queue.empty():
        try:
            frame_queue.get_nowait()
        except queue.Empty:
            break
    
    # Start recording
    is_recording_active = True
    recording_event.set()
    
    # Start video writer thread
    video_thread = threading.Thread(
        target=video_writer_thread,
        args=(config,),
        daemon=True
    )
    video_thread.start()
    
    logger.info("Recording started")

def handle_stop_notification():
    """Handle a 'stop' notification from ntfy.sh."""
    global is_recording_active
    
    logger = logging.getLogger('imx296_capture')
    
    # If not recording, ignore
    if not is_recording_active:
        logger.info("Not recording, ignoring stop notification")
        return
    
    logger.info("Handling 'stop' notification - ending recording")
    
    # Stop recording
    is_recording_active = False
    recording_event.clear()
    
    logger.info("Recording stopped")

# =============================================================================
# Video Writer Thread (FFmpeg)
# =============================================================================

def video_writer_thread(config):
    """Thread to write video frames to file using ffmpeg."""
    global ffmpeg_process, frame_queue
    
    logger = logging.getLogger('imx296_capture')
    
    # Generate output filename with timestamp
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = config['recording']['output_dir']
    format_ext = config['recording']['format']
    
    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)
    
    output_file = os.path.join(output_dir, f"recording_{timestamp}.{format_ext}")
    
    # Configure FFmpeg command
    ffmpeg_path = config['system']['ffmpeg_path']
    width = config['camera']['width']
    height = config['camera']['height']
    fps = config['camera']['fps']
    
    cmd = [
        ffmpeg_path,
        "-f", "h264",            # Input format is H.264
        "-i", "-",               # Input from stdin
        "-c:v", "copy",          # Copy video codec (no re-encoding)
        "-an",                   # No audio
        "-y",                    # Overwrite output file if exists
        output_file              # Output file
    ]
    
    logger.info(f"Starting ffmpeg with command: {' '.join(cmd)}")
    logger.info(f"Recording to file: {output_file}")
    
    try:
        # Start ffmpeg process
        ffmpeg_process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0  # Unbuffered
        )
        
        # Start stderr reader thread to capture ffmpeg log messages
        stderr_thread = threading.Thread(
            target=log_stderr_output,
            args=(ffmpeg_process.stderr, "ffmpeg"),
            daemon=True
        )
        stderr_thread.start()
        
        # Write frames from queue to ffmpeg's stdin
        frame_count = 0
        last_log_time = time.time()
        
        while is_recording_active or not frame_queue.empty():
            try:
                # Get a frame from the queue with timeout
                timestamp, frame_data = frame_queue.get(timeout=0.5)
                
                # Write frame to ffmpeg
                ffmpeg_process.stdin.write(frame_data)
                frame_count += 1
                
                # Log progress periodically
                current_time = time.time()
                if current_time - last_log_time > 5.0:  # Log every 5 seconds
                    logger.info(f"Recording progress: {frame_count} frames written to {output_file}")
                    last_log_time = current_time
                
            except queue.Empty:
                # No frames available but recording is still active
                if is_recording_active:
                    logger.debug("No frames available in queue, waiting...")
                    time.sleep(0.01)  # Short sleep to avoid CPU spin
                else:
                    # Recording stopped and queue is empty, exit
                    logger.info("No more frames to write, finalizing video")
                    break
        
        # Close ffmpeg's stdin to signal end of input
        ffmpeg_process.stdin.close()
        
        # Wait for ffmpeg to finish
        logger.info("Waiting for ffmpeg to finalize video file...")
        ffmpeg_process.wait()
        
        logger.info(f"Recording complete: {frame_count} frames written to {output_file}")
        
    except Exception as e:
        logger.error(f"Error in video writer thread: {e}")
    finally:
        # Clean up
        if ffmpeg_process:
            try:
                if ffmpeg_process.poll() is None:  # Process still running
                    ffmpeg_process.stdin.close()
                    ffmpeg_process.terminate()
                    ffmpeg_process.wait(timeout=5)
            except:
                if ffmpeg_process.poll() is None:
                    ffmpeg_process.kill()
            ffmpeg_process = None
        
        logger.info("Video writer thread exited")

# =============================================================================
# Signal Handling and Cleanup
# =============================================================================

def signal_handler(sig, frame):
    """Handle signals for graceful shutdown."""
    logger = logging.getLogger('imx296_capture')
    logger.info(f"Received signal {sig}, initiating graceful shutdown")
    
    # Set stop event to signal all threads to exit
    stop_event.set()
    
    # Stop recording if active
    global is_recording_active
    if is_recording_active:
        is_recording_active = False
        recording_event.clear()

def cleanup():
    """Clean up resources before exiting."""
    logger = logging.getLogger('imx296_capture')
    logger.info("Cleaning up resources...")
    
    # Terminate processes if they're still running
    global libcamera_vid_process, ffmpeg_process
    
    if libcamera_vid_process:
        try:
            libcamera_vid_process.terminate()
            libcamera_vid_process.wait(timeout=5)
        except:
            libcamera_vid_process.kill()
        libcamera_vid_process = None
    
    if ffmpeg_process:
        try:
            if ffmpeg_process.poll() is None:  # Process still running
                ffmpeg_process.stdin.close()
                ffmpeg_process.terminate()
                ffmpeg_process.wait(timeout=5)
        except:
            if ffmpeg_process.poll() is None:
                ffmpeg_process.kill()
        ffmpeg_process = None
    
    # Clean up temporary files
    pts_file = None
    try:
        config = load_config()
        pts_file = config['camera']['pts_file_path']
    except:
        pass
    
    if pts_file and os.path.exists(pts_file):
        try:
            os.remove(pts_file)
            logger.info(f"Removed temporary PTS file: {pts_file}")
        except:
            pass
    
    logger.info("Cleanup complete")

# =============================================================================
# Main Function
# =============================================================================

def main():
    """Main function to run the camera capture system."""
    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Parse command-line arguments
    import argparse
    parser = argparse.ArgumentParser(description="IMX296 Global Shutter Camera Capture System")
    parser.add_argument("--config", default="config/config.yaml", help="Path to config file")
    args = parser.parse_args()
    
    # Load configuration
    config = load_config(args.config)
    
    # Setup logging
    logger = setup_logging(config)
    
    logger.info("========== IMX296 Global Shutter Camera Capture System ==========")
    logger.info(f"Starting with config file: {args.config}")
    
    try:
        # Configure media-ctl for hardware cropping
        logger.info("Configuring media-ctl for hardware cropping...")
        if not configure_media_ctl(config):
            logger.error("Failed to configure media-ctl, exiting")
            return 1
        
        # Setup LSL stream
        logger.info("Setting up LSL stream...")
        if not setup_lsl_stream(config):
            logger.warning("Failed to setup LSL stream, continuing without LSL")
        
        # Start camera thread
        logger.info("Starting camera capture thread...")
        camera_thread_obj = threading.Thread(
            target=camera_thread,
            args=(config,),
            daemon=True
        )
        camera_thread_obj.start()
        
        # Start ntfy thread
        logger.info("Starting ntfy notification thread...")
        ntfy_thread_obj = threading.Thread(
            target=ntfy_thread,
            args=(config,),
            daemon=True
        )
        ntfy_thread_obj.start()
        
        # Main thread just waits for stop event
        logger.info("System ready and listening for ntfy notifications")
        while not stop_event.is_set():
            time.sleep(0.1)
        
        # Wait for threads to exit
        logger.info("Waiting for threads to exit...")
        ntfy_thread_obj.join(timeout=10)
        camera_thread_obj.join(timeout=10)
        
    except Exception as e:
        logger.error(f"Unhandled exception in main: {e}")
        return 1
    finally:
        # Clean up resources
        cleanup()
        logger.info("IMX296 Global Shutter Camera Capture System exited")
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 