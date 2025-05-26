#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IMX296 Global Shutter Camera Capture System

This module provides the main camera capture functionality for the IMX296 Global Shutter camera
using the GScrop shell script for frame capture with precise LSL timestamping.
Integrated with service management, ntfy.sh remote control, and dashboard monitoring.

Author: Anzal KS <anzal.ks@gmail.com>
Date: May 26, 2025
"""

import os
import sys
import time
import threading
import subprocess
import logging
import queue
import datetime
import signal
import re
from pathlib import Path
import pylsl
import yaml

# Global variables for threading coordination
stop_event = threading.Event()
frame_queue = queue.Queue(maxsize=10000)

class GSCropCameraCapture:
    """
    GScrop-based camera capture with LSL integration.
    
    This class wraps the GScrop shell script to provide frame capture
    with precise LSL timestamping, integrated with the main branch's
    service infrastructure.
    """
    
    def __init__(self, config):
        """Initialize the GScrop capture system."""
        self.config = config
        self.logger = logging.getLogger('imx296_capture')
        self.lsl_outlet = None
        self.camera_process = None
        self.lsl_thread = None
        self.monitor_thread = None
        self.recording_active = False
        self.frame_count = 0
        self.frames_processed = 0
        self.start_time = None
        
        # Camera settings from config
        self.width = config['camera']['width']
        self.height = config['camera']['height']
        self.fps = config['camera']['fps']
        self.exposure_us = config['camera'].get('exposure_time_us', 5000)
        
        # GScrop-specific settings
        self.markers_file = config['camera'].get('markers_file', '/dev/shm/camera_markers.txt')
        self.frame_queue_size = config['camera'].get('frame_queue_size', 10000)
        
        # Output settings
        self.output_dir = Path(config['recording']['output_dir'])
        self.output_dir.mkdir(exist_ok=True)
        
        # GScrop script path
        self.gscrop_path = self._find_gscrop_script()
        
        # Initialize LSL outlet
        self._setup_lsl()
        
        self.logger.info(f"IMX296 capture initialized: {self.width}x{self.height}@{self.fps}fps")
    
    def _find_gscrop_script(self):
        """Find the GScrop script in the project."""
        # Get script path from config
        script_path = self.config['camera'].get('script_path', 'bin/GScrop')
        
        # Look for GScrop script in common locations
        script_locations = [
            script_path,
            "./GScrop",
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), script_path)
        ]
        
        for location in script_locations:
            if os.path.isfile(location) and os.access(location, os.X_OK):
                self.logger.info(f"Found GScrop script at: {location}")
                return os.path.abspath(location)
        
        # If not found, raise an error
        raise FileNotFoundError("GScrop script not found. Please ensure bin/GScrop exists and is executable.")
    
    def _setup_lsl(self):
        """Setup LSL outlet for frame timing data."""
        try:
            lsl_config = self.config.get('lsl', {})
            stream_name = lsl_config.get('name', 'IMX296Camera_GScrop')
            stream_type = lsl_config.get('type', 'VideoEvents')
            source_id = lsl_config.get('id', 'gscrop_cam')
            
            # Create stream info with frame number channel
            info = pylsl.StreamInfo(
                name=stream_name,
                type=stream_type,
                channel_count=1,  # Only frame number
                nominal_srate=self.fps,
                channel_format=pylsl.cf_double64,
                source_id=source_id
            )
            
            # Add channel description
            channels = info.desc().append_child("channels")
            channels.append_child("channel").append_child_value("label", "FrameNumber")
            
            # Create outlet with larger chunk size for better performance
            self.lsl_outlet = pylsl.StreamOutlet(info, chunk_size=64, max_buffered=self.fps*8)
            self.logger.info(f"LSL outlet '{stream_name}' created successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to create LSL outlet: {e}")
            self.lsl_outlet = None
    
    def _push_lsl_sample(self, frame_number, timestamp):
        """Push a frame sample to LSL."""
        if self.lsl_outlet:
            try:
                self.lsl_outlet.push_sample([float(frame_number)], timestamp)
                self.frames_processed += 1
            except Exception as e:
                self.logger.error(f"Error pushing LSL sample: {e}")
    
    def _monitor_markers_file(self):
        """Monitor the markers file created by GScrop for frame timing data."""
        self.logger.info(f"Starting markers file monitoring: {self.markers_file}")
        
        # Wait for markers file to be created
        while not stop_event.is_set() and not os.path.exists(self.markers_file):
            time.sleep(0.1)
        
        if stop_event.is_set():
            return
        
        last_pos = 0
        last_frame = 0
        
        # Start LSL worker thread
        self.lsl_thread = threading.Thread(target=self._lsl_worker_thread, daemon=True)
        self.lsl_thread.start()
        
        while not stop_event.is_set() and self.recording_active:
            try:
                if not os.path.exists(self.markers_file):
                    time.sleep(0.1)
                    continue
                
                with open(self.markers_file, 'r') as f:
                    # Seek to last read position
                    f.seek(last_pos)
                    new_lines = f.readlines()
                    
                    if new_lines:
                        last_pos = f.tell()
                        
                        for line in new_lines:
                            line = line.strip()
                            if not line or line.startswith(("Starting", "Recording", "CONFIG", "COMMAND", "ERROR", "MEDIA_DEVICE")):
                                continue
                            
                            # Parse frame number and timestamp
                            try:
                                parts = line.split()
                                if len(parts) >= 2:
                                    frame_num = int(parts[0])
                                    frame_time = float(parts[1])
                                    
                                    # Only process new frames
                                    if frame_num > last_frame:
                                        frame_queue.put((frame_num, frame_time))
                                        last_frame = frame_num
                                        self.frame_count = frame_num
                                        
                            except (ValueError, IndexError) as e:
                                self.logger.debug(f"Error parsing markers line '{line}': {e}")
                
                # Minimal sleep for responsiveness
                time.sleep(0.001)
                
            except Exception as e:
                self.logger.warning(f"Error monitoring markers file: {e}")
                time.sleep(0.1)
        
        self.logger.info(f"Stopped monitoring markers file after {self.frame_count} frames")
    
    def _lsl_worker_thread(self):
        """Worker thread to process frames from queue and send to LSL."""
        self.logger.info("LSL worker thread started")
        
        while not stop_event.is_set() or not frame_queue.empty():
            try:
                # Get frame data from queue
                try:
                    frame_num, frame_time = frame_queue.get(timeout=0.1)
                    self._push_lsl_sample(frame_num, frame_time)
                    frame_queue.task_done()
                except queue.Empty:
                    continue
                    
            except Exception as e:
                self.logger.warning(f"Error in LSL worker thread: {e}")
        
        self.logger.info(f"LSL worker thread finished after processing {self.frames_processed} frames")
    
    def start_recording(self, duration_seconds=None, output_filename=None):
        """Start recording using GScrop script."""
        if self.recording_active:
            self.logger.warning("Recording already active")
            return False
        
        try:
            # Generate output filename if not provided
            if output_filename is None:
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                output_filename = f"gscrop_{self.width}x{self.height}_{self.fps}fps_{timestamp}"
            
            # Full output path
            output_path = self.output_dir / output_filename
            
            # Convert duration to milliseconds (GScrop expects ms)
            duration_ms = int(duration_seconds * 1000) if duration_seconds else 0
            
            # Build GScrop command
            cmd = [
                self.gscrop_path,
                str(self.width),
                str(self.height), 
                str(self.fps),
                str(duration_ms),
                str(self.exposure_us),
                str(output_path)
            ]
            
            self.logger.info(f"Starting GScrop recording: {' '.join(cmd)}")
            
            # Set environment variables if needed
            env = os.environ.copy()
            
            # Clear any existing markers file
            if os.path.exists(self.markers_file):
                os.remove(self.markers_file)
            
            # Start the camera process
            self.camera_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                cwd=os.path.dirname(self.gscrop_path)
            )
            
            self.recording_active = True
            self.start_time = time.time()
            self.frame_count = 0
            self.frames_processed = 0
            
            # Start monitoring markers file
            self.monitor_thread = threading.Thread(target=self._monitor_markers_file, daemon=True)
            self.monitor_thread.start()
            
            self.logger.info("GScrop recording started successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start GScrop recording: {e}")
            self.recording_active = False
            return False
    
    def stop_recording(self):
        """Stop the recording."""
        if not self.recording_active:
            self.logger.warning("No recording active to stop")
            return
        
        self.logger.info("Stopping GScrop recording...")
        self.recording_active = False
        
        # Terminate camera process
        if self.camera_process and self.camera_process.poll() is None:
            self.camera_process.terminate()
            try:
                self.camera_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.camera_process.kill()
                self.camera_process.wait()
        
        # Wait for monitoring thread to finish
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=2)
        
        # Wait for LSL worker to finish processing queue
        if self.lsl_thread and self.lsl_thread.is_alive():
            frame_queue.join()  # Wait for queue to be empty
            self.lsl_thread.join(timeout=2)
        
        # Log statistics
        if self.start_time:
            duration = time.time() - self.start_time
            actual_fps = self.frame_count / duration if duration > 0 else 0
            self.logger.info(f"Recording completed: {self.frame_count} frames in {duration:.2f}s ({actual_fps:.1f} fps)")
            self.logger.info(f"LSL samples sent: {self.frames_processed}")
    
    def is_recording(self):
        """Check if recording is currently active."""
        return self.recording_active
    
    def get_stats(self):
        """Get current recording statistics."""
        if not self.start_time:
            return None
            
        current_time = time.time()
        duration = current_time - self.start_time
        actual_fps = self.frame_count / duration if duration > 0 else 0
        
        return {
            'recording_active': self.recording_active,
            'frame_count': self.frame_count,
            'frames_processed': self.frames_processed,
            'duration': duration,
            'actual_fps': actual_fps,
            'target_fps': self.fps,
            'queue_size': frame_queue.qsize()
        }
    
    def cleanup(self):
        """Clean up resources."""
        self.logger.info("Cleaning up GScrop capture...")
        
        # Stop recording if active
        if self.recording_active:
            self.stop_recording()
        
        # Clean up markers file
        if os.path.exists(self.markers_file):
            try:
                os.remove(self.markers_file)
            except Exception as e:
                self.logger.warning(f"Could not remove markers file: {e}")


def signal_handler(sig, frame):
    """Handle interrupt signals gracefully."""
    logger = logging.getLogger('imx296_capture')
    logger.info(f"Received signal {sig}, stopping...")
    stop_event.set()


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
    
    # Clear existing handlers
    logger.handlers.clear()
    
    # Create handlers
    if log_config.get('console', True):
        console_handler = logging.StreamHandler()
        console_handler.setLevel(log_level)
        console_handler.setFormatter(logging.Formatter(log_format))
        logger.addHandler(console_handler)
    
    if log_file:
        from logging.handlers import RotatingFileHandler
        max_size = log_config.get('max_size_mb', 10) * 1024 * 1024  # Convert to bytes
        backup_count = log_config.get('backup_count', 5)
        file_handler = RotatingFileHandler(
            log_file, maxBytes=max_size, backupCount=backup_count
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(logging.Formatter(log_format))
        logger.addHandler(file_handler)
    
    return logger


def load_config(config_file="config/config.yaml"):
    """Load configuration from YAML file."""
    logger = logging.getLogger('imx296_capture')
    
    # Try the local config file first, then fallback to other locations
    config_locations = [
        os.path.join(os.getcwd(), "config/config.yaml"),
        config_file,
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "config/config.yaml")
    ]
    
    # Try each location
    for loc in config_locations:
        try:
            if os.path.exists(loc):
                with open(loc, 'r') as f:
                    config = yaml.safe_load(f)
                logger.info(f"Successfully loaded config from: {loc}")
                return config
        except Exception as e:
            logger.warning(f"Error loading config from {loc}: {e}")
    
    # If we get here, all locations failed - create default config
    logger.warning("Failed to load config from any location, using default values")
    
    # Create a basic default config
    default_config = {
        'system': {
            'media_ctl_path': "/usr/bin/media-ctl",
            'ffmpeg_path': "/usr/bin/ffmpeg"
        },
        'camera': {
            'width': 400,
            'height': 400,
            'fps': 100,
            'exposure_time_us': 5000,
            'script_path': 'bin/GScrop',
            'markers_file': '/dev/shm/camera_markers.txt',
            'frame_queue_size': 10000,
            'lsl_worker_threads': 1,
            'media_ctl': {
                'device_pattern': "/dev/media%d",
                'entity_pattern': "imx296",
                'bayer_format': "SBGGR10_1X10"
            }
        },
        'buffer': {
            'duration_seconds': 5,
            'max_frames': 500
        },
        'lsl': {
            'name': "IMX296Camera",
            'type': "VideoEvents",
            'id': "cam1"
        },
        'recording': {
            'output_dir': "recordings",
            'video_format': "mkv",
            'codec': "mjpeg",
            'quality': 90
        },
        'ntfy': {
            'server': "https://ntfy.sh",
            'topic': "raspie-camera-dawg-123",
            'poll_interval_sec': 2
        },
        'logging': {
            'level': "DEBUG",
            'console': True,
            'file': "logs/imx296_capture.log",
            'max_size_mb': 10,
            'backup_count': 5
        }
    }
    
    # Try to save the default config locally
    try:
        os.makedirs("config", exist_ok=True)
        with open("config/config.yaml", 'w') as f:
            yaml.dump(default_config, f)
        logger.info(f"Created default config at: config/config.yaml")
    except Exception as e:
        logger.warning(f"Could not create default config: {e}")
    
    return default_config


def main():
    """Main function to run the IMX296 capture system."""
    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Load configuration
    config = load_config()
    
    # Set up logging
    logger = setup_logging(config)
    logger.info("Starting IMX296 Global Shutter Camera Capture System")
    logger.info(f"Configuration loaded: {config['camera']['width']}x{config['camera']['height']}@{config['camera']['fps']}fps")
    
    try:
        # Create capture instance
        capture = GSCropCameraCapture(config)
        
        logger.info("Camera capture system initialized successfully")
        logger.info("System ready for recording commands")
        logger.info("Press Ctrl+C to exit")
        
        # Keep the program running
        try:
            while not stop_event.is_set():
                time.sleep(1)
                
                # Display basic stats if recording
                if capture.is_recording():
                    stats = capture.get_stats()
                    if stats:
                        logger.info(
                            f"Recording: {stats['frame_count']} frames, "
                            f"{stats['actual_fps']:.1f} fps, "
                            f"Queue: {stats['queue_size']}"
                        )
                        
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt")
            
    except Exception as e:
        logger.error(f"Error in main: {e}", exc_info=True)
        return 1
    finally:
        # Cleanup
        if 'capture' in locals():
            capture.cleanup()
        logger.info("IMX296 capture system stopped")
    
    return 0


# Test/example usage
if __name__ == "__main__":
    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Load configuration
    config_file = "config/config.yaml"
    if len(sys.argv) > 1:
        config_file = sys.argv[1]
    
    try:
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)
    except Exception as e:
        print(f"Error loading config: {e}")
        sys.exit(1)
    
    # Create capture instance
    try:
        capture = GSCropCameraCapture(config)
        
        # Start recording for 10 seconds
        if capture.start_recording(duration_seconds=10):
            print("Recording started... Press Ctrl+C to stop early")
            
            # Wait for recording to complete or user interrupt
            try:
                while capture.is_recording() and not stop_event.is_set():
                    stats = capture.get_stats()
                    if stats:
                        print(f"Frames: {stats['frame_count']}, FPS: {stats['actual_fps']:.1f}, Queue: {stats['queue_size']}")
                    time.sleep(1)
            except KeyboardInterrupt:
                pass
            
            capture.stop_recording()
        else:
            print("Failed to start recording")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if 'capture' in locals():
            capture.cleanup() 