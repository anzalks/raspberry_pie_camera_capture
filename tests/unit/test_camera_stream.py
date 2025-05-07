#!/usr/bin/env python3
"""
Unit tests for camera stream implementation.
"""

import os
import time
import pytest
import numpy as np
from unittest.mock import Mock, patch
from raspberry_pi_lsl_stream.camera_stream import LSLCameraStreamer, StatusDisplay

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
    camera.capture.return_value = None
    return camera

def test_camera_streamer_init():
    """Test camera streamer initialization."""
    streamer = LSLCameraStreamer(
        camera_id=0,
        width=640,
        height=480,
        target_fps=30.0,
        save_video=True,
        output_path="test_recordings",
        codec="auto",
        show_preview=False,
        push_to_lsl=False,
        stream_name="test_stream",
        use_buffer=True,
        buffer_size_seconds=5.0,
        ntfy_topic="test-topic"
    )
    
    assert streamer.camera_id == 0
    assert streamer.width == 640
    assert streamer.height == 480
    assert streamer.target_fps == 30.0
    assert streamer.save_video is True
    assert streamer.output_path == "test_recordings"
    assert streamer.codec == "auto"
    assert streamer.show_preview is False
    assert streamer.push_to_lsl is False
    assert streamer.stream_name == "test_stream"
    assert streamer.use_buffer is True
    assert streamer.buffer_size_seconds == 5.0
    assert streamer.ntfy_topic == "test-topic"
    
    assert streamer._is_running is False
    assert streamer.frame_count == 0
    assert streamer.frames_written_count == 0
    assert streamer.frames_dropped_count == 0
    assert streamer.actual_fps == 30.0
    
    assert streamer.camera is None
    assert streamer.is_picamera is False
    assert streamer.camera_lock is not None
    
    assert streamer.info is None
    assert streamer.outlet is None
    assert streamer.buffer_trigger_manager is None
    assert streamer.waiting_for_trigger is False
    assert streamer.recording_triggered is False
    assert streamer.video_writer is None
    assert streamer.frame_queue is None
    assert streamer.writer_thread is None
    assert streamer.stop_writer_event is None

@patch("cv2.VideoCapture")
def test_camera_streamer_webcam(mock_video_capture, mock_camera):
    """Test camera streamer with webcam."""
    mock_video_capture.return_value = mock_camera
    
    streamer = LSLCameraStreamer(
        camera_id=0,
        width=640,
        height=480,
        target_fps=30.0,
        save_video=False,
        show_preview=False,
        push_to_lsl=False,
        use_buffer=False
    )
    
    assert streamer.camera is not None
    assert streamer.is_picamera is False
    assert streamer.actual_fps == 30.0

@patch("picamera2.Picamera2")
def test_camera_streamer_picamera(mock_picamera2, mock_picamera):
    """Test camera streamer with PiCamera."""
    mock_picamera2.return_value = mock_picamera
    
    streamer = LSLCameraStreamer(
        camera_id="pi",
        width=640,
        height=480,
        target_fps=30.0,
        save_video=False,
        show_preview=False,
        push_to_lsl=False,
        use_buffer=False
    )
    
    assert streamer.camera is not None
    assert streamer.is_picamera is True
    assert streamer.actual_fps == 30.0

def test_status_display():
    """Test status display."""
    status = StatusDisplay()
    
    assert status.update_interval == 1.0
    assert status.stop_event is not None
    assert status.display_thread is None
    assert status.frame_count == 0
    assert status.frames_written == 0
    assert status.frames_dropped == 0
    assert status.buffer_size == 0
    assert status.recording_active is False
    assert status.start_time is None
    
    # Test start
    status.start()
    assert status.display_thread is not None
    assert status.start_time is not None
    
    # Test update
    status.update(
        frame_count=10,
        frames_written=8,
        frames_dropped=2,
        buffer_size=5,
        recording_active=True
    )
    assert status.frame_count == 10
    assert status.frames_written == 8
    assert status.frames_dropped == 2
    assert status.buffer_size == 5
    assert status.recording_active is True
    
    # Test stop
    status.stop()
    assert status.display_thread is None

@patch("cv2.VideoCapture")
def test_camera_streamer_capture(mock_video_capture, mock_camera):
    """Test camera streamer frame capture."""
    mock_video_capture.return_value = mock_camera
    
    streamer = LSLCameraStreamer(
        camera_id=0,
        width=640,
        height=480,
        target_fps=30.0,
        save_video=False,
        show_preview=False,
        push_to_lsl=False,
        use_buffer=False
    )
    
    # Start streamer
    streamer.start()
    assert streamer._is_running is True
    
    # Wait for frames
    time.sleep(0.1)
    assert streamer.frame_count > 0
    
    # Stop streamer
    streamer.stop()
    assert streamer._is_running is False

@patch("cv2.VideoCapture")
def test_camera_streamer_buffer(mock_video_capture, mock_camera):
    """Test camera streamer buffer functionality."""
    mock_video_capture.return_value = mock_camera
    
    streamer = LSLCameraStreamer(
        camera_id=0,
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
    
    # Start streamer
    streamer.start()
    assert streamer._is_running is True
    assert streamer.buffer_trigger_manager is not None
    assert streamer.waiting_for_trigger is True
    assert streamer.recording_triggered is False
    
    # Wait for buffer to fill
    time.sleep(1.0)
    assert streamer.buffer_trigger_manager.get_buffer_size() > 0
    
    # Trigger recording
    streamer.buffer_trigger_manager.trigger_manually()
    assert streamer.recording_triggered is True
    
    # Wait for frames
    time.sleep(0.1)
    assert streamer.frame_count > 0
    
    # Stop recording
    streamer.buffer_trigger_manager.stop_manually()
    assert streamer.recording_triggered is False
    
    # Stop streamer
    streamer.stop()
    assert streamer._is_running is False

@patch("cv2.VideoCapture")
def test_camera_streamer_video_writer(mock_video_capture, mock_camera):
    """Test camera streamer video writer."""
    mock_video_capture.return_value = mock_camera
    
    output_dir = "test_recordings"
    os.makedirs(output_dir, exist_ok=True)
    
    streamer = LSLCameraStreamer(
        camera_id=0,
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
    
    # Start streamer
    streamer.start()
    assert streamer._is_running is True
    assert streamer.video_writer is not None
    
    # Wait for frames
    time.sleep(0.1)
    assert streamer.frame_count > 0
    assert streamer.frames_written_count > 0
    
    # Stop streamer
    streamer.stop()
    assert streamer._is_running is False
    assert streamer.video_writer is None 