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
import json

# Setup more verbose logging
logging.basicConfig(
    level=logging.DEBUG,  # Use DEBUG for more detailed information
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('test_direct_capture')

# Also log to a file for later analysis
file_handler = logging.FileHandler('/tmp/camera_test_debug.log')
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)

def load_config():
    """Load configuration from config.yaml"""
    try:
        config_paths = [
            os.path.join(os.getcwd(), 'config', 'config.yaml'),
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config', 'config.yaml'),
            "/etc/imx296-camera/config.yaml"  # System-wide config
        ]
        
        for config_path in config_paths:
            if os.path.exists(config_path):
                with open(config_path, 'r') as file:
                    config = yaml.safe_load(file)
                    logger.info(f"Loaded config from {config_path}")
                    return config
        
        # If no config found, create a minimal one
        logger.warning("No config file found, using defaults")
        return {
            'system': {
                'libcamera_vid_path': "/usr/bin/libcamera-vid",
                'ffmpeg_path': "/usr/bin/ffmpeg"
            },
            'camera': {
                'width': 400,
                'height': 400,
                'fps': 100,
                'exposure_time_us': 5000
            },
            'recording': {
                'video_format': "mkv",
                'codec': "mjpeg"
            }
        }
    except Exception as e:
        logger.error(f"Error loading config: {e}", exc_info=True)
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
    
    # Log system information for debugging
    logger.info(f"System information:")
    logger.info(f"Python version: {sys.version}")
    try:
        import platform
        logger.info(f"Platform: {platform.platform()}")
        logger.info(f"Architecture: {platform.machine()}")
    except Exception as e:
        logger.warning(f"Could not get platform info: {e}")
    
    # List available cameras
    logger.info("Checking available cameras...")
    try:
        list_cmd = [libcamera_vid_path, "--list-cameras"]
        camera_list = subprocess.check_output(list_cmd, universal_newlines=True)
        logger.info(f"Available cameras:\n{camera_list}")
    except Exception as e:
        logger.error(f"Error listing cameras: {e}")
    
    # Verify ffmpeg installation
    logger.info("Checking ffmpeg installation...")
    try:
        ffmpeg_version = subprocess.check_output([ffmpeg_path, "-version"], universal_newlines=True).split('\n')[0]
        logger.info(f"FFmpeg version: {ffmpeg_version}")
    except Exception as e:
        logger.error(f"Error checking ffmpeg: {e}")
    
    # Determine output file
    if output_file is None:
        output_file = f"/tmp/test_capture_{time.strftime('%Y%m%d_%H%M%S')}.{format_ext}"
    
    # Check directory access permissions
    logger.info(f"Checking output directory permissions...")
    output_dir = os.path.dirname(output_file)
    if os.path.exists(output_dir):
        logger.info(f"Output dir exists: {output_dir}")
        if os.access(output_dir, os.W_OK):
            logger.info(f"Output dir is writable: {output_dir}")
        else:
            logger.error(f"Output dir is not writable: {output_dir}")
    else:
        logger.error(f"Output dir does not exist: {output_dir}")
        try:
            os.makedirs(output_dir, exist_ok=True)
            logger.info(f"Created output dir: {output_dir}")
        except Exception as e:
            logger.error(f"Failed to create output dir: {e}")
    
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
        "-v", "debug",  # More verbose ffmpeg output for debugging
        output_file     # Output file
    ]
    
    logger.info(f"Starting direct capture with commands:")
    logger.info(f"Camera: {' '.join(camera_cmd)}")
    logger.info(f"FFmpeg: {' '.join(ffmpeg_cmd)}")
    logger.info(f"Output file: {output_file}")
    
    try:
        # Create output file first with correct permissions to avoid ffmpeg permission issues
        try:
            with open(output_file, 'w') as f:
                pass
            os.chmod(output_file, 0o666)
            logger.info(f"Created empty output file with permissions: {output_file}")
        except Exception as e:
            logger.error(f"Error creating output file: {e}")
        
        # Start libcamera-vid process
        logger.info("Starting libcamera-vid process...")
        camera_process = subprocess.Popen(
            camera_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=10*1024*1024  # 10MB buffer
        )
        
        # Start ffmpeg process
        logger.info("Starting ffmpeg process...")
        ffmpeg_process = subprocess.Popen(
            ffmpeg_cmd,
            stdin=camera_process.stdout,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=10*1024*1024  # 10MB buffer
        )
        
        # Close camera stdout in parent process to avoid deadlocks
        camera_process.stdout.close()
        
        # Start stderr readers for both processes
        def read_stderr(process, name):
            lines = []
            while True:
                line = process.stderr.readline()
                if not line:
                    break
                try:
                    decoded_line = line.decode('utf-8', errors='replace').strip()
                    if decoded_line:
                        logger.debug(f"{name} stderr: {decoded_line}")
                        lines.append(decoded_line)
                except Exception as e:
                    logger.error(f"Error decoding {name} stderr: {e}")
            return lines
        
        # Start stderr reader threads
        import threading
        camera_stderr_thread = threading.Thread(
            target=read_stderr, 
            args=(camera_process, "libcamera-vid"),
            daemon=True
        )
        ffmpeg_stderr_thread = threading.Thread(
            target=read_stderr, 
            args=(ffmpeg_process, "ffmpeg"),
            daemon=True
        )
        
        camera_stderr_thread.start()
        ffmpeg_stderr_thread.start()
        
        # Wait for the specified duration
        logger.info(f"Recording in progress for {duration} seconds...")
        start_time = time.time()
        
        # Check progress during recording
        while time.time() - start_time < duration + 1:
            try:
                # Check if processes are still running
                if camera_process.poll() is not None:
                    logger.error(f"Camera process exited early with code: {camera_process.returncode}")
                    break
                
                if ffmpeg_process.poll() is not None:
                    logger.error(f"FFmpeg process exited early with code: {ffmpeg_process.returncode}")
                    break
                
                # Check if output file is growing
                if os.path.exists(output_file):
                    file_size = os.path.getsize(output_file)
                    logger.debug(f"Current file size: {file_size} bytes")
                
                time.sleep(0.5)
            except Exception as e:
                logger.error(f"Error during progress check: {e}")
        
        # Terminate processes
        logger.info("Terminating processes...")
        try:
            camera_process.terminate()
            ffmpeg_process.terminate()
            
            # Wait for processes to exit with timeout
            try:
                camera_process.wait(timeout=5)
                ffmpeg_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.warning("Process termination timed out, forcing kill")
                camera_process.kill()
                ffmpeg_process.kill()
        except Exception as e:
            logger.error(f"Error terminating processes: {e}")
        
        # Check file size and details
        if os.path.exists(output_file):
            file_size = os.path.getsize(output_file)
            logger.info(f"Created output file: {output_file} ({file_size / 1024:.2f} KB)")
            
            # Analyze file if small
            if file_size < 5000:  # Less than 5KB is probably just headers
                logger.error(f"File seems empty or corrupted (only {file_size} bytes)")
                logger.error("This usually indicates no frames were successfully captured")
                
                # Try to analyze the file content
                try:
                    file_info = subprocess.check_output(
                        [ffmpeg_path, "-i", output_file, "-v", "error"], 
                        stderr=subprocess.STDOUT, 
                        universal_newlines=True
                    )
                    logger.error(f"File analysis: {file_info}")
                except Exception as e:
                    logger.error(f"Error analyzing file: {e}")
            else:
                # Get more detailed file info
                try:
                    file_info = subprocess.check_output(
                        [ffmpeg_path, "-i", output_file, "-v", "error"], 
                        stderr=subprocess.STDOUT, 
                        universal_newlines=True
                    )
                    logger.info(f"File info: {file_info}")
                except Exception as e:
                    logger.warning(f"Error getting file info: {e}")
        else:
            logger.error(f"Output file was not created: {output_file}")
        
        return output_file
            
    except Exception as e:
        logger.error(f"Error during direct capture: {e}", exc_info=True)
    
    return None

