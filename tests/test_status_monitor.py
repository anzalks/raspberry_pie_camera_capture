#!/usr/bin/env python3
"""
Test Status Monitor Functionality
=================================

Tests for the real-time status monitor system to ensure it correctly
reads status data and displays information.

Author: Anzal KS <anzal.ks@gmail.com>
Date: December 2024
"""

import os
import sys
import json
import time
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add project root to Python path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

# Import the status monitor
from bin.status_monitor import CameraStatusMonitor

class TestStatusMonitor(unittest.TestCase):
    """Test cases for the camera status monitor."""
    
    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.test_status_file = os.path.join(self.temp_dir, "test_status.json")
        
        # Create test monitor with custom status file
        self.monitor = CameraStatusMonitor()
        
        # Patch the status file location
        self.status_file_patcher = patch('bin.status_monitor.STATUS_FILE', self.test_status_file)
        self.status_file_patcher.start()
    
    def tearDown(self):
        """Clean up test environment."""
        self.status_file_patcher.stop()
        
        # Clean up temp files
        if os.path.exists(self.test_status_file):
            os.remove(self.test_status_file)
        os.rmdir(self.temp_dir)
    
    def test_load_status_default(self):
        """Test loading status when no file exists."""
        status = self.monitor.load_status()
        
        # Should return default status
        self.assertFalse(status['service_running'])
        self.assertEqual(status['uptime'], 0)
        self.assertFalse(status['lsl_status']['connected'])
        self.assertEqual(status['buffer_status']['current_size'], 0)
    
    def test_load_status_from_file(self):
        """Test loading status from existing file."""
        # Create test status data
        test_status = {
            'service_running': True,
            'uptime': 123.45,
            'lsl_status': {
                'connected': True,
                'samples_sent': 1000,
                'samples_per_second': 100.0,
                'last_sample': [500, 1640995200.0, 1]
            },
            'buffer_status': {
                'current_size': 750,
                'max_size': 1500,
                'utilization_percent': 50.0,
                'oldest_frame_age': 10
            },
            'recording_status': {
                'active': True,
                'current_file': '/path/to/recording.mkv',
                'frames_recorded': 500,
                'duration': 5.0
            },
            'video_status': {
                'recording': True,
                'current_file': '/path/to/video.mkv',
                'duration': 5.0
            },
            'trigger_status': {
                'last_trigger_type': 1,
                'last_trigger_time': 1640995200.0,
                'trigger_count': 5
            },
            'system_info': {
                'cpu_percent': 25.5,
                'memory_percent': 60.2,
                'disk_usage_percent': 45.8
            }
        }
        
        # Write test data to file
        with open(self.test_status_file, 'w') as f:
            json.dump(test_status, f)
        
        # Load and verify
        status = self.monitor.load_status()
        self.assertTrue(status['service_running'])
        self.assertEqual(status['uptime'], 123.45)
        self.assertTrue(status['lsl_status']['connected'])
        self.assertEqual(status['lsl_status']['samples_sent'], 1000)
        self.assertEqual(status['buffer_status']['current_size'], 750)
        self.assertEqual(status['buffer_status']['utilization_percent'], 50.0)
        self.assertTrue(status['recording_status']['active'])
        self.assertEqual(status['trigger_status']['trigger_count'], 5)
    
    def test_format_uptime(self):
        """Test uptime formatting."""
        # Test seconds
        self.assertEqual(self.monitor.format_uptime(30), "30s")
        
        # Test minutes
        self.assertEqual(self.monitor.format_uptime(90), "1m 30s")
        
        # Test hours
        self.assertEqual(self.monitor.format_uptime(3665), "1h 1m")
    
    def test_format_file_size(self):
        """Test file size formatting."""
        self.assertEqual(self.monitor.format_file_size(512), "512B")
        self.assertEqual(self.monitor.format_file_size(1536), "1.5KB")
        self.assertEqual(self.monitor.format_file_size(1048576), "1.0MB")
        self.assertEqual(self.monitor.format_file_size(1073741824), "1.0GB")
    
    def test_get_trigger_type_name(self):
        """Test trigger type name mapping."""
        self.assertEqual(self.monitor.get_trigger_type_name(0), "None")
        self.assertEqual(self.monitor.get_trigger_type_name(1), "Keyboard")
        self.assertEqual(self.monitor.get_trigger_type_name(2), "ntfy")
        self.assertEqual(self.monitor.get_trigger_type_name(99), "Unknown")
    
    def test_load_status_invalid_json(self):
        """Test loading status with invalid JSON."""
        # Write invalid JSON
        with open(self.test_status_file, 'w') as f:
            f.write("invalid json content")
        
        # Should return default status
        status = self.monitor.load_status()
        self.assertFalse(status['service_running'])
    
    @patch('curses.wrapper')
    def test_monitor_initialization(self, mock_wrapper):
        """Test monitor initialization and main function."""
        from bin.status_monitor import main
        
        # Mock curses wrapper to avoid actual terminal interaction
        mock_wrapper.return_value = 0
        
        # Test main function
        with patch('bin.status_monitor.os.path.exists', return_value=True):
            result = main()
            self.assertEqual(result, 0)
            mock_wrapper.assert_called_once()


