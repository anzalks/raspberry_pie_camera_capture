#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IMX296 Camera Capture Launcher Script
This script handles proper initialization and launching of the IMX296 camera capture system.

Author: Anzal KS <anzal.ks@gmail.com>
Date: May 22, 2025
"""

import os
import sys
import time
import subprocess
import logging
import shutil
from pathlib import Path

# Setup basic logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/camera_launcher.log')
    ]
)
logger = logging.getLogger('camera_launcher')

# Ensure we're in the project root directory
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(project_root)
logger.info(f"Working directory: {os.getcwd()}")

def check_camera_devices():
    """Check if camera devices are available."""
    logger.info("Checking camera devices...")
    
    # Check for video devices
    video_devices = []
    for i in range(10):
        dev_path = f"/dev/video{i}"
        if os.path.exists(dev_path):
            video_devices.append(dev_path)
    
    if not video_devices:
        logger.error("No video devices found!")
        return False
    
    logger.info(f"Found video devices: {video_devices}")
    
    # Check if media devices exist
    media_devices = []
    for i in range(10):
        dev_path = f"/dev/media{i}"
        if os.path.exists(dev_path):
            media_devices.append(dev_path)
    
    if not media_devices:
        logger.warning("No media devices found. This might be a problem for hardware cropping.")
    else:
        logger.info(f"Found media devices: {media_devices}")
    
    # Use libcamera-hello to verify camera is detected
    try:
        logger.info("Running libcamera-hello to check camera...")
        result = subprocess.run(
            ["libcamera-hello", "--list-cameras"],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        logger.info(f"libcamera-hello output: {result.stdout}")
        logger.info(f"libcamera-hello error: {result.stderr}")
        
        if "imx296" in result.stdout.lower() or "camera0" in result.stdout.lower():
            logger.info("Camera detected by libcamera-hello")
            return True
        else:
            logger.warning("IMX296 camera not explicitly detected by libcamera-hello")
            if "available cameras" in result.stdout.lower():
                logger.info("But some camera was detected, will proceed")
                return True
    except subprocess.TimeoutExpired:
        logger.error("libcamera-hello timed out")
    except Exception as e:
        logger.error(f"Error running libcamera-hello: {e}")
    
    # Fall back to v4l2-ctl as a final check
    try:
        logger.info("Checking with v4l2-ctl as fallback...")
        result = subprocess.run(
            ["v4l2-ctl", "--list-devices"],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        logger.info(f"v4l2-ctl output: {result.stdout}")
        
        if result.stdout.strip():
            logger.info("Some video devices detected by v4l2-ctl, will proceed")
            return True
    except Exception as e:
        logger.error(f"Error running v4l2-ctl: {e}")
    
    return False

def reset_camera_devices():
    """Reset camera devices to ensure clean start."""
    logger.info("Resetting camera devices...")
    
    # Reset any existing V4L2 devices
    try:
        for i in range(10):
            dev_path = f"/dev/video{i}"
            if os.path.exists(dev_path):
                logger.info(f"Resetting {dev_path}")
                subprocess.run(
                    ["v4l2-ctl", "-d", dev_path, "--all"],
                    capture_output=True,
                    timeout=2
                )
                subprocess.run(
                    ["v4l2-ctl", "-d", dev_path, "-c", "timeout_value=3000"],
                    capture_output=True,
                    timeout=2
                )
    except Exception as e:
        logger.warning(f"Error resetting v4l2 devices: {e}")
    
    # Reset media devices
    try:
        for i in range(10):
            dev_path = f"/dev/media{i}"
            if os.path.exists(dev_path):
                logger.info(f"Resetting {dev_path}")
                subprocess.run(
                    ["media-ctl", "-d", dev_path, "-r"],
                    capture_output=True,
                    timeout=2
                )
    except Exception as e:
        logger.warning(f"Error resetting media devices: {e}")
    
    # Give devices time to stabilize
    time.sleep(2)
    logger.info("Camera reset completed")

def ensure_directories():
    """Ensure required directories exist with proper permissions."""
    dirs = ['logs', 'recordings']
    for dir_name in dirs:
        dir_path = os.path.join(project_root, dir_name)
        os.makedirs(dir_path, exist_ok=True)
        try:
            # Try to set permissions, but don't fail if not possible
            os.chmod(dir_path, 0o777)
        except:
            pass
        logger.info(f"Ensured directory exists: {dir_path}")

def launch_camera_capture():
    """Launch the IMX296 capture script."""
    logger.info("Launching IMX296 camera capture system...")
    
    # Import and run the main capture script
    try:
        logger.info("Importing imx296_capture module...")
        sys.path.insert(0, os.path.join(project_root, 'src'))
        
        # Use the module path for the IMX296 capture
        from imx296_gs_capture import imx296_capture
        
        # Run the main function
        logger.info("Starting imx296_capture.main()")
        return imx296_capture.main()
    except ImportError as e:
        logger.error(f"Failed to import imx296_capture module: {e}")
        
        # Try to run as subprocess instead
        logger.info("Trying to run as subprocess instead...")
        try:
            capture_script = os.path.join(project_root, 'src', 'imx296_gs_capture', 'imx296_capture.py')
            if os.path.exists(capture_script):
                logger.info(f"Running {capture_script}")
                
                # Make sure it's executable
                os.chmod(capture_script, 0o755)
                
                # Run the script
                subprocess.run([sys.executable, capture_script], check=True)
                return 0
            else:
                logger.error(f"Script not found: {capture_script}")
        except Exception as subproc_e:
            logger.error(f"Failed to run as subprocess: {subproc_e}")
    except Exception as e:
        logger.error(f"Error launching camera capture: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
    
    return 1

def main():
    """Main function to run the camera capture launcher."""
    logger.info("========== IMX296 Camera Capture Launcher ==========")
    
    # Ensure directories exist
    ensure_directories()
    
    # Reset camera devices
    reset_camera_devices()
    
    # Check if camera is available
    if not check_camera_devices():
        logger.error("Camera check failed. Cannot proceed.")
        return 1
    
    # Launch camera capture
    return launch_camera_capture()

if __name__ == "__main__":
    sys.exit(main()) 