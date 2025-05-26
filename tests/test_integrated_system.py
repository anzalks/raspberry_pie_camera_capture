#!/usr/bin/env python3
"""
Integrated System Test Suite
============================

Comprehensive test suite for the IMX296 camera system with:
- GScrop capture integration
- 3-channel LSL streaming
- ntfy.sh remote control
- Video recording pipeline

Author: Anzal KS <anzal.ks@gmail.com>
Date: May 23, 2025
"""

import os
import sys
import time
import unittest
import tempfile
import threading
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

try:
    from src.imx296_gs_capture import GSCropCameraCapture, NtfyHandler, VideoRecorder
    from src.imx296_gs_capture.imx296_capture import load_config
except ImportError as e:
    print(f"Import error: {e}")
    print("Please ensure the project is properly set up")
    sys.exit(1)


class TestIntegratedSystem(unittest.TestCase):
    """Test the integrated camera system."""
    
    def setUp(self):
        """Set up test environment."""
        self.test_config = {
            'camera': {
                'width': 900,
                'height': 600,
                'fps': 100,
                'exposure_time_us': 5000,
                'script_path': 'bin/GScrop',
                'markers_file': '/tmp/test_markers.txt',
                'frame_queue_size': 1000,
                'lsl_worker_threads': 1,
                'auto_detect': False
            },
            'recording': {
                'output_dir': 'test_recordings',
                'video_format': 'mkv',
                'codec': 'mjpeg',
                'quality': 90
            },
            'system': {
                'ffmpeg_path': '/usr/bin/ffmpeg'
            },
            'lsl': {
                'name': 'TestCamera',
                'type': 'VideoEvents',
                'id': 'test_cam',
                'channel_count': 3
            },
            'ntfy': {
                'server': 'https://ntfy.sh',
                'topic': 'test-camera-topic',
                'poll_interval_sec': 1
            },
            'buffer': {
                'duration_seconds': 5,
                'max_frames': 500
            },
            'logging': {
                'level': 'DEBUG'
            }
        }
        
        # Create test directories
        Path('test_recordings').mkdir(exist_ok=True)
    
    def tearDown(self):
        """Clean up test environment."""
        # Clean up test files
        import shutil
        if Path('test_recordings').exists():
            shutil.rmtree('test_recordings')
        
        if Path('/tmp/test_markers.txt').exists():
            os.remove('/tmp/test_markers.txt')
    
    @patch('src.imx296_gs_capture.imx296_capture.pylsl')
    def test_camera_initialization(self, mock_pylsl):
        """Test camera system initialization."""
        # Mock pylsl components
        mock_pylsl.StreamInfo.return_value = Mock()
        mock_pylsl.StreamOutlet.return_value = Mock()
        
        # Mock GScrop script existence
        with patch('os.path.isfile', return_value=True), \
             patch('os.access', return_value=True):
            
            camera = GSCropCameraCapture(self.test_config)
            
            # Verify initialization
            self.assertEqual(camera.width, 900)
            self.assertEqual(camera.height, 600)
            self.assertEqual(camera.fps, 100)
            self.assertIsNotNone(camera.video_recorder)
            self.assertFalse(camera.recording_active)
    
    def test_ntfy_handler_initialization(self):
        """Test ntfy handler initialization."""
        callback = Mock()
        
        handler = NtfyHandler(self.test_config['ntfy'], callback)
        
        self.assertEqual(handler.topic, 'test-camera-topic')
        self.assertEqual(handler.poll_interval, 1)
        self.assertFalse(handler.running)
    
    def test_ntfy_command_parsing(self):
        """Test ntfy command parsing."""
        callback = Mock()
        handler = NtfyHandler(self.test_config['ntfy'], callback)
        
        # Test simple command
        result = handler._parse_command('start_recording')
        self.assertEqual(result['command'], 'start_recording')
        
        # Test command with parameters
        result = handler._parse_command('start_recording 30')
        self.assertEqual(result['command'], 'start_recording')
        self.assertEqual(result['params']['duration'], 30.0)
        
        # Test JSON command
        result = handler._parse_command('{"command": "stop_recording"}')
        self.assertEqual(result['command'], 'stop_recording')
    
    def test_video_recorder_initialization(self):
        """Test video recorder initialization."""
        recorder = VideoRecorder(self.test_config['recording'])
        
        self.assertEqual(recorder.video_format, 'mkv')
        self.assertEqual(recorder.codec, 'mjpeg')
        self.assertEqual(recorder.quality, 90)
        self.assertFalse(recorder.recording)
    
    def test_video_path_generation(self):
        """Test video recording path generation."""
        recorder = VideoRecorder(self.test_config['recording'])
        
        from datetime import datetime
        test_time = datetime(2025, 5, 23, 14, 30, 45)
        
        path = recorder._get_recording_path(test_time)
        
        # Check path structure: recordings/2025_05_23/video/2025_05_23_14_30_45.mkv
        expected_parts = ['test_recordings', '2025_05_23', 'video', '2025_05_23_14_30_45.mkv']
        path_parts = path.parts
        
        self.assertTrue(all(part in str(path) for part in expected_parts))
        self.assertTrue(path.name.endswith('.mkv'))
    
    @patch('subprocess.run')
    def test_ffmpeg_check(self, mock_run):
        """Test ffmpeg availability check."""
        recorder = VideoRecorder(self.test_config['recording'])
        
        # Test successful check
        mock_run.return_value.returncode = 0
        self.assertTrue(recorder._check_ffmpeg())
        
        # Test failed check
        mock_run.return_value.returncode = 1
        self.assertFalse(recorder._check_ffmpeg())
    
    @patch('src.imx296_gs_capture.imx296_capture.pylsl')
    def test_lsl_setup(self, mock_pylsl):
        """Test LSL setup with 3 channels."""
        mock_info = Mock()
        mock_desc = Mock()
        mock_channels = Mock()
        
        mock_info.desc.return_value = mock_desc
        mock_desc.append_child.return_value = mock_channels
        mock_channels.append_child.return_value = mock_channels
        
        mock_pylsl.StreamInfo.return_value = mock_info
        mock_pylsl.StreamOutlet.return_value = Mock()
        
        with patch('os.path.isfile', return_value=True), \
             patch('os.access', return_value=True):
            
            camera = GSCropCameraCapture(self.test_config)
            
            # Verify LSL setup was called with correct parameters
            mock_pylsl.StreamInfo.assert_called_once()
            call_args = mock_pylsl.StreamInfo.call_args
            
            # Check channel count is 3
            self.assertEqual(call_args[1]['channel_count'], 3)
    
    @patch('src.imx296_gs_capture.imx296_capture.pylsl')
    @patch('subprocess.Popen')
    def test_recording_start_stop(self, mock_popen, mock_pylsl):
        """Test recording start and stop functionality."""
        # Mock pylsl
        mock_pylsl.StreamInfo.return_value = Mock()
        mock_pylsl.StreamOutlet.return_value = Mock()
        
        # Mock process
        mock_process = Mock()
        mock_process.poll.return_value = None
        mock_popen.return_value = mock_process
        
        with patch('os.path.isfile', return_value=True), \
             patch('os.access', return_value=True), \
             patch('os.path.exists', return_value=False), \
             patch('src.imx296_gs_capture.video_recorder.VideoRecorder.start_recording') as mock_video_start, \
             patch('src.imx296_gs_capture.video_recorder.VideoRecorder.stop_recording') as mock_video_stop, \
             patch('src.imx296_gs_capture.video_recorder.VideoRecorder.is_recording', return_value=False):
            
            # Mock video recorder methods
            mock_video_start.return_value = "/test/video/file.mkv"
            mock_video_stop.return_value = {'file_size_mb': 10.5, 'duration': 5.0}
            
            camera = GSCropCameraCapture(self.test_config)
            
            # Test start recording
            success = camera.start_recording(duration_seconds=5)
            self.assertTrue(success)
            self.assertTrue(camera.recording_active)
            
            # Test stop recording
            stats = camera.stop_recording()
            self.assertFalse(camera.recording_active)
            self.assertIsInstance(stats, dict)
    
    def test_config_loading(self):
        """Test configuration loading."""
        # Create temporary config file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            import yaml
            yaml.dump(self.test_config, f)
            temp_config_path = f.name
        
        try:
            config = load_config(temp_config_path)
            self.assertEqual(config['camera']['width'], 900)
            self.assertEqual(config['camera']['fps'], 100)
        finally:
            os.unlink(temp_config_path)
    
    @patch('requests.get')
    def test_ntfy_message_checking(self, mock_get):
        """Test ntfy message checking."""
        callback = Mock()
        handler = NtfyHandler(self.test_config['ntfy'], callback)
        
        # Mock response
        mock_response = Mock()
        mock_response.text = '{"id": "test123", "message": "start_recording"}\n'
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        handler._check_messages()
        
        # Verify callback was called
        callback.assert_called_once_with('start_recording', {})
    
    def test_system_integration_flow(self):
        """Test complete system integration flow."""
        with patch('src.imx296_gs_capture.imx296_capture.pylsl'), \
             patch('os.path.isfile', return_value=True), \
             patch('os.access', return_value=True), \
             patch('subprocess.Popen'), \
             patch('requests.get'), \
             patch('requests.post'):
            
            # Initialize system
            camera = GSCropCameraCapture(self.test_config)
            
            # Test status
            status = camera.get_status()
            self.assertIn('is_recording', status)
            self.assertIn('frame_count', status)
            
            # Test ntfy command handling
            camera._handle_ntfy_command('status', {})
            
            # Verify system is properly initialized
            self.assertIsNotNone(camera.ntfy_handler)
            self.assertIsNotNone(camera.video_recorder)
    
    @patch('src.imx296_gs_capture.imx296_capture.pylsl')
    def test_rolling_buffer_initialization(self, mock_pylsl):
        """Test rolling buffer initialization."""
        mock_pylsl.StreamInfo.return_value = Mock()
        mock_pylsl.StreamOutlet.return_value = Mock()
        
        with patch('os.path.isfile', return_value=True), \
             patch('os.access', return_value=True):
            
            camera = GSCropCameraCapture(self.test_config)
            
            # Verify rolling buffer is initialized and started
            self.assertTrue(camera.buffer_active)
            self.assertIsNotNone(camera.rolling_buffer)
            self.assertEqual(camera.rolling_buffer.maxlen, camera.buffer_max_frames)
            self.assertIsNotNone(camera.buffer_thread)
    
    @patch('src.imx296_gs_capture.imx296_capture.pylsl')
    def test_rolling_buffer_frame_storage(self, mock_pylsl):
        """Test rolling buffer frame storage mechanism."""
        mock_pylsl.StreamInfo.return_value = Mock()
        mock_pylsl.StreamOutlet.return_value = Mock()
        
        with patch('os.path.isfile', return_value=True), \
             patch('os.access', return_value=True):
            
            camera = GSCropCameraCapture(self.test_config)
            
            # Clear any existing frames in buffer first
            camera.rolling_buffer.clear()
            
            # Manually add frames to buffer to test
            test_frames = [(i, time.time() + i * 0.01) for i in range(10)]
            for frame_num, frame_time in test_frames:
                camera.rolling_buffer.append((frame_num, frame_time))
            
            # Verify frames are stored
            self.assertEqual(len(camera.rolling_buffer), 10)
            
            # Test buffer max size (should not exceed maxlen)
            buffer_config = self.test_config.get('buffer', {})
            max_frames = buffer_config.get('max_frames', 500)
            
            # Clear buffer again for clean test
            camera.rolling_buffer.clear()
            
            # Add exactly max_frames + 10 items one by one
            # deque automatically removes oldest items when maxlen is exceeded
            for i in range(max_frames + 10):
                camera.rolling_buffer.append((i + 100, time.time()))
            
            # Should equal max frames due to deque maxlen behavior
            self.assertEqual(len(camera.rolling_buffer), max_frames)
            
            # Verify the buffer contains the most recent frames
            # (first 10 frames should have been discarded)
            buffer_list = list(camera.rolling_buffer)
            first_frame_num = buffer_list[0][0]
            self.assertEqual(first_frame_num, 110)  # 100 + 10 (first 10 discarded)
    
    @patch('src.imx296_gs_capture.imx296_capture.pylsl')
    def test_buffer_save_to_file(self, mock_pylsl):
        """Test saving rolling buffer contents to file."""
        mock_pylsl.StreamInfo.return_value = Mock()
        mock_pylsl.StreamOutlet.return_value = Mock()
        
        with patch('os.path.isfile', return_value=True), \
             patch('os.access', return_value=True):
            
            camera = GSCropCameraCapture(self.test_config)
            
            # Add test frames to buffer
            test_frames = [(i, time.time() + i * 0.01) for i in range(5)]
            for frame_num, frame_time in test_frames:
                camera.rolling_buffer.append((frame_num, frame_time))
            
            # Test saving buffer to file
            test_output_path = Path('test_recordings/test_output')
            frames_saved = camera._save_buffer_to_file(test_output_path)
            
            # Verify frames were saved
            self.assertEqual(frames_saved, 5)
            
            # Check if buffer file was created
            buffer_file = test_output_path.parent / f"{test_output_path.stem}_buffer{test_output_path.suffix}"
            if buffer_file.exists():
                # Verify file contents
                with open(buffer_file, 'r') as f:
                    content = f.read()
                    self.assertIn("Pre-trigger buffer frames", content)
                    self.assertIn("Buffer duration:", content)
                    # Should contain all 5 frames
                    lines = [line for line in content.split('\n') if line and not line.startswith('#')]
                    self.assertEqual(len(lines), 5)
    
    @patch('src.imx296_gs_capture.imx296_capture.pylsl')
    @patch('subprocess.Popen')
    def test_recording_with_buffer_integration(self, mock_popen, mock_pylsl):
        """Test that recording properly saves buffer contents before starting."""
        # Mock pylsl
        mock_pylsl.StreamInfo.return_value = Mock()
        mock_pylsl.StreamOutlet.return_value = Mock()
        
        # Mock process
        mock_process = Mock()
        mock_process.poll.return_value = None
        mock_popen.return_value = mock_process
        
        with patch('os.path.isfile', return_value=True), \
             patch('os.access', return_value=True), \
             patch('os.path.exists', return_value=False), \
             patch('src.imx296_gs_capture.video_recorder.VideoRecorder.start_recording') as mock_video_start, \
             patch('src.imx296_gs_capture.video_recorder.VideoRecorder.stop_recording') as mock_video_stop, \
             patch('src.imx296_gs_capture.video_recorder.VideoRecorder.is_recording', return_value=False):
            
            # Mock video recorder methods
            mock_video_start.return_value = "/test/video/file.mkv"
            mock_video_stop.return_value = {'file_size_mb': 10.5, 'duration': 5.0}
            
            camera = GSCropCameraCapture(self.test_config)
            
            # Add frames to rolling buffer
            test_frames = [(i, time.time() + i * 0.01) for i in range(3)]
            for frame_num, frame_time in test_frames:
                camera.rolling_buffer.append((frame_num, frame_time))
            
            # Mock the _save_buffer_to_file method to verify it's called
            with patch.object(camera, '_save_buffer_to_file', return_value=3) as mock_save_buffer:
                success = camera.start_recording(duration_seconds=5)
                
                # Verify recording started successfully
                self.assertTrue(success)
                self.assertTrue(camera.recording_active)
                
                # Verify buffer save was called
                mock_save_buffer.assert_called_once()
                
                # Stop recording
                camera.stop_recording()
    
    @patch('src.imx296_gs_capture.imx296_capture.pylsl')
    def test_buffer_cleanup(self, mock_pylsl):
        """Test proper cleanup of rolling buffer."""
        mock_pylsl.StreamInfo.return_value = Mock()
        mock_pylsl.StreamOutlet.return_value = Mock()
        
        with patch('os.path.isfile', return_value=True), \
             patch('os.access', return_value=True):
            
            camera = GSCropCameraCapture(self.test_config)
            
            # Verify buffer is active
            self.assertTrue(camera.buffer_active)
            
            # Cleanup camera
            camera.cleanup()
            
            # Verify buffer is stopped
            self.assertFalse(camera.buffer_active)