class TestStatusMonitorIntegration(unittest.TestCase):
    """Integration tests for status monitor with camera system."""
    
    def setUp(self):
        """Set up integration test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.test_status_file = os.path.join(self.temp_dir, "integration_status.json")
    
    def tearDown(self):
        """Clean up integration test environment."""
        if os.path.exists(self.test_status_file):
            os.remove(self.test_status_file)
        os.rmdir(self.temp_dir)
    
    def test_status_file_creation_simulation(self):
        """Test simulated status file creation by camera service."""
        # Simulate camera service writing status
        camera_status = {
            'service_running': True,
            'uptime': 60.0,
            'lsl_status': {
                'connected': True,
                'samples_sent': 6000,
                'samples_per_second': 100.0,
                'last_sample': [6000, time.time(), 0]
            },
            'buffer_status': {
                'current_size': 1200,
                'max_size': 1500,
                'utilization_percent': 80.0,
                'oldest_frame_age': 12
            },
            'recording_status': {
                'active': False,
                'current_file': None,
                'frames_recorded': 0,
                'duration': 0
            },
            'video_status': {
                'recording': True,
                'current_file': '/tmp/test_video.mkv',
                'duration': 60.0
            },
            'trigger_status': {
                'last_trigger_type': 0,
                'last_trigger_time': 0,
                'trigger_count': 0
            },
            'system_info': {
                'cpu_percent': 15.2,
                'memory_percent': 45.8,
                'disk_usage_percent': 30.1
            }
        }
        
        # Write status file
        with open(self.test_status_file, 'w') as f:
            json.dump(camera_status, f)
        
        # Create monitor and load status
        monitor = CameraStatusMonitor()
        
        with patch('bin.status_monitor.STATUS_FILE', self.test_status_file):
            status = monitor.load_status()
        
        # Verify status was loaded correctly
        self.assertTrue(status['service_running'])
        self.assertEqual(status['uptime'], 60.0)
        self.assertTrue(status['lsl_status']['connected'])
        self.assertEqual(status['lsl_status']['samples_sent'], 6000)
        self.assertEqual(status['buffer_status']['utilization_percent'], 80.0)
        self.assertTrue(status['video_status']['recording'])
        self.assertEqual(status['system_info']['cpu_percent'], 15.2)


def run_tests():
    """Run all status monitor tests."""
    print("Running Status Monitor Tests...")
    print("=" * 50)
    
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add test cases
    suite.addTests(loader.loadTestsFromTestCase(TestStatusMonitor))
    suite.addTests(loader.loadTestsFromTestCase(TestStatusMonitorIntegration))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Print summary
    print("\n" + "=" * 50)
    print(f"Status Monitor Tests Summary:")
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
    print(f"\nOverall: {'✅ PASSED' if success else '❌ FAILED'}")
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(run_tests()) 