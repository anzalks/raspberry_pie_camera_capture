"""Class-based implementation for camera streaming and LSL interaction."""

import time
import numpy as np
import cv2 # Import OpenCV
import traceback
import platform # For OS-specific checks
import threading # Added for writer thread
from queue import Queue, Empty, Full # Added for frame buffer queue

# Attempt to import Picamera2 and set a flag indicating its availability.
# This allows the code to run on non-Pi systems (using a webcam)
# without crashing on import if picamera2 is not installed or supported.
try:
    from picamera2 import Picamera2
    PICAMERA2_AVAILABLE = True
except ImportError:
    PICAMERA2_AVAILABLE = False
    # Inform the user if the PiCamera library is missing
    print("Warning: picamera2 library not found. Raspberry Pi camera functionality disabled.")

# Import pylsl for LabStreamingLayer communication
from pylsl import StreamInfo, StreamOutlet, local_clock

class LSLCameraStreamer:
    """
    Handles the initialization of either a Raspberry Pi camera (via picamera2)
    or a standard USB webcam (via OpenCV), sets up an LSL stream, captures
    frames continuously, and pushes them with timestamps to the LSL outlet.
    Video is automatically saved to a timestamped file using a separate thread.
    """
    def __init__(self, width=640, height=480, fps=30, pixel_format='RGB888',
                 stream_name='RaspberryPiCamera', source_id='RPiCam_UniqueID',
                 show_preview=False,
                 use_max_settings=False,
                 queue_size_seconds=2,
                 threaded_writer=False):
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
            queue_size_seconds (int): Approximate buffer size in seconds for the video writer queue (used only if threaded_writer is True).
            threaded_writer (bool): If True, use a separate thread for video writing.
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
        self.threaded_writer = threaded_writer
        self.auto_output_filename = None
        self.video_writer = None

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
            self._initialize_video_writer() # Handles conditional frame queue init
            
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
        """Initializes the camera by trying PiCamera first (if available on Linux),
           then falling back to standard webcams via OpenCV."""
        # webcam_indices_to_try = [0, 1] # Moved lower
        initialized = False

        # --- Try PiCamera First on Linux if Available ---
        if platform.system() == 'Linux' and PICAMERA2_AVAILABLE:
            print("Detected Linux with picamera2 library available. Trying PiCamera first...")
            if self._initialize_picamera():
                initialized = True
            else:
                print("PiCamera initialization failed. Falling back to webcams...")

        # --- Fallback to Webcam Initialization (if PiCamera failed or wasn't tried) ---
        if not initialized:
            print("Attempting Webcam initialization via OpenCV...")
            webcam_indices_to_try = [0, 1]
            for index in webcam_indices_to_try:
                if self._initialize_webcam(index):
                    initialized = True
                    print(f"Using selected Webcam (index {index}).")
                    break # Stop trying if one webcam worked
            
            if not initialized:
                 print(f"Webcam indices {webcam_indices_to_try} also failed or unavailable.")

        # --- Final Check ---
        if not initialized:
            error_message = "Could not initialize any camera. "
            if platform.system() == 'Linux' and PICAMERA2_AVAILABLE:
                 error_message += "Both PiCamera and Webcam attempts failed."
            elif platform.system() == 'Linux':
                 error_message += "Picamera2 library unavailable and Webcam attempts failed."
            else:
                 error_message += "Webcam attempts failed (Not on Linux or Picamera2 unavailable)."
            raise RuntimeError(error_message)

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
        """Attempts to initialize and configure the PiCamera."""
        if not PICAMERA2_AVAILABLE:
            return False # Should not happen if called correctly, but safeguard
            
        # NOTE: Max settings heuristic NOT implemented for PiCamera
        # Using requested/default width, height, fps for PiCamera
        try:
            print(f"Configuring PiCamera for {self.requested_width}x{self.requested_height} @ {self.requested_fps:.2f}fps, format {self.pixel_format}...")
            self.picam2 = Picamera2()
            # Check format compatibility (optional, but good practice)
            # sensor_formats = self.picam2.sensor_formats
            # if self.pixel_format not in sensor_formats:
            #     print(f"Warning: Format {self.pixel_format} not directly supported by sensor. Available: {sensor_formats}. Trying anyway...")

            config = self.picam2.create_video_configuration(
                main={"size": (self.requested_width, self.requested_height)},
                controls={"FrameRate": self.requested_fps}
            )
            self.picam2.configure(config)

            # Read back actual configuration details if possible (might need adjustment based on picamera2 API version)
            # For now, assume requested settings are achieved for PiCamera
            self.width = self.requested_width
            self.height = self.requested_height
            self.actual_fps = self.requested_fps
            self.camera_model = self.picam2.camera_properties.get('Model', 'Unknown PiCam')
            self.lsl_pixel_format = self.pixel_format
            self._determine_picam_channels() # Sets self.num_channels

            print(f"PiCamera initialized successfully. Model: {self.camera_model}")
            self.is_picamera = True
            return True

        except Exception as e:
            print(f"ERROR: Fallback to PiCamera failed during configuration: {e}")
            traceback.print_exc()
            if self.picam2:
                 try: self.picam2.close() # Attempt cleanup
                 except: pass
            self.picam2 = None
            self.is_picamera = False
            return False

    def _determine_picam_channels(self):
        """Estimates the number of color channels based on the PiCamera pixel format.
        
        This is used for calculating the total number of channels in the flattened
        LSL stream data (width * height * num_channels).
        Handles common RGB, RGBA, YUV, and basic Bayer formats.
        Defaults to 3 for unknown formats.
        """
        fmt = self.pixel_format
        if fmt == 'RGB888': self.num_channels = 3
        elif fmt in ['XBGR8888', 'XRGB8888']: self.num_channels = 4 # Alpha channel
        elif fmt == 'YUV420': 
            # YUV420 is planar and more complex. For simplicity in reshaping,
            # we might treat it as 3 channels, but this might not be visually correct
            # without proper conversion on the receiving end.
            print("Warning: YUV420 streaming needs careful handling. Treating as 3 channels for LSL channel count.")
            self.num_channels = 3 
        elif fmt.startswith('S') and fmt.endswith(('10', '12')): # Raw Bayer formats (e.g., SBGGR10)
             # Raw Bayer data is single channel before debayering.
             print(f"Warning: Raw Bayer format ({fmt}). Streaming raw data. Channel count set to 1.")
             self.num_channels = 1
        else:
            # Fallback for other/unknown formats.
            print(f"Warning: Unsupported PiCamera format {fmt} for channel count estimation. Assuming 3.")
            self.num_channels = 3

    def _initialize_video_writer(self):
        """Initializes the OpenCV VideoWriter and, if threaded, the frame queue."""
        
        # Generate filename based on timestamp
        timestamp_str = time.strftime("%Y%m%d_%H%M%S")
        self.auto_output_filename = f"lsl_capture_{timestamp_str}.mp4"
        
        # Choose codec - Revert to h264
        fourcc = cv2.VideoWriter_fourcc(*'h264')
        frame_size = (self.width, self.height)
        
        # Ensure FPS is valid for VideoWriter and Queue sizing
        fps = self.actual_fps
        if fps <= 0:
            print(f"Warning: Invalid actual FPS ({fps}) detected. Using requested FPS ({self.requested_fps}) for writer.")
            fps = self.requested_fps
            if fps <= 0:
                 print(f"Warning: Requested FPS ({fps}) also invalid. Defaulting to 30 FPS for writer.")
                 fps = 30.0

        # --- Initialize Frame Queue (Conditional again) ---
        if self.threaded_writer:
            queue_max_size = max(10, int(fps * self.queue_size_seconds))
            print(f"Initializing frame queue for threaded writer (max size: {queue_max_size})")
            self.frame_queue = Queue(maxsize=queue_max_size)
        else:
            print("Threaded writer disabled. Frames will be written synchronously.")
            self.frame_queue = None # Ensure it's None if not threaded
        # ---

        print(f"Initializing video writer: {self.auto_output_filename}, Codec: h264 (in MP4), Size: {frame_size}, FPS: {fps:.2f}")
        try:
            self.video_writer = cv2.VideoWriter(self.auto_output_filename, fourcc, float(fps), frame_size)
            if not self.video_writer.isOpened():
                print(f"Error: Could not open VideoWriter for file '{self.auto_output_filename}'. Check codec support for MP4 container.") 
                self.video_writer = None
            else:
                print("Video writer initialized successfully.")
        except Exception as e:
            print(f"Error initializing VideoWriter: {e}")
            traceback.print_exc()
            self.video_writer = None

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
        desc.append_child_value("acquisition_software", "RaspberryPiLSLStream")
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
        print(f"Writer thread stopping. Total frames written: {frame_write_count}")

    def start(self):
        """Starts the camera capture process and optionally the writer thread."""
        if self._is_running:
            print("Streamer already running.")
            return
            
        # --- Start Writer Thread (Conditional again) ---
        if self.threaded_writer:
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
             self._is_running = True
        else:
            print("Error: Camera hardware could not be started. Stopping dependent threads.")
            # Stop writer thread if it was started
            if self.threaded_writer and self.writer_thread is not None:
                self.stop_writer_event.set()
                self.writer_thread.join(timeout=1.0)
                self.writer_thread = None
            raise RuntimeError("Failed to start camera hardware.")


    def stop(self):
        """Stops the camera capture, optionally the writer thread, and releases resources."""
        if not self._is_running and (not self.threaded_writer or self.writer_thread is None):
             return 
             
        print("Stopping stream and cleaning up resources...")
        
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
        if self.threaded_writer and self.writer_thread is not None:
            print("Signaling writer thread to stop and waiting for queue to flush...")
            self.stop_writer_event.set()
            try:
                 self.writer_thread.join(timeout=max(5.0, self.queue_size_seconds * 1.5))
                 if self.writer_thread.is_alive():
                       print("Warning: Writer thread did not finish within timeout.")
                 else:
                       print("Writer thread finished.")
            except Exception as e:
                 print(f"Error waiting for writer thread: {e}")
            self.writer_thread = None
        elif self.threaded_writer and self.writer_thread is None:
             print("Warning: Threaded writer was enabled but thread object is None during stop.")

        # --- Release VideoWriter (AFTER writer thread finishes) ---
        if self.video_writer is not None:
            print(f"Releasing video writer ('{self.auto_output_filename}')...")
            try:
                self.video_writer.release()
                print("Video writer released.")
            except Exception as e:
                print(f"Error releasing video writer: {e}")
            self.video_writer = None
            
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
        """Captures a single frame, puts it in the queue (if threaded) or writes directly (if not threaded), displays preview, and pushes LSL."""
        if not self._is_running:
             return None, None
             
        timestamp = local_clock()
        frame_data = None
        
        try:
            # --- Capture frame ---
            if self.is_picamera and self.picam2:
                 frame_data = self.picam2.capture_array()
            elif not self.is_picamera and self.cap:
                ret, frame_data = self.cap.read()
                if not ret or frame_data is None:
                    print("Warning: Failed to grab frame from webcam. Skipping.")
                    return None, None
            else:
                print("Error: Camera not available for capture (state inconsistency).")
                self._is_running = False
                return None, None

            # --- Write Frame (Conditional: Queue or Direct) ---
            if self.video_writer is not None:
                 if self.threaded_writer:
                     if self.frame_queue is not None:
                          try:
                              self.frame_queue.put_nowait(frame_data)
                          except Full:
                              print("Warning: Frame queue full (threaded writer). Dropping frame.")
                          except Exception as e:
                               print(f"Error putting frame into queue: {e}")
                     else:
                          print("Error: Threaded writer enabled but queue is None.")
                 else:
                     # --- Write frame directly (Non-Threaded) ---
                     try:
                         self.video_writer.write(frame_data)
                     except Exception as e:
                         print(f"Error writing frame directly: {e}")

            # --- Push Frame Number to LSL (Always Direct Now) ---
            if self.outlet is not None:
                 try:
                     self.outlet.push_sample([self.frame_count], timestamp)
                 except Exception as e:
                     print(f"Error pushing frame number to LSL directly: {e}")
            else:
                  print("Warning: LSL Outlet is None. Cannot push sample.")
            
            # --- Show Preview Frame ---
            if self.show_preview and hasattr(self, 'preview_window_name'):
                 try:
                     if cv2.getWindowProperty(self.preview_window_name, cv2.WND_PROP_VISIBLE) >= 1:
                          cv2.imshow(self.preview_window_name, frame_data)
                          key = cv2.waitKey(1)
                 except Exception as e:
                      pass
            
            # Increment frame count *before* queueing/pushing
            self.frame_count += 1
            
            return frame_data, timestamp

        except Exception as e:
            # Catch errors specific to camera capture or preview
            print(f"Error during frame capture/preview: {e}")
            traceback.print_exc()
            # Attempt to gracefully stop if capture fails critically?
            # self.stop() # Maybe too aggressive?
            return None, None # Indicate failure for this frame


    def get_info(self):
        """Returns a dictionary containing the current stream configuration and status."""
        qsize = -1 # Indicate queue not applicable if not threaded
        if self.threaded_writer and self.frame_queue is not None:
            qsize = self.frame_queue.qsize()
        
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
            "threaded_writer_enabled": self.threaded_writer,
            "frame_queue_size": qsize
        }

    def get_frame_count(self):
        """Returns the number of frames successfully pushed to LSL."""
        return self.frame_count

    # Ensure cleanup if the object is deleted or goes out of scope
    def __del__(self):
        """Destructor to ensure stop() is called for cleanup."""
        # print(f"LSLCameraStreamer object ({self.source_id}) being deleted. Ensuring stop().")
        self.stop() # Call stop on deletion

# (Optional: Old standalone function - kept commented out for reference if needed)
# def stream_camera(...): ... 