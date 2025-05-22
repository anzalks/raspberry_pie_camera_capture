"""Class-based implementation for camera streaming and LSL interaction."""

import time
import numpy as np
import cv2 # Import OpenCV
import traceback
import platform # For OS-specific checks
import os # Added for checking device existence
import threading # Added for writer thread
import queue # Added for frame buffer queue
from queue import Queue, Empty, Full # Added for frame buffer queue
import glob # Added for device detection
import datetime # Added for timestamp generation
import uuid # Added for UUID generation
import subprocess # Added for running commands to detect and configure global shutter camera

# Import Picamera2 
print("DEBUG: Importing picamera2 for Raspberry Pi Camera...")
try:
    from picamera2 import Picamera2, Preview
    PICAMERA2_AVAILABLE = True
    try:
        picamera2_version = Picamera2.__version__
        print(f"DEBUG: picamera2 imported successfully. Version: {picamera2_version}")
    except AttributeError:
        print("DEBUG: picamera2 imported successfully but version information not available.")
except ImportError as e:
    print(f"ERROR: Failed to import picamera2: {e}")
    print("This application requires picamera2 to be installed.")
    PICAMERA2_AVAILABLE = False

# Import pylsl for LabStreamingLayer communication
from pylsl import StreamInfo, StreamOutlet, local_clock

# Monkey patch for pylsl StreamInfo.__del__ issue
# This prevents a common error message on exit with some pylsl versions.
def _safe_pylsl_streaminfo_del(self):
    try:
        # Check if the original __del__ was already replaced or if obj exists
        if hasattr(self, 'obj') and hasattr(self, '_original_del'): 
            self._original_del() # Call original if it was stored
        elif hasattr(self, 'obj') and self.obj is not None: # Fallback for direct attribute check
            # This part is tricky as direct lib.lsl_destroy_streaminfo(self.obj) might be needed
            # but an explicit call here without knowing original __del__ is risky.
            # For now, we rely on the fact that if _original_del is not there, 
            # it was either never patched or already handled.
            pass 
    except Exception as e:
        # print(f"Safely handled StreamInfo deletion error: {e}") # Optional: for debugging
        pass

if hasattr(StreamInfo, '__del__') and not hasattr(StreamInfo, '_original_del'):
    StreamInfo._original_del = StreamInfo.__del__
    StreamInfo.__del__ = _safe_pylsl_streaminfo_del
    print("Applied LSL StreamInfo __del__ monkey patch.")

# Import the buffer trigger system
from .buffer_trigger import BufferTriggerManager, RollingBuffer, NtfySubscriber
from .status_file import StatusFileWriter

# Try to import psutil for CPU affinity management
try:
    import psutil
    PSUTIL_AVAILABLE = True
    print("DEBUG: psutil imported successfully.")
except ImportError:
    PSUTIL_AVAILABLE = False
    print("Warning: psutil library not found. CPU core affinity will not be managed.")

