#!/usr/bin/env python3
"""
Camera Environment Check Script
-------------------------------
Checks environment configuration for Raspberry Pi Camera Capture System
Tests for camera detection, proper permissions, and Global Shutter Camera
"""

import os
import sys
import platform
import subprocess
import glob
import time
import traceback

# ANSI color codes for terminal output
GREEN = '\033[0;32m'
YELLOW = '\033[1;33m'
RED = '\033[0;31m'
BLUE = '\033[0;34m'
NC = '\033[0m'  # No Color

def print_status(message, status=None):
    """Print a status message with optional status indicator."""
    if status is True:
        print(f"{BLUE}[INFO]{NC} {message}")
    elif status is False:
        print(f"{RED}[FAIL]{NC} {message}")
    elif status == "warning":
        print(f"{YELLOW}[WARN]{NC} {message}")
    elif status == "success":
        print(f"{GREEN}[PASS]{NC} {message}")
    else:
        print(message)

def check_system_info():
    """Check system information."""
    print_status("\n=== System Information ===", True)
    print(f"Platform: {platform.platform()}")
    print(f"Python: {platform.python_version()}")
    print(f"Architecture: {platform.machine()}")
    
    # Check if running on Raspberry Pi
    is_raspberry_pi = False
    try:
        with open('/proc/cpuinfo', 'r') as f:
            cpuinfo = f.read()
        if 'Raspberry Pi' in cpuinfo or 'BCM' in cpuinfo:
            is_raspberry_pi = True
            model = [line for line in cpuinfo.split('\n') if 'Model' in line]
            if model:
                print(f"Raspberry Pi Model: {model[0].split(':')[1].strip()}")
            
            # Check if it's a Raspberry Pi 5
            if 'Revision' in cpuinfo and any(rev in cpuinfo for rev in ['a02140', 'd04170', 'c04170']):
                print(f"{GREEN}Detected Raspberry Pi 5{NC}")
    except Exception as e:
        print_status(f"Error checking Raspberry Pi hardware: {e}", False)
    
    if is_raspberry_pi:
        print_status("Detected Raspberry Pi hardware", "success")
    else:
        print_status("Not running on Raspberry Pi hardware", "warning")

def check_camera_modules():
    """Check if camera modules are loaded."""
    print_status("\n=== Camera Modules ===", True)
    
    try:
        # Check for V4L2 modules
        lsmod_output = subprocess.check_output(['lsmod'], text=True)
        if 'videodev' in lsmod_output:
            print_status("V4L2 modules loaded", "success")
        else:
            print_status("V4L2 modules not loaded", False)
            print_status("Try running: sudo modprobe videodev", "warning")
    except Exception as e:
        print_status(f"Error checking camera modules: {e}", False)
    
    try:
        # Check if picamera2 is available
        import importlib
        picamera2_spec = importlib.util.find_spec("picamera2")
        if picamera2_spec is not None:
            import picamera2
            print_status(f"picamera2 is installed: {getattr(picamera2, '__version__', 'version unknown')}", "success")
        else:
            print_status("picamera2 is not installed", False)
            print_status("Try running: sudo apt install -y python3-picamera2", "warning")
    except Exception as e:
        print_status(f"Error checking picamera2: {e}", False)

