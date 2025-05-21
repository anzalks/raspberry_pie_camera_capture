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
    def __init__(self, width=640, height=480, fps=30, pixel_format='RGB888',
                 stream_name='RaspieVideo', source_id='RaspieCapture_Video',
                 show_preview=False,
                 use_max_settings=False,
                 queue_size_seconds=5,
                 output_path=None,
                 camera_index='auto',
                 save_video=True,
                 codec='auto',
                 bitrate=0,
                 quality_preset='medium',
                 buffer_size_seconds=20,
                 use_buffer=False,
                 ntfy_topic=None,
                 push_to_lsl=True,
                 threaded_writer=False,
                 capture_cpu_core=None,
                 writer_cpu_core=None,
                 visualizer_cpu_core=None):
        """
        Initializes the streamer configuration and sets up camera and LSL.

        Args:
            width (int): Desired frame width.
            height (int): Desired frame height.
            fps (int): Desired frame rate.
            pixel_format (str): Desired pixel format for PiCamera (e.g., 'RGB888', 'XBGR8888').
                                Ignored if use_webcam is True.
            stream_name (str): Name for the LSL stream.
            source_id (str): Unique identifier for the LSL stream source.
            show_preview (bool): If True, display a live preview window using OpenCV.
            use_max_settings (bool): If True, attempt to use max resolution/FPS for webcams.
            queue_size_seconds (int): Approximate buffer size in seconds for the video writer queue.
            output_path (str, optional): Directory path to save the video file. Defaults to current directory if None.
            camera_index (str | int): Specific camera to use ('auto', 'pi', or int index). Default 'auto'.
            save_video (bool): Whether to save the video to a file. Default True.
            codec (str): Preferred video codec ('h264', 'h265', 'mjpg', 'auto'). Default 'auto'.
            bitrate (int): Constant bitrate in Kbps (0=codec default). Default 0.
            quality_preset (str): Encoding quality preset (e.g., 'medium', 'fast'). Default 'medium'.
            buffer_size_seconds (int): Size of the rolling buffer in seconds for pre-trigger recording.
            use_buffer (bool): Whether to use the rolling buffer for pre-trigger recording.
            ntfy_topic (str): The ntfy topic to subscribe to for recording triggers.
            push_to_lsl (bool): Whether to push frames to LSL. Default True.
            threaded_writer (bool): Whether to use a separate thread for writing frames. Default False.
            capture_cpu_core (int): Specific CPU core for capture operations. Default None.
            writer_cpu_core (int): Specific CPU core for writer thread. Default None.
            visualizer_cpu_core (int): Specific CPU core for visualization. Default None.
        """
        
        # Store configuration parameters
        # Note: width, height, fps might be overridden by use_max_settings for webcams
        self.requested_width = width 
        self.requested_height = height
        self.requested_fps = float(fps)
        self.pixel_format = pixel_format # PiCam specific format request
        self.stream_name = stream_name
        self.source_id = source_id
        self.is_picamera = False # Flag to indicate if PiCamera is being used
        self.show_preview = show_preview 
        self.use_max_settings = use_max_settings
        self.queue_size_seconds = queue_size_seconds
        self.threaded_writer = threaded_writer # <<< ALWAYS True now
        self.auto_output_filename = None
        self.video_writer = None
        self.output_path = output_path # Store the output path
        self.requested_camera_index = camera_index # Store requested index
        self.save_video = save_video # <<< Store flag
        self.codec = codec.lower()  # Store preferred codec
        self.bitrate = bitrate      # Store bitrate setting
        self.quality_preset = quality_preset  # Store quality preset
        
        # CPU core assignments for threads
        self.capture_cpu_core = capture_cpu_core
        self.writer_cpu_core = writer_cpu_core
        self.visualizer_cpu_core = visualizer_cpu_core
        
        # Buffer and trigger configuration
        self.buffer_size_seconds = buffer_size_seconds
        self.use_buffer = use_buffer
        self.ntfy_topic = ntfy_topic
        self.buffer_trigger_manager = None
        self.waiting_for_trigger = use_buffer  # Start in waiting mode if buffer enabled
        self.recording_triggered = False       # Flag to track if recording was triggered

        # Internal state variables that get set during init
        self.width = width # Actual width used
        self.height = height # Actual height used
        self.cap = None
        self.picam2 = None
        self.lsl_pixel_format = pixel_format
        self.num_channels = 3
        self.actual_fps = self.requested_fps
        self.camera_model = "Unknown" 
        self.outlet = None
        self.info = None
        self.frame_count = 0
        self.frames_written_count = 0
        self.frames_dropped_count = 0
        self._is_running = False

        # --- Threading components ---
        self.frame_queue = None # Conditionally initialized
        self.stop_writer_event = threading.Event()
        self.writer_thread = None
        # ---

        # Initialize camera and LSL stream upon instantiation
        try:
            self._initialize_camera()
            self._setup_lsl()
            
            # Initialize buffer trigger manager if enabled
            if self.use_buffer:
                self._initialize_buffer_trigger()
            
            if self.save_video and not self.use_buffer:
                # If using a buffer, we'll initialize video writer only after trigger
                self._initialize_video_writer()
            
            # Create preview window if requested (do this after knowing dimensions)
            if self.show_preview:
                self.preview_window_name = f"Preview: {self.stream_name}"
                cv2.namedWindow(self.preview_window_name, cv2.WINDOW_NORMAL)
                cv2.resizeWindow(self.preview_window_name, self.width // 2, self.height // 2) # Smaller preview
        except Exception as e:
            # Ensure cleanup if initialization fails
            print(f"Streamer initialization failed: {e}")
            self.stop() # Attempt to release any partially acquired resources
            raise # Re-raise the exception to signal failure

    def _initialize_camera(self):
        """Initializes the camera based on requested_camera_index ('auto', 'pi', or int)."""
        initialized = False
        is_linux = platform.system() == 'Linux'
        picam2_usable = is_linux and PICAMERA2_AVAILABLE
        requested_index = self.requested_camera_index

        print(f"Starting camera initialization (Requested: '{requested_index}')...")

        # --- Handle explicit requests --- 
        if isinstance(requested_index, int) or requested_index.isdigit():
            # Explicit webcam index request
            try:
                 index_to_try = int(requested_index)
                 print(f"Explicitly trying Webcam index {index_to_try}...")
                 if self._initialize_webcam(index_to_try):
                    initialized = True
                 else:
                     raise RuntimeError(f"Failed to initialize explicitly requested Webcam index {index_to_try}.")
            except ValueError:
                 raise ValueError(f"Invalid integer format for --camera-index: '{requested_index}'")
        
        elif requested_index == 'pi':
            # Explicit PiCamera request
            print("Explicitly trying PiCamera...")
            if not picam2_usable:
                 raise RuntimeError("PiCamera requested ('--camera-index pi') but picamera2 library not available or not on Linux.")
            if self._initialize_picamera():
                initialized = True
            else:
                 raise RuntimeError("Failed to initialize explicitly requested PiCamera.")

        elif requested_index == 'auto':
            # --- Automatic detection logic --- 
            print("Using automatic camera detection ('auto')...")
            if picam2_usable:
                print("picamera2 library available. Prioritizing PiCamera...")
                if self._initialize_picamera():
                    initialized = True
                else:
                    print("PiCamera initialization failed. Falling back to detecting and trying Webcams...")
                    # Try webcams only if PiCamera fails
                    webcam_indices_to_try = self._detect_webcam_indices(is_linux)
                    for index in webcam_indices_to_try:
                        if self._initialize_webcam(index):
                            initialized = True
                            break # Stop on first success
            else:
                print("picamera2 library not available or not Linux. Detecting and trying Webcams...")
                webcam_indices_to_try = self._detect_webcam_indices(is_linux)
                for index in webcam_indices_to_try:
                    if self._initialize_webcam(index):
                        initialized = True
                        break # Stop on first success
        else:
             # Invalid string for requested_index
             raise ValueError(f"Invalid value for --camera-index: '{requested_index}'. Use 'auto', 'pi', or an integer.")

        # --- Final Check ---
        if not initialized:
            # Construct error message based on what was attempted
            error_message = "Could not initialize any camera. "
            if isinstance(requested_index, int) or requested_index.isdigit():
                 error_message += f"Attempted Webcam index {requested_index}. "
            elif requested_index == 'pi':
                 error_message += "Attempted PiCamera. "
            elif requested_index == 'auto':
                 if picam2_usable:
                     error_message += "Attempted PiCamera (failed) and detected Webcams. "
            else:
                     error_message += "Attempted detected Webcams. "
            error_message += "Initialization failed."
            raise RuntimeError(error_message)
            
    def _detect_webcam_indices(self, is_linux):
        """Detects available /dev/videoX indices on Linux, returns default list otherwise."""
        indices = []
        if is_linux:
            try:
                print("Detecting video devices in /dev/...")
                devices = glob.glob('/dev/video*')
                for device in devices:
                    try:
                        # Extract number from end of /dev/videoX
                        index = int(device.replace('/dev/video', '')) 
                        indices.append(index)
                    except (ValueError, IndexError):
                        print(f"  Warning: Could not parse index from device '{device}'. Skipping.")
                        continue
                indices.sort() # Try lower indices first
                if indices:
                    print(f"  Detected potential webcam indices: {indices}")
                else:
                    print("  No /dev/video* devices found. Will try default indices [0, 1].")
                    indices = [0, 1] # Fallback if glob finds nothing
            except Exception as e:
                print(f"Error detecting video devices: {e}. Will try default indices [0, 1].")
                indices = [0, 1]
        else:
            print("Not on Linux. Will try default webcam indices [0, 1].")
            indices = [0, 1] # Default for non-Linux
        return indices

    def _initialize_webcam(self, index):
        """Attempts to initialize and configure a specific webcam index."""
        print(f"Attempting to initialize Webcam index {index} via OpenCV...")
        cap_attempt = None
        try:
            cap_attempt = cv2.VideoCapture(index)
            if cap_attempt is None or not cap_attempt.isOpened():
                print(f"Warning: Could not open webcam index {index}.")
                if cap_attempt: cap_attempt.release()
                return False

            print(f"Successfully opened Webcam index {index}. Configuring...")
            self.cap = cap_attempt # Assign to self.cap only if successful

            # --- Max Settings or Requested Settings Logic ---
            detected_width = 0
            detected_height = 0
            detected_fps = 0.0
            
            if self.use_max_settings:
                print("Attempting to detect maximum settings using heuristic...")
                # Try setting very high resolution and reading back
                try:
                    if self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 4096) and \
                       self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 4096):
                        time.sleep(0.1) # Allow driver time to settle
                        detected_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                        detected_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                        if detected_width > 0 and detected_height > 0:
                             print(f"  Detected Resolution: {detected_width}x{detected_height}")
                        else:
                             print("  Warning: Failed to get valid resolution after setting high value.")
                             detected_width = 0 # Reset if invalid
                             detected_height = 0
                    else:
                        print("  Warning: Failed to set high resolution for detection.")
                except Exception as e_res:
                    print(f"  Warning: Error during resolution detection: {e_res}")

                # Use detected resolution (if valid) for FPS detection, else requested
                temp_width = detected_width if detected_width > 0 else self.requested_width
                temp_height = detected_height if detected_height > 0 else self.requested_height
                
                # Try setting very high FPS and reading back (after setting width/height)
                try:
                    if self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, temp_width) and \
                       self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, temp_height) and \
                       self.cap.set(cv2.CAP_PROP_FPS, 120): # Try high FPS
                        time.sleep(0.1)
                        detected_fps = self.cap.get(cv2.CAP_PROP_FPS)
                        if detected_fps > 0:
                            print(f"  Detected FPS: {detected_fps}")
                        else:
                             print("  Warning: Failed to get valid FPS after setting high value.")
                             detected_fps = 0.0 # Reset if invalid
                    else:
                        print("  Warning: Failed to set high FPS for detection.")
                except Exception as e_fps:
                    print(f"  Warning: Error during FPS detection: {e_fps}")
            
            # Decide which settings to actually use
            target_width = self.requested_width
            target_height = self.requested_height
            target_fps = self.requested_fps
            
            if self.use_max_settings and detected_width > 0 and detected_height > 0:
                print("Using detected resolution for configuration.")
                target_width = detected_width
                target_height = detected_height
                # Only use detected FPS if it's valid
                if detected_fps > 0:
                     print("Using detected FPS for configuration.")
                     target_fps = detected_fps
                else:
                     print("Detected FPS invalid, using requested FPS.")
            else:
                 print("Using requested/default settings for configuration.")

            # Set the final target properties
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, target_width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, target_height)
            self.cap.set(cv2.CAP_PROP_FPS, target_fps)
            time.sleep(0.1) # Give it a moment to apply settings

            # Read back final actual properties
            actual_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            actual_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            actual_fps_cv2 = self.cap.get(cv2.CAP_PROP_FPS)

            print(f"Webcam final request: {target_width}x{target_height} @ {target_fps:.2f}fps.")
            print(f"Webcam actual properties: {actual_width}x{actual_height} @ {actual_fps_cv2:.2f}fps.")

            # Check if properties were set correctly (some cameras ignore requests)
            if actual_width == 0 or actual_height == 0:
                 print("Error: Webcam returned zero dimensions after configuration. Cannot use.")
                 self.cap.release()
                 self.cap = None
                 return False
                 
            # Update internal state with actual values
            self.width = actual_width
            self.height = actual_height
            self.actual_fps = actual_fps_cv2
            if self.actual_fps <= 0:
                print(f"Warning: Webcam reported invalid final FPS ({actual_fps_cv2}). Using requested FPS ({self.requested_fps}) as fallback.")
                self.actual_fps = self.requested_fps
            else:
                 print(f"Using actual webcam FPS {self.actual_fps:.2f}.")

            self.num_channels = 3
            self.lsl_pixel_format = 'BGR888'
            self.camera_model = f"OpenCV Webcam {index}"
            print(f"Using selected Webcam (index {index}).")
            self.is_picamera = False
            return True # Webcam succeeded

        except Exception as e:
            print(f"Error during webcam index {index} initialization: {e}")
            traceback.print_exc()
            if cap_attempt is not None:
                cap_attempt.release()
            self.cap = None # Ensure cap is None if error occurred
            return False

    def _initialize_picamera(self):
        """Attempts to initialize and configure the PiCamera, verifying the model."""
        if not PICAMERA2_AVAILABLE:
            return False # Should not happen if called correctly, but safeguard
            
        target_format = 'BGR888' 
        temp_picam2 = None # Use a temporary object for initial check
        try:
            print(f"Attempting to initialize PiCamera object...")
            temp_picam2 = Picamera2()
            
            # --- Verify Camera Model ---
            cam_props = temp_picam2.camera_properties
            cam_model = cam_props.get('Model', 'Unknown')
            print(f"  picamera2 detected model: {cam_model}")
            
            # Heuristic check for non-Pi camera models
            # Add known USB/Webcam identifiers here if needed
            non_pi_identifiers = ['usb', 'webcam', 'logitech', 'angetube'] 
            is_non_pi_cam = any(identifier in cam_model.lower() for identifier in non_pi_identifiers)
            
            if is_non_pi_cam:
                 print(f"  Detected model '{cam_model}' does not appear to be a Pi Camera module. Skipping picamera2 initialization.")
                 temp_picam2.close() # Release the temporary object
                 return False # Indicate failure so fallback can occur
            # ---
            
            # If we passed the check, assign to self and configure
            self.picam2 = temp_picam2 
            self.camera_model = cam_model # Store the verified model
            
            print(f"Configuring PiCamera ({self.camera_model}) for {self.requested_width}x{self.requested_height} @ {self.requested_fps:.2f}fps, format {target_format}...")

            config = self.picam2.create_video_configuration(
                main={"size": (self.requested_width, self.requested_height), "format": target_format}
            )
            self.picam2.configure(config)
            
            # Now attempt to set controls AFTER configuration, if needed
            try:
                 print(f"Setting FrameRate control to {self.requested_fps}...")
                 self.picam2.set_controls({"FrameRate": self.requested_fps})
            except RuntimeError as e_ctrl:
                 print(f"Warning: Could not set FrameRate control explicitly after configure: {e_ctrl}")
                 print("Proceeding with default/inferred frame rate.")

            # Read back actual configuration details if possible
            self.width = self.requested_width
            self.height = self.requested_height
            self.actual_fps = self.requested_fps
            self.lsl_pixel_format = target_format 
            self.num_channels = 3 # Explicitly 3 for BGR888

            print(f"PiCamera initialized successfully.")
            self.is_picamera = True
            return True

        except Exception as e:
            print(f"ERROR: PiCamera initialization/configuration failed: {e}")
            traceback.print_exc()
            # Clean up potential picam2 object (either temp or self assigned)
            if self.picam2:
                 try: self.picam2.close()
                 except: pass
                 self.picam2 = None
            elif temp_picam2: # If error happened before assignment to self.picam2
                 try: temp_picam2.close()
                 except: pass
            self.is_picamera = False
            return False

    def _initialize_video_writer(self):
        """Initialize the OpenCV VideoWriter for saving frames to a file."""
        if not self.save_video:
            print("Video saving is disabled.")
            return
            
        # Create output directory if it doesn't exist
        if self.output_path:
            os.makedirs(self.output_path, exist_ok=True)
            
        # Generate a timestamped filename for the video file
        timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        video_file = f"raspie_video_{timestamp_str}.mkv"
        
        if self.output_path:
            self.output_file = os.path.join(self.output_path, video_file)
        else:
            self.output_file = video_file

    def _setup_lsl(self):
        """Configures and creates the LSL StreamInfo and StreamOutlet for Frame Numbers."""
        # LSL stream for frame numbers only
        channel_count = 1 # Only sending the frame number
        channel_format_lsl = 4 # cf_int32
        stream_type = 'FrameCounter'

        # Use the potentially corrected fps value
        fps_for_lsl = self.actual_fps if self.actual_fps > 0 else self.requested_fps
        if fps_for_lsl <= 0: fps_for_lsl = 30.0 # Use fallback if still invalid

        print(f"LSL Stream Info: Name='{self.stream_name}', Type={stream_type}, Channels={channel_count}, Format=cf_int32, Rate={fps_for_lsl:.2f}")

        self.info = StreamInfo(name=self.stream_name,
                               type=stream_type,
                               channel_count=channel_count,
                               nominal_srate=float(fps_for_lsl), # Use potentially corrected rate
                               channel_format=channel_format_lsl,
                               source_id=self.source_id)

        # Add metadata
        desc = self.info.desc()
        desc.append_child_value("acquisition_software", "RaspieCapture")
        desc.append_child_value("camera_model", self.camera_model)
        desc.append_child_value("source_type", "PiCamera" if self.is_picamera else "Webcam")
        
        chn = desc.append_child("channels").append_child("channel")
        chn.append_child_value("label", "FrameNumber")
        chn.append_child_value("unit", "count")
        chn.append_child_value("type", stream_type)

        try:
            self.outlet = StreamOutlet(self.info)
            print(f"LSL stream '{self.stream_name}' created and waiting for consumers.")
        except Exception as e:
            print(f"Error creating LSL outlet: {e}")
            traceback.print_exc()
            self.info = None
            raise
            
    def _writer_loop(self):
        """Method executed by the writer thread to save frames from the queue."""
        print("Writer thread started.")
        
        # Set CPU affinity if requested and available
        self._set_thread_affinity("writer thread", self.writer_cpu_core)
        
        frame_write_count = 0
        while not self.stop_writer_event.is_set() or not self.frame_queue.empty():
            try:
                frame_data = self.frame_queue.get(timeout=0.1)
                if frame_data is not None and self.video_writer is not None:
                    try:
                        self.video_writer.write(frame_data)
                        frame_write_count += 1
                    except Exception as e:
                        print(f"Error writing frame in writer thread: {e}")
                    finally:
                        self.frame_queue.task_done()
                elif frame_data is None:
                     pass
            except Empty:
                if self.stop_writer_event.is_set():
                     break
                else:
                     continue
            except Exception as e:
                 print(f"Unexpected error in writer thread loop: {e}")
                 traceback.print_exc()
        # Store the final count before exiting
        self.frames_written_count = frame_write_count
        print(f"Writer thread stopping. Total frames written by this thread: {self.frames_written_count}")

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
        """Starts the camera capture process and optionally the writer thread."""
        if self._is_running:
            print("Streamer already running.")
            return
            
        # --- Start Writer Thread (Conditional) ---
        if self.save_video and not self.use_buffer:
            # If using buffer, we'll start the writer only after trigger
            if self.video_writer is not None and self.video_writer.isOpened():
                if self.writer_thread is None:
                    print("Starting writer thread...")
                    self.stop_writer_event.clear()
                    self.writer_thread = threading.Thread(target=self._writer_loop, daemon=True)
                    self.writer_thread.start()
                else:
                    print("Warning: Writer thread object already exists.")
            else:
                print("Warning: Video writer not ready. Cannot start writer thread.")
        # ---
        
        # Start the buffer trigger manager if enabled
        if self.use_buffer and self.buffer_trigger_manager:
            self.buffer_trigger_manager.start()
            print("Started buffer trigger manager")

        # --- Start Camera ---
        camera_started = False
        if self.is_picamera and self.picam2:
            try:
                print("Starting Picamera2 capture...")
                self.picam2.start()
                camera_started = True
                print("Picamera2 started.")
            except Exception as e:
                print(f"Error starting Picamera2: {e}")
                traceback.print_exc()
        elif not self.is_picamera and self.cap:
            print("Starting OpenCV webcam capture (implicit via read)...")
            camera_started = True
        
        if camera_started:
            # Set CPU affinity for capture operations if specified
            if PSUTIL_AVAILABLE and self.capture_cpu_core is not None:
                self._set_thread_affinity("capture operations", self.capture_cpu_core)
             
            self._is_running = True
        else:
            print("Error: Camera hardware could not be started. Stopping dependent threads.")
            # Stop writer thread if it was started
            if self.save_video and self.writer_thread is not None:
                self.stop_writer_event.set()
                self.writer_thread.join(timeout=1.0)
                self.writer_thread = None
            raise RuntimeError("Failed to start camera hardware.")

    def stop(self):
        """Stops the camera capture, writer thread (if active), and releases resources."""
        # <<< Need to adjust the initial check slightly if writer isn't always used >>>
        # if not self._is_running and (not self.save_video or self.writer_thread is None):
        # Simplified: Just check if running, handle components individually
        if not self._is_running:
             return 
             
        print("Stopping stream and cleaning up resources...")
        
        # Stop the buffer trigger manager if enabled
        if self.use_buffer and self.buffer_trigger_manager:
            print("Stopping buffer trigger manager...")
            self.buffer_trigger_manager.stop()
        
        # --- Stop Camera First ---
        # This prevents more frames being added to the queue while stopping
        self._is_running = False # Signal capture loop to stop
        
        if self.is_picamera and self.picam2:
            try:
                # Check if picam2 object still exists and has 'stop'
                if self.picam2 and hasattr(self.picam2, 'is_open') and self.picam2.is_open:
                     print("Stopping Picamera2...")
                     self.picam2.stop()
                     print("Picamera2 stopped.")
                # No else needed, if not open, nothing to stop
            except Exception as e:
                print(f"Error stopping Picamera2: {e}")
            finally:
                # Close connection regardless of stop success
                try:
                    if self.picam2:
                        print("Closing Picamera2 connection...")
                        self.picam2.close()
                        print("Picamera2 closed.")
                        self.picam2 = None
                except Exception as e:
                    print(f"Error closing Picamera2 connection: {e}")
        elif not self.is_picamera and self.cap:
            try:
                if self.cap and self.cap.isOpened():
                     print("Releasing OpenCV webcam...")
                     self.cap.release()
                     print("OpenCV webcam released.")
                self.cap = None
            except Exception as e:
                print(f"Error releasing OpenCV webcam: {e}")
        
        # --- Stop Writer Thread Gracefully (Conditional) ---
        if self.save_video and self.writer_thread is not None:
            print("Signaling writer thread to stop and waiting for queue to flush...")
            self.stop_writer_event.set()
            try:
                 # Drastically Increased timeout: at least 60s, plus more based on queue size
                 join_timeout = max(60.0, self.queue_size_seconds * 3.0) # Give it much more time
                 print(f"Waiting up to {join_timeout:.1f} seconds for writer thread...")
                 self.writer_thread.join(timeout=join_timeout)
                 if self.writer_thread.is_alive():
                       print("ERROR: Writer thread is STILL ALIVE after extended timeout! Video file might be incomplete or corrupted.")
                 else:
                       print("Writer thread finished.")
            except Exception as e:
                 print(f"Error waiting for writer thread: {e}")
            self.writer_thread = None # Set to None even if it didn't join cleanly
        elif self.save_video and self.writer_thread is None:
             # Only warn if saving was intended but thread is missing
             print("Warning: Video saving enabled but writer thread object is None during stop.")

        # --- Release VideoWriter (Conditional) ---
        if self.save_video and self.video_writer is not None:
             # Check if it's still considered open by OpenCV before releasing
             # Note: This check might not be foolproof if the object is corrupted internally
             is_opened = False
             try:
                  is_opened = self.video_writer.isOpened()
             except Exception as e_check:
                  print(f"Warning: Error checking if VideoWriter is open before release: {e_check}")
            
             if is_opened:
                 print(f"Releasing video writer ('{self.output_file}')...")
                 try:
                     self.video_writer.release()
                     print("Video writer released.")
                 except Exception as e:
                     print(f"Error releasing video writer: {e}") # Still might segfault here if internal state is bad
             else:
                  print(f"Video writer ('{self.output_file}') was not considered open. Skipping release call.")
             self.video_writer = None # Set to None regardless
            
        # --- Destroy Preview Window ---
        if self.show_preview:
            if hasattr(self, 'preview_window_name'):
                print(f"Closing preview window ('{self.preview_window_name}')...")
                try:
                    if cv2.getWindowProperty(self.preview_window_name, cv2.WND_PROP_VISIBLE) >= 1:
                         cv2.destroyWindow(self.preview_window_name)
                except Exception as e:
                    pass
        
        # --- LSL Cleanup (AFTER potential LSL thread join) ---
        if self.outlet is not None:
             print("Initiating LSL stream outlet cleanup...")
             self.outlet = None
        self.info = None
        # ---

        print("Stream cleanup complete.")


    def capture_frame(self):
        """Captures a single frame, puts it in the queue (if saving), displays preview, and pushes LSL."""
        if not self._is_running:
             return None, None
             
        timestamp = local_clock()
        frame_data = None
        current_frame_index = -1
        
        try:
            # --- Capture frame ---
            if self.is_picamera and self.picam2:
                # Use the standard capture_array method which is more compatible
                try:
                    frame_data = self.picam2.capture_array("main")
                    if frame_data is None:
                        print("Warning: PiCamera capture_array returned None. Skipping frame.")
                        return None, None
                except Exception as e:
                    print(f"Error capturing frame from PiCamera: {e}")
                    traceback.print_exc()
                    return None, None
            elif not self.is_picamera and self.cap:
                # Standard OpenCV capture for webcams
                ret, frame_data = self.cap.read()
                if not ret or frame_data is None:
                    print("Warning: Failed to grab frame from webcam. Skipping.")
                    return None, None
            else:
                print("Error: Camera not available for capture (state inconsistency).")
                self._is_running = False
                return None, None
            
            # --- Assign frame index *after* successful capture ---
            current_frame_index = self.frame_count
            self.frame_count += 1

            # --- Process Frame Based on Current State ---
            
            # If using buffer and waiting for trigger, add to buffer only
            if self.use_buffer and self.waiting_for_trigger:
                if self.buffer_trigger_manager:
                    self.buffer_trigger_manager.add_frame(frame_data, timestamp)
                    
                # Still show preview even in buffer mode
                if self.show_preview and hasattr(self, 'preview_window_name'):
                    try:
                        # Set visualizer core affinity if showing preview
                        if PSUTIL_AVAILABLE and self.visualizer_cpu_core is not None and current_frame_index == 0:
                            self._set_thread_affinity("visualization", self.visualizer_cpu_core)
                            
                        if cv2.getWindowProperty(self.preview_window_name, cv2.WND_PROP_VISIBLE) >= 1:
                            cv2.imshow(self.preview_window_name, frame_data)
                            key = cv2.waitKey(1)
                            
                            # Check if 't' key pressed for manual trigger
                            if key == ord('t'):
                                print("Manual trigger activated by 't' key")
                                if self.buffer_trigger_manager:
                                    self.buffer_trigger_manager.trigger_manually()
                            # Check if 's' key pressed for manual stop
                            elif key == ord('s'):
                                print("Manual stop activated by 's' key")
                                if self.buffer_trigger_manager and self.recording_triggered:
                                    self.buffer_trigger_manager.stop_manually()
                    except Exception as e:
                        pass
                
                # Still push to LSL even in buffer mode
                if self.outlet is not None:
                    try:
                        self.outlet.push_sample([current_frame_index], timestamp)
                    except Exception as e:
                        print(f"Error pushing frame number ({current_frame_index}) to LSL: {e}")
            
            # Normal processing if recording active or not using buffer
            else:
                # --- Write Frame (Conditional: Queue Only) ---
                if self.save_video:
                     if self.video_writer is not None:
                         if self.frame_queue is not None:
                              try:
                                  # Important: Using a zero-copy view. Downstream must not modify in-place.
                                  self.frame_queue.put_nowait(frame_data)
                              except Full:
                                  print("Warning: Frame queue full. Dropping frame.")
                                  self.frames_dropped_count += 1 
                              except Exception as e:
                                   print(f"Error putting frame into queue: {e}")
                         else:
                              print("Error: Video saving enabled but queue is None.")
                     # else: # Log if writer is none? Redundant if init fails cleanly.

                # --- Push Frame Number to LSL (Always done if outlet exists) ---
                if self.outlet is not None:
                     try:
                         self.outlet.push_sample([current_frame_index], timestamp)
                     except Exception as e:
                         print(f"Error pushing frame number ({current_frame_index}) to LSL directly: {e}")
                
                # --- Show Preview (Conditional) ---
                if self.show_preview and hasattr(self, 'preview_window_name'):
                     try:
                         if cv2.getWindowProperty(self.preview_window_name, cv2.WND_PROP_VISIBLE) >= 1:
                             cv2.imshow(self.preview_window_name, frame_data)
                             cv2.waitKey(1)
                     except Exception as e:
                          print(f"Error showing preview: {e}")
                          pass
            
            return frame_data, timestamp
        except Exception as e:
            print(f"Error during frame capture/processing: {e}")
            traceback.print_exc()
            return None, None

    def _initialize_buffer_trigger(self):
        """Initialize the buffer trigger system for pre-trigger recording."""
        print(f"Initializing buffer trigger system with {self.buffer_size_seconds}s buffer")
        
        # Create buffer trigger manager with callback to our trigger handler
        self.buffer_trigger_manager = BufferTriggerManager(
            buffer_size_seconds=self.buffer_size_seconds,
            ntfy_topic=self.ntfy_topic,
            callback=self._handle_recording_trigger,
            stop_callback=self._handle_recording_stop
        )
        
        print("Buffer trigger system initialized")
        if self.ntfy_topic:
            print(f"Waiting for trigger notification on ntfy topic: {self.ntfy_topic}")
            print(f"To start recording: curl -d \"start recording\" ntfy.sh/{self.ntfy_topic}")
            print(f"To stop recording: curl -d \"stop recording\" ntfy.sh/{self.ntfy_topic}")
        else:
            print("No ntfy topic specified. Use manual triggering.")
            
    def _handle_recording_trigger(self, buffer_frames, trigger_message):
        """
        Handle recording trigger from ntfy notification.
        
        Args:
            buffer_frames: List of (frame, timestamp) tuples from the rolling buffer
            trigger_message: The notification message that triggered recording
        """
        if self.recording_triggered:
            print("Recording already triggered - ignoring duplicate trigger")
            return
            
        print(f"Recording triggered by notification: {trigger_message.get('title', 'No title')}")
        print(f"Writing {len(buffer_frames)} frames from buffer")
        
        # Set flag to indicate recording has been triggered
        self.recording_triggered = True
        self.waiting_for_trigger = False
        
        # Initialize the video writer now that we're recording
        if self.save_video and self.video_writer is None:
            self._initialize_video_writer()
            
            # Start the writer thread
            if self.video_writer is not None and self.video_writer.isOpened():
                if self.writer_thread is None:
                    print("Starting writer thread...")
                    self.stop_writer_event.clear()
                    self.writer_thread = threading.Thread(target=self._writer_loop, daemon=True)
                    self.writer_thread.start()
                    
        # Process the buffer frames (if writer is ready)
        if self.save_video and self.video_writer is not None:
            try:
                # Write the buffer frames to the video file
                for frame, timestamp in buffer_frames:
                    try:
                        self.frame_queue.put_nowait(frame)
                    except Full:
                        print("Warning: Frame queue full when writing buffer. Dropping frame.")
                        self.frames_dropped_count += 1
                    except Exception as e:
                        print(f"Error queuing buffer frame: {e}")
                
                print(f"Buffer frames added to write queue")
            except Exception as e:
                print(f"Error processing buffer frames: {e}")

    def _handle_recording_stop(self, stop_message):
        """
        Handle stop recording notification from ntfy.
        
        Args:
            stop_message: The notification message that triggered the stop
        """
        if not self.recording_triggered:
            print("Recording not active - ignoring stop command")
            return
            
        print(f"Recording stop triggered by notification: {stop_message.get('title', 'No title')}")
        
        # We'll create a new video file when the next start trigger arrives
        # by just switching back to waiting mode, but keeping everything running
        self.recording_triggered = False
        self.waiting_for_trigger = True
        
        # Flush the current video file by releasing the writer
        if self.save_video and self.video_writer is not None:
            # First stop the writer thread
            if self.writer_thread is not None:
                print("Stopping writer thread...")
                self.stop_writer_event.set()
                
                # Wait for the writer thread to finish with a reasonable timeout
                print("Waiting for writer thread to finish...")
                self.writer_thread.join(timeout=10.0)
                
                if self.writer_thread.is_alive():
                    print("Warning: Writer thread did not terminate within timeout")
                else:
                    print("Writer thread stopped")
                    
                self.writer_thread = None
                
            # Now release the video writer
            if self.video_writer is not None:
                print(f"Releasing video writer for file: {self.output_file}")
                try:
                    self.video_writer.release()
                    print("Video writer released")
                except Exception as e:
                    print(f"Error releasing video writer: {e}")
                    
                self.video_writer = None
                self.auto_output_filename = None
                
        print("Waiting for next trigger notification...")
        
        # Clear the buffer to start fresh
        if self.buffer_trigger_manager and self.buffer_trigger_manager.rolling_buffer:
            self.buffer_trigger_manager.rolling_buffer.clear()
            print("Rolling buffer cleared")
            
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
        qsize = -1 # Indicate queue not applicable if not threaded
        if self.save_video and self.frame_queue is not None:
            qsize = self.frame_queue.qsize()
        
        buffer_info = {}
        if self.use_buffer and self.buffer_trigger_manager:
            buffer_size = self.buffer_trigger_manager.rolling_buffer.get_buffer_size()
            buffer_duration = self.buffer_trigger_manager.rolling_buffer.get_buffer_duration()
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
            "auto_output_filename": self.auto_output_filename,
            "threaded_writer_enabled": self.save_video,
            "frame_queue_size": qsize,
            "buffer_mode": self.use_buffer,
            "capture_cpu_core": self.capture_cpu_core,
            "writer_cpu_core": self.writer_cpu_core,
            "visualizer_cpu_core": self.visualizer_cpu_core,
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

# (Optional: Old standalone function - kept commented out for reference if needed)
# def stream_camera(...): ... 