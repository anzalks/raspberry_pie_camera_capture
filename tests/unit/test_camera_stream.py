#!/usr/bin/env python3
"""
Unit tests for camera stream implementation.
"""

import os
import time
import pytest
import numpy as np
from unittest.mock import Mock, patch
from raspberry_pi_lsl_stream.camera_stream_fixed import LSLCameraStreamer
from raspberry_pi_lsl_stream.status_display import StatusDisplay

@pytest.fixture
def mock_camera():
    """Create a mock camera object."""
    camera = Mock()
    camera.isOpened.return_value = True
    camera.read.return_value = (True, np.zeros((480, 640, 3), dtype=np.uint8))
    camera.get.return_value = 30.0
    return camera

@pytest.fixture
def mock_picamera():
    """Create a mock PiCamera object."""
    camera = Mock()
    camera.create_video_configuration.return_value = {}
    camera.configure.return_value = None
    camera.start.return_value = None
    camera.capture_array.return_value = np.zeros((480, 640, 3), dtype=np.uint8)
    return camera

def test_camera_streamer_init():
    """Test camera streamer initialization."""
    with patch('picamera2.Picamera2') as mock_picamera2:
        # Mock the picamera2 to avoid actual hardware access
        mock_picamera2.return_value = Mock()
        
        streamer = LSLCameraStreamer(
            width=640,
            height=480,
            target_fps=30.0,
            save_video=True,
            output_path="test_recordings",
            codec="h264",
            show_preview=False,
            push_to_lsl=False,
            stream_name="test_stream",
            use_buffer=True,
            buffer_size_seconds=5.0,
            ntfy_topic="test-topic"
        )
        
        # Check that basic parameters are set correctly
        assert streamer.width == 640
        assert streamer.height == 480
        assert streamer.target_fps == 30.0
        assert streamer.save_video is True
        assert streamer.output_path == "test_recordings"
        assert streamer.codec == "h264"
        assert streamer.show_preview is False
        assert streamer.push_to_lsl is False
        assert streamer.stream_name == "test_stream"
        assert streamer.use_buffer is True
        assert streamer.buffer_size_seconds == 5.0
        assert streamer.ntfy_topic == "test-topic"
        
        # Check internal state
        assert streamer._is_running is False
        assert streamer.frame_count == 0
        assert streamer.frames_written_count == 0
        assert streamer.frames_dropped_count == 0
        assert streamer.actual_fps == 30.0
        
        # Check camera initialization
        assert streamer.camera is None
        assert streamer.camera_lock is not None
        
        # Check LSL initialization
        assert streamer.outlet is None
        assert streamer.status_outlet is None

@patch("picamera2.Picamera2")
def test_camera_streamer_picamera(mock_picamera2, mock_picamera):
    """Test camera streamer with PiCamera."""
    mock_picamera2.return_value = mock_picamera
    
    streamer = LSLCameraStreamer(
        width=640,
        height=480,
        target_fps=30.0,
        save_video=False,
        show_preview=False,
        push_to_lsl=False,
        use_buffer=False
    )
    
    # Start streamer to initialize camera
    streamer._initialize_camera()
    
    assert streamer.camera is not None
    assert streamer.actual_fps == 30.0

def test_status_display():
    """Test status display."""
    # Create mock objects for testing
    mock_camera = Mock()
    mock_camera.get_info.return_value = {
        'width': 640, 
        'height': 480, 
        'actual_fps': 30.0,
        'codec': 'h264'
    }
    mock_camera.get_frame_count.return_value = 10
    mock_camera.get_frames_written.return_value = 8
    mock_camera.get_frames_dropped.return_value = 2
    mock_camera.waiting_for_trigger = False
    
    mock_buffer = Mock()
    mock_buffer.get_buffer_size.return_value = 5
    mock_buffer.get_buffer_duration.return_value = 2.5
    
    # Create status display with mocks
    status = StatusDisplay(
        camera_streamer=mock_camera,
        buffer_manager=mock_buffer,
        ntfy_topic="test-topic",
        update_interval=0.1
    )
    
    # Check initial state
    assert status.update_interval == 0.1
    assert status.stop_event is not None
    assert status.display_thread is None
    assert status.camera_streamer is mock_camera
    assert status.buffer_manager is mock_buffer
    assert status.ntfy_topic == "test-topic"
    
    # Test notify method
    status.notify("Test notification")
    assert status.last_notification == "Test notification"
    assert status.notification_time is not None
    
    # Test start/stop methods without actually running the thread
    status.display_thread = Mock()
    status.stop()
    status.display_thread.join.assert_called_once()

@patch("picamera2.Picamera2")
def test_camera_streamer_capture(mock_picamera2, mock_picamera):
    """Test camera streamer frame capture."""
    mock_picamera2.return_value = mock_picamera
    
    streamer = LSLCameraStreamer(
        width=640,
        height=480,
        target_fps=30.0,
        save_video=False,
        show_preview=False,
        push_to_lsl=False,
        use_buffer=False
    )
    
    # Manually initialize camera
    streamer.camera = mock_picamera
    streamer._is_running = True
    
    # Capture a frame
    frame = streamer.capture_frame()
    
    # Check that frame was captured
    assert frame is not None
    assert streamer.get_frame_count() == 1

@patch("picamera2.Picamera2")
def test_camera_streamer_buffer(mock_picamera2, mock_picamera):
    """Test camera streamer buffer functionality."""
    mock_picamera2.return_value = mock_picamera
    
    # Create a streamer with buffer
    streamer = LSLCameraStreamer(
        width=640,
        height=480,
        target_fps=30.0,
        save_video=False,
        show_preview=False,
        push_to_lsl=False,
        use_buffer=True,
        buffer_size_seconds=1.0,
        ntfy_topic="test-topic"
    )
    
    # Mock buffer trigger manager methods
    streamer.buffer_trigger_manager = Mock()
    streamer.buffer_trigger_manager.get_buffer_size.return_value = 10
    streamer.buffer_trigger_manager.get_buffer_duration.return_value = 1.0
    
    # Test manual trigger and stop
    streamer.manual_trigger()
    streamer.buffer_trigger_manager.trigger_manually.assert_called_once()
    
    streamer.manual_stop()
    streamer.buffer_trigger_manager.stop_manually.assert_called_once()
    
    # Test get_info method
    info = streamer.get_info()
    assert info['width'] == 640
    assert info['height'] == 480
    assert info['actual_fps'] == 30.0
    assert 'buffer_size_frames' in info

@patch("picamera2.Picamera2")
def test_camera_streamer_video_writer(mock_picamera2, mock_picamera):
    """Test camera streamer video writer initialization."""
    mock_picamera2.return_value = mock_picamera
    
    output_dir = "test_recordings"
    os.makedirs(output_dir, exist_ok=True)
    
    with patch('cv2.VideoWriter') as mock_video_writer:
        # Mock VideoWriter to avoid actual file operations
        mock_writer = Mock()
        mock_writer.isOpened.return_value = True
        mock_video_writer.return_value = mock_writer
        
        # Create streamer with video saving enabled
        streamer = LSLCameraStreamer(
            width=640,
            height=480,
            target_fps=30.0,
            save_video=True,
            output_path=output_dir,
            codec="mjpg",
            show_preview=False,
            push_to_lsl=False,
            use_buffer=False
        )
        
        # Initialize video writer
        streamer._initialize_video_writer()
        
        # Check video writer initialization
        assert streamer.video_writer is not None
        assert streamer.frame_queue is not None
        assert streamer.writer_thread is not None
        assert streamer.stop_writer_event is not None 