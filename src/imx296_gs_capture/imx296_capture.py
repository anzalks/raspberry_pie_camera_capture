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
lsl_has_string_support = False

# =============================================================================
# Configuration Management
# =============================================================================

def load_config(config_file="config/config.yaml"):
    """Load configuration from YAML file."""
    try:
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)
        
        # Set defaults for video format if not specified
        if 'recording' in config:
            if 'video_format' not in config['recording']:
                config['recording']['video_format'] = 'mkv'
            if 'codec' not in config['recording']:
                config['recording']['codec'] = 'mjpeg'
        
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

    # Important note: According to the logs, the IMX296 sensor format is 400x400-SBGGR10_1X10
    # We need to make sure we use this format instead of trying to crop to a larger size
    
    # Use 400x400 as the target size since that's what the sensor actually supports
    target_width = 400
    target_height = 400
    
    # Calculate crop coordinates to center the 400x400 window in the sensor if needed
    sensor_width = config['camera'].get('sensor_width', 1456)  # Default to full sensor
    sensor_height = config['camera'].get('sensor_height', 1088)  # Default to full sensor
    
    # Center the crop in the sensor
    crop_x = (sensor_width - target_width) // 2
    crop_y = (sensor_height - target_height) // 2
    
    # Use SBGGR10_1X10 as the bayer format since that's what's reported in the logs
    bayer_format = config['camera']['media_ctl'].get('bayer_format', 'SBGGR10_1X10')
    
    # Log the configuration we're about to apply
    logger.info(f"Configuring IMX296 camera on {media_dev}")
    logger.info(f"Entity: {entity_name}")
    logger.info(f"Using native sensor format: {target_width}x{target_height}")
    logger.info(f"Format: {bayer_format}")
    
    # Construct and execute the media-ctl command
    try:
        # Try multiple media-ctl commands with different syntax to find one that works
        commands = [
            # Direct 400x400 format without cropping
            [media_ctl_path, "-d", media_dev, "--set-v4l2", f'"{entity_name}":0[fmt:{bayer_format}/{target_width}x{target_height}]'],
            
            # Without quotes around entity name
            [media_ctl_path, "-d", media_dev, "--set-v4l2", f'{entity_name}:0[fmt:{bayer_format}/{target_width}x{target_height}]'],
            
            # With explicit crop parameter
            [media_ctl_path, "-d", media_dev, "--set-v4l2", f'{entity_name}:0[fmt:{bayer_format}/{target_width}x{target_height} crop:(0,0)/{target_width}x{target_height}]'],
            
            # Using centered crop from sensor
            [media_ctl_path, "-d", media_dev, "--set-v4l2", f'{entity_name}:0[fmt:{bayer_format}/{sensor_width}x{sensor_height} crop:({crop_x},{crop_y})/{target_width}x{target_height}]']
        ]
        
        # Try each command until one works
        success = False
        for i, cmd in enumerate(commands):
            logger.info(f"Trying media-ctl command (attempt {i+1}): {' '.join(cmd)}")
            try:
                output = subprocess.check_output(cmd, universal_newlines=True, stderr=subprocess.STDOUT)
                logger.info(f"media-ctl success, output: {output}")
                success = True
                break
            except subprocess.CalledProcessError as e:
                logger.warning(f"Command failed: {e}")
                logger.warning(f"Output: {e.output if hasattr(e, 'output') else 'No output'}")
                continue
        
        # If all standard attempts failed, try a more basic approach
        if not success:
            logger.warning("All standard media-ctl commands failed. Trying simplified approach.")
            try:
                # Get the basic sensor configuration without cropping
                cmd = [media_ctl_path, "-d", media_dev, "--set-v4l2", f'{entity_name}:0[fmt:{bayer_format}]']
                subprocess.check_output(cmd, universal_newlines=True, stderr=subprocess.STDOUT)
                logger.info("Successfully set basic format without crop.")
                success = True
            except subprocess.CalledProcessError as e:
                logger.error(f"Basic format setting also failed: {e}")
        
        # Verify the configuration
        cmd_verify = [media_ctl_path, "-d", media_dev, "-p"]
        verify_output = subprocess.check_output(cmd_verify, universal_newlines=True)
        logger.debug(f"media-ctl verification output: {verify_output}")
        
        # Look for the verification in the output 
        if f"{target_width}x{target_height}" in verify_output or "400x400" in verify_output:
            logger.info(f"✅ Verified: Camera is correctly configured with 400x400 format")
        else:
            logger.warning(f"⚠️ Could not verify 400x400 in media-ctl output")
        
        # Optional: Run libcamera-hello to verify the crop
        verify_with_libcamera_hello(config)
        
        return success
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
    """Set up LSL stream for camera frames metadata."""
    global lsl_outlet, lsl_has_string_support
    
    try:
        # Import pylsl
        import pylsl
    except ImportError:
        logger = logging.getLogger('imx296_capture')
        logger.warning("PyLSL not found. Streaming will be disabled.")
        return None
    
    # Create a new LSL stream info
    logger = logging.getLogger('imx296_capture')
    logger.info("Creating LSL stream for camera metadata")
    
    # Stream name from config or default
    stream_name = config.get('lsl', {}).get('name', 'CameraFrames')
    stream_type = config.get('lsl', {}).get('type', 'VideoMetadata')
    stream_id = config.get('lsl', {}).get('id', 'cam1')
    
    # Define the stream info - only numeric values supported (no strings)
    try:
        # Define channel format - always floats for reliability
        channel_format = pylsl.cf_double  # Always use double precision to avoid type issues
        
        # Create stream info with full numeric channel info
        stream_info = pylsl.StreamInfo(
            name=stream_name,
            type=stream_type,
            channel_count=4,  # [timestamp, recording_active, frame_count, trigger_source]
            nominal_srate=config.get('fps', 30),  # Expected sample rate based on camera FPS
            channel_format=channel_format,
            source_id=stream_id
        )
        
        # Add metadata to the stream to describe the channels
        channels = stream_info.desc().append_child("channels")
        channels.append_child("channel").append_child_value("label", "timestamp").append_child_value("type", "time").append_child_value("unit", "s")
        channels.append_child("channel").append_child_value("label", "recording").append_child_value("type", "status").append_child_value("unit", "bool")
        channels.append_child("channel").append_child_value("label", "frame").append_child_value("type", "index").append_child_value("unit", "count")
        channels.append_child("channel").append_child_value("label", "trigger").append_child_value("type", "code").append_child_value("unit", "id")
        
        # Add description of trigger source codes in stream metadata
        trigger_codes = stream_info.desc().append_child("trigger_codes")
        trigger_codes.append_child_value("0", "none")
        trigger_codes.append_child_value("1", "ntfy")
        trigger_codes.append_child_value("2", "keyboard")
        
        # Create outlet
        lsl_outlet = pylsl.StreamOutlet(stream_info)
        logger.info(f"Created LSL stream: {stream_name} ({stream_type})")
        
        # Now, check if we can even send a test message
        sample = [time.time(), 0.0, 0.0, 0.0]  # All numeric: timestamp, not recording, frame 0, no trigger
        lsl_outlet.push_sample(sample)
        logger.info("Sent test LSL sample successfully")
        
        # Return the outlet for use
        return lsl_outlet
    
    except Exception as e:
        logger.error(f"Error creating LSL stream: {e}")
        return None

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
        
        # Check if output contains IMX296 or any camera
        if "imx296" not in output.lower():
            # Check if any camera is detected - sometimes the name is different
            if "camera" in output.lower() or "available" in output.lower():
                logger.warning("IMX296 camera not specifically found, but a camera was detected. Will try to use it.")
            else:
                logger.error("No camera detected by libcamera-vid. Check camera connection.")
                return
    except subprocess.CalledProcessError as e:
        logger.error(f"Error testing libcamera-vid: {e}")
        logger.error(f"Output: {e.output if hasattr(e, 'output') else 'No output'}")
        logger.error("Will try to continue anyway, in case the camera is available but command output is unexpected.")
    
    # Test with simple capture with adjusted parameters
    logger.info("Testing simple capture with libcamera-vid...")
    test_cmd = [
        libcamera_vid_path,
        "--width", str(width),
        "--height", str(height),
        "--framerate", str(fps),
        "--timeout", "1000",  # 1 second timeout
        "--codec", "mjpeg",   # Use MJPEG codec for better compatibility
        "--output", "/tmp/test_capture.mkv",  # Use MKV format for better compatibility
        "--nopreview",  # Add this to prevent display issues
        "--inline"      # Add inline for better format handling
    ]
    
    # Try increasing timeout before running capture
    time.sleep(2)
    
    try:
        logger.info(f"Running test capture: {' '.join(test_cmd)}")
        output = subprocess.check_output(test_cmd, universal_newlines=True, stderr=subprocess.STDOUT)
        logger.info(f"libcamera-vid test capture output:\n{output}")
        # Clean up the test file
        try:
            if os.path.exists("/tmp/test_capture.mkv"):
                os.remove("/tmp/test_capture.mkv")
        except:
            pass
    except subprocess.CalledProcessError as e:
        logger.error(f"Error testing simple capture: {e}")
        logger.error(f"Output: {e.output if hasattr(e, 'output') else 'No output'}")
        
        # Try a more basic capture approach with other parameters
        try:
            logger.warning("Trying simpler capture command with raw format...")
            basic_cmd = [
                libcamera_vid_path,
                "--timeout", "1000",         # 1 second timeout
                "--codec", "mjpeg",          # Use MJPEG codec
                "--output", "/tmp/test_capture.mkv",  # Use MKV container
                "--nopreview",
                "--inline"                   # Use inline for better format handling
            ]
            output = subprocess.check_output(basic_cmd, universal_newlines=True, stderr=subprocess.STDOUT)
            logger.info(f"Raw format test output:\n{output}")
            
            # If we get here, basic capture worked, so we can try the main capture
            logger.info("Basic camera test succeeded, proceeding with main capture")
        except subprocess.CalledProcessError as e2:
            # Also try with direct V4L2 access
            try:
                logger.warning("Direct V4L2 frame grab attempt...")
                for i in range(10):
                    dev_path = f"/dev/video{i}"
                    if os.path.exists(dev_path):
                        v4l2_cmd = ["v4l2-ctl", "-d", dev_path, "--set-fmt-video=width=400,height=400", "--stream-mmap", "--stream-count=1"]
                        subprocess.run(v4l2_cmd, timeout=3, capture_output=True)
                logger.info("V4L2 direct access test completed - proceeding with main command")
            except Exception as v4l2_e:
                logger.error(f"V4L2 direct test also failed: {v4l2_e}")
                # Continue anyway as a final attempt
    
    # Build libcamera-vid command
    cmd = [
        libcamera_vid_path,
        "--width", str(width),
        "--height", str(height),
        "--framerate", str(fps),
        "--shutter", str(exposure_time_us),
        "--denoise", "cdn_off",
        "--save-pts", pts_file_path,
        "--codec", "mjpeg",  # Use MJPEG codec for better compatibility
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
        # Calculate exposure time based on framerate standards
        logger.info(f"Calculating exposure time based on framerate: {fps} fps")
        
        # For IMX296, exposure should be limited to frame period
        # Maximum exposure time = 1000000/fps microseconds 
        # But set to 80% of max to be safe
        exposure_time = min(exposure_time_us, int(0.8 * 1000000 / fps))
        logger.info(f"Using calculated exposure time of {exposure_time} µs")
        
        # Simplify command for better stability - add adjusted exposure
        simplified_cmd = [
            libcamera_vid_path,
            "--width", str(width),
            "--height", str(height),
            "--framerate", str(fps),
            "--shutter", str(exposure_time),  # Use calculated exposure
            "--timeout", "0",
            "--nopreview",  # Add nopreview to avoid display issues
            "--codec", "mjpeg",  # Use MJPEG codec for better compatibility
            "--inline",  # Important for proper output
            "-o", "-"  # Output to stdout
        ]

        # Try also with v4l2-ctl to reset the camera before starting
        try:
            # Reset any existing v4l2 devices that might be causing the issue
            reset_cmd = ["v4l2-ctl", "--all"]
            logger.info(f"Resetting v4l2 devices before starting: {' '.join(reset_cmd)}")
            subprocess.run(reset_cmd, timeout=5, capture_output=True)
            
            # Try an alternative reset method
            for i in range(10):
                dev_path = f"/dev/video{i}"
                if os.path.exists(dev_path):
                    try:
                        reset_dev_cmd = ["v4l2-ctl", "-d", dev_path, "-c", "timeout_value=3000"]
                        subprocess.run(reset_dev_cmd, timeout=2, capture_output=True)
                    except:
                        pass
        except Exception as e:
            logger.warning(f"Error resetting v4l2 devices: {e}")
            # Continue anyway
        
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
        frame_start_marker = b'\xFF\xD8'  # JPEG SOI marker for MJPEG streams
        frame_end_marker = b'\xFF\xD9'    # JPEG EOI marker
        frame_count = 0
        last_pts_read_time = 0
        pts_data = []
        
        # Track time for FPS calculation
        last_fps_time = time.time()
        last_fps_count = 0
        
        # Main loop for reading frames
        logger.info("Camera capture started, buffering frames to RAM")
        
        while not stop_event.is_set():
            # Check if process is still running
            if libcamera_vid_process.poll() is not None:
                logger.error("libcamera-vid process terminated unexpectedly")
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
                        sample = [time.time(), float(recording_event.is_set()), float(frame_count), get_trigger_source_string(last_trigger_source)]
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

def process_frame(frame_data, frame_num, start_time, frame_buffer, pts_data):
    """Process a frame from libcamera-vid."""
    global session_frame_counter, frame_queue, last_trigger_source, lsl_has_string_support
    
    # Generate timestamp for the frame
    frame_timestamp = find_timestamp_for_frame(frame_num, pts_data, start_time)
    
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
                # Convert trigger source numeric code to string (for log display only)
                trigger_str = get_trigger_source_string(last_trigger_source)
                # Log the data that's being sent - using string format for display
                logger.info(f"Frame: {session_frame_counter}, Trigger: {trigger_str} ({last_trigger_source})")
        except queue.Full:
            # If queue is full, we're probably too slow to write frames, log warning
            logger = logging.getLogger('imx296_capture')
            logger.warning(f"Frame queue full ({frame_queue.qsize()}/{frame_queue.maxsize}), dropping frame")
    
    # Send metadata to LSL regardless of recording status
    if lsl_outlet:
        # Prepare sample - NUMERIC ONLY for LSL
        try:
            # Always ensure trigger source is numeric
            numeric_trigger = get_numeric_trigger_source(last_trigger_source)
            
            # Format all values as floats for LSL
            sample = [
                float(frame_timestamp),             # timestamp as double
                float(recording_event.is_set()),    # recording status as float (0.0 or 1.0)
                float(frame_num),                   # frame number as float
                float(numeric_trigger)              # trigger source as numeric code
            ]
            
            # Send the data with timestamp
            lsl_outlet.push_sample(sample, float(frame_timestamp))
            
            # Periodically log the LSL data being sent for debugging
            if frame_num % 100 == 0:
                logger = logging.getLogger('imx296_capture')
                logger.debug(f"LSL data: timestamp={frame_timestamp:.3f}, recording={int(recording_event.is_set())}, "
                           f"frame={frame_num}, trigger={numeric_trigger}")
        except Exception as e:
            # If we hit an LSL error, log it but don't crash
            logger = logging.getLogger('imx296_capture')
            logger.error(f"Error sending LSL data: {e}")
            # Try one more time with completely safe types
            try:
                safe_sample = [float(frame_timestamp), 
                              0.0 if not recording_event.is_set() else 1.0, 
                              float(frame_num), 
                              float(get_numeric_trigger_source(last_trigger_source))]
                lsl_outlet.push_sample(safe_sample)
                logger.debug("Sent fallback LSL data")
            except Exception as e2:
                logger.error(f"Error sending fallback LSL data: {e2}")
    
    return frame_timestamp

def find_timestamp_for_frame(frame_num, pts_data, start_time):
    """Find the timestamp for a given frame from PTS data."""
    # If we have PTS data, use it
    for pts_frame_num, pts_us, wall_time in pts_data:
        if pts_frame_num == frame_num:
            return wall_time
    
    # Fallback: use current time
    return time.time()

def get_trigger_source_string(numeric_code):
    """Convert numeric trigger source code to string format for logging."""
    # This function should return string values for logging purposes
    if numeric_code == 1 or numeric_code == 1.0:
        return 'ntfy'  # notification trigger
    elif numeric_code == 2 or numeric_code == 2.0:
        return 'keyboard'  # keyboard trigger
    else:
        return 'unknown'  # unknown/none

def get_numeric_trigger_source(code):
    """Ensure the trigger source is always a floating point number for LSL."""
    # Always return a numeric value
    if isinstance(code, (int, float)):
        return float(code)
    elif code == 'ntfy' or code == 'n':
        return 1.0
    elif code == 'keyboard' or code == 'k':
        return 2.0
    else:
        return 0.0  # unknown/default

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
    format_ext = config['recording'].get('video_format', 'mkv')  # Default to MKV format
    codec = config['recording'].get('codec', 'mjpeg')  # Default to MJPEG codec
    
    # Ensure output directory exists with proper permissions
    try:
        # Expand user directory (handles ~/ notation)
        output_dir = os.path.expanduser(output_dir)
        
        # Verify if directory exists
        if not os.path.exists(output_dir):
            logger.warning(f"Recording directory does not exist: {output_dir}")
            try:
                # Create directory with all parent directories
                os.makedirs(output_dir, exist_ok=True)
                logger.info(f"Successfully created recording directory: {output_dir}")
            except PermissionError:
                logger.error(f"Permission denied creating directory: {output_dir}")
                # Try alternative directories
                alt_dirs = [
                    "/tmp/recordings",  # /tmp is usually writeable
                    os.path.expanduser("~/recordings"),  # Home directory
                    os.path.join(os.getcwd(), "recordings")  # Current working directory
                ]
                
                for alt_dir in alt_dirs:
                    try:
                        logger.warning(f"Trying alternative directory: {alt_dir}")
                        os.makedirs(alt_dir, exist_ok=True)
                        if os.access(alt_dir, os.W_OK):
                            output_dir = alt_dir
                            logger.info(f"Using alternative directory: {output_dir}")
                            break
                    except:
                        continue
        
        # Now set permissions if we have access
        try:
            os.chmod(output_dir, 0o777)  # Make sure directory is writeable
            logger.info(f"Set permissions on directory: {output_dir}")
        except PermissionError:
            logger.warning(f"Cannot set permissions on {output_dir}, but directory exists")
            # Continue anyway as long as directory exists
            
        # Final check if directory exists and is writeable
        if not os.path.exists(output_dir):
            logger.error(f"Directory still doesn't exist: {output_dir}")
            output_dir = "/tmp"  # Fallback to /tmp as last resort
            logger.warning(f"Falling back to {output_dir}")
        elif not os.access(output_dir, os.W_OK):
            logger.error(f"Directory exists but is not writeable: {output_dir}")
            output_dir = "/tmp"  # Fallback to /tmp as last resort
            logger.warning(f"Falling back to {output_dir}")
                
    except Exception as e:
        logger.error(f"Error handling output directory: {e}")
        output_dir = "/tmp"  # Final fallback
        logger.warning(f"Using {output_dir} as final fallback")
    
    # Create absolute path for output file
    output_file = os.path.join(os.path.abspath(output_dir), f"recording_{timestamp}.{format_ext}")
    logger.info(f"Will write to absolute path: {output_file}")
    
    # Verify that the directory is writable
    test_file = os.path.join(os.path.abspath(output_dir), "write_test.tmp")
    try:
        with open(test_file, 'wb') as f:
            f.write(b'\0')  # Write a single byte
        os.chmod(test_file, 0o666)
        os.remove(test_file)
        logger.info(f"Successfully verified write access to {output_dir}")
    except Exception as e:
        logger.error(f"Error verifying write access to output directory: {e}")
        # Try /tmp as fallback
        output_dir = "/tmp"
        output_file = f"/tmp/recording_{timestamp}.{format_ext}"
        logger.info(f"Using fallback path: {output_file}")
    
    # Create the file and set permissions with improved error handling
    try:
        # Use os.open to create the file with correct permissions from the start
        fd = os.open(output_file, os.O_CREAT | os.O_WRONLY, 0o666)
        os.close(fd)
        logger.info(f"Created output file with proper permissions: {output_file}")
    except Exception as e:
        logger.error(f"Error creating output file {output_file}: {e}")
        try:
            # Try alternative approach - create in /tmp
            output_file = f"/tmp/recording_{timestamp}.{format_ext}"
            logger.warning(f"Using fallback path: {output_file}")
            
            fd = os.open(output_file, os.O_CREAT | os.O_WRONLY, 0o666)
            os.close(fd)
            logger.info(f"Created fallback file: {output_file}")
        except Exception as e2:
            logger.error(f"Failed to create fallback file too: {e2}")
            # Last resort: use a truly temporary file
            try:
                tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=f".{format_ext}")
                tmp_file.close()
                output_file = tmp_file.name
                logger.warning(f"Using temporary file as last resort: {output_file}")
            except Exception as e3:
                logger.error(f"All file creation methods failed: {e3}")
                return  # Cannot proceed without a file
    
    # Configure FFmpeg command with optimized settings for robust recording
    ffmpeg_path = config['system']['ffmpeg_path']
    
    # Determine input format based on codec
    input_format = "mjpeg" if codec == "mjpeg" else "h264"
    
    # Use ffmpeg command with appropriate settings for the codec and container
    cmd = [
        ffmpeg_path,
        "-f", input_format,        # Input format based on codec
        "-i", "-",                 # Input from stdin
        "-c:v", "copy",            # Copy video codec (no re-encoding)
        "-an",                     # No audio
        "-y",                      # Overwrite output file if exists
        output_file                # Output file (.mkv)
    ]
    
    logger.info(f"Starting ffmpeg with command: {' '.join(cmd)}")
    logger.info(f"Recording to file: {output_file}")
    
    # Send notification to LSL and logs about recording start with file info
    logger.info(f"RECORDING_STARTED: file={output_file}")
    
    # Create the process and send key frames first
    try:
        ffmpeg_process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,  # Capture stdout for debugging
            stderr=subprocess.PIPE,
            bufsize=10*1024*1024  # 10MB buffer
        )
        
        # Start stderr reader thread to capture ffmpeg log messages
        stderr_thread = threading.Thread(
            target=log_stderr_output,
            args=(ffmpeg_process.stderr, "ffmpeg"),
            daemon=True
        )
        stderr_thread.start()
        
        # Start stdout reader thread to capture ffmpeg output messages
        stdout_thread = threading.Thread(
            target=log_stderr_output,
            args=(ffmpeg_process.stdout, "ffmpeg-out"),
            daemon=True
        )
        stdout_thread.start()
        
        # Write frames from queue to ffmpeg's stdin
        frame_count = 0
        last_log_time = time.time()
        
        # Main loop for writing frames
        while is_recording_active or not frame_queue.empty():
            try:
                # Get a frame from the queue with timeout
                timestamp, frame_data = frame_queue.get(timeout=0.1)
                
                # Debug: log first few frames
                if frame_count < 5:
                    logger.info(f"Writing frame {frame_count}, size: {len(frame_data)} bytes")
                    
                # Write frame to ffmpeg
                try:
                    ffmpeg_process.stdin.write(frame_data)
                    ffmpeg_process.stdin.flush()  # Ensure data is sent immediately
                    frame_count += 1
                except IOError as e:
                    logger.error(f"IOError writing to ffmpeg: {e}")
                    # Try to recover by checking file size and restarting if needed
                    file_size = os.path.getsize(output_file)
                    logger.error(f"Current file size: {file_size} bytes")
                    
                    if file_size == 0:
                        logger.error("File size is 0, trying to restart ffmpeg")
                        try:
                            ffmpeg_process.terminate()
                            ffmpeg_process = subprocess.Popen(
                                cmd,
                                stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                bufsize=10*1024*1024
                            )
                            # Start new reader threads
                            stderr_thread = threading.Thread(
                                target=log_stderr_output,
                                args=(ffmpeg_process.stderr, "ffmpeg-restart"),
                                daemon=True
                            )
                            stderr_thread.start()
                            stdout_thread = threading.Thread(
                                target=log_stderr_output,
                                args=(ffmpeg_process.stdout, "ffmpeg-out-restart"),
                                daemon=True
                            )
                            stdout_thread.start()
                            logger.info("Restarted ffmpeg process")
                        except Exception as restart_e:
                            logger.error(f"Failed to restart ffmpeg: {restart_e}")
                    continue
                
                # Log progress and check file size frequently to ensure it's growing
                current_time = time.time()
                if current_time - last_log_time > 0.5:  # Check every half second
                    # Check file size
                    file_size = os.path.getsize(output_file)
                    logger.info(f"Recording progress: {frame_count} frames, file size: {file_size/1024:.1f}KB")
                    
                    # Debug: Verify file is actually growing
                    if file_size > 0:
                        logger.info(f"✓ File is growing properly: {output_file}")
                    else:
                        logger.warning(f"⚠ File size is still 0 after {frame_count} frames!")
                        
                    last_log_time = current_time
                
            except queue.Empty:
                # No frames available but recording is still active
                if is_recording_active:
                    time.sleep(0.01)  # Short sleep
                else:
                    # Recording stopped and queue is empty
                    logger.info("No more frames to write, finalizing video")
                    break
        
        # Finalize the recording
        logger.info("Closing ffmpeg stdin to finalize recording")
        ffmpeg_process.stdin.close()
        
        # Wait with timeout
        try:
            ffmpeg_process.wait(timeout=10)
            logger.info("ffmpeg process completed successfully")
        except subprocess.TimeoutExpired:
            logger.warning("ffmpeg process did not exit in time, forcing termination")
            ffmpeg_process.terminate()
            try:
                ffmpeg_process.wait(timeout=5)
            except:
                ffmpeg_process.kill()
        
        # Verify the final file
        file_size = os.path.getsize(output_file)
        logger.info(f"Recording complete: {frame_count} frames, final size: {file_size/1024:.1f}KB")
        
        if file_size == 0:
            logger.error("ERROR: Recording file is empty (0 bytes)")
            # Try to diagnose why file is empty
            logger.error("Diagnosing empty file issue...")
            try:
                # Check if directory is writable
                dirname = os.path.dirname(output_file)
                logger.error(f"Directory permissions for {dirname}: {oct(os.stat(dirname).st_mode)}")
                
                # Check ffmpeg version
                ffmpeg_ver_cmd = [ffmpeg_path, "-version"]
                ffmpeg_ver = subprocess.check_output(ffmpeg_ver_cmd, universal_newlines=True)
                logger.error(f"FFmpeg version: {ffmpeg_ver.splitlines()[0]}")
                
                # Try to write a simple test file directly with ffmpeg
                test_out = f"/tmp/ffmpeg_test_{timestamp}.mp4"
                test_cmd = [
                    ffmpeg_path, 
                    "-f", "lavfi", 
                    "-i", "testsrc=duration=1:size=320x240:rate=30", 
                    "-c:v", "libx264",
                    test_out
                ]
                try:
                    subprocess.run(test_cmd, timeout=5, capture_output=True)
                    test_size = os.path.getsize(test_out) if os.path.exists(test_out) else 0
                    logger.error(f"FFmpeg test file size: {test_size} bytes")
                except Exception as test_e:
                    logger.error(f"FFmpeg test error: {test_e}")
            except Exception as diag_e:
                logger.error(f"Diagnostics error: {diag_e}")
        elif file_size < 1024:
            logger.warning(f"WARNING: Recording file is very small ({file_size} bytes)")
        
        # Make sure the file has the right permissions 
        os.chmod(output_file, 0o666)
        
        # Send notification to LSL and logs about recording completion with file info
        logger.info(f"RECORDING_COMPLETED: file={output_file}, size={file_size}, frames={frame_count}")
        
    except Exception as e:
        logger.error(f"Error in video writer thread: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
    finally:
        # Clean up
        if ffmpeg_process and ffmpeg_process.poll() is None:
            try:
                ffmpeg_process.stdin.close()
            except:
                pass
            try:
                ffmpeg_process.terminate()
                ffmpeg_process.wait(timeout=5)
            except:
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
                last_trigger_source = 2  # Use numeric code (2) for keyboard
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
                last_trigger_source = 2  # Use numeric code (2) for keyboard
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
    
    # Set trigger source before starting recording - ensure it's numeric
    last_trigger_source = 2.0  # keyboard as float
    
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
        try:
            # All values must be numeric
            sample = [time.time(), 1.0, 0.0, 2.0]  # timestamp, recording=true, frame=0, trigger=keyboard
            lsl_outlet.push_sample(sample)
            logger.info(f"Sent LSL start marker: {sample}")
        except Exception as e:
            logger.error(f"Error sending LSL start marker: {e}")
    
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
    
    # Set trigger source to numeric value
    last_trigger_source = 2.0  # keyboard as float
    
    # Stop recording
    is_recording_active = False
    recording_event.clear()
    
    # Send a test LSL sample to show in dashboard
    if lsl_outlet:
        try:
            # All values must be numeric
            sample = [time.time(), 0.0, float(session_frame_counter), 2.0]  # timestamp, recording=false, frame=current, trigger=keyboard
            lsl_outlet.push_sample(sample)
            logger.info(f"Sent LSL stop marker: {sample}")
        except Exception as e:
            logger.error(f"Error sending LSL stop marker: {e}")
    
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

def update_recordings_list():
    """Update a global list of recent recordings and their info."""
    logger = logging.getLogger('imx296_capture')
    try:
        # Load config to get recording directory
        config = load_config()
        output_dir = config['recording']['output_dir']
        
        # Expand user path if needed
        output_dir = os.path.expanduser(output_dir)
        
        # Check if directory exists
        if not os.path.isdir(output_dir):
            logger.warning(f"Recording directory does not exist: {output_dir}")
            
            # Try to create it automatically
            try:
                os.makedirs(output_dir, exist_ok=True)
                logger.info(f"Created recording directory: {output_dir}")
                
                # Set permissions if possible
                try:
                    os.chmod(output_dir, 0o777)
                except Exception as perm_e:
                    logger.warning(f"Could not set permissions on created directory: {perm_e}")
            except Exception as e:
                logger.error(f"Failed to create recording directory: {e}")
                return
            
            # Check again if directory now exists
            if not os.path.isdir(output_dir):
                logger.error("Directory could not be created. Cannot update recordings list.")
                return
        
        # Find all MKV files in the directory
        recording_files = []
        try:
            for file in os.listdir(output_dir):
                if file.endswith('.mkv') or file.endswith('.mp4'):
                    file_path = os.path.join(output_dir, file)
                    try:
                        # Get file stats
                        stats = os.stat(file_path)
                        file_size = stats.st_size
                        mod_time = stats.st_mtime
                        
                        recording_files.append({
                            'path': file_path,
                            'name': file,
                            'size': file_size,
                            'time': mod_time
                        })
                    except Exception as e:
                        logger.error(f"Error getting stats for {file_path}: {e}")
        except Exception as list_e:
            logger.error(f"Error listing directory contents: {list_e}")
            return
        
        # Sort by modification time (newest first)
        recording_files.sort(key=lambda x: x['time'], reverse=True)
        
        # Log the most recent files
        logger.info(f"Found {len(recording_files)} recording files")
        for i, file in enumerate(recording_files[:3]):
            size_str = f"{file['size'] / 1024 / 1024:.2f} MB" if file['size'] > 0 else "0 bytes"
            time_str = datetime.datetime.fromtimestamp(file['time']).strftime('%Y-%m-%d %H:%M:%S')
            logger.info(f"Recent recording {i+1}: {file['name']} ({size_str}) - {time_str}")
    
    except Exception as e:
        logger.error(f"Error updating recordings list: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")

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
        
        # Log system information
        logger.info(f"Python version: {sys.version}")
        logger.info(f"System: {os.uname().sysname} {os.uname().release}")
        
        # Get username safely without os.getlogin()
        try:
            import pwd
            username = pwd.getpwuid(os.getuid()).pw_name
        except:
            username = "unknown"
        
        logger.info(f"Running as user: {os.getuid()} / {username}")
        logger.info(f"Working directory: {os.getcwd()}")
        
        # Check output directory
        output_dir = config['recording']['output_dir']
        output_dir = os.path.expanduser(output_dir)  # Handle ~ in path
        
        # Create output directory with better error handling
        logger.info(f"Checking recording directory: {output_dir}")
        create_recording_dir(output_dir, logger)
        
        # Log existing recordings
        update_recordings_list()
        
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
                time.sleep(1.0)
                
                # Periodically send LSL heartbeat data
                if lsl_outlet:
                    try:
                        current_time = time.time()
                        # Make sure all values are numbers - fix the error with trigger_source
                        if lsl_has_string_support:
                            trigger_str = get_trigger_source_string(last_trigger_source)
                            sample = [float(current_time), float(recording_event.is_set()), -1.0, trigger_str]
                        else:
                            # All numeric version
                            sample = [float(current_time), float(recording_event.is_set()), -1.0, float(last_trigger_source)]
                        
                        lsl_outlet.push_sample(sample)
                        logger.debug(f"Sent LSL heartbeat at {current_time}")
                    except Exception as e:
                        logger.error(f"Error sending LSL heartbeat: {e}")
                        # Try a safer approach with explicit numeric types
                        try:
                            sample = [float(current_time), float(recording_event.is_set()), float(-1), float(last_trigger_source)]
                            lsl_outlet.push_sample(sample)
                            logger.debug("Sent fallback LSL heartbeat")
                        except Exception as e2:
                            logger.error(f"Error sending fallback LSL heartbeat: {e2}")
                
                # Periodically update recording files list
                update_recordings_list()
            
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

# Add a new helper function for directory creation
def create_recording_dir(dir_path, logger):
    """Create recording directory with proper error handling and permissions."""
    try:
        # Ensure path is absolute
        dir_path = os.path.abspath(os.path.expanduser(dir_path))
        
        if os.path.isdir(dir_path):
            logger.info(f"Recording directory exists: {dir_path}")
            
            # Check if writable
            if os.access(dir_path, os.W_OK):
                logger.info(f"Directory is writable: {dir_path}")
            else:
                logger.warning(f"Directory exists but is not writable: {dir_path}")
                try:
                    os.chmod(dir_path, 0o777)  # Try to set permissions
                    logger.info(f"Set permissions on existing directory: {dir_path}")
                except Exception as e:
                    logger.error(f"Failed to set permissions: {e}")
        else:
            logger.warning(f"Creating output directory: {dir_path}")
            try:
                # Create with parents
                os.makedirs(dir_path, exist_ok=True)
                
                # Set permissions
                try:
                    os.chmod(dir_path, 0o777)
                    logger.info(f"Created directory with full permissions: {dir_path}")
                except Exception as perm_e:
                    logger.warning(f"Created directory but couldn't set permissions: {perm_e}")
                
                # Verify creation
                if not os.path.isdir(dir_path):
                    logger.error(f"Failed to create directory despite no errors: {dir_path}")
                    return False
                    
                # Test write access with a file
                test_file = os.path.join(dir_path, ".write_test")
                try:
                    with open(test_file, 'w') as f:
                        f.write("test")
                    os.remove(test_file)
                    logger.info(f"Successfully verified write access to new directory")
                except Exception as test_e:
                    logger.error(f"Directory created but not writable: {test_e}")
                    return False
                    
                logger.info(f"Successfully created and verified directory: {dir_path}")
                return True
                
            except Exception as e:
                logger.error(f"Failed to create directory {dir_path}: {e}")
                return False
                
        return True
    except Exception as e:
        logger.error(f"Unexpected error handling directory {dir_path}: {e}")
        return False

if __name__ == "__main__":
    sys.exit(main()) 