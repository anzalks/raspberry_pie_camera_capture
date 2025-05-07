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

def set_camera_properties(device_path):
    """Set camera properties using v4l2-ctl"""
    try:
        # Set the format to BGR3 (which is what the camera supports)
        subprocess.run(['v4l2-ctl', '--device', device_path, 
                       '--set-fmt-video=width=640,height=480,pixelformat=BGR3'])
        # Set the FPS
        subprocess.run(['v4l2-ctl', '--device', device_path, 
                       '--set-ctrl=video_bitrate=10000000'])
        return True
    except Exception as e:
        print(f"Error setting camera properties: {e}")
        return False

def test_camera():
    print("Starting camera test...")
    print(f"Operating System: {platform.system()}")
    
    # First, let's check if we're using a Raspberry Pi camera
    if os.path.exists('/dev/video0'):
        print("\nChecking Raspberry Pi camera interface...")
        device_info = get_device_info('/dev/video0')
        print(device_info)
        
        # Set camera properties using v4l2-ctl
        print("\nSetting camera properties...")
        if not set_camera_properties('/dev/video0'):
            print("Warning: Could not set camera properties using v4l2-ctl")
        
        # Try to open the camera with specific settings
        print("\nAttempting to open camera with specific settings...")
        cap = cv2.VideoCapture(0, cv2.CAP_V4L2)
        
        if not cap.isOpened():
            print("Error: Could not open camera!")
            return
        
        # Set specific camera properties
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('B', 'G', 'R', '3'))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap.set(cv2.CAP_PROP_FPS, 30)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Minimize buffer size
        
        print("\nCamera properties after setting:")
        print(f"Resolution: {cap.get(cv2.CAP_PROP_FRAME_WIDTH)}x{cap.get(cv2.CAP_PROP_FRAME_HEIGHT)}")
        print(f"FPS: {cap.get(cv2.CAP_PROP_FPS)}")
        print(f"Format: {cap.get(cv2.CAP_PROP_FOURCC)}")
        
        # Try to read a frame with retry
        print("\nAttempting to read frame...")
        max_retries = 5
        for attempt in range(max_retries):
            ret, frame = cap.read()
            if ret and frame is not None and frame.size > 0:
                print(f"Successfully read frame on attempt {attempt + 1}!")
                break
            print(f"Failed to read frame on attempt {attempt + 1}")
            time.sleep(0.5)  # Wait a bit before retrying
        
        if not ret or frame is None or frame.size == 0:
            print("Error: Could not read frame after multiple attempts!")
            cap.release()
            return
        
        # Display the frame
        cv2.namedWindow('Camera Test', cv2.WINDOW_NORMAL)
        cv2.imshow('Camera Test', frame)
        print("Displaying frame. Press 'q' to quit...")
        
        # Keep displaying frames for 5 seconds
        start_time = time.time()
        while time.time() - start_time < 5:
            ret, frame = cap.read()
            if ret and frame is not None and frame.size > 0:
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