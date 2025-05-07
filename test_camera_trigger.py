#!/usr/bin/env python3
"""
Test script to verify camera detection and ntfy integration.
Author: Anzal
Email: anzal.ks@gmail.com
"""

import sys
import time
import logging
import os
from raspberry_pi_lsl_stream.camera_stream import LSLCameraStreamer
from raspberry_pi_lsl_stream.buffer_trigger import BufferTriggerManager

# Configure logging
logging.basicConfig(level=logging.INFO,
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("CameraTest")

def test_camera_and_trigger():
    """Test camera detection and ntfy integration"""
    logger.info("Starting camera and trigger test...")
    
    # Check if we're running over SSH
    is_ssh = 'SSH_CONNECTION' in os.environ
    show_preview = not is_ssh  # Only show preview if not running over SSH
    
    # Create camera streamer with debug settings
    streamer = LSLCameraStreamer(
        width=640,
        height=480,
        fps=30,
        show_preview=show_preview,  # Disable preview over SSH
        camera_index='auto',  # Try to auto-detect camera
        save_video=True,
        use_buffer=True,  # Enable buffer for testing
        buffer_size_seconds=10,  # 10 second buffer
        ntfy_topic='raspie-camera-test',  # Test topic
        push_to_lsl=False  # Disable LSL for testing
    )
    
    try:
        # Start the streamer
        logger.info("Starting camera streamer...")
        streamer.start()
        
        # Wait for 30 seconds to test buffer and ntfy
        logger.info("Waiting for 30 seconds to test buffer and ntfy...")
        logger.info("You can send ntfy messages to trigger recording:")
        logger.info("1. Start recording: curl -d 'Start Recording' ntfy.sh/raspie-camera-test")
        logger.info("2. Stop recording: curl -d 'Stop Recording' ntfy.sh/raspie-camera-test")
        
        time.sleep(30)
        
    except KeyboardInterrupt:
        logger.info("Test interrupted by user")
    except Exception as e:
        logger.error(f"Error during test: {e}")
    finally:
        # Stop the streamer
        logger.info("Stopping camera streamer...")
        streamer.stop()
        
        # Print final statistics
        logger.info("Test completed!")
        logger.info(f"Frames captured: {streamer.get_frame_count()}")
        logger.info(f"Frames written: {streamer.get_frames_written()}")
        logger.info(f"Frames dropped: {streamer.get_frames_dropped()}")

if __name__ == "__main__":
    test_camera_and_trigger() 