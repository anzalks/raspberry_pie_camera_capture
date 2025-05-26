#!/usr/bin/env python3
"""
IMX296 Camera Status Monitor
===========================

Real-time terminal UI for monitoring the IMX296 camera service status.
Displays LSL streaming, buffer status, recording status, and system information
with minimal processor overhead using Python curses.

Author: Anzal KS <anzal.ks@gmail.com>
Date: December 2024
"""

import os
import sys
import json
import time
import curses
import datetime
import threading
from pathlib import Path
from typing import Dict, Any, Optional

# Status file location in shared memory
STATUS_FILE = "/dev/shm/imx296_status.json"
UPDATE_INTERVAL = 1.0  # Update every 1 second

class CameraStatusMonitor:
    """Terminal UI status monitor for IMX296 camera service."""
    
    def __init__(self):
        self.running = False
        self.status_data = {}
        self.last_update = 0
        self.start_time = time.time()
        
    def load_status(self) -> Dict[str, Any]:
        """Load status data from shared memory file."""
        try:
            if os.path.exists(STATUS_FILE):
                with open(STATUS_FILE, 'r') as f:
                    return json.load(f)
        except (json.JSONDecodeError, IOError, OSError):
            pass
        
        # Return default status if file doesn't exist or can't be read
        return {
            'service_running': False,
            'uptime': 0,
            'lsl_status': {
                'connected': False,
                'samples_sent': 0,
                'samples_per_second': 0.0,
                'last_sample': [0, 0, 0]
            },
            'buffer_status': {
                'current_size': 0,
                'max_size': 1500,
                'utilization_percent': 0.0,
                'oldest_frame_age': 0
            },
            'recording_status': {
                'active': False,
                'current_file': None,
                'frames_recorded': 0,
                'duration': 0
            },
            'video_status': {
                'recording': False,
                'current_file': None,
                'duration': 0
            },
            'trigger_status': {
                'last_trigger_type': 0,
                'last_trigger_time': 0,
                'trigger_count': 0
            },
            'system_info': {
                'cpu_percent': 0.0,
                'memory_percent': 0.0,
                'disk_usage_percent': 0.0
            }
        }
    
    def format_uptime(self, seconds: float) -> str:
        """Format uptime in human-readable format."""
        if seconds < 60:
            return f"{seconds:.0f}s"
        elif seconds < 3600:
            minutes = seconds // 60
            secs = seconds % 60
            return f"{minutes:.0f}m {secs:.0f}s"
        else:
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            return f"{hours:.0f}h {minutes:.0f}m"
    
    def format_file_size(self, size_bytes: int) -> str:
        """Format file size in human-readable format."""
        if size_bytes < 1024:
            return f"{size_bytes}B"
        elif size_bytes < 1024**2:
            return f"{size_bytes/1024:.1f}KB"
        elif size_bytes < 1024**3:
            return f"{size_bytes/(1024**2):.1f}MB"
        else:
            return f"{size_bytes/(1024**3):.1f}GB"
    
    def get_trigger_type_name(self, trigger_type: int) -> str:
        """Get human-readable trigger type name."""
        trigger_names = {0: "None", 1: "Keyboard", 2: "ntfy"}
        return trigger_names.get(trigger_type, "Unknown")
    
    def draw_header(self, stdscr, y_pos: int) -> int:
        """Draw the header section."""
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        monitor_uptime = time.time() - self.start_time
        
        stdscr.addstr(y_pos, 0, "═" * 80, curses.A_BOLD)
        y_pos += 1
        
        title = "IMX296 CAMERA SERVICE STATUS MONITOR"
        stdscr.addstr(y_pos, (80 - len(title)) // 2, title, curses.A_BOLD | curses.A_REVERSE)
        y_pos += 1
        
        stdscr.addstr(y_pos, 0, f"Current Time: {current_time}")
        stdscr.addstr(y_pos, 40, f"Monitor Uptime: {self.format_uptime(monitor_uptime)}")
        y_pos += 1
        
        stdscr.addstr(y_pos, 0, "═" * 80, curses.A_BOLD)
        y_pos += 2
        
        return y_pos
    
    def draw_service_status(self, stdscr, y_pos: int) -> int:
        """Draw service status section."""
        service_running = self.status_data.get('service_running', False)
        uptime = self.status_data.get('uptime', 0)
        
        # Service status
        status_text = "RUNNING" if service_running else "STOPPED"
        status_color = curses.A_BOLD if service_running else curses.A_BOLD | curses.A_BLINK
        
        stdscr.addstr(y_pos, 0, "SERVICE STATUS: ", curses.A_BOLD)
        stdscr.addstr(y_pos, 16, status_text, status_color)
        
        if service_running:
            stdscr.addstr(y_pos, 30, f"Uptime: {self.format_uptime(uptime)}")
        
        y_pos += 2
        return y_pos
    
    def draw_lsl_status(self, stdscr, y_pos: int) -> int:
        """Draw LSL streaming status section."""
        lsl_status = self.status_data.get('lsl_status', {})
        
        stdscr.addstr(y_pos, 0, "LSL STREAMING:", curses.A_BOLD)
        y_pos += 1
        
        # Connection status
        connected = lsl_status.get('connected', False)
        conn_text = "CONNECTED" if connected else "DISCONNECTED"
        conn_color = curses.A_NORMAL if connected else curses.A_BLINK
        
        stdscr.addstr(y_pos, 2, f"Status: {conn_text}", conn_color)
        stdscr.addstr(y_pos, 25, f"Rate: {lsl_status.get('samples_per_second', 0):.1f} Hz")
        stdscr.addstr(y_pos, 45, f"Total: {lsl_status.get('samples_sent', 0):,}")
        y_pos += 1
        
        # Channel data
        last_sample = lsl_status.get('last_sample', [0, 0, 0])
        stdscr.addstr(y_pos, 2, "Channels:", curses.A_UNDERLINE)
        y_pos += 1
        
        stdscr.addstr(y_pos, 4, f"frame_number: {last_sample[0]:,}")
        y_pos += 1
        
        trigger_time = last_sample[1]
        if trigger_time > 0:
            dt = datetime.datetime.fromtimestamp(trigger_time)
            time_str = dt.strftime("%H:%M:%S.%f")[:-3]
        else:
            time_str = "N/A"
        stdscr.addstr(y_pos, 4, f"trigger_time: {time_str}")
        y_pos += 1
        
        trigger_type = int(last_sample[2])
        trigger_name = self.get_trigger_type_name(trigger_type)
        stdscr.addstr(y_pos, 4, f"trigger_type: {trigger_name} ({trigger_type})")
        y_pos += 2
        
        return y_pos
    
    def draw_buffer_status(self, stdscr, y_pos: int) -> int:
        """Draw rolling buffer status section."""
        buffer_status = self.status_data.get('buffer_status', {})
        
        stdscr.addstr(y_pos, 0, "ROLLING BUFFER:", curses.A_BOLD)
        y_pos += 1
        
        current_size = buffer_status.get('current_size', 0)
        max_size = buffer_status.get('max_size', 1500)
        utilization = buffer_status.get('utilization_percent', 0.0)
        
        stdscr.addstr(y_pos, 2, f"Size: {current_size:,} / {max_size:,} frames")
        stdscr.addstr(y_pos, 35, f"Utilization: {utilization:.1f}%")
        y_pos += 1
        
        # Progress bar for buffer utilization
        bar_width = 40
        filled = int(bar_width * utilization / 100)
        bar = "█" * filled + "░" * (bar_width - filled)
        stdscr.addstr(y_pos, 2, f"[{bar}]")
        y_pos += 2
        
        return y_pos
    
    def draw_recording_status(self, stdscr, y_pos: int) -> int:
        """Draw recording status section."""
        recording_status = self.status_data.get('recording_status', {})
        video_status = self.status_data.get('video_status', {})
        
        stdscr.addstr(y_pos, 0, "RECORDING STATUS:", curses.A_BOLD)
        y_pos += 1
        
        # Main recording
        recording_active = recording_status.get('active', False)
        rec_text = "ACTIVE" if recording_active else "INACTIVE"
        rec_color = curses.A_BOLD if recording_active else curses.A_DIM
        
        stdscr.addstr(y_pos, 2, f"Main Recording: {rec_text}", rec_color)
        
        if recording_active:
            frames = recording_status.get('frames_recorded', 0)
            duration = recording_status.get('duration', 0)
            stdscr.addstr(y_pos, 25, f"Frames: {frames:,}")
            stdscr.addstr(y_pos, 40, f"Duration: {self.format_uptime(duration)}")
        
        y_pos += 1
        
        # Video recording
        video_recording = video_status.get('recording', False)
        vid_text = "ACTIVE" if video_recording else "INACTIVE"
        vid_color = curses.A_BOLD if video_recording else curses.A_DIM
        
        stdscr.addstr(y_pos, 2, f"Video Recording: {vid_text}", vid_color)
        
        if video_recording:
            vid_duration = video_status.get('duration', 0)
            stdscr.addstr(y_pos, 25, f"Duration: {self.format_uptime(vid_duration)}")
        
        y_pos += 1
        
        # Current files
        current_file = recording_status.get('current_file')
        if current_file:
            filename = os.path.basename(current_file)
            stdscr.addstr(y_pos, 2, f"File: {filename}")
        
        y_pos += 2
        return y_pos
    
    def draw_trigger_status(self, stdscr, y_pos: int) -> int:
        """Draw trigger status section."""
        trigger_status = self.status_data.get('trigger_status', {})
        
        stdscr.addstr(y_pos, 0, "TRIGGER STATUS:", curses.A_BOLD)
        y_pos += 1
        
        last_trigger_type = trigger_status.get('last_trigger_type', 0)
        last_trigger_time = trigger_status.get('last_trigger_time', 0)
        trigger_count = trigger_status.get('trigger_count', 0)
        
        trigger_name = self.get_trigger_type_name(last_trigger_type)
        stdscr.addstr(y_pos, 2, f"Last Trigger: {trigger_name}")
        stdscr.addstr(y_pos, 25, f"Total Triggers: {trigger_count}")
        y_pos += 1
        
        if last_trigger_time > 0:
            dt = datetime.datetime.fromtimestamp(last_trigger_time)
            time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
            time_ago = time.time() - last_trigger_time
            stdscr.addstr(y_pos, 2, f"Time: {time_str} ({self.format_uptime(time_ago)} ago)")
        else:
            stdscr.addstr(y_pos, 2, "Time: No triggers yet")
        
        y_pos += 2
        return y_pos
    
    def draw_system_info(self, stdscr, y_pos: int) -> int:
        """Draw system information section."""
        system_info = self.status_data.get('system_info', {})
        
        stdscr.addstr(y_pos, 0, "SYSTEM INFO:", curses.A_BOLD)
        y_pos += 1
        
        cpu_percent = system_info.get('cpu_percent', 0.0)
        memory_percent = system_info.get('memory_percent', 0.0)
        disk_percent = system_info.get('disk_usage_percent', 0.0)
        
        stdscr.addstr(y_pos, 2, f"CPU: {cpu_percent:.1f}%")
        stdscr.addstr(y_pos, 15, f"Memory: {memory_percent:.1f}%")
        stdscr.addstr(y_pos, 30, f"Disk: {disk_percent:.1f}%")
        y_pos += 2
        
        return y_pos
    
    def draw_footer(self, stdscr, y_pos: int) -> int:
        """Draw footer with controls."""
        stdscr.addstr(y_pos, 0, "═" * 80, curses.A_BOLD)
        y_pos += 1
        
        stdscr.addstr(y_pos, 0, "Controls: 'q' = Quit, 'r' = Refresh, 'c' = Clear", curses.A_DIM)
        stdscr.addstr(y_pos, 50, f"Last Update: {datetime.datetime.fromtimestamp(self.last_update).strftime('%H:%M:%S')}", curses.A_DIM)
        
        return y_pos
    
    def draw_screen(self, stdscr):
        """Draw the complete status screen."""
        height, width = stdscr.getmaxyx()
        stdscr.clear()
        
        y_pos = 0
        
        try:
            # Draw all sections
            y_pos = self.draw_header(stdscr, y_pos)
            y_pos = self.draw_service_status(stdscr, y_pos)
            y_pos = self.draw_lsl_status(stdscr, y_pos)
            y_pos = self.draw_buffer_status(stdscr, y_pos)
            y_pos = self.draw_recording_status(stdscr, y_pos)
            y_pos = self.draw_trigger_status(stdscr, y_pos)
            y_pos = self.draw_system_info(stdscr, y_pos)
            
            # Draw footer at bottom
            footer_y = height - 2
            if footer_y > y_pos:
                self.draw_footer(stdscr, footer_y)
            
        except curses.error:
            # Handle screen too small
            stdscr.addstr(0, 0, "Terminal too small! Please resize to at least 80x25", curses.A_BLINK)
        
        stdscr.refresh()
    
    def run(self, stdscr):
        """Main run loop for the status monitor."""
        # Configure curses
        curses.curs_set(0)  # Hide cursor
        stdscr.nodelay(1)   # Non-blocking input
        stdscr.timeout(100) # 100ms timeout for getch()
        
        # Initialize colors if available
        if curses.has_colors():
            curses.start_colors()
        
        self.running = True
        
        while self.running:
            # Load latest status data
            self.status_data = self.load_status()
            self.last_update = time.time()
            
            # Draw screen
            self.draw_screen(stdscr)
            
            # Handle input
            try:
                key = stdscr.getch()
                if key == ord('q') or key == ord('Q'):
                    self.running = False
                elif key == ord('r') or key == ord('R'):
                    # Force refresh
                    pass
                elif key == ord('c') or key == ord('C'):
                    # Clear screen
                    stdscr.clear()
            except:
                pass
            
            # Sleep for update interval
            time.sleep(UPDATE_INTERVAL)


def main():
    """Main function to run the status monitor."""
    try:
        # Check if status file exists
        if not os.path.exists(STATUS_FILE):
            print(f"Warning: Status file {STATUS_FILE} not found.")
            print("Make sure the IMX296 camera service is running.")
            print("Starting monitor anyway...")
            time.sleep(2)
        
        # Initialize and run monitor
        monitor = CameraStatusMonitor()
        curses.wrapper(monitor.run)
        
    except KeyboardInterrupt:
        print("\nStatus monitor stopped by user.")
    except Exception as e:
        print(f"Error running status monitor: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main()) 