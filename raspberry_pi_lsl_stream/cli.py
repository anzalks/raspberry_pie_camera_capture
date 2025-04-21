"""Command-line interface for the Raspberry Pi LSL stream."""

import argparse
import sys
import signal
import time  # Import time for the loop sleep
import atexit # Import atexit for cleanup registration
# from .camera_stream import stream_camera # Relative import <- Remove old import
from .camera_stream import LSLCameraStreamer # <-- Import the class
from ._version import __version__

def main():
    """Parses command-line arguments, sets up the streamer, and runs the capture loop."""
    # --- Argument Parsing ---
    # Use argparse to define and parse command-line options.
    # ArgumentDefaultsHelpFormatter shows default values in the --help message.
    parser = argparse.ArgumentParser(
        description=f'Stream Raspberry Pi camera data via LSL (v{__version__}).',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    # Camera/Stream configuration arguments
    parser.add_argument('--width', type=int, default=640, help='Video width')
    parser.add_argument('--height', type=int, default=480, help='Video height')
    parser.add_argument('--fps', type=int, default=30, help='Frames per second')
    parser.add_argument('--format', type=str, default='RGB888',
                        help='Camera pixel format (e.g., RGB888, XBGR8888, YUV420) - PiCam only')
    # LSL configuration arguments
    parser.add_argument('--stream-name', type=str, default='RaspberryPiCamera',
                        help='LSL stream name')
    parser.add_argument('--source-id', type=str, default='RPiCam_UniqueID',
                        help='Unique LSL source ID')
    # Video saving is automatic now
    parser.add_argument('--show-preview', action='store_true',
                        help='Show a live preview window (using OpenCV). Requires graphical environment.')
    parser.add_argument('--use-max-settings', action='store_true',
                        help='[Webcam Only] Attempt to use the highest resolution and FPS reported by the webcam. Overrides --width, --height, --fps.')
    parser.add_argument('--duration', type=int, default=None,
                        help='Record for a fixed duration (in seconds) then stop automatically.')
    # Other arguments
    parser.add_argument('--version', action='version', version=f'%(prog)s {__version__}')

    # Parse the arguments provided by the user
    args = parser.parse_args()

    # --- Initial Information Output ---
    print(f"Starting LSL stream '{args.stream_name}'...")

    streamer = None # Initialize streamer variable for cleanup in finally block

    # Define a signal handler for graceful shutdown on Ctrl+C (SIGINT) or termination (SIGTERM).
    def signal_handler(sig, frame):
        print(f'\nCaught signal {sig}, initiating shutdown...')
        if streamer:
            # Call the streamer's stop method to release camera and LSL resources.
            streamer.stop() 
        sys.exit(0) # Exit cleanly

    # Register the signal handler for SIGINT and SIGTERM.
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # Instantiate the LSLCameraStreamer with parsed arguments.
        # This will initialize the camera and LSL stream.
        streamer = LSLCameraStreamer(
            width=args.width,
            height=args.height,
            fps=args.fps,
            pixel_format=args.format, # Note: format is mostly relevant for PiCamera
            stream_name=args.stream_name,
            source_id=args.source_id,
            show_preview=args.show_preview,
            use_max_settings=args.use_max_settings
        )
        
        # Register the streamer stop method to be called on normal/exception exit
        # This provides an extra layer of cleanup attempts.
        # Note: Does NOT handle abrupt external kills (SIGKILL, power loss).
        atexit.register(streamer.stop)

        # Get and print the actual configuration reported by the streamer
        # (camera might have adjusted width, height, fps).
        stream_info = streamer.get_info()
        print(f"Actual Stream Config: {stream_info['width']}x{stream_info['height']} @ {stream_info['actual_fps']:.2f}fps")
        print(f"LSL Info: Name='{stream_info['stream_name']}', SourceID='{stream_info['source_id']}'")
        print(f"Camera Model: {stream_info['camera_model']}")

        # Start the camera capture process (e.g., picam2.start()).
        streamer.start()

        print("\nStreaming frames... Press Ctrl+C to stop (or wait for duration if set).")

        # --- Main Capture Loop ---
        # Continuously capture frames and push them to LSL until interrupted or duration expires.
        start_time = time.time() # Record start time for duration check
        while True:
            # --- Duration Check --- 
            if args.duration is not None:
                elapsed_time = time.time() - start_time
                if elapsed_time >= args.duration:
                    print(f"\nDuration of {args.duration} seconds reached. Stopping...")
                    break # Exit the loop
            # ---
            
            # Capture a frame and get its LSL timestamp.
            frame, timestamp = streamer.capture_frame()
            
            # Check if capture failed (e.g., stream stopped, error)
            if frame is None:
                print("Capture frame returned None, stream might have stopped or errored. Exiting loop.")
                break # Exit the loop cleanly

            # Optional: A small sleep can be added here if the loop consumes too much CPU,
            # especially if the camera's frame rate is very high or capture is very fast.
            # However, ideally, the blocking nature of capture_frame or LSL push
            # should regulate the loop speed close to the actual frame rate.
            # time.sleep(0.001) 

    except KeyboardInterrupt:
        # This block catches Ctrl+C if the signal handler doesn't exit first.
        # The signal handler should ideally handle the stop call.
        print("KeyboardInterrupt caught (likely via signal handler), stopping.")
    except RuntimeError as e:
        # Catch specific errors raised during streamer initialization or runtime 
        # (e.g., camera not found, OS incompatibility).
        print(f"Runtime Error: {e}", file=sys.stderr)
        sys.exit(1) # Exit with a non-zero code to indicate error
    except Exception as e:
        # Catch any other unexpected errors during the process.
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc() # Print the full traceback for debugging
        sys.exit(1) # Exit with error code
    finally:
        # --- Cleanup ---
        # This block executes whether the loop finished normally, was interrupted,
        # or an exception occurred (unless it was sys.exit).
        if streamer:
            print("\nStopping stream and cleaning up resources...")
            # Get the final frame count before stopping.
            final_frame_count = streamer.get_frame_count()
            # Ensure the streamer's stop method is called to release resources.
            streamer.stop() 
            print(f"Stream stopped. Total frames pushed: {final_frame_count}")
        else:
            # Handle cases where the streamer object wasn't successfully created.
            print("Stream process finished (streamer was not initialized).")

# Standard Python entry point check: ensures main() runs only when script is executed directly.
if __name__ == '__main__':
    main() 