class TestSystemPerformance(unittest.TestCase):
    """Test system performance characteristics."""
    
    def test_frame_queue_performance(self):
        """Test frame queue performance under load."""
        import queue
        import threading
        
        test_queue = queue.Queue(maxsize=1000)
        
        def producer():
            for i in range(500):
                test_queue.put((i, time.time()))
                time.sleep(0.001)  # Simulate 1000 FPS
        
        def consumer():
            count = 0
            while count < 500:
                try:
                    test_queue.get(timeout=1)
                    count += 1
                except queue.Empty:
                    break
        
        start_time = time.time()
        
        producer_thread = threading.Thread(target=producer)
        consumer_thread = threading.Thread(target=consumer)
        
        producer_thread.start()
        consumer_thread.start()
        
        producer_thread.join()
        consumer_thread.join()
        
        duration = time.time() - start_time
        
        # Should complete in reasonable time (less than 2 seconds for 500 frames)
        self.assertLess(duration, 2.0)


def run_tests():
    """Run all tests."""
    print("Running Integrated System Test Suite...")
    print("=" * 50)
    
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add test cases
    suite.addTests(loader.loadTestsFromTestCase(TestIntegratedSystem))
    suite.addTests(loader.loadTestsFromTestCase(TestSystemPerformance))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Print summary
    print("\n" + "=" * 50)
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    
    if result.failures:
        print("\nFailures:")
        for test, traceback in result.failures:
            print(f"- {test}: {traceback}")
    
    if result.errors:
        print("\nErrors:")
        for test, traceback in result.errors:
            print(f"- {test}: {traceback}")
    
    success = len(result.failures) == 0 and len(result.errors) == 0
    print(f"\nOverall: {'PASS' if success else 'FAIL'}")
    
    return success


if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1) 