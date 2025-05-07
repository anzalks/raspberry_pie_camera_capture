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

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

logger = logging.getLogger('CameraCapture')

try:
    from .camera_lock import CameraLock
    from .camera_stream import LSLCameraStreamer
    from .buffer_trigger import BufferTriggerManager
    from .status_display import StatusDisplay
except ImportError:
    # Handle relative imports if run as script
    sys.path.append(str(Path(__file__).resolve().parent.parent))
    from src.raspberry_pi_lsl_stream.camera_lock import CameraLock
    from src.raspberry_pi_lsl_stream.camera_stream import LSLCameraStreamer
    from src.raspberry_pi_lsl_stream.buffer_trigger import BufferTriggerManager
    from src.raspberry_pi_lsl_stream.status_display import StatusDisplay

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

def main():
    """Main function for camera capture."""
    global running
    
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    parser = argparse.ArgumentParser(description='Camera capture and streaming')
    parser.add_argument('--camera-id', type=int, default=0, help='Camera index or ID to use')
    parser.add_argument('--width', type=int, default=640, help='Frame width')
    parser.add_argument('--height', type=int, default=480, help='Frame height')
    parser.add_argument('--fps', type=int, default=30, help='Target frame rate')
    parser.add_argument('--save-video', action='store_true', help='Save video files')
    parser.add_argument('--output-dir', type=str, default='recordings', help='Directory to save recordings')
    parser.add_argument('--codec', type=str, choices=['auto', 'h264', 'h265', 'mjpg'], default='auto', 
                       help='Video codec to use')
    parser.add_argument('--no-preview', action='store_true', help='Disable preview window')
    parser.add_argument('--no-lsl', action='store_true', help='Disable LSL streaming')
    parser.add_argument('--stream-name', type=str, default='VideoStream', help='LSL stream name')
    parser.add_argument('--no-buffer', action='store_true', help='Disable buffer trigger system')
    parser.add_argument('--buffer-size', type=float, default=5.0, help='Buffer size in seconds')
    parser.add_argument('--ntfy-topic', type=str, default='raspie-camera-test', 
                       help='Topic for ntfy notifications')
    
    args = parser.parse_args()
    
    # Force cleanup previous instances
    force_cleanup_previous_instances()
    
    # Try to acquire the camera lock
    with CameraLock() as camera_lock:
        if not camera_lock.is_locked:
            logger.error("Failed to acquire camera lock. Another instance may be running.")
            return 1
            
        logger.info("Starting camera capture system...")
        
        # Create output directory if saving videos
        if args.save_video:
            os.makedirs(args.output_dir, exist_ok=True)
            logger.info(f"Video recordings will be saved to: {args.output_dir}")
            
        # Set up buffer trigger manager if enabled
        buffer_manager = None
        if not args.no_buffer:
            buffer_frames = int(args.buffer_size * args.fps)
            buffer_manager = BufferTriggerManager(
                buffer_size=buffer_frames,
                ntfy_topic=args.ntfy_topic
            )
        
        # Set up the camera streamer
        camera = LSLCameraStreamer(
            camera_id=args.camera_id,
            width=args.width,
            height=args.height,
            fps=args.fps,
            buffer_manager=buffer_manager,
            lsl_enabled=not args.no_lsl,
            stream_name=args.stream_name,
            output_dir=args.output_dir if args.save_video else None,
            preview_enabled=not args.no_preview,
            codec=args.codec
        )
        
        # Set up status display
        status_display = None
        if not args.no_preview:
            status_display = StatusDisplay(
                camera_streamer=camera,
                buffer_manager=buffer_manager,
                ntfy_topic=args.ntfy_topic if buffer_manager else None
            )
        
        # Start the camera
        if not camera.start():
            logger.error("Failed to start camera")
            return 1
            
        try:
            # Main loop
            logger.info("Camera capture started. Press Ctrl+C to stop.")
            
            while running:
                # Update status display
                if status_display:
                    status_display.update()
                time.sleep(0.1)
                
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
        except Exception as e:
            logger.exception(f"Error in main loop: {e}")
        finally:
            # Cleanup resources
            logger.info("Stopping camera...")
            camera.stop()
            
            if buffer_manager:
                logger.info("Stopping buffer manager...")
                buffer_manager.stop()
                
            logger.info("Camera capture stopped")
    
    return 0
    
if __name__ == '__main__':
    sys.exit(main()) 