class LSLCameraStreamer:
    """Captures frames from a Raspberry Pi camera and streams via LSL."""
    def __init__(self, 
                 width=640,
                 height=480,
                 target_fps=30.0,
                 save_video=True,
                 output_path=None,
                 codec='h264',
                 show_preview=True,
                 push_to_lsl=True,
                 stream_name='camera_stream',
                 use_buffer=True,
                 buffer_size_seconds=5.0,
                 ntfy_topic='raspie-camera-test',
                 queue_size_seconds=2.0,
                 capture_cpu_core=None,
                 writer_cpu_core=None,
                 lsl_cpu_core=None,
                 enable_crop=None, # Deprecated for Global Shutter, use Picamera2 controls
                 camera_id=0):
        """Initialize the camera streamer."""
        self._validate_config(width, height, target_fps, codec, buffer_size_seconds, 
                             queue_size_seconds, capture_cpu_core, writer_cpu_core, lsl_cpu_core)
                             
        self.width = width
        self.height = height
        self.target_fps = target_fps
        self.save_video = save_video
        self.output_path = output_path
        self.codec = codec
        self.show_preview = show_preview 
        self.push_to_lsl = push_to_lsl
        self.stream_name = stream_name
        self.use_buffer = use_buffer
        self.buffer_size_seconds = buffer_size_seconds
        self.ntfy_topic = ntfy_topic
        self.queue_size_seconds = queue_size_seconds
        self.capture_cpu_core = capture_cpu_core
        self.writer_cpu_core = writer_cpu_core
        self.lsl_cpu_core = lsl_cpu_core
        self.camera_id = camera_id
        
        self._is_running = False
        self.frame_count = 0
        self.frames_written_count = 0
        self.frames_dropped_count = 0
        self.actual_fps = target_fps
        self.camera_model = "Raspberry Pi Camera"
        self.is_global_shutter = False
        self.media_device = None # No longer used for configuration

        self._check_global_shutter_camera() # Detects if it is a GS camera
        
        try:
            self.source_id = self._get_raspberry_pi_id()
        except:
            self.source_id = str(uuid.uuid4())
            
        self.lsl_pixel_format = "BGR"
        self.num_channels = 3
        self.buffer = None
        
        self.outlet = None
        self.status_outlet = None
        
        if self.output_path:
            os.makedirs(self.output_path, exist_ok=True)
            
        self.camera = None
        self.camera_lock = threading.Lock()
        
        if not PICAMERA2_AVAILABLE:
            raise RuntimeError("Picamera2 is required but not available. Please install picamera2.")
               
        if self.push_to_lsl:
            self._setup_lsl()
            
        self.buffer_trigger_manager = None
        self.waiting_for_trigger = False
        self.recording_triggered = False
        if self.use_buffer:
            self._initialize_buffer_trigger()
            
        self.video_writer = None
        self.frame_queue = None
        self.writer_thread = None
        self.stop_writer_event = None
        if self.save_video:
            self._initialize_video_writer()
        
        self.stop_status_event = threading.Event()
        self.status_thread = None
        self.status_display = None
        self.status_file_writer = None

    def _get_raspberry_pi_id(self):
        """Get Raspberry Pi's unique serial number from /proc/cpuinfo."""
        try:
            if not os.path.exists("/proc/cpuinfo"):
                return str(uuid.uuid4())
            with open("/proc/cpuinfo", "r") as f:
                for line in f:
                    if line.startswith("Serial"):
                        return line.split(":")[1].strip()
            return str(uuid.uuid4())
        except Exception as e:
            print(f"Error getting Raspberry Pi ID: {e}")
            return str(uuid.uuid4())

    def _check_global_shutter_camera(self):
        """Detect if a Global Shutter Camera is connected using v4l2-ctl and libcamera."""
        if platform.system() != "Linux":
            print("Global Shutter Camera detection only works on Linux")
            return False
            
        try:
            # Primary check using v4l2-ctl
            cmd = ["v4l2-ctl", "--list-devices"]
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if "imx296" in result.stdout.lower():
                print(f"Global Shutter Camera (IMX296) detected via v4l2-ctl")
                self.is_global_shutter = True
                self.camera_model = "Raspberry Pi Global Shutter Camera (IMX296)"
                return True

            # Fallback check using libcamera-hello (if Picamera2 is available)
            if PICAMERA2_AVAILABLE:
                try:
                    cameras = Picamera2.global_camera_info()
                    for cam_info in cameras:
                        if "imx296" in cam_info.get("Model", "").lower():
                            print(f"Global Shutter Camera (IMX296) detected via Picamera2.global_camera_info()")
                            self.is_global_shutter = True
                            self.camera_model = "Raspberry Pi Global Shutter Camera (IMX296)"
                            return True
                except Exception as e:
                    print(f"Error checking with Picamera2.global_camera_info(): {e}")

        except FileNotFoundError:
            print("v4l2-ctl not found. Cannot reliably detect Global Shutter camera type.")
        except Exception as e:
            print(f"Error checking for Global Shutter Camera: {e}")
        
        print("Global Shutter Camera not detected, or detection method failed.")
        return False

    def _configure_global_shutter_crop(self):
        """Configures Global Shutter Camera for specific resolution and FPS using Picamera2 controls.
           This method is called during _initialize_camera if a Global Shutter camera is detected.
           It does NOT use media-ctl or v4l2-ctl directly anymore.
        """
        if not self.is_global_shutter or not self.camera:
            return

        print(f"Configuring Global Shutter Camera for {self.width}x{self.height} @ {self.target_fps}fps using Picamera2 controls")
        
        # Global Shutter Camera sensor dimensions
        sensor_width = 1456
        sensor_height = 1088

        # Ensure requested width and height are even
        req_width = self.width + (self.width % 2) # Make even
        req_height = self.height + (self.height % 2) # Make even

        if req_width > sensor_width or req_height > sensor_height:
            print(f"Warning: Requested resolution {req_width}x{req_height} exceeds sensor {sensor_width}x{sensor_height}. Adjusting.")
            req_width = min(req_width, sensor_width)
            req_height = min(req_height, sensor_height)
            req_width += (req_width % 2)
            req_height += (req_height % 2)
            print(f"Adjusted to {req_width}x{req_height}")

        # Calculate centered crop
        left = (sensor_width - req_width) // 2
        top = (sensor_height - req_height) // 2
        left -= (left % 2) # Ensure even
        top -= (top % 2)   # Ensure even

        # The raw stream from a Global Shutter camera is often full sensor.
        # We need to configure the camera to output the desired (cropped) resolution.
        # Picamera2 handles this via the 'raw' stream configuration and controls.
        
        # Formats: SBGGR10_CSI2P for MIPI, SBGGR10 for unpacked 10-bit Bayer.
        # Picamera2 usually manages this selection well.
        raw_format = 'SBGGR10' # Common for GS IMX296

        # This is a simplified approach. For full control similar to Hermann-SW's media-ctl, 
        # one might need to delve into camera.camera_controls or more specific libcamera parameters.
        # However, Picamera2 aims to abstract much of this.

        try:
            # Create a configuration that includes a raw stream for sensor control
            # and a main stream for the desired output.
            cam_config = self.camera.create_still_configuration(
                main={"size": (req_width, req_height), "format": "XBGR8888"}, # For preview/capture
                raw={"size": (sensor_width, sensor_height), "format": raw_format}, # Control sensor mode
                controls={
                    "FrameRate": self.target_fps,
                    "ScalerCrop": (left, top, req_width, req_height)
                }
            )
            print(f"Applying GS config: main={req_width}x{req_height}, raw={sensor_width}x{sensor_height}, crop=({left},{top})/{req_width}x{req_height}, FPS={self.target_fps}")
            self.camera.configure(cam_config)
            print("Global Shutter Camera configured with ScalerCrop via Picamera2.")
            
            # Update width/height if adjusted
            self.width = req_width
            self.height = req_height

        except Exception as e:
            print(f"Error configuring Global Shutter Camera with Picamera2 ScalerCrop: {e}")
            print("Falling back to simpler configuration without explicit raw stream for sensor control.")
            try:
                cam_config = self.camera.create_video_configuration(
                    main={"size": (req_width, req_height), "format": "XBGR8888"},
                    controls={"FrameRate": self.target_fps, "ScalerCrop": (left, top, req_width, req_height)}
                )
                self.camera.configure(cam_config)
                print("Global Shutter Camera configured with fallback ScalerCrop method.")
                self.width = req_width
                self.height = req_height
            except Exception as e2:
                print(f"Fallback GS configuration also failed: {e2}")
                print("Proceeding without specific Global Shutter ScalerCrop configuration.")

    def _validate_config(self, width, height, target_fps, codec, buffer_size_seconds, 
                        queue_size_seconds, capture_cpu_core, writer_cpu_core, lsl_cpu_core):
        """Validate configuration parameters."""
        if not isinstance(width, int) or width <= 0:
            raise ValueError("Width must be a positive integer.")
        if not isinstance(height, int) or height <= 0:
            raise ValueError("Height must be a positive integer.")
        if not isinstance(target_fps, (int, float)) or target_fps <= 0:
            raise ValueError("Target FPS must be a positive number.")
        if codec.lower() not in ['h264', 'h265', 'mjpg', 'libx264']:
            raise ValueError(f"Invalid codec: {codec}. Must be h264, h265, mjpg, or libx264.")
        if not isinstance(buffer_size_seconds, (int, float)) or buffer_size_seconds < 0:
            raise ValueError("Buffer size must be a non-negative number.")
        if not isinstance(queue_size_seconds, (int, float)) or queue_size_seconds <= 0:
            raise ValueError("Queue size must be a positive number.")
        
        if PSUTIL_AVAILABLE:
            num_cores = psutil.cpu_count()
            if capture_cpu_core is not None and (not isinstance(capture_cpu_core, int) or not (0 <= capture_cpu_core < num_cores)):
                raise ValueError(f"Invalid capture_cpu_core: {capture_cpu_core}. Must be between 0 and {num_cores - 1}.")
            if writer_cpu_core is not None and (not isinstance(writer_cpu_core, int) or not (0 <= writer_cpu_core < num_cores)):
                raise ValueError(f"Invalid writer_cpu_core: {writer_cpu_core}. Must be between 0 and {num_cores - 1}.")
            if lsl_cpu_core is not None and (not isinstance(lsl_cpu_core, int) or not (0 <= lsl_cpu_core < num_cores)):
                raise ValueError(f"Invalid lsl_cpu_core: {lsl_cpu_core}. Must be between 0 and {num_cores - 1}.")
        else:
            if any([capture_cpu_core, writer_cpu_core, lsl_cpu_core]):
                print("Warning: CPU core affinity specified, but psutil is not available. Affinity will not be set.")


    def _optimize_dimensions_for_fps(self):
        """Adjusts width and height for optimal FPS if needed, especially for Global Shutter."""
        # This is a placeholder. Specific cameras might have tables of supported modes.
        # For Global Shutter, Picamera2 controls should handle this better.
        if self.is_global_shutter:
            print("Global Shutter detected. Picamera2 will manage mode selection.")
            # Ensure dimensions are even, as often required by raw sensor modes
            if self.width % 2 != 0:
                self.width += 1
                print(f"Adjusted width to be even: {self.width}")
            if self.height % 2 != 0:
                self.height += 1
                print(f"Adjusted height to be even: {self.height}")
        return self.width, self.height, self.target_fps

    def _initialize_camera(self):
        """Initialize the Picamera2 instance and configure it."""
        if not PICAMERA2_AVAILABLE:
            print("ERROR: Picamera2 not available, cannot initialize camera.")
            self.camera_model = "Unavailable (Picamera2 missing)"
            return

        with self.camera_lock:
            try:
                print("Initializing Raspberry Pi Camera...")
                self.camera = Picamera2(self.camera_id)
                
                # Get camera properties to update model if possible
                try:
                    props = self.camera.camera_properties
                    self.camera_model = props.get("Model", self.camera_model)
                    print(f"Camera Model from properties: {self.camera_model}")
                    # Update is_global_shutter based on properties as a fallback
                    if not self.is_global_shutter and "imx296" in self.camera_model.lower():
                        self.is_global_shutter = True
                        print("Detected Global Shutter from camera properties.")

                except Exception as e:
                    print(f"Could not get camera properties: {e}")

                print(f"Initializing camera with: {self.width}x{self.height} @ {self.target_fps}fps")

                # If Global Shutter, try specific configuration
                if self.is_global_shutter:
                    self._configure_global_shutter_crop() # Uses Picamera2 controls
                else:
                    # Standard camera configuration
                    video_config = self.camera.create_video_configuration(
                        main={"size": (self.width, self.height), "format": "XBGR8888"},
                        controls={"FrameRate": self.target_fps}
                    )
                    self.camera.configure(video_config)
                    print(f"Standard camera configured: {video_config}")
                
                # Set up preview if enabled
                if self.show_preview:
                    self.camera.start_preview(Preview.QTGL) # Or Preview.DRM for non-desktop
                    print("Preview window started.")

                self.camera.start()
                print(f"Camera started successfully. Actual FPS will be determined.")
                # Allow some time for FPS to stabilize if possible
                time.sleep(0.5) 
                
                # Try to get actual FPS if available from controls
                try:
                    self.actual_fps = self.camera.camera_controls['FrameRate'].value
                    print(f"Actual camera FPS from controls: {self.actual_fps:.2f}")
                except (KeyError, AttributeError, TypeError):
                    print(f"Could not retrieve actual FPS from camera controls, using target: {self.target_fps:.2f}")
                    self.actual_fps = self.target_fps

            except Exception as e:
                print(f"Error initializing camera: {e}")
                traceback.print_exc()
                self.camera = None # Ensure camera is None if initialization fails
                raise RuntimeError(f"Failed to initialize Camera: {e}")

    def _initialize_video_writer(self):
        """Initialize the video writer and frame queue."""
        if not self.save_video or not self.output_path:
            return

        # Max queue size based on seconds of video at target FPS
        max_queue_frames = int(self.queue_size_seconds * self.target_fps)
        self.frame_queue = Queue(maxsize=max_queue_frames)
        self.stop_writer_event = threading.Event()
        
        # Determine fourcc code
        if self.codec.lower() == 'h264' or self.codec.lower() == 'libx264':
            # Try common H.264 fourccs, prefer 'X264' if available, fallback to 'H264'
            # Note: OpenCV's VideoWriter might have limited FourCC support on some platforms.
            # Using 'mp4v' for .mp4 or relying on container to imply might be more robust
            # if direct H.264 doesn't work.
            self.fourcc = cv2.VideoWriter_fourcc(*'X264') 
            # self.fourcc = cv2.VideoWriter_fourcc(*'H264')
        elif self.codec.lower() == 'h265':
            self.fourcc = cv2.VideoWriter_fourcc(*'HEVC')
        elif self.codec.lower() == 'mjpg':
            self.fourcc = cv2.VideoWriter_fourcc(*'MJPG')
        else:
            raise ValueError(f"Unsupported codec: {self.codec}")

        # Generate a unique filename for each recording session
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.output_filename = os.path.join(self.output_path, f"recording_{timestamp}.mkv")
        
        print(f"Video writer initialized. Output to: {self.output_filename}, Codec: {self.codec}, FPS: {self.actual_fps:.2f}")
        
        self.writer_thread = threading.Thread(target=self._writer_loop, name="VideoWriterThread")
        self.writer_thread.daemon = True
        self.writer_thread.start()

    def _writer_loop(self):
        """Background thread to write frames from the queue to a video file."""
        if PSUTIL_AVAILABLE and self.writer_cpu_core is not None:
            self._set_thread_affinity("Writer", self.writer_cpu_core)
            
        video_out = None
        frames_processed_in_session = 0

        try:
            while not self.stop_writer_event.is_set() or not self.frame_queue.empty():
                try:
                    frame_data = self.frame_queue.get(timeout=0.1) # Wait for a short time
                    if frame_data is None: # Sentinel value to stop
                        break
                        
                    frame, timestamp = frame_data
                    
                    if video_out is None:
                        # Initialize VideoWriter on the first frame to get correct dimensions
                        current_height, current_width = frame.shape[:2]
                        # Use actual_fps which should be set by _initialize_camera
                        video_out = cv2.VideoWriter(self.output_filename, self.fourcc, 
                                                    self.actual_fps, (current_width, current_height))
                        if not video_out.isOpened():
                            print(f"ERROR: Could not open video writer for {self.output_filename}")
                            self.stop_writer_event.set() # Stop trying if writer fails
                            return
                        print(f"Video writer started for {self.output_filename} at {current_width}x{current_height} @ {self.actual_fps:.2f} FPS")
                    
                    video_out.write(frame)
                    self.frames_written_count += 1
                    frames_processed_in_session +=1
                    self.frame_queue.task_done()
                    
                except Empty:
                    if self.stop_writer_event.is_set() and self.frame_queue.empty():
                        break # Exit if stopping and queue is empty
                    continue # Keep waiting if not stopping
                except Exception as e:
                    print(f"Error in writer loop: {e}")
                    traceback.print_exc()
                    # Continue trying to process frames unless explicitly stopped
                    
        finally:
            if video_out and video_out.isOpened():
                video_out.release()
                print(f"Video writer closed. {frames_processed_in_session} frames written to {self.output_filename}")
            elif video_out:
                print(f"Video writer for {self.output_filename} was initialized but may not have opened or written frames.")
            else:
                print("Video writer was not initialized in this session.")

    def _setup_lsl(self):
        """Set up the LSL stream outlets."""
        # Video stream info
        # Using BGR8 for pixel format as OpenCV uses BGR by default
        info = StreamInfo(name=self.stream_name, type='Video', channel_count=self.num_channels, 
                          nominal_srate=self.target_fps, channel_format='double', # Using double for pixel values (0-255)
                          source_id=self.source_id)
        
        # Add metadata to the stream info
        desc = info.desc()
        desc.append_child_value("camera_model", self.camera_model)
        desc.append_child_value("resolution_width", str(self.width))
        desc.append_child_value("resolution_height", str(self.height))
        desc.append_child_value("target_fps", str(self.target_fps))
        desc.append_child_value("actual_fps", str(self.actual_fps))
        desc.append_child_value("pixel_format", self.lsl_pixel_format)
        desc.append_child_value("acquisition_time_type", "local_clock_opencv")
        desc.append_child_value("output_path", self.output_path if self.output_path else "N/A")
        desc.append_child_value("codec", self.codec)
        desc.append_child_value("is_global_shutter", str(self.is_global_shutter))

        self.outlet = StreamOutlet(info)
        print(f"LSL video stream '{self.stream_name}' created.")

        # Recording status stream info
        status_info = StreamInfo(name=f"{self.stream_name}_Status", type='Markers', channel_count=1,
                                 nominal_srate=0, channel_format='string', 
                                 source_id=f"{self.source_id}_status")
        status_desc = status_info.desc()
        status_desc.append_child_value("description", "Indicates recording status (RECORDING_START, RECORDING_STOP) and frame drops.")
        self.status_outlet = StreamOutlet(status_info)
        print(f"LSL status stream '{self.stream_name}_Status' created.")

    def _set_thread_affinity(self, thread_name, cpu_core):
        """Set CPU affinity for the current thread."""
        if not PSUTIL_AVAILABLE or cpu_core is None:
            return
        try:
            p = psutil.Process()
            p.cpu_affinity([cpu_core])
            print(f"Set CPU affinity for {thread_name} thread to core {cpu_core}")
        except Exception as e:
            print(f"Warning: Failed to set CPU affinity for {thread_name} thread: {e}")

    def start(self):
        """Start the camera capture and LSL streaming."""
        if self._is_running:
            print("Camera streamer is already running.")
            return

        try:
            self._initialize_camera()
            if not self.camera:
                 print("Camera initialization failed. Cannot start streamer.")
                 return # Exit if camera did not initialize

            self._is_running = True
            self.frame_count = 0
            self.frames_written_count = 0
            self.frames_dropped_count = 0
            
            # Start the status thread for LSL publishing
            if self.push_to_lsl:
                self.stop_status_event.clear()
                self.status_thread = threading.Thread(target=self._status_thread, name="LSLStatusThread")
                self.status_thread.daemon = True
                self.status_thread.start()
                
            # Start the buffer trigger manager if enabled
            if self.use_buffer and self.buffer_trigger_manager:
                self.buffer_trigger_manager.start()
                self.waiting_for_trigger = True # Initially wait for trigger
                print("Buffer trigger system started. Waiting for ntfy trigger.")
            else:
                self.waiting_for_trigger = False # Not using buffer, so not waiting
                # If not using buffer but saving video, start writer immediately
                if self.save_video and not self.video_writer:
                    self._initialize_video_writer()

            print("Camera capture started.")
            
            # Set CPU affinity for capture thread (main thread here)
            if PSUTIL_AVAILABLE and self.capture_cpu_core is not None:
                self._set_thread_affinity("Capture", self.capture_cpu_core)

        except Exception as e:
            print(f"Error starting camera streamer: {e}")
            traceback.print_exc()
            self.stop() # Ensure cleanup if start fails

    def stop(self):
        """Stop the camera capture and LSL streaming."""
        if not self._is_running:
            # print("Camera streamer is not running.")
            return

        print("Stopping camera streamer...")
        self._is_running = False
        
        # Stop the status thread
        if self.status_thread and self.status_thread.is_alive():
            self.stop_status_event.set()
            self.status_thread.join(timeout=1)
            if self.status_thread.is_alive():
                print("Warning: LSL status thread did not terminate cleanly.")
        self.status_thread = None

        # Stop the buffer trigger manager
        if self.buffer_trigger_manager:
            self.buffer_trigger_manager.stop()
            self.buffer_trigger_manager = None

        # Stop the video writer thread
        if self.writer_thread and self.writer_thread.is_alive():
            self.stop_writer_event.set()
            if self.frame_queue: # Send sentinel if queue exists
                try: self.frame_queue.put_nowait(None) 
                except Full: pass
            self.writer_thread.join(timeout=2) # Increased timeout for writer
            if self.writer_thread.is_alive():
                print("Warning: Writer thread did not terminate cleanly.")
        self.writer_thread = None
        self.video_writer = None # Ensure writer is reset

        # Release camera
        with self.camera_lock:
            if self.camera:
                try:
                    if self.camera.started:
                        self.camera.stop_preview() # Stop preview if it was started
                        self.camera.stop()
                        print("Camera stopped.")
                    self.camera.close()
                    print("Camera closed.")
                except Exception as e:
                    print(f"Error stopping/closing camera: {e}")
                finally:
                    self.camera = None
        
        # Clean up LSL outlets
        if self.outlet:
            # No explicit close for pylsl outlets, just let them be garbage collected
            self.outlet = None
            print("LSL video outlet released.")
        if self.status_outlet:
            self.status_outlet = None
            print("LSL status outlet released.")

        print("Camera streamer stopped.")

    def capture_frame(self):
        """Capture a single frame from the camera."""
        if not self._is_running or not self.camera:
            return None, None

        try:
            # Picamera2 capture_array returns a NumPy array
            # The format is typically BGR or RGB depending on configuration.
            # For XBGR8888, it's BGR after removing alpha.
            array = self.camera.capture_array("main") # Capture from the 'main' stream
            capture_time = local_clock() # Use LSL's local_clock for consistency
            
            # Assuming XBGR8888, it has 4 channels. We need 3 (BGR or RGB).
            # OpenCV expects BGR by default.
            if array.shape[2] == 4: # If 4 channels (e.g., XBGR)
                frame = array[:, :, :3] # Take B, G, R channels, discard Alpha
            else:
                frame = array # Assume it's already 3 channels or needs other handling
            
            self.frame_count += 1
            return frame, capture_time
        except Exception as e:
            print(f"Error capturing frame: {e}")
            # traceback.print_exc() # Potentially too verbose for every frame error
            return None, None

    def process_frame(self, frame, timestamp):
        """Process a captured frame: display, save, and push to LSL."""
        if frame is None or timestamp is None:
            return

        # Buffer frame if buffer trigger is active and waiting
        if self.use_buffer and self.buffer_trigger_manager and self.waiting_for_trigger:
            self.buffer_trigger_manager.add_frame(frame, timestamp)
            return # Don't process further until trigger or buffer is full
        
        # If buffer trigger is not active, or if it has triggered, process frame directly
        # Display preview if enabled (Picamera2 handles its own preview window)
        # self.show_preview is checked during camera initialization for Picamera2

        # Save video if enabled
        if self.save_video and self.frame_queue is not None:
            try:
                self.frame_queue.put_nowait((frame, timestamp))
            except Full:
                self.frames_dropped_count += 1
                if self.status_outlet and self.frame_count % (int(self.actual_fps) * 5) == 0: # Log every 5s
                    self.status_outlet.push_sample([f"FRAME_DROPPED_QUEUE_FULL_Count_{self.frames_dropped_count}"], local_clock())
                # print(f"Warning: Frame queue full. Dropped frame {self.frame_count}. Total dropped: {self.frames_dropped_count}")

        # Push to LSL if enabled
        if self.push_to_lsl and self.outlet:
            try:
                # LSL expects a list of samples, even if it's just one frame.
                # Flatten the frame and send. For BGR8, this is width*height*3 channels.
                # Convert frame to list of doubles for LSL (as per channel_format='double')
                # This might be inefficient. Consider sending raw bytes or changing channel_format.
                # For now, sending as flattened list of pixel values.
                # Frame is HxWxC (e.g., 480x640x3). Flatten to 1D array.
                flat_frame = frame.flatten().astype(float).tolist()
                self.outlet.push_sample(flat_frame, timestamp)
            except Exception as e:
                print(f"Error pushing frame to LSL: {e}")
                # traceback.print_exc() # Potentially too verbose
                # Attempt to re-initialize LSL outlet on error?
                # For now, just print error and continue.

    def _initialize_buffer_trigger(self):
        """Initialize the buffer trigger manager."""
        if not self.use_buffer:
            return
            
        buffer_capacity = int(self.buffer_size_seconds * self.target_fps)
        self.buffer = RollingBuffer(capacity=buffer_capacity)
        
        # Subscriber for ntfy notifications
        ntfy_subscriber = NtfySubscriber(self.ntfy_topic)
        
        self.buffer_trigger_manager = BufferTriggerManager(
            buffer=self.buffer,
            subscriber=ntfy_subscriber,
            on_trigger_callback=self._handle_recording_trigger,
            on_stop_callback=self._handle_recording_stop,
            lsl_status_outlet=self.status_outlet # Pass the LSL outlet here
        )
        print(f"Buffer trigger system initialized with {self.buffer_size_seconds}s buffer")

    def _handle_recording_trigger(self, frames):
        """Callback when recording is triggered."""
        print(f"Recording triggered. Processing {len(frames)} buffered frames.")
        self.waiting_for_trigger = False # No longer waiting, now recording
        self.recording_triggered = True

        # Ensure video writer is initialized if saving video
        if self.save_video and not self.video_writer and self.frame_queue is None:
             print("Initializing video writer due to trigger...")
             self._initialize_video_writer() # This starts the writer thread
        elif self.save_video and self.video_writer is None and self.frame_queue is not None:
             # This case implies writer_thread might have exited or not started correctly
             print("Re-initializing video writer as it was not active...")
             # Ensure old thread is cleaned up if it exists and is dead
             if self.writer_thread and not self.writer_thread.is_alive():
                 self.writer_thread.join(timeout=0.1)
                 self.writer_thread = None
             self._initialize_video_writer()

        if self.status_outlet:
            self.status_outlet.push_sample(["RECORDING_START"], local_clock())
        
        # Write buffered frames
        if self.save_video and self.frame_queue is not None:
            num_buffered_written = 0
            for frame, timestamp in frames:
                try:
                    self.frame_queue.put_nowait((frame, timestamp)) # Add to writer queue
                    num_buffered_written +=1
                except Full:
                    self.frames_dropped_count += 1
                    print(f"Warning: Frame queue full while writing buffered frames. Dropped. Total dropped: {self.frames_dropped_count}")
                    if self.status_outlet:
                         self.status_outlet.push_sample([f"FRAME_DROPPED_BUFFER_QUEUE_FULL_Count_{self.frames_dropped_count}"], local_clock())
            print(f"Added {num_buffered_written} buffered frames to writer queue.")
        
        # Push buffered frames to LSL
        if self.push_to_lsl and self.outlet:
            for frame, timestamp in frames:
                try:
                    flat_frame = frame.flatten().astype(float).tolist()
                    self.outlet.push_sample(flat_frame, timestamp)
                except Exception as e:
                    print(f"Error pushing buffered frame to LSL: {e}")

    def _handle_recording_stop(self):
        """Callback when recording is stopped."""
        print("Recording stop triggered.")
        self.recording_triggered = False
        self.waiting_for_trigger = True # Go back to waiting for a trigger

        if self.status_outlet:
            self.status_outlet.push_sample(["RECORDING_STOP"], local_clock())
        
        # If we were saving video, the writer thread handles its own closure based on stop_writer_event.
        # However, if we want to finalize the current file and start a new one on next trigger:
        if self.save_video:
            print("Recording stopped. Video file will be finalized by writer thread.")
            # To start a new file on next trigger, we need to stop and None-out the current writer
            # so _initialize_video_writer creates a new one.
            if self.writer_thread and self.writer_thread.is_alive():
                self.stop_writer_event.set()
                if self.frame_queue: 
                    try: self.frame_queue.put_nowait(None) # Sentinel
                    except Full: print("Warning: Could not send stop sentinel to writer, queue full.")
                self.writer_thread.join(timeout=2)
                if self.writer_thread.is_alive():
                    print("Warning: Writer thread did not terminate cleanly after stop trigger.")
            self.writer_thread = None
            self.video_writer = None # This will force re-initialization on next trigger / write
            self.frame_queue = None # Also re-init queue
            self.stop_writer_event = None
            print("Video writer reset for next recording session.")


    def manual_trigger(self):
        """Manually trigger recording if buffer system is active."""
        if self.use_buffer and self.buffer_trigger_manager:
            print("Manually triggering recording...")
            self.buffer_trigger_manager.trigger_recording()
        else:
            print("Buffer system not active, manual trigger has no effect.")

    def manual_stop(self):
        """Manually stop recording if buffer system is active."""
        if self.use_buffer and self.buffer_trigger_manager:
            print("Manually stopping recording...")
            self.buffer_trigger_manager.stop_recording()
        else:
            print("Buffer system not active, manual stop has no effect.")
    
    def get_current_filename(self):
        if hasattr(self, 'output_filename') and self.output_filename:
            return self.output_filename
        return "Not Recording / Filename N/A"

    def get_info(self):
        """Get current status information."""
        return {
            "camera_model": self.camera_model,
            "is_global_shutter": self.is_global_shutter,
            "is_running": self._is_running,
            "width": self.width,
            "height": self.height,
            "target_fps": self.target_fps,
            "actual_fps": self.actual_fps,
            "save_video": self.save_video,
            "output_path": self.output_path,
            "current_file": self.get_current_filename(),
            "codec": self.codec,
            "show_preview": self.show_preview,
            "push_to_lsl": self.push_to_lsl,
            "lsl_stream_name": self.stream_name,
            "use_buffer": self.use_buffer,
            "buffer_size_seconds": self.buffer_size_seconds,
            "ntfy_topic": self.ntfy_topic,
            "waiting_for_trigger": self.waiting_for_trigger,
            "recording_active": self.recording_triggered, # or check self.video_writer.isOpened() if more direct
            "frames_captured_session": self.frame_count,
            "frames_written_session": self.frames_written_count,
            "frames_dropped_session": self.frames_dropped_count
        }

    def get_frame_count(self):
        return self.frame_count

    def get_frames_written(self):
        return self.frames_written_count

    def get_frames_dropped(self):
        return self.frames_dropped_count

    def __del__(self):
        self.stop()

    def _status_thread(self):
        """Periodically publishes status updates to LSL."""
        if PSUTIL_AVAILABLE and self.lsl_cpu_core is not None:
            self._set_thread_affinity("LSLStatus", self.lsl_cpu_core)
            
        status_update_interval = 2.0  # seconds
        last_status_time = time.time()

        while not self.stop_status_event.is_set():
            current_time = time.time()
            if current_time - last_status_time >= status_update_interval:
                if self.status_outlet:
                    status_msg = f"STATUS_UPDATE FrameCount:{self.frame_count} Written:{self.frames_written_count} Dropped:{self.frames_dropped_count} FPS_Actual:{self.actual_fps:.1f}"
                    if self.recording_triggered:
                        status_msg += " State:RECORDING"
                    elif self.waiting_for_trigger:
                        status_msg += " State:WAITING_TRIGGER"
                    else:
                        status_msg += " State:IDLE_NO_BUFFER"
                    try:
                        self.status_outlet.push_sample([status_msg], local_clock())
                    except Exception as e:
                        print(f"Error pushing status to LSL: {e}")
                last_status_time = current_time
            
            # Sleep for a short duration to avoid busy-waiting
            # Check stop event more frequently than update interval
            if self.stop_status_event.wait(timeout=0.1):
                break 
        print("LSL Status thread stopped.")

    def _validate_config(self, width, height, target_fps, codec, buffer_size_seconds, 
                        queue_size_seconds, capture_cpu_core, writer_cpu_core, lsl_cpu_core):
        # Parameter validation logic (as provided by user previously)
        if not isinstance(width, int) or width <= 0:
            raise ValueError("Width must be a positive integer.")
        if not isinstance(height, int) or height <= 0:
            raise ValueError("Height must be a positive integer.")
        if not isinstance(target_fps, (int, float)) or target_fps <= 0:
            raise ValueError("Target FPS must be a positive number.")
        if codec.lower() not in ['h264', 'h265', 'mjpg', 'libx264']:
            # Added libx264 as a common alias for H.264, OpenCV might use it
            raise ValueError(f"Invalid codec: {codec}. Must be h264, h265, mjpg, or libx264.")
        if not isinstance(buffer_size_seconds, (int, float)) or buffer_size_seconds < 0:
            # Allow 0 for no buffer if use_buffer is False, but BufferTriggerManager might expect >0
            raise ValueError("Buffer size must be a non-negative number.")
        if not isinstance(queue_size_seconds, (int, float)) or queue_size_seconds <= 0:
            raise ValueError("Queue size must be a positive number.")
        
        # CPU core validation
        if PSUTIL_AVAILABLE:
            num_cores = psutil.cpu_count()
            if capture_cpu_core is not None and (not isinstance(capture_cpu_core, int) or not (0 <= capture_cpu_core < num_cores)):
                raise ValueError(f"Invalid capture_cpu_core: {capture_cpu_core}. Must be between 0 and {num_cores - 1}.")
            if writer_cpu_core is not None and (not isinstance(writer_cpu_core, int) or not (0 <= writer_cpu_core < num_cores)):
                raise ValueError(f"Invalid writer_cpu_core: {writer_cpu_core}. Must be between 0 and {num_cores - 1}.")
            if lsl_cpu_core is not None and (not isinstance(lsl_cpu_core, int) or not (0 <= lsl_cpu_core < num_cores)):
                raise ValueError(f"Invalid lsl_cpu_core: {lsl_cpu_core}. Must be between 0 and {num_cores - 1}.")
        elif any([capture_cpu_core, writer_cpu_core, lsl_cpu_core]):
            print("Warning: CPU core affinity specified, but psutil is not available. Affinity will not be set.")

