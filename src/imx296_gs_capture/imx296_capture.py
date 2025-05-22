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
import glob

# Global variables for threading coordination
stop_event = threading.Event()
recording_event = threading.Event()
is_recording_active = False
frame_queue = queue.Queue(maxsize=1000)  # Queue for passing frames from buffer to ffmpeg
lsl_outlet = None  # LSL outlet for metadata
session_frame_counter = 0  # Frame counter for the current recording session
libcamera_vid_process = None
ffmpeg_process = None
last_trigger_source = 0  # 0=none, 1=ntfy, 2=keyboard

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
    
    logger.info("Searching for IMX296 camera in available media devices...")
    
    # First, run libcamera-hello to see if the camera is detected by libcamera
    try:
        libcamera_hello_path = config['system']['libcamera_hello_path']
        cmd = [libcamera_hello_path, "--list-cameras"]
        logger.info(f"Running: {' '.join(cmd)}")
        output = subprocess.check_output(cmd, universal_newlines=True, stderr=subprocess.STDOUT)
        logger.info(f"libcamera-hello output:\n{output}")
        
        if "imx296" not in output.lower():
            logger.error("IMX296 camera not detected by libcamera-hello. Check camera connection.")
    except subprocess.CalledProcessError as e:
        logger.warning(f"Error running libcamera-hello: {e}")
        logger.warning(f"Output: {e.output if hasattr(e, 'output') else 'No output'}")
    
    # Check if device_pattern has a %d format specifier
    is_pattern = '%d' in device_pattern
    
    # List all media devices
    media_devices = []
    for i in range(10):  # Check media0 through media9
        if is_pattern:
            media_dev = device_pattern % i
        else:
            media_dev = f"/dev/media{i}"
        
        if os.path.exists(media_dev):
            media_devices.append(media_dev)
    
    logger.info(f"Found media devices: {media_devices}")
    
    # Try each media device
    for media_dev in media_devices:
        logger.info(f"Checking media device: {media_dev}")
        
        try:
            # Run media-ctl to list entities
            cmd = [media_ctl_path, "-d", media_dev, "-p"]
            logger.info(f"Running: {' '.join(cmd)}")
            output = subprocess.check_output(cmd, universal_newlines=True, stderr=subprocess.STDOUT)
            
            # Log the full output for debugging
            logger.debug(f"media-ctl output for {media_dev}:\n{output}")
            
            # Check if IMX296 is mentioned anywhere in the output
            if "imx296" in output.lower():
                logger.info(f"Found IMX296 in {media_dev}")
                
                # Look for the specific entity
                for line in output.splitlines():
                    # This regex looks for IMX296 in different formats
                    match = re.search(r'entity\s+\d+:\s+(imx296\s+[a-z0-9\-]+)', line, re.IGNORECASE)
                    if match:
                        entity_match = match.group(1)
                        logger.info(f"Found IMX296 entity: {entity_match}")
                        return media_dev, entity_match
                
                # If we found imx296 but not the exact entity, try to extract the entity from another line
                for line in output.splitlines():
                    if "imx296" in line.lower():
                        parts = line.split(":")
                        if len(parts) >= 2:
                            entity_name = parts[1].strip()
                            logger.info(f"Found IMX296 entity using fallback method: {entity_name}")
                            return media_dev, entity_name
                
                # If we still haven't found a specific entity but know the camera is on this device
                logger.info(f"IMX296 found in {media_dev} but couldn't identify entity name. Using default.")
                return media_dev, "imx296"
                
        except subprocess.CalledProcessError as e:
            logger.warning(f"Error running media-ctl on {media_dev}: {e}")
            logger.warning(f"Output: {e.output if hasattr(e, 'output') else 'No output'}")
            continue
    
    # Try a different approach - look for device patterns that might indicate a camera
    logger.warning("Could not find IMX296 camera using standard methods. Trying alternative search.")
    for media_dev in media_devices:
        try:
            cmd = [media_ctl_path, "-d", media_dev, "-p"]
            output = subprocess.check_output(cmd, universal_newlines=True, stderr=subprocess.STDOUT)
            
            # Look for terms that might indicate a camera
            camera_indicators = ["camera", "sensor", "csi", "mipi"]
            for indicator in camera_indicators:
                if indicator in output.lower():
                    logger.info(f"Found potential camera device: {media_dev} (contains '{indicator}')")
                    # Extract any entity that might be a camera
                    for line in output.splitlines():
                        if "entity" in line.lower() and any(ind in line.lower() for ind in camera_indicators):
                            parts = line.split(":")
                            if len(parts) >= 2:
                                entity_name = parts[1].strip()
                                logger.info(f"Using camera entity: {entity_name}")
                                return media_dev, entity_name
        except:
            continue
    
    logger.error("Could not find IMX296 camera or any camera device. Is it connected and powered on?")
    return None, None

