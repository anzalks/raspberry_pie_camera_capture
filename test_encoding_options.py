#!/usr/bin/env python3
"""
Test script to verify encoding options work correctly.
This script tests writing a simple video with different encoding options.
"""

import cv2
import numpy as np
import os
import time
from datetime import datetime
import argparse

def test_encoder(width, height, fps, codec, bitrate, quality_preset):
    """Test encoding with specified parameters."""
    
    # Create output filename with encoding parameters
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"encoding_test_{codec}_{bitrate}kbps_{quality_preset}_{timestamp}.mkv"
    
    # Print test parameters
    print(f"\nTesting encoding with:")
    print(f"  Resolution: {width}x{height}")
    print(f"  FPS: {fps}")
    print(f"  Codec: {codec}")
    print(f"  Bitrate: {bitrate} Kbps")
    print(f"  Quality Preset: {quality_preset}")
    print(f"  Output file: {output_file}")
    
    # Map codec string to fourcc
    codec_map = {
        'h264': 'H264',
        'h265': 'H265',
        'hevc': 'HEVC',
        'mjpg': 'MJPG'
    }
    
    # Get fourcc
    fourcc_str = codec_map.get(codec.lower(), 'H264')
    fourcc = cv2.VideoWriter_fourcc(*fourcc_str)
    
    # Create video writer
    writer = cv2.VideoWriter(output_file, fourcc, float(fps), (width, height))
    
    # Set encoding parameters if possible
    if bitrate > 0:
        print(f"  Setting constant bitrate: {bitrate} Kbps")
        writer.set(cv2.VIDEOWRITER_PROP_QUALITY, 0)  # Quality=0 for bitrate control
        result = writer.set(cv2.VIDEOWRITER_PROP_TARGET_BITRATE, float(bitrate))
        print(f"  Bitrate set: {'Success' if result else 'Failed'}")
    
    # Set quality preset if possible
    preset_map = {
        'ultrafast': 0, 'superfast': 1, 'veryfast': 2, 'faster': 3, 
        'fast': 4, 'medium': 5, 'slow': 6, 'slower': 7, 'veryslow': 8
    }
    preset_value = preset_map.get(quality_preset.lower(), 5)  # Default to medium (5)
    print(f"  Setting quality preset: {quality_preset} (value: {preset_value})")
    result = writer.set(cv2.VIDEOWRITER_PROP_SPEED_PRESET, float(preset_value))
    print(f"  Preset set: {'Success' if result else 'Failed'}")
    
    # Check if writer is open
    if not writer.isOpened():
        print(f"ERROR: Failed to open video writer with codec {fourcc_str}")
        return False
    
    # Generate and write test frames
    print(f"  Writing test frames...")
    num_frames = int(fps * 5)  # 5 seconds of video
    start_time = time.time()
    
    try:
        for i in range(num_frames):
            # Create a test pattern frame
            frame = np.zeros((height, width, 3), dtype=np.uint8)
            
            # Draw a moving pattern
            cv2.rectangle(frame, (i % width, i % height), 
                        ((i + 100) % width, (i + 100) % height), 
                        (0, 255, 0), -1)
            
            # Add text with frame number
            cv2.putText(frame, f"Frame {i}", (20, 40), 
                       cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
            
            # Write the frame
            writer.write(frame)
            
            # Print progress
            if i % 10 == 0:
                print(f"  Progress: {i}/{num_frames} frames", end='\r')
    
    except Exception as e:
        print(f"\nERROR during encoding: {e}")
        writer.release()
        return False
    
    # Release the writer
    writer.release()
    
    # Calculate performance
    end_time = time.time()
    elapsed_time = end_time - start_time
    actual_fps = num_frames / elapsed_time
    
    print(f"\nEncoding complete:")
    print(f"  Frames encoded: {num_frames}")
    print(f"  Elapsed time: {elapsed_time:.2f} seconds")
    print(f"  Average FPS: {actual_fps:.2f}")
    
    # Check if file exists and get size
    if os.path.exists(output_file):
        file_size_mb = os.path.getsize(output_file) / (1024 * 1024)
        print(f"  Output file size: {file_size_mb:.2f} MB")
        print(f"  File saved at: {output_file}")
        return True
    else:
        print(f"ERROR: Output file not created")
        return False

def main():
    parser = argparse.ArgumentParser(description='Test video encoding options')
    parser.add_argument('--width', type=int, default=640, help='Video width')
    parser.add_argument('--height', type=int, default=480, help='Video height')
    parser.add_argument('--fps', type=int, default=30, help='Frames per second')
    parser.add_argument('--codec', type=str, default='h264', choices=['h264', 'h265', 'mjpg'], 
                        help='Video codec to use')
    parser.add_argument('--bitrate', type=int, default=2000, help='Bitrate in Kbps')
    parser.add_argument('--quality-preset', type=str, default='medium', 
                       choices=['ultrafast', 'superfast', 'veryfast', 'faster', 'fast', 
                               'medium', 'slow', 'slower', 'veryslow'],
                       help='Encoding preset')
    
    args = parser.parse_args()
    
    # Run the test
    success = test_encoder(
        args.width, args.height, args.fps,
        args.codec, args.bitrate, args.quality_preset
    )
    
    # Exit with status
    exit(0 if success else 1)

if __name__ == "__main__":
    main() 