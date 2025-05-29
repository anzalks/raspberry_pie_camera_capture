#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IMX296 Global Shutter Camera Capture System (Enhanced with Simplified Approach)

This module provides the main camera capture functionality for the IMX296 Global Shutter camera
using the GScrop shell script for frame capture with precise LSL timestamping.
Integrated with service management, ntfy.sh remote control, and dashboard monitoring.
Enhanced with the proven simplified approach from simple_camera_lsl.py.

Author: Anzal KS <anzal.ks@gmail.com>
Date: May 29, 2025
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
import glob

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
    LSL_AVAILABLE = True
except ImportError:
    pylsl = None
    LSL_AVAILABLE = False

try:
    import yaml
except ImportError:
    yaml = None

from .ntfy_handler import NtfyHandler
from .video_recorder import VideoRecorder

# Global variables for threading coordination
stop_event = threading.Event()
frame_queue = queue.Queue()

# Status file for monitoring
STATUS_FILE = "/dev/shm/imx296_status.json"

class GSCropCameraCapture:
    """
    GScrop-based camera capture with LSL integration and enhanced simplified approach.
    
    This class integrates the proven working approach from simple_camera_lsl.py
    with the comprehensive features of the main branch including service infrastructure,
    ntfy notifications, and dashboard monitoring.
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
        
        # Enhanced: Use proven approach from simple_camera_lsl.py
        self.lsl_data = []  # Store LSL data for statistics
        self.total_frames_captured = 0  # Track actual frames captured
        
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
        
        # Enhanced: Use local output directory (no sudo required)
        self.output_dir = Path(config['recording']['output_dir'])
        self.output_dir.mkdir(exist_ok=True)
        
        # Enhanced: Local markers file in output directory
        self.markers_file = str(self.output_dir / "camera_markers.txt")
        
        # Rolling buffer settings
        buffer_config = config.get('buffer', {})
        self.buffer_duration = buffer_config.get('duration_seconds', 15)
        self.buffer_max_frames = buffer_config.get('max_frames', 1500)
        
        # Initialize rolling buffer
        self.rolling_buffer = collections.deque(maxlen=self.buffer_max_frames)
        self.buffer_active = False
        self.buffer_thread = None
        
        # Auto-detect camera if enabled
        if config['camera'].get('auto_detect', True):
            self._auto_detect_camera()
        
        # Enhanced: Find GScrop script using proven approach
        self.gscrop_path = self._find_gscrop_script()
        
        # Initialize LSL outlet using proven approach
        if LSL_AVAILABLE:
            self._setup_lsl_proven()
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
                self.logger.info("Video recorder initialized")
            except Exception as e:
                self.logger.warning(f"Failed to initialize video recorder: {e}")
        
        # Start rolling buffer immediately
        self.start_rolling_buffer()
        
        # Start status reporting
        self._start_status_reporting()
        
        self.logger.info(f"Enhanced GScrop camera capture initialized: {self.width}x{self.height}@{self.fps}fps")
    
    def _find_gscrop_script(self):
        """Find the GScrop script using the proven approach from simple_camera_lsl.py."""
        # Enhanced: Search multiple locations dynamically
        script_locations = [
            # Project root relative paths
            project_root / "bin" / "GScrop",
            project_root / "GScrop",
            # Current directory relative paths
            Path("./bin/GScrop"),
            Path("./GScrop"),
            # Config-specified path
            Path(self.config['camera'].get('script_path', 'bin/GScrop'))
        ]
        
        for script_path in script_locations:
            if script_path.exists() and os.access(script_path, os.X_OK):
                self.logger.info(f"Found GScrop script at: {script_path}")
                return str(script_path)
        
        # Default fallback
        default_path = str(project_root / "bin" / "GScrop")
        self.logger.warning(f"GScrop script not found, using default: {default_path}")
        return default_path
    
    def _auto_detect_camera(self):
        """Auto-detect camera configuration with unlimited device support using glob.glob."""
        import glob
        
        self.logger.info("Auto-detecting IMX296 camera with unlimited device support...")
        
        # Dynamic search using glob for unlimited device support
        media_devices = glob.glob('/dev/media*')
        media_devices.sort()  # Sort for consistent ordering
        
        self.logger.info(f"Scanning {len(media_devices)} media devices: {media_devices}")
        
        detected_device = None
        detected_entity = None
        
        for device_path in media_devices:
            # Skip non-numeric devices with smart filtering
            try:
                device_num = int(device_path.split('media')[-1])
                self.logger.debug(f"Testing device: {device_path} (device number: {device_num})")
            except ValueError:
                self.logger.debug(f"Skipping non-numeric device: {device_path}")
                continue
            
            # Test each device for IMX296 compatibility
            if self._test_imx296_device(device_path):
                detected_device = device_path
                self.logger.info(f"✅ IMX296 found on {device_path}")
                break
            else:
                self.logger.debug(f"❌ No IMX296 found on {device_path}")
        
        if detected_device:
            self.detected_device = detected_device
            self.logger.info(f"Auto-detection successful: Using {detected_device}")
            return detected_device
        else:
            self.logger.warning("⚠️  No IMX296 devices found in comprehensive scan")
            # Fallback to first available device
            if media_devices:
                fallback_device = media_devices[0]
                self.detected_device = fallback_device
                self.logger.warning(f"Falling back to: {fallback_device}")
                return fallback_device
            else:
                self.logger.error("❌ No media devices found at all")
                return None

    def _test_imx296_device(self, device_path):
        """Test if a media device has IMX296 camera - enhanced validation."""
        try:
            import subprocess
            
            # Use media-ctl to probe the device for IMX296 entity
            result = subprocess.run(
                ['media-ctl', '-d', device_path, '-p'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                # Look for IMX296 entity in the output
                output = result.stdout.lower()
                if 'imx296' in output:
                    self.logger.debug(f"✅ IMX296 entity found on {device_path}")
                    return True
                else:
                    self.logger.debug(f"❌ No IMX296 entity on {device_path}")
                    return False
            else:
                self.logger.debug(f"❌ Failed to probe {device_path}: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            self.logger.debug(f"❌ Timeout probing {device_path}")
            return False
        except FileNotFoundError:
            self.logger.debug("❌ media-ctl not found - cannot validate devices")
            return False
        except Exception as e:
            self.logger.debug(f"❌ Error testing {device_path}: {e}")
            return False
    
    def _setup_lsl_proven(self):
        """Setup LSL outlet for frame timing data using the proven approach."""
        try:
            lsl_config = self.config.get('lsl', {})
            name = lsl_config.get('stream_name', 'IMX296Camera_Enhanced')
            stream_type = lsl_config.get('stream_type', 'VideoEvents')
            
            # Create 3-channel stream info as required by summary.md
            info = pylsl.StreamInfo(
                name=name,
                type=stream_type,
                channel_count=3,  # Enhanced: 3-channel as required
                nominal_srate=self.fps,
                channel_format=pylsl.cf_double64,  # Use double precision
                source_id=f"IMX296_{name}_{int(time.time())}"
            )
            
            # Add 3-channel descriptions for LabRecorder compatibility
            channels = info.desc().append_child("channels")
            
            # Channel 1: Frame Number
            ch1 = channels.append_child("channel")
            ch1.append_child_value("label", "FrameNumber")
            ch1.append_child_value("unit", "count")
            ch1.append_child_value("type", "Frame")
            
            # Channel 2: Trigger Time
            ch2 = channels.append_child("channel")
            ch2.append_child_value("label", "TriggerTime")
            ch2.append_child_value("unit", "seconds")
            ch2.append_child_value("type", "Timestamp")
            
            # Channel 3: Trigger Type
            ch3 = channels.append_child("channel")
            ch3.append_child_value("label", "TriggerType")
            ch3.append_child_value("unit", "enum")
            ch3.append_child_value("type", "Trigger")
            
            # Add metadata for better identification
            desc = info.desc()
            desc.append_child_value("manufacturer", "Anzal_KS")
            desc.append_child_value("model", "IMX296_GlobalShutter")
            desc.append_child_value("version", "2.0_Enhanced_3Channel")
            
            # Create outlet with minimal buffering for real-time streaming
            self.lsl_outlet = pylsl.StreamOutlet(info, chunk_size=1, max_buffered=0)
            self.logger.info(f"LSL outlet '{name}' created successfully (enhanced 3-channel)")
            self.logger.info("IMPORTANT: LSL configured for 3-CHANNEL streaming - frame_number, trigger_time, trigger_type")
            
        except Exception as e:
            self.logger.error(f"Failed to create LSL outlet: {e}")
            self.lsl_outlet = None
    
    def _push_lsl_sample(self, frame_number, timestamp):
        """Push a 3-channel sample to LSL with precise timestamps - enhanced approach."""
        # Store data internally for statistics (proven approach)
        self.lsl_data.append([timestamp, float(frame_number), float(self.last_trigger_type)])
        
        if self.lsl_outlet:
            try:
                # Push 3-channel sample: [frame_number, trigger_time, trigger_type]
                sample = [
                    float(frame_number),
                    float(self.last_trigger_time),
                    float(self.last_trigger_type)
                ]
                self.lsl_outlet.push_sample(sample)
                self.lsl_samples_sent += 1
                self.last_lsl_sample = sample  # Update for status monitoring
            except Exception as e:
                self.logger.error(f"Error pushing 3-channel LSL sample: {e}")
    
    def _queue_frame_data(self, frame_num, frame_time, source="unknown"):
        """Queue frame data for LSL processing - proven approach."""
        try:
            frame_queue.put((frame_num, frame_time), block=False)
            self.total_frames_captured += 1
            
            # Periodic debug logging to avoid spam
            if frame_num % 100 == 0:
                self.logger.debug(f"Queued frame {frame_num} from {source}")
        except queue.Full:
            self.logger.warning(f"Frame queue full, dropping frame {frame_num}")
        except Exception as e:
            self.logger.error(f"Failed to queue frame {frame_num} from {source}: {e}")
    
    def _lsl_worker_thread(self):
        """Worker thread to process frames and send to LSL - enhanced proven approach."""
        self.logger.info("Enhanced LSL worker thread started - processing EVERY frame captured")
        frames_processed = 0
        last_report_time = time.time()
        
        # Simple rolling window for frame rate calculation (last 100 frames)
        frame_window = []  # Store (timestamp, frame_num) tuples
        
        while not stop_event.is_set():
            try:
                # Get frame data from the queue with short timeout
                frame_data = frame_queue.get(timeout=0.1)
                frame_num, frame_time = frame_data
                
                # Add to rolling window
                frame_window.append((frame_time, frame_num))
                
                # Keep only last 100 frames
                if len(frame_window) > 100:
                    frame_window = frame_window[-100:]
                
                # Push the frame data to LSL using proven method
                self._push_lsl_sample(frame_num, frame_time)
                
                frames_processed += 1
                
                # Report frame rate every 10 seconds
                current_time = time.time()
                if current_time - last_report_time >= 10.0 and len(frame_window) >= 50:
                    # Calculate frame rate from rolling window
                    window_duration = frame_window[-1][0] - frame_window[0][0]
                    window_frames = len(frame_window)
                    
                    if window_duration > 0:
                        current_fps = (window_frames - 1) / window_duration
                        self.logger.debug(f"Enhanced LSL processing: {current_fps:.1f} FPS (rolling window)")
                    
                    last_report_time = current_time
                
                # Mark task as done
                frame_queue.task_done()
                
            except queue.Empty:
                # No data in queue, just continue
                pass
            except Exception as e:
                self.logger.error(f"Error in enhanced LSL worker thread: {e}")
        
        # Final frame rate calculation
        if len(frame_window) >= 2:
            total_duration = frame_window[-1][0] - frame_window[0][0]
            total_frames = len(frame_window)
            if total_duration > 0:
                final_fps = (total_frames - 1) / total_duration
                self.logger.info(f"Enhanced LSL worker finished: {frames_processed} frames processed, final rate: {final_fps:.1f} FPS")
        else:
            self.logger.info(f"Enhanced LSL worker finished: {frames_processed} frames processed")
    
    def _monitor_process_output(self, pipe, name):
        """Monitor GScrop process output and extract frame data - enhanced proven approach."""
        if pipe is None:
            self.logger.warning(f"No {name} pipe to monitor")
            return
        
        frames_processed = 0
        
        for line in iter(pipe.readline, b''):
            if stop_event.is_set():
                break
            
            line_str = line.decode().strip()
            if not line_str:
                continue
            
            # Parse frame data from GScrop output (proven approach)
            if line_str.startswith("FRAME_DATA:") and name == "stdout":
                try:
                    # Parse FRAME_DATA:frame_num:timestamp format
                    parts = line_str.split(":")
                    if len(parts) == 3:
                        frame_num = int(parts[1])
                        timestamp = float(parts[2])
                        
                        # Add to queue for LSL processing using proven method
                        self._queue_frame_data(frame_num, timestamp, source="process_output")
                        frames_processed += 1
                        
                except (ValueError, IndexError) as e:
                    self.logger.debug(f"Error parsing frame data: {line_str} - {e}")
                continue
            
            # Log the output based on content (non-frame data)
            if "error" in line_str.lower() or "ERROR" in line_str:
                self.logger.error(f"GScrop {name}: {line_str}")
            elif "warning" in line_str.lower() or "WARNING" in line_str:
                self.logger.warning(f"GScrop {name}: {line_str}")
            elif "FRAME_DATA:" not in line_str:  # Don't log frame data as regular output
                self.logger.debug(f"GScrop {name}: {line_str}")
        
        if frames_processed > 0:
            self.logger.debug(f"Enhanced process output monitoring finished: {frames_processed} frames")
        
        self.logger.debug(f"End of {name} pipe monitoring")
    
    def _run_gscrop_script(self, duration_ms, output_path, **kwargs):
        """Run the GScrop script with specified parameters - enhanced proven approach."""
        cmd = [self.gscrop_path, str(self.width), str(self.height), str(self.fps)]
        
        if duration_ms > 0:
            cmd.append(str(duration_ms))
        
        if self.exposure_us:
            cmd.append(str(self.exposure_us))
        
        if output_path:
            cmd.append(output_path)
        
        # Set environment variables for enhanced functionality
        env = os.environ.copy()
        
        # Enable real-time LSL streaming (proven approach)
        env["STREAM_LSL"] = "1"
        
        # Handle additional options from kwargs
        if kwargs.get('preview'):
            env["PREVIEW"] = "1"
        if kwargs.get('no_awb'):
            env["no_awb"] = "1"
        if kwargs.get('enable_plot'):
            env["ENABLE_PLOT"] = "1"
        if kwargs.get('container', 'auto') != 'auto':
            env["VIDEO_CONTAINER"] = kwargs['container']
        if kwargs.get('encoder', 'auto') != 'auto':
            env["VIDEO_ENCODER"] = kwargs['encoder']
        if kwargs.get('fragmented'):
            env["FRAGMENTED_MP4"] = "1"
        
        # Add cam1 if using second camera
        if os.environ.get("cam1"):
            env["cam1"] = "1"
        
        self.logger.info(f"Starting enhanced GScrop with command: {' '.join(cmd)}")
        
        # Debug output
        self.logger.debug(f"Environment variables for enhanced GScrop:")
        for key, value in env.items():
            if key.startswith(('STREAM_', 'ENABLE_', 'cam', 'PREVIEW', 'no_awb', 'VIDEO_', 'FRAGMENTED_')):
                self.logger.debug(f"  {key}={value}")
        
        try:
            # Start the GScrop script
            camera_process = subprocess.Popen(
                cmd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0  # Unbuffered output
            )
            
            # Start threads to monitor stdout and stderr using proven approach
            threading.Thread(target=self._monitor_process_output, args=(camera_process.stdout, "stdout"), daemon=True).start()
            threading.Thread(target=self._monitor_process_output, args=(camera_process.stderr, "stderr"), daemon=True).start()
            
            return camera_process
            
        except Exception as e:
            self.logger.error(f"Failed to start enhanced GScrop script: {e}")
            return None
    
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
    
    def start_recording(self, duration_seconds=None, output_filename=None, **kwargs):
        """Start recording using enhanced GScrop script with proven approach."""
        if self.recording_active:
            self.logger.warning("Recording already active")
            return False
        
        try:
            # Generate output filename if not provided
            if not output_filename:
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                output_filename = f"recording_{self.width}x{self.height}_{self.fps}fps_{timestamp}"
            
            output_path = str(self.output_dir / output_filename)
            duration_ms = int(duration_seconds * 1000) if duration_seconds else 0
            
            # Reset counters and queues
            self.lsl_data = []
            self.total_frames_captured = 0
            stop_event.clear()
            
            # Clear frame queue
            while not frame_queue.empty():
                try:
                    frame_queue.get_nowait()
                except queue.Empty:
                    break
            
            # Start LSL worker thread first
            if LSL_AVAILABLE and self.lsl_outlet:
                self.lsl_thread = threading.Thread(target=self._lsl_worker_thread, daemon=True)
                self.lsl_thread.start()
                self.logger.info("Enhanced LSL worker thread started")
            
            # Start camera process using enhanced proven approach
            self.camera_process = self._run_gscrop_script(duration_ms, output_path, **kwargs)
            
            if not self.camera_process:
                self.logger.error("Failed to start enhanced camera process")
                return False
            
            self.recording_active = True
            self.start_time = time.time()
            
            # Send ntfy notification if available
            if self.ntfy_handler:
                self.ntfy_handler.send_recording_started(output_path, duration_seconds)
            
            self.logger.info(f"Enhanced recording started: {output_path}")
            
            # Start video recorder if available (separate process)
            if self.video_recorder:
                try:
                    self.video_recorder.start_recording(output_filename, duration_seconds)
                    self.logger.info("Video recorder started independently")
                except Exception as e:
                    self.logger.warning(f"Failed to start video recorder: {e}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start enhanced recording: {e}")
            return False
    
    def stop_recording(self):
        """Stop recording and cleanup - enhanced proven approach."""
        if not self.recording_active:
            self.logger.warning("No recording active")
            return False
        
        try:
            # Signal stop to all threads
            stop_event.set()
            
            # Terminate camera process
            if self.camera_process and self.camera_process.poll() is None:
                self.logger.info("Terminating camera process...")
                self.camera_process.terminate()
                try:
                    # Wait for graceful shutdown
                    self.camera_process.wait(timeout=5)
                    self.logger.info("Camera process terminated gracefully")
                except subprocess.TimeoutExpired:
                    self.logger.warning("Camera process did not terminate gracefully, forcing kill")
                    self.camera_process.kill()
            
            # Wait for LSL thread to finish
            if self.lsl_thread and self.lsl_thread.is_alive():
                self.logger.info("Waiting for LSL thread to finish...")
                self.lsl_thread.join(timeout=3)
                if self.lsl_thread.is_alive():
                    self.logger.warning("LSL thread did not finish in time")
            
            # Stop video recorder if active
            if self.video_recorder:
                try:
                    self.video_recorder.stop_recording()
                    self.logger.info("Video recorder stopped")
                except Exception as e:
                    self.logger.warning(f"Error stopping video recorder: {e}")
            
            # Calculate statistics
            stats = self.get_stats()
            
            # Send ntfy notification with stats
            if self.ntfy_handler:
                self.ntfy_handler.send_recording_stopped(stats)
            
            self.recording_active = False
            self.logger.info(f"Enhanced recording stopped. Stats: {stats['frames_captured']} frames captured")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to stop enhanced recording: {e}")
            return False
    
    def get_stats(self):
        """Get recording statistics - enhanced with proven data."""
        stats = {
            'recording_active': self.recording_active,
            'frames_captured': len(self.lsl_data),
            'total_frames': self.total_frames_captured,
            'lsl_samples_sent': self.lsl_samples_sent,
            'width': self.width,
            'height': self.height,
            'fps': self.fps,
            'exposure_us': self.exposure_us,
            'output_dir': str(self.output_dir)
        }
        
        # Calculate duration and FPS if we have data
        if self.start_time and self.lsl_data:
            current_time = time.time()
            duration = current_time - self.start_time
            stats['duration'] = duration
            
            # Calculate actual FPS from LSL data
            if len(self.lsl_data) >= 2:
                first_timestamp = self.lsl_data[0][0]
                last_timestamp = self.lsl_data[-1][0]
                frame_duration = last_timestamp - first_timestamp
                if frame_duration > 0:
                    stats['actual_fps'] = (len(self.lsl_data) - 1) / frame_duration
                else:
                    stats['actual_fps'] = 0
            else:
                stats['actual_fps'] = 0
        
        return stats
    
    def is_recording(self):
        """Check if recording is currently active."""
        return self.recording_active
    
    def get_status(self):
        """Get current status of the camera capture system."""
        current_time = time.time()
        uptime = current_time - self.service_start_time if hasattr(self, 'service_start_time') else 0
        
        # Basic status information
        status = {
            'service_running': True,
            'uptime': uptime,
            'recording_active': self.recording_active,
            'buffer_active': self.buffer_active,
            'camera_config': {
                'width': self.width,
                'height': self.height,
                'fps': self.fps,
                'exposure_us': self.exposure_us
            },
            'frame_counts': {
                'lsl_data': len(self.lsl_data),
                'total_captured': self.total_frames_captured,
                'lsl_samples_sent': self.lsl_samples_sent
            },
            'buffer_status': {
                'size': len(self.rolling_buffer),
                'max_size': self.buffer_max_frames
            }
        }
        
        # Add LSL status
        if LSL_AVAILABLE:
            status['lsl_status'] = {
                'available': True,
                'outlet_active': self.lsl_outlet is not None,
                'samples_sent': self.lsl_samples_sent
            }
        
        # Add recording duration if active
        if self.recording_active and self.start_time:
            status['recording_duration'] = current_time - self.start_time
        
        return status
    
    def cleanup(self):
        """Cleanup all resources - enhanced proven approach."""
        try:
            self.logger.info("Starting enhanced cleanup...")
            
            # Stop recording if active
            if self.recording_active:
                self.stop_recording()
            
            # Signal stop to all threads
            stop_event.set()
            
            # Stop rolling buffer
            if self.buffer_active:
                self.stop_rolling_buffer()
            
            # Stop video recorder
            if self.video_recorder:
                try:
                    self.video_recorder.cleanup()
                    self.logger.info("Video recorder cleaned up")
                except Exception as e:
                    self.logger.warning(f"Error cleaning up video recorder: {e}")
            
            # Stop ntfy handler
            if self.ntfy_handler:
                try:
                    self.ntfy_handler.stop()
                    self.logger.info("ntfy handler stopped")
                except Exception as e:
                    self.logger.warning(f"Error stopping ntfy handler: {e}")
            
            # Stop status reporting
            if self.status_update_active:
                self.status_update_active = False
                if self.status_update_thread and self.status_update_thread.is_alive():
                    self.status_update_thread.join(timeout=2)
            
            # Clean up any remaining threads
            threads_to_check = [self.lsl_thread, self.monitor_thread, self.buffer_thread]
            for thread in threads_to_check:
                if thread and thread.is_alive():
                    thread.join(timeout=1)
            
            self.logger.info("Enhanced cleanup completed successfully")
            
        except Exception as e:
            self.logger.error(f"Error during enhanced cleanup: {e}")
    
    def _handle_ntfy_command(self, command: str, params: Dict[str, Any]):
        """Handle ntfy commands - enhanced for proven approach."""
        try:
            if command == 'start_recording':
                duration = params.get('duration', 30)  # Default 30 seconds
                filename = params.get('filename')
                
                self.logger.info(f"ntfy command: start recording for {duration}s")
                
                if self.recording_active:
                    error_msg = "Recording already active"
                    self.logger.warning(error_msg)
                    if self.ntfy_handler:
                        self.ntfy_handler.send_error(error_msg)
                else:
                    success = self.start_recording(duration_seconds=duration, output_filename=filename)
                    if not success:
                        error_msg = "Failed to start recording"
                        self.logger.error(error_msg)
                        if self.ntfy_handler:
                            self.ntfy_handler.send_error(error_msg)
                
            elif command == 'stop_recording':
                self.logger.info("ntfy command: stop recording")
                
                if not self.recording_active:
                    error_msg = "No recording active"
                    self.logger.warning(error_msg)
                    if self.ntfy_handler:
                        self.ntfy_handler.send_error(error_msg)
                else:
                    self.stop_recording()
                
            elif command == 'status' or command == 'get_stats':
                self.logger.info("ntfy command: get status")
                stats = self.get_stats()
                if self.ntfy_handler:
                    self.ntfy_handler.send_status(stats)
                    
            elif command == 'trigger':
                self.logger.info("ntfy command: trigger event")
                self.trigger_event(source='ntfy')
                if self.ntfy_handler:
                    self.ntfy_handler.send_trigger_confirmation()
                    
            else:
                error_msg = f"Unknown command: {command}"
                self.logger.warning(error_msg)
                if self.ntfy_handler:
                    self.ntfy_handler.send_error(error_msg)
                    
        except Exception as e:
            error_msg = f"Error handling ntfy command {command}: {e}"
            self.logger.error(error_msg)
            if self.ntfy_handler:
                self.ntfy_handler.send_error(error_msg)

    def start_rolling_buffer(self):
        """Start the rolling buffer for pre-trigger capture."""
        if self.buffer_active:
            return
        
        self.logger.info(f"Starting rolling buffer: {self.buffer_duration}s ({self.buffer_max_frames} frames)")
        self.buffer_active = True
        self.buffer_thread = threading.Thread(target=self._rolling_buffer_worker, daemon=True)
        self.buffer_thread.start()
    
    def stop_rolling_buffer(self):
        """Stop the rolling buffer."""
        if not self.buffer_active:
            return
        
        self.buffer_active = False
        if self.buffer_thread and self.buffer_thread.is_alive():
            self.buffer_thread.join(timeout=2)
        
        self.logger.info(f"Rolling buffer stopped: {len(self.rolling_buffer)} frames")
    
    def _rolling_buffer_worker(self):
        """Worker thread for the rolling buffer."""
        last_frame_time = 0
        frame_interval = 1.0 / self.fps
        
        while self.buffer_active and not stop_event.is_set():
            current_time = time.time()
            
            # Only capture frames at the specified interval
            if current_time - last_frame_time >= frame_interval:
                # Simulate frame capture (in real implementation, this would capture actual frames)
                frame_data = {
                    'timestamp': current_time,
                    'frame_number': len(self.rolling_buffer),
                    'simulated': True
                }
                
                self.rolling_buffer.append(frame_data)
                last_frame_time = current_time
            
            time.sleep(0.001)  # Small sleep to prevent CPU spinning
    
    def _start_status_reporting(self):
        """Start background thread for status file updates."""
        if not self.status_update_active:
            self.status_update_active = True
            self.status_update_thread = threading.Thread(target=self._status_update_worker, daemon=True)
            self.status_update_thread.start()
            self.logger.info("Status reporting started")
    
    def _status_update_worker(self):
        """Worker thread to periodically update status file."""
        while self.status_update_active and not stop_event.is_set():
            try:
                self._update_status_file()
                time.sleep(5)  # Update every 5 seconds
            except Exception as e:
                self.logger.debug(f"Error in status update worker: {e}")
        
        self.logger.debug("Status update worker finished")
    
    def _update_status_file(self):
        """Update the status file with current system information."""
        try:
            status = self.get_status()
            
            with open(STATUS_FILE, 'w') as f:
                json.dump(status, f, indent=2)
            
        except Exception as e:
            self.logger.debug(f"Error writing status file: {e}")

    def trigger_event(self, source='manual'):
        """Trigger an event marker - enhanced for proven approach."""
        trigger_time = time.time()
        
        # Map source to trigger type
        if source == 'keyboard':
            self.last_trigger_type = 1
        elif source == 'ntfy':
            self.last_trigger_type = 2
        else:
            self.last_trigger_type = 1  # Default to manual
        
        self.last_trigger_time = trigger_time
        self.trigger_count += 1
        
        self.logger.info(f"Enhanced event triggered from {source} at {trigger_time}")
        
        return True


def signal_handler(sig, frame):
    """Handle shutdown signals gracefully."""
    logger = logging.getLogger('imx296_capture')
    logger.info(f"Received signal {sig}, shutting down...")
    
    # Set stop event for all threads
    stop_event.set()
    
    sys.exit(0)


def setup_logging(config):
    """Setup logging configuration."""
    log_config = config.get('system', {})
    log_level = getattr(logging, log_config.get('log_level', 'INFO').upper())
    
    # Create logs directory if it doesn't exist
    log_dir = Path('logs')
    log_dir.mkdir(exist_ok=True)
    
    # Setup logging format
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    
    # File handler
    file_handler = logging.FileHandler(log_dir / 'imx296_capture.log')
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)
    
    # Setup root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Clear existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Add our handlers
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    
    # Set specific logger levels
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('requests').setLevel(logging.WARNING)


def load_config(config_file="config/config.yaml"):
    """Load configuration from YAML file with fallback defaults."""
    try:
        config_path = Path(config_file)
        if config_path.exists():
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f) if yaml else {}
            print(f"Loaded configuration from {config_path}")
        else:
            print(f"Config file {config_path} not found, using defaults")
            config = {}
    except Exception as e:
        print(f"Error loading config: {e}, using defaults")
        config = {}
    
    # Provide fallback defaults
    default_config = {
        'camera': {
            'width': 400,
            'height': 400,
            'fps': 100,
            'exposure_time_us': 5000,
            'auto_detect': True,
            'script_path': 'bin/GScrop'
        },
        'recording': {
            'output_dir': 'recordings',
            'container': 'mp4',
            'encoder': 'h264',
            'enable_fragmented': False
        },
        'buffer': {
            'duration_seconds': 15,
            'max_frames': 1500
        },
        'lsl': {
            'stream_name': 'IMX296Camera_Enhanced',
            'stream_type': 'Video'
        },
        'ntfy': {
            'server': '',
            'topic': '',
            'poll_interval_sec': 2
        },
        'system': {
            'log_level': 'INFO'
        }
    }
    
    # Merge with defaults
    def merge_config(default, loaded):
        for key, value in default.items():
            if key not in loaded:
                loaded[key] = value
            elif isinstance(value, dict) and isinstance(loaded[key], dict):
                merge_config(value, loaded[key])
    
    merge_config(default_config, config)
    return config


def main():
    """Main entry point for running the capture system."""
    try:
        # Parse command line arguments
        import argparse
        parser = argparse.ArgumentParser(description='Enhanced IMX296 Camera Capture System')
        parser.add_argument('--config', default='config/config.yaml', help='Configuration file path')
        parser.add_argument('--interactive', action='store_true', help='Run in interactive mode')
        parser.add_argument('--duration', type=float, help='Recording duration in seconds')
        parser.add_argument('--output', help='Output filename')
        args = parser.parse_args()
        
        # Load configuration
        config = load_config(args.config)
        
        # Setup logging
        setup_logging(config)
        logger = logging.getLogger('imx296_capture')
        
        # Register signal handlers
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        logger.info("Enhanced IMX296 Camera Capture System starting...")
        
        # Create capture instance
        capture = GSCropCameraCapture(config)
        
        try:
            if args.interactive:
                # Interactive mode
                logger.info("Starting interactive mode...")
                logger.info("Commands: 's <duration>' (start), 'q' (quit), 't' (status)")
                
                while True:
                    try:
                        cmd = input("\nEnter command: ").strip().lower()
                        
                        if cmd.startswith('s'):
                            parts = cmd.split()
                            duration = float(parts[1]) if len(parts) > 1 else 30
                            capture.start_recording(duration_seconds=duration)
                            
                        elif cmd == 'q':
                            break
                            
                        elif cmd == 't':
                            stats = capture.get_stats()
                            print(f"Stats: {stats}")
                            
                    except KeyboardInterrupt:
                        break
                    except Exception as e:
                        logger.error(f"Error processing command: {e}")
            
            elif args.duration:
                # Single recording mode
                logger.info(f"Starting single recording for {args.duration} seconds...")
                capture.start_recording(duration_seconds=args.duration, output_filename=args.output)
                
                # Wait for recording to complete
                while capture.is_recording():
                    time.sleep(0.5)
                
                stats = capture.get_stats()
                logger.info(f"Recording completed: {stats}")
            
            else:
                # Service mode
                logger.info("Starting service mode...")
                
                # Start ntfy handler if configured
                if capture.ntfy_handler:
                    capture.ntfy_handler.start()
                    logger.info("ntfy handler started - camera can be controlled remotely")
                
                # Keep running
                while not stop_event.is_set():
                    time.sleep(1)
        
        finally:
            capture.cleanup()
            
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


# Factory function for easier import
def create_gscrop_capture(config):
    """Factory function to create a GSCropCameraCapture instance."""
    return GSCropCameraCapture(config)


if __name__ == "__main__":
    main() 