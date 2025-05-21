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
except ImportError:
    # Handle relative imports if run as script
    sys.path.append(str(Path(__file__).resolve().parent.parent))
    from src.raspberry_pi_lsl_stream.camera_lock import CameraLock
    from src.raspberry_pi_lsl_stream.camera_stream_fixed import LSLCameraStreamer
    from src.raspberry_pi_lsl_stream.buffer_trigger import BufferTriggerManager
    from src.raspberry_pi_lsl_stream.status_display import StatusDisplay

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
    
    parser = argparse.ArgumentParser(description='Camera capture and streaming')
    parser.add_argument('--camera-id', type=int, default=0, 
                       help='Camera index or ID to use (0=default camera, 1=second camera)')
    parser.add_argument('--width', type=int, default=400, help='Frame width')
    parser.add_argument('--height', type=int, default=400, help='Frame height')
    parser.add_argument('--fps', type=int, default=100, help='Target frame rate')
    parser.add_argument('--save-video', action='store_true', help='Save video files')
    parser.add_argument('--output-dir', type=str, default='recordings', help='Directory to save recordings')
    parser.add_argument('--codec', type=str, choices=['auto', 'h264', 'h265', 'mjpg'], default='mjpg', 
                       help='Video codec to use (mjpg recommended for high frame rates)')
    parser.add_argument('--no-preview', action='store_true', help='Disable preview window')
    parser.add_argument('--no-lsl', action='store_true', help='Disable LSL streaming')
    parser.add_argument('--stream-name', type=str, default='VideoStream', help='LSL stream name')
    parser.add_argument('--no-buffer', action='store_true', help='Disable buffer trigger system')
    parser.add_argument('--buffer-size', type=float, default=20.0, help='Buffer size in seconds')
    parser.add_argument('--ntfy-topic', type=str, default='raspie-camera-test', 
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
    
    args = parser.parse_args()
    
    # Force cleanup previous instances
    force_cleanup_previous_instances()
    
    # Set CPU affinity for main process if requested
    set_cpu_affinity(args.capture_cpu_core)
    
    # Try to acquire the camera lock
    with CameraLock() as camera_lock:
        if not camera_lock.is_locked:
            logger.error("Failed to acquire camera lock. Another instance may be running.")
            return 1
            
        logger.info("Starting camera capture system...")
        
        # Create output directory with date-based structure
        output_dir = args.output_dir
        if args.save_video:
            # Create date-based directory
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
        if not args.no_buffer:
            # Using the correct parameter names according to BufferTriggerManager.__init__
            buffer_manager = BufferTriggerManager(
                buffer_size_seconds=args.buffer_size,
                ntfy_topic=args.ntfy_topic,
                ntfy_cpu_core=args.ntfy_cpu_core
                # We'll connect the status_display after it's created
            )
        
        # Set up the camera streamer - adjust parameters as needed
        camera = None
        try:
            camera = LSLCameraStreamer(
                width=args.width,
                height=args.height,
                target_fps=args.fps,
                save_video=args.save_video,
                output_path=output_dir if args.save_video else None,
                codec=args.codec,
                show_preview=not args.no_preview,
                push_to_lsl=not args.no_lsl,
                stream_name=args.stream_name,
                use_buffer=not args.no_buffer,
                buffer_size_seconds=args.buffer_size,
                ntfy_topic=args.ntfy_topic,
                capture_cpu_core=args.capture_cpu_core,
                writer_cpu_core=args.writer_cpu_core,
                lsl_cpu_core=args.lsl_cpu_core,
                camera_id=args.camera_id,
                enable_crop=args.enable_crop
            )
            
            # Set up status display - always enable it for terminal UI
            status_display = StatusDisplay(
                camera_streamer=camera,
                buffer_manager=buffer_manager,
                ntfy_topic=args.ntfy_topic if buffer_manager else None
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