"""Utility script to verify metadata of saved video files."""

import argparse
import cv2
import os
import sys

def verify_video(filename):
    """Opens a video file and prints its metadata."""

    if not os.path.exists(filename):
        print(f"Error: File not found: {filename}", file=sys.stderr)
        return False

    cap = None
    try:
        cap = cv2.VideoCapture(filename)
        if not cap.isOpened():
            print(f"Error: Could not open video file: {filename}", file=sys.stderr)
            return False

        # Get properties
        fps = cap.get(cv2.CAP_PROP_FPS)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        duration = 0.0
        if fps > 0 and frame_count > 0:
             duration = frame_count / fps

        print(f"--- Video Statistics for: {os.path.basename(filename)} ---")
        print(f"  Resolution: {width}x{height}")
        print(f"  FPS (metadata): {fps:.3f}")
        print(f"  Frame Count: {frame_count}")
        print(f"  Duration (calculated): {duration:.3f} seconds")
        print("-----------------------------------------------------")
        
        return True

    except Exception as e:
        print(f"An error occurred while processing {filename}: {e}", file=sys.stderr)
        return False
    finally:
        if cap is not None:
            cap.release()

def main():
    parser = argparse.ArgumentParser(
        description='Verify metadata (FPS, resolution, etc.) of a video file.',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument('filename', type=str, help='Path to the video file to verify.')
    
    args = parser.parse_args()
    
    if not verify_video(args.filename):
        sys.exit(1)

if __name__ == "__main__":
    main() 