#!/usr/bin/env python3
"""
IMX296 Camera Direct Capture Test
Author: Anzal KS <anzal.ks@gmail.com>
Date: May 23, 2025

This script tests direct capture from the IMX296 camera to ffmpeg without using the service.
It helps diagnose issues with the video capture pipeline.
"""

import os
import sys
import time
import subprocess
import argparse
import yaml
import signal
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('test_direct_capture')

def load_config():
    """Load configuration from config.yaml"""
    try:
        # Try to find config in the current directory first
        config_path = os.path.join(os.getcwd(), 'config', 'config.yaml')
        if not os.path.exists(config_path):
            # Try parent directory
            config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config', 'config.yaml')
            
        with open(config_path, 'r') as file:
            config = yaml.safe_load(file)
            logger.info(f"Loaded config from {config_path}")
            return config
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        sys.exit(1)

def run_direct_capture(config, duration=5, output_file=None):
    """Run direct camera capture with libcamera-vid piped to ffmpeg"""
    
    # Get paths and settings from config
    libcamera_vid_path = config['system']['libcamera_vid_path']
    ffmpeg_path = config['system']['ffmpeg_path']
    width = config['camera']['width']
    height = config['camera']['height']
    fps = config['camera']['fps']
    exposure_time_us = config['camera']['exposure_time_us']
    codec = config['recording'].get('codec', 'mjpeg').lower()
    format_ext = config['recording'].get('video_format', 'mkv')
    
    # Determine output file
    if output_file is None:
        output_file = f"/tmp/test_capture_{time.strftime('%Y%m%d_%H%M%S')}.{format_ext}"
    
    # Construct libcamera-vid command
    camera_cmd = [
        libcamera_vid_path,
        "--width", str(width),
        "--height", str(height),
        "--framerate", str(fps),
        "--shutter", str(exposure_time_us),
        "--timeout", str(duration * 1000),  # Convert seconds to milliseconds
        "--codec", codec,
        "--inline",
        "--nopreview",
        "--no-raw",
        "-o", "-"  # Output to stdout
    ]
    
    # Construct ffmpeg command
    ffmpeg_cmd = [
        ffmpeg_path,
        "-f", codec,    # Input format matches codec
        "-i", "-",      # Input from stdin
        "-c:v", "copy", # Copy video codec (no re-encoding)
        "-an",          # No audio
        "-y",           # Overwrite output file if exists
        output_file     # Output file
    ]
    
    logger.info(f"Starting direct capture with commands:")
    logger.info(f"Camera: {' '.join(camera_cmd)}")
    logger.info(f"FFmpeg: {' '.join(ffmpeg_cmd)}")
    logger.info(f"Output file: {output_file}")
    
    try:
        # Start libcamera-vid process
        camera_process = subprocess.Popen(
            camera_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=10*1024*1024  # 10MB buffer
        )
        
        # Start ffmpeg process
        ffmpeg_process = subprocess.Popen(
            ffmpeg_cmd,
            stdin=camera_process.stdout,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=10*1024*1024  # 10MB buffer
        )
        
        # Close camera stdout in parent process to avoid deadlocks
        camera_process.stdout.close()
        
        # Wait for the specified duration
        logger.info(f"Recording in progress for {duration} seconds...")
        time.sleep(duration + 1)  # Add 1 second buffer
        
        # Terminate processes
        logger.info("Terminating processes...")
        camera_process.terminate()
        ffmpeg_process.terminate()
        
        # Wait for processes to exit
        camera_process.wait(timeout=5)
        ffmpeg_process.wait(timeout=5)
        
        # Get output and error messages
        camera_stderr = camera_process.stderr.read().decode('utf-8', errors='ignore')
        ffmpeg_stderr = ffmpeg_process.stderr.read().decode('utf-8', errors='ignore')
        
        # Check file size
        if os.path.exists(output_file):
            file_size = os.path.getsize(output_file)
            logger.info(f"Created output file: {output_file} ({file_size / 1024:.2f} KB)")
            
            if file_size < 5000:  # Less than 5KB is probably just headers
                logger.error(f"File seems empty or corrupted (only {file_size} bytes)")
                logger.error("This usually indicates no frames were captured")
        else:
            logger.error(f"Output file was not created: {output_file}")
        
        # Log error output if the file is small
        if os.path.exists(output_file) and os.path.getsize(output_file) < 5000:
            logger.error("Camera process stderr output:")
            for line in camera_stderr.splitlines():
                logger.error(f"  {line}")
            
            logger.error("FFmpeg process stderr output:")
            for line in ffmpeg_stderr.splitlines():
                logger.error(f"  {line}")
        
        return output_file
            
    except subprocess.TimeoutExpired:
        logger.error("Timeout waiting for processes to exit")
        # Force kill any remaining processes
        try:
            camera_process.kill()
            ffmpeg_process.kill()
        except:
            pass
    except Exception as e:
        logger.error(f"Error during direct capture: {e}")
    
    return None

def main():
    """Main function"""
    parser = argparse.ArgumentParser(description='Test direct camera capture with ffmpeg')
    parser.add_argument('-d', '--duration', type=int, default=5, help='Recording duration in seconds')
    parser.add_argument('-o', '--output', type=str, help='Output filename')
    args = parser.parse_args()
    
    # Load configuration
    config = load_config()
    
    # Run direct capture
    output_file = run_direct_capture(config, args.duration, args.output)
    
    if output_file and os.path.exists(output_file):
        file_size = os.path.getsize(output_file)
        if file_size > 5000:
            logger.info(f"SUCCESS: Capture completed successfully! File size: {file_size / 1024:.2f} KB")
            logger.info(f"You can view the file with: ffplay {output_file}")
        else:
            logger.error(f"FAILED: Capture resulted in empty file ({file_size} bytes)")
    else:
        logger.error("FAILED: Capture process failed or output file not created")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(0) 