def check_camera_devices():
    """Check for camera devices."""
    print_status("\n=== Camera Devices ===", True)
    
    # Check for video devices
    video_devices = glob.glob('/dev/video*')
    if video_devices:
        print_status(f"Found {len(video_devices)} video devices:", "success")
        for dev in video_devices:
            try:
                # Check permissions
                stat_info = os.stat(dev)
                mode = stat_info.st_mode
                perms = oct(mode)[-3:]  # Get last 3 digits (file permissions)
                
                # Check if device has rw permissions for user/group/others (666)
                if perms == '666':
                    print(f"  {dev}: Permissions {perms} {GREEN}OK{NC}")
                else:
                    print(f"  {dev}: Permissions {perms} {RED}NOT OPTIMAL{NC} (should be 666)")
                    print_status(f"    Run: sudo chmod 666 {dev}", "warning")
            except Exception as e:
                print(f"  {dev}: Error checking permissions: {e}")
    else:
        print_status("No video devices found", False)
        print_status("Camera may not be connected or enabled", "warning")
    
    # Check for media devices (important for Global Shutter Camera)
    media_devices = glob.glob('/dev/media*')
    if media_devices:
        print_status(f"Found {len(media_devices)} media devices:", "success")
        for dev in media_devices:
            try:
                # Check permissions
                stat_info = os.stat(dev)
                mode = stat_info.st_mode
                perms = oct(mode)[-3:]  # Get last 3 digits
                
                # Check if device has rw permissions for user/group/others (666)
                if perms == '666':
                    print(f"  {dev}: Permissions {perms} {GREEN}OK{NC}")
                else:
                    print(f"  {dev}: Permissions {perms} {RED}NOT OPTIMAL{NC} (should be 666)")
                    print_status(f"    Run: sudo chmod 666 {dev}", "warning")
            except Exception as e:
                print(f"  {dev}: Error checking permissions: {e}")
    else:
        print_status("No media devices found", False)
        print_status("Media control may not be available for Global Shutter Camera", "warning")

def check_global_shutter_camera():
    """Check for Global Shutter Camera."""
    print_status("\n=== Global Shutter Camera Detection ===", True)
    
    # Check if media-ctl is available
    try:
        subprocess.check_output(['which', 'media-ctl'])
        print_status("media-ctl is installed", "success")
    except subprocess.CalledProcessError:
        print_status("media-ctl is not installed", False)
        print_status("Install with: sudo apt install -y libcamera-tools media-ctl", "warning")
        return
    
    # Check for IMX296 sensor
    gs_detected = False
    
    try:
        # Method 1: Try using media-ctl to detect IMX296
        for m in range(6):  # Try media devices 0-5
            try:
                output = subprocess.check_output(['media-ctl', '-d', f'/dev/media{m}', '-p'], 
                                                text=True, stderr=subprocess.PIPE)
                if 'imx296' in output.lower():
                    print_status(f"Found Global Shutter Camera (IMX296) on /dev/media{m}", "success")
                    gs_detected = True
                    
                    # Try to get more details
                    print("\nSensor details:")
                    print(output)
                    break
            except (subprocess.CalledProcessError, FileNotFoundError):
                pass
        
        # Method 2: Try v4l2-ctl as a fallback
        if not gs_detected:
            try:
                output = subprocess.check_output(['v4l2-ctl', '--list-devices'], text=True)
                if 'imx296' in output.lower():
                    print_status("Global Shutter Camera (IMX296) detected through v4l2-ctl", "success")
                    print("\nDevice listing:")
                    print(output)
                    gs_detected = True
            except (subprocess.CalledProcessError, FileNotFoundError):
                pass
        
        # Method 3: Try libcamera-hello for detection
        if not gs_detected:
            try:
                output = subprocess.check_output(['libcamera-hello', '--list-cameras'], text=True)
                if 'imx296' in output.lower():
                    print_status("Global Shutter Camera detected through libcamera-hello", "success")
                    print("\nCamera listing:")
                    print(output)
                    gs_detected = True
            except (subprocess.CalledProcessError, FileNotFoundError):
                pass
        
        if not gs_detected:
            print_status("No Global Shutter Camera (IMX296) detected", "warning")
    except Exception as e:
        print_status(f"Error checking for Global Shutter Camera: {e}", False)
        traceback.print_exc()

def check_bookworm_os():
    """Check if running on Bookworm OS."""
    print_status("\n=== OS Version Check ===", True)
    
    try:
        # Check if it's a Bookworm OS
        if os.path.exists('/etc/os-release'):
            with open('/etc/os-release', 'r') as f:
                os_release = f.read()
                if '=bookworm' in os_release:
                    print_status("Detected Bookworm OS - need --no-raw workaround for Global Shutter Camera", "warning")
                    return True
        
        print_status("Not running Bookworm OS, no special workaround needed", "success")
        return False
    except Exception as e:
        print_status(f"Error checking OS version: {e}", False)
        return False

