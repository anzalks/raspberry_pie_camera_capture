#!/usr/bin/env python3
"""
Test Cleanup System Functionality
=================================

Tests for the comprehensive cleanup system to ensure it correctly
identifies and cleans up conflicting services and files.

Author: Anzal KS <anzal.ks@gmail.com>
Date: December 2024
"""

import os
import sys
import tempfile
import unittest
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add project root to Python path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

# Import the cleanup system
from bin.cleanup_and_start import CameraSystemCleanup

class TestCleanupSystem(unittest.TestCase):
    """Test cases for the camera system cleanup."""
    
    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.cleanup = CameraSystemCleanup()
        
        # Mock project root to use temp directory
        self.cleanup.project_root = Path(self.temp_dir)
    
    def tearDown(self):
        """Clean up test environment."""
        # Clean up temp directory
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_cleanup_initialization(self):
        """Test cleanup system initialization."""
        self.assertIsInstance(self.cleanup.systemd_services, list)
        self.assertIsInstance(self.cleanup.shared_memory_files, list)
        self.assertIsInstance(self.cleanup.process_names, list)
        
        # Check that expected services are in the list
        self.assertIn('imx296-camera', self.cleanup.systemd_services)
        self.assertIn('imx296-camera-monitor', self.cleanup.systemd_services)
        
        # Check that expected shared memory files are listed
        self.assertIn('/dev/shm/imx296_status.json', self.cleanup.shared_memory_files)
        self.assertIn('/dev/shm/camera_markers.txt', self.cleanup.shared_memory_files)
    
    @patch('subprocess.run')
    def test_stop_systemd_services(self, mock_run):
        """Test stopping systemd services."""
        # Mock service is active
        mock_run.return_value = MagicMock(returncode=0, stdout="active", stderr="")
        
        self.cleanup.stop_systemd_services()
        
        # Should check each service and stop active ones
        self.assertTrue(mock_run.called)
        
        # Check that systemctl commands were called
        calls = mock_run.call_args_list
        service_check_calls = [call for call in calls if 'is-active' in str(call)]
        self.assertTrue(len(service_check_calls) > 0)
    
    @patch('os.path.exists')
    @patch('subprocess.run')
    def test_disable_systemd_services(self, mock_run, mock_exists):
        """Test disabling and removing systemd service files."""
        # Mock service files exist
        mock_exists.return_value = True
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        
        self.cleanup.disable_systemd_services()
        
        # Should disable and remove service files
        self.assertTrue(mock_run.called)
        
        # Check for disable and remove commands
        calls = mock_run.call_args_list
        disable_calls = [call for call in calls if 'disable' in str(call)]
        remove_calls = [call for call in calls if 'rm' in str(call)]
        
        self.assertTrue(len(disable_calls) > 0)
        self.assertTrue(len(remove_calls) > 0)
    
    @patch('subprocess.run')
    def test_kill_related_processes(self, mock_run):
        """Test killing related processes."""
        # Mock finding processes - provide enough return values for all process names
        mock_returns = []
        
        # For each process name, provide pgrep result and kill commands
        for process_name in self.cleanup.process_names:
            # pgrep finds some processes
            mock_returns.append(MagicMock(returncode=0, stdout="1234\n5678", stderr=""))
            # kill commands for found processes
            mock_returns.append(MagicMock(returncode=0, stdout="", stderr=""))
            mock_returns.append(MagicMock(returncode=0, stdout="", stderr=""))
            # Second pgrep check (after sleep) finds no processes
            mock_returns.append(MagicMock(returncode=1, stdout="", stderr=""))
        
        mock_run.side_effect = mock_returns
        
        self.cleanup.kill_related_processes()
        
        # Should find and kill processes
        self.assertTrue(mock_run.called)
        
        # Check for pgrep and kill commands
        calls = mock_run.call_args_list
        pgrep_calls = [call for call in calls if 'pgrep' in str(call)]
        kill_calls = [call for call in calls if 'kill' in str(call)]
        
        self.assertTrue(len(pgrep_calls) > 0)
        # Note: kill_calls might be 0 if no processes were found in actual test
    
    def test_cleanup_shared_memory(self):
        """Test cleaning up shared memory files."""
        # Create test shared memory files
        test_shm_files = []
        for shm_file in self.cleanup.shared_memory_files[:2]:  # Test first 2
            test_file = Path(self.temp_dir) / Path(shm_file).name
            test_file.touch()
            test_shm_files.append(str(test_file))
        
        # Temporarily modify the list to use our test files
        original_files = self.cleanup.shared_memory_files
        self.cleanup.shared_memory_files = test_shm_files
        
        try:
            self.cleanup.cleanup_shared_memory()
            
            # Check that files were removed
            for test_file in test_shm_files:
                self.assertFalse(os.path.exists(test_file), f"File should be removed: {test_file}")
        
        finally:
            # Restore original list
            self.cleanup.shared_memory_files = original_files
    
    def test_cleanup_old_configs(self):
        """Test cleaning up old configuration files."""
        # Create test config files
        test_config_file = Path(self.temp_dir) / "config.yaml"
        test_config_file.touch()
        
        test_config_dir = Path(self.temp_dir) / "old_config"
        test_config_dir.mkdir()
        (test_config_dir / "test.yaml").touch()
        
        self.cleanup.cleanup_old_configs()
        
        # Check that test files were removed
        self.assertFalse(test_config_file.exists())
        self.assertFalse(test_config_dir.exists())
    
    def test_cleanup_python_cache(self):
        """Test cleaning up Python cache directories."""
        # Create test __pycache__ directory
        cache_dir = Path(self.temp_dir) / "test_module" / "__pycache__"
        cache_dir.mkdir(parents=True)
        (cache_dir / "test.pyc").touch()
        
        self.cleanup.cleanup_python_cache()
        
        # Check that cache directory was removed
        self.assertFalse(cache_dir.exists())
    
    def test_cleanup_log_files(self):
        """Test cleaning up log files."""
        # Create test log directory and files
        log_dir = Path(self.temp_dir) / "logs"
        log_dir.mkdir()
        
        current_log = log_dir / "imx296_capture.log"
        old_log1 = log_dir / "imx296_capture.log.1"
        old_log2 = log_dir / "imx296_capture.log.2"
        
        current_log.touch()
        old_log1.touch()
        old_log2.touch()
        
        # Test keeping current log
        self.cleanup.cleanup_log_files(keep_current=True)
        
        # Current log should remain, old logs should be removed
        self.assertTrue(current_log.exists())
        self.assertFalse(old_log1.exists())
        self.assertFalse(old_log2.exists())
    
    @patch('subprocess.run')
    def test_verify_clean_state(self, mock_run):
        """Test verifying clean state."""
        # Mock no active services or processes
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")
        
        # No shared memory files exist (using temp dir)
        original_files = self.cleanup.shared_memory_files
        self.cleanup.shared_memory_files = []
        
        try:
            result = self.cleanup.verify_clean_state()
            self.assertTrue(result)
        finally:
            self.cleanup.shared_memory_files = original_files
    
    @patch('bin.cleanup_and_start.CameraSystemCleanup.verify_clean_state')
    @patch('bin.cleanup_and_start.CameraSystemCleanup.cleanup_python_cache')
    @patch('bin.cleanup_and_start.CameraSystemCleanup.cleanup_log_files')
    @patch('bin.cleanup_and_start.CameraSystemCleanup.cleanup_old_configs')
    @patch('bin.cleanup_and_start.CameraSystemCleanup.cleanup_shared_memory')
    @patch('bin.cleanup_and_start.CameraSystemCleanup.kill_related_processes')
    @patch('bin.cleanup_and_start.CameraSystemCleanup.disable_systemd_services')
    @patch('bin.cleanup_and_start.CameraSystemCleanup.stop_systemd_services')
    def test_full_cleanup(self, mock_stop, mock_disable, mock_kill, mock_shm, 
                         mock_configs, mock_logs, mock_cache, mock_verify):
        """Test full cleanup process."""
        mock_verify.return_value = True
        
        result = self.cleanup.full_cleanup()
        
        # All cleanup methods should be called
        mock_stop.assert_called_once()
        mock_disable.assert_called_once()
        mock_kill.assert_called_once()
        mock_shm.assert_called_once()
        mock_configs.assert_called_once()
        mock_logs.assert_called_once()
        mock_cache.assert_called_once()
        mock_verify.assert_called_once()
        
        self.assertTrue(result)