def configure_media_ctl(config):
    """Configure the IMX296 sensor using media-ctl for hardware cropping."""
    logger = logging.getLogger('imx296_capture')
    media_ctl_path = config['system']['media_ctl_path']
    
    # Find the IMX296 media device and entity
    media_dev, entity_name = find_imx296_media_device(config)
    if not media_dev or not entity_name:
        logger.error("Cannot configure media-ctl without a valid device and entity")
        # Try to provide some diagnostic information
        try:
            # Check if libcamera can see the camera
            libcamera_hello_path = config['system']['libcamera_hello_path']
            logger.info("Checking for cameras with libcamera-hello:")
            cmd = [libcamera_hello_path, "--list-cameras"]
            output = subprocess.check_output(cmd, universal_newlines=True, stderr=subprocess.STDOUT)
            logger.info(f"libcamera-hello output:\n{output}")
            
            # List all media devices
            logger.info("Listing all media devices:")
            for i in range(10):
                media_path = f"/dev/media{i}"
                if os.path.exists(media_path):
                    logger.info(f"Found {media_path}")
                    try:
                        cmd = [media_ctl_path, "-d", media_path, "-p"]
                        output = subprocess.check_output(cmd, universal_newlines=True, stderr=subprocess.STDOUT)
                        logger.info(f"media-ctl output summary for {media_path}: {len(output.splitlines())} lines")
                    except subprocess.CalledProcessError as e:
                        logger.error(f"Error running media-ctl on {media_path}: {e}")
            
            logger.info("Camera not found. Please check connections and ensure camera is enabled in raspi-config.")
        except Exception as e:
            logger.error(f"Error during diagnostics: {e}")
        
        return False
    
    # Calculate crop coordinates to center the 400x400 window in the sensor
    sensor_width = config['camera']['sensor_width']
    sensor_height = config['camera']['sensor_height']
    target_width = config['camera']['width']
    target_height = config['camera']['height']
    
    crop_x = (sensor_width - target_width) // 2
    crop_y = (sensor_height - target_height) // 2
    
    bayer_format = config['camera']['media_ctl']['bayer_format']
    
    # Log the configuration we're about to apply
    logger.info(f"Configuring IMX296 camera on {media_dev}")
    logger.info(f"Entity: {entity_name}")
    logger.info(f"Crop: {crop_x},{crop_y}/{target_width}x{target_height}")
    logger.info(f"Format: {bayer_format}")
    
    # Construct and execute the media-ctl command
    try:
        # Format the command with the calculated crop coordinates
        cmd = [
            media_ctl_path, "-d", media_dev,
            "--set-v4l2", f'"{entity_name}":0[fmt:{bayer_format}/{target_width}x{target_height} crop:({crop_x},{crop_y})/{target_width}x{target_height}]'
        ]
        
        logger.info(f"Executing media-ctl command: {' '.join(cmd)}")
        
        # Try with different quoting styles if necessary
        try:
            output = subprocess.check_output(cmd, universal_newlines=True, stderr=subprocess.STDOUT, shell=False)
            logger.info(f"media-ctl output: {output}")
        except subprocess.CalledProcessError:
            # Try without quotes around the entity name
            cmd = [
                media_ctl_path, "-d", media_dev,
                "--set-v4l2", f'{entity_name}:0[fmt:{bayer_format}/{target_width}x{target_height} crop:({crop_x},{crop_y})/{target_width}x{target_height}]'
            ]
            logger.info(f"Retrying with modified command: {' '.join(cmd)}")
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
        
        # Try to provide more diagnostics
        logger.info("Attempting diagnostics for media-ctl failure:")
        try:
            # List available formats
            cmd = [media_ctl_path, "-d", media_dev, "--print-dot"]
            output = subprocess.check_output(cmd, universal_newlines=True, stderr=subprocess.STDOUT)
            logger.info(f"Available formats and connections (dot graph):\n{output}")
        except Exception as diag_e:
            logger.error(f"Diagnostics failed: {diag_e}")
        
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
    channel_count = lsl_config.get('channel_count', 4)  # Updated to 4 channels
    nominal_srate = lsl_config.get('nominal_srate', 100)
    
    # Create channel format
    channel_format = pylsl.cf_double64  # Use double precision for all channels
    
    # Create channel names - Added trigger_source as 4th channel
    channel_names = ["CaptureTimeUnix", "ntfy_notification_active", "session_frame_no", "trigger_source"]
    
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
    
    # First test if basic libcamera-vid works
    logger.info("Testing basic libcamera-vid functionality...")
    test_cmd = [
        libcamera_vid_path,
        "--list-cameras"
    ]
    try:
        logger.info(f"Running test command: {' '.join(test_cmd)}")
        output = subprocess.check_output(test_cmd, universal_newlines=True, stderr=subprocess.STDOUT)
        logger.info(f"libcamera-vid test output:\n{output}")
    except subprocess.CalledProcessError as e:
        logger.error(f"Error testing libcamera-vid: {e}")
        logger.error(f"Output: {e.output if hasattr(e, 'output') else 'No output'}")
    
    # Test with simple capture
    logger.info("Testing simple capture with libcamera-vid...")
    test_cmd = [
        libcamera_vid_path,
        "--width", str(width),
        "--height", str(height),
        "--framerate", str(fps),
        "--timeout", "1000",  # 1 second timeout
        "--output", "/dev/null"
    ]
    try:
        logger.info(f"Running test capture: {' '.join(test_cmd)}")
        output = subprocess.check_output(test_cmd, universal_newlines=True, stderr=subprocess.STDOUT)
        logger.info(f"libcamera-vid test capture output:\n{output}")
    except subprocess.CalledProcessError as e:
        logger.error(f"Error testing simple capture: {e}")
        logger.error(f"Output: {e.output if hasattr(e, 'output') else 'No output'}")
        logger.warning("Will proceed with full command but expect issues...")
    
    # Build libcamera-vid command
    cmd = [
        libcamera_vid_path,
        "--width", str(width),
        "--height", str(height),
        "--framerate", str(fps),
        "--shutter", str(exposure_time_us),
        "--denoise", "cdn_off",
        "--save-pts", pts_file_path,
        "--inline",
        "--flush",
        "-o", "-"  # Output to stdout
    ]
    
    # Add timeout to commands to ensure they don't hang
    cmd.insert(1, "--timeout")
    cmd.insert(2, "0")  # 0 means run indefinitely
    
    # Check if global-shutter flag is supported
    try:
        help_cmd = [libcamera_vid_path, "--help"]
        help_output = subprocess.check_output(help_cmd, universal_newlines=True, stderr=subprocess.STDOUT)
        if "--global-shutter" in help_output:
            logger.info("--global-shutter flag is supported, adding to command")
            cmd.insert(1, "--global-shutter")  # Add after the command path
        else:
            logger.warning("--global-shutter flag not found in help output, skipping")
            logger.info("Available options from help:\n" + help_output)
    except subprocess.CalledProcessError as e:
        logger.error(f"Error checking libcamera-vid help: {e}")
    
    logger.info(f"Starting libcamera-vid with command: {' '.join(cmd)}")
    logger.info(f"Using RAM buffer of {buffer_duration_sec} seconds (max {max_frames} frames)")
    
    try:
        # Simplify command for better stability
        simplified_cmd = [
            libcamera_vid_path,
            "--width", str(width),
            "--height", str(height),
            "--framerate", str(fps),
            "--timeout", "0",
            "-o", "-"  # Output to stdout
        ]
        
        # Try the simplified command first
        logger.info(f"Starting libcamera-vid with simplified command: {' '.join(simplified_cmd)}")
        
        libcamera_vid_process = subprocess.Popen(
            simplified_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=10*1024*1024  # Use a large buffer
        )
        
        # Start stderr reader thread to capture log messages
        stderr_thread = threading.Thread(
            target=log_stderr_output,
            args=(libcamera_vid_process.stderr, "libcamera-vid-simple"),
            daemon=True
        )
        stderr_thread.start()
        
        # Check if process started successfully
        time.sleep(1)
        if libcamera_vid_process.poll() is not None:
            logger.error(f"libcamera-vid simplified command failed with code {libcamera_vid_process.returncode}")
            # Fall back to more basic command
            basic_cmd = [
                libcamera_vid_path,
                "-o", "-"  # Output to stdout
            ]
            logger.info(f"Trying most basic command: {' '.join(basic_cmd)}")
            
            libcamera_vid_process = subprocess.Popen(
                basic_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=10*1024*1024
            )
            
            # Check if even this works
            time.sleep(1)
            if libcamera_vid_process.poll() is not None:
                logger.error(f"Basic libcamera-vid command also failed with code {libcamera_vid_process.returncode}")
                logger.error("Camera capture cannot proceed. Check camera connection and libcamera setup.")
                return
        
        # Record start time for timestamp calculation
        start_time = time.time()
        
        # Initialize variables for frame collection
        current_frame = bytearray()
        frame_start_marker = b'\x00\x00\x00\x01'  # H.264 NAL unit start code
        frame_count = 0
        last_pts_read_time = 0
        pts_data = []
        
        # Create simulated frames for testing LSL if camera fails to produce real ones
        use_simulated_frames = False
        if use_simulated_frames:
            logger.info("Using simulated frames for LSL testing")
            # Start a thread to generate simulated frames
            sim_thread = threading.Thread(
                target=simulate_frames,
                args=(frame_buffer, config),
                daemon=True
            )
            sim_thread.start()
        
        # Track time for FPS calculation
        last_fps_time = time.time()
        last_fps_count = 0
        
        # Main loop for reading frames
        logger.info("Camera capture started, buffering frames to RAM")
        
        while not stop_event.is_set():
            # Check if process is still running
            if libcamera_vid_process.poll() is not None:
                logger.error("libcamera-vid process terminated unexpectedly")
                if not use_simulated_frames:
                    # Switch to simulated frames
                    logger.info("Switching to simulated frames mode")
                    use_simulated_frames = True
                    sim_thread = threading.Thread(
                        target=simulate_frames,
                        args=(frame_buffer, config),
                        daemon=True
                    )
                    sim_thread.start()
                time.sleep(0.1)  # Short sleep before checking again
                continue
            
            # Read a chunk of data
            try:
                chunk = libcamera_vid_process.stdout.read(4096)
                if not chunk:
                    logger.warning("No data from libcamera-vid, will retry")
                    time.sleep(0.1)
                    continue
                
                # Process chunk as before
                if frame_start_marker in chunk:
                    if current_frame:
                        marker_pos = chunk.find(frame_start_marker)
                        current_frame.extend(chunk[:marker_pos])
                        
                        # Keep track of frame count
                        frame_count += 1
                        
                        # Store in buffer
                        frame_time = time.time()
                        frame_buffer.append((frame_time, bytes(current_frame)))
                        
                        # Process the frame
                        process_frame(bytes(current_frame), frame_count, start_time, frame_buffer, pts_data)
                        
                        # Start a new frame
                        current_frame = bytearray(chunk[marker_pos:])
                    else:
                        # First frame
                        current_frame.extend(chunk)
                else:
                    current_frame.extend(chunk)
                
                # Calculate FPS
                if time.time() - last_fps_time >= 1.0:
                    current_fps = frame_count - last_fps_count
                    last_fps_count = frame_count
                    last_fps_time = time.time()
                    logger.info(f"Current FPS: {current_fps}")
                
                # Log buffer status periodically
                if frame_count % 100 == 0:
                    buffer_size = len(frame_buffer)
                    logger.info(f"Captured {frame_count} frames, buffer contains {buffer_size} frames")
                    
                    # Send LSL data sample for dashboard to see
                    if lsl_outlet:
                        sample = [time.time(), float(recording_event.is_set()), float(frame_count), float(last_trigger_source)]
                        lsl_outlet.push_sample(sample)
                        logger.info(f"LSL output: {sample}")
            except Exception as e:
                logger.error(f"Error reading from libcamera-vid: {e}")
                time.sleep(0.1)
        
        logger.info("Camera thread stopping...")
        
    except Exception as e:
        logger.error(f"Error in camera thread: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
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

def simulate_frames(frame_buffer, config):
    """Generate simulated frames for testing when real camera fails."""
    logger = logging.getLogger('imx296_capture')
    logger.info("Starting simulated frame generator")
    
    frame_count = 0
    
    # Create a simple pattern frame
    width = config['camera']['width']
    height = config['camera']['height']
    pattern_frame = bytearray([0x00, 0x00, 0x00, 0x01] + [0x67, 0x42, 0x00, 0x0A] * 100)  # Fake h264 header + some data
    
    while not stop_event.is_set():
        # Create timestamp for the frame
        frame_time = time.time()
        
        # Add to buffer
        frame_buffer.append((frame_time, bytes(pattern_frame)))
        
        # Process frame
        frame_count += 1
        process_frame(bytes(pattern_frame), frame_count, time.time() - 10, frame_buffer, [])
        
        # Log periodically
        if frame_count % 100 == 0:
            buffer_size = len(frame_buffer)
            logger.info(f"Generated {frame_count} simulated frames, buffer contains {buffer_size} frames")
        
        # Sleep to control frame rate
        time.sleep(1.0 / config['camera']['fps'])
    
    logger.info("Simulated frame generator stopped")

def process_frame(frame_data, frame_num, start_time, frame_buffer, pts_data):
    """Process a frame from libcamera-vid."""
    global session_frame_counter, frame_queue, last_trigger_source
    
    # Generate timestamp for the frame
    frame_timestamp = find_timestamp_for_frame(frame_num, pts_data, start_time)
    
    # Store frame in buffer as (timestamp, frame_data) tuple
    frame_buffer.append((frame_timestamp, frame_data))
    
    # If recording is active, add frame to the output queue
    if recording_event.is_set():
        # Increment session frame counter for this recording
        session_frame_counter += 1
        
        try:
            # Add to frame queue for writing to file
            frame_queue.put((frame_timestamp, frame_data), block=False)
            
            # Log frame count periodically
            if session_frame_counter % 100 == 0:
                logger = logging.getLogger('imx296_capture')
                # Updated to include trigger_source
                data = [frame_timestamp, int(recording_event.is_set()), session_frame_counter, last_trigger_source]
                logger.info(f"LSL output: {data}")
        except queue.Full:
            # If queue is full, we're probably too slow to write frames, log warning
            logger = logging.getLogger('imx296_capture')
            logger.warning(f"Frame queue full ({frame_queue.qsize()}/{frame_queue.maxsize}), dropping frame")
    
    # Send metadata to LSL regardless of recording status
    if lsl_outlet:
        # Prepare sample: [unix_timestamp, recording_active, frame_number, trigger_source]
        sample = [frame_timestamp, float(recording_event.is_set()), float(frame_num), float(last_trigger_source)]
        
        # Send the data
        try:
            lsl_outlet.push_sample(sample, frame_timestamp)
            
            # Periodically log the LSL data being sent for debugging
            if frame_num % 100 == 0 or (recording_event.is_set() and session_frame_counter % 10 == 0):
                logger = logging.getLogger('imx296_capture')
                logger.info(f"LSL data sent: timestamp={frame_timestamp:.3f}, recording={int(recording_event.is_set())}, "
                           f"frame={frame_num}, trigger_source={last_trigger_source}")
        except Exception as e:
            logger = logging.getLogger('imx296_capture')
            logger.error(f"Error sending LSL data: {e}")
    
    return frame_timestamp

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
    logger.info(f"Started {process_name} stderr reader thread")
    
    # Buffer for collecting lines
    line_buffer = []
    for line in stderr:
        try:
            line_str = line.decode('utf-8', errors='replace').strip()
            if line_str:
                logger.debug(f"{process_name}: {line_str}")
                line_buffer.append(line_str)
        except Exception as e:
            logger.error(f"Error decoding {process_name} stderr: {e}")
    
    # Log a summary when the process exits
    logger.info(f"{process_name} process exited, last 10 stderr lines:")
    for i, line in enumerate(line_buffer[-10:]):
        logger.info(f"{process_name} stderr[{i}]: {line}")

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
    global is_recording_active, session_frame_counter, frame_queue, last_trigger_source
    
    logger = logging.getLogger('imx296_capture')
    
    # If already recording, ignore
    if is_recording_active:
        logger.info("Already recording, ignoring start notification")
        return
    
    logger.info("Handling 'start' notification - beginning recording")
    
    # Set trigger source to ntfy
    last_trigger_source = 1
    
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
    global is_recording_active, last_trigger_source
    
    logger = logging.getLogger('imx296_capture')
    
    # If not recording, ignore
    if not is_recording_active:
        logger.info("Not recording, ignoring stop notification")
        return
    
    logger.info("Handling 'stop' notification - ending recording")
    
    # Set trigger source to ntfy
    last_trigger_source = 1
    
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
# Keyboard Trigger Detection
# =============================================================================

def keyboard_trigger_thread(config):
    """Thread to monitor for keyboard trigger marker files created by the dashboard."""
    global is_recording_active, last_trigger_source
    
    logger = logging.getLogger('imx296_capture')
    logger.info("Starting keyboard trigger monitor thread")
    
    # Look for marker files with pattern /tmp/camera_recording_*_$PID.tmp
    marker_pattern = "/tmp/camera_recording_*_*.tmp"
    
    while not stop_event.is_set():
        try:
            # Check for start marker files
            start_markers = glob.glob("/tmp/camera_recording_start_*.tmp")
            if start_markers:
                logger.info(f"Found keyboard start marker: {start_markers[0]}")
                
                # Set trigger source to keyboard before starting recording
                last_trigger_source = 2
                logger.info(f"Setting trigger source to KEYBOARD (2)")
                
                # If not already recording, start recording
                if not is_recording_active:
                    logger.info("Starting recording via keyboard trigger")
                    # Don't use handle_start_notification as it would set trigger_source to 1
                    start_recording_keyboard(config)
                
                # Remove the marker
                for marker in start_markers:
                    try:
                        os.remove(marker)
                        logger.debug(f"Removed start marker: {marker}")
                    except:
                        logger.warning(f"Failed to remove start marker: {marker}")
            
            # Check for stop marker files
            stop_markers = glob.glob("/tmp/camera_recording_stop_*.tmp")
            if stop_markers:
                logger.info(f"Found keyboard stop marker: {stop_markers[0]}")
                
                # Set trigger source to keyboard
                last_trigger_source = 2
                logger.info(f"Setting trigger source to KEYBOARD (2)")
                
                # If recording, stop recording
                if is_recording_active:
                    logger.info("Stopping recording via keyboard trigger")
                    # Don't use handle_stop_notification as it would set trigger_source to 1
                    stop_recording_keyboard()
                
                # Remove the marker
                for marker in stop_markers:
                    try:
                        os.remove(marker)
                        logger.debug(f"Removed stop marker: {marker}")
                    except:
                        logger.warning(f"Failed to remove stop marker: {marker}")
            
        except Exception as e:
            logger.error(f"Error in keyboard trigger thread: {e}")
        
        # Sleep briefly before checking again
        time.sleep(0.2)
    
    logger.info("Keyboard trigger thread exited")

def start_recording_keyboard(config):
    """Start recording from keyboard trigger."""
    global is_recording_active, session_frame_counter, frame_queue, last_trigger_source
    
    logger = logging.getLogger('imx296_capture')
    
    # If already recording, ignore
    if is_recording_active:
        logger.info("Already recording, ignoring keyboard start")
        return
    
    logger.info("Handling keyboard start trigger - beginning recording")
    
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
    
    # Send a test LSL sample to show in dashboard
    if lsl_outlet:
        sample = [time.time(), 1.0, 0.0, 2.0]  # timestamp, recording=true, frame=0, trigger=keyboard
        lsl_outlet.push_sample(sample)
        logger.info(f"Sent LSL start marker: {sample}")
    
    logger.info("Recording started via keyboard")

def stop_recording_keyboard():
    """Stop recording from keyboard trigger."""
    global is_recording_active, last_trigger_source
    
    logger = logging.getLogger('imx296_capture')
    
    # If not recording, ignore
    if not is_recording_active:
        logger.info("Not recording, ignoring keyboard stop")
        return
    
    logger.info("Handling keyboard stop trigger - ending recording")
    
    # Stop recording
    is_recording_active = False
    recording_event.clear()
    
    # Send a test LSL sample to show in dashboard
    if lsl_outlet:
        sample = [time.time(), 0.0, float(session_frame_counter), 2.0]  # timestamp, recording=false, frame=current, trigger=keyboard
        lsl_outlet.push_sample(sample)
        logger.info(f"Sent LSL stop marker: {sample}")
    
    logger.info("Recording stopped via keyboard")

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
    
    try:
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
            
            # Start keyboard trigger thread
            logger.info("Starting keyboard trigger thread...")
            keyboard_thread_obj = threading.Thread(
                target=keyboard_trigger_thread,
                args=(config,),
                daemon=True
            )
            keyboard_thread_obj.start()
            
            # Main thread just waits for stop event
            logger.info("System ready and listening for notifications (ntfy and keyboard)")
            while not stop_event.is_set():
                time.sleep(0.1)
            
            # Wait for threads to exit
            logger.info("Waiting for threads to exit...")
            ntfy_thread_obj.join(timeout=10)
            camera_thread_obj.join(timeout=10)
            keyboard_thread_obj.join(timeout=10)
            
        except Exception as e:
            logger.error(f"Unhandled exception in main: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return 1
        finally:
            # Clean up resources
            cleanup()
            logger.info("IMX296 Global Shutter Camera Capture System exited")
        
        return 0
    except Exception as e:
        print(f"Critical error before logging was setup: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main()) 