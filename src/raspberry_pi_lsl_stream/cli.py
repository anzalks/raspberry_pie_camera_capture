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
from .audio_stream import LSLAudioStreamer # <-- Import audio streamer
from ._version import __version__
from .verify_video import verify_video # <<< Import the verification function

def _status_updater_loop(start_time, stop_event):
    """Target function for the status update thread."""
    while not stop_event.is_set():
        current_time = time.time()
        elapsed_total_seconds = current_time - start_time
        # Calculate hours, minutes, seconds
        hours = int(elapsed_total_seconds // 3600)
        minutes = int((elapsed_total_seconds % 3600) // 60)
        seconds = int(elapsed_total_seconds % 60)
        
        # Format to HH:MM:SS
        status_text = f"Running for: {hours:02d}:{minutes:02d}:{seconds:02d}"
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
    
    # Camera/Video configuration arguments
    video_group = parser.add_argument_group('Video Capture Options')
    video_group.add_argument('--width', type=int, default=400, help='Video width')
    video_group.add_argument('--height', type=int, default=400, help='Video height')
    video_group.add_argument('--fps', type=int, default=100, help='Frames per second')
    video_group.add_argument('--format', type=str, default='RGB888',
                        help='Camera pixel format (e.g., RGB888, XBGR8888, YUV420) - PiCam only')
    # Explicit camera selection
    video_group.add_argument('--camera-index', type=str, default='auto',
                        help="Camera to use: 'auto' (default: PiCam then Webcams), 'pi' (PiCam only), or an integer index (e.g., 0, 1) for a specific webcam.")
    # Add encoding options
    video_group.add_argument('--codec', type=str, default='auto',
                       help="Preferred video codec ('h264', 'h265', 'mjpg', 'auto'). Default 'auto' attempts hardware-accelerated codecs first.")
    video_group.add_argument('--bitrate', type=int, default=0,
                       help="Constant bitrate in Kbps (0=codec default). Setting this enables CBR mode.")
    video_group.add_argument('--quality-preset', type=str, default='medium',
                       choices=['ultrafast', 'superfast', 'veryfast', 'faster', 'fast', 'medium', 'slow', 'slower', 'veryslow'],
                       help="Encoding quality preset (trade-off between speed and compression efficiency).")
    # Video preview and max settings
    video_group.add_argument('--show-preview', action='store_true',
                        help='Show a live preview window (using OpenCV). Requires graphical environment.')
    video_group.add_argument('--use-max-settings', action='store_true',
                        help='[Webcam Only] Attempt to use the highest resolution and FPS reported by the webcam. Overrides --width, --height, --fps.')
    video_group.add_argument('--threaded-writer', action='store_true', 
                        help='Use a separate thread for writing video frames (recommended for high resolution/fps).')
    video_group.add_argument('--no-save-video', action='store_true', 
                        help='Disable saving video to file (keeps LSL).')
    
    # Audio capture options
    audio_group = parser.add_argument_group('Audio Capture Options')
    audio_group.add_argument('--enable-audio', action='store_true',
                         help='Enable audio capture from USB microphone.')
    audio_group.add_argument('--audio-device', type=str, default=None,
                         help='Audio device index or name (default: auto-detect first input device).')
    audio_group.add_argument('--sample-rate', type=int, default=48000,
                         help='Audio sampling rate in Hz.')
    audio_group.add_argument('--channels', type=int, default=1,
                         help='Number of audio channels (1=mono, 2=stereo).')
    audio_group.add_argument('--bit-depth', type=int, default=16, choices=[16, 24, 32],
                         help='Audio bit depth (16, 24, or 32 bits).')
    audio_group.add_argument('--chunk-size', type=int, default=1024,
                         help='Audio processing chunk size.')
    audio_group.add_argument('--no-save-audio', action='store_true',
                         help='Disable saving audio to file (keeps LSL).')
    audio_group.add_argument('--threaded-audio-writer', action='store_true', default=True,
                         help='Use a separate thread for writing audio chunks.')
    audio_group.add_argument('--show-audio-preview', action='store_true',
                         help='Show audio visualization window with waveform and spectrum display.')
    
    # Output configuration
    output_group = parser.add_argument_group('Output Options')
    output_group.add_argument('--output-path', type=str, default='recordings',
                        help='Directory path to save the output files. Defaults to the "recordings" folder.')
    output_group.add_argument('--duration', type=int, default=None,
                        help='Record for a fixed duration (in seconds) then stop automatically.')
    
    # LSL configuration arguments
    lsl_group = parser.add_argument_group('LSL Options')
    lsl_group.add_argument('--video-stream-name', type=str, default='RaspieVideo',
                        help='LSL stream name for video frames')
    lsl_group.add_argument('--audio-stream-name', type=str, default='RaspieAudio',
                        help='LSL stream name for audio chunks')
    lsl_group.add_argument('--source-id', type=str, default='RaspieCapture',
                        help='Base LSL source ID (will be suffixed with _Video or _Audio)')
    lsl_group.add_argument('--no-lsl', action='store_true', 
                        help='Disable pushing data to LSL.')
    
    # Add buffer and trigger options
    buffer_group = parser.add_argument_group('Buffer and Trigger Options')
    buffer_group.add_argument('--use-buffer', action='store_true', default=True,
                             help='Enable rolling buffer mode to capture frames before trigger.')
    buffer_group.add_argument('--buffer-size', type=int, default=20,
                             help='Size of the rolling buffer in seconds (default: 20).')
    buffer_group.add_argument('--ntfy-topic', type=str, default="rpi_camera_trigger",
                             help='The ntfy.sh topic to subscribe to for recording triggers (default: rpi_camera_trigger).')
    buffer_group.add_argument('--no-ntfy', action='store_true',
                             help='Disable ntfy notifications and use manual triggering only.')
    
    # Add CPU core options under a new argument group
    core_group = parser.add_argument_group('CPU Core Affinity Options')
    core_group.add_argument('--video-capture-core', type=int, default=None,
                        help='Specific CPU core for video capture operations (requires psutil).')
    core_group.add_argument('--video-writer-core', type=int, default=None,
                        help='Specific CPU core for video writer thread (requires psutil).')
    core_group.add_argument('--video-vis-core', type=int, default=None,
                        help='Specific CPU core for video visualization (requires psutil).')
    core_group.add_argument('--audio-capture-core', type=int, default=None,
                        help='Specific CPU core for audio capture operations (requires psutil).')
    core_group.add_argument('--audio-writer-core', type=int, default=None,
                        help='Specific CPU core for audio writer thread (requires psutil).')
    core_group.add_argument('--audio-vis-core', type=int, default=None,
                        help='Specific CPU core for audio visualization (requires psutil).')
    
    # Other arguments
    parser.add_argument('--version', action='version', version=f'%(prog)s {__version__}')

    # Parse the arguments provided by the user
    args = parser.parse_args()

    # --- Initial Information Output ---
    print(f"Starting capture with LSL streaming...")

    # Initialize objects to None for cleanup
    video_streamer = None
    audio_streamer = None
    status_thread = None
    stop_event = threading.Event()

    # Define a signal handler for graceful shutdown
    def signal_handler(sig, frame):
        print(f'\nCaught signal {sig}, initiating shutdown...')
        stop_event.set()

    # Register the signal handler for SIGINT and SIGTERM
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # Initialize video streamer
        video_streamer = LSLCameraStreamer(
            width=args.width,
            height=args.height,
            fps=args.fps,
            pixel_format=args.format,
            stream_name=args.video_stream_name,
            source_id=f"{args.source_id}_Video",
            show_preview=args.show_preview,
            use_max_settings=args.use_max_settings,
            output_path=args.output_path,
            camera_index=args.camera_index,
            save_video=not args.no_save_video,
            codec=args.codec,
            bitrate=args.bitrate,
            quality_preset=args.quality_preset,
            buffer_size_seconds=args.buffer_size,
            use_buffer=args.use_buffer,
            ntfy_topic=None if args.no_ntfy else args.ntfy_topic,
            push_to_lsl=not args.no_lsl,
            threaded_writer=args.threaded_writer,
            capture_cpu_core=args.video_capture_core,
            writer_cpu_core=args.video_writer_core,
            visualizer_cpu_core=args.video_vis_core
        )
        
        # Register the video streamer stop method to be called on exit
        atexit.register(video_streamer.stop)

        # Initialize audio streamer if enabled
        if args.enable_audio:
            try:
                audio_streamer = LSLAudioStreamer(
                    sample_rate=args.sample_rate,
                    channels=args.channels,
                    device_index=args.audio_device,
                    stream_name=args.audio_stream_name,
                    source_id=f"{args.source_id}_Audio",
                    output_path=args.output_path,
                    bit_depth=args.bit_depth,
                    buffer_size_seconds=args.buffer_size,
                    use_buffer=args.use_buffer,
                    chunk_size=args.chunk_size,
                    threaded_writer=args.threaded_audio_writer,
                    save_audio=not args.no_save_audio,
                    show_preview=args.show_audio_preview,
                    capture_cpu_core=args.audio_capture_core,
                    writer_cpu_core=args.audio_writer_core,
                    visualizer_cpu_core=args.audio_vis_core
                )
                
                # Register the audio streamer stop method to be called on exit
                atexit.register(audio_streamer.stop)
            except Exception as e:
                print(f"Audio initialization error: {e}")
                print("Continuing with video only")
                audio_streamer = None

        # Print configuration information
        video_info = video_streamer.get_info()
        print(f"\nVideo Configuration:")
        print(f"  Resolution: {video_info['width']}x{video_info['height']}")
        print(f"  Frame Rate: {video_info['actual_fps']:.2f} fps")
        print(f"  Camera: {video_info['camera_model']}")
        print(f"  Buffer Mode: {'Enabled' if args.use_buffer else 'Disabled'}")
        
        if audio_streamer:
            audio_info = audio_streamer.get_info()
            print(f"\nAudio Configuration:")
            print(f"  Device: {audio_info['device_name']}")
            print(f"  Sample Rate: {audio_info['sample_rate']} Hz")
            print(f"  Channels: {audio_info['channels']}")
            print(f"  Bit Depth: {audio_info['bit_depth']} bits")
        
        if args.use_buffer:
            if args.ntfy_topic and not args.no_ntfy:
                print(f"\nTrigger Configuration:")
                print(f"  Notification Topic: {args.ntfy_topic}")
                print(f"  Buffer Size: {args.buffer_size} seconds")
                print("  Manual Trigger: Press 't' in preview window")
                print("  Manual Stop: Press 's' in preview window")
            else:
                print(f"\nTrigger Configuration:")
                print(f"  Mode: Manual only")
                print(f"  Buffer Size: {args.buffer_size} seconds")
                print("  Trigger: Press 't' in preview window")
                print("  Stop: Press 's' in preview window")

        # Start the capture processes
        print("\nStarting capture...")
        video_streamer.start()
        if audio_streamer:
            audio_streamer.start()
        
        # Start status updater thread
        start_time = time.time()
        status_thread = threading.Thread(
            target=_status_updater_loop, 
            args=(start_time, stop_event)
        )
        status_thread.start()

        print("\nCapture active. Press Ctrl+C to stop (or wait for duration if set).")

        # Define a function to handle synchronized start/stop for both streamers
        def handle_trigger_start():
            """Handle synchronized start of video and audio recording."""
            print("\nTriggered recording START")
            video_streamer.start_recording()
            if audio_streamer:
                audio_streamer.start_recording()

        def handle_trigger_stop():
            """Handle synchronized stop of video and audio recording."""
            print("\nTriggered recording STOP")
            video_streamer.stop_recording()
            if audio_streamer:
                audio_streamer.stop_recording()

        # Install the handler for video triggers to also control audio
        # Override the original handlers in the video streamer
        video_streamer._handle_trigger_callback = handle_trigger_start
        video_streamer._handle_stop_callback = handle_trigger_stop

        # Main capture loop
        while not stop_event.is_set():
            # Check for duration limit
            if args.duration is not None:
                current_time = time.time()
                elapsed_time = current_time - start_time
                if elapsed_time >= args.duration:
                    print(f"\nDuration of {args.duration} seconds reached. Stopping...")
                    stop_event.set()
                    break
            
            # Capture video frame
            frame, timestamp = video_streamer.capture_frame()
            
            # Check if capture failed
            if frame is None and not stop_event.is_set():
                print("\nCapture frame returned None, stream might have stopped or errored.")
                stop_event.set()
                break
            elif frame is None and stop_event.is_set():
                break

    except KeyboardInterrupt:
        print("\nKeyboardInterrupt caught, stopping...")
        stop_event.set()
    except RuntimeError as e:
        print(f"Runtime Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        # Cleanup
        print()  # Ensure newline before final messages
        end_time = time.time()
        
        # Set stop event for threads
        stop_event.set()
        
        # Stop status thread
        if status_thread and status_thread.is_alive():
            print("Stopping status updater thread...")
            status_thread.join(timeout=1.5)
            if status_thread.is_alive():
                print("Warning: Status thread did not exit cleanly.")
        
        # Stop video streamer and report stats
        if video_streamer:
            print("\nStopping video stream...")
            video_filename = video_streamer.auto_output_filename
            video_frames_processed = video_streamer.get_frame_count()
            video_frames_written = video_streamer.get_frames_written()
            video_frames_dropped = video_streamer.get_frames_dropped()
            video_threaded = video_streamer.threaded_writer
            
            video_streamer.stop()
            
            print("\n--- Video Statistics ---")
            print(f"Frames processed: {video_frames_processed}")
            print(f"Frames written: {video_frames_written}")
            if video_threaded:
                print(f"Frames dropped: {video_frames_dropped}")
                if video_frames_processed > 0:
                    dropped_percentage = (video_frames_dropped / video_frames_processed) * 100
                    print(f"Dropped percentage: {dropped_percentage:.2f}%")
            
            # Verify video file if it exists
            if video_filename and os.path.exists(video_filename):
                print("\nVerifying saved video file...")
                verify_video(video_filename)
        
        # Stop audio streamer and report stats
        if audio_streamer:
            print("\nStopping audio stream...")
            audio_filename = audio_streamer.auto_output_filename
            audio_chunks_processed = audio_streamer.get_frame_count()
            audio_chunks_written = audio_streamer.get_frames_written()
            audio_chunks_dropped = audio_streamer.get_frames_dropped()
            
            audio_streamer.stop()
            
            print("\n--- Audio Statistics ---")
            print(f"Audio chunks processed: {audio_chunks_processed}")
            print(f"Audio chunks written: {audio_chunks_written}")
            print(f"Audio chunks dropped: {audio_chunks_dropped}")
            if audio_filename:
                print(f"Audio saved to: {audio_filename}")
        
        # Print total run time
        total_run_duration = end_time - start_time
        minutes = int(total_run_duration // 60)
        seconds = total_run_duration % 60
        print(f"\nTotal Run Time: {minutes}m {seconds:.2f}s")
        print("Capture completed.")

# Standard Python entry point check
if __name__ == '__main__':
    main() 