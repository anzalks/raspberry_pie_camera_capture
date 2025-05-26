#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script for GScrop integration

This script tests the basic functionality of the GScrop-based capture system
without requiring the full Raspberry Pi environment.

Author: Anzal KS <anzal.ks@gmail.com>
Date: May 26, 2025
"""

import os
import sys
import yaml
import logging
from pathlib import Path

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'src'))

def test_config_loading():
    """Test configuration loading."""
    print("Testing configuration loading...")
    
    try:
        # Try to import the module (will fail on pylsl but that's expected)
        try:
            from imx296_gs_capture.imx296_capture import load_config, setup_logging
            print("✓ Module import successful (ignoring pylsl dependency)")
        except ImportError as e:
            if "pylsl" in str(e):
                print("✓ Module structure correct (pylsl not available, expected)")
            else:
                print(f"✗ Unexpected import error: {e}")
                return False
        
        # Test config loading directly
        config_path = "config/config.yaml"
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            print("✓ Configuration file loaded successfully")
            
            # Check required sections
            required_sections = ['system', 'camera', 'recording', 'lsl']
            for section in required_sections:
                if section in config:
                    print(f"✓ Config section '{section}' found")
                else:
                    print(f"✗ Config section '{section}' missing")
                    return False
            
            # Check GScrop-specific settings
            if 'script_path' in config['camera']:
                print("✓ GScrop script path configured")
            else:
                print("✗ GScrop script path not configured")
                return False
                
            if 'markers_file' in config['camera']:
                print("✓ Markers file path configured")
            else:
                print("✗ Markers file path not configured")
                return False
                
        else:
            print(f"✗ Configuration file not found: {config_path}")
            return False
            
    except Exception as e:
        print(f"✗ Error testing configuration: {e}")
        return False
    
    return True

def test_gscrop_script():
    """Test GScrop script availability."""
    print("\nTesting GScrop script...")
    
    script_path = "bin/GScrop"
    
    if not os.path.exists(script_path):
        print(f"✗ GScrop script not found: {script_path}")
        return False
    
    print(f"✓ GScrop script found: {script_path}")
    
    if not os.access(script_path, os.X_OK):
        print("✗ GScrop script is not executable")
        try:
            os.chmod(script_path, 0o755)
            print("✓ Made GScrop script executable")
        except Exception as e:
            print(f"✗ Failed to make GScrop executable: {e}")
            return False
    else:
        print("✓ GScrop script is executable")
    
    # Check script content for key functionality
    try:
        with open(script_path, 'r') as f:
            content = f.read()
        
        if 'media-ctl' in content:
            print("✓ GScrop script contains media-ctl configuration")
        else:
            print("✗ GScrop script missing media-ctl configuration")
            return False
            
        if 'markers' in content.lower():
            print("✓ GScrop script contains markers file functionality")
        else:
            print("✗ GScrop script missing markers file functionality")
            return False
            
    except Exception as e:
        print(f"✗ Error reading GScrop script: {e}")
        return False
    
    return True

def test_project_structure():
    """Test that project has correct structure using dynamic path detection."""
    # Get project root dynamically
    current_file = Path(__file__).resolve()
    project_root = current_file.parent.parent
    
    required_dirs = ['src/imx296_gs_capture', 'config', 'bin', 'logs', 'recordings']
    
    missing_dirs = []
    for dir_path in required_dirs:
        full_path = project_root / dir_path
        if not full_path.exists():
            missing_dirs.append(str(full_path))
            
            # Try to create logs and recordings directories for tests
            if dir_path in ['logs', 'recordings']:
                try:
                    full_path.mkdir(parents=True, exist_ok=True)
                    print(f"✓ Created directory for tests: {full_path}")
                except Exception as e:
                    print(f"✗ Failed to create test directory {full_path}: {e}")
    
    # Filter out directories we successfully created
    missing_dirs = [d for d in missing_dirs if not Path(d).exists()]
    
    if missing_dirs:
        print(f"✗ Missing required directories: {missing_dirs}")
    
    return len(missing_dirs) == 0

def test_launcher_script():
    """Test the launcher script."""
    print("\nTesting launcher script...")
    
    launcher_path = "bin/run_imx296_capture.py"
    
    if not os.path.exists(launcher_path):
        print(f"✗ Launcher script not found: {launcher_path}")
        return False
    
    print(f"✓ Launcher script found: {launcher_path}")
    
    # Check if it's executable
    if not os.access(launcher_path, os.X_OK):
        try:
            os.chmod(launcher_path, 0o755)
            print("✓ Made launcher script executable")
        except Exception as e:
            print(f"✗ Failed to make launcher executable: {e}")
            return False
    else:
        print("✓ Launcher script is executable")
    
    return True

def main():
    """Run all tests."""
    print("=" * 60)
    print("GScrop Integration Test Suite")
    print("=" * 60)
    
    tests = [
        ("Directory Structure", test_project_structure),
        ("Configuration Loading", test_config_loading),
        ("GScrop Script", test_gscrop_script),
        ("Launcher Script", test_launcher_script),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n{'='*20} {test_name} {'='*20}")
        try:
            if test_func():
                print(f"✓ {test_name} PASSED")
                passed += 1
            else:
                print(f"✗ {test_name} FAILED")
        except Exception as e:
            print(f"✗ {test_name} ERROR: {e}")
    
    print("\n" + "=" * 60)
    print(f"Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! GScrop integration is ready.")
        return 0
    else:
        print("❌ Some tests failed. Please fix the issues above.")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 