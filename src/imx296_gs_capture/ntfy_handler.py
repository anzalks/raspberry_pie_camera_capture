#!/usr/bin/env python3
"""
ntfy.sh Handler for Remote Camera Control
=========================================

Handles remote camera control via ntfy.sh notifications.
Supports commands: start_recording, stop_recording, status

Author: Anzal KS <anzal.ks@gmail.com>
Date: May 23, 2025
"""

import requests
import threading
import time
import json
import logging
from typing import Callable, Dict, Any, Optional


class NtfyHandler:
    """Handles ntfy.sh notifications for remote camera control."""
    
    def __init__(self, config: Dict[str, Any], callback_handler: Callable[[str, Dict], None]):
        """
        Initialize ntfy handler.
        
        Args:
            config: ntfy configuration dictionary
            callback_handler: Function to call when commands are received
                             Should accept (command: str, params: Dict)
        """
        self.config = config
        self.callback_handler = callback_handler
        self.logger = logging.getLogger(__name__)
        
        # ntfy configuration
        self.server = self.config.get('server', 'https://ntfy.sh')
        self.topic = self.config.get('topic', 'raspie-camera-dawg-123')
        self.poll_interval = self.config.get('poll_interval_sec', 2)
        
        # State tracking
        self.running = False
        self.poll_thread = None
        self.last_message_id = None
        
        # Supported commands
        self.supported_commands = {
            'start_recording': self._handle_start_recording,
            'stop_recording': self._handle_stop_recording,
            'status': self._handle_status,
            'get_stats': self._handle_get_stats
        }
        
        self.logger.info(f"ntfy handler initialized for topic: {self.topic}")
    
    def start(self):
        """Start the ntfy polling thread."""
        if self.running:
            self.logger.warning("ntfy handler already running")
            return
        
        self.running = True
        self.poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self.poll_thread.start()
        self.logger.info("ntfy polling started")
        
        # Send startup notification
        self._send_notification("Camera system started", "🟢 Ready for commands", tags=["white_check_mark"])
    
    def stop(self):
        """Stop the ntfy polling thread."""
        if not self.running:
            return
        
        self.running = False
        if self.poll_thread and self.poll_thread.is_alive():
            self.poll_thread.join(timeout=5)
        
        self.logger.info("ntfy polling stopped")
        
        # Send shutdown notification
        self._send_notification("Camera system stopped", "🔴 System shutting down", tags=["x"])
    
    def _poll_loop(self):
        """Main polling loop for ntfy messages."""
        self.logger.info(f"Starting ntfy polling for topic: {self.topic}")
        
        while self.running:
            try:
                self._check_messages()
                time.sleep(self.poll_interval)
            except Exception as e:
                self.logger.error(f"Error in ntfy polling loop: {e}")
                time.sleep(self.poll_interval * 2)  # Backoff on error
    
    def _check_messages(self):
        """Check for new messages from ntfy."""
        try:
            url = f"{self.server}/{self.topic}/json"
            params = {}
            
            # Only get messages since last check
            if self.last_message_id:
                params['since'] = self.last_message_id
            else:
                params['since'] = 'all'  # Get recent messages on first run
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            # Process each line as a separate JSON message
            for line in response.text.strip().split('\n'):
                if not line.strip():
                    continue
                
                try:
                    message = json.loads(line)
                    self._process_message(message)
                except json.JSONDecodeError as e:
                    self.logger.debug(f"Error parsing message JSON: {e}")
                    continue
        
        except requests.RequestException as e:
            self.logger.warning(f"Error checking ntfy messages: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error checking messages: {e}")
    
    def _process_message(self, message: Dict[str, Any]):
        """Process a single ntfy message."""
        try:
            # Update last message ID
            if 'id' in message:
                self.last_message_id = message['id']
            
            # Skip if no message content
            if 'message' not in message:
                return
            
            content = message['message'].strip()
            self.logger.info(f"Received ntfy message: {content}")
            
            # Parse command and parameters
            command_data = self._parse_command(content)
            if not command_data:
                return
            
            command = command_data['command']
            params = command_data.get('params', {})
            
            # Handle supported commands
            if command in self.supported_commands:
                self.supported_commands[command](params)
            else:
                self.logger.warning(f"Unsupported command: {command}")
                self._send_notification(
                    "Unsupported Command",
                    f"❌ Command '{command}' not recognized",
                    tags=["warning"]
                )
        
        except Exception as e:
            self.logger.error(f"Error processing ntfy message: {e}")
    
    def _parse_command(self, content: str) -> Optional[Dict[str, Any]]:
        """Parse command from message content."""
        try:
            # Support both JSON and simple text commands
            if content.startswith('{'):
                # JSON format: {"command": "start_recording", "duration": 30}
                return json.loads(content)
            else:
                # Simple text format: "start_recording 30" or "stop_recording"
                parts = content.split()
                if not parts:
                    return None
                
                command = parts[0].lower()
                params = {}
                
                # Parse simple parameters
                if len(parts) > 1:
                    if command == 'start_recording':
                        try:
                            params['duration'] = float(parts[1])
                        except ValueError:
                            pass
                
                return {'command': command, 'params': params}
        
        except (json.JSONDecodeError, ValueError) as e:
            self.logger.debug(f"Error parsing command '{content}': {e}")
            return None
    
    def _handle_start_recording(self, params: Dict[str, Any]):
        """Handle start recording command."""
        self.logger.info(f"Processing start_recording command with params: {params}")
        
        # Extract duration if provided
        duration = params.get('duration')
        if duration:
            self.logger.info(f"Starting recording for {duration} seconds")
        else:
            self.logger.info("Starting recording (no duration specified)")
        
        # Call the main callback handler
        self.callback_handler('start_recording', params)
    
    def _handle_stop_recording(self, params: Dict[str, Any]):
        """Handle stop recording command."""
        self.logger.info("Processing stop_recording command")
        self.callback_handler('stop_recording', params)
    
    def _handle_status(self, params: Dict[str, Any]):
        """Handle status request command."""
        self.logger.info("Processing status command")
        self.callback_handler('status', params)
    
    def _handle_get_stats(self, params: Dict[str, Any]):
        """Handle get stats command."""
        self.logger.info("Processing get_stats command")
        self.callback_handler('get_stats', params)
    
    def _send_notification(self, title: str, message: str, tags: list = None, priority: int = 3):
        """Send a notification via ntfy."""
        try:
            url = f"{self.server}/{self.topic}"
            
            data = {
                'title': title,
                'message': message,
                'priority': priority
            }
            
            if tags:
                data['tags'] = tags
            
            response = requests.post(url, json=data, timeout=10)
            response.raise_for_status()
            
            self.logger.debug(f"Sent ntfy notification: {title}")
        
        except requests.RequestException as e:
            self.logger.warning(f"Failed to send ntfy notification: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error sending notification: {e}")
    
    def send_recording_started(self, output_file: str, duration: Optional[float] = None):
        """Send notification when recording starts."""
        duration_text = f" for {duration}s" if duration else ""
        self._send_notification(
            "Recording Started",
            f"🔴 Recording{duration_text}\nFile: {output_file}",
            tags=["movie_camera"]
        )
    
    def send_recording_stopped(self, stats: Dict[str, Any]):
        """Send notification when recording stops."""
        frame_count = stats.get('frame_count', 0)
        duration = stats.get('duration', 0)
        
        self._send_notification(
            "Recording Stopped",
            f"⏹️ Recording completed\nFrames: {frame_count}\nDuration: {duration:.1f}s",
            tags=["stop_button"]
        )
    
    def send_status(self, status: Dict[str, Any]):
        """Send current status notification."""
        is_recording = status.get('is_recording', False)
        frame_count = status.get('frame_count', 0)
        uptime = status.get('uptime', 0)
        
        status_icon = "🔴" if is_recording else "🟢"
        recording_text = "Recording" if is_recording else "Idle"
        
        self._send_notification(
            "Camera Status",
            f"{status_icon} Status: {recording_text}\nFrames: {frame_count}\nUptime: {uptime:.1f}s",
            tags=["information_source"]
        )
    
    def send_error(self, error_message: str):
        """Send error notification."""
        self._send_notification(
            "Camera Error",
            f"❌ Error: {error_message}",
            tags=["x"],
            priority=4
        ) 