"""LSL Client to view frame numbers and timestamps from the stream."""

from pylsl import StreamInlet, resolve_byprop
import sys
import time
import argparse
import xml.etree.ElementTree as ET


def main():
    """Finds the LSL stream, connects to it, 
       and prints received frame numbers and timestamps.
    """
    parser = argparse.ArgumentParser(
        description='View LSL stream frame numbers and timestamps.',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument('--stream-name', type=str, default='RaspberryPiCamera', 
                        help='Name of the LSL stream to connect to.')
    parser.add_argument('--timeout', type=float, default=5.0, 
                        help='Timeout in seconds to search for the stream.')
    args = parser.parse_args()

    STREAM_NAME = args.stream_name
    TIMEOUT_SECONDS = args.timeout

    # --- LSL Stream Discovery ---
    print(f"Looking for LSL stream named '{STREAM_NAME}' (timeout={TIMEOUT_SECONDS}s)...")
    streams = resolve_byprop('name', STREAM_NAME, timeout=TIMEOUT_SECONDS)

    if not streams:
        print(f"Error: Could not find LSL stream '{STREAM_NAME}'.", file=sys.stderr)
        print("Make sure the rpi-lsl-stream script is running.", file=sys.stderr)
        sys.exit(1)

    # --- LSL Inlet Creation ---
    print(f"Found stream '{STREAM_NAME}'. Creating inlet...")
    inlet = StreamInlet(streams[0])

    # --- Optional: Display some stream metadata ---
    try:
        info_xml = inlet.info().as_xml()
        root = ET.fromstring(info_xml)
        print("--- Stream Info --- ")
        s_name = root.find('name')
        s_type = root.find('type')
        s_rate = root.find('nominal_srate')
        s_id = root.find('source_id')
        cam_model = root.find('./desc/camera_model')
        src_type = root.find('./desc/source_type')
        
        print(f"  Name: {s_name.text if s_name is not None else 'N/A'}")
        print(f"  Type: {s_type.text if s_type is not None else 'N/A'}")
        print(f"  Nominal Rate: {s_rate.text if s_rate is not None else 'N/A'} Hz")
        print(f"  Source ID: {s_id.text if s_id is not None else 'N/A'}")
        print(f"  Camera Model: {cam_model.text if cam_model is not None else 'N/A'}")
        print(f"  Source Type: {src_type.text if src_type is not None else 'N/A'}")
        print("-------------------")
    except Exception as e:
        print(f"Warning: Could not parse full stream info - {e}")

    print("\nReceiving stream data... Press Ctrl+C to stop.")
    frames_received = 0
    start_time = time.time()

    try:
        while True:
            # Pull a sample (frame number) and its timestamp from the LSL inlet.
            # The sample should be a list containing one integer.
            sample, timestamp = inlet.pull_sample(timeout=1.0) # Timeout after 1 second

            if sample:
                frames_received += 1
                try:
                    frame_number = int(sample[0])
                    # Print frame number and timestamp
                    print(f"Received Frame: {frame_number:<6} | LSL Timestamp: {timestamp:.6f}", end='\r')
                except (IndexError, ValueError, TypeError) as e:
                    print(f"\nWarning: Received unexpected sample format: {sample} ({e}). Skipping.")
            else:
                # Handle timeout
                print("Waiting for data...                     ", end='\r')
                pass

    except KeyboardInterrupt:
         print("\nCtrl+C pressed, exiting.")
    finally:
        # --- Cleanup ---
        print(f"\nClosing LSL inlet. Total samples received: {frames_received}")
        if frames_received > 0:
             elapsed = time.time() - start_time
             avg_rate = frames_received / elapsed
             print(f"Average received rate: {avg_rate:.2f} Hz")
        inlet.close_stream()

if __name__ == '__main__':
    main() 