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
    from picamera2 import Picamera2
    PICAMERA2_AVAILABLE = True
    # Check if we can get the version
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
                 enable_crop=None,
                 camera_id=0):
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
            enable_crop (bool, optional): Automatically detected if None, otherwise forces crop mode.
            camera_id (int): Camera ID to use (for multiple cameras).
        """
        # Validate and sanitize parameters
        self._validate_config(width, height, target_fps, codec, buffer_size_seconds, 
                             queue_size_seconds, capture_cpu_core, writer_cpu_core, lsl_cpu_core)
                             
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
        self.enable_crop = enable_crop
        self.camera_id = camera_id
        
        # Initialize state variables
        self._is_running = False
        self.frame_count = 0
        self.frames_written_count = 0
        self.frames_dropped_count = 0
        self.actual_fps = target_fps
        self.camera_model = "Raspberry Pi Camera"
        self.is_global_shutter = False
        
        # Check if it's a Global Shutter Camera
        self._check_global_shutter_camera()
        
        # Get Raspberry Pi's unique ID from /proc/cpuinfo
        try:
            self.source_id = self._get_raspberry_pi_id()
        except:
            # Fallback to UUID if we can't get the Pi's ID
            self.source_id = str(uuid.uuid4())
            
        self.lsl_pixel_format = "BGR"
        self.num_channels = 3
        self.buffer = None  # Initialize buffer reference
        
        # Initialize LSL outlets
        self.outlet = None
        self.status_outlet = None  # New outlet for recording status
        
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
        
        # Start status thread for LSL status publishing
        self.stop_status_event = threading.Event()
        self.status_thread = None
        self.status_display = None
        self.status_file_writer = None

    def _get_raspberry_pi_id(self):
        """Get Raspberry Pi's unique serial number from /proc/cpuinfo."""
        try:
            # Only works on Raspberry Pi
            if not os.path.exists("/proc/cpuinfo"):
                return str(uuid.uuid4())
                
            with open("/proc/cpuinfo", "r") as f:
                for line in f:
                    if line.startswith("Serial"):
                        # Extract serial number after colon and strip whitespace
                        return line.split(":")[1].strip()
            
            # If serial not found
            return str(uuid.uuid4())
        except Exception as e:
            print(f"Error getting Raspberry Pi ID: {e}")
            return str(uuid.uuid4())

    def _check_global_shutter_camera(self):
        """Detect if a Global Shutter Camera is connected and configure it."""
        if platform.system() != "Linux":
            print("Global Shutter Camera detection only works on Linux")
            return False
            
        try:
            # Check for the IMX296 sensor which is used in the Global Shutter Camera
            result = subprocess.run(
                ["vcgencmd", "get_camera"],
                capture_output=True,
                text=True,
                check=False
            )
            
            if "detected=1" in result.stdout:
                # Further check if it's specifically a Global Shutter Camera by checking for IMX296
                for m in range(6):  # Try media devices 0-5
                    cmd = ["media-ctl", "-d", f"/dev/media{m}", "-p"]
                    try:
                        media_result = subprocess.run(cmd, capture_output=True, text=True, check=False)
                        if "imx296" in media_result.stdout.lower():
                            print(f"Global Shutter Camera detected on /dev/media{m}")
                            self.is_global_shutter = True
                            self.camera_model = "Raspberry Pi Global Shutter Camera (IMX296)"
                            self.media_device = f"/dev/media{m}"
                            
                            # Set auto-cropping if enable_crop is None (auto-detect mode)
                            if self.enable_crop is None:
                                # We'll now auto-enable cropping for all Global Shutter Camera operations
                                # based on Hermann-SW's gist for achieving high frame rates
                                print(f"Auto-enabling Global Shutter Camera cropping for {self.width}x{self.height} at {self.target_fps}fps")
                                self.enable_crop = True
                            
                            # Configure cropping if enabled
                            if self.enable_crop:
                                self._configure_global_shutter_crop(m)
                            return True
                    except Exception as e:
                        print(f"Error checking media device {m}: {e}")
                        continue
                        
                # Additional check for IMX296 device node
                try:
                    for i in range(10):
                        cmd = ["v4l2-ctl", "--list-devices"]
                        device_result = subprocess.run(cmd, capture_output=True, text=True, check=False)
                        if "imx296" in device_result.stdout.lower():
                            print(f"Global Shutter Camera (IMX296) detected through v4l2 devices")
                            self.is_global_shutter = True
                            self.camera_model = "Raspberry Pi Global Shutter Camera (IMX296)"
                            # Configure with default media device since we couldn't find specific one
                            self.media_device = "/dev/media0"
                            
                            # Enable cropping for optimal performance
                            if self.enable_crop is None:
                                self.enable_crop = True
                                
                            if self.enable_crop:
                                self._configure_global_shutter_crop(0)  # Use media0 as fallback
                            return True
                except Exception as e:
                    print(f"Error checking v4l2 devices for IMX296: {e}")
        except Exception as e:
            print(f"Error detecting Global Shutter Camera: {e}")
            
        print("No Global Shutter Camera detected or cropping not enabled")
        return False
        
    def _configure_global_shutter_crop(self, media_device_num):
        """Configure cropping for Global Shutter Camera.
        
        This implements the cropping technique from Hermann-SW's gist:
        https://gist.github.com/Hermann-SW/e6049fe1a24fc2b5a53c654e0e9f6b9c
        
        The technique uses media-ctl to set specific crop regions that allow achieving
        high frame rates with the Global Shutter Camera.
        
        Args:
            media_device_num: The media device number (/dev/mediaX)
        """
        try:
            # Make sure width and height are even numbers
            if self.width % 2 != 0 or self.height % 2 != 0:
                print("Warning: Global Shutter Camera requires even width and height. Adjusting dimensions.")
                self.width = self.width - (self.width % 2)
                self.height = self.height - (self.height % 2)
                
            # Check if dimensions and FPS combination requires optimization
            self._optimize_dimensions_for_fps()
                
            # Determine the device ID based on Pi model and camera ID
            device_id = 10  # Default for camera 0
            try:
                # Check if we're on a Pi 5
                is_pi5 = False
                with open("/proc/cpuinfo", "r") as f:
                    cpuinfo = f.read()
                    if "Revision" in cpuinfo and any(rev in cpuinfo for rev in ["17", "18"]):
                        is_pi5 = True
                        
                if is_pi5:
                    # Pi 5 uses different device IDs
                    device_id = 10 if self.camera_id == 0 else 11
            except Exception as e:
                print(f"Error determining Pi model: {e}")
                
            # Calculate crop parameters (centered on the sensor)
            # Global Shutter Camera has a 1456×1088 sensor
            sensor_width = 1456  # Full sensor width for precise cropping
            sensor_height = 1088
            
            # Calculate the top-left corner for crop to center it
            left = (sensor_width - self.width) // 2
            top = (sensor_height - self.height) // 2
            
            # Make sure left and top are even numbers
            left = left - (left % 2)
            top = top - (top % 2)
            
            # Check for bookworm OS to apply workaround if needed
            workaround = ""
            try:
                with open("/etc/os-release", "r") as f:
                    os_release = f.read()
                    if "=bookworm" in os_release:
                        workaround = "--no-raw"
                        print("Detected Bookworm OS, applying --no-raw workaround")
            except Exception as e:
                print(f"Error checking OS version: {e}")
            
            # Build the media-ctl command using Hermann-SW's approach
            # This command sets both format and crop in one operation
            cmd = [
                "media-ctl",
                "-d", f"/dev/media{media_device_num}",
                "--set-v4l2",
                f"'imx296 {device_id}-001a':0 [fmt:SBGGR10_1X10/{self.width}x{self.height} crop:({left},{top})/{self.width}x{self.height}]",
                "-v"
            ]
            
            print(f"Configuring Global Shutter Camera crop: {' '.join(cmd)}")
            cmd_str = " ".join(cmd)
            crop_result = subprocess.run(cmd_str, shell=True, capture_output=True, text=True)
            
            if crop_result.returncode == 0:
                print(f"Successfully configured Global Shutter Camera cropping to {self.width}x{self.height}")
                # Let's check if the configuration was applied correctly by listing camera info
                check_cmd = ["libcamera-hello", "--list-cameras"]
                check_result = subprocess.run(check_cmd, capture_output=True, text=True)
                print("Camera configuration verified:")
                if check_result.returncode == 0:
                    # Extract and print relevant crop info from the output
                    for line in check_result.stdout.split('\n'):
                        if "crop" in line:
                            print(f"  {line.strip()}")
                else:
                    print("  Failed to verify camera configuration")
                
                # Update camera model with current configuration
                self.camera_model = f"Raspberry Pi Global Shutter Camera (IMX296) {self.width}x{self.height}@{self.target_fps}fps"
                return True
            else:
                print(f"Error configuring Global Shutter Camera cropping: {crop_result.stderr}")
                # Try alternative method with v4l2-ctl if media-ctl fails
                try:
                    print("Attempting fallback method with v4l2-ctl...")
                    # Find the video device for the IMX296
                    video_device = None
                    cmd = ["v4l2-ctl", "--list-devices"]
                    v4l2_result = subprocess.run(cmd, capture_output=True, text=True)
                    lines = v4l2_result.stdout.split('\n')
                    for i, line in enumerate(lines):
                        if "imx296" in line.lower() and i+1 < len(lines):
                            video_device = lines[i+1].strip()
                            break
                            
                    if video_device:
                        print(f"Found IMX296 on {video_device}")
                        # Set format using v4l2-ctl
                        format_cmd = [
                            "v4l2-ctl",
                            "-d", video_device,
                            "--set-fmt-video=width={},height={},pixelformat=RGGB".format(self.width, self.height)
                        ]
                        subprocess.run(format_cmd)
                        
                        # Set crop using v4l2-ctl
                        crop_cmd = [
                            "v4l2-ctl",
                            "-d", video_device,
                            "--set-crop=top={},left={},width={},height={}".format(top, left, self.width, self.height)
                        ]
                        subprocess.run(crop_cmd)
                        print("Applied fallback configuration with v4l2-ctl")
                        return True
                    else:
                        print("Could not find IMX296 video device")
                except Exception as e:
                    print(f"Fallback configuration failed: {e}")
                return False
                
        except Exception as e:
            print(f"Error configuring Global Shutter Camera crop: {e}")
            traceback.print_exc()
            return False

    def _optimize_dimensions_for_fps(self):
        """Optimize dimensions based on target FPS for Global Shutter Camera.
        
        Based on Hermann-SW's research (https://gist.github.com/Hermann-SW/e6049fe1a24fc2b5a53c654e0e9f6b9c)
        the following crop configurations work reliably:
        - 1456x96 at 536fps (full width, minimal height)
        - 688x136 at 400fps (medium crop)
        - 224x96 at 500fps (small crop)
        - 600x600 at 200fps (square crop for general usage)
        """
        # Store original dimensions for reporting
        original_width = self.width
        original_height = self.height
    
        # Check if user requested a square crop (equal width and height)
        is_square_crop = self.width == self.height
        
        # Optimize dimensions for specific frame rate targets
        if self.target_fps >= 500:
            # For very high fps (500+), use either the 224x96 or 1456x96 configuration
            # from Hermann-SW's research
            if self.height > 96:
                print(f"Warning: Adjusting height from {self.height} to 96 to achieve {self.target_fps}fps")
                self.height = 96
                
            if self.width != 224 and self.width != 1456:
                # Check if user wanted full width or narrow crop
                if self.width < 800:  # User probably wanted small ROI
                    print(f"Warning: Adjusting width from {self.width} to 224 to achieve {self.target_fps}fps")
                    self.width = 224
                else:  # User probably wanted full width
                    print(f"Warning: Adjusting width from {self.width} to 1456 to achieve {self.target_fps}fps")
                    self.width = 1456
                    
        elif self.target_fps > 350 and self.target_fps < 500:
            # For ~400fps, use the 688x136 configuration that Hermann-SW found optimal
            if self.width != 688 or self.height != 136:
                print(f"Warning: Adjusting dimensions from {self.width}x{self.height} to 688x136 to achieve {self.target_fps}fps")
                self.width = 688
                self.height = 136
                
        elif self.target_fps > 180 and self.target_fps <= 350:
            # For ~200fps with square crop, we can use up to about 600x600
            if is_square_crop and self.width > 600:
                print(f"Warning: Adjusting square dimensions from {self.width}x{self.height} to 600x600 to achieve {self.target_fps}fps")
                self.width = 600
                self.height = 600
            elif not is_square_crop:
                # For non-square crops at ~200fps, scale dimensions appropriately
                max_total_pixels = 600 * 600
                current_pixels = self.width * self.height
                
                if current_pixels > max_total_pixels:
                    # Scale dimensions down while maintaining aspect ratio
                    scale_factor = (max_total_pixels / current_pixels) ** 0.5
                    self.width = int(self.width * scale_factor)
                    self.height = int(self.height * scale_factor)
                    print(f"Warning: Scaling dimensions to {self.width}x{self.height} to achieve {self.target_fps}fps")
                    
                    # Ensure dimensions are even
                    self.width = self.width - (self.width % 2)
                    self.height = self.height - (self.height % 2)
                
        elif self.target_fps > 120:
            # For other high frame rates (120-180fps), ensure dimensions are reasonable
            max_total_pixels = 700 * 700  # Slightly higher max pixel count
            current_pixels = self.width * self.height
            
            if current_pixels > max_total_pixels:
                # Scale dimensions down while maintaining aspect ratio
                scale_factor = (max_total_pixels / current_pixels) ** 0.5
                self.width = int(self.width * scale_factor)
                self.height = int(self.height * scale_factor)
                print(f"Warning: Scaling dimensions to {self.width}x{self.height} to achieve {self.target_fps}fps")
                
                # Ensure dimensions are even
                self.width = self.width - (self.width % 2)
                self.height = self.height - (self.height % 2)
        
        # Make sure we still have even dimensions (required by the camera)
        if self.width % 2 != 0:
            self.width -= 1
        if self.height % 2 != 0:
            self.height -= 1
        
        # Report if dimensions were changed
        if original_width != self.width or original_height != self.height:
            print(f"Dimensions adjusted from {original_width}x{original_height} to {self.width}x{self.height} for target fps: {self.target_fps}")
        else:
            print(f"Using dimensions: {self.width}x{self.height} for target fps: {self.target_fps}")

    def _initialize_camera(self):
        """Initialize the Pi Camera."""
        try:
            print("Initializing Raspberry Pi Camera...")
            
            # Create PiCamera object
            self.camera = Picamera2()
            
            # If camera_id is specified for multiple cameras, set it
            if self.camera_id > 0:
                self.camera.set_camera(self.camera_id)
            
            # First, check if we haven't already detected the camera type
            if not hasattr(self, 'is_global_shutter') or not hasattr(self, 'enable_crop'):
                # Check for Global Shutter Camera
                self._check_global_shutter_camera()
            
            if self.is_global_shutter:
                print(f"Using Global Shutter Camera: {self.width}x{self.height} at {self.target_fps} fps")
                
                # For high frame rates, we need to enable crop mode
                if self.target_fps > 100 and (self.enable_crop is None or self.enable_crop):
                    # Auto-enable cropping for high frame rates
                    self.enable_crop = True
                    print(f"Auto-enabling crop mode for high frame rate: {self.target_fps} fps")
                
                # Special settings for Global Shutter Camera
                if self.enable_crop:
                    # If cropping is enabled, the configuration has already been done by media-ctl
                    # We don't need additional configuration here, just start the camera
                    pass
                else:
                    # For standard usage without cropping, configure with normal settings
                    config = self.camera.create_video_configuration(
                        main={"size": (self.width, self.height), "format": "BGR888"},
                        lores={"size": (self.width, self.height), "format": "YUV420"}
                    )
                    
                    # Set additional video parameters for Global Shutter camera
                    config["controls"] = {
                        "FrameRate": self.target_fps,
                        "NoiseReductionMode": 1,  # Fast noise reduction
                        # Add any Global Shutter specific controls here
                    }
                    
                    self.camera.configure(config)
            else:
                # Standard configuration for regular Pi camera
                # Using BGR format directly since OpenCV uses BGR
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
            print(f"Camera initialized with resolution {self.width}x{self.height} at target {self.target_fps} fps")
            
            # Set frame rate
            self.actual_fps = self.target_fps
            print(f"Camera frame rate set to: {self.actual_fps} fps")
            print(f"Camera color format: BGR888 (native for OpenCV)")
            
            # Test frame capture using capture_array()
            try:
                frame = self.camera.capture_array("main")
                if frame is None or frame.size == 0:
                    raise RuntimeError("Failed to capture test frame (empty frame)")
                print(f"Test frame shape: {frame.shape}, dtype: {frame.dtype}")
            except Exception as e:
                print(f"Error during test frame capture: {e}")
                raise
                
            print("Successfully initialized Camera")
            return True

        except Exception as e:
            print(f"Error initializing Camera: {e}")
            if self.camera is not None:
                try:
                    self.camera.stop()
                except Exception as e:
                    print(f"Error stopping Camera: {e}")
            self.camera = None
            raise RuntimeError(f"Failed to initialize Camera: {e}")

    def _initialize_video_writer(self):
        """Initialize the video writer for saving frames."""
        if not self.save_video:
            return
            
        try:
            # Generate output filename with timestamp
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Always use MKV as the container format
            extension = "mkv"
                
            self.auto_output_filename = f"recording_{timestamp}.{extension}"
            
            # Create full output path
            if self.output_path:
                output_file = os.path.join(self.output_path, self.auto_output_filename)
            else:
                output_file = self.auto_output_filename
                
            print(f"Initializing video writer for file: {output_file}")
            
            # Determine codec - use MJPG as the preferred codec for high frame rates
            codec_map = {
                'h264': 'X264',  # X264 is more compatible with Raspberry Pi
                'h265': 'X265',  # X265 for HEVC codec
                'mjpg': 'MJPG'   # Motion JPEG - better for high fps
            }
            
            if self.codec.lower() not in codec_map:
                print(f"Warning: Unsupported codec '{self.codec}'. Falling back to MJPG for high frame rate support.")
                fourcc = cv2.VideoWriter_fourcc(*'MJPG')
                self.codec = 'mjpg'  # Update codec to match what we're actually using
            else:
                fourcc = cv2.VideoWriter_fourcc(*codec_map[self.codec.lower()])
                
            print(f"Using codec: {self.codec.lower()} with FourCC: {codec_map.get(self.codec.lower(), 'MJPG')} in MKV container")
            
            # Create video writer - always using MKV container for robustness
            self.video_writer = cv2.VideoWriter(
                output_file,
                fourcc,
                self.actual_fps,
                (self.width, self.height)
            )
            
            if not self.video_writer.isOpened():
                print("Failed to open video writer with MKV container, retrying with MKV/MJPG combination...")
                
                # Try MJPG with MKV as a consistent fallback
                mjpg_mkv_file = os.path.join(os.path.dirname(output_file), 
                                       f"retry_{os.path.basename(output_file)}")
                self.video_writer = cv2.VideoWriter(
                    mjpg_mkv_file,
                    cv2.VideoWriter_fourcc(*'MJPG'),
                    self.actual_fps,
                    (self.width, self.height)
                )
                
                if not self.video_writer.isOpened():
                    raise RuntimeError(f"Failed to open video writer with MKV container")
                else:
                    print(f"Successfully opened video writer with fallback: {mjpg_mkv_file}")
                    
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
                    
            # Create StreamInfo for frame numbers only
            self.info = StreamInfo(
                name=self.stream_name,
                type='Markers',
                channel_count=4,  # Channel 1: frame number, Channel 2: timestamp, Channel 3: is_keyframe, Channel 4: ntfy_notification_active
                nominal_srate=self.actual_fps,
                channel_format='double',
                source_id=self.source_id
            )
            
            # Add metadata
            self.info.desc().append_child_value("manufacturer", "Raspberry Pi")
            self.info.desc().append_child_value("camera_model", "IMX708")
            self.info.desc().append_child_value("resolution", f"{self.width}x{self.height}")
            self.info.desc().append_child_value("fps", str(self.actual_fps))
            self.info.desc().append_child_value("format", "BGR")
            self.info.desc().append_child_value("content", "frame_metadata")
            self.info.desc().append_child_value("codec", self.codec)
            self.info.desc().append_child_value("buffer_size_seconds", str(self.buffer_size_seconds))
            
            # Add channel metadata
            channels = self.info.desc().append_child("channels")
            channels.append_child("channel").append_child_value("label", "FrameNumber")
            channels.append_child("channel").append_child_value("label", "Timestamp")
            channels.append_child("channel").append_child_value("label", "IsKeyframe")
            channels.append_child("channel").append_child_value("label", "NtfyNotificationActive")
            
            # Create outlet
            self.outlet = StreamOutlet(self.info)
            print(f"LSL stream '{self.stream_name}' created for frame metadata")
            
            # Create a separate LSL stream for recording status
            status_info = StreamInfo(
                name=f"{self.stream_name}_Status",
                type='RecordingStatus',
                channel_count=2,  # Channel 1: status flag, Channel 2: timestamp
                nominal_srate=10.0,  # Update status at 10Hz
                channel_format='double',
                source_id=f"{self.source_id}_Status"
            )
            
            # Add metadata
            status_info.desc().append_child_value("manufacturer", "Raspberry Pi")
            status_info.desc().append_child_value("camera_model", "IMX708")
            status_info.desc().append_child_value("content", "recording_status")
            status_info.desc().append_child_value("description", "0=not_recording, 1=recording, 2=buffering")
            
            # Create status channel label
            channels = status_info.desc().append_child("channels")
            channels.append_child("channel").append_child_value("label", "RecordingStatus")
            channels.append_child("channel").append_child_value("label", "Timestamp")
            
            # Create status outlet
            self.status_outlet = StreamOutlet(status_info)
            print(f"Created LSL status outlet: {self.stream_name}_Status")
            
        except Exception as e:
            print(f"Error setting up LSL stream: {e}")
            self.info = None
            self.outlet = None
            self.status_outlet = None

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
            
            # Start status thread if LSL is enabled
            if self.push_to_lsl and self.status_outlet:
                self.stop_status_event.clear()
                self.status_thread = threading.Thread(
                    target=self._status_thread,
                    name="CameraStatusThread",
                    daemon=True
                )
                self.status_thread.start()
                print("Camera status thread started")
            
            # Initialize status file writer for terminal fallback
            self.status_file_writer = StatusFileWriter(camera=self, buffer_manager=self.buffer_trigger_manager)
            self.status_file_writer.start()
            
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
        
        # Stop status thread if running
        if self.status_thread is not None and self.stop_status_event is not None:
            self.stop_status_event.set()
            self.status_thread.join(timeout=2.0)
            self.status_thread = None
        
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
            
        # Stop status file writer if running
        if self.status_file_writer:
            self.status_file_writer.stop()
            self.status_file_writer = None
            
        print("Camera stream stopped")

    def capture_frame(self):
        """Capture a single frame from the camera."""
        try:
            if not self._is_running:
                return None
                
            # Capture frame from PiCamera
            with self.camera_lock:
                try:
                    # Use capture_array which is the correct method for picamera2
                    frame = self.camera.capture_array("main")
                except Exception as e:
                    print(f"Failed to grab frame from camera: {e}")
                    return None
                    
                # Check if frame is valid
                if frame is None or frame.size == 0:
                    print("Failed to capture frame")
                    return None
                
                # Note: No conversion needed as we're already in BGR format
                
            # Update frame count
            self.frame_count += 1
            frame_timestamp = time.time()
            
            # Push frame metadata to LSL if enabled
            if self.push_to_lsl and self.outlet is not None:
                try:
                    # Send frame metadata: frame number, timestamp, keyframe flag (simulated), and ntfy_notification_active
                    # Every 30th frame is considered a keyframe for illustration
                    is_keyframe = 1.0 if self.frame_count % 30 == 0 else 0.0
                    ntfy_notification_active = 1.0 if self.recording_triggered else 0.0
                    self.outlet.push_sample([float(self.frame_count), frame_timestamp, is_keyframe, ntfy_notification_active])
                except Exception as e:
                    print(f"Error pushing frame metadata to LSL: {e}")
                    
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
                
            # Make sure frame queue is initialized even if video writer init failed but we want to try again
            if self.save_video and self.frame_queue is None:
                print("Frame queue not initialized. Initializing now...")
                try:
                    self.frame_queue = Queue(maxsize=int(self.queue_size_seconds * self.actual_fps))
                    # Start writer thread if not running
                    if self.writer_thread is None or not self.writer_thread.is_alive():
                        self.stop_writer_event = threading.Event()
                        self.writer_thread = threading.Thread(target=self._writer_loop, daemon=True)
                        self.writer_thread.start()
                        print("Writer thread started")
                except Exception as e:
                    print(f"Error initializing frame queue: {e}")
                    self.frame_queue = None
                
            # Write buffered frames
            if self.save_video and self.video_writer is not None and self.frame_queue is not None:
                for frame, timestamp in frames:
                    if not self.frame_queue.full():
                        self.frame_queue.put(frame)
                    else:
                        print("Frame queue full, dropping frame")
                        self.frames_dropped_count += 1
                        
            # Update state
            self.waiting_for_trigger = False
            self.recording_triggered = True
            
            # Send immediate status update
            if self.push_to_lsl and self.status_outlet:
                self.status_outlet.push_sample([1])  # 1 = recording
                
            print("Recording started")
            
        except Exception as e:
            print(f"Error handling recording trigger: {e}")
            # Try to recover from error
            if self.save_video and self.video_writer is None:
                print("Attempting to recover by re-initializing video writer...")
                try:
                    self._initialize_video_writer()
                    if self.video_writer is not None:
                        print("Video writer recovery successful")
                except Exception as recovery_error:
                    print(f"Recovery failed: {recovery_error}")

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
            
            # Send immediate status update
            if self.push_to_lsl and self.status_outlet:
                self.status_outlet.push_sample([2])  # 2 = buffering
                
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
        if self.push_to_lsl and self.status_outlet:
            self.status_outlet.push_sample([1])  # 1 = recording
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
        if self.push_to_lsl and self.status_outlet:
            self.status_outlet.push_sample([2])  # 2 = buffering
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

    def _status_thread(self):
        """Thread for publishing continuous camera status via LSL."""
        if self.status_outlet is None:
            return
            
        try:
            # Set CPU affinity if requested
            if self.lsl_cpu_core is not None:
                self._set_thread_affinity("status LSL", self.lsl_cpu_core)
                
            # Status update loop
            while not self.stop_status_event.is_set() and self._is_running:
                try:
                    # Determine current status
                    if self.recording_triggered:
                        status_value = 1  # Recording
                    elif self.waiting_for_trigger and self.use_buffer:
                        status_value = 2  # Buffering
                    else:
                        status_value = 0  # Idle
                        
                    # Current timestamp
                    current_time = time.time()
                        
                    # Send status update through LSL
                    self.status_outlet.push_sample([float(status_value), current_time])
                    
                    # Update at 10Hz
                    time.sleep(0.1)
                    
                except Exception as e:
                    print(f"Error in camera status thread: {e}")
                    time.sleep(1.0)  # Avoid tight loop on error
                    
        except Exception as e:
            print(f"Fatal error in camera status thread: {e}")

    def _validate_config(self, width, height, target_fps, codec, buffer_size_seconds, 
                        queue_size_seconds, capture_cpu_core, writer_cpu_core, lsl_cpu_core):
        """Validate and adjust configuration parameters to be compatible with hardware.
        
        Args:
            width (int): Desired frame width
            height (int): Desired frame height
            target_fps (float): Target frame rate
            codec (str): Video codec to use
            buffer_size_seconds (float): Size of rolling buffer in seconds
            queue_size_seconds (float): Size of frame queue in seconds
            capture_cpu_core (int): CPU core for capture thread
            writer_cpu_core (int): CPU core for writer thread
            lsl_cpu_core (int): CPU core for LSL thread
            
        Returns:
            None. Raises ValueError for invalid configurations.
        """
        # Resolution validation
        if width <= 0 or height <= 0:
            raise ValueError(f"Invalid resolution: {width}x{height}. Width and height must be positive.")
            
        # Check for reasonable resolution bounds for Pi Camera
        if width > 4032 or height > 3040:
            print(f"Warning: Resolution {width}x{height} exceeds maximum Pi Camera v3 resolution (4032x3040)")
            print("Performance may be degraded or capture may fail")
            
        # FPS validation
        if target_fps <= 0:
            raise ValueError(f"Invalid frame rate: {target_fps}. FPS must be positive.")
            
        if target_fps > 120:
            print(f"Warning: High frame rate requested ({target_fps} fps). The Raspberry Pi may struggle.")
            print("Consider reducing to 90 fps or less for better stability.")
            
        # Codec validation
        valid_codecs = ['h264', 'h265', 'mjpg']
        if codec.lower() not in valid_codecs:
            print(f"Warning: Codec '{codec}' not in supported list {valid_codecs}.")
            print("Falling back to MJPG for high frame rate compatibility")
            codec = 'mjpg'  # Reassigned in the caller
            
        # Buffer size validation
        if buffer_size_seconds <= 0:
            raise ValueError(f"Invalid buffer size: {buffer_size_seconds}. Buffer size must be positive.")
            
        # For high-resolution, high-fps combinations, ensure adequate buffer
        expected_frame_bytes = width * height * 3  # Estimated bytes per BGR frame
        frames_per_second = target_fps
        expected_buffer_bytes = expected_frame_bytes * frames_per_second * buffer_size_seconds
        
        # 1 GB in bytes as an arbitrary limit for reasonable memory usage
        if expected_buffer_bytes > 1 * 1024 * 1024 * 1024:
            print(f"Warning: Estimated buffer size is large: {expected_buffer_bytes / (1024*1024):.1f} MB")
            print("Consider reducing resolution, FPS, or buffer duration to avoid memory issues")
            
        # Queue size validation
        if queue_size_seconds <= 0:
            raise ValueError(f"Invalid queue size: {queue_size_seconds}. Queue size must be positive.")
            
        # CPU core validation
        if PSUTIL_AVAILABLE:
            try:
                cpu_count = psutil.cpu_count()
                
                # Validate capture CPU core
                if capture_cpu_core is not None and (capture_cpu_core < 0 or capture_cpu_core >= cpu_count):
                    print(f"Warning: Invalid capture CPU core: {capture_cpu_core}. Must be between 0 and {cpu_count-1}")
                    capture_cpu_core = None  # Reassigned in the caller
                    
                # Validate writer CPU core
                if writer_cpu_core is not None and (writer_cpu_core < 0 or writer_cpu_core >= cpu_count):
                    print(f"Warning: Invalid writer CPU core: {writer_cpu_core}. Must be between 0 and {cpu_count-1}")
                    writer_cpu_core = None  # Reassigned in the caller
                    
                # Validate LSL CPU core
                if lsl_cpu_core is not None and (lsl_cpu_core < 0 or lsl_cpu_core >= cpu_count):
                    print(f"Warning: Invalid LSL CPU core: {lsl_cpu_core}. Must be between 0 and {cpu_count-1}")
                    lsl_cpu_core = None  # Reassigned in the caller
                    
                # Check for duplicated CPU core assignments
                cores = [c for c in (capture_cpu_core, writer_cpu_core, lsl_cpu_core) if c is not None]
                if len(cores) != len(set(cores)):
                    print("Warning: Multiple threads assigned to same CPU core. Performance may be degraded.")
            except Exception as e:
                print(f"Warning: Error validating CPU cores: {e}")
                
        print("Configuration validation complete.") 