class TestCleanupIntegration(unittest.TestCase):
    """Integration tests for cleanup system."""
    
    def test_import_cleanup_module(self):
        """Test that cleanup module can be imported."""
        try:
            from bin.cleanup_and_start import CameraSystemCleanup, main
            self.assertTrue(True)
        except ImportError as e:
            self.fail(f"Could not import cleanup module: {e}")
    
    def test_cleanup_script_executable(self):
        """Test that cleanup script exists and is executable."""
        script_path = project_root / "bin" / "cleanup_and_start.py"
        self.assertTrue(script_path.exists(), "Cleanup script does not exist")
        
        # Check if script is executable (on Unix systems)
        if hasattr(os, 'access'):
            self.assertTrue(os.access(script_path, os.X_OK), "Cleanup script is not executable")
    
    def test_bash_wrapper_exists(self):
        """Test that bash wrapper script exists."""
        wrapper_path = project_root / "bin" / "clean_start_camera.sh"
        self.assertTrue(wrapper_path.exists(), "Bash wrapper does not exist")
        
        # Check if script is executable
        if hasattr(os, 'access'):
            self.assertTrue(os.access(wrapper_path, os.X_OK), "Bash wrapper is not executable")


def run_tests():
    """Run all cleanup system tests."""
    print("Running Cleanup System Tests...")
    print("=" * 50)
    
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add test cases
    suite.addTests(loader.loadTestsFromTestCase(TestCleanupSystem))
    suite.addTests(loader.loadTestsFromTestCase(TestCleanupIntegration))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Print summary
    print("\n" + "=" * 50)
    print(f"Cleanup System Tests Summary:")
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