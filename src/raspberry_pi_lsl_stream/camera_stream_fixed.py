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

# Import Picamera2 
print("DEBUG: Importing picamera2 for Raspberry Pi Camera...")
try:
    from picamera2 import Picamera2
    PICAMERA2_AVAILABLE = True
    print("DEBUG: picamera2 imported successfully.")
except ImportError as e:
    print(f"ERROR: Failed to import picamera2: {e}")
    print("This application requires picamera2 to be installed.")
    PICAMERA2_AVAILABLE = False

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
                 lsl_cpu_core=None):
        """Initialize the camera streamer.

        Args:
            width (int): Desired frame width.
            height (int): Desired frame height.
            target_fps (float): Target frame rate.
            save_video (bool): Whether to save video files.
            output_path (str): Path to save video files.
            codec (str): Video codec to use ('h264', 'h265', 'mjpg').
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
        self.camera_model = "Raspberry Pi Camera"
        self.source_id = str(uuid.uuid4())
        self.lsl_pixel_format = "BGR"
        self.num_channels = 3
        self.buffer = None  # Initialize buffer reference
        
        # Create output directory if needed
        if self.output_path:
            os.makedirs(self.output_path, exist_ok=True)
            
        # Initialize camera
        self.camera = None
        self.camera_lock = threading.Lock()
        
        # Check if picamera2 is available
        if not PICAMERA2_AVAILABLE:
            raise RuntimeError("Picamera2 is required but not available. Please install picamera2.")
               
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
        """Initialize the Pi Camera."""
        try:
            print("Initializing Raspberry Pi Camera...")
            
            # Create PiCamera object
            self.camera = Picamera2()
            
            # Configure camera with explicit H264-friendly settings
            # Using BGR format directly since that's what the camera provides
            config = self.camera.create_video_configuration(
                main={"size": (self.width, self.height), "format": "BGR888"},
                lores={"size": (self.width, self.height), "format": "YUV420"}
            )
            
            # Set additional video parameters
            config["controls"] = {
                "FrameRate": self.target_fps,
                "NoiseReductionMode": 1  # Fast noise reduction
            }
            
            self.camera.configure(config)
            
            # Start camera
            self.camera.start()
            print(f"PiCamera initialized with resolution {self.width}x{self.height} at target {self.target_fps} fps")
            
            # Set frame rate
            self.actual_fps = self.target_fps
            print(f"PiCamera frame rate set to: {self.actual_fps} fps")
            print(f"PiCamera color format: BGR888 (native for OpenCV)")
            
            # Test frame capture - using capture_array() which is the correct method for picamera2
            try:
                frame = self.camera.capture_array("main")
                if frame is None or frame.size == 0:
                    raise RuntimeError("Failed to capture test frame (empty frame)")
            except Exception as e:
                print(f"Error during test frame capture: {e}")
                raise
                
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
            raise RuntimeError(f"Failed to initialize PiCamera: {e}")

    def _initialize_video_writer(self):
        """Initialize the video writer for saving frames."""
        if not self.save_video:
            return
            
        try:
            # Generate output filename with timestamp
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Use mp4 extension only when using h264/h265
            if self.codec.lower() in ['h264', 'h265']:
                extension = "mp4"
            else:
                extension = "avi"  # Use AVI for MJPG
                
            self.auto_output_filename = f"recording_{timestamp}.{extension}"
            
            # Create full output path
            if self.output_path:
                output_file = os.path.join(self.output_path, self.auto_output_filename)
            else:
                output_file = self.auto_output_filename
                
            print(f"Initializing video writer for file: {output_file}")
            
            # Determine codec - using Raspberry Pi compatible FourCC codes
            codec_map = {
                'h264': 'X264',  # X264 is more compatible with Raspberry Pi
                'h265': 'X265',  # X265 for HEVC codec
                'mjpg': 'MJPG'   # Motion JPEG
            }
            
            if self.codec.lower() not in codec_map:
                print(f"Warning: Unsupported codec '{self.codec}'. Falling back to h264/X264.")
                fourcc = cv2.VideoWriter_fourcc(*'X264')
            else:
                fourcc = cv2.VideoWriter_fourcc(*codec_map[self.codec.lower()])
                
            print(f"Using codec: {self.codec.lower()} with FourCC: {codec_map.get(self.codec.lower(), 'X264')}")
            
            # Create video writer
            self.video_writer = cv2.VideoWriter(
                output_file,
                fourcc,
                self.actual_fps,
                (self.width, self.height)
            )
            
            if not self.video_writer.isOpened():
                # Try an alternate codec if the first one failed
                print("Failed to open video writer with primary codec, trying MJPG as fallback...")
                fallback_file = os.path.join(os.path.dirname(output_file), 
                                            f"fallback_{os.path.basename(output_file)}.avi")
                self.video_writer = cv2.VideoWriter(
                    fallback_file,
                    cv2.VideoWriter_fourcc(*'MJPG'),
                    self.actual_fps,
                    (self.width, self.height)
                )
                if not self.video_writer.isOpened():
                    raise RuntimeError(f"Failed to open video writer with any codec")
                else:
                    print(f"Successfully opened video writer with fallback MJPG codec: {fallback_file}")
                    
            # Initialize frame queue for threaded writing
            self.frame_queue = Queue(maxsize=int(self.queue_size_seconds * self.actual_fps))
            
            # Start writer thread
            self.stop_writer_event = threading.Event()
            self.writer_thread = threading.Thread(target=self._writer_loop, daemon=True)
            self.writer_thread.start()
            
            print(f"Video writer initialized successfully")
            
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
            except Empty:
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
            self.info.desc().append_child_value("camera_model", "IMX708")
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
            return False
            
        try:
            # Initialize camera - we only need to do this once
            print("Starting Pi camera...")
            self._initialize_camera()
            
            # Set running flag
            self._is_running = True
            print("Camera stream started")
            return True
            
        except Exception as e:
            print(f"Error starting camera stream: {e}")
            self.stop()
            return False

    def stop(self):
        """Stop the camera capture and processing loop."""
        if not self._is_running:
            return 
            
        print("Stopping camera stream...")
        self._is_running = False
        
        # Stop writer thread if running
        if self.writer_thread is not None and self.stop_writer_event is not None:
            self.stop_writer_event.set()
            self.writer_thread.join(timeout=2.0)
            
        # Release video writer
        if self.video_writer is not None:
            try:
                self.video_writer.release()
            except Exception as e:
                print(f"Error releasing video writer: {e}")
                
        # Release camera
        if self.camera is not None:
            try:
                self.camera.stop()
            except Exception as e:
                print(f"Error stopping PiCamera: {e}")
                    
        # Close preview window
        if self.show_preview:
            cv2.destroyAllWindows()
            
        print("Camera stream stopped")

    def capture_frame(self):
        """Capture a single frame from the camera."""
        try:
            if not self._is_running:
                return None
                
            # Capture frame from PiCamera
            with self.camera_lock:
                try:
                    # Use capture_array() which is the correct method for picamera2
                    frame = self.camera.capture_array("main")
                except Exception as e:
                    print(f"Failed to grab frame from camera: {e}")
                    return None
                    
                # Check if frame is valid
                if frame is None or frame.size == 0:
                    print("Failed to capture frame")
                    return None
                
                # BGR format is already compatible with OpenCV - no conversion needed
                
            # Update frame count
            self.frame_count += 1
            
            # Push frame to LSL if enabled
            if self.push_to_lsl and self.outlet is not None:
                try:
                    # Reshape frame to 1D array
                    frame_data = frame.reshape(-1)
                    self.outlet.push_sample(frame_data)
                except Exception as e:
                    print(f"Error pushing frame to LSL: {e}")
                    
            # Add frame to buffer if enabled
            if self.use_buffer and self.buffer:
                try:
                    self.buffer.add_frame(frame)
                except Exception as e:
                    print(f"Error adding frame to buffer: {e}")
            
            # Show preview if enabled
            if self.show_preview:
                try:
                    cv2.imshow('Camera Preview', frame)
                    key = cv2.waitKey(1)
                    if key == ord('q'):
                        self.stop()
                    elif key == ord('s'):
                        self.manual_trigger()
                    elif key == ord('x'):
                        self.manual_stop()
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
            if self.save_video and self.video_writer is not None and self.frame_queue is not None:
                for frame, timestamp in frames:
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
                    self.video_writer = None
                except Exception as e:
                    print(f"Error releasing video writer: {e}")
                    
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
            "source_type": "PiCamera",
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
        self.stop() # Call stop on deletion

class StatusDisplay:
    """Display real-time status updates in the terminal."""
    
    def __init__(self, camera_streamer=None, buffer_manager=None, ntfy_topic=None, update_interval=1.0):
        """Initialize the status display.
        
        Args:
            camera_streamer: The LSLCameraStreamer instance to monitor
            buffer_manager: The BufferTriggerManager instance to monitor
            ntfy_topic: The ntfy topic for remote control
            update_interval: Update interval in seconds
        """
        self.update_interval = update_interval
        self.camera_streamer = camera_streamer
        self.buffer_manager = buffer_manager
        self.ntfy_topic = ntfy_topic
        self.stop_event = threading.Event()
        self.display_thread = None
        
    def start(self):
        """Start the status display thread."""
        if self.display_thread is not None:
            return
            
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
        
    def update(self):
        """Update the display with current information."""
        if not self.camera_streamer:
            return
            
        info = self.camera_streamer.get_info()
        
        # Get buffer info
        buffer_size = 0
        buffer_duration = 0.0
        recording_active = False
        
        if self.buffer_manager:
            buffer_size = self.buffer_manager.get_buffer_size()
            buffer_duration = self.buffer_manager.get_buffer_duration()
            recording_active = not self.camera_streamer.waiting_for_trigger
            
        # Print status
        print("\033[H\033[J")  # Clear screen
        print(f"=== Camera Status ===")
        print(f"Camera: {info['source_type']} ({info['width']}x{info['height']})")
        print(f"FPS: {info['actual_fps']:.1f}")
        print(f"Frames captured: {self.camera_streamer.get_frame_count()}")
        print(f"Frames written: {self.camera_streamer.get_frames_written()}")
        print(f"Frames dropped: {self.camera_streamer.get_frames_dropped()}")
        print(f"Buffer size: {buffer_size} frames ({buffer_duration:.1f}s)")
        print(f"Recording: {'ACTIVE' if recording_active else 'WAITING FOR TRIGGER'}")
        print(f"NTFY topic: {self.ntfy_topic}")
        print(f"Press 's' to start recording, 'x' to stop, 'q' to quit")
        
    def _display_loop(self):
        """Thread function to update the display periodically."""
        while not self.stop_event.is_set():
            try:
                self.update()
                time.sleep(self.update_interval)
            except Exception as e:
                print(f"Error updating status display: {e}")
                time.sleep(1.0) 