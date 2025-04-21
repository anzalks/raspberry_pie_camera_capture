"""Class-based implementation for camera streaming and LSL interaction."""

import time
import numpy as np
import cv2 # Import OpenCV
import traceback
import platform # For OS-specific checks

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
    Video is automatically saved to a timestamped file.
    """
    def __init__(self, width=640, height=480, fps=30, pixel_format='RGB888',
                 stream_name='RaspberryPiCamera', source_id='RPiCam_UniqueID',
                 show_preview=False,
                 use_max_settings=False):
        """
        Initializes the streamer configuration and sets up camera and LSL.
        Video is automatically saved to a timestamped file.

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
        self.use_max_settings = use_max_settings # Store the flag
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

        # Initialize camera and LSL stream upon instantiation
        try:
            self._initialize_camera()
            self._setup_lsl()
            # Initialize VideoWriter AFTER camera is initialized
            # Filename is now generated automatically within this method
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
        """Initializes the camera, trying webcam indices [0, 1] first, then falling back to PiCamera on Linux if available."""
        
        webcam_indices_to_try = [0, 1]
        
        # --- Attempt Webcam Initialization First (Priority) ---
        for index in webcam_indices_to_try:
            print(f"Attempting to initialize Webcam index {index} via OpenCV...")
            try:
                cap_attempt = cv2.VideoCapture(index)
                if cap_attempt is not None and cap_attempt.isOpened():
                    print(f"Successfully opened Webcam index {index}. Configuring...")
                    self.cap = cap_attempt
                    
                    # --- Max Settings Heuristic (if requested) ---
                    detected_width = 0
                    detected_height = 0
                    detected_fps = 0.0
                    if self.use_max_settings:
                        print("Attempting to detect maximum settings using heuristic...")
                        # Try setting very high resolution and reading back
                        try:
                            if self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 4096) and \
                               self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 4096):
                                time.sleep(0.1) # Allow driver time to settle? Might not be needed.
                                detected_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                                detected_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                                print(f"  Detected Resolution: {detected_width}x{detected_height}")
                            else:
                                print("  Warning: Failed to set high resolution for detection.")
                        except Exception as e_res:
                            print(f"  Warning: Error during resolution detection: {e_res}")
                        
                        # Use detected resolution (if valid) for FPS detection
                        temp_width = detected_width if detected_width > 0 else self.requested_width
                        temp_height = detected_height if detected_height > 0 else self.requested_height
                        
                        # Try setting very high FPS and reading back
                        try:
                            # Ensure resolution is set before trying FPS
                            if self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, temp_width) and \
                               self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, temp_height) and \
                               self.cap.set(cv2.CAP_PROP_FPS, 120): # Try high FPS
                                time.sleep(0.1)
                                detected_fps = self.cap.get(cv2.CAP_PROP_FPS)
                                print(f"  Detected FPS: {detected_fps}")
                            else:
                                print("  Warning: Failed to set high FPS for detection.")
                        except Exception as e_fps:
                            print(f"  Warning: Error during FPS detection: {e_fps}")
                    # --- End Max Settings Heuristic ---
                        
                    # Decide which settings to actually use
                    target_width = self.requested_width
                    target_height = self.requested_height
                    target_fps = self.requested_fps
                    
                    if self.use_max_settings and detected_width > 0 and detected_height > 0:
                        print("Using detected resolution for configuration.")
                        target_width = detected_width
                        target_height = detected_height
                        # Only use detected FPS if it's valid and higher than requested
                        if detected_fps > 0:
                             print("Using detected FPS for configuration.")
                             target_fps = detected_fps 
                        else:
                             print("Detected FPS invalid or lower, using requested FPS.")
                    else:
                        print("Using requested/default settings for configuration.")
                        
                    # Set the final target properties
                    self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, target_width)
                    self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, target_height)
                    self.cap.set(cv2.CAP_PROP_FPS, target_fps)

                    # Read back final actual properties
                    actual_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                    actual_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    actual_fps_cv2 = self.cap.get(cv2.CAP_PROP_FPS)

                    print(f"Webcam final request: {target_width}x{target_height} @ {target_fps}fps.")
                    print(f"Webcam actual properties: {actual_width}x{actual_height} @ {actual_fps_cv2}fps.")
                    
                    # Update internal state with actual values
                    self.width = actual_width
                    self.height = actual_height
                    self.actual_fps = actual_fps_cv2
                    if self.actual_fps <= 0:
                        print(f"Warning: Webcam reported invalid final FPS ({actual_fps_cv2}). Using requested FPS ({self.requested_fps}) as fallback.")
                        self.actual_fps = self.requested_fps
                    else:
                         print(f"Using actual webcam FPS {self.actual_fps}.")

                    self.num_channels = 3
                    self.lsl_pixel_format = 'BGR888' 
                    self.camera_model = f"OpenCV Webcam {index}" 
                    print(f"Using selected Webcam (index {index}).")
                    self.is_picamera = False
                    return # Webcam succeeded
                else:
                    print(f"Warning: Could not open webcam index {index}.")
                    if cap_attempt is not None:
                         cap_attempt.release()
            except Exception as e:
                print(f"Error during webcam index {index} initialization attempt: {e}")

        # --- Fallback to PiCamera on Linux (if All Webcams Failed) ---
        if self.cap is None and platform.system() == 'Linux' and PICAMERA2_AVAILABLE:
            print(f"Webcam indices {webcam_indices_to_try} failed. Detected Linux and Picamera2 library. Attempting fallback to PiCamera...")
            # -- NOTE: Max settings heuristic NOT implemented for PiCamera --
            # -- Using requested/default width, height, fps for PiCamera --
            try:
                print(f"Configuring for {self.requested_width}x{self.requested_height} @ {self.requested_fps}fps, format {self.pixel_format}...") # Use requested args
                self.picam2 = Picamera2()
                sensor_formats = self.picam2.sensor_formats
                if self.pixel_format not in sensor_formats:
                    print(f"Warning: Format {self.pixel_format} not directly supported by sensor. Available: {sensor_formats}")
                
                config = self.picam2.create_video_configuration(
                    main={"size": (self.requested_width, self.requested_height)}, # Use requested args
                    controls={"FrameRate": self.requested_fps} # Use requested args
                )
                self.picam2.configure(config)
                self.camera_model = self.picam2.camera_properties.get('Model', 'Unknown PiCam')
                self.lsl_pixel_format = self.pixel_format
                # Assume PiCamera achieves requested settings
                self.width = self.requested_width
                self.height = self.requested_height
                self.actual_fps = self.requested_fps 
                self._determine_picam_channels()
                print(f"PiCamera initialized successfully as fallback. Model: {self.camera_model}")
                self.is_picamera = True
                return # PiCamera succeeded

            except Exception as e:
                print(f"ERROR: Fallback to PiCamera also failed: {e}")
        
        # --- Final Check and Error --- 
        if self.cap is None and self.picam2 is None:
            error_message = f"Could not initialize any camera. Failed Webcam indices: {webcam_indices_to_try}."
            if platform.system() == 'Linux' and PICAMERA2_AVAILABLE:
                 error_message += " Fallback attempt to PiCamera also failed."
            elif platform.system() == 'Linux':
                 error_message += " Picamera2 library not found or failed to import for fallback."
            else: 
                 error_message += " Not on Linux or Picamera2 library unavailable for PiCamera fallback."
            raise RuntimeError(error_message)

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
        """Initializes the OpenCV VideoWriter, generating a timestamped filename."""
        # if self.output_video_file: # Removed check - always attempt to save
        
        # Generate filename based on timestamp
        timestamp_str = time.strftime("%Y%m%d_%H%M%S")
        self.auto_output_filename = f"lsl_capture_{timestamp_str}.mp4"
        
        # Choose a codec. 'avc1' (H.264) is often more compatible for .mp4 than 'mp4v'.
        # Alternatives: 'mp4v', 'h264' (might depend on specific OpenCV build/backend)
        fourcc = cv2.VideoWriter_fourcc(*'h264') # Use h264 as requested
        # Use actual width, height, and fps determined during camera init
        frame_size = (self.width, self.height)
        fps = self.actual_fps
        
        # Ensure FPS is valid for VideoWriter
        if fps <= 0:
            print(f"Warning: Invalid FPS ({fps}) for VideoWriter. Defaulting to 30.")
            fps = 30.0
            
        print(f"Initializing video writer: {self.auto_output_filename}, Codec: h264, Size: {frame_size}, FPS: {fps:.2f}")
        print(f"DEBUG: Passing FPS value {float(fps)} to cv2.VideoWriter()")
        try:
            self.video_writer = cv2.VideoWriter(self.auto_output_filename, fourcc, float(fps), frame_size)
            if not self.video_writer.isOpened():
                print(f"Error: Could not open VideoWriter for file '{self.auto_output_filename}'. Check codec, path, and permissions.")
                self.video_writer = None # Ensure it's None if failed
            else:
                print("Video writer initialized successfully.")
        except Exception as e:
            print(f"Error initializing VideoWriter: {e}")
            self.video_writer = None
            
    def _setup_lsl(self):
        """Configures and creates the LSL StreamInfo and StreamOutlet for Frame Numbers."""
        # LSL stream for frame numbers only
        channel_count = 1 # Only sending the frame number
        # Use cf_int32 for frame number (pylsl constant is 4)
        # Use cf_int64 (5) if frame counts might exceed 2 billion
        channel_format_lsl = 4 # cf_int32 
        stream_type = 'FrameCounter' 

        print(f"LSL Stream Info: Name='{self.stream_name}', Type={stream_type}, Channels={channel_count}, Format=cf_int32, Rate={self.actual_fps}")

        # Create the StreamInfo object describing the stream.
        self.info = StreamInfo(name=self.stream_name,
                               type=stream_type, 
                               channel_count=channel_count, # Single channel for frame number
                               nominal_srate=float(self.actual_fps), # Rate frames are generated
                               channel_format=channel_format_lsl, 
                               source_id=self.source_id)

        # Add detailed metadata to the stream description (XML format).
        desc = self.info.desc()
        desc.append_child_value("acquisition_software", "RaspberryPiLSLStream")
        desc.append_child_value("camera_model", self.camera_model) # Keep camera info
        desc.append_child_value("source_type", "PiCamera" if self.is_picamera else "Webcam") # Keep source info
        
        # Add description for the single channel
        chn = desc.append_child("channels").append_child("channel")
        chn.append_child_value("label", "FrameNumber")
        chn.append_child_value("unit", "count")
        chn.append_child_value("type", stream_type)

        # (Removed resolution/pixel format metadata from LSL stream description)
        # desc.append_child("timing").append_child_value("frame_numbering", "Sequential starting from 1") # Implicitly true now

        # Create the StreamOutlet using the configured StreamInfo.
        try:
            self.outlet = StreamOutlet(self.info)
            print(f"LSL stream '{self.stream_name}' created and waiting for consumers.")
        except Exception as e:
            # Handle potential errors during outlet creation (e.g., network issues)
            print(f"Error creating LSL outlet: {e}")
            traceback.print_exc()
            self.info = None # Invalidate info if outlet creation failed
            raise # Re-raise the exception to signal failure
            
    def start(self):
        """Starts the camera capture process based on which camera was initialized."""
        if self._is_running:
            print("Streamer already running.")
            return
            
        if self.is_picamera and self.picam2:
            # Start PiCamera
            try:
                print("Starting Picamera2 capture...")
                self.picam2.start()
                self._is_running = True
                print("Picamera2 started.")
            except Exception as e:
                print(f"Error starting Picamera2: {e}")
                traceback.print_exc()
        elif not self.is_picamera and self.cap:
             # Start Webcam (implicitly via read)
            print("Starting OpenCV webcam capture (implicit via read)...")
            self._is_running = True
        else:
            print("Error: Camera not properly initialized. Cannot start.")

    def stop(self):
        """Stops the camera capture and releases resources."""
        if not self._is_running:
             return
             
        print("Stopping camera...")
        self._is_running = False 
        
        # Release resources based on which camera was used
        if self.is_picamera and self.picam2:
            # Stop and close PiCamera resources
            try:
                if hasattr(self.picam2, 'is_open') and self.picam2.is_open:
                     self.picam2.stop()
                     print("Picamera2 stopped.")
                else:
                     pass 
            except Exception as e:
                print(f"Error stopping Picamera2: {e}")
            finally:
                try:
                    if self.picam2:
                        self.picam2.close()
                        print("Picamera2 closed.")
                        self.picam2 = None
                except Exception as e:
                    print(f"Error closing Picamera2 connection: {e}")
        elif not self.is_picamera and self.cap:
            # Release Webcam resources
            try:
                self.cap.release()
                print("OpenCV webcam released.")
                self.cap = None
            except Exception as e:
                print(f"Error releasing OpenCV webcam: {e}")
        
        # --- Release VideoWriter ---
        if self.video_writer is not None:
            # Use the automatically generated filename in the message
            print(f"Releasing video writer ('{self.auto_output_filename}')...")
            try:
                self.video_writer.release()
                print("Video writer released.")
            except Exception as e:
                print(f"Error releasing video writer: {e}")
            self.video_writer = None
        # ---
            
        # --- Destroy Preview Window ---
        if self.show_preview:
            # Check if attribute exists in case init failed before window creation
            if hasattr(self, 'preview_window_name'): 
                print(f"Closing preview window ('{self.preview_window_name}')...")
                try:
                    cv2.destroyWindow(self.preview_window_name)
                except Exception as e:
                    print(f"Error closing preview window: {e}")
        # ---
        
        # LSL Outlet cleanup: Python's garbage collector handles closing the 
        # underlying LSL C library connection when the StreamOutlet object is destroyed.
        # Explicitly setting to None helps ensure the reference is cleared sooner.
        self.outlet = None 
        self.info = None
        print("LSL stream outlet cleanup initiated (handled by garbage collection).")

    def capture_frame(self):
        """
        Captures a single frame from the initialized camera, saves it locally,
        optionally displays preview, and pushes frame number to LSL.

        Returns:
            tuple: (frame_data, timestamp) where frame_data is the captured 
                   numpy array (or None if capture failed/not running), and 
                   timestamp is the LSL timestamp (or None).
        """
        if not self._is_running:
             return None, None # Check running state first
             
        # Outlet check moved after running check
        if self.outlet is None:
             print("Error: LSL Outlet is not available. Cannot push sample.")
             return None, None

        timestamp = local_clock()
        frame_data = None
        
        try:
            # Capture frame based on the automatically detected camera
            if self.is_picamera and self.picam2:
                 # Capture frame as a numpy array using Picamera2
                 frame_data = self.picam2.capture_array()
            elif not self.is_picamera and self.cap:
                # Capture frame using OpenCV
                ret, frame_data = self.cap.read() 
                if not ret:
                    print("Warning: Failed to grab frame from webcam. Skipping.")
                    return None, None
            else:
                print("Error: Camera not available for capture (state inconsistency).")
                return None, None

            # --- Write frame to local video file --- 
            if self.video_writer is not None:
                try:
                    self.video_writer.write(frame_data) 
                except Exception as e:
                    print(f"Error writing frame to video file: {e}")
            # ---
            
            # --- Show Preview Frame (if enabled) ---
            if self.show_preview and hasattr(self, 'preview_window_name'):
                 try:
                     cv2.imshow(self.preview_window_name, frame_data)
                     key = cv2.waitKey(1) 
                 except Exception as e:
                     print(f"Error showing preview frame: {e}")
            # ---
            
            # --- Push Frame Number to LSL ---
            self.frame_count += 1 
            try:
                self.outlet.push_sample([self.frame_count], timestamp) 
            except Exception as e:
                print(f"Error pushing frame number to LSL: {e}")
                return None, None # Indicate failure if LSL push fails
            # ---
            
            # Return frame_data (for potential external use) and timestamp
            return frame_data, timestamp

        except Exception as e:
            print(f"Error during frame capture/processing: {e}")
            traceback.print_exc()
            return None, None # Indicate failure
            
    def get_info(self):
        """Returns a dictionary containing the current stream configuration and status."""
        return {
            "width": self.width,
            "height": self.height,
            "actual_fps": self.actual_fps,
            "lsl_pixel_format": self.lsl_pixel_format,
            "num_channels": self.num_channels, # Note: May not be relevant for frame counter stream
            "stream_name": self.stream_name,
            "source_id": self.source_id,
            "camera_model": self.camera_model,
            # Update source type based on detected camera
            "source_type": "PiCamera" if self.is_picamera else "Webcam", 
            "is_running": self._is_running,
            "auto_output_filename": self.auto_output_filename # Add filename info
        }

    def get_frame_count(self):
        """Returns the number of frames successfully pushed to LSL."""
        return self.frame_count

    # Ensure cleanup if the object is deleted or goes out of scope
    def __del__(self):
        """Destructor to ensure stop() is called for cleanup."""
        # print(f"LSLCameraStreamer object ({self.source_id}) being deleted. Ensuring stop().")
        self.stop()

# (Optional: Old standalone function - kept commented out for reference if needed)
# def stream_camera(...): ... 