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
    """
    def __init__(self, width=640, height=480, fps=30, pixel_format='RGB888',
                 stream_name='RaspberryPiCamera', source_id='RPiCam_UniqueID',
                 use_webcam=False, webcam_index=0):
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
            use_webcam (bool): If True, use OpenCV to access a USB webcam.
                               If False, attempt to use Picamera2.
            webcam_index (int): Index of the webcam to use if use_webcam is True.
        """
        
        # Store configuration parameters
        self.width = width
        self.height = height
        self.requested_fps = float(fps)
        self.pixel_format = pixel_format # PiCam specific format request
        self.stream_name = stream_name
        self.source_id = source_id
        self.use_webcam = use_webcam
        self.webcam_index = webcam_index

        # Internal state variables
        self.cap = None # Holds the OpenCV VideoCapture object if using webcam
        self.picam2 = None # Holds the Picamera2 object if using Pi camera
        self.lsl_pixel_format = pixel_format # Actual format used for LSL metadata (may differ from request)
        self.num_channels = 3 # Estimated number of color channels (default to 3)
        self.actual_fps = self.requested_fps # Actual frame rate achieved (may differ from request)
        self.camera_model = "Unknown" # Model identifier for LSL metadata
        self.outlet = None # LSL StreamOutlet object
        self.info = None # LSL StreamInfo object
        self.frame_count = 0 # Counter for frames successfully pushed to LSL
        self._is_running = False # Flag indicating if the capture loop should run

        # Initialize camera and LSL stream upon instantiation
        try:
            self._initialize_camera()
            self._setup_lsl()
        except Exception as e:
            # Ensure cleanup if initialization fails
            print(f"Streamer initialization failed: {e}")
            self.stop() # Attempt to release any partially acquired resources
            raise # Re-raise the exception

    def _initialize_camera(self):
        """Initializes either the webcam using OpenCV or the PiCamera using Picamera2."""
        if self.use_webcam:
            # --- Webcam Initialization (OpenCV) ---
            print(f"Initializing USB Webcam (index {self.webcam_index}) via OpenCV...")
            # Create OpenCV capture object
            self.cap = cv2.VideoCapture(self.webcam_index)
            if not self.cap.isOpened():
                # Error if the webcam cannot be opened
                raise RuntimeError(f"Could not open webcam with index {self.webcam_index}.")

            # Request desired properties (camera may override these)
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            self.cap.set(cv2.CAP_PROP_FPS, self.requested_fps)

            # Read back the actual properties set by the camera driver
            actual_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            actual_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            actual_fps_cv2 = self.cap.get(cv2.CAP_PROP_FPS)

            print(f"Webcam requested {self.width}x{self.height} @ {self.requested_fps}fps.")
            print(f"Webcam actual properties: {actual_width}x{actual_height} @ {actual_fps_cv2}fps.")
            
            # Update internal state with actual values reported by the camera
            self.width = actual_width
            self.height = actual_height
            self.actual_fps = actual_fps_cv2
            # Handle cases where camera reports invalid FPS (e.g., 0)
            if self.actual_fps <= 0:
                print(f"Warning: Webcam reported FPS {actual_fps_cv2}. Using requested FPS {self.requested_fps}.")
                self.actual_fps = self.requested_fps
            else:
                 print(f"Using actual webcam FPS {self.actual_fps}.")

            # OpenCV typically provides BGR format frames
            self.num_channels = 3
            self.lsl_pixel_format = 'BGR888' 
            self.camera_model = f"OpenCV Webcam {self.webcam_index}"
            print("Webcam initialized.")

        elif PICAMERA2_AVAILABLE:
            # --- PiCamera Initialization (Picamera2) ---
            print(f"Initializing Raspberry Pi Camera via Picamera2...")
            print(f"Configuring for {self.width}x{self.height} @ {self.requested_fps}fps, format {self.pixel_format}...")

            # Create Picamera2 instance
            self.picam2 = Picamera2()
            # Check if requested format is directly supported by sensor (informational)
            sensor_formats = self.picam2.sensor_formats
            if self.pixel_format not in sensor_formats:
                print(f"Warning: Format {self.pixel_format} not directly supported by sensor. Available: {sensor_formats}")
            
            # Create a video configuration with desired size, format, and frame rate control
            config = self.picam2.create_video_configuration(
                main={"size": (self.width, self.height), "format": self.pixel_format},
                controls={"FrameRate": self.requested_fps}
            )
            # Apply the configuration
            self.picam2.configure(config)
            # Get camera model from properties for LSL metadata
            self.camera_model = self.picam2.camera_properties.get('Model', 'Unknown PiCam')
            # Use the requested pixel format for LSL metadata (assuming picamera2 handles conversion if needed)
            self.lsl_pixel_format = self.pixel_format
            # Assume Picamera2 respects the requested frame rate
            self.actual_fps = self.requested_fps 

            # Determine number of channels based on the pixel format for LSL setup
            self._determine_picam_channels()
            print(f"Picamera2 configured. Model: {self.camera_model}")

        else:
            # --- No Camera Available --- 
            # This block executes if webcam wasn't chosen AND Picamera2 import failed.
            if not self.use_webcam:
                # User specifically wanted PiCamera, but it's not available.
                # Check if the reason is an incompatible OS.
                if platform.system() != 'Linux':
                    # Provide a specific warning for non-Linux systems.
                    print(f"\n--- OS PLATFORM WARNING ---")
                    print(f"Attempted to use PiCamera on '{platform.system()}'.")
                    print(f"The 'picamera2' library and its dependencies generally require a Linux environment (like Raspberry Pi OS).")
                    print(f"Cannot initialize PiCamera.")
                    print(f"---------------------------")
                    raise RuntimeError(f"PiCamera interface selected, but it requires Linux (running on {platform.system()}). Choose a webcam (-w/--use-webcam) or run on a compatible system.")
                else:
                    # It's Linux, but picamera2 still failed to import.
                    # This suggests an installation issue (missing libcamera, etc.).
                    print(f"\n--- IMPORT WARNING ---")
                    print(f"Attempted to use PiCamera on Linux, but the 'picamera2' library failed to import.")
                    print(f"Ensure 'picamera2' and its system dependencies (e.g., libcamera-apps) are installed correctly.")
                    print(f"-----------------------")
                    raise RuntimeError("PiCamera selected, but 'picamera2' library failed to import. Check installation and system dependencies.")
            else:
                # Fallback error if webcam was intended but failed (though VideoCapture should raise earlier)
                # or if somehow this state is reached unexpectedly.
                raise RuntimeError("No suitable camera interface found (Webcam failed or was not selected, and PiCamera is not available/supported on this platform).")

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

    def _setup_lsl(self):
        """Configures and creates the LSL StreamInfo and StreamOutlet."""
        # LSL requires the data to be flattened into a 1D array.
        # The channel count reflects the total number of elements in this array.
        channel_count = self.width * self.height * self.num_channels
        print(f"LSL Stream Info: Channels={channel_count}, Format={self.lsl_pixel_format}, Rate={self.actual_fps}")

        # Create the StreamInfo object describing the stream.
        # channel_format=2 corresponds to pylsl.cf_uint8.
        self.info = StreamInfo(name=self.stream_name,
                               type='Video', # Standard type for video streams
                               channel_count=channel_count, # Total elements in flattened frame
                               nominal_srate=float(self.actual_fps), # Expected frame rate
                               channel_format=2, # Data type: uint8
                               source_id=self.source_id)

        # Add detailed metadata to the stream description (XML format).
        # This metadata can be read by LSL clients (like view_stream.py)
        # to correctly interpret the stream (e.g., reshape frames).
        desc = self.info.desc()
        desc.append_child_value("acquisition_software", "RaspberryPiLSLStream")
        desc.append_child_value("camera_model", self.camera_model)
        desc.append_child_value("source_type", "Webcam" if self.use_webcam else "PiCamera")
        
        # Add a dedicated <resolution> child element for clarity
        resolution_info = desc.append_child("resolution")
        resolution_info.append_child_value("width", str(self.width))
        resolution_info.append_child_value("height", str(self.height))
        resolution_info.append_child_value("num_channels_estimated", str(self.num_channels))
        resolution_info.append_child_value("lsl_channel_count", str(channel_count))
        resolution_info.append_child_value("pixel_format_lsl", self.lsl_pixel_format)

        # Create the StreamOutlet using the configured StreamInfo.
        # This makes the stream available on the network.
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
        """Starts the camera capture process.
        
        For OpenCV VideoCapture, reading the first frame implicitly starts capture.
        For Picamera2, explicitly calls its start() method.
        Sets the _is_running flag to True.
        """
        if self._is_running:
            # Prevent starting if already running
            print("Streamer already running.")
            return
            
        if self.use_webcam and self.cap:
            # OpenCV VideoCapture doesn't require an explicit start command
            # after initialization. Capture begins with the first .read() call.
            print("Starting OpenCV webcam capture (implicit via read)...")
            self._is_running = True
        elif self.picam2:
            # Picamera2 requires an explicit start call.
            try:
                print("Starting Picamera2 capture...")
                self.picam2.start()
                self._is_running = True
                print("Picamera2 started.")
            except Exception as e:
                # Handle errors during Picamera2 start
                print(f"Error starting Picamera2: {e}")
                traceback.print_exc()
                # Do not set _is_running to True if start failed
        else:
            # Should not happen if initialization succeeded, but check anyway.
            print("Error: Camera not properly initialized. Cannot start.")

    def stop(self):
        """Stops the camera capture and releases resources.
        
        Sets the _is_running flag to False.
        Releases the OpenCV capture object or stops/closes the Picamera2 object.
        The LSL outlet is implicitly closed when the object is garbage collected,
        but setting it to None helps signal intent.
        """
        if not self._is_running:
             # Avoid stopping if already stopped or never started
             return
             
        print("Stopping camera...")
        self._is_running = False # Signal loops to stop attempting capture
        
        # Release Webcam resources
        if self.use_webcam and self.cap:
            try:
                self.cap.release()
                print("OpenCV webcam released.")
                self.cap = None # Clear the object reference
            except Exception as e:
                print(f"Error releasing OpenCV webcam: {e}")
                
        # Stop and close PiCamera resources
        elif self.picam2:
            try:
                # Check if picam2 object exists and has the 'started' attribute 
                # (or similar check depending on picamera2 version specifics if needed)
                # and if it was actually started.
                if hasattr(self.picam2, 'is_open') and self.picam2.is_open: # Check based on typical camera objects
                     # Newer picamera2 might use different state checks, adjust if necessary.
                    self.picam2.stop()
                    print("Picamera2 stopped.")
                else:
                     # print("Picamera2 object exists but was not running/started.")
                     pass 
            except Exception as e:
                print(f"Error stopping Picamera2: {e}")
            finally:
                # Attempt to close the camera connection even if stop failed or wasn't needed.
                try:
                    if self.picam2: # Check if picam2 object still exists
                        self.picam2.close()
                        print("Picamera2 closed.")
                        self.picam2 = None # Clear the object reference
                except Exception as e:
                    print(f"Error closing Picamera2 connection: {e}")
        
        # LSL Outlet cleanup: Python's garbage collector handles closing the 
        # underlying LSL C library connection when the StreamOutlet object is destroyed.
        # Explicitly setting to None helps ensure the reference is cleared sooner.
        self.outlet = None 
        self.info = None
        print("LSL stream outlet cleanup initiated (handled by garbage collection).")

    def capture_frame(self):
        """
        Captures a single frame from the initialized camera, flattens it,
        pushes it to the LSL outlet with a timestamp.

        Returns:
            tuple: (frame_data, timestamp) where frame_data is the captured 
                   numpy array (or None if capture failed/not running), and 
                   timestamp is the LSL timestamp (or None).
        """
        # Check if the stream is supposed to be running and the outlet is valid
        if not self._is_running or self.outlet is None:
            return None, None

        # Get LSL timestamp as close to the capture time as possible
        timestamp = local_clock()
        frame_data = None
        
        try:
            # Capture frame based on the camera type
            if self.use_webcam and self.cap:
                ret, frame_data = self.cap.read() # Reads a frame in BGR format
                if not ret:
                    # Handle cases where the webcam fails to provide a frame
                    print("Warning: Failed to grab frame from webcam. Skipping.")
                    return None, None
            elif self.picam2:
                # Capture frame as a numpy array using Picamera2
                frame_data = self.picam2.capture_array()
            else:
                # This case should ideally not be reached if _is_running is True
                print("Error: Camera not available for capture.")
                return None, None

            # Flatten the numpy array (e.g., 3D HxWxC to 1D)
            # LSL push_sample expects a list or 1D numpy array.
            flat_frame_data = frame_data.flatten()
            
            # Push the flattened data and timestamp to the LSL outlet
            self.outlet.push_sample(flat_frame_data, timestamp)
            self.frame_count += 1 # Increment frame counter
            
            # Return the original (non-flattened) frame data and timestamp
            return frame_data, timestamp

        except Exception as e:
            # Catch potential errors during capture (e.g., camera disconnect) or LSL push
            print(f"Error during frame capture or LSL push: {e}")
            traceback.print_exc()
            # Consider adding logic to stop the stream after repeated errors.
            # self.stop()
            return None, None # Indicate failure
            
    def get_info(self):
        """Returns a dictionary containing the current stream configuration and status."""
        return {
            "width": self.width,
            "height": self.height,
            "actual_fps": self.actual_fps,
            "lsl_pixel_format": self.lsl_pixel_format,
            "num_channels": self.num_channels,
            "stream_name": self.stream_name,
            "source_id": self.source_id,
            "camera_model": self.camera_model,
            "source_type": "Webcam" if self.use_webcam else "PiCamera",
            "is_running": self._is_running,
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