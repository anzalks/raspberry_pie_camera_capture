"""
Status display for camera capture system.

This module provides a real-time terminal dashboard for
monitoring the camera capture system with visual indicators
and status updates.

Author: Anzal
Email: anzal.ks@gmail.com
GitHub: https://github.com/anzalks/
"""

import os
import sys
import time
import threading
import logging
import traceback
from datetime import datetime

logger = logging.getLogger('StatusDisplay')

class StatusDisplay:
    """Terminal-based status display for camera capture."""
    
    def __init__(self, camera_streamer=None, buffer_manager=None, ntfy_topic=None, update_interval=0.5):
        """
        Initialize the status display.
        
        Args:
            camera_streamer: LSLCameraStreamer instance
            buffer_manager: BufferTriggerManager instance 
            ntfy_topic: NTFY topic for notifications
            update_interval: Update interval in seconds
        """
        self.camera_streamer = camera_streamer
        self.buffer_manager = buffer_manager
        self.ntfy_topic = ntfy_topic
        self.update_interval = update_interval
        self.stop_event = threading.Event()
        self.display_thread = None
        self.last_notification = "None"
        self.notification_time = None
        self.start_time = time.time()
        self.frame_rate_history = []
        self.frame_count_prev = 0
        self.last_update_time = time.time()
        self.prev_terminal_width = 0
        self.prev_terminal_height = 0
        
    def start(self):
        """Start the status display thread."""
        if self.display_thread is not None:
            return
            
        self.stop_event.clear()
        self.display_thread = threading.Thread(target=self._display_loop, daemon=True)
        self.display_thread.start()
        logger.info("Status display started")
        
    def stop(self):
        """Stop the status display thread."""
        if self.display_thread is None:
            return
            
        self.stop_event.set()
        self.display_thread.join(timeout=2.0)
        self.display_thread = None
        logger.info("Status display stopped")
        
    def notify(self, message):
        """Record a notification message to display."""
        self.last_notification = message
        self.notification_time = time.time()
        logger.info(f"Notification: {message}")
        
    def _get_terminal_size(self):
        """Get terminal size with fallback values for non-terminal environments."""
        try:
            terminal_width, terminal_height = os.get_terminal_size()
            # Enforce minimum size to prevent layout issues
            terminal_width = max(terminal_width, 80)
            terminal_height = max(terminal_height, 24)
            
            # Check if terminal size has changed
            size_changed = (terminal_width != self.prev_terminal_width or 
                           terminal_height != self.prev_terminal_height)
            
            # Update stored values
            self.prev_terminal_width = terminal_width
            self.prev_terminal_height = terminal_height
            
            return terminal_width, terminal_height, size_changed
        except (OSError, AttributeError):
            # Default fallback values
            return 80, 24, False
        
    def update(self):
        """Update the display with current information."""
        if not self.camera_streamer:
            return
            
        info = self.camera_streamer.get_info() if hasattr(self.camera_streamer, 'get_info') else {}
        
        # Get buffer info
        buffer_size = 0
        buffer_duration = 0.0
        recording_active = False
        
        if self.buffer_manager:
            buffer_size = self.buffer_manager.get_buffer_size() if hasattr(self.buffer_manager, 'get_buffer_size') else 0
            buffer_duration = self.buffer_manager.get_buffer_duration() if hasattr(self.buffer_manager, 'get_buffer_duration') else 0.0
            recording_active = False
            if hasattr(self.camera_streamer, 'waiting_for_trigger'):
                recording_active = not self.camera_streamer.waiting_for_trigger
            
        # Calculate current frame rate
        now = time.time()
        elapsed = now - self.last_update_time
        
        current_count = 0
        if hasattr(self.camera_streamer, 'get_frame_count'):
            current_count = self.camera_streamer.get_frame_count()
        
        frames_since_last = current_count - self.frame_count_prev
        
        if elapsed > 0:
            current_fps = frames_since_last / elapsed
            self.frame_rate_history.append(current_fps)
            if len(self.frame_rate_history) > 10:
                self.frame_rate_history.pop(0)
        
        self.frame_count_prev = current_count
        self.last_update_time = now
        
        # Get average fps from history
        avg_fps = sum(self.frame_rate_history) / max(len(self.frame_rate_history), 1)
        
        # Calculate uptime
        uptime_seconds = int(now - self.start_time)
        uptime_str = f"{uptime_seconds // 3600:02}:{(uptime_seconds % 3600) // 60:02}:{uptime_seconds % 60:02}"
        
        # Get terminal size with detection of size changes
        terminal_width, terminal_height, size_changed = self._get_terminal_size()
        
        # Clear screen - use full reset if terminal size changed
        if size_changed:
            os.system('clear' if os.name == 'posix' else 'cls')
        else:
            # Fast cursor return to home position for less flicker
            print("\033[H", end="")
            
        # Draw header
        header = " Pi Camera Capture - Status Dashboard "
        header_pad = (terminal_width - len(header)) // 2
        print("╔" + "═" * (terminal_width - 2) + "╗")
        print("║" + " " * header_pad + header + " " * (terminal_width - len(header) - header_pad - 2) + "║")
        print("╠" + "═" * (terminal_width - 2) + "╣")
        
        # Draw system info section
        print(f"║ System Status{' ' * (terminal_width - 16)}║")
        print(f"║ • Uptime: {uptime_str}{' ' * (terminal_width - 13 - len(uptime_str))}║")
        
        # Safe access to info dictionary with fallbacks
        source_type = info.get('source_type', 'Camera')
        width = info.get('width', 0)
        height = info.get('height', 0)
        codec = info.get('codec', 'Unknown')
        actual_fps = info.get('actual_fps', 0.0)
        
        print(f"║ • Camera: {source_type} ({width}x{height}){' ' * (terminal_width - 16 - len(source_type) - len(str(width)) - len(str(height)) - 5)}║")
        print(f"║ • Codec: {codec}{' ' * (terminal_width - 12 - len(str(codec)))}║")
        
        # Draw recording status
        status_color = "\033[92m" if recording_active else "\033[93m"  # Green if recording, yellow if waiting
        status_text = "RECORDING" if recording_active else "BUFFERING"
        status_reset = "\033[0m"
        print(f"║ • Status: {status_color}{status_text}{status_reset}{' ' * (terminal_width - 13 - len(status_text))}║")
        
        # Draw buffer info section
        print("╠" + "═" * (terminal_width - 2) + "╣")
        print(f"║ Buffer Status{' ' * (terminal_width - 16)}║")
        
        # Safely get buffer size seconds
        buffer_size_seconds = 20.0  # Default fallback
        if hasattr(self.camera_streamer, 'buffer_size_seconds'):
            buffer_size_seconds = self.camera_streamer.buffer_size_seconds
        
        # Create buffer fill visual indicator
        buffer_percent = 0
        if buffer_size_seconds > 0:
            buffer_percent = min(100, int((buffer_duration / buffer_size_seconds) * 100))
        
        indicator_width = max(10, terminal_width - 28)  # Ensure minimum width for tiny terminals
        filled_chars = int((buffer_percent / 100) * indicator_width)
        buffer_indicator = "█" * filled_chars + "░" * (indicator_width - filled_chars)
        
        print(f"║ • Frames in buffer: {buffer_size}{' ' * (terminal_width - 23 - len(str(buffer_size)))}║")
        print(f"║ • Buffer duration: {buffer_duration:.1f}s / {buffer_size_seconds:.1f}s{' ' * (terminal_width - 23 - len(f'{buffer_duration:.1f}') - len(f'{buffer_size_seconds:.1f}') - 4)}║")
        print(f"║ • Buffer fill: [{buffer_indicator}] {buffer_percent}%{' ' * (terminal_width - 20 - indicator_width - len(str(buffer_percent)) - 3)}║")
        
        # Draw frame statistics section
        print("╠" + "═" * (terminal_width - 2) + "╣")
        print(f"║ Frame Statistics{' ' * (terminal_width - 18)}║")
        print(f"║ • Target FPS: {actual_fps:.1f}{' ' * (terminal_width - 16 - len(f'{actual_fps:.1f}'))}║")
        print(f"║ • Current FPS: {avg_fps:.1f}{' ' * (terminal_width - 17 - len(f'{avg_fps:.1f}'))}║")
        
        # Safe access to frame counts
        frames_captured = 0
        frames_written = 0
        frames_dropped = 0
        
        if hasattr(self.camera_streamer, 'get_frame_count'):
            frames_captured = self.camera_streamer.get_frame_count()
        if hasattr(self.camera_streamer, 'get_frames_written'):
            frames_written = self.camera_streamer.get_frames_written()
        if hasattr(self.camera_streamer, 'get_frames_dropped'):
            frames_dropped = self.camera_streamer.get_frames_dropped()
            
        print(f"║ • Frames captured: {frames_captured}{' ' * (terminal_width - 21 - len(str(frames_captured)))}║")
        print(f"║ • Frames written: {frames_written}{' ' * (terminal_width - 20 - len(str(frames_written)))}║")
        print(f"║ • Frames dropped: {frames_dropped}{' ' * (terminal_width - 20 - len(str(frames_dropped)))}║")
        
        # Draw notification section
        print("╠" + "═" * (terminal_width - 2) + "╣")
        print(f"║ Notification Status{' ' * (terminal_width - 21)}║")
        ntfy_topic_display = self.ntfy_topic if self.ntfy_topic else "Not configured"
        print(f"║ • NTFY Topic: {ntfy_topic_display}{' ' * (terminal_width - 16 - len(str(ntfy_topic_display)))}║")
        
        # If we have a notification time, show how long ago it was received
        notification_age = ""
        if self.notification_time:
            age_seconds = int(now - self.notification_time)
            if age_seconds < 60:
                notification_age = f"({age_seconds}s ago)"
            else:
                notification_age = f"({age_seconds // 60}m {age_seconds % 60}s ago)"
        
        # Truncate notification if needed to fit in terminal
        max_notification_len = max(10, terminal_width - 40)  # Give at least 10 chars for notification
        notification_display = self.last_notification
        if len(notification_display) > max_notification_len:
            notification_display = notification_display[:max_notification_len-3] + "..."
                
        print(f"║ • Last notification: {notification_display} {notification_age}{' ' * (terminal_width - 22 - len(notification_display) - len(notification_age) - 1)}║")
        
        # Draw keyboard commands
        print("╠" + "═" * (terminal_width - 2) + "╣")
        print(f"║ Keyboard Controls{' ' * (terminal_width - 19)}║")
        print(f"║ • [S] Start Recording  • [X] Stop Recording  • [Q] Quit{' ' * (terminal_width - 56)}║")
        print("╚" + "═" * (terminal_width - 2) + "╝")
        
        # Fill remaining lines with empty space if terminal is taller than our dashboard
        dashboard_height = 19  # Approximate number of lines in our dashboard
        for _ in range(max(0, terminal_height - dashboard_height - 1)):
            print()
        
        # Flush output to ensure it's displayed immediately
        sys.stdout.flush() 
        
    def _display_loop(self):
        """Thread function to update the display periodically."""
        try:
            # Hide cursor for cleaner display
            if os.name == 'posix':
                os.system('tput civis')
                
            while not self.stop_event.is_set():
                try:
                    self.update()
                    time.sleep(self.update_interval)
                except Exception as e:
                    logger.error(f"Error updating status display: {e}")
                    traceback.print_exc()
                    time.sleep(1.0)
        finally:
            # Restore cursor
            if os.name == 'posix':
                os.system('tput cnorm')
                # Clear screen on exit
                os.system('clear') 