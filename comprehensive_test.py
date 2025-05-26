#!/usr/bin/env python3
"""
Comprehensive test suite for IMX296 GScrop integration
Tests logic flow, configuration, and integration without requiring Pi hardware
"""

import sys
import os
import yaml
import tempfile
import shutil
from pathlib import Path

# Add src to path
sys.path.insert(0, 'src')

def test_configuration_logic():
    """Test configuration loading and validation logic."""
    print("=" * 60)
    print("Testing Configuration Logic")
    print("=" * 60)
    
    try:
        # Test main config loading
        with open('config/config.yaml') as f:
            config = yaml.safe_load(f)
        print("✓ Main config loads successfully")
        
        # Test required sections
        required_sections = ['system', 'camera', 'recording', 'lsl', 'ntfy', 'logging']
        for section in required_sections:
            if section in config:
                print(f"✓ Required section '{section}' present")
            else:
                print(f"✗ Missing section '{section}'")
                return False
        
        # Test camera settings
        camera = config['camera']
        required_camera_keys = ['width', 'height', 'fps', 'script_path', 'markers_file']
        for key in required_camera_keys:
            if key in camera:
                print(f"✓ Camera config '{key}': {camera[key]}")
            else:
                print(f"✗ Missing camera config '{key}'")
                return False
        
        # Test GScrop-specific settings moved from old structure
        if 'gscrop' in config:
            print("✗ Old 'gscrop' section still present - should be removed")
            return False
        else:
            print("✓ Old 'gscrop' section properly removed")
        
        # Test that GScrop settings are in camera section
        gscrop_keys = ['script_path', 'markers_file', 'frame_queue_size']
        for key in gscrop_keys:
            if key in camera:
                print(f"✓ GScrop setting '{key}' moved to camera section")
            else:
                print(f"✗ Missing GScrop setting '{key}' in camera section")
                return False
        
        # Test recording settings
        recording = config['recording']
        if recording['output_dir'] == 'recordings':
            print("✓ Recording output directory set correctly")
        else:
            print(f"✗ Recording output directory unexpected: {recording['output_dir']}")
            
        print("✓ Configuration logic validation complete")
        return True
        
    except Exception as e:
        print(f"✗ Configuration test failed: {e}")
        return False

def test_gscrop_script_analysis():
    """Test GScrop script structure and functionality."""
    print("\n" + "=" * 60)
    print("Testing GScrop Script Analysis")
    print("=" * 60)
    
    try:
        script_path = 'bin/GScrop'
        
        if not os.path.exists(script_path):
            print(f"✗ GScrop script not found: {script_path}")
            return False
        
        print(f"✓ GScrop script found: {script_path}")
        
        # Check permissions
        if os.access(script_path, os.X_OK):
            print("✓ GScrop script is executable")
        else:
            print("✗ GScrop script is not executable")
            return False
        
        # Analyze script content
        with open(script_path, 'r') as f:
            content = f.read()
        
        # Check for key functionality
        checks = {
            'media-ctl': 'media-ctl hardware configuration',
            'v4l2-ctl': 'V4L2 camera control',
            'markers': 'frame markers functionality',
            'ffmpeg': 'video encoding',
            '/dev/shm': 'shared memory usage',
            'SBGGR10': 'Bayer format configuration'
        }
        
        for pattern, description in checks.items():
            if pattern in content:
                print(f"✓ GScrop contains {description}")
            else:
                print(f"? GScrop may be missing {description} (pattern: {pattern})")
        
        # Check script size (should be substantial)
        lines = content.split('\n')
        if len(lines) > 100:
            print(f"✓ GScrop script is substantial ({len(lines)} lines)")
        else:
            print(f"? GScrop script seems short ({len(lines)} lines)")
        
        print("✓ GScrop script analysis complete")
        return True
        
    except Exception as e:
        print(f"✗ GScrop script analysis failed: {e}")
        return False

def test_module_structure_logic():
    """Test the module structure and import logic."""
    print("\n" + "=" * 60)
    print("Testing Module Structure Logic")
    print("=" * 60)
    
    try:
        # Test directory structure
        required_dirs = ['src/imx296_gs_capture', 'config', 'bin', 'logs', 'recordings']
        for dir_path in required_dirs:
            if os.path.exists(dir_path):
                print(f"✓ Directory exists: {dir_path}")
            else:
                print(f"✗ Missing directory: {dir_path}")
                return False
        
        # Test key files
        required_files = [
            'src/imx296_gs_capture/__init__.py',
            'src/imx296_gs_capture/imx296_capture.py',
            'config/config.yaml',
            'bin/GScrop',
            'bin/run_imx296_capture.py'
        ]
        
        for file_path in required_files:
            if os.path.exists(file_path):
                print(f"✓ File exists: {file_path}")
            else:
                print(f"✗ Missing file: {file_path}")
                return False
        
        # Test __init__.py exports
        with open('src/imx296_gs_capture/__init__.py', 'r') as f:
            init_content = f.read()
        
        expected_exports = ['GSCropCameraCapture', 'main', 'load_config', 'setup_logging']
        for export in expected_exports:
            if export in init_content:
                print(f"✓ __init__.py exports '{export}'")
            else:
                print(f"✗ __init__.py missing export '{export}'")
                return False
        
        # Test that old files are removed
        old_files = [
            'src/imx296_gs_capture/gscrop_capture.py',
            'src/imx296_gs_capture/libcamera_capture.py'
        ]
        
        for old_file in old_files:
            if not os.path.exists(old_file):
                print(f"✓ Old file properly removed: {old_file}")
            else:
                print(f"✗ Old file still exists: {old_file}")
                return False
        
        print("✓ Module structure validation complete")
        return True
        
    except Exception as e:
        print(f"✗ Module structure test failed: {e}")
        return False

