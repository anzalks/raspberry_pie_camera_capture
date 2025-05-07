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

def setup_audio_parser(subparsers):
    """Set up the argument parser for audio capture."""
    audio_parser = subparsers.add_parser(
        'audio', 
        help='Capture audio from USB microphone'
    )
    
    # Basic audio settings
    audio_parser.add_argument('--device', type=str, default='default',
                          help='Audio device name or index (default: auto-detect)')
    audio_parser.add_argument('--sample-rate', type=int, default=44100,
                          help='Audio sample rate in Hz (default: 44100)')
    audio_parser.add_argument('--channels', type=int, default=1,
                          help='Number of audio channels (1=mono, 2=stereo) (default: 1)')
    audio_parser.add_argument('--bit-depth', type=int, default=16, choices=[16, 24, 32],
                          help='Audio bit depth (default: 16)')
    audio_parser.add_argument('--chunk-size', type=int, default=1024,
                          help='Audio chunk size in samples (default: 1024)')
    
    # Storage options
    audio_parser.add_argument('--save-audio', action='store_true',
                          help='Save audio to file')
    audio_parser.add_argument('--output-dir', type=str, default='recordings/audio',
                          help='Directory to save recordings (default: recordings/audio)')
    audio_parser.add_argument('--audio-format', type=str, default='wav', choices=['wav'],
                          help='Audio format (default: wav)')
    
    # Buffer settings
    audio_parser.add_argument('--no-buffer', action='store_true',
                          help='Disable pre-trigger buffer')
    audio_parser.add_argument('--buffer-size', type=float, default=20.0,
                          help='Pre-trigger buffer size in seconds (default: 20.0)')
    
    # Remote control
    audio_parser.add_argument('--ntfy-topic', type=str, default='raspie-camera-test',
                          help='Topic for ntfy.sh notifications (default: raspie-camera-test)')
    
    # Visualization
    audio_parser.add_argument('--show-preview', action='store_true',
                          help='Show audio visualization window')
    
    # CPU affinity options
    audio_parser.add_argument('--capture-cpu-core', type=int,
                          help='CPU core to use for capture thread')
    audio_parser.add_argument('--writer-cpu-core', type=int,
                          help='CPU core to use for writer thread')
    audio_parser.add_argument('--visualizer-cpu-core', type=int,
                          help='CPU core to use for visualizer thread')
    
    # Register the function to handle this command
    audio_parser.set_defaults(func=handle_audio_command)

def handle_audio_command(args):
    """Handle the audio capture command."""
    # Import here for faster CLI responsiveness
    from .audio_stream import LSLAudioStreamer
    from .buffer_trigger import NtfySubscriber
    
    import signal
    import datetime
    import os
    
    # Signal handler for clean shutdown
    running = True
    
    def signal_handler(sig, frame):
        nonlocal running
        print("\nStopping audio capture...")
        running = False
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Create output directory with date structure if needed
    if args.save_audio:
        today = datetime.datetime.now().strftime("%Y_%m_%d")
        base_dir = args.output_dir
        
        # Check if we need to create the date structure
        if not os.path.basename(base_dir).startswith("20"):  # Not already a date folder
            base_dir = os.path.join(base_dir, today)
        
        os.makedirs(base_dir, exist_ok=True)
        args.output_dir = base_dir  # Update the path
        print(f"Audio will be saved to: {base_dir}")
    
    # Create audio streamer
    audio = LSLAudioStreamer(
        sample_rate=args.sample_rate,
        channels=args.channels,
        device_index=args.device,
        stream_name='RaspieAudio',
        output_path=args.output_dir if args.save_audio else None,
        bit_depth=args.bit_depth,
        buffer_size_seconds=args.buffer_size,
        use_buffer=not args.no_buffer,
        chunk_size=args.chunk_size,
        save_audio=args.save_audio,
        audio_format=args.audio_format,
        show_preview=args.show_preview,
        capture_cpu_core=args.capture_cpu_core,
        writer_cpu_core=args.writer_cpu_core,
        visualizer_cpu_core=args.visualizer_cpu_core
    )
    
    # Set up ntfy subscriber for remote control
    ntfy_subscriber = None
    
    def ntfy_callback(message):
        msg_text = message.get('message', '').lower()
        print(f"Received notification: {msg_text}")
        
        if 'start recording' in msg_text or 'start' in msg_text:
            print("Starting audio recording")
            audio.start_recording()
        elif 'stop recording' in msg_text or 'stop' in msg_text:
            print("Stopping audio recording")
            audio.stop_recording()
    
    if args.ntfy_topic:
        try:
            from .buffer_trigger import NtfySubscriber
            ntfy_subscriber = NtfySubscriber(
                args.ntfy_topic,
                ntfy_callback
            )
            ntfy_subscriber.start()
            print(f"Listening for commands on ntfy topic: {args.ntfy_topic}")
        except Exception as e:
            print(f"Failed to set up ntfy subscriber: {e}")
    
    # Start audio capture
    try:
        print("Starting audio capture")
        audio.start()
        
        # Main loop - wait for interruption or error
        while running:
            time.sleep(0.1)
    except Exception as e:
        print(f"Error in audio capture: {e}")
    finally:
        print("Stopping audio capture")
        audio.stop()
        if ntfy_subscriber:
            ntfy_subscriber.stop()

def main():
    """Main entry point for the CLI."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Raspberry Pi Camera and Audio Capture')
    subparsers = parser.add_subparsers(dest='command', help='Command to run')
    
    # Set up parsers for each command
    setup_camera_parser(subparsers)
    setup_view_parser(subparsers)
    setup_audio_parser(subparsers)
    setup_convert_parser(subparsers)
    
    args = parser.parse_args()
    
    # If no command specified, show help
    if not hasattr(args, 'func'):
        parser.print_help()
        return
    
    # Execute the command function
    args.func(args)

# Standard Python entry point check
if __name__ == '__main__':
    main() 