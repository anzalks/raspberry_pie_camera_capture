#!/usr/bin/env python3
"""
Simple Integration Test
=======================

Basic test to verify the integrated system components work.

Author: Anzal KS <anzal.ks@gmail.com>
Date: May 23, 2025
"""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

def test_imports():
    """Test that all modules can be imported."""
    print("Testing imports...")
    
    try:
        from src.imx296_gs_capture.ntfy_handler import NtfyHandler
        print("✅ NtfyHandler imported successfully")
    except ImportError as e:
        print(f"❌ Failed to import NtfyHandler: {e}")
        return False
    
    try:
        from src.imx296_gs_capture.video_recorder import VideoRecorder
        print("✅ VideoRecorder imported successfully")
    except ImportError as e:
        print(f"❌ Failed to import VideoRecorder: {e}")
        return False
    
    try:
        from src.imx296_gs_capture.imx296_capture import GSCropCameraCapture, load_config
        print("✅ GSCropCameraCapture imported successfully")
    except ImportError as e:
        print(f"❌ Failed to import GSCropCameraCapture: {e}")
        return False
    
    return True

def test_config_loading():
    """Test configuration loading."""
    print("\nTesting configuration loading...")
    
    try:
        from src.imx296_gs_capture.imx296_capture import load_config
        config = load_config("config/config.yaml")
        
        # Check required sections
        required_sections = ['camera', 'recording', 'lsl', 'ntfy']
        for section in required_sections:
            if section not in config:
                print(f"❌ Missing config section: {section}")
                return False
        
        print("✅ Configuration loaded successfully")
        print(f"   Camera: {config['camera']['width']}x{config['camera']['height']}@{config['camera']['fps']}fps")
        print(f"   LSL: {config['lsl']['name']}")
        print(f"   ntfy: {config['ntfy']['topic']}")
        return True
        
    except Exception as e:
        print(f"❌ Failed to load configuration: {e}")
        return False

def test_ntfy_handler():
    """Test ntfy handler initialization."""
    print("\nTesting ntfy handler...")
    
    try:
        from src.imx296_gs_capture.ntfy_handler import NtfyHandler
        
        test_config = {
            'server': 'https://ntfy.sh',
            'topic': 'test-topic',
            'poll_interval_sec': 2
        }
        
        def dummy_callback(command, params):
            print(f"Received command: {command} with params: {params}")
        
        handler = NtfyHandler(test_config, dummy_callback)
        
        # Test command parsing
        result = handler._parse_command('start_recording 30')
        if result['command'] == 'start_recording' and result['params']['duration'] == 30.0:
            print("✅ ntfy handler initialized and command parsing works")
            return True
        else:
            print("❌ Command parsing failed")
            return False
            
    except Exception as e:
        print(f"❌ Failed to test ntfy handler: {e}")
        return False

def test_video_recorder():
    """Test video recorder initialization."""
    print("\nTesting video recorder...")
    
    try:
        from src.imx296_gs_capture.video_recorder import VideoRecorder
        
        test_config = {
            'output_dir': 'test_recordings',
            'video_format': 'mkv',
            'codec': 'mjpeg',
            'quality': 90
        }
        
        recorder = VideoRecorder(test_config)
        
        # Test path generation
        from datetime import datetime
        test_time = datetime(2025, 5, 23, 14, 30, 45)
        path = recorder._get_recording_path(test_time)
        
        expected_filename = "2025_05_23_14_30_45.mkv"
        if path.name == expected_filename:
            print("✅ Video recorder initialized and path generation works")
            return True
        else:
            print(f"❌ Path generation failed: expected {expected_filename}, got {path.name}")
            return False
            
    except Exception as e:
        print(f"❌ Failed to test video recorder: {e}")
        return False

def test_gscrop_script():
    """Test GScrop script availability."""
    print("\nTesting GScrop script...")
    
    gscrop_path = Path("bin/GScrop")
    if gscrop_path.exists() and os.access(gscrop_path, os.X_OK):
        print("✅ GScrop script found and executable")
        return True
    else:
        print(f"❌ GScrop script not found or not executable at {gscrop_path}")
        return False

def main():
    """Run all tests."""
    print("Simple Integration Test Suite")
    print("=" * 40)
    
    tests = [
        test_imports,
        test_config_loading,
        test_ntfy_handler,
        test_video_recorder,
        test_gscrop_script
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"❌ Test {test.__name__} failed with exception: {e}")
    
    print("\n" + "=" * 40)
    print(f"Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed!")
        return True
    else:
        print("❌ Some tests failed")
        return False

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1) 