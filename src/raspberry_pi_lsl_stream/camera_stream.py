"""Class-based implementation for camera streaming and LSL interaction."""

import time
import numpy as np
import cv2 # Import OpenCV
import traceback
import platform # For OS-specific checks
import os # Added for checking device existence
import threading # Added for writer thread
from queue import Queue, Empty, Full # Added for frame buffer queue
import glob # Added for device detection
import datetime # Added for timestamp generation
import uuid # Added for UUID generation

# Attempt to import Picamera2 and set a flag indicating its availability.
# This allows the code to run on non-Pi systems (using a webcam)
# without crashing on import if picamera2 is not installed or supported.
print("DEBUG: About to attempt importing picamera2...")
try:
    from picamera2 import Picamera2
    PICAMERA2_AVAILABLE = True
    print("DEBUG: picamera2 imported successfully.")
except ImportError as e:
    print(f"DEBUG: Failed to import picamera2: {e}")
    PICAMERA2_AVAILABLE = False
    # Inform the user if the PiCamera library is missing
    print("Warning: picamera2 library not found. Raspberry Pi camera functionality disabled.")

# Import pylsl for LabStreamingLayer communication
from pylsl import StreamInfo, StreamOutlet, local_clock

# Import the buffer trigger system
from .buffer_trigger import BufferTriggerManager, RollingBuffer, NtfySubscriber

# Try to import psutil for CPU affinity management
try:
    import psutil
    PSUTIL_AVAILABLE = True
    print("DEBUG: psutil imported successfully.")
except ImportError:
    PSUTIL_AVAILABLE = False
    print("Warning: psutil library not found. CPU core affinity will not be managed.")

