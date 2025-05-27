#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IMX296 Camera Capture Launcher Script - Dynamic Path Compatible
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
import glob

# Dynamic path detection - works regardless of installation location
script_path = Path(__file__).resolve()
project_root = script_path.parent.parent
bin_dir = script_path.parent

# Change to project root for consistent operation
original_cwd = Path.cwd()
os.chdir(project_root)

# Setup basic logging with dynamic paths
log_dir = project_root / "logs"
log_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(log_dir / 'camera_launcher.log')
    ]
)
logger = logging.getLogger('camera_launcher')

# Log dynamic path detection for debugging
logger.info(f"Dynamic path detection:")
logger.info(f"  Script location: {script_path}")
logger.info(f"  Project root: {project_root}")
logger.info(f"  Bin directory: {bin_dir}")
logger.info(f"  Working directory: {Path.cwd()}")
logger.info(f"  Original CWD: {original_cwd}")

def check_camera_hardware():
    """Check if IMX296 camera hardware is available with dynamic device detection."""
    logger = logging.getLogger('camera_check')
    
    try:
        # Dynamic media device detection
        media_devices = glob.glob('/dev/media*')
        media_devices.sort()
        
        logger.info(f"Checking {len(media_devices)} media devices for IMX296 camera")
        
        imx296_found = False
        for device_path in media_devices:
            # Skip non-numeric devices
            try:
                device_num = int(device_path.split('media')[-1])
            except ValueError:
                continue
                
            if os.path.exists(device_path):
                try:
                    result = subprocess.run([
                        'media-ctl', '-d', device_path, '-p'
                    ], capture_output=True, text=True, timeout=5)
                    
                    if 'imx296' in result.stdout.lower():
                        logger.info(f"IMX296 camera found on {device_path}")
                        imx296_found = True
                        break
                        
                except (subprocess.TimeoutExpired, FileNotFoundError):
                    continue
        
        if not imx296_found:
            logger.warning("IMX296 camera not detected via media-ctl")
            
        # Dynamic video device detection
        video_devices = glob.glob('/dev/video*')
        video_devices.sort()
        
        logger.info(f"Available video devices: {video_devices}")
        
        for device_path in video_devices:
            # Skip non-numeric devices
            try:
                device_num = int(device_path.split('video')[-1])
            except ValueError:
                continue
                
            if os.path.exists(device_path):
                try:
                    result = subprocess.run([
                        'v4l2-ctl', '-d', device_path, '--list-formats-ext'
                    ], capture_output=True, text=True, timeout=3)
                    
                    if result.returncode == 0:
                        logger.info(f"Video device {device_path} is accessible")
                        
                except (subprocess.TimeoutExpired, FileNotFoundError):
                    continue
        
        return True
        
    except Exception as e:
        logger.error(f"Camera hardware check failed: {e}")
        return False

def find_project_root():
    """Find project root directory dynamically."""
    current = Path(__file__).resolve()
    
    # Look for key project files to identify root
    key_files = ['config/config.yaml', 'src/imx296_gs_capture', 'bin/GScrop']
    
    for parent in [current.parent.parent, current.parent, current]:
        if all((parent / key_file).exists() for key_file in key_files):
            return parent
    
    # Fallback to parent directory
    return current.parent.parent

