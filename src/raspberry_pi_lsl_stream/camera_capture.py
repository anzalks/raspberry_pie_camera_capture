#!/usr/bin/env python3
"""
Main script for camera capture and streaming.
"""

import os
import sys
import time
import signal
import argparse
import subprocess
import platform
from pathlib import Path
import logging
import datetime
import shutil

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

logger = logging.getLogger('CameraCapture')

try:
    from .camera_lock import CameraLock
    from .camera_stream_fixed import LSLCameraStreamer
    from .buffer_trigger import BufferTriggerManager
    from .status_display import StatusDisplay
    from .config_loader import get_camera_config  # Import the config loader
    from .status_file import StatusFileWriter  # Import the status file writer
except ImportError:
    # Handle relative imports if run as script
    sys.path.append(str(Path(__file__).resolve().parent.parent))
    from src.raspberry_pi_lsl_stream.camera_lock import CameraLock
    from src.raspberry_pi_lsl_stream.camera_stream_fixed import LSLCameraStreamer
    from src.raspberry_pi_lsl_stream.buffer_trigger import BufferTriggerManager
    from src.raspberry_pi_lsl_stream.status_display import StatusDisplay
    from src.raspberry_pi_lsl_stream.config_loader import get_camera_config  # Import the config loader
    from src.raspberry_pi_lsl_stream.status_file import StatusFileWriter  # Import the status file writer

# Try to import psutil for CPU affinity management
try:
    import psutil
    PSUTIL_AVAILABLE = True
    logger.info("psutil imported successfully for CPU affinity management")
except ImportError:
    PSUTIL_AVAILABLE = False
    logger.warning("psutil library not found. CPU core affinity will not be managed.")

# Global flag to control running state
running = True

def signal_handler(sig, frame):
    """Handle signals to clean up resources."""
    global running
    print("\nStopping camera capture...")
    running = False

def force_cleanup_previous_instances():
    """
    Force cleanup any previous instances that might be running.
    This ensures we don't have multiple instances trying to use the camera.
    """
    logger.info("Checking for previous instances...")
    
    # Force release any stale camera locks
    CameraLock.force_release()
    
    # Try to detect and kill any other camera capture processes
    if platform.system() == "Linux":
        try:
            # Find other python processes running camera_capture
            output = subprocess.check_output(
                ["pgrep", "-f", "python.*camera_capture"],
                universal_newlines=True
            ).strip()
            
            pids = output.splitlines()
            my_pid = os.getpid()
            
            for pid_str in pids:
                try:
                    pid = int(pid_str)
                    # Don't kill ourselves
                    if pid != my_pid:
                        logger.warning(f"Killing previous camera process: {pid}")
                        os.kill(pid, signal.SIGKILL)
                except (ValueError, ProcessLookupError):
                    pass
                    
        except subprocess.CalledProcessError:
            # No matching processes found
            pass
    
    logger.info("Cleanup complete")

def check_system_packages():
    """Check that all required system executables are installed."""
    if platform.system() != "Linux":
        return True
        
    executables = {
        "v4l2-ctl": "v4l-utils (video4linux utilities, install with 'sudo apt install v4l-utils')",
        "libcamera-hello": "libcamera-apps (camera interface library, install with 'sudo apt install libcamera-apps')"
    }
    
    all_installed = True
    for executable, description in executables.items():
        if shutil.which(executable) is None:
            logger.warning(f"Required system executable '{executable}' (from {description}) is not found in PATH.")
            all_installed = False
        else:
            logger.info(f"System executable '{executable}' found.")
            
    return all_installed

def set_cpu_affinity(cpu_core):
    """Set CPU affinity for the current process if psutil is available.
    
    Args:
        cpu_core: CPU core to pin the process to
    """
    if not PSUTIL_AVAILABLE or cpu_core is None:
        return
        
    try:
        p = psutil.Process()
        p.cpu_affinity([cpu_core])
        logger.info(f"Set process affinity to core {cpu_core}")
    except Exception as e:
        logger.error(f"Failed to set CPU affinity: {e}")

