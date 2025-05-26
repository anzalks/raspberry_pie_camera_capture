#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IMX296 Camera Capture Launcher Script
This script handles proper initialization and launching of the IMX296 camera capture system.

Author: Anzal KS <anzal.ks@gmail.com>
Date: May 26, 2025
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
    
    return True

def check_gscrop_script():
    """Check if GScrop script is available and executable."""
    logger.info("Checking GScrop script...")
    
    gscrop_path = os.path.join(project_root, 'bin', 'GScrop')
    
    if not os.path.exists(gscrop_path):
        logger.error(f"GScrop script not found at: {gscrop_path}")
        return False
    
    if not os.access(gscrop_path, os.X_OK):
        logger.error(f"GScrop script is not executable: {gscrop_path}")
        logger.info("Attempting to make GScrop executable...")
        try:
            os.chmod(gscrop_path, 0o755)
            logger.info("Successfully made GScrop executable")
        except Exception as e:
            logger.error(f"Failed to make GScrop executable: {e}")
            return False
    
    logger.info(f"GScrop script found and executable: {gscrop_path}")
    return True

def reset_camera_devices():
    """Reset camera devices to ensure clean start."""
    logger.info("Resetting camera devices...")
    
    # Reset any existing V4L2 devices
    try:
        for i in range(10):
            dev_path = f"/dev/video{i}"
            if os.path.exists(dev_path):
                logger.debug(f"Resetting {dev_path}")
                subprocess.run(
                    ["v4l2-ctl", "-d", dev_path, "--all"],
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
                logger.debug(f"Resetting {dev_path}")
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
    
    return 1

def main():
    """Main function to set up and launch the camera capture system."""
    logger.info("Starting IMX296 camera capture launcher...")
    
    # Ensure required directories exist
    ensure_directories()
    
    # Check if GScrop script is available
    if not check_gscrop_script():
        logger.error("Cannot proceed without GScrop script")
        return 1
    
    # Check camera devices
    if not check_camera_devices():
        logger.warning("No camera devices found, but will try to proceed anyway")
    
    # Reset camera devices for clean start
    reset_camera_devices()
    
    # Launch the capture system
    try:
        return launch_camera_capture()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down...")
        return 0
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 