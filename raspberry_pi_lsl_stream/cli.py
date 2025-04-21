"""Command-line interface for the Raspberry Pi LSL stream."""

import argparse
import sys
import signal
from .camera_stream import stream_camera # Relative import
from ._version import __version__

def main():
    parser = argparse.ArgumentParser(
        description=f'Stream Raspberry Pi camera data via LSL (v{__version__}).',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter # Show defaults in help
    )
    parser.add_argument('--width', type=int, default=640, help='Video width')
    parser.add_argument('--height', type=int, default=480, help='Video height')
    parser.add_argument('--fps', type=int, default=30, help='Frames per second')
    parser.add_argument('--format', type=str, default='RGB888', 
                        help='Camera pixel format (e.g., RGB888, XBGR8888, YUV420)')
    parser.add_argument('--stream-name', type=str, default='RaspberryPiCamera',
                        help='LSL stream name')
    parser.add_argument('--source-id', type=str, default='RPiCam_UniqueID',
                        help='Unique LSL source ID')
    parser.add_argument('--version', action='version', version=f'%(prog)s {__version__}')
    parser.add_argument('--webcam', action='store_true', 
                        help='Use a standard USB webcam (via OpenCV) instead of PiCamera')

    args = parser.parse_args()

    print(f"Starting LSL stream '{args.stream_name}'...")
    if args.webcam:
        print("Using USB Webcam via OpenCV.")
    else:
        print("Using Raspberry Pi Camera via Picamera2.")
    print(f"Config: {args.width}x{args.height} @ {args.fps}fps, Format: {args.format if not args.webcam else 'BGR (implied)'}, Source ID: {args.source_id}")
    print("Press Ctrl+C to stop.")

    # Define a signal handler for graceful shutdown on SIGINT/SIGTERM
    def signal_handler(sig, frame):
        print(f'\nCaught signal {sig}, initiating shutdown...')
        # The stream_camera function handles its own cleanup in its finally block,
        # so we just need to let the KeyboardInterrupt exception propagate or exit.
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)  # Handle Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler) # Handle termination signals

    try:
        stream_camera(
            width=args.width,
            height=args.height,
            fps=args.fps,
            pixel_format=args.format,
            stream_name=args.stream_name,
            source_id=args.source_id,
            use_webcam=args.webcam
        )
    except Exception as e:
        print(f"Critical error during stream setup or execution: {e}", file=sys.stderr)
        sys.exit(1) # Exit with error code
    finally:
        print("Stream process finished.")

if __name__ == '__main__':
    main() 