def main():
    """Main function for camera capture."""
    global running
    
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Set up command-line argument parser
    parser = argparse.ArgumentParser(description='Camera capture and streaming')
    parser.add_argument('--config', type=str, default='config.yaml',
                       help='Path to configuration file')
    parser.add_argument('--camera-id', type=int, default=None, 
                       help='Camera index or ID to use (0=default camera, 1=second camera)')
    parser.add_argument('--width', type=int, default=None, help='Frame width')
    parser.add_argument('--height', type=int, default=None, help='Frame height')
    parser.add_argument('--fps', type=int, default=None, help='Target frame rate')
    parser.add_argument('--save-video', action='store_true', help='Save video files')
    parser.add_argument('--output-dir', type=str, default=None, help='Directory to save recordings')
    parser.add_argument('--codec', type=str, choices=['auto', 'h264', 'h265', 'mjpg'], default=None, 
                       help='Video codec to use (mjpg recommended for high frame rates)')
    parser.add_argument('--no-preview', action='store_true', help='Disable preview window')
    parser.add_argument('--no-lsl', action='store_true', help='Disable LSL streaming')
    parser.add_argument('--stream-name', type=str, default=None, help='LSL stream name')
    parser.add_argument('--no-buffer', action='store_true', help='Disable buffer trigger system')
    parser.add_argument('--buffer-size', type=float, default=None, help='Buffer size in seconds')
    parser.add_argument('--ntfy-topic', type=str, default=None, 
                       help='Topic for ntfy notifications')
    parser.add_argument('--enable-crop', action='store_true',
                       help='Enable camera sensor cropping (automatically enabled for Global Shutter Camera)')
    
    # Add CPU core affinity options
    parser.add_argument('--capture-cpu-core', type=int, default=None, 
                       help='CPU core to use for capture thread')
    parser.add_argument('--writer-cpu-core', type=int, default=None, 
                       help='CPU core to use for writer thread')
    parser.add_argument('--lsl-cpu-core', type=int, default=None, 
                       help='CPU core to use for LSL thread')
    parser.add_argument('--ntfy-cpu-core', type=int, default=None, 
                       help='CPU core to use for ntfy subscriber thread')
    
    # Parse command-line arguments
    args = parser.parse_args()
    
    # Load configuration from file and merge with command-line arguments
    config = get_camera_config(args.config, args)
    
    # Extract configuration values with command-line overrides
    camera_config = config.get('camera', {})
    storage_config = config.get('storage', {})
    buffer_config = config.get('buffer', {})
    remote_config = config.get('remote', {})
    lsl_config = config.get('lsl', {})
    performance_config = config.get('performance', {})
    
    # Force cleanup previous instances
    force_cleanup_previous_instances()
    
    # Check system packages
    if not check_system_packages():
        logger.warning("Some required system executables are missing. Camera functionality may be limited.")
    
    # Set CPU affinity for main process if requested
    capture_cpu_core = performance_config.get('capture_cpu_core')
    set_cpu_affinity(capture_cpu_core)
    
    # Try to acquire the camera lock
    with CameraLock() as camera_lock:
        if not camera_lock.is_locked:
            logger.error("Failed to acquire camera lock. Another instance may be running.")
            return 1
            
        logger.info("Starting camera capture system...")
        
        # Create output directory with date-based structure
        output_dir = storage_config.get('output_dir', 'recordings')
        save_video = storage_config.get('save_video', True)
        
        if save_video:
            # Create date-based directory if enabled
            if storage_config.get('create_date_folders', True):
                today = datetime.datetime.now().strftime("%Y_%m_%d")
                
                # Check if output_dir already ends with a date
                if not os.path.basename(output_dir).startswith("20"):
                    output_dir = os.path.join(output_dir, today)
                    
            # Add video subdirectory
            video_dir = os.path.join(output_dir, "video")
            os.makedirs(video_dir, exist_ok=True)
            logger.info(f"Video recordings will be saved to: {video_dir} in MKV format")
            output_dir = video_dir
            
        # Set up buffer trigger manager if enabled
        buffer_manager = None
        buffer_enabled = buffer_config.get('enabled', True)
        if buffer_enabled:
            buffer_size = buffer_config.get('size', 20.0)
            ntfy_topic = remote_config.get('ntfy_topic', 'raspie-camera-test')
            ntfy_cpu_core = performance_config.get('ntfy_cpu_core')
            
            # Using the correct parameter names according to BufferTriggerManager.__init__
            buffer_manager = BufferTriggerManager(
                buffer_size_seconds=buffer_size,
                ntfy_topic=ntfy_topic,
                ntfy_cpu_core=ntfy_cpu_core
                # We'll connect the status_display after it's created
            )
        
        # Set up the camera streamer - adjust parameters as needed
        camera = None
        try:
            width = camera_config.get('width', 400)
            height = camera_config.get('height', 400)
            fps = camera_config.get('fps', 100)
            codec = camera_config.get('codec', 'mjpg')
            show_preview = camera_config.get('preview', False)
            stream_name = lsl_config.get('stream_name', 'VideoStream')
            camera_id = args.camera_id if args.camera_id is not None else 0
            
            # Handle enable_crop setting
            enable_crop_setting = camera_config.get('enable_crop', 'auto')
            enable_crop = False
            if enable_crop_setting == True or args.enable_crop:
                enable_crop = True
            # 'auto' is handled by the camera streamer internally
            
            # Get CPU core settings
            writer_cpu_core = performance_config.get('writer_cpu_core')
            lsl_cpu_core = performance_config.get('lsl_cpu_core')
            
            camera = LSLCameraStreamer(
                width=width,
                height=height,
                target_fps=fps,
                save_video=save_video,
                output_path=output_dir if save_video else None,
                codec=codec,
                show_preview=show_preview,
                push_to_lsl=not args.no_lsl,
                stream_name=stream_name,
                use_buffer=buffer_enabled,
                buffer_size_seconds=buffer_config.get('size', 20.0),
                ntfy_topic=remote_config.get('ntfy_topic', 'raspie-camera-test'),
                capture_cpu_core=capture_cpu_core,
                writer_cpu_core=writer_cpu_core,
                lsl_cpu_core=lsl_cpu_core,
                camera_id=camera_id,
                enable_crop=enable_crop
            )
            
            # Set up status display - always enable it for terminal UI
            status_display = StatusDisplay(
                camera_streamer=camera,
                buffer_manager=buffer_manager,
                ntfy_topic=remote_config.get('ntfy_topic') if buffer_manager else None
            )
            
            # Connect status display to buffer manager after creation
            if buffer_manager:
                buffer_manager.status_display = status_display
            
            # Start the camera
            started = camera.start()
            if not started:
                logger.error("Failed to start camera")
                return 1
                
            # Start the buffer manager if it exists
            if buffer_manager:
                buffer_manager.start()
                
            # Start the status display
            status_display.start()
                
            # Main loop
            logger.info("Camera capture started. Press Ctrl+C to stop.")
            
            while running:
                # Capture a frame
                frame = camera.capture_frame()
                
                # Small sleep to prevent CPU overuse
                time.sleep(0.01)
                
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
        except Exception as e:
            logger.exception(f"Error in main loop: {e}")
        finally:
            # Cleanup resources
            if 'status_display' in locals() and status_display:
                logger.info("Stopping status display...")
                status_display.stop()
                
            if camera:
                logger.info("Stopping camera...")
                camera.stop()
                
            if buffer_manager:
                logger.info("Stopping buffer manager...")
                buffer_manager.stop()
                
            logger.info("Camera capture stopped")
    
    return 0
    
if __name__ == '__main__':
    sys.exit(main()) 