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
    
    def __init__(self, buffer_size_seconds=5.0, expected_fps=30):
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
        
    def add_frame(self, frame, timestamp=None):
        """
        Add a frame to the rolling buffer.
        
        Args:
            frame: The video frame (numpy array)
            timestamp: Optional timestamp when the frame was captured. If None, current time is used
        """
        with self.lock:
            if frame is None:
                logger.warning("Attempted to add None frame to buffer")
                return
                
            try:
                # Use current time if no timestamp provided
                if timestamp is None:
                    timestamp = time.time()
                    
                # Store a copy of the frame to prevent external modification
                frame_copy = frame.copy()
                self.buffer.append((frame_copy, timestamp))
                logger.debug(f"Added frame to buffer. Current size: {len(self.buffer)}")
            except Exception as e:
                logger.error(f"Error adding frame to buffer: {e}")
    
    def get_buffer_contents(self):
        """
        Get all frames currently in the buffer.
        
        Returns:
            List of (frame, timestamp) tuples, oldest first
        """
        with self.lock:
            # Return a copy of the buffer contents
            contents = list(self.buffer)
            logger.debug(f"Retrieved {len(contents)} frames from buffer")
            return contents
    
    def clear(self):
        """Clear all frames from the buffer."""
        with self.lock:
            size = len(self.buffer)
            self.buffer.clear()
            logger.info(f"Cleared {size} frames from buffer")
    
    def get_buffer_size(self):
        """Return the number of frames currently in the buffer."""
        with self.lock:
            size = len(self.buffer)
            logger.debug(f"Buffer size: {size} frames")
            return size
            
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
            duration = newest_timestamp - oldest_timestamp
            logger.debug(f"Buffer duration: {duration:.2f}s")
            return duration


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
    
    def __init__(self, buffer_size_seconds=5.0, ntfy_topic=None, on_trigger=None, on_stop=None):
        """
        Initialize the buffer trigger manager.
        
        Args:
            buffer_size_seconds: Number of seconds of footage to keep in the buffer
            ntfy_topic: The ntfy topic to subscribe to for triggers
            on_trigger: Function to call when recording is triggered, receives frames list
            on_stop: Function to call when recording is stopped
        """
        self.buffer = RollingBuffer(buffer_size_seconds)
        self.ntfy_subscriber = None
        self.on_trigger = on_trigger
        self.on_stop = on_stop
        self.recording_active = False
        self.ntfy_topic = ntfy_topic
        
        if ntfy_topic:
            self.setup_ntfy_subscription(ntfy_topic)
            
    def setup_ntfy_subscription(self, topic):
        """Set up the ntfy subscription for the given topic."""
        logger.info(f"Setting up ntfy subscription for topic: {topic}")
        self.ntfy_subscriber = NtfySubscriber(
            topic,
            self._handle_notification
        )
        
    def start(self):
        """Start the buffer trigger manager."""
        logger.info("Starting buffer trigger manager")
        if self.ntfy_subscriber:
            self.ntfy_subscriber.start()
            
    def stop(self):
        """Stop the buffer trigger manager."""
        logger.info("Stopping buffer trigger manager")
        if self.ntfy_subscriber:
            self.ntfy_subscriber.stop()
            
    def add_frame(self, frame):
        """Add a frame to the buffer."""
        if not self.recording_active:
            self.buffer.add_frame(frame, time.time())
            
    def _handle_notification(self, message):
        """Handle an incoming ntfy notification."""
        try:
            msg_text = message.get('message', '').lower()
            logger.info(f"Received notification: {message.get('message', 'No message')}")
            
            if 'start recording' in msg_text or 'start' in msg_text:
                logger.info("Start recording command received")
                self.trigger_manually()
            elif 'stop recording' in msg_text or 'stop' in msg_text:
                logger.info("Stop recording command received")
                self.stop_manually()
        except Exception as e:
            logger.error(f"Error handling notification: {e}")
            
    def trigger_manually(self):
        """Manually trigger recording."""
        logger.info("Manual trigger activated")
        if not self.recording_active:
            buffer_frames = self.buffer.get_buffer_contents()
            buffer_duration = self.buffer.get_buffer_duration()
            logger.info(f"Manual trigger with {len(buffer_frames)} frames in buffer ({buffer_duration:.2f}s)")
            
            # Set recording state
            self.recording_active = True
            
            # Call callback with buffer contents
            if self.on_trigger:
                self.on_trigger(buffer_frames)
        else:
            logger.info("Recording already active, ignoring manual trigger")
            
    def stop_manually(self):
        """Manually stop recording."""
        logger.info("Manual stop activated")
        if self.recording_active:
            self.recording_active = False
            if self.on_stop:
                self.on_stop()
        else:
            logger.info("Recording not active, ignoring manual stop")
            
    def get_buffer_size(self):
        """Get current number of frames in buffer."""
        return self.buffer.get_buffer_size()
        
    def get_buffer_duration(self):
        """Get current duration of buffer in seconds."""
        return self.buffer.get_buffer_duration() 