def test_camera_capture():
    """Test camera capture if possible."""
    print_status("\n=== Camera Capture Test ===", True)
    
    try:
        import picamera2
        from picamera2 import Picamera2
        
        print_status("Initializing camera for test...", True)
        camera = Picamera2()
        camera.start()
        
        print_status("Capturing test frame...", True)
        time.sleep(2)  # Give camera time to initialize
        frame = camera.capture_array()
        
        if frame is not None:
            print_status(f"Successfully captured frame with shape {frame.shape}", "success")
        else:
            print_status("Frame capture returned None", False)
        
        camera.stop()
        print_status("Camera test completed", "success")
    except ImportError:
        print_status("Cannot test camera capture - picamera2 not available", "warning")
    except Exception as e:
        print_status(f"Error testing camera capture: {e}", False)
        traceback.print_exc()

def check_recordings_dir():
    """Check recordings directory structure."""
    print_status("\n=== Recordings Directory Check ===", True)
    
    # Get script location to determine project root
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(script_dir)
        recordings_dir = os.path.join(project_root, 'recordings')
        
        if os.path.exists(recordings_dir):
            print_status(f"Found recordings directory: {recordings_dir}", "success")
            
            # Check for date-based folders
            date_dirs = [d for d in os.listdir(recordings_dir) 
                         if os.path.isdir(os.path.join(recordings_dir, d)) and 
                         len(d) == 10 and d[4] == '-' and d[7] == '-']
            
            if date_dirs:
                print_status(f"Found {len(date_dirs)} date-based recording folders:", "success")
                for date_dir in sorted(date_dirs, reverse=True)[:5]:  # Show most recent 5
                    dir_path = os.path.join(recordings_dir, date_dir)
                    videos = [f for f in os.listdir(dir_path) if f.endswith(('.mkv', '.mp4'))]
                    print(f"  {date_dir}: {len(videos)} videos")
            else:
                print_status("No date-based recording folders found", "warning")
                print_status(f"To create one: mkdir -p {os.path.join(recordings_dir, time.strftime('%Y-%m-%d'))}", True)
        else:
            print_status(f"Recordings directory not found: {recordings_dir}", "warning")
            print_status(f"To create: mkdir -p {recordings_dir}", True)
    except Exception as e:
        print_status(f"Error checking recordings directory: {e}", False)

def main():
    """Main function to run all checks."""
    print("\n" + "=" * 80)
    print("RASPBERRY PI CAMERA ENVIRONMENT CHECK".center(80))
    print("=" * 80)
    
    # Display information about the current file structure
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(script_dir)
        print(f"Project root: {project_root}")
        print(f"Scripts directory: {os.path.join(project_root, 'scripts')}")
        print(f"Bin directory: {script_dir}")
    except Exception as e:
        print(f"Error determining file structure: {e}")
    
    print("\nRunning environment checks...\n")
    
    # Run all checks
    check_system_info()
    check_camera_modules()
    check_camera_devices()
    check_global_shutter_camera()
    check_bookworm_os()
    check_recordings_dir()
    
    # Only run camera test if on Raspberry Pi
    try:
        if os.path.exists('/proc/cpuinfo'):
            with open('/proc/cpuinfo', 'r') as f:
                if 'Raspberry Pi' in f.read() or 'BCM' in f.read():
                    test_camera_capture()
    except Exception:
        pass
    
    print("\n" + "=" * 80)
    print("ENVIRONMENT CHECK COMPLETE".center(80))
    print("=" * 80)
    
    # Print final summary
    print("\nNext steps:")
    print("1. Make sure camera is properly connected")
    print("2. Run camera with: ./scripts/run-camera.sh")
    print("3. Manage camera service with: ./scripts/camera-service.sh")
    print("\nFor Global Shutter Camera high frame rate support, run camera script")
    print("and follow the interactive prompts to select optimal configuration.")
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 