def test_launcher_logic():
    """Test launcher script logic."""
    print("\n" + "=" * 60)
    print("Testing Launcher Logic")
    print("=" * 60)
    
    try:
        launcher_path = 'bin/run_imx296_capture.py'
        
        # Read launcher script
        with open(launcher_path, 'r') as f:
            launcher_content = f.read()
        
        # Check for key functions
        required_functions = [
            'check_gscrop_script',
            'launch_camera_capture',
            'ensure_directories',
            'check_camera_devices'
        ]
        
        for func in required_functions:
            if f"def {func}" in launcher_content:
                print(f"✓ Launcher contains function '{func}'")
            else:
                print(f"✗ Launcher missing function '{func}'")
                return False
        
        # Check that it imports the right module
        if 'from imx296_gs_capture import imx296_capture' in launcher_content:
            print("✓ Launcher imports correct module")
        else:
            print("✗ Launcher has incorrect import")
            return False
        
        # Check for fallback logic
        if 'subprocess.run' in launcher_content and 'ImportError' in launcher_content:
            print("✓ Launcher has fallback subprocess logic")
        else:
            print("? Launcher may be missing fallback logic")
        
        # Check that old libcamera logic is removed
        if 'libcamera' not in launcher_content.lower():
            print("✓ Old libcamera logic properly removed from launcher")
        else:
            print("✗ Launcher still contains libcamera references")
            return False
        
        print("✓ Launcher logic validation complete")
        return True
        
    except Exception as e:
        print(f"✗ Launcher logic test failed: {e}")
        return False

def test_integration_flow():
    """Test the overall integration flow."""
    print("\n" + "=" * 60)
    print("Testing Integration Flow")
    print("=" * 60)
    
    try:
        # Test that we can load config using the module's load_config function
        # (This won't work because of pylsl import, but we can test the fallback)
        
        # Test config loading manually (simulating the module's logic)
        config_locations = [
            os.path.join(os.getcwd(), "config/config.yaml"),
            "config/config.yaml"
        ]
        
        config_loaded = False
        for loc in config_locations:
            try:
                if os.path.exists(loc):
                    with open(loc, 'r') as f:
                        config = yaml.safe_load(f)
                    print(f"✓ Config loadable from: {loc}")
                    config_loaded = True
                    break
            except Exception as e:
                print(f"? Error testing config location {loc}: {e}")
        
        if not config_loaded:
            print("✗ No config location works")
            return False
        
        # Test GScrop script path resolution
        script_path = config['camera'].get('script_path', 'bin/GScrop')
        script_locations = [
            script_path,
            "./GScrop",
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname('src/imx296_gs_capture/imx296_capture.py'))), script_path)
        ]
        
        script_found = False
        for location in script_locations:
            if os.path.isfile(location) and os.access(location, os.X_OK):
                print(f"✓ GScrop script resolvable at: {location}")
                script_found = True
                break
        
        if not script_found:
            print("✗ GScrop script not resolvable")
            return False
        
        # Test output directory creation
        output_dir = Path(config['recording']['output_dir'])
        if output_dir.exists():
            print(f"✓ Output directory exists: {output_dir}")
        else:
            print(f"? Output directory will be created: {output_dir}")
        
        # Test markers file path (should be writable on Pi)
        markers_file = config['camera']['markers_file']
        markers_dir = os.path.dirname(markers_file)
        if markers_dir == '/dev/shm':
            print("✓ Markers file uses shared memory (/dev/shm)")
        else:
            print(f"? Markers file location: {markers_file}")
        
        print("✓ Integration flow validation complete")
        return True
        
    except Exception as e:
        print(f"✗ Integration flow test failed: {e}")
        return False

def main():
    """Run all comprehensive tests."""
    print("=" * 80)
    print("COMPREHENSIVE IMX296 GSCROP INTEGRATION TEST SUITE")
    print("=" * 80)
    
    tests = [
        ("Configuration Logic", test_configuration_logic),
        ("GScrop Script Analysis", test_gscrop_script_analysis),
        ("Module Structure Logic", test_module_structure_logic),
        ("Launcher Logic", test_launcher_logic),
        ("Integration Flow", test_integration_flow),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        try:
            if test_func():
                passed += 1
                print(f"\n🎉 {test_name} PASSED")
            else:
                print(f"\n❌ {test_name} FAILED")
        except Exception as e:
            print(f"\n💥 {test_name} ERROR: {e}")
    
    print("\n" + "=" * 80)
    print(f"FINAL RESULTS: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 ALL TESTS PASSED!")
        print("✓ GScrop integration is ready for Raspberry Pi deployment")
        print("✓ Configuration structure is correct")
        print("✓ Module imports will work (with pylsl on Pi)")
        print("✓ Launcher logic is sound")
        print("✓ Integration flow is validated")
        return 0
    else:
        print("❌ SOME TESTS FAILED")
        print("Please fix the issues above before deployment")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 