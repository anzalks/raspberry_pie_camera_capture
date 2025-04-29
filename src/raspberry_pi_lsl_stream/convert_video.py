"""Utility script to convert video format (e.g., BGR to RGB)."""

import argparse
import cv2
import os
import sys
import time

def convert_bgr_to_rgb(input_filename, output_filename):
    """Opens a BGR video file, converts frames to RGB, and saves to a new file."""

    if not os.path.exists(input_filename):
        print(f"Error: Input file not found: {input_filename}", file=sys.stderr)
        return False

    cap = None
    writer = None
    frame_count = 0
    start_time = time.time()

    try:
        # Open Input Video
        cap = cv2.VideoCapture(input_filename)
        if not cap.isOpened():
            print(f"Error: Could not open input video file: {input_filename}", file=sys.stderr)
            return False

        # Get Input Properties
        fps = cap.get(cv2.CAP_PROP_FPS)
        input_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        input_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        input_frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        print(f"Input: {input_w}x{input_h} @ {fps:.2f} FPS (approx {input_frame_count} frames)")

        if input_w == 0 or input_h == 0:
             print("Error: Input video has zero dimensions.", file=sys.stderr)
             return False
        if fps <= 0:
             print("Warning: Input video FPS is zero or invalid. Using 30.0 as fallback for output.")
             fps = 30.0 # Fallback FPS

        # Setup Output Video Writer
        # Using MJPG codec in MKV container - relatively safe for RGB but large files
        # WARNING: Playback compatibility/color correctness may vary!
        fourcc = cv2.VideoWriter_fourcc(*'MJPG')
        print(f"Output: {output_filename}, Codec: MJPG, Container: MKV")
        writer = cv2.VideoWriter(output_filename, fourcc, float(fps), (input_w, input_h), isColor=True)
        if not writer.isOpened():
            print(f"Error: Could not open output video file for writing: {output_filename}", file=sys.stderr)
            return False
            
        print("Starting conversion (BGR -> RGB)... Press Ctrl+C to interrupt.")

        # Process Frames
        while True:
            ret, frame_bgr = cap.read()
            if not ret:
                break # End of video
            
            frame_count += 1
            
            # Convert BGR to RGB
            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            
            # Write the RGB frame
            writer.write(frame_rgb)
            
            # Print progress
            if frame_count % 100 == 0:
                 print(f"  Processed {frame_count} frames...", end='\r')

        end_time = time.time()
        print(f"\nConversion finished. Processed {frame_count} frames in {end_time - start_time:.2f} seconds.")
        return True

    except KeyboardInterrupt:
        print("\nConversion interrupted by user.")
        # Output file might be incomplete/corrupted
        return False
    except Exception as e:
        print(f"\nAn error occurred during conversion: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return False
    finally:
        if cap is not None:
            cap.release()
        if writer is not None:
            writer.release()
        print("Cleaned up resources.")

def main():
    parser = argparse.ArgumentParser(
        description='Convert a video file from BGR to RGB format (saving as MJPG in MKV). Warning: Playback compatibility may vary.',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument('input_file', type=str, help='Path to the input BGR video file.')
    parser.add_argument('-o', '--output-file', type=str, default=None, 
                        help='Path for the output RGB video file. Defaults to [input_file]_RGB.mkv')
    
    args = parser.parse_args()
    
    output_file = args.output_file
    if output_file is None:
        base, ext = os.path.splitext(args.input_file)
        output_file = f"{base}_RGB.mkv"
        
    if os.path.abspath(args.input_file) == os.path.abspath(output_file):
        print("Error: Input and output filenames cannot be the same.", file=sys.stderr)
        sys.exit(1)

    print(f"Input video: {args.input_file}")
    print(f"Output video (RGB): {output_file}")
    
    if not convert_bgr_to_rgb(args.input_file, output_file):
        print("Conversion failed.")
        sys.exit(1)
    else:
        print("Conversion successful.")

if __name__ == "__main__":
    main() 