def main():
    """Run the camera streamer directly from the command line."""
    import argparse
    import time
    import os
    import sys
    import logging
    import signal
    
    # Configure logging
    logging.basicConfig(level=logging.INFO, 
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger = logging.getLogger("CameraStream")
    
    # Parse arguments
    parser = argparse.ArgumentParser(description="Raspberry Pi Camera Streamer")
    parser.add_argument("--width", type=int, default=400, help="Frame width")
    parser.add_argument("--height", type=int, default=400, help="Frame height")
    parser.add_argument("--fps", type=int, default=100, help="Target FPS")
    parser.add_argument("--output", type=str, default=None, help="Output directory (default: recordings/YYYY-MM-DD)")
    parser.add_argument("--codec", type=str, default="mjpg", help="Video codec (mjpg, h264)")
    parser.add_argument("--preview", action="store_true", help="Show preview window")
    parser.add_argument("--no-preview", action="store_true", help="Don't show preview window")
    parser.add_argument("--no-lsl", action="store_true", help="Disable LSL streaming")
    parser.add_argument("--no-buffer", action="store_true", help="Disable rolling buffer")
    parser.add_argument("--buffer-size", type=float, default=20.0, help="Buffer size in seconds")
    parser.add_argument("--ntfy-topic", type=str, default="raspie-camera-test", help="ntfy.sh topic for triggers")
    
    args = parser.parse_args()
    
    # Create date-based output directory if not specified
    if args.output is None:
        today = time.strftime("%Y-%m-%d")
        output_dir = os.path.join("recordings", today)
        os.makedirs(output_dir, exist_ok=True)
        logger.info(f"Created output directory: {output_dir}")
    else:
        output_dir = args.output
        os.makedirs(output_dir, exist_ok=True)
        
    print(f"📁 Recordings will be saved to: {output_dir}")
    print(f"📹 Files will be named: recording_YYYYMMDD_HHMMSS.mkv")
    
    # Determine preview setting
    show_preview = True
    if args.no_preview:
        show_preview = False
    elif args.preview:
        show_preview = True
    
    # Create and start the camera streamer
    try:
        camera = LSLCameraStreamer(
            width=args.width,
            height=args.height,
            target_fps=args.fps,
            save_video=True,
            output_path=output_dir,
            codec=args.codec,
            show_preview=show_preview,
            push_to_lsl=not args.no_lsl,
            stream_name="VideoStream",
            use_buffer=not args.no_buffer,
            buffer_size_seconds=args.buffer_size,
            ntfy_topic=args.ntfy_topic,
            enable_crop=True,  # Auto-detect Global Shutter Camera
        )
        
        # Register signal handlers
        def signal_handler(sig, frame):
            print("Received signal, shutting down...")
            if camera:
                camera.stop()
            sys.exit(0)
            
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Start the camera
        camera.start()
        
        # Create terminal UI function
        def print_status_update():
            # Clear terminal and print header
            os.system('clear' if os.name != 'nt' else 'cls')
            print("=" * 60)
            print("RASPBERRY PI CAMERA CAPTURE".center(60))
            print("=" * 60)
            
            info = camera.get_info()
            print(f"Camera: {info.get('camera_model', 'Unknown')}")
            print(f"Resolution: {info.get('width', 0)}x{info.get('height', 0)} @ {info.get('fps', 0)} fps")
            print(f"Frames captured: {camera.get_frame_count()}")
            print(f"Frames written: {camera.get_frames_written()}")
            
            if camera.buffer_trigger_manager:
                buffer_size = camera.buffer_trigger_manager.get_buffer_size()
                buffer_duration = camera.buffer_trigger_manager.get_buffer_duration()
                print(f"Buffer: {buffer_size} frames ({buffer_duration:.1f}s)")
                
            recording = info.get('recording', False)
            if recording:
                print("\033[1;32mRECORDING ACTIVE\033[0m")
            else:
                print("\033[1;33mWaiting for trigger\033[0m")
            
            print("-" * 60)
            print("Commands:")
            print(f"  - Start recording: curl -d 'Start Recording' ntfy.sh/{args.ntfy_topic}")
            print(f"  - Stop recording: curl -d 'Stop Recording' ntfy.sh/{args.ntfy_topic}")
            print("  - Press Ctrl+C to exit")
            print("-" * 60)
        
        # Main loop
        status_update_interval = 0.5  # Update status every 0.5 seconds
        last_update = time.time()
        
        while True:
            # Update status display
            if time.time() - last_update >= status_update_interval:
                print_status_update()
                last_update = time.time()
                
            time.sleep(0.1)
            
    except KeyboardInterrupt:
        print("Interrupted by user")
    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if 'camera' in locals() and camera:
            camera.stop()
            logger.info("Camera stopped")

if __name__ == "__main__":
    main() 