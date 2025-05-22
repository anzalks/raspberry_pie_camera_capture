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
        for dev in sorted(video_devices):
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
        for dev in sorted(media_devices):
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
        print_status("No media devices found. This is usually fine unless using specific UVC features or Global Shutter advanced config.", "warning")

def check_global_shutter_camera():
    """Check for Global Shutter Camera using v4l2-ctl."""
    print_status("\n=== Global Shutter Camera Detection ===", True)
    
    try:
        subprocess.check_output(['which', 'v4l2-ctl'])
        print_status("v4l2-ctl is installed", "success")
    except subprocess.CalledProcessError:
        print_status("v4l2-ctl is not installed", False)
        print_status("Install with: sudo apt install -y v4l-utils", "warning")
        return
    
    gs_detected = False
    try:
        output = subprocess.check_output(['v4l2-ctl', '--list-devices'], text=True, stderr=subprocess.PIPE)
        if 'imx296' in output.lower():
            print_status("Global Shutter Camera (IMX296) detected through v4l2-ctl", "success")
            print("\nDevice listing:")
            print(output)
            gs_detected = True
        
        # Additional check for rp1-cfe media device details if GS is found
        if gs_detected:
            media_devices = glob.glob('/dev/media*')
            for m_dev in media_devices:
                try:
                    # On Bookworm media-ctl functionality moved to v4l2-ctl
                    # Try v4l2-ctl first, fallback to media-ctl if available
                    try:
                        media_output = subprocess.check_output(['v4l2-ctl', '--device', m_dev, '--info'],
                                                           text=True, stderr=subprocess.PIPE)
                    except (subprocess.CalledProcessError, FileNotFoundError):
                        # Fallback to media-ctl for older systems
                        try:
                            media_output = subprocess.check_output(['media-ctl', '-d', m_dev, '-p'],
                                                               text=True, stderr=subprocess.PIPE)
                        except (subprocess.CalledProcessError, FileNotFoundError):
                            continue  # Skip to next device if both commands fail
                            
                    if 'imx296' in media_output.lower():
                        print(f"\nSensor details from {m_dev}:")
                        print(media_output)
                        break # Show details for the first GS camera found
                except (subprocess.CalledProcessError, FileNotFoundError):
                    pass # Command might not be installed or device not found
                    
        if not gs_detected:
            # Fallback: Try libcamera-hello for detection if v4l2-ctl fails
            try:
                output = subprocess.check_output(['libcamera-hello', '--list-cameras'], text=True, stderr=subprocess.PIPE)
                if 'imx296' in output.lower():
                    print_status("Global Shutter Camera detected through libcamera-hello", "success")
                    print("\nCamera listing:")
                    print(output)
                    gs_detected = True
            except (subprocess.CalledProcessError, FileNotFoundError):
                pass # libcamera-hello might not be installed

        if not gs_detected:
            print_status("No Global Shutter Camera (IMX296) detected", "warning")
            
    except Exception as e:
        print_status(f"Error checking for Global Shutter Camera: {e}", False)
        traceback.print_exc()

def check_bookworm_os():
    """Check if running on Bookworm OS and v4l-utils status."""
    print_status("\n=== OS Version Check ===", True)
    is_bookworm = False
    try:
        if os.path.exists('/etc/os-release'):
            with open('/etc/os-release', 'r') as f:
                os_release = f.read()
                if '=bookworm' in os_release:
                    print_status("Detected Raspberry Pi OS Bookworm", "warning")
                    is_bookworm = True
        
        if not is_bookworm:
            print_status("Not running Bookworm OS or OS could not be determined.", True)

        # Check v4l2-ctl status regardless of OS, as it's our primary tool
        try:
            v4l2_ctl_version = subprocess.check_output(['v4l2-ctl', '--version'], text=True, stderr=subprocess.PIPE).strip()
            print_status(f"v4l2-ctl is available: {v4l2_ctl_version}", "success")

            # Check if v4l2-ctl can list devices
            try:
                subprocess.check_output(['v4l2-ctl', '--list-devices'], stderr=subprocess.PIPE)
                print_status("v4l2-ctl can list devices.", "success")
            except subprocess.CalledProcessError as e:
                print_status(f"v4l2-ctl --list-devices failed: {e.stderr.strip() if e.stderr else e}", "warning")

        except (subprocess.CalledProcessError, FileNotFoundError):
            print_status("v4l2-ctl is not installed or not working properly.", False)
            print_status("Install/reinstall v4l-utils: sudo apt install -y v4l-utils", "warning")

        if is_bookworm:
             print_status("NOTE: On Bookworm OS, ensure v4l-utils is up to date for full camera support.", "warning")
             print_status("Example: libcamera-hello --no-raw --list-cameras (if using libcamera directly)", "warning")
             
        return is_bookworm
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
        
        # Attempt to list cameras first to ensure libcamera stack is responsive
        try:
            cameras = Picamera2.global_camera_info()
            if not cameras:
                print_status("No cameras found by Picamera2.global_camera_info(). Ensure camera is enabled in raspi-config and libcamera is working.", False)
                return
            print_status(f"Available cameras: {cameras}", True)
        except Exception as e:
            print_status(f"Error listing cameras with Picamera2: {e}", False)
            print_status("This might indicate an issue with the libcamera stack.", "warning")
            return

        cam = Picamera2()
        
        # Create a default configuration, explicitly disabling raw stream for this test
        config = cam.create_preview_configuration(raw=None)
        cam.configure(config)
        
        print_status(f"Configured for preview: {config}", True)
        
        cam.start()
        print_status("Camera started for test.", True)
        time.sleep(1)  # Give camera time to initialize
        
        frame = cam.capture_array()
        if frame is not None:
            print_status(f"Successfully captured test frame with shape {frame.shape}", "success")
        else:
            print_status("Frame capture returned None", False)
        
        cam.stop()
        print_status("Camera test completed and stopped.", "success")
    except ImportError:
        print_status("Cannot test camera capture - picamera2 not available", "warning")
    except Exception as e:
        print_status(f"Error testing camera capture: {e}", False)
        traceback.print_exc()