# --- Main execution for testing --- 

def main():
    """Main function for testing the camera streamer."""
    print("Starting LSLCameraStreamer test...")
    
    # Get config from environment variables or use defaults
    width = int(os.getenv("CAM_WIDTH", 640))
    height = int(os.getenv("CAM_HEIGHT", 480))
    fps = float(os.getenv("CAM_FPS", 30.0))
    preview_enabled = os.getenv("PREVIEW_ENABLED", "true").lower() == "true"
    output_dir = os.getenv("OUTPUT_DIR", "recordings/test_output")
    
    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)
    
    # Create a status file writer
    status_file = os.path.join(output_dir, "camera_status.txt")
    status_writer = StatusFileWriter(status_file)
    status_writer.update_status("Initializing")

    # Global streamer instance to be controlled by signal handler
    global camera_streamer
    camera_streamer = None

    def signal_handler(sig, frame):
        global camera_streamer
        print("Signal received, shutting down camera streamer...")
        if camera_streamer:
            camera_streamer.stop()
        if status_writer:
            status_writer.update_status("Stopped by signal")
            status_writer.close()
        sys.exit(0)

    import signal
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        camera_streamer = LSLCameraStreamer(
            width=width,
            height=height,
            target_fps=fps,
            save_video=True,
            output_path=output_dir,
            codec='mjpg', # MJPG for broader compatibility and less CPU than H264 for OpenCV writer
            show_preview=preview_enabled,
            push_to_lsl=True,
            stream_name="TestVideoStream",
            use_buffer=True, 
            buffer_size_seconds=10.0, 
            ntfy_topic="raspie-camera-testing"
        )
        
        camera_streamer.status_display = print_status_update # Simple terminal UI
        camera_streamer.status_file_writer = status_writer
        
        camera_streamer.start()
        status_writer.update_status("Running")
        
        # Keep main thread alive, periodically update status
        last_info_print_time = time.time()
        while camera_streamer._is_running:
            current_time = time.time()
            if current_time - last_info_print_time >= 1.0: # Print info every 1 second
                if callable(camera_streamer.status_display):
                    camera_streamer.status_display()
                last_info_print_time = current_time
            time.sleep(0.1) # Keep main thread responsive
            
    except RuntimeError as e:
        print(f"Runtime Error during streamer initialization or execution: {e}")
        if status_writer:
            status_writer.update_status(f"Error: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        traceback.print_exc()
        if status_writer:
            status_writer.update_status(f"Unexpected Error: {e}")
    finally:
        print("Cleaning up...")
        if camera_streamer:
            camera_streamer.stop()
        if status_writer:
            status_writer.update_status("Exited")
            status_writer.close()
        print("LSLCameraStreamer test finished.")

# Helper for terminal UI (can be passed to status_display)
def print_status_update():
    # Clear terminal and print header
    os.system('clear' if os.name != 'nt' else 'cls')
    print("=" * 60)
    print("RASPBERRY PI CAMERA STREAMER - TEST MODE".center(60))
    print("=" * 60)
    
    global camera_streamer
    if camera_streamer:
        info = camera_streamer.get_info()
        print(f"Camera: {info.get('camera_model', 'N/A')} ({GREEN if info.get('is_running') else RED}{ 'RUNNING' if info.get('is_running') else 'STOPPED'}{NC})")
        print(f"Resolution: {info.get('width',0)}x{info.get('height',0)} @ {info.get('actual_fps',0):.1f} FPS (Target: {info.get('target_fps',0):.1f} FPS)")
        print(f"Global Shutter: {GREEN if info.get('is_global_shutter') else YELLOW}{info.get('is_global_shutter')}{NC}")
        print("-" * 30)
        print(f"LSL Stream: '{info.get('lsl_stream_name')}' ({GREEN if info.get('push_to_lsl') else RED}{ 'ACTIVE' if info.get('push_to_lsl') else 'INACTIVE'}{NC})")
        print("-" * 30)
        print(f"Video Saving: ({GREEN if info.get('save_video') else RED}{ 'ENABLED' if info.get('save_video') else 'DISABLED'}{NC})")
        if info.get('save_video'):
            print(f"  Output: {info.get('output_path')}")
            print(f"  File: {info.get('current_file')}")
            print(f"  Codec: {info.get('codec')}")
        print("-" * 30)
        print(f"Buffer System: ({GREEN if info.get('use_buffer') else YELLOW}{ 'ACTIVE' if info.get('use_buffer') else 'INACTIVE'}{NC})")
        if info.get('use_buffer'):
            print(f"  Waiting for Trigger: {GREEN if info.get('waiting_for_trigger') else YELLOW}{info.get('waiting_for_trigger')}{NC}")
            print(f"  Recording Active: {GREEN if info.get('recording_active') else YELLOW}{info.get('recording_active')}{NC}")
            print(f"  Ntfy Topic: {info.get('ntfy_topic')}")
        print("-" * 30)
        print(f"Frames Captured: {info.get('frames_captured_session',0)}")
        print(f"Frames Written: {info.get('frames_written_session',0)}")
        print(f"Frames Dropped: {RED if info.get('frames_dropped_session',0) > 0 else GREEN}{info.get('frames_dropped_session',0)}{NC}")
    else:
        print("Camera streamer not initialized.")
    
    print("=" * 60)
    print("Press Ctrl+C to exit test mode.")
    print("=" * 60)

if __name__ == "__main__":
    main() 