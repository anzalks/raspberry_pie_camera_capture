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

def get_device_info(device_path):
    """Get detailed information about a video device"""
    try:
        result = subprocess.run(['v4l2-ctl', '--device', device_path, '--all'], 
                              capture_output=True, text=True)
        return result.stdout
    except Exception as e:
        return f"Error getting device info: {e}"

def test_camera():
    print("Starting camera test...")
    print(f"Operating System: {platform.system()}")
    
    # First, let's check if we're using a Raspberry Pi camera
    if os.path.exists('/dev/video0'):
        print("\nChecking Raspberry Pi camera interface...")
        device_info = get_device_info('/dev/video0')
        print(device_info)
        
        # Try to open the camera with specific settings
        print("\nAttempting to open camera with specific settings...")
        cap = cv2.VideoCapture(0, cv2.CAP_V4L2)
        
        if not cap.isOpened():
            print("Error: Could not open camera!")
            return
        
        # Set specific camera properties
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M', 'J', 'P', 'G'))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap.set(cv2.CAP_PROP_FPS, 30)
        
        print("\nCamera properties after setting:")
        print(f"Resolution: {cap.get(cv2.CAP_PROP_FRAME_WIDTH)}x{cap.get(cv2.CAP_PROP_FRAME_HEIGHT)}")
        print(f"FPS: {cap.get(cv2.CAP_PROP_FPS)}")
        print(f"Format: {cap.get(cv2.CAP_PROP_FOURCC)}")
        
        # Try to read a frame
        print("\nAttempting to read frame...")
        ret, frame = cap.read()
        if not ret:
            print("Error: Could not read frame!")
            cap.release()
            return
        
        print("Successfully read a frame!")
        
        # Display the frame
        cv2.namedWindow('Camera Test', cv2.WINDOW_NORMAL)
        cv2.imshow('Camera Test', frame)
        print("Displaying frame. Press 'q' to quit...")
        
        # Keep displaying frames for 5 seconds
        start_time = time.time()
        while time.time() - start_time < 5:
            ret, frame = cap.read()
            if ret:
                cv2.imshow('Camera Test', frame)
            
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
        
        # Cleanup
        cap.release()
        cv2.destroyAllWindows()
    else:
        print("Error: No video device found at /dev/video0")
    
    print("\nTest completed!")

if __name__ == "__main__":
    test_camera() 