def check_recordings_dir():
    """Check if the recordings directory exists."""
    print_status("\n=== Recordings Directory Check ===", True)
    # Try to determine project root to find recordings relative to it
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir) # Assumes script is in a 'scripts' or 'bin' subdirectory
    
    # If a common structure is raspberry_pie_camera_capture/scripts, go one more up
    if os.path.basename(project_root) == "raspberry_pie_camera_capture" and os.path.basename(script_dir) in ["scripts", "bin"]:
         project_root = os.path.dirname(project_root)

    # Fallback to current working directory if structure is unusual
    if not os.path.exists(os.path.join(project_root, "config.yaml")): # A common file to indicate root
        project_root = os.getcwd()

    recordings_dir = os.path.join(project_root, "recordings")
    
    if os.path.exists(recordings_dir) and os.path.isdir(recordings_dir):
        print_status(f"Recordings directory found: {recordings_dir}", "success")
    else:
        print_status(f"Recordings directory not found: {recordings_dir}", "warning")
        print_status(f"To create: mkdir -p {recordings_dir}", True)

def main():
    """Main function to run all checks."""
    print("\n" + "=" * 80)
    print("RASPBERRY PI CAMERA ENVIRONMENT CHECK".center(80))
    print("=" * 80)
    
    # Determine project root and scripts/bin directory
    script_path = os.path.abspath(__file__)
    bin_dir = os.path.dirname(script_path)
    scripts_dir = os.path.dirname(bin_dir) # Assumes bin is inside scripts, or scripts is project root
    project_root = os.path.dirname(scripts_dir) if os.path.basename(scripts_dir) == "scripts" else scripts_dir

    # A more robust way to find project root (where .git or a known file like run-camera.sh might be)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    max_levels = 3 # Search up to 3 levels for a .git folder or specific file
    found_root = False
    for _ in range(max_levels):
        if os.path.exists(os.path.join(current_dir, ".git")) or \
           os.path.exists(os.path.join(current_dir, "run-camera.sh")) or \
           os.path.exists(os.path.join(current_dir, "config.yaml")):
            project_root = current_dir
            found_root = True
            break
        parent_dir = os.path.dirname(current_dir)
        if parent_dir == current_dir: # Reached filesystem root
            break
        current_dir = parent_dir
    
    if not found_root:
        project_root = os.getcwd() # Fallback
        print_status(f"Could not reliably determine project root, using CWD: {project_root}", "warning")

    scripts_dir_path = os.path.join(project_root, "scripts")
    bin_dir_path = os.path.join(project_root, "bin")

    print(f"Project root: {project_root}")
    print(f"Scripts directory: {scripts_dir_path if os.path.exists(scripts_dir_path) else 'Not found'}")
    print(f"Bin directory: {bin_dir_path if os.path.exists(bin_dir_path) else 'Not found'}")

    print("\nRunning environment checks...\n")
    
    # Run all checks
    check_system_info()
    check_camera_modules()
    check_camera_devices()
    check_global_shutter_camera()
    is_bookworm = check_bookworm_os()
    check_recordings_dir()
    test_camera_capture()

    print("\n" + "=" * 80)
    print("ENVIRONMENT CHECK COMPLETE".center(80))
    print("=" * 80)
    
    # Print final summary
    print("\nNext steps:")
    print("1. Make sure camera is properly connected")
    print(f"2. Run camera with: {os.path.join(scripts_dir_path, 'run-camera.sh') if os.path.exists(scripts_dir_path) else './run-camera.sh'}")
    print(f"3. Manage camera service with: {os.path.join(scripts_dir_path, 'camera-service.sh') if os.path.exists(scripts_dir_path) else './camera-service.sh'}")

    if is_bookworm:
        print_status("\nFor Global Shutter Camera high frame rate support, run camera script", "warning")
        print_status("and follow the interactive prompts to select optimal configuration.", "warning")

    return 0

if __name__ == "__main__":
    sys.exit(main()) 