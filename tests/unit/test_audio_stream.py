#!/usr/bin/env python3
"""Unit tests for the audio stream module."""

import os
import sys
import unittest
import tempfile
import time
import threading
import numpy as np
from unittest.mock import patch, MagicMock, ANY

# Add parent directory to path to import the module
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../src')))

from raspberry_pi_lsl_stream.audio_stream import LSLAudioStreamer

class MockSoundDevice:
    """Mock for sounddevice module"""
    def __init__(self):
        self.devices = [
            {'name': 'Mock Audio Device 1', 'max_input_channels': 2},
            {'name': 'Mock Audio Device 2', 'max_input_channels': 1}
        ]
        self.stream_started = False
        self.stream_closed = False
        self.callback = None
        
    def query_devices(self, device=None):
        if device is None:
            return self.devices
        return self.devices[device]
    
    class InputStream:
        def __init__(self, samplerate, blocksize, device, channels, dtype, callback):
            self.samplerate = samplerate
            self.blocksize = blocksize
            self.device = device
            self.channels = channels
            self.dtype = dtype
            self.callback = callback
            self.started = False
            self.closed = False
        
        def start(self):
            self.started = True
        
        def stop(self):
            self.started = False
        
        def close(self):
            self.closed = True

class TestLSLAudioStreamer(unittest.TestCase):
    """Test cases for LSLAudioStreamer."""
    
    @patch('raspberry_pi_lsl_stream.audio_stream.pylsl')
    @patch('raspberry_pi_lsl_stream.audio_stream.wave')
    def setUp(self, mock_wave, mock_pylsl):
        """Set up test fixtures."""
        # Mock sounddevice
        self.mock_sd = MockSoundDevice()
        
        # Create a temp directory for output files
        self.temp_dir = tempfile.TemporaryDirectory()
        
        # Create streamer with mocked dependencies
        with patch('raspberry_pi_lsl_stream.audio_stream.sounddevice') as mock_sounddevice:
            mock_sounddevice.return_value = self.mock_sd
            mock_sounddevice.query_devices.side_effect = self.mock_sd.query_devices
            mock_sounddevice.InputStream.return_value = self.mock_sd.InputStream
            
            self.streamer = LSLAudioStreamer(
                sample_rate=44100,
                channels=1,
                device_index=0,
                stream_name="TestAudio",
                source_id="TestID",
                output_path=self.temp_dir.name,
                bit_depth=16,
                buffer_size_seconds=5,
                use_buffer=True
            )
            
            # Replace sd with mock
            self.streamer.sd = mock_sounddevice
    
    def tearDown(self):
        """Tear down test fixtures."""
        # Stop streamer if running
        if hasattr(self, 'streamer') and self.streamer.running:
            self.streamer.stop()
        
        # Clean up temp directory
        if hasattr(self, 'temp_dir'):
            self.temp_dir.cleanup()
    
    def test_initialization(self):
        """Test that the streamer initializes correctly."""
        self.assertEqual(self.streamer.sample_rate, 44100)
        self.assertEqual(self.streamer.channels, 1)
        self.assertEqual(self.streamer.bit_depth, 16)
        self.assertEqual(self.streamer.buffer_size_seconds, 5)
        self.assertTrue(self.streamer.use_buffer)
        self.assertFalse(self.streamer.running)
        self.assertFalse(self.streamer.is_recording)
    
    @patch('raspberry_pi_lsl_stream.audio_stream.threading.Thread')
    def test_start_stop(self, mock_thread):
        """Test start and stop methods."""
        # Mock thread start
        mock_thread.return_value.start.return_value = None
        mock_thread.return_value.join.return_value = None
        
        # Start streamer
        self.streamer.start()
        self.assertTrue(self.streamer.running)
        
        # Should have started two threads (capture and writer)
        self.assertEqual(mock_thread.call_count, 2)
        
        # Stop streamer
        self.streamer.stop()
        self.assertFalse(self.streamer.running)
    
    @patch('raspberry_pi_lsl_stream.audio_stream.threading.Thread')
    def test_recording_start_stop(self, mock_thread):
        """Test recording start and stop."""
        # Mock wave file
        mock_wave_file = MagicMock()
        self.streamer.audio_file = mock_wave_file
        
        # Mock file creation
        with patch.object(self.streamer, '_create_new_file') as mock_create:
            # Start recording
            self.streamer.start_recording()
            self.assertTrue(self.streamer.is_recording)
            mock_create.assert_called_once()
            
            # Stop recording
            with patch.object(self.streamer, '_close_current_file') as mock_close:
                self.streamer.stop_recording()
                self.assertFalse(self.streamer.is_recording)
                mock_close.assert_called_once()
    
    def test_buffer_functionality(self):
        """Test the rolling buffer mechanism."""
        # Create test audio data
        test_chunk = np.ones((100, 1), dtype=np.int16)
        
        # Fill buffer with test data manually
        for i in range(10):
            for sample in test_chunk:
                self.streamer.audio_buffer.append(sample[0])
        
        # Verify buffer has data
        self.assertEqual(len(self.streamer.audio_buffer), 1000)
        
        # Simulate buffer overflow and check it maintains max size
        for i in range(10):
            for sample in test_chunk:
                self.streamer.audio_buffer.append(sample[0])
        
        # Buffer size should still be limited by maxlen
        self.assertEqual(len(self.streamer.audio_buffer), 
                         self.streamer.buffer_size_samples)
    
    def test_audio_callback(self):
        """Test the audio capture callback."""
        # Create a fake audio stream to get the callback
        input_stream_mock = MagicMock()
        
        # Get the captured callback function
        with patch.object(self.streamer, 'sd') as mock_sd:
            with patch.object(self.streamer, 'audio_stream') as mock_stream:
                # Start streamer to initialize audio stream
                self.streamer.running = True
                self.streamer._audio_capture_thread()
                
                # Get the callback that would be passed to InputStream
                callback_fn = mock_sd.InputStream.call_args[1]['callback']
                
                # Test callback with fake audio data
                test_audio = np.ones((1024, 1), dtype=np.int16)
                
                # Mock LSL outlet
                self.streamer.outlet = MagicMock()
                
                # Call the callback function directly
                callback_fn(test_audio, 1024, {'current_time': time.time()}, None)
                
                # Check that LSL outlet was called
                self.streamer.outlet.push_sample.assert_called_once()
                
                # Check frame count incremented
                self.assertEqual(self.streamer.frame_count, 1)

if __name__ == '__main__':
    unittest.main() 