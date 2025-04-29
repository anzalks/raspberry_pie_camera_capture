"""Command-line interface for the Raspberry Pi LSL stream."""

import argparse
import sys
import signal
import time  # Import time for the loop sleep
import atexit # Import atexit for cleanup registration
import os # Import os for file existence check
import threading # <<< Import threading
# from .camera_stream import stream_camera # Relative import <- Remove old import
from .camera_stream import LSLCameraStreamer # <-- Import the class
from ._version import __version__
from .verify_video import verify_video # <<< Import the verification function

def _status_updater_loop(start_time, stop_event):
    """Target function for the status update thread."""
    while not stop_event.is_set():
        current_time = time.time()
        elapsed_total_seconds = current_time - start_time
        minutes = int(elapsed_total_seconds // 60)
        seconds = int(elapsed_total_seconds % 60)
        
        status_text = f"Running for: {minutes:02d}:{seconds:02d}"
        # Print status, padding with spaces to overwrite previous line, use \r
        print(f"{status_text:<70}", end='\r') 
        
        # Wait for 1 second or until stop_event is set
        stop_event.wait(timeout=1.0)
    # Clear the status line one last time upon exit
    print(" " * 70, end='\r')

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
    # Explicit camera selection
    parser.add_argument('--camera-index', type=str, default='auto',
                        help="Camera to use: 'auto' (default: PiCam then Webcams), 'pi' (PiCam only), or an integer index (e.g., 0, 1) for a specific webcam.")
    # Output configuration
    parser.add_argument('--output-path', type=str, default=None,
                        help='Directory path to save the output video file. Defaults to the current directory.')
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
    # Add the flag back
    parser.add_argument('--threaded-writer', action='store_true', 
                        help='Use a separate thread for writing video frames (recommended for high resolution/fps).')
    # Other arguments
    parser.add_argument('--version', action='version', version=f'%(prog)s {__version__}')

    # Parse the arguments provided by the user
    args = parser.parse_args()

    # --- Initial Information Output ---
    print(f"Starting LSL stream '{args.stream_name}'...")

    streamer = None # Initialize streamer variable for cleanup in finally block
    status_thread = None # Initialize status thread variable
    stop_event = threading.Event() # Event to signal threads to stop

    # Define a signal handler for graceful shutdown on Ctrl+C (SIGINT) or termination (SIGTERM).
    def signal_handler(sig, frame):
        print(f'\nCaught signal {sig}, initiating shutdown...')
        stop_event.set() # <<< Signal status thread to stop
        # Let the finally block handle streamer.stop() and thread join
        # if streamer: 
        #     streamer.stop() 
        # sys.exit(0) # Let the main thread exit naturally after the loop breaks

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
            use_max_settings=args.use_max_settings,
            threaded_writer=args.threaded_writer,
            output_path=args.output_path, # Pass the output path argument
            camera_index=args.camera_index # <<< Pass the camera index
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
        
        # --- Start Status Updater Thread ---
        start_time = time.time() # Record start time
        status_thread = threading.Thread(
            target=_status_updater_loop, 
            args=(start_time, stop_event)
        )
        status_thread.start()
        # ---

        print("\nStreaming frames... Press Ctrl+C to stop (or wait for duration if set).")

        # --- Main Capture Loop ---
        # Continuously capture frames and push them to LSL until interrupted or duration expires.
        # REMOVED: start_time = time.time()
        # REMOVED: last_status_update_time = start_time
        # REMOVED: frames_in_last_second = 0
        # REMOVED: current_loop_fps = 0.0
        
        while not stop_event.is_set(): # <<< Check stop_event here
            # --- Duration Check --- 
            if args.duration is not None:
                current_time_for_duration = time.time() # Need current time here
                elapsed_time = current_time_for_duration - start_time
                if elapsed_time >= args.duration:
                    print(f"\nDuration of {args.duration} seconds reached. Stopping...")
                    stop_event.set() # <<< Signal stop
                    break # Exit the loop
            # ---
            
            # Capture a frame and get its LSL timestamp.
            # Add timeout to capture_frame call if possible? Or handle blocking differently?
            # For now, assume capture_frame might block, but check stop_event frequently.
            frame, timestamp = streamer.capture_frame()
            
            # Check if capture failed (e.g., stream stopped, error)
            if frame is None and not stop_event.is_set(): # Only print if not already stopping
                print() 
                print("Capture frame returned None, stream might have stopped or errored. Exiting loop.")
                stop_event.set() # <<< Signal stop
                break # Exit the loop cleanly
            elif frame is None and stop_event.is_set():
                 # Expected if stopping, just break
                 break
                 
            # --- Status Update REMOVED from here --- 

            # Optional: A small sleep could be added if the main loop is too tight 
            #           when capture_frame doesn't block sufficiently.
            # time.sleep(0.001) 

    except KeyboardInterrupt:
        # Signal handler should catch this first and set the event
        print("\nKeyboardInterrupt caught (main loop), ensuring stop.") 
        stop_event.set()
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
        print() # Ensure newline before final messages
        end_time = time.time() # <<< Record end time
        
        # Ensure stop_event is set for threads
        stop_event.set()
        
        # Stop and join the status thread
        if status_thread is not None:
            print("Stopping status updater thread...")
            status_thread.join(timeout=1.5) # Wait for thread to finish
            if status_thread.is_alive():
                print("Warning: Status thread did not exit cleanly.")
        
        output_filename = None # Store filename for verification later
        if streamer:
            print("\nStopping stream and cleaning up resources...")
            # Get stats *before* calling stop, as stop might alter them or cleanup objects
            # Note: frame_count includes frames attempted, not necessarily written/pushed
            output_filename = streamer.auto_output_filename # Get filename before stop potentially clears it
            total_frames_processed = streamer.get_frame_count()
            frames_written = streamer.get_frames_written()
            frames_dropped = streamer.get_frames_dropped()
            threaded = streamer.threaded_writer # Store threading state
            
            # Ensure the streamer's stop method is called to release resources.
            streamer.stop() 
            
            # Report statistics
            print("\n--- Stream Statistics ---")
            
            # Timing Info
            total_run_duration = end_time - start_time
            minutes = int(total_run_duration // 60)
            seconds = total_run_duration % 60
            print(f"Total Run Time: {minutes}m {seconds:.2f}s") # <<< Add Total Run Time
            print("-") # Separator
            
            # Threading Info
            if threaded:
                print("Threading: Enabled (Main thread: Capture/LSL/Queue, Writer thread: Video Save)")
                print(f"Application Threads Primarily Used: 2")
            else:
                print("Threading: Disabled (Main thread: Capture/LSL/Video Save)")
                print(f"Application Threads Primarily Used: 1")
                
            print("-") # Separator
            
            # Frame Counts
            print(f"Frames processed by capture loop (Main Thread): {total_frames_processed}")
            if threaded:
                print(f"Frames successfully written to file (Writer Thread): {frames_written}")
                print(f"Frames dropped due to full queue (Main Thread): {frames_dropped}")
                if total_frames_processed > 0:
                    dropped_percentage = (frames_dropped / total_frames_processed) * 100
                    print(f"Dropped percentage: {dropped_percentage:.2f}%")
                else:
                    print("Dropped percentage: N/A")
            else: # Non-threaded
                print(f"Frames successfully written to file (Main Thread): {frames_written}")
                # Drop count is not applicable/tracked in non-threaded mode
                
            print("------------------------")
            
            # --- Automatic Video Verification ---
            if output_filename and os.path.exists(output_filename):
                print("\nVerifying saved video file...")
                verify_video(output_filename) # Call the verification function
            elif output_filename:
                print(f"\nWarning: Output file '{output_filename}' not found. Skipping verification.")
            # ---
            
        else:
            # Handle cases where the streamer object wasn't successfully created.
            print("Stream process finished (streamer was not initialized).")

# Standard Python entry point check: ensures main() runs only when script is executed directly.
if __name__ == '__main__':
    main() 