#!/usr/bin/env python3
"""
Simple test script to verify camera detection and display.
Author: Anzal
Email: anzal.ks@gmail.com
"""

import cv2
import time
import platform
import os
import glob
import subprocess

def check_v4l2_info():
    """Check v4l2-ctl information for all video devices"""
    print("\nChecking v4l2-ctl information...")
    try:
        result = subprocess.run(['v4l2-ctl', '--list-devices'], capture_output=True, text=True)
        print(result.stdout)
    except Exception as e:
        print(f"Error running v4l2-ctl: {e}")

def test_camera_device(device_index):
    """Test a specific camera device"""
    print(f"\nTesting camera device {device_index}...")
    cap = cv2.VideoCapture(device_index)
    
    if not cap.isOpened():
        print(f"Error: Could not open camera device {device_index}!")
        return False
    
    print(f"Camera {device_index} opened successfully!")
    
    # Try to set some basic properties
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_FPS, 30)
    
    print(f"Camera properties:")
    print(f"Resolution: {cap.get(cv2.CAP_PROP_FRAME_WIDTH)}x{cap.get(cv2.CAP_PROP_FRAME_HEIGHT)}")
    print(f"FPS: {cap.get(cv2.CAP_PROP_FPS)}")
    
    # Try to read a frame
    ret, frame = cap.read()
    if not ret:
        print(f"Error: Could not read frame from device {device_index}!")
        cap.release()
        return False
    
    print(f"Successfully read a frame from device {device_index}!")
    
    # Display the frame
    cv2.namedWindow(f'Camera Test - Device {device_index}', cv2.WINDOW_NORMAL)
    cv2.imshow(f'Camera Test - Device {device_index}', frame)
    print(f"Displaying frame from device {device_index}. Press 'q' to quit...")
    
    # Keep displaying frames for 5 seconds
    start_time = time.time()
    while time.time() - start_time < 5:
        ret, frame = cap.read()
        if ret:
            cv2.imshow(f'Camera Test - Device {device_index}', frame)
        
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
    
    # Cleanup
    cap.release()
    cv2.destroyAllWindows()
    return True

def test_camera():
    print("Starting camera test...")
    print(f"Operating System: {platform.system()}")
    
    # Check v4l2 information
    check_v4l2_info()
    
    # Try to detect available cameras
    if platform.system() == 'Linux':
        # Check for video devices on Linux
        video_devices = glob.glob('/dev/video*')
        print(f"\nFound video devices: {video_devices}")
        
        # Try each video device
        for device in video_devices:
            device_index = int(device.split('/dev/video')[-1])
            if test_camera_device(device_index):
                print(f"\nSuccessfully tested device {device_index}")
                break
    else:
        # For non-Linux systems, just try the default camera
        test_camera_device(0)
    
    print("\nTest completed!")

if __name__ == "__main__":
    test_camera() 