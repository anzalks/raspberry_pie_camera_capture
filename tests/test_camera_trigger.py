#!/usr/bin/env python3
"""
Test script for camera capture and trigger functionality.
"""

import os
import sys
import time
import signal
import argparse
from raspberry_pi_lsl_stream.camera_stream import LSLCameraStreamer, StatusDisplay

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Test camera capture and trigger")
    
    # Camera settings
    parser.add_argument("--camera-id", type=int, default=0,
                       help="Camera index or ID to use")
    parser.add_argument("--width", type=int, default=640,
                       help="Frame width")
    parser.add_argument("--height", type=int, default=480,
                       help="Frame height")
    parser.add_argument("--fps", type=float, default=30.0,
                       help="Target frame rate")
                       
    # Test settings
    parser.add_argument("--test-duration", type=float, default=30.0,
                       help="Test duration in seconds")
    parser.add_argument("--trigger-delay", type=float, default=5.0,
                       help="Delay before triggering recording")
    parser.add_argument("--record-duration", type=float, default=10.0,
                       help="Recording duration in seconds")
                       
    # Display settings
    parser.add_argument("--no-preview", action="store_true",
                       help="Disable preview window")
                       
    return parser.parse_args()

def main():
    """Main function."""
    # Parse arguments
    args = parse_args()
    
    # Create output directory
    output_dir = "test_recordings"
    os.makedirs(output_dir, exist_ok=True)
    
    # Initialize status display
    status = StatusDisplay()
    
    try:
        # Initialize camera streamer
        streamer = LSLCameraStreamer(
            camera_id=args.camera_id,
            width=args.width,
            height=args.height,
            target_fps=args.fps,
            save_video=True,
            output_path=output_dir,
            codec="auto",
            show_preview=not args.no_preview,
            push_to_lsl=False,
            stream_name="test_stream",
            use_buffer=True,
            buffer_size_seconds=5.0,
            ntfy_topic="raspie-camera-test"
        )
        
        # Start status display
        status.start()
        
        # Start camera streamer
        streamer.start()
        print("\nCamera streamer started")
        print(f"Test duration: {args.test_duration} seconds")
        print(f"Trigger delay: {args.trigger_delay} seconds")
        print(f"Record duration: {args.record_duration} seconds")
        
        # Wait for trigger delay
        print(f"\nWaiting {args.trigger_delay} seconds before triggering...")
        start_time = time.time()
        while time.time() - start_time < args.trigger_delay:
            # Update status
            status.update(
                frame_count=streamer.frame_count,
                frames_written=streamer.frames_written_count,
                frames_dropped=streamer.frames_dropped_count,
                buffer_size=streamer.buffer.get_buffer_size() if streamer.use_buffer else 0,
                recording_active=streamer.recording_triggered
            )
            time.sleep(0.1)
            
        # Trigger recording
        print("\nTriggering recording...")
        os.system("curl -d 'Start Recording' ntfy.sh/raspie-camera-test")
        
        # Wait for recording duration
        print(f"\nRecording for {args.record_duration} seconds...")
        start_time = time.time()
        while time.time() - start_time < args.record_duration:
            # Update status
            status.update(
                frame_count=streamer.frame_count,
                frames_written=streamer.frames_written_count,
                frames_dropped=streamer.frames_dropped_count,
                buffer_size=streamer.buffer.get_buffer_size() if streamer.use_buffer else 0,
                recording_active=streamer.recording_triggered
            )
            time.sleep(0.1)
            
        # Stop recording
        print("\nStopping recording...")
        os.system("curl -d 'Stop Recording' ntfy.sh/raspie-camera-test")
        
        # Wait for remaining test duration
        remaining_time = args.test_duration - (args.trigger_delay + args.record_duration)
        if remaining_time > 0:
            print(f"\nWaiting {remaining_time} seconds before stopping...")
            start_time = time.time()
            while time.time() - start_time < remaining_time:
                # Update status
                status.update(
                    frame_count=streamer.frame_count,
                    frames_written=streamer.frames_written_count,
                    frames_dropped=streamer.frames_dropped_count,
                    buffer_size=streamer.buffer.get_buffer_size() if streamer.use_buffer else 0,
                    recording_active=streamer.recording_triggered
                )
                time.sleep(0.1)
                
        # Print final statistics
        print("\nTest completed!")
        print(f"Frames captured: {streamer.frame_count}")
        print(f"Frames written: {streamer.frames_written_count}")
        print(f"Frames dropped: {streamer.frames_dropped_count}")
        
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
        
    finally:
        # Stop status display
        status.stop()
        
        # Stop camera streamer
        if 'streamer' in locals():
            streamer.stop()
            
if __name__ == "__main__":
    main() 