def check_dependencies():
    """Check if all required dependencies are available with dynamic detection."""
    logger = logging.getLogger('deps_check')
    
    missing_deps = []
    
    # Check Python packages
    try:
        import yaml
        import requests
        import psutil
    except ImportError as e:
        missing_deps.append(f"Python package: {e}")
    
    # Check LSL
    try:
        import pylsl
        logger.info(f"LSL available: {pylsl.__version__}")
    except ImportError:
        missing_deps.append("pylsl (Lab Streaming Layer)")
    
    # Check system tools with dynamic detection
    import subprocess
    system_tools = ['media-ctl', 'v4l2-ctl', 'ffmpeg']
    
    for tool in system_tools:
        try:
            result = subprocess.run(['which', tool], capture_output=True, text=True)
            if result.returncode == 0:
                logger.info(f"{tool} found at: {result.stdout.strip()}")
            else:
                missing_deps.append(f"System tool: {tool}")
        except FileNotFoundError:
            missing_deps.append(f"System tool: {tool}")
    
    # Dynamic libcamera detection
    libcamera_tools = ['libcamera-hello', 'rpicam-hello', 'libcamera-vid', 'rpicam-vid']
    libcamera_found = False
    
    for tool in libcamera_tools:
        try:
            result = subprocess.run(['which', tool], capture_output=True, text=True)
            if result.returncode == 0:
                logger.info(f"Libcamera tool found: {tool} at {result.stdout.strip()}")
                libcamera_found = True
                break
        except FileNotFoundError:
            continue
    
    if not libcamera_found:
        missing_deps.append("libcamera tools (libcamera-hello/rpicam-hello)")
    
    if missing_deps:
        logger.error("Missing dependencies:")
        for dep in missing_deps:
            logger.error(f"  - {dep}")
        return False
    
    logger.info("All dependencies available")
    return True

def check_gscrop_script():
    """Check if GScrop script is available and executable using dynamic path detection."""
    logger.info("Checking GScrop script with dynamic path detection...")
    
    # Search for GScrop in multiple locations
    gscrop_locations = [
        project_root / 'bin' / 'GScrop',
        bin_dir / 'GScrop',
        project_root / 'GScrop',
        Path.cwd() / 'GScrop'
    ]
    
    for gscrop_path in gscrop_locations:
        if gscrop_path.exists():
            if not os.access(gscrop_path, os.X_OK):
                logger.warning(f"GScrop script found but not executable: {gscrop_path}")
                logger.info("Attempting to make GScrop executable...")
                try:
                    gscrop_path.chmod(0o755)
                    logger.info("Successfully made GScrop executable")
                except Exception as e:
                    logger.error(f"Failed to make GScrop executable: {e}")
                    continue
            
            logger.info(f"GScrop script found and executable: {gscrop_path}")
            return True
    
    logger.error("GScrop script not found in any expected location:")
    for path in gscrop_locations:
        logger.error(f"  - {path}")
    
    return False

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
    """Ensure required directories exist with proper permissions using dynamic paths."""
    required_dirs = ['logs', 'recordings', 'config']
    
    for dir_name in required_dirs:
        dir_path = project_root / dir_name
        dir_path.mkdir(exist_ok=True)
        try:
            # Try to set permissions, but don't fail if not possible
            dir_path.chmod(0o777)
        except:
            pass
        logger.info(f"Ensured directory exists: {dir_path}")

def launch_camera_capture():
    """Launch the IMX296 capture script using dynamic path detection."""
    logger.info("Launching IMX296 camera capture system...")
    
    # Import and run the main capture script
    try:
        logger.info("Importing imx296_capture module...")
        
        # Add project source directory to Python path
        src_dir = project_root / 'src'
        if str(src_dir) not in sys.path:
            sys.path.insert(0, str(src_dir))
        
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
            capture_script = project_root / 'src' / 'imx296_gs_capture' / 'imx296_capture.py'
            if capture_script.exists():
                logger.info(f"Running {capture_script}")
                
                # Make sure it's executable
                capture_script.chmod(0o755)
                
                # Run the script
                subprocess.run([sys.executable, str(capture_script)], check=True)
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
    logger.info("Starting IMX296 camera capture launcher with dynamic path support...")
    logger.info(f"Project root: {project_root}")
    
    # Ensure required directories exist
    ensure_directories()
    
    # Check if GScrop script is available
    if not check_gscrop_script():
        logger.error("Cannot proceed without GScrop script")
        return 1
    
    # Check camera devices
    if not check_camera_hardware():
        logger.warning("No camera devices found, but will try to proceed anyway")
    
    # Reset camera devices for clean start
    reset_camera_devices()
    
    # Launch the capture system
    try:
        return launch_camera_capture()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, stopping...")
        return 0
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code) 