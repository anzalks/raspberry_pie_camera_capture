#!/usr/bin/env python3
"""
Script to check if the Raspberry Pi camera environment is properly set up.
This script tests all the imports and verifies camera functionality.

Author: Anzal
Email: anzal.ks@gmail.com
GitHub: https://github.com/anzalks/
"""

import os
import sys
import platform
from pathlib import Path

def print_header(text):
    print("\n" + "=" * 60)
    print(f" {text}")
    print("=" * 60)

def print_status(name, status, message=""):
    status_text = "✅ PASS" if status else "❌ FAIL"
    print(f"{status_text} - {name}")
    if message:
        print(f"      {message}")

print_header("Raspberry Pi Camera Setup Checker")
print(f"Python version: {platform.python_version()}")
print(f"Platform: {platform.platform()}")

# Check if running in virtual environment
in_venv = sys.prefix != sys.base_prefix
print_status("Virtual Environment", in_venv, 
             f"Active: {os.environ.get('VIRTUAL_ENV', 'Not activated')}" if in_venv 
             else "Not running in a virtual environment")

# Check paths
print_header("Checking System Paths")
for path in sys.path:
    print(f"- {path}")

# Check for required libraries
print_header("Checking Required Libraries")

# Check OpenCV
try:
    import cv2
    print_status("OpenCV", True, f"Version: {cv2.__version__}")
except ImportError as e:
    print_status("OpenCV", False, f"Error: {e}")

# Check numpy
try:
    import numpy as np
    print_status("NumPy", True, f"Version: {np.__version__}")
except ImportError as e:
    print_status("NumPy", False, f"Error: {e}")

# Check PiCamera2
try:
    from picamera2 import Picamera2
    print_status("PiCamera2", True, "Library found")
except ImportError as e:
    print_status("PiCamera2", False, f"Error: {e}")

# Check pylsl
try:
    from pylsl import StreamInfo
    print_status("pylsl", True, "Library found")
except ImportError as e:
    print_status("pylsl", False, f"Error: {e}")

# Check our own package
print_header("Checking Project Package")
try:
    import src.raspberry_pi_lsl_stream
    print_status("Project Package", True, "Successfully imported")
    
    try:
        is_pi = getattr(src.raspberry_pi_lsl_stream, 'IS_RASPBERRY_PI', None)
        print_status("Raspberry Pi Detection", True if is_pi else False, 
                    "Detected as Raspberry Pi" if is_pi else "Not detected as Raspberry Pi")
    except:
        print_status("Raspberry Pi Detection", False, "Failed to check")
except ImportError as e:
    print_status("Project Package", False, f"Error: {e}")

# Check camera devices
print_header("Checking Camera Devices")
try:
    import glob
    device_paths = glob.glob('/dev/video*')
    if device_paths:
        print_status("Camera Devices", True, f"Found {len(device_paths)} devices: {', '.join(device_paths)}")
        
        # Try opening the first camera to check if it's accessible
        try:
            cap = cv2.VideoCapture(0)
            if cap.isOpened():
                ret, frame = cap.read()
                if ret:
                    print_status("Camera Access", True, "Successfully captured a frame")
                else:
                    print_status("Camera Access", False, "Failed to read frame")
                cap.release()
            else:
                print_status("Camera Access", False, "Failed to open camera")
        except Exception as e:
            print_status("Camera Access", False, f"Error: {e}")
    else:
        print_status("Camera Devices", False, "No video devices found")
except Exception as e:
    print_status("Camera Devices", False, f"Error checking camera devices: {e}")

# Print overall summary
print_header("Summary")
print("If any checks failed, you may need to:")
print("1. Activate the virtual environment: source .venv/bin/activate")
print("2. Install missing packages: pip install -r requirements.txt")
print("3. Ensure camera is enabled: sudo raspi-config")
print("4. Check camera connections")
print("5. Ensure user is in the video group: sudo usermod -a -G video $USER")
print("\nTo run the camera system with proper environment:")
print("  ./run-camera.sh") 