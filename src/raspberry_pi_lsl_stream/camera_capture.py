#!/usr/bin/env python3
"""
Main script for camera capture and streaming.
"""

import os
import sys
import time
import signal
import argparse
from .camera_stream import LSLCameraStreamer, StatusDisplay

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Camera capture and streaming")
    
    # Camera settings
    parser.add_argument("--camera-id", type=int, default=0,
                       help="Camera index or ID to use")
    parser.add_argument("--width", type=int, default=640,
                       help="Frame width")
    parser.add_argument("--height", type=int, default=480,
                       help="Frame height")
    parser.add_argument("--fps", type=float, default=30.0,
                       help="Target frame rate")
                       
    # Recording settings
    parser.add_argument("--save-video", action="store_true",
                       help="Save video files")
    parser.add_argument("--output-dir", type=str, default="recordings",
                       help="Directory to save recordings")
    parser.add_argument("--codec", type=str, default="auto",
                       choices=["auto", "h264", "h265", "mjpg"],
                       help="Video codec to use")
                       
    # Display settings
    parser.add_argument("--no-preview", action="store_true",
                       help="Disable preview window")
                       
    # LSL settings
    parser.add_argument("--no-lsl", action="store_true",
                       help="Disable LSL streaming")
    parser.add_argument("--stream-name", type=str, default="camera_stream",
                       help="LSL stream name")
                       
    # Buffer settings
    parser.add_argument("--no-buffer", action="store_true",
                       help="Disable buffer trigger system")
    parser.add_argument("--buffer-size", type=float, default=5.0,
                       help="Buffer size in seconds")
    parser.add_argument("--ntfy-topic", type=str, default="raspie-camera-test",
                       help="Topic for ntfy notifications")
                       
    return parser.parse_args()

def handle_ntfy_notification(status, message):
    """Handle ntfy notification."""
    if isinstance(message, dict):
        msg_text = message.get('message', '')
    else:
        msg_text = str(message)
        
    status.notify(msg_text)

def main():
    """Main function."""
    # Parse arguments
    args = parse_args()
    
    # Create output directory
    if args.save_video:
        os.makedirs(args.output_dir, exist_ok=True)
        
    print(f"Starting Raspberry Pi Camera Capture")
    print(f"Camera: ID {args.camera_id}, {args.width}x{args.height} @ {args.fps}fps")
    print(f"NTFY Topic: {args.ntfy_topic}")
    print(f"Output Directory: {args.output_dir}")
    print(f"Press Ctrl+C to exit")
    print("\nInitializing...")
        
    # Initialize status display
    status = StatusDisplay()
    status.start()
    
    try:
        # Initialize camera streamer
        streamer = LSLCameraStreamer(
            camera_id=args.camera_id,
            width=args.width,
            height=args.height,
            target_fps=args.fps,
            save_video=args.save_video,
            output_path=args.output_dir if args.save_video else None,
            codec=args.codec,
            show_preview=not args.no_preview,
            push_to_lsl=not args.no_lsl,
            stream_name=args.stream_name,
            use_buffer=not args.no_buffer,
            buffer_size_seconds=args.buffer_size,
            ntfy_topic=args.ntfy_topic
        )
        
        # Set up notification handler
        if streamer.buffer_trigger_manager:
            streamer.buffer_trigger_manager.ntfy_subscriber.callback = lambda msg: handle_ntfy_notification(status, msg)
        
        # Start camera streamer
        streamer.start()
        status.notify("Camera streamer started")
        
        # Main loop
        while True:
            try:
                # Get buffer duration if available
                buffer_duration = 0.0
                if streamer.use_buffer and streamer.buffer:
                    buffer_duration = streamer.buffer.get_buffer_duration()
                
                # Get resolution string
                resolution = f"{streamer.width}x{streamer.height}"
                
                # Update status
                status.update(
                    frame_count=streamer.frame_count,
                    frames_written=streamer.frames_written_count,
                    frames_dropped=streamer.frames_dropped_count,
                    buffer_size=streamer.buffer.get_buffer_size() if streamer.use_buffer and streamer.buffer else 0,
                    buffer_duration=buffer_duration,
                    recording_active=streamer.recording_triggered,
                    camera_model=streamer.camera_model,
                    resolution=resolution,
                    ntfy_topic=args.ntfy_topic
                )
                
                # Sleep to prevent tight loop
                time.sleep(0.1)
                
            except KeyboardInterrupt:
                status.notify("Stopping due to keyboard interrupt...")
                break
                
    except Exception as e:
        status.notify(f"Error: {e}")
        print(f"Error: {e}")
        sys.exit(1)
        
    finally:
        # Stop camera streamer
        if 'streamer' in locals():
            streamer.stop()
            
        # Stop status display
        status.stop()
        print("\nCamera capture stopped")
            
if __name__ == "__main__":
    main() 