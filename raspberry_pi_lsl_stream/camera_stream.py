"""Class-based implementation for camera streaming and LSL interaction."""

import time
import numpy as np
import cv2 # Import OpenCV
import traceback

try:
    from picamera2 import Picamera2
    PICAMERA2_AVAILABLE = True
except ImportError:
    PICAMERA2_AVAILABLE = False
    print("Warning: picamera2 library not found. Raspberry Pi camera functionality disabled.")

from pylsl import StreamInfo, StreamOutlet, local_clock

class LSLCameraStreamer:
    """
    Manages camera initialization (PiCamera or Webcam), LSL stream setup,
    frame capture, and LSL pushing.
    """
    def __init__(self, width=640, height=480, fps=30, pixel_format='RGB888',
                 stream_name='RaspberryPiCamera', source_id='RPiCam_UniqueID',
                 use_webcam=False, webcam_index=0):
        
        self.width = width
        self.height = height
        self.requested_fps = float(fps)
        self.pixel_format = pixel_format # PiCam specific
        self.stream_name = stream_name
        self.source_id = source_id
        self.use_webcam = use_webcam
        self.webcam_index = webcam_index

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

        self._initialize_camera()
        self._setup_lsl()

    def _initialize_camera(self):
        """Initializes either the webcam or PiCamera."""
        if self.use_webcam:
            print(f"Initializing USB Webcam (index {self.webcam_index}) via OpenCV...")
            self.cap = cv2.VideoCapture(self.webcam_index)
            if not self.cap.isOpened():
                raise RuntimeError(f"Could not open webcam with index {self.webcam_index}.")

            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            self.cap.set(cv2.CAP_PROP_FPS, self.requested_fps)

            actual_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            actual_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            actual_fps_cv2 = self.cap.get(cv2.CAP_PROP_FPS)

            print(f"Webcam requested {self.width}x{self.height} @ {self.requested_fps}fps.")
            print(f"Webcam actual properties: {actual_width}x{actual_height} @ {actual_fps_cv2}fps.")
            
            # Use actual properties reported by the camera
            self.width = actual_width
            self.height = actual_height
            self.actual_fps = actual_fps_cv2
            if self.actual_fps <= 0:
                print(f"Warning: Webcam reported FPS {actual_fps_cv2}. Using requested FPS {self.requested_fps}.")
                self.actual_fps = self.requested_fps
            else:
                 print(f"Using actual webcam FPS {self.actual_fps}.")

            self.num_channels = 3
            self.lsl_pixel_format = 'BGR888' 
            self.camera_model = f"OpenCV Webcam {self.webcam_index}"
            print("Webcam initialized.")

        elif PICAMERA2_AVAILABLE:
            print(f"Initializing Raspberry Pi Camera via Picamera2...")
            print(f"Configuring for {self.width}x{self.height} @ {self.requested_fps}fps, format {self.pixel_format}...")

            self.picam2 = Picamera2()
            sensor_formats = self.picam2.sensor_formats
            if self.pixel_format not in sensor_formats:
                print(f"Warning: Format {self.pixel_format} not directly supported by sensor. Available: {sensor_formats}")
            
            config = self.picam2.create_video_configuration(
                main={"size": (self.width, self.height), "format": self.pixel_format},
                controls={"FrameRate": self.requested_fps}
            )
            self.picam2.configure(config)
            self.camera_model = self.picam2.camera_properties.get('Model', 'Unknown PiCam')
            self.lsl_pixel_format = self.pixel_format
            self.actual_fps = self.requested_fps # PiCam usually respects the requested rate

            self._determine_picam_channels()
            print(f"Picamera2 configured. Model: {self.camera_model}")

        else:
             raise RuntimeError("No suitable camera interface found (Picamera2 not installed and webcam not selected).")

    def _determine_picam_channels(self):
        """Sets num_channels based on PiCamera pixel format."""
        fmt = self.pixel_format
        if fmt == 'RGB888': self.num_channels = 3
        elif fmt in ['XBGR8888', 'XRGB8888']: self.num_channels = 4
        elif fmt == 'YUV420': 
            print("Warning: YUV420 streaming needs careful handling. Treating as 3 channels.")
            self.num_channels = 3
        elif fmt.startswith('S') and fmt.endswith(('10', '12')): # Raw Bayer
             print(f"Warning: Raw Bayer format ({fmt}). Streaming raw data. Channel count set to 1.")
             self.num_channels = 1
        else:
            print(f"Warning: Unsupported PiCamera format {fmt} for channel count. Assuming 3.")
            self.num_channels = 3

    def _setup_lsl(self):
        """Sets up the LSL StreamInfo and Outlet."""
        channel_count = self.width * self.height * self.num_channels
        print(f"LSL Stream Info: Channels={channel_count}, Format={self.lsl_pixel_format}, Rate={self.actual_fps}")

        self.info = StreamInfo(name=self.stream_name,
                               type='Video',
                               channel_count=channel_count,
                               nominal_srate=float(self.actual_fps),
                               channel_format=2, # Use integer 2 for uint8
                               source_id=self.source_id)

        desc = self.info.desc()
        desc.append_child_value("acquisition_software", "RaspberryPiLSLStream")
        desc.append_child_value("camera_model", self.camera_model)
        desc.append_child_value("source_type", "Webcam" if self.use_webcam else "PiCamera")
        resolution_info = desc.append_child("resolution")
        resolution_info.append_child_value("width", str(self.width))
        resolution_info.append_child_value("height", str(self.height))
        resolution_info.append_child_value("num_channels_estimated", str(self.num_channels))
        resolution_info.append_child_value("lsl_channel_count", str(channel_count))
        resolution_info.append_child_value("pixel_format_lsl", self.lsl_pixel_format)

        try:
            self.outlet = StreamOutlet(self.info)
            print(f"LSL stream '{self.stream_name}' created and waiting for consumers.")
        except Exception as e:
            print(f"Error creating LSL outlet: {e}")
            traceback.print_exc()
            self.info = None # Invalidate info if outlet fails
            raise # Re-raise after printing
            
    def start(self):
        """Starts the camera capture process."""
        if self._is_running:
            print("Streamer already running.")
            return
            
        if self.use_webcam and self.cap:
            print("Starting OpenCV webcam capture (implicit via read)...")
            # No explicit start needed for VideoCapture
            self._is_running = True
        elif self.picam2:
            try:
                print("Starting Picamera2 capture...")
                self.picam2.start()
                self._is_running = True
                print("Picamera2 started.")
            except Exception as e:
                print(f"Error starting Picamera2: {e}")
                traceback.print_exc()
        else:
            print("Error: Camera not properly initialized.")

    def stop(self):
        """Stops the camera and releases resources."""
        if not self._is_running:
             # print("Streamer not running or already stopped.")
             return # Already stopped or never started
             
        print("Stopping camera...")
        self._is_running = False # Indicate stopping
        # Allow some time for any ongoing capture frame to finish? Might not be needed.
        # time.sleep(0.1)
        
        if self.use_webcam and self.cap:
            try:
                self.cap.release()
                print("OpenCV webcam released.")
                self.cap = None
            except Exception as e:
                print(f"Error releasing OpenCV webcam: {e}")
        elif self.picam2:
            try:
                # Check if picam2 object exists and was started
                if hasattr(self.picam2, 'started') and self.picam2.started:
                    self.picam2.stop()
                    print("Picamera2 stopped.")
            except Exception as e:
                print(f"Error stopping Picamera2: {e}")
            finally:
                # Attempt to close even if stop failed
                try:
                    if self.picam2: # Check if picam2 object exists
                        self.picam2.close()
                        print("Picamera2 closed.")
                        self.picam2 = None
                except Exception as e:
                    print(f"Error closing Picamera2 connection: {e}")
        
        # LSL Outlet cleanup is handled by garbage collection
        # Setting outlet to None might help signal this earlier
        self.outlet = None 
        self.info = None
        print("LSL stream outlet cleanup initiated.")

    def capture_frame(self):
        """
        Captures a single frame, pushes it to LSL, and returns the frame and timestamp.
        Returns None, None if not running or capture fails.
        """
        if not self._is_running or self.outlet is None:
            return None, None

        timestamp = local_clock() # Get timestamp as close to capture as possible
        frame_data = None
        
        try:
            if self.use_webcam and self.cap:
                ret, frame_data = self.cap.read() # Read BGR frame
                if not ret:
                    print("Warning: Failed to grab frame from webcam. Skipping.")
                    return None, None
            elif self.picam2:
                frame_data = self.picam2.capture_array()
            else:
                print("Error: Camera not available for capture.")
                return None, None

            # Push to LSL
            flat_frame_data = frame_data.flatten()
            self.outlet.push_sample(flat_frame_data, timestamp)
            self.frame_count += 1
            
            return frame_data, timestamp

        except Exception as e:
            print(f"Error during frame capture or LSL push: {e}")
            traceback.print_exc()
            # Consider stopping the stream on repeated errors?
            # self.stop()
            return None, None
            
    def get_info(self):
        """Returns a dictionary with current stream configuration."""
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
        """Returns the number of frames successfully pushed."""
        return self.frame_count

    # Ensure cleanup on object deletion (e.g., if GUI closes unexpectedly)
    def __del__(self):
        self.stop()

# Remove old standalone function
# def stream_camera(...): ... 