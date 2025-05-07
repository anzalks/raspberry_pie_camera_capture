"""
Status display for camera capture system.

This module provides a simple terminal-based status display for
monitoring the camera capture system.

Author: Anzal
Email: anzal.ks@gmail.com
GitHub: https://github.com/anzalks/
"""

import os
import sys
import time
import threading
import logging
from datetime import datetime

logger = logging.getLogger('StatusDisplay')

class StatusDisplay:
    """Terminal-based status display for camera capture."""
    
    def __init__(self, camera_streamer=None, buffer_manager=None, ntfy_topic=None):
        """
        Initialize the status display.
        
        Args:
            camera_streamer: LSLCameraStreamer instance
            buffer_manager: BufferTriggerManager instance 
            ntfy_topic: NTFY topic for notifications
        """
        self.camera_streamer = camera_streamer
        self.buffer_manager = buffer_manager
        self.ntfy_topic = ntfy_topic
        self.last_notification = "No notifications yet"
        self.last_update_time = time.time()
        self.fps = 0
        self.frame_times = []
        self._lock = threading.RLock()
        
    def notify(self, message):
        """Display a notification message."""
        with self._lock:
            self.last_notification = message
            logger.info(f"Notification: {message}")
            self._print_status()
    
    def update(self):
        """Update the status display."""
        with self._lock:
            now = time.time()
            
            # Calculate FPS
            self.frame_times.append(now)
            # Keep only the last 30 frame times for FPS calculation
            while len(self.frame_times) > 30 and (now - self.frame_times[0]) > 5:
                self.frame_times.pop(0)
                
            if len(self.frame_times) > 1:
                self.fps = (len(self.frame_times) - 1) / (self.frame_times[-1] - self.frame_times[0])
            
            # Only update the display every 0.5 seconds to reduce flickering
            if now - self.last_update_time > 0.5:
                self.last_update_time = now
                self._print_status()
    
    def _print_status(self):
        """Print the current status to the terminal."""
        # Clear the terminal
        os.system('cls' if os.name == 'nt' else 'clear')
        
        # Get current time
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Print header
        header = "=" * 60
        print(f"\n{header}")
        print(f" Raspberry Pi Camera Capture - Status Display")
        print(f" {current_time}")
        print(f"{header}")
        
        # Print camera information
        print("\n[Camera Information]")
        if self.camera_streamer:
            camera_id = getattr(self.camera_streamer, 'camera_id', 'Unknown')
            resolution = f"{getattr(self.camera_streamer, 'width', 0)}x{getattr(self.camera_streamer, 'height', 0)}"
            fps = getattr(self.camera_streamer, 'fps', 0)
            recording = getattr(self.camera_streamer, 'is_recording', False)
            
            print(f"  Camera ID:         {camera_id}")
            print(f"  Resolution:        {resolution}")
            print(f"  Target FPS:        {fps:.1f}")
            print(f"  Current FPS:       {self.fps:.1f}")
            print(f"  Recording Status:  {'Active' if recording else 'Standby'}")
        else:
            print("  Camera not available")
        
        # Print buffer information
        print("\n[Buffer Information]")
        if self.buffer_manager:
            buffer_size = getattr(self.buffer_manager, 'buffer_size', 0)
            frames_in_buffer = getattr(self.buffer_manager, 'frames_in_buffer', 0)
            max_buffer_size = getattr(self.buffer_manager, 'max_buffer_size', 0)
            oldest_frame_age = getattr(self.buffer_manager, 'oldest_frame_age', 0)
            
            print(f"  Buffer Size:       {buffer_size} frames")
            print(f"  Frames in Buffer:  {frames_in_buffer}/{max_buffer_size}")
            print(f"  Buffer Duration:   {oldest_frame_age:.2f} seconds")
        else:
            print("  Buffer not available")
        
        # Print frame statistics
        print("\n[Frame Statistics]")
        if self.camera_streamer:
            frames_captured = getattr(self.camera_streamer, 'frames_captured', 0)
            frames_written = getattr(self.camera_streamer, 'frames_written', 0)
            frames_dropped = getattr(self.camera_streamer, 'frames_dropped', 0)
            
            print(f"  Frames Captured:   {frames_captured}")
            print(f"  Frames Written:    {frames_written}")
            print(f"  Frames Dropped:    {frames_dropped}")
        else:
            print("  Statistics not available")
        
        # Print notification information
        print("\n[Notifications]")
        if self.ntfy_topic:
            print(f"  NTFY Topic:        {self.ntfy_topic}")
            print(f"  Last Message:      {self.last_notification}")
        else:
            print("  NTFY notifications not configured")
        
        # Print footer
        print(f"\n{header}")
        print(" Press Ctrl+C to exit")
        print(f"{header}\n")
        
        # Flush output to ensure it's displayed immediately
        sys.stdout.flush() 