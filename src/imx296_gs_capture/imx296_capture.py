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
import collections
import json
from pathlib import Path
from typing import Dict, Any, Optional

# Optional system monitoring
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    psutil = None
    PSUTIL_AVAILABLE = False

# Add project root to Python path - dynamic detection from actual file location
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

# Change working directory to project root for consistent file access
original_cwd = os.getcwd()
os.chdir(project_root)

# Log the dynamic paths for debugging
if __name__ == "__main__":
    print(f"Dynamic path detection:")
    print(f"  Script location: {Path(__file__).resolve()}")
    print(f"  Project root: {project_root}")
    print(f"  Working directory: {os.getcwd()}")
    print(f"  Original CWD: {original_cwd}")

try:
    import pylsl
except ImportError:
    pylsl = None

try:
    import yaml
except ImportError:
    yaml = None

from .ntfy_handler import NtfyHandler
from .video_recorder import VideoRecorder

# Global variables for threading coordination
stop_event = threading.Event()
frame_queue = queue.Queue(maxsize=10000)

# Status file for monitoring
STATUS_FILE = "/dev/shm/imx296_status.json"

class GSCropCameraCapture:
    """
    GScrop-based camera capture with LSL integration and rolling buffer.
    
    This class wraps the GScrop shell script to provide frame capture
    with precise LSL timestamping, integrated with the main branch's
    service infrastructure and includes a pre-trigger rolling buffer.
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
        
        # Trigger tracking for LSL
        self.last_trigger_time = 0.0
        self.last_trigger_type = 0  # 0=none, 1=keyboard, 2=ntfy
        
        # Status tracking for monitor
        self.service_start_time = time.time()
        self.trigger_count = 0
        self.last_lsl_sample = [0, 0, 0]
        self.lsl_samples_sent = 0
        self.status_update_thread = None
        self.status_update_active = False
        
        self.ntfy_handler = None
        self.video_recorder = None
        
        # Camera settings from config
        self.width = config['camera']['width']
        self.height = config['camera']['height']
        self.fps = config['camera']['fps']
        self.exposure_us = config['camera'].get('exposure_time_us', 5000)
        
        # GScrop-specific settings
        self.markers_file = config['camera'].get('markers_file', '/dev/shm/camera_markers.txt')
        self.frame_queue_size = config['camera'].get('frame_queue_size', 10000)
        
        # Rolling buffer settings
        buffer_config = config.get('buffer', {})
        self.buffer_duration = buffer_config.get('duration_seconds', 15)
        self.buffer_max_frames = buffer_config.get('max_frames', 1500)
        
        # Initialize rolling buffer
        self.rolling_buffer = collections.deque(maxlen=self.buffer_max_frames)
        self.buffer_active = False
        self.buffer_thread = None
        
        # Output settings
        self.output_dir = Path(config['recording']['output_dir'])
        self.output_dir.mkdir(exist_ok=True)
        
        # Auto-detect camera if enabled
        if config['camera'].get('auto_detect', True):
            self._auto_detect_camera()
        
        # GScrop script path
        self.gscrop_path = self._find_gscrop_script()
        
        # Initialize LSL outlet (independent of trigger mode)
        if pylsl:
            self._setup_lsl()
            self._start_independent_lsl_streaming()
        else:
            self.logger.warning("pylsl not available - LSL streaming disabled")
        
        # Initialize ntfy handler
        ntfy_config = self.config.get('ntfy', {})
        if ntfy_config.get('server') and ntfy_config.get('topic'):
            try:
                self.ntfy_handler = NtfyHandler(
                    ntfy_config,
                    self._handle_ntfy_command
                )
                self.logger.info("ntfy handler initialized")
            except Exception as e:
                self.logger.warning(f"Failed to initialize ntfy handler: {e}")
        
        # Initialize video recorder (independent mode)
        recording_config = self.config.get('recording', {})
        if recording_config:
            try:
                # Merge system config into recording config for video recorder
                full_recording_config = {**recording_config, 'system': self.config.get('system', {})}
                self.video_recorder = VideoRecorder(full_recording_config)
                # Start independent video recording
                self._start_independent_video_recording()
                self.logger.info("Video recorder initialized in independent mode")
            except Exception as e:
                self.logger.warning(f"Failed to initialize video recorder: {e}")
        
        # Start rolling buffer immediately
        self.start_rolling_buffer()
        
        # Start status reporting
        self._start_status_reporting()
        
        self.logger.info(f"GScrop camera capture initialized: {self.width}x{self.height}@{self.fps}fps (independent mode)")
    
    def _find_gscrop_script(self):
        """Find the GScrop script in the project using dynamic path detection."""
        # Get script path from config (should be relative to project root)
        script_path = self.config['camera'].get('script_path', 'bin/GScrop')
        
        # Get project root dynamically
        project_root = Path(__file__).resolve().parent.parent.parent
        
        # Look for GScrop script in dynamic locations
        script_locations = [
            # Relative to project root (preferred)
            project_root / script_path,
            # Direct relative path (current working directory)
            Path(script_path),
            # Legacy absolute path if script_path is absolute
            Path(script_path) if os.path.isabs(script_path) else None,
            # Fallback: search in project bin directory
            project_root / "bin" / "GScrop",
            # Fallback: current directory
            Path.cwd() / "GScrop",
            # Fallback: script directory
            Path(__file__).parent / "GScrop"
        ]
        
        # Filter out None values
        script_locations = [loc for loc in script_locations if loc is not None]
        
        for location in script_locations:
            abs_location = location.resolve()
            if abs_location.is_file() and os.access(abs_location, os.X_OK):
                self.logger.info(f"Found GScrop script at: {abs_location}")
                return str(abs_location)
        
        # If not found, provide helpful error message
        self.logger.error("GScrop script not found. Searched in:")
        for location in script_locations:
            self.logger.error(f"  - {location.resolve()}")
        
        raise FileNotFoundError(
            f"GScrop script not found. Please ensure it exists and is executable in one of the expected locations. "
            f"Project root: {project_root}"
        )
    
    def _auto_detect_camera(self):
        """Automatically detect IMX296 camera and configure media pipeline."""
        self.logger.info("Auto-detecting IMX296 camera...")
        
        media_config = self.config['camera'].get('media_ctl', {})
        device_pattern = media_config.get('device_pattern', '/dev/media%d')
        entity_pattern = media_config.get('entity_pattern', 'imx296')
        
        # Search for media devices
        detected_device = None
        for i in range(10):  # Check media0 through media9
            device_path = device_pattern % i
            if os.path.exists(device_path):
                try:
                    # Use media-ctl to check if IMX296 is present
                    result = subprocess.run([
                        'media-ctl', '-d', device_path, '-e', entity_pattern
                    ], capture_output=True, text=True, timeout=5)
                    
                    if result.returncode == 0 and result.stdout.strip():
                        detected_device = device_path
                        self.logger.info(f"Found IMX296 camera on {device_path}")
                        break
                except (subprocess.TimeoutExpired, FileNotFoundError) as e:
                    self.logger.debug(f"Error checking {device_path}: {e}")
                    continue
        
        if not detected_device:
            self.logger.warning("No IMX296 camera detected automatically, using default configuration")
            return
        
        # Configure media pipeline for detected camera
        try:
            bayer_format = media_config.get('bayer_format', 'SBGGR10_1X10')
            
            # Set up media pipeline
            setup_commands = [
                ['media-ctl', '-d', detected_device, '--reset'],
                ['media-ctl', '-d', detected_device, '-l', f'"{entity_pattern} 0":0->"csi2_rx":0[1]'],
                ['v4l2-ctl', '-d', '/dev/video0', '-c', 'exposure=5000'],
                ['v4l2-ctl', '-d', '/dev/video0', '--set-fmt-video', 
                 f'width={self.width},height={self.height},pixelformat={bayer_format}']
            ]
            
            for cmd in setup_commands:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                if result.returncode != 0:
                    self.logger.warning(f"Media setup command failed: {' '.join(cmd)}")
                    self.logger.warning(f"Error: {result.stderr}")
            
            self.logger.info(f"Camera auto-configured: {self.width}x{self.height} @ {bayer_format}")
            
        except Exception as e:
            self.logger.error(f"Failed to auto-configure camera: {e}")
    
    def _setup_lsl(self):
        """Setup LSL outlet for frame timing data."""
        try:
            lsl_config = self.config.get('lsl', {})
            stream_name = lsl_config.get('name', 'IMX296Camera_GScrop')
            stream_type = lsl_config.get('type', 'VideoEvents')
            source_id = lsl_config.get('id', 'gscrop_cam')
            
            # Create stream info with 3 channels: frame_number, trigger_time, trigger_type
            info = pylsl.StreamInfo(
                name=stream_name,
                type=stream_type,
                channel_count=3,  # frame_number, trigger_time, trigger_type
                nominal_srate=self.fps,
                channel_format=pylsl.cf_double64,
                source_id=source_id
            )
            
            # Add channel descriptions
            channels = info.desc().append_child("channels")
            channels.append_child("channel").append_child_value("label", "frame_number") 
            channels.append_child("channel").append_child_value("label", "trigger_time")
            channels.append_child("channel").append_child_value("label", "trigger_type")
            
            # Create outlet with larger chunk size for better performance
            self.lsl_outlet = pylsl.StreamOutlet(info, chunk_size=64, max_buffered=self.fps*8)
            self.logger.info(f"LSL outlet '{stream_name}' created with 3 channels successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to create LSL outlet: {e}")
            self.lsl_outlet = None
    
    def _push_lsl_sample(self, frame_number, timestamp):
        """Push a frame sample to LSL with 3 channels: frame_number, trigger_time, trigger_type."""
        if self.lsl_outlet:
            try:
                # Build sample with 3 channels
                sample = [
                    float(frame_number),              # frame_number
                    float(self.last_trigger_time),    # trigger_time (Unix timestamp)
                    float(self.last_trigger_type)     # trigger_type (0=none, 1=keyboard, 2=ntfy)
                ]
                self.lsl_outlet.push_sample(sample, timestamp)
                self.frames_processed += 1
                
                # Update status tracking
                self.lsl_samples_sent += 1
                self.last_lsl_sample = sample
                
            except Exception as e:
                self.logger.error(f"Error pushing LSL sample: {e}")
    
    def _start_independent_lsl_streaming(self):
        """Start independent LSL streaming that runs continuously."""
        if not self.lsl_outlet:
            return
            
        self.logger.info("Starting independent LSL streaming...")
        # LSL streaming is now handled by the rolling buffer monitoring
        # Each frame captured gets streamed immediately regardless of recording state
    
    def _start_independent_video_recording(self):
        """Start independent video recording that runs continuously."""
        if not self.video_recorder:
            return
            
        try:
            self.logger.info("Starting independent video recording...")
            # Start continuous video recording to a rotating buffer
            video_file = self.video_recorder.start_continuous_recording('/dev/video0')
            if video_file:
                self.logger.info(f"Independent video recording started: {video_file}")
            else:
                self.logger.warning("Failed to start independent video recording")
        except Exception as e:
            self.logger.error(f"Error starting independent video recording: {e}")
    
    def set_trigger(self, trigger_type, trigger_time=None):
        """Set trigger information for LSL streaming.
        
        Args:
            trigger_type: 0=none, 1=keyboard, 2=ntfy
            trigger_time: Unix timestamp, defaults to current time
        """
        if trigger_time is None:
            trigger_time = time.time()
            
        self.last_trigger_time = trigger_time
        self.last_trigger_type = trigger_type
        
        # Count non-zero triggers
        if trigger_type > 0:
            self.trigger_count += 1
        
        self.logger.info(f"Trigger set: type={trigger_type}, time={trigger_time}")
    
    def handle_keyboard_trigger(self, key_command):
        """Handle keyboard trigger events.
        
        Args:
            key_command: String command from keyboard (e.g., 'start_recording', 'stop_recording')
        """
        self.logger.info(f"Keyboard trigger received: {key_command}")
        
        # Set trigger for LSL streaming
        self.set_trigger(trigger_type=1, trigger_time=time.time())  # 1 = keyboard trigger
        
        try:
            if key_command.startswith('start_recording'):
                # Parse duration if provided
                parts = key_command.split()
                duration = None
                if len(parts) > 1:
                    try:
                        duration = float(parts[1])
                    except ValueError:
                        self.logger.warning(f"Invalid duration in keyboard command: {parts[1]}")
                
                success = self.start_recording(duration_seconds=duration)
                self.logger.info(f"Keyboard recording start: {'success' if success else 'failed'}")
                
            elif key_command == 'stop_recording':
                stats = self.stop_recording()
                self.logger.info(f"Keyboard recording stop: {stats.get('frame_count', 0)} frames")
                
            elif key_command == 'status':
                status = self.get_status()
                self.logger.info(f"System status: {status}")
                
            else:
                self.logger.warning(f"Unknown keyboard command: {key_command}")
        
        except Exception as e:
            self.logger.error(f"Error handling keyboard command '{key_command}': {e}")
        
        finally:
            # Reset trigger after processing (small delay to ensure LSL captures it)
            threading.Timer(1.0, lambda: self.set_trigger(trigger_type=0)).start()
    
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
        """Start recording using GScrop script with video recording."""
        if self.recording_active:
            self.logger.warning("Recording already active")
            return False
        
        try:
            # Generate output filename if not provided
            if output_filename is None:
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                output_filename = f"gscrop_{self.width}x{self.height}_{self.fps}fps_{timestamp}"
            
            # Full output path for raw capture
            output_path = self.output_dir / output_filename
            
            # Save rolling buffer contents when recording starts
            buffer_frames_saved = 0
            if self.rolling_buffer:
                buffer_frames_saved = self._save_buffer_to_file(output_path)
                self.logger.info(f"Pre-trigger buffer saved: {buffer_frames_saved} frames")
            
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
            
            # Start video recording if available
            video_file = None
            if self.video_recorder:
                # For now, we'll use /dev/video0 as input source for video recording
                # This can be enhanced later to use the GScrop output or FIFO
                video_file = self.video_recorder.start_recording('/dev/video0', duration_seconds)
                if video_file:
                    self.logger.info(f"Video recording started: {video_file}")
                else:
                    self.logger.warning("Failed to start video recording")
            
            self.recording_active = True
            self.start_time = time.time()
            self.frame_count = 0
            self.frames_processed = 0
            
            # Start monitoring markers file
            self.monitor_thread = threading.Thread(target=self._monitor_markers_file, daemon=True)
            self.monitor_thread.start()
            
            # Start ntfy handler if available
            if self.ntfy_handler and not self.ntfy_handler.running:
                self.ntfy_handler.start()
            
            self.logger.info(f"GScrop recording started successfully (buffer frames: {buffer_frames_saved})")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start GScrop recording: {e}")
            self.recording_active = False
            return False
    
    def stop_recording(self):
        """Stop the recording and return statistics."""
        if not self.recording_active:
            self.logger.warning("No recording active to stop")
            return {}
        
        self.logger.info("Stopping GScrop recording...")
        self.recording_active = False
        
        stats = {}
        
        # Stop video recording first
        if self.video_recorder and self.video_recorder.is_recording():
            video_stats = self.video_recorder.stop_recording()
            stats.update(video_stats)
            self.logger.info("Video recording stopped")
        
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
        
        # Calculate final statistics
        if self.start_time:
            duration = time.time() - self.start_time
            actual_fps = self.frame_count / duration if duration > 0 else 0
            stats.update({
                'frame_count': self.frame_count,
                'duration': duration,
                'actual_fps': actual_fps,
                'frames_processed': self.frames_processed,
                'target_fps': self.fps
            })
            
            self.logger.info(f"Recording completed: {self.frame_count} frames in {duration:.2f}s ({actual_fps:.1f} fps)")
            self.logger.info(f"LSL samples sent: {self.frames_processed}")
        
        return stats
    
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
    
    def get_status(self):
        """Get current system status."""
        current_time = time.time()
        
        status = {
            'is_recording': self.recording_active,
            'frame_count': self.frame_count,
            'frames_processed': self.frames_processed,
            'last_trigger_type': self.last_trigger_type,
            'last_trigger_time': self.last_trigger_time,
        }
        
        if self.start_time:
            status['uptime'] = current_time - self.start_time
            if self.recording_active:
                status['recording_duration'] = current_time - self.start_time
                status['actual_fps'] = self.frame_count / status['recording_duration'] if status['recording_duration'] > 0 else 0
        else:
            status['uptime'] = 0
        
        # Add video recording status if available
        if self.video_recorder:
            video_stats = self.video_recorder.get_stats()
            status.update({
                'video_recording': video_stats.get('recording', False),
                'video_file': video_stats.get('current_file')
            })
        
        return status
    
    def cleanup(self):
        """Clean up resources."""
        self.logger.info("Cleaning up GScrop capture...")
        
        # Stop recording if active
        if self.recording_active:
            self.stop_recording()
        
        # Stop rolling buffer
        if self.buffer_active:
            self.stop_rolling_buffer()
        
        # Stop status reporting
        self._stop_status_reporting()
        
        # Clean up ntfy handler
        if self.ntfy_handler:
            self.ntfy_handler.stop()
            self.logger.info("ntfy handler stopped")
        
        # Clean up video recorder
        if self.video_recorder:
            self.video_recorder.cleanup()
            self.logger.info("Video recorder cleaned up")
        
        # Clean up markers files
        marker_files = [self.markers_file, '/dev/shm/buffer_markers.txt']
        for marker_file in marker_files:
            if os.path.exists(marker_file):
                try:
                    os.remove(marker_file)
                except Exception as e:
                    self.logger.warning(f"Could not remove markers file {marker_file}: {e}")
        
        self.logger.info("Cleanup completed")

    def _handle_ntfy_command(self, command: str, params: Dict[str, Any]):
        """Handle commands received from ntfy notifications."""
        self.logger.info(f"Processing ntfy command: {command} with params: {params}")
        
        # Set trigger for LSL streaming
        self.set_trigger(trigger_type=2, trigger_time=time.time())  # 2 = ntfy trigger
        
        try:
            if command == 'start_recording':
                duration = params.get('duration')
                success = self.start_recording(duration_seconds=duration)
                
                if success and self.ntfy_handler:
                    if self.video_recorder and self.video_recorder.get_current_file():
                        output_file = self.video_recorder.get_current_file()
                    else:
                        output_file = "camera_capture"
                    
                    self.ntfy_handler.send_recording_started(output_file, duration)
                elif self.ntfy_handler:
                    self.ntfy_handler.send_error("Failed to start recording")
            
            elif command == 'stop_recording':
                stats = self.stop_recording()
                if self.ntfy_handler:
                    self.ntfy_handler.send_recording_stopped(stats)
            
            elif command == 'status':
                status = self.get_status()
                if self.ntfy_handler:
                    self.ntfy_handler.send_status(status)
            
            elif command == 'get_stats':
                stats = self.get_stats()
                if self.ntfy_handler:
                    # Send stats as status for now
                    self.ntfy_handler.send_status(stats)
            
            else:
                self.logger.warning(f"Unknown ntfy command: {command}")
                if self.ntfy_handler:
                    self.ntfy_handler.send_error(f"Unknown command: {command}")
        
        except Exception as e:
            self.logger.error(f"Error handling ntfy command '{command}': {e}")
            if self.ntfy_handler:
                self.ntfy_handler.send_error(str(e))
        
        finally:
            # Reset trigger after processing (small delay to ensure LSL captures it)
            threading.Timer(1.0, lambda: self.set_trigger(trigger_type=0)).start()

    def start_rolling_buffer(self):
        """Start the rolling buffer thread."""
        if not self.buffer_active:
            self.buffer_active = True
            self.buffer_thread = threading.Thread(target=self._rolling_buffer_worker, daemon=True)
            self.buffer_thread.start()
            self.logger.info(f"Rolling buffer started: {self.buffer_duration}s / {self.buffer_max_frames} frames")
    
    def stop_rolling_buffer(self):
        """Stop the rolling buffer."""
        self.buffer_active = False
        if self.buffer_thread and self.buffer_thread.is_alive():
            self.buffer_thread.join(timeout=2)
        self.logger.info("Rolling buffer stopped")
    
    def _rolling_buffer_worker(self):
        """Worker thread to continuously capture frames into rolling buffer."""
        self.logger.info("Rolling buffer worker started")
        
        # Start a continuous capture process for buffering
        buffer_markers_file = '/dev/shm/buffer_markers.txt'
        
        while self.buffer_active and not stop_event.is_set():
            try:
                # Start GScrop for continuous capture (duration 0 = infinite)
                cmd = [
                    self.gscrop_path,
                    str(self.width),
                    str(self.height), 
                    str(self.fps),
                    "0",  # Infinite duration for rolling buffer
                    str(self.exposure_us),
                    "/dev/null"  # We don't need the video output for buffer
                ]
                
                # Set custom markers file for buffer
                env = os.environ.copy()
                env['MARKERS_FILE'] = buffer_markers_file
                
                # Clear markers file
                if os.path.exists(buffer_markers_file):
                    os.remove(buffer_markers_file)
                
                self.logger.debug(f"Starting buffer capture: {' '.join(cmd)}")
                
                buffer_process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=env,
                    cwd=os.path.dirname(self.gscrop_path)
                )
                
                # Monitor the buffer markers file
                self._monitor_buffer_markers(buffer_markers_file, buffer_process)
                
                # Clean up process
                if buffer_process.poll() is None:
                    buffer_process.terminate()
                    try:
                        buffer_process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        buffer_process.kill()
                
            except Exception as e:
                self.logger.warning(f"Error in rolling buffer worker: {e}")
                time.sleep(1)  # Wait before retrying
        
        self.logger.info("Rolling buffer worker finished")
    
    def _monitor_buffer_markers(self, markers_file, process):
        """Monitor buffer markers file and maintain rolling buffer."""
        last_pos = 0
        
        while self.buffer_active and not stop_event.is_set() and process.poll() is None:
            try:
                if not os.path.exists(markers_file):
                    time.sleep(0.1)
                    continue
                
                with open(markers_file, 'r') as f:
                    f.seek(last_pos)
                    new_lines = f.readlines()
                    
                    if new_lines:
                        last_pos = f.tell()
                        
                        for line in new_lines:
                            line = line.strip()
                            if not line or line.startswith(("Starting", "Recording", "CONFIG", "COMMAND", "ERROR", "MEDIA_DEVICE")):
                                continue
                            
                            try:
                                parts = line.split()
                                if len(parts) >= 2:
                                    frame_num = int(parts[0])
                                    frame_time = float(parts[1])
                                    
                                    # Add to rolling buffer
                                    self.rolling_buffer.append((frame_num, frame_time))
                                    
                                    # Push to LSL for independent streaming
                                    self._push_lsl_sample(frame_num, frame_time)
                                    
                                    # If recording is active, also send to main queue
                                    if self.recording_active:
                                        try:
                                            frame_queue.put_nowait((frame_num, frame_time))
                                        except queue.Full:
                                            self.logger.warning("Frame queue is full, dropping frame")
                                    
                            except (ValueError, IndexError) as e:
                                self.logger.debug(f"Error parsing buffer markers line '{line}': {e}")
                
                time.sleep(0.001)  # Very small sleep for responsiveness
                
            except Exception as e:
                self.logger.warning(f"Error monitoring buffer markers: {e}")
                time.sleep(0.1)
    
    def _save_buffer_to_file(self, output_path):
        """Save current rolling buffer contents to file."""
        if not self.rolling_buffer:
            self.logger.warning("No buffer contents to save")
            return 0
        
        buffer_file = output_path.parent / f"{output_path.stem}_buffer{output_path.suffix}"
        frames_saved = 0
        
        try:
            with open(buffer_file, 'w') as f:
                f.write("# Pre-trigger buffer frames\n")
                f.write(f"# Buffer duration: {self.buffer_duration}s\n")
                f.write(f"# Frame format: frame_number timestamp\n")
                
                # Save all frames in buffer
                buffer_copy = list(self.rolling_buffer)
                for frame_num, frame_time in buffer_copy:
                    f.write(f"{frame_num} {frame_time}\n")
                    frames_saved += 1
            
            self.logger.info(f"Saved {frames_saved} buffer frames to {buffer_file}")
            
        except Exception as e:
            self.logger.error(f"Failed to save buffer to file: {e}")
        
        return frames_saved

    def _start_status_reporting(self):
        """Start background status reporting thread."""
        self.status_update_active = True
        self.status_update_thread = threading.Thread(target=self._status_update_worker, daemon=True)
        self.status_update_thread.start()
        self.logger.info("Status reporting started")
    
    def _stop_status_reporting(self):
        """Stop background status reporting."""
        self.status_update_active = False
        if self.status_update_thread and self.status_update_thread.is_alive():
            self.status_update_thread.join(timeout=2)
        
        # Remove status file
        try:
            if os.path.exists(STATUS_FILE):
                os.remove(STATUS_FILE)
        except:
            pass
        
        self.logger.info("Status reporting stopped")
    
    def _status_update_worker(self):
        """Background worker to update status file periodically."""
        while self.status_update_active and not stop_event.is_set():
            try:
                self._write_status_file()
                time.sleep(2.0)  # Update every 2 seconds
            except Exception as e:
                self.logger.debug(f"Error updating status file: {e}")
                time.sleep(1.0)
    
    def _get_system_info(self) -> Dict[str, float]:
        """Get current system information."""
        try:
            cpu_percent = psutil.cpu_percent(interval=None) if PSUTIL_AVAILABLE else 0.0
            memory = psutil.virtual_memory() if PSUTIL_AVAILABLE else None
            disk = psutil.disk_usage('/') if PSUTIL_AVAILABLE else None
            
            return {
                'cpu_percent': cpu_percent,
                'memory_percent': memory.percent if memory else 0.0,
                'disk_usage_percent': disk.percent if disk else 0.0
            }
        except Exception:
            return {
                'cpu_percent': 0.0,
                'memory_percent': 0.0,
                'disk_usage_percent': 0.0
            }
    
    def _write_status_file(self):
        """Write current status to shared memory file."""
        try:
            # Calculate current status
            current_time = time.time()
            uptime = current_time - self.service_start_time
            
            # LSL status
            lsl_connected = self.lsl_outlet is not None
            samples_per_second = 0.0
            if uptime > 0 and self.lsl_samples_sent > 0:
                samples_per_second = self.lsl_samples_sent / uptime
            
            # Buffer status
            buffer_size = len(self.rolling_buffer)
            buffer_utilization = (buffer_size / self.buffer_max_frames) * 100 if self.buffer_max_frames > 0 else 0
            
            # Recording status
            recording_duration = 0
            if self.recording_active and self.start_time:
                recording_duration = current_time - self.start_time
            
            # Video status
            video_stats = {}
            if self.video_recorder:
                video_stats = self.video_recorder.get_stats()
            
            # Build status data
            status_data = {
                'service_running': True,
                'uptime': uptime,
                'lsl_status': {
                    'connected': lsl_connected,
                    'samples_sent': self.lsl_samples_sent,
                    'samples_per_second': samples_per_second,
                    'last_sample': self.last_lsl_sample
                },
                'buffer_status': {
                    'current_size': buffer_size,
                    'max_size': self.buffer_max_frames,
                    'utilization_percent': buffer_utilization,
                    'oldest_frame_age': 0  # Could be calculated if needed
                },
                'recording_status': {
                    'active': self.recording_active,
                    'current_file': str(self.output_dir) if self.recording_active else None,
                    'frames_recorded': self.frame_count,
                    'duration': recording_duration
                },
                'video_status': {
                    'recording': video_stats.get('recording', False),
                    'current_file': video_stats.get('current_file'),
                    'duration': video_stats.get('duration', 0)
                },
                'trigger_status': {
                    'last_trigger_type': self.last_trigger_type,
                    'last_trigger_time': self.last_trigger_time,
                    'trigger_count': self.trigger_count
                },
                'system_info': self._get_system_info()
            }
            
            # Write to file atomically
            temp_file = STATUS_FILE + ".tmp"
            with open(temp_file, 'w') as f:
                json.dump(status_data, f)
            os.rename(temp_file, STATUS_FILE)
            
        except Exception as e:
            self.logger.debug(f"Error writing status file: {e}")


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
    """Load configuration from YAML file using dynamic path detection."""
    logger = logging.getLogger('imx296_capture')
    
    # Get project root dynamically
    project_root = Path(__file__).resolve().parent.parent.parent
    
    # Dynamic config file locations - check in order of preference
    config_locations = [
        # User-specified config file (if absolute path)
        Path(config_file) if os.path.isabs(config_file) else None,
        # Config relative to project root (preferred)
        project_root / config_file,
        # Config relative to current working directory
        Path.cwd() / config_file,
        # Default config location in project
        project_root / "config" / "config.yaml",
        # Config in script directory
        Path(__file__).parent / "config.yaml",
        # Fallback to example config
        project_root / "config" / "config.yaml.example",
    ]
    
    # Filter out None values
    config_locations = [loc for loc in config_locations if loc is not None]
    
    # Try each location
    for loc in config_locations:
        try:
            abs_loc = loc.resolve()
            if abs_loc.exists():
                with open(abs_loc, 'r') as f:
                    config = yaml.safe_load(f)
                logger.info(f"Successfully loaded config from: {abs_loc}")
                return config
        except Exception as e:
            logger.warning(f"Error loading config from {loc}: {e}")
    
    # If we get here, all locations failed - create default config
    logger.warning("Failed to load config from any location, using default values")
    logger.info("Searched in:")
    for loc in config_locations:
        logger.info(f"  - {loc.resolve()}")
    
    # Create a basic default config with dynamic paths
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
            'script_path': 'bin/GScrop',  # Relative to project root
            'markers_file': '/dev/shm/camera_markers.txt',
            'frame_queue_size': 10000,
            'lsl_worker_threads': 1,
            'auto_detect': True,
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
            'output_dir': "recordings",  # Relative to project root
            'video_format': "mkv",
            'codec': "mjpeg",
            'quality': 90
        },
        'ntfy': {
            'server': "https://ntfy.sh",
            'topic': f"raspie-camera-{os.uname().nodename}-{int(time.time()) % 10000}",  # Dynamic topic
            'poll_interval_sec': 2
        },
        'logging': {
            'level': "DEBUG",
            'console': True,
            'file': "logs/imx296_capture.log",  # Relative to project root
            'max_size_mb': 10,
            'backup_count': 5
        }
    }
    
    # Try to save the default config in project root
    try:
        config_dir = project_root / "config"
        config_dir.mkdir(exist_ok=True)
        config_file_path = config_dir / "config.yaml"
        with open(config_file_path, 'w') as f:
            yaml.dump(default_config, f, default_flow_style=False, indent=2)
        logger.info(f"Created default config at: {config_file_path}")
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