"""Rolling buffer and notification trigger implementation for camera capture."""

import time
import threading
import queue
import requests
import json
import numpy as np
from collections import deque
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("BufferTrigger")

class RollingBuffer:
    """Maintains a rolling buffer of frames with timestamps."""
    
    def __init__(self, buffer_size_seconds=15, expected_fps=30):
        """
        Initialize the rolling buffer.
        
        Args:
            buffer_size_seconds: Number of seconds of footage to keep in the buffer
            expected_fps: Expected frames per second, used to estimate buffer capacity
        """
        self.buffer_size_seconds = buffer_size_seconds
        self.expected_fps = expected_fps
        # Calculate approximate capacity (+20% for safety)
        capacity = int(buffer_size_seconds * expected_fps * 1.2)
        logger.info(f"Initializing rolling buffer with {capacity} frame capacity (~{buffer_size_seconds}s at {expected_fps}fps)")
        
        # Use deque for efficient rolling buffer implementation
        self.buffer = deque(maxlen=capacity)
        self.lock = threading.RLock()  # Reentrant lock for thread safety
        
    def add_frame(self, frame, timestamp):
        """
        Add a frame to the rolling buffer.
        
        Args:
            frame: The video frame (numpy array)
            timestamp: LSL timestamp when the frame was captured
        """
        with self.lock:
            # Store a copy of the frame to prevent external modification
            self.buffer.append((frame.copy(), timestamp))
    
    def get_buffer_contents(self):
        """
        Get all frames currently in the buffer.
        
        Returns:
            List of (frame, timestamp) tuples, oldest first
        """
        with self.lock:
            # Return a copy of the buffer contents
            return list(self.buffer)
    
    def clear(self):
        """Clear all frames from the buffer."""
        with self.lock:
            self.buffer.clear()
    
    def get_buffer_size(self):
        """Return the number of frames currently in the buffer."""
        with self.lock:
            return len(self.buffer)
            
    def get_buffer_duration(self):
        """
        Calculate and return the current buffer duration in seconds.
        
        Returns:
            Float representing seconds of footage in buffer, or 0 if buffer has < 2 frames
        """
        with self.lock:
            if len(self.buffer) < 2:
                return 0.0
            
            # Get timestamps of oldest and newest frames
            oldest_timestamp = self.buffer[0][1]
            newest_timestamp = self.buffer[-1][1]
            
            # Return duration
            return newest_timestamp - oldest_timestamp


class NtfySubscriber:
    """Subscribes to ntfy topics and triggers actions on messages."""
    
    def __init__(self, topic, callback, filter_condition=None):
        """
        Initialize the ntfy subscriber.
        
        Args:
            topic: The ntfy topic to subscribe to (string)
            callback: Function to call when a message is received
            filter_condition: Optional function that takes message dict and returns 
                              True to trigger callback, False to ignore
        """
        self.topic = topic
        self.callback = callback
        self.filter_condition = filter_condition
        self.stop_event = threading.Event()
        self.thread = None
        self.topic_url = f"https://ntfy.sh/{topic}/json"
        
    def start(self):
        """Start the subscription in a background thread."""
        if self.thread and self.thread.is_alive():
            logger.warning("Subscription already running")
            return
            
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._subscription_loop, daemon=True)
        self.thread.start()
        logger.info(f"Started ntfy subscription to topic: {self.topic}")
        
    def stop(self):
        """Stop the subscription."""
        if not self.thread or not self.thread.is_alive():
            return
            
        logger.info("Stopping ntfy subscription...")
        self.stop_event.set()
        
        # The requests call may be blocking, so we wait with a timeout
        self.thread.join(timeout=3.0)
        
        if self.thread.is_alive():
            logger.warning("Subscription thread did not terminate cleanly within timeout")
        else:
            logger.info("Subscription stopped")
    
    def _subscription_loop(self):
        """Main subscription loop - runs in a background thread."""
        # Use a session for connection pooling
        session = requests.Session()
        
        while not self.stop_event.is_set():
            try:
                # Subscribe with a stream and process messages
                logger.info(f"Connecting to ntfy topic: {self.topic}")
                
                # Use a timeout to allow clean shutdown
                resp = session.get(self.topic_url, stream=True, timeout=10)
                
                if resp.status_code == 200:
                    logger.info(f"Connected to ntfy topic: {self.topic}")
                    
                    # Process the streaming response
                    for line in resp.iter_lines():
                        if self.stop_event.is_set():
                            break
                            
                        if not line:
                            continue
                            
                        try:
                            # Process the JSON message
                            message = json.loads(line)
                            
                            # Apply filter if provided
                            if self.filter_condition is None or self.filter_condition(message):
                                logger.info(f"Received notification: {message.get('title', 'No title')}")
                                # Call the callback with the message
                                self.callback(message)
                                
                        except json.JSONDecodeError:
                            logger.warning(f"Failed to decode JSON: {line}")
                        except Exception as e:
                            logger.error(f"Error processing message: {e}")
                else:
                    logger.error(f"Failed to connect to ntfy topic: {resp.status_code}")
                    # Wait before retry
                    time.sleep(5)
                    
            except requests.exceptions.Timeout:
                # This is expected when using timeout to allow for clean shutdown
                logger.debug("Request timed out (expected for clean shutdown checks)")
                continue
            except requests.exceptions.RequestException as e:
                logger.error(f"Error in ntfy subscription: {e}")
                # Wait before retry
                time.sleep(5)
            except Exception as e:
                logger.error(f"Unexpected error in subscription: {e}")
                # Wait before retry
                time.sleep(5)
                
        logger.info("Subscription loop terminated")


