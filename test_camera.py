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

def test_camera():
    print("Starting camera test...")
    print(f"Operating System: {platform.system()}")
    
    # Try to detect available cameras
    if platform.system() == 'Linux':
        # Check for video devices on Linux
        video_devices = glob.glob('/dev/video*')
        print(f"Found video devices: {video_devices}")
    
    # Try to open the camera
    print("Attempting to open camera...")
    cap = cv2.VideoCapture(0)
    
    if not cap.isOpened():
        print("Error: Could not open camera!")
        return
    
    print("Camera opened successfully!")
    print(f"Camera properties:")
    print(f"Resolution: {cap.get(cv2.CAP_PROP_FRAME_WIDTH)}x{cap.get(cv2.CAP_PROP_FRAME_HEIGHT)}")
    print(f"FPS: {cap.get(cv2.CAP_PROP_FPS)}")
    
    # Try to read a frame
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
    print("Test completed!")

if __name__ == "__main__":
    test_camera() 