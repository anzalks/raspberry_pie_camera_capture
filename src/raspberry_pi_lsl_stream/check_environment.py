#!/usr/bin/env python3
"""
Utility script to check the environment and create necessary directories.
"""

import os
import sys
import platform
import importlib
import subprocess

def check_module(module_name, display_name=None):
    """Checks if a Python module is installed."""
    if display_name is None:
        display_name = module_name
        
    try:
        importlib.import_module(module_name)
        print(f"✅ {display_name} is installed")
        return True
    except ImportError:
        print(f"❌ {display_name} is NOT installed")
        return False

def check_system_libraries():
    """Checks for necessary system libraries."""
    if platform.system() != "Linux":
        print("⚠️  Not running on Linux, skipping system library checks")
        return
        
    # Check for required libraries
    try:
        ldd_output = subprocess.check_output(["ldconfig", "-p"], text=True)
        libraries = {
            "liblsl": "LabStreamingLayer",
            "libcamera": "libcamera",
            "libfuse": "FUSE filesystem",
            "libportaudio": "PortAudio"
        }
        
        for lib, name in libraries.items():
            if lib in ldd_output:
                print(f"✅ {name} library is installed")
            else:
                print(f"❌ {name} library may NOT be installed")
    except Exception as e:
        print(f"⚠️  Could not check system libraries: {e}")

def create_directories():
    """Creates necessary directories."""
    directories = ["recordings", "analysis_reports"]
    
    for directory in directories:
        if not os.path.exists(directory):
            try:
                os.makedirs(directory)
                print(f"✅ Created {directory}/ directory")
            except Exception as e:
                print(f"❌ Failed to create {directory}/ directory: {e}")
        else:
            print(f"✅ {directory}/ directory already exists")

def check_camera():
    """Tries to detect camera devices."""
    camera_found = False
    
    # Check for Raspberry Pi camera
    try:
        from picamera2 import Picamera2
        picam2 = Picamera2()
        print(f"✅ PiCamera2 found: {picam2.camera_properties.get('Model', 'Unknown')}")
        picam2.close()
        camera_found = True
    except Exception as e:
        print(f"ℹ️  PiCamera2 not detected: {e}")
    
    # Check for OpenCV cameras
    try:
        import cv2
        # Try to open the default camera
        cap = cv2.VideoCapture(0)
        if cap.isOpened():
            print(f"✅ Webcam found at index 0")
            cap.release()
            camera_found = True
        else:
            print("ℹ️  No webcam found at index 0")
    except Exception as e:
        print(f"ℹ️  Could not check webcam: {e}")
        
    if not camera_found:
        print("❌ WARNING: No cameras detected. Please check your connections.")

def check_lsl():
    """Tests LSL functionality by creating a test stream."""
    try:
        from pylsl import StreamInfo, StreamOutlet, local_clock
        
        # Create a test stream
        info = StreamInfo("TestStream", "Markers", 1, 0, 'string', 'test123')
        outlet = StreamOutlet(info)
        
        # Push a sample
        outlet.push_sample(["Test"])
        print(f"✅ Created and used an LSL test stream successfully")
    except Exception as e:
        print(f"❌ Could not test LSL functionality: {e}")

def main():
    """Main function."""
    print("===== Environment Check =====")
    
    # Check Python version
    python_version = ".".join(map(str, sys.version_info[:3]))
    if sys.version_info >= (3, 7):
        print(f"✅ Python version {python_version} (3.7+ required)")
    else:
        print(f"❌ Python version {python_version} (3.7+ required)")
    
    # Check required modules
    required_modules = [
        ("numpy", "NumPy"),
        ("cv2", "OpenCV"),
        ("pylsl", "pylsl"),
        ("scipy", "SciPy"),
        ("sounddevice", "SoundDevice"),
        ("matplotlib", "Matplotlib"),
        ("requests", "Requests")
    ]
    
    for module, name in required_modules:
        check_module(module, name)
    
    # Check system libraries
    check_system_libraries()
    
    # Create necessary directories
    create_directories()
    
    # Check for cameras
    check_camera()
    
    # Test LSL
    check_lsl()
    
    print("\n===== Check Complete =====")
    print("If any issues were detected, please refer to the README.md for installation instructions.")
    print("To start capturing, run: rpi-lsl-stream")

if __name__ == "__main__":
    main() 