class BufferTriggerManager:
    """Manages the rolling buffer and notification trigger for camera recording."""
    
    def __init__(self, buffer_size_seconds=15, ntfy_topic=None, callback=None, stop_callback=None):
        """
        Initialize the buffer trigger manager.
        
        Args:
            buffer_size_seconds: Size of rolling buffer in seconds
            ntfy_topic: ntfy topic to subscribe to for triggers
            callback: Function to call when recording should start
            stop_callback: Function to call when recording should stop
        """
        self.rolling_buffer = RollingBuffer(buffer_size_seconds=buffer_size_seconds)
        self.recording_active = False
        self.callback = callback
        self.stop_callback = stop_callback
        self.ntfy_subscriber = None
        
        # Set up ntfy subscriber if topic is provided
        if ntfy_topic:
            self.setup_ntfy_subscription(ntfy_topic)
    
    def setup_ntfy_subscription(self, topic):
        """Set up the ntfy subscription with the given topic."""
        self.ntfy_subscriber = NtfySubscriber(
            topic=topic,
            callback=self._handle_notification
        )
    
    def start(self):
        """Start the buffer trigger manager."""
        if self.ntfy_subscriber:
            self.ntfy_subscriber.start()
        logger.info("Buffer trigger manager started")
    
    def stop(self):
        """Stop the buffer trigger manager."""
        if self.ntfy_subscriber:
            self.ntfy_subscriber.stop()
        logger.info("Buffer trigger manager stopped")
    
    def add_frame(self, frame, timestamp):
        """Add a frame to the rolling buffer."""
        self.rolling_buffer.add_frame(frame, timestamp)
    
    def _handle_notification(self, message):
        """Handle incoming ntfy notification."""
        logger.info(f"Received notification: {message.get('title', 'No title')}")
        
        # Check if this is a start or stop command
        message_text = message.get('message', '').lower()
        action = message.get('action', '').lower()
        title = message.get('title', '').lower()
        
        # Look for stop keywords in various fields
        stop_indicators = ['stop', 'end', 'halt', 'finish', 'terminate']
        start_indicators = ['start', 'begin', 'record', 'trigger', 'capture']
        
        # Check if any stop indicators are in the message
        is_stop_command = any(word in message_text for word in stop_indicators) or \
                         any(word in title for word in stop_indicators) or \
                         (action and any(word in action for word in stop_indicators))
                         
        # Check if any start indicators are in the message (if not explicitly a stop)
        is_start_command = not is_stop_command and (
                            any(word in message_text for word in start_indicators) or \
                            any(word in title for word in start_indicators) or \
                            (action and any(word in action for word in start_indicators)) or \
                            # If no explicit action words found, treat as start by default
                            (not any(word in message_text for word in start_indicators + stop_indicators) and \
                             not any(word in title for word in start_indicators + stop_indicators) and \
                             not (action and any(word in action for word in start_indicators + stop_indicators)))
                          )
        
        # Handle stop command
        if is_stop_command:
            logger.info("Stop recording command received")
            if self.recording_active and self.stop_callback:
                logger.info("Calling stop callback")
                self.recording_active = False
                self.stop_callback(message)
            else:
                logger.info("Recording not active or no stop callback registered")
            return
        
        # Handle start command
        if is_start_command:
            logger.info("Start recording command received")
            if not self.recording_active:
                # Get the current buffer contents
                buffer_frames = self.rolling_buffer.get_buffer_contents()
                buffer_duration = self.rolling_buffer.get_buffer_duration()
                
                logger.info(f"Trigger received with {len(buffer_frames)} frames in buffer ({buffer_duration:.2f}s)")
                
                # Call the callback with the buffer contents
                if self.callback:
                    self.recording_active = True
                    self.callback(buffer_frames, message)
            else:
                logger.info("Recording already active, ignoring start command")
            return
            
        # If we got here, the message didn't contain clear start/stop indicators
        logger.info(f"Notification did not contain clear start/stop indicators, treating as start by default")
        if not self.recording_active and self.callback:
            buffer_frames = self.rolling_buffer.get_buffer_contents()
            self.recording_active = True
            self.callback(buffer_frames, message)
    
    def trigger_manually(self):
        """Manually trigger recording (for testing or alternative trigger methods)."""
        logger.info("Manual trigger activated")
        
        # Only trigger if not already recording
        if not self.recording_active:
            # Simulate a notification with manual=True flag
            self._handle_notification({"title": "Manual Trigger", "message": "start recording", "manual": True})
        else:
            logger.info("Recording already active, ignoring manual trigger")
    
    def stop_manually(self):
        """Manually stop recording (for testing or alternative trigger methods)."""
        logger.info("Manual stop triggered")
        
        # Only stop if currently recording
        if self.recording_active and self.stop_callback:
            self.recording_active = False
            self.stop_callback({"title": "Manual Stop", "message": "stop recording", "manual": True}) 