def main():
    """Main function"""
    parser = argparse.ArgumentParser(description='Test direct camera capture with ffmpeg')
    parser.add_argument('-d', '--duration', type=int, default=5, help='Recording duration in seconds')
    parser.add_argument('-o', '--output', type=str, help='Output filename')
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable even more verbose output')
    args = parser.parse_args()
    
    # Set more verbose logging if requested
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.info("Verbose logging enabled")
    
    logger.info(f"Starting camera test with duration {args.duration}s")
    
    # Load configuration
    config = load_config()
    
    # Debug configuration
    logger.debug(f"Using configuration: {json.dumps(config, indent=2)}")
    
    # Run direct capture
    output_file = run_direct_capture(config, args.duration, args.output)
    
    if output_file and os.path.exists(output_file):
        file_size = os.path.getsize(output_file)
        if file_size > 5000:
            logger.info(f"SUCCESS: Capture completed successfully! File size: {file_size / 1024:.2f} KB")
            logger.info(f"You can view the file with: ffplay {output_file}")
            print(f"SUCCESS: Capture completed successfully! File size: {file_size / 1024:.2f} KB")
            return 0
        else:
            logger.error(f"FAILED: Capture resulted in empty file ({file_size} bytes)")
            print(f"FAILED: Capture resulted in empty file ({file_size} bytes)")
            return 1
    else:
        logger.error("FAILED: Capture process failed or output file not created")
        print("FAILED: Capture process failed or output file not created")
        return 1

if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(0) 
    except Exception as e:
        logger.error(f"Unhandled exception: {e}", exc_info=True)
        sys.exit(1) 