class LSLCameraStreamer:
    """Captures frames from a Raspberry Pi camera or webcam and streams via LSL."""
    def __init__(self, 
                 camera_id=0,
                 width=640,
                 height=480,
                 target_fps=30.0,
                 save_video=True,
                 output_path=None,
                 codec='auto',
                 show_preview=True,
                 push_to_lsl=True,
                 stream_name='camera_stream',
                 use_buffer=True,
                 buffer_size_seconds=5.0,
                 ntfy_topic='raspie-camera-test',
                 queue_size_seconds=2.0,
                 capture_cpu_core=None,
                 writer_cpu_core=None,
                 lsl_cpu_core=None):
        """Initialize the camera streamer.

        Args:
            camera_id (int): Camera index or ID to use.
            width (int): Desired frame width.
            height (int): Desired frame height.
            target_fps (float): Target frame rate.
            save_video (bool): Whether to save video files.
            output_path (str): Path to save video files.
            codec (str): Video codec to use ('auto', 'h264', 'h265', 'mjpg').
            show_preview (bool): Whether to show preview window.
            push_to_lsl (bool): Whether to push frames to LSL.
            stream_name (str): Name of the LSL stream.
            use_buffer (bool): Whether to use buffer trigger system.
            buffer_size_seconds (float): Size of rolling buffer in seconds.
            ntfy_topic (str): Topic for ntfy notifications.
            queue_size_seconds (float): Size of frame queue in seconds.
            capture_cpu_core (int, optional): CPU core to use for capture thread.
            writer_cpu_core (int, optional): CPU core to use for writer thread.
            lsl_cpu_core (int, optional): CPU core to use for LSL thread.
        """
        # Store parameters
        self.camera_id = camera_id
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
        
        # Initialize state variables
        self._is_running = False
        self.frame_count = 0
        self.frames_written_count = 0
        self.frames_dropped_count = 0
        self.actual_fps = target_fps
        self.camera_model = "Unknown"
        self.source_id = str(uuid.uuid4())
        self.lsl_pixel_format = "BGR"
        self.num_channels = 3
        self.buffer = None  # Initialize buffer reference
        
        # Create output directory if needed
        if self.output_path:
            os.makedirs(self.output_path, exist_ok=True)
            
        # Initialize camera
        self.camera = None
        self.is_picamera = False
        self.camera_lock = threading.Lock()
        
        # Try to detect PiCamera first
        try:
            self._initialize_picamera()
        except Exception as e:
            print(f"PiCamera initialization failed: {e}")
            print("Falling back to webcam")
            try:
                self._initialize_webcam(self.camera_id)
            except Exception as e:
                print(f"Webcam initialization failed: {e}")
                raise RuntimeError("Failed to initialize any camera")
                
        # Initialize LSL if enabled
        self.info = None
        self.outlet = None
        if self.push_to_lsl:
            self._setup_lsl()
            
        # Initialize buffer trigger if enabled
        self.buffer_trigger_manager = None
        self.waiting_for_trigger = False
        self.recording_triggered = False
        if self.use_buffer:
            self._initialize_buffer_trigger()
            
        # Initialize video writer if enabled
        self.video_writer = None
        self.frame_queue = None
        self.writer_thread = None
        self.stop_writer_event = None
        if self.save_video:
            self._initialize_video_writer()

    def _initialize_camera(self):
        """Initialize the camera based on type."""
        try:
            if self.is_picamera:
                # Initialize PiCamera
                self.camera = Picamera2()
                config = self.camera.create_video_configuration(
                    main={"size": (self.width, self.height), "format": "RGB888"},
                    lores={"size": (self.width, self.height), "format": "YUV420"}
                )
                self.camera.configure(config)
                self.camera.start()
                print(f"PiCamera initialized with resolution {self.width}x{self.height}")
            else:
                # Initialize webcam
                self.camera = cv2.VideoCapture(self.camera_id)
                if not self.camera.isOpened():
                    raise RuntimeError("Failed to open camera")
                self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
                print(f"Webcam initialized with resolution {self.width}x{self.height}")
                
            # Get actual frame rate
            if self.is_picamera:
                self.actual_fps = 30.0  # PiCamera default
            else:
                self.actual_fps = self.camera.get(cv2.CAP_PROP_FPS)
                if self.actual_fps <= 0:
                    self.actual_fps = 30.0  # Fallback
                    
            print(f"Camera frame rate: {self.actual_fps} fps")
            
        except Exception as e:
            print(f"Error initializing camera: {e}")
            if self.camera is not None:
                try:
                    if self.is_picamera:
                        self.camera.stop()
                        else:
                        self.camera.release()
                except Exception as e:
                    print(f"Error releasing camera: {e}")
            self.camera = None
            raise

    def _detect_webcam_indices(self):
        """Detect available webcam indices."""
        try:
            # List of potential video device paths
            device_paths = glob.glob('/dev/video*')
            print(f"Found video devices: {device_paths}")
            
            # Extract indices from device paths
            indices = []
            for path in device_paths:
                try:
                    index = int(path.replace('/dev/video', ''))
                    indices.append(index)
                except ValueError:
                    continue
                    
            # Sort indices for consistent ordering
            indices.sort()
            print(f"Available camera indices: {indices}")
            
            return indices
            
        except Exception as e:
            print(f"Error detecting webcam indices: {e}")
            return []

    def _initialize_webcam(self, index):
        """Initialize webcam with specified index."""
        try:
            print(f"Initializing webcam with index {index}")
            
            # Create capture object
            cap = cv2.VideoCapture(index)
            if not cap.isOpened():
                raise RuntimeError(f"Failed to open webcam with index {index}")
                
            # Set resolution
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            
            # Get actual resolution
            actual_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            actual_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            print(f"Webcam resolution: {actual_width}x{actual_height}")
            
            # Get frame rate
            fps = cap.get(cv2.CAP_PROP_FPS)
            if fps <= 0:
                fps = 30.0  # Fallback
            print(f"Webcam frame rate: {fps} fps")
            
            # Test frame capture
            ret, frame = cap.read()
            if not ret or frame is None:
                raise RuntimeError("Failed to capture test frame")
                
            # Store camera object
            self.camera = cap
            self.is_picamera = False
            self.actual_fps = fps
            print(f"Successfully initialized webcam with index {index}")
            
            return True

        except Exception as e:
            print(f"Error initializing webcam with index {index}: {e}")
            if cap is not None:
                cap.release()
            return False

    def _initialize_picamera(self):
        """Initialize PiCamera."""
        try:
            print("Initializing PiCamera")
            
            # Create PiCamera object
            self.camera = Picamera2()
            
            # Configure camera
            config = self.camera.create_video_configuration(
                main={"size": (self.width, self.height), "format": "RGB888"},
                lores={"size": (self.width, self.height), "format": "YUV420"}
            )
            self.camera.configure(config)
            
            # Start camera
            self.camera.start()
            print(f"PiCamera initialized with resolution {self.width}x{self.height}")
            
            # Set frame rate
            self.actual_fps = 30.0  # PiCamera default
            print(f"PiCamera frame rate: {self.actual_fps} fps")
            
            # Test frame capture
            frame = np.empty((self.height, self.width, 3), dtype=np.uint8)
            self.camera.capture(frame, format='rgb', use_video_port=True)
            if frame is None:
                raise RuntimeError("Failed to capture test frame")
                
            # Store camera type
            self.is_picamera = True
            print("Successfully initialized PiCamera")
            
            return True

        except Exception as e:
            print(f"Error initializing PiCamera: {e}")
            if self.camera is not None:
                try:
                    self.camera.stop()
                except Exception as e:
                    print(f"Error stopping PiCamera: {e}")
            self.camera = None
            return False

    def _initialize_video_writer(self):
        """Initialize the video writer for saving frames."""
        if not self.save_video:
            return
            
        try:
            # Generate output filename with timestamp
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            self.auto_output_filename = f"recording_{timestamp}.mp4"
            
            # Create full output path
            if self.output_path:
                output_file = os.path.join(self.output_path, self.auto_output_filename)
            else:
                output_file = self.auto_output_filename
                
            print(f"Initializing video writer for file: {output_file}")
            
            # Determine codec
            if self.codec == 'auto':
                if self.is_picamera:
                    # Use H.264 for PiCamera
                    fourcc = cv2.VideoWriter_fourcc(*'avc1')
                else:
                    # Use MJPG for webcams
                    fourcc = cv2.VideoWriter_fourcc(*'MJPG')
            else:
                # Use specified codec
                codec_map = {
                    'h264': 'avc1',
                    'h265': 'hev1',
                    'mjpg': 'MJPG'
                }
                fourcc = cv2.VideoWriter_fourcc(*codec_map.get(self.codec, 'avc1'))
                
            # Create video writer
            self.video_writer = cv2.VideoWriter(
                output_file,
                fourcc,
                self.actual_fps,
                (self.width, self.height)
            )
            
            if not self.video_writer.isOpened():
                raise RuntimeError("Failed to open video writer")
                
            # Initialize frame queue for threaded writing
            self.frame_queue = Queue(maxsize=int(self.queue_size_seconds * self.actual_fps))
            
            # Start writer thread
            self.stop_writer_event = threading.Event()
            self.writer_thread = threading.Thread(target=self._writer_loop, daemon=True)
            self.writer_thread.start()
            
            print(f"Video writer initialized with codec {self.codec} at {self.actual_fps}fps")
            
        except Exception as e:
            print(f"Error initializing video writer: {e}")
            self.video_writer = None
            self.frame_queue = None
            self.writer_thread = None
            
    def _writer_loop(self):
        """Writer loop for the video writer thread."""
        if self.writer_cpu_core is not None:
            try:
                self._set_thread_affinity("writer", self.writer_cpu_core)
            except Exception as e:
                print(f"Failed to set CPU affinity for writer thread: {e}")
                
        while not self.stop_writer_event.is_set():
            try:
                # Wait for a frame with a timeout to allow for clean shutdown
                frame = self.frame_queue.get(timeout=0.5)
                if frame is None:
                    continue
                    
                # Write frame to video file
                self.video_writer.write(frame)
                self.frames_written_count += 1
                
                # Mark task as done in the queue
                self.frame_queue.task_done()
            except queue.Empty:
                # This is expected when using timeout to allow clean shutdown
                continue
            except Exception as e:
                print(f"Error in writer loop: {e}")
                time.sleep(0.1)  # Prevent tight loop on error
                
        print("Writer thread stopped")

    def _setup_lsl(self):
        """Set up the LSL stream."""
        try:
            if self.lsl_cpu_core is not None:
                try:
                    self._set_thread_affinity("LSL", self.lsl_cpu_core)
                except Exception as e:
                    print(f"Failed to set CPU affinity for LSL thread: {e}")
                    
            # Create StreamInfo
            self.info = StreamInfo(
                name=self.stream_name,
                type='Video',
                channel_count=self.width * self.height * 3,  # RGB channels
                nominal_srate=self.actual_fps,
                channel_format='float32',
                source_id=str(uuid.uuid4())
            )
            
            # Add metadata
            self.info.desc().append_child_value("manufacturer", "Raspberry Pi")
            self.info.desc().append_child_value("camera_model", "IMX708" if self.is_picamera else "Webcam")
            self.info.desc().append_child_value("resolution", f"{self.width}x{self.height}")
            self.info.desc().append_child_value("fps", str(self.actual_fps))
            
            # Create outlet
            self.outlet = StreamOutlet(self.info)
            print(f"LSL stream '{self.stream_name}' created and waiting for consumers")
            
        except Exception as e:
            print(f"Error setting up LSL stream: {e}")
            self.info = None
            self.outlet = None

    def _set_thread_affinity(self, thread_name, cpu_core):
        """Set CPU affinity for the current thread if psutil is available."""
        if not PSUTIL_AVAILABLE or cpu_core is None:
            return
            
        try:
            p = psutil.Process()
            p.cpu_affinity([cpu_core])
            print(f"Set {thread_name} affinity to core {cpu_core}")
                    except Exception as e:
            print(f"Failed to set CPU affinity for {thread_name}: {e}")

    def start(self):
        """Start the camera capture and processing loop."""
        if self._is_running:
            print("Camera stream is already running")
            return
            
        try:
            # Initialize camera
            if self.is_picamera:
                self.camera = Picamera2()
                config = self.camera.create_video_configuration(
                    main={"size": (self.width, self.height), "format": "RGB888"},
                    lores={"size": (self.width, self.height), "format": "YUV420"}
                )
                self.camera.configure(config)
                self.camera.start()
                print(f"PiCamera initialized with resolution {self.width}x{self.height}")
                else:
                self.camera = cv2.VideoCapture(self.camera_id)
                if not self.camera.isOpened():
                    raise RuntimeError("Failed to open camera")
                self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
                print(f"Webcam initialized with resolution {self.width}x{self.height}")
                
            # Initialize LSL stream if enabled
            if self.push_to_lsl:
                self._setup_lsl()
                
            # Initialize buffer trigger if enabled
            if self.use_buffer:
                self._initialize_buffer_trigger()
                
            # Initialize video writer if enabled
            if self.save_video:
                self._initialize_video_writer()
                
            # Set running flag
             self._is_running = True
            print("Camera stream started")
            
            # Main capture loop
            while self._is_running:
                try:
                    # Capture frame
                    frame = self.capture_frame()
                    if frame is None:
                        print("Failed to capture frame")
                        continue
                        
                    # Process frame based on current state
                    if self.use_buffer:
                        if self.waiting_for_trigger:
                            # Add frame to buffer only
                            self.buffer.add_frame(frame)
                        elif self.recording_triggered:
                            # Write frame to video file
                            if self.save_video and self.video_writer is not None:
                                if not self.frame_queue.full():
                                    self.frame_queue.put(frame)
        else:
                                print("Frame queue full, dropping frame")
                    else:
                        # Normal processing without buffer
                        if self.save_video and self.video_writer is not None:
                            if not self.frame_queue.full():
                                self.frame_queue.put(frame)
                            else:
                                print("Frame queue full, dropping frame")
                                
                    # Control frame rate
                    if self.target_fps > 0:
                        time.sleep(1.0 / self.target_fps)
                        
                except Exception as e:
                    print(f"Error in main capture loop: {e}")
                    time.sleep(0.1)  # Prevent tight loop on error
                    
        except Exception as e:
            print(f"Error starting camera stream: {e}")
            self.stop()

    def stop(self):
        """Stop the camera capture and processing loop."""
        if not self._is_running:
             return 
             
        print("Stopping camera stream...")
        self._is_running = False
        
        # Stop writer thread if running
        if self.writer_thread is not None:
            self.stop_writer_event.set()
            self.writer_thread.join(timeout=2.0)
            
        # Release video writer
        if self.video_writer is not None:
            try:
                self.video_writer.release()
            except Exception as e:
                print(f"Error releasing video writer: {e}")
                
        # Release camera
        if self.is_picamera:
            if self.camera is not None:
                try:
                    self.camera.stop()
                except Exception as e:
                    print(f"Error stopping PiCamera: {e}")
        else:
            if self.camera is not None:
                try:
                    self.camera.release()
            except Exception as e:
                    print(f"Error releasing webcam: {e}")
                    
        # Close preview window
        if self.show_preview:
            cv2.destroyAllWindows()
            
        print("Camera stream stopped")

    def capture_frame(self):
        """Capture a single frame from the camera."""
        try:
            if self.is_picamera:
                # Capture frame from PiCamera
                with self.camera_lock:
                    # Create a memory-mapped array to store the frame
                    frame = np.empty((self.height, self.width, 3), dtype=np.uint8)
                    self.camera.capture(frame, format='rgb', use_video_port=True)
                    
                    # Convert RGB to BGR for OpenCV
                    frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                 else:
                # Capture frame from standard webcam
                ret, frame = self.camera.read()
                if not ret:
                    print("Failed to grab frame from camera")
                    return None
                    
            # Update frame count
            self.frame_count += 1
            
            # Add frame to buffer if enabled
            if self.use_buffer:
                try:
                    self.buffer.add_frame(frame)
                    print(f"Added frame to buffer. Current size: {self.buffer.get_buffer_size()}")
            except Exception as e:
                    print(f"Error adding frame to buffer: {e}")
                    
            # Push frame to LSL if enabled
            if self.push_to_lsl and self.outlet is not None:
                try:
                    # Reshape frame to 1D array
                    frame_data = frame.reshape(-1)
                    self.outlet.push_sample(frame_data)
                except Exception as e:
                    print(f"Error pushing frame to LSL: {e}")
                    
            # Add frame to video writer queue if saving video
            if self.save_video and self.video_writer is not None:
                try:
                    if not self.frame_queue.full():
                        self.frame_queue.put(frame)
                except Exception as e:
                    print(f"Error adding frame to video queue: {e}")
            
            # Show preview if enabled
        if self.show_preview:
                try:
                    cv2.imshow('Camera Preview', frame)
                    key = cv2.waitKey(1)
                    if key == ord('q'):
                        self.stop()
                    elif key == ord('s'):
                        self.trigger_manually()
                    elif key == ord('x'):
                        self.stop_manually()
                except Exception as e:
                    print(f"Error showing preview: {e}")
                    
            return frame
            
        except Exception as e:
            print(f"Error capturing frame: {e}")
            return None

    def _initialize_buffer_trigger(self):
        """Initialize the buffer trigger system."""
        if not self.use_buffer:
            return
            
        try:
            # Create buffer trigger manager
            self.buffer_trigger_manager = BufferTriggerManager(
                buffer_size_seconds=self.buffer_size_seconds,
                ntfy_topic=self.ntfy_topic,
                on_trigger=self._handle_recording_trigger,
                on_stop=self._handle_recording_stop
            )
            
            # Set initial state
            self.waiting_for_trigger = True
            self.recording_triggered = False
            
            # Set buffer reference for easier access
            self.buffer = self.buffer_trigger_manager.buffer
            
            # Start buffer trigger manager
            self.buffer_trigger_manager.start()
            print(f"Buffer trigger system initialized with {self.buffer_size_seconds}s buffer")
            print(f"Waiting for trigger notification on ntfy topic: {self.ntfy_topic}")
            print(f"To start recording: curl -d \"Start Recording\" ntfy.sh/{self.ntfy_topic}")
            print(f"To stop recording: curl -d \"Stop Recording\" ntfy.sh/{self.ntfy_topic}")
            
        except Exception as e:
            print(f"Error initializing buffer trigger system: {e}")
            self.buffer_trigger_manager = None
            self.buffer = None
            self.waiting_for_trigger = False
            self.recording_triggered = False
            
    def _handle_recording_trigger(self, frames):
        """Handle recording trigger from buffer trigger manager."""
        if self.recording_triggered:
            print("Recording already active, ignoring trigger")
            return
            
        try:
            print(f"Recording triggered with {len(frames)} frames in buffer")
            
            # Initialize video writer if not already done
            if self.save_video and self.video_writer is None:
                self._initialize_video_writer()
                
            # Write buffered frames
            if self.save_video and self.video_writer is not None:
                for frame in frames:
                    if not self.frame_queue.full():
                        self.frame_queue.put(frame)
            else:
                print("Frame queue full, dropping frame")
                        
            # Update state
            self.waiting_for_trigger = False
            self.recording_triggered = True
            print("Recording started")
            
                          except Exception as e:
            print(f"Error handling recording trigger: {e}")
            
    def _handle_recording_stop(self):
        """Handle recording stop from buffer trigger manager."""
        if not self.recording_triggered:
            print("Recording not active, ignoring stop")
            return
            
        try:
            print("Recording stop triggered")
            
            # Release video writer
            if self.video_writer is not None:
                try:
                    self.video_writer.release()
                 except Exception as e:
                    print(f"Error releasing video writer: {e}")
                finally:
                    self.video_writer = None
                    
            # Update state
            self.waiting_for_trigger = True
            self.recording_triggered = False
            print("Recording stopped")
            
                 except Exception as e:
            print(f"Error handling recording stop: {e}")

    def manual_trigger(self):
        """Manually trigger recording if using buffer mode."""
        if not self.use_buffer or not self.buffer_trigger_manager:
            print("Manual trigger only available in buffer mode")
            return False
            
        if self.recording_triggered:
            print("Recording already triggered")
            return False
            
        print("Manually triggering recording")
        self.buffer_trigger_manager.trigger_manually()
        return True
        
    def manual_stop(self):
        """Manually stop recording if using buffer mode."""
        if not self.use_buffer or not self.buffer_trigger_manager:
            print("Manual stop only available in buffer mode")
            return False
            
        if not self.recording_triggered:
            print("Recording not active")
            return False
            
        print("Manually stopping recording")
        self.buffer_trigger_manager.stop_manually()
        return True

    def get_info(self):
        """Returns a dictionary containing the current stream configuration and status."""
        qsize = -1  # Indicate queue not applicable if not threaded
        if self.save_video and self.frame_queue is not None:
            qsize = self.frame_queue.qsize()
        
        buffer_info = {}
        if self.use_buffer and self.buffer_trigger_manager:
            buffer_size = self.buffer_trigger_manager.buffer.get_buffer_size()
            buffer_duration = self.buffer_trigger_manager.buffer.get_buffer_duration()
            buffer_info = {
                "buffer_size_frames": buffer_size,
                "buffer_duration_seconds": buffer_duration,
                "waiting_for_trigger": self.waiting_for_trigger,
                "recording_triggered": self.recording_triggered,
                "ntfy_topic": self.ntfy_topic
            }
        
        return {
            "width": self.width,
            "height": self.height,
            "actual_fps": self.actual_fps,
            "lsl_pixel_format": self.lsl_pixel_format,
            "num_channels": self.num_channels,
            "stream_name": self.stream_name,
            "source_id": self.source_id,
            "camera_model": self.camera_model,
            "source_type": "PiCamera" if self.is_picamera else "Webcam",
            "is_running": self._is_running,
            "auto_output_filename": self.auto_output_filename if hasattr(self, 'auto_output_filename') else None,
            "threaded_writer_enabled": self.save_video,
            "frame_queue_size": qsize,
            "buffer_mode": self.use_buffer,
            "capture_cpu_core": self.capture_cpu_core,
            "writer_cpu_core": self.writer_cpu_core,
            "lsl_cpu_core": self.lsl_cpu_core,
            **buffer_info
        }

    def get_frame_count(self):
        """Returns the number of frames attempted to be processed by capture_frame."""
        return self.frame_count

    def get_frames_written(self):
        """Returns the total number of frames successfully written to the video file."""
        return self.frames_written_count
    
    def get_frames_dropped(self):
        """Returns the number of frames dropped because the writer queue was full."""
        return self.frames_dropped_count

    # Ensure cleanup if the object is deleted or goes out of scope
    def __del__(self):
        """Destructor to ensure stop() is called for cleanup."""
        # print(f"LSLCameraStreamer object ({self.source_id}) being deleted. Ensuring stop().")
        self.stop() # Call stop on deletion

class StatusDisplay:
    """Display real-time status updates in the terminal."""
    
    def __init__(self, update_interval=1.0):
        """Initialize the status display.
        
        Args:
            update_interval (float): Update interval in seconds.
        """
        self.update_interval = update_interval
        self.stop_event = threading.Event()
        self.display_thread = None
        self.frame_count = 0
        self.frames_written = 0
        self.frames_dropped = 0
        self.buffer_size = 0
        self.buffer_duration = 0.0
        self.recording_active = False
        self.start_time = None
        self.fps = 0.0
        self.camera_model = "Unknown"
        self.resolution = "0x0"
        self.ntfy_topic = "Unknown"
        self.last_message = ""
        self.last_message_time = 0
        
    def start(self):
        """Start the status display thread."""
        if self.display_thread is not None:
            return
            
        self.start_time = time.time()
        self.stop_event.clear()
        self.display_thread = threading.Thread(target=self._display_loop, daemon=True)
        self.display_thread.start()
        
    def stop(self):
        """Stop the status display thread."""
        if self.display_thread is None:
            return
            
        self.stop_event.set()
        self.display_thread.join(timeout=2.0)
        self.display_thread = None
        
    def update(self, frame_count, frames_written, frames_dropped, buffer_size, buffer_duration=0.0, 
               recording_active=False, camera_model="Unknown", resolution="0x0", ntfy_topic="Unknown"):
        """Update status values."""
        self.frame_count = frame_count
        self.frames_written = frames_written
        self.frames_dropped = frames_dropped
        self.buffer_size = buffer_size
        self.buffer_duration = buffer_duration
        self.recording_active = recording_active
        self.camera_model = camera_model
        self.resolution = resolution
        self.ntfy_topic = ntfy_topic
        
    def notify(self, message):
        """Record a notification message to display."""
        self.last_message = message
        self.last_message_time = time.time()
        
    def _display_loop(self):
        """Display loop that updates status periodically."""
        # Print initial blank lines for status display
        for i in range(15):
            print("")
            
        while not self.stop_event.is_set():
            try:
                # Calculate elapsed time and FPS
                elapsed_time = time.time() - self.start_time
                self.fps = self.frame_count / elapsed_time if elapsed_time > 0 else 0
                
                # Format elapsed time as HH:MM:SS
                hours = int(elapsed_time // 3600)
                minutes = int((elapsed_time % 3600) // 60)
                seconds = int(elapsed_time % 60)
                elapsed_formatted = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                
                # Clear previous display (move up 15 lines and clear each line)
                print("\033[15A", end="")
                for i in range(15):
                    print("\033[K")
                print("\033[15A", end="")
                
                # Print header with timestamp
                current_time = time.strftime("%Y-%m-%d %H:%M:%S")
                print(f"┌────────────────────────────────────────────────────────────────┐")
                print(f"│ RASPBERRY PI CAMERA CAPTURE - {current_time} │")
                print(f"├────────────────────────────────────────────────────────────────┤")
                
                # Print camera info
                print(f"│ Camera: {self.camera_model:<20} Resolution: {self.resolution:<11} │")
                print(f"│ Runtime: {elapsed_formatted}                 FPS: {self.fps:.1f}        │")
                print(f"├────────────────────────────────────────────────────────────────┤")
                
                # Print recording status
                status = "RECORDING" if self.recording_active else "WAITING FOR TRIGGER"
                print(f"│ Status: {status:<46} │")
                print(f"├────────────────────────────────────────────────────────────────┤")
                
                # Print buffer and frame statistics
                print(f"│ Buffer size: {self.buffer_size} frames ({self.buffer_duration:.1f}s)                      │")
                print(f"│ Frames captured: {self.frame_count:<10}                            │")
                print(f"│ Frames written: {self.frames_written:<10}                           │")
                print(f"│ Frames dropped: {self.frames_dropped:<10}                           │")
                print(f"├────────────────────────────────────────────────────────────────┤")
                
                # Print notification and control info
                msg_age = time.time() - self.last_message_time
                last_msg = self.last_message if msg_age < 10.0 else ""
                print(f"│ NTFY topic: {self.ntfy_topic:<42} │")
                print(f"│ Last message: {last_msg:<41} │")
                print(f"└────────────────────────────────────────────────────────────────┘")
                
                # Wait for next update
                time.sleep(self.update_interval)
                
            except Exception as e:
                print(f"Error in status display: {e}")
                time.sleep(1.0)

# (Optional: Old standalone function - kept commented out for reference if needed)
# def stream_camera(...): ... 