#!/usr/bin/env python3
"""
Environment checker for Raspberry Pi camera system.

This script verifies the system environment to ensure all requirements
are met for the camera capture system to function properly.

Author: Anzal
Email: anzal.ks@gmail.com
GitHub: https://github.com/anzalks/
"""

import sys
import os
import platform
import shutil
import subprocess
import importlib
import tempfile
import time
from pathlib import Path
import argparse
import pkg_resources
import importlib.util
import glob
import datetime
import ctypes

def print_header(text):
    """Print a formatted header."""
    print("\n" + "=" * 60)
    print(f" {text}")
    print("=" * 60)

def print_status(name, status, details=None):
    """Print a status line with colored output."""
    if status:
        status_text = "\033[92m✓ PASS\033[0m"  # Green
    else:
        status_text = "\033[91m✗ FAIL\033[0m"  # Red
        
    print(f"{name:30} {status_text:10}", end="")
    if details:
        print(f" {details}")
    else:
        print()

def check_python_version():
    """Check if Python version is sufficient."""
    required_version = (3, 7)
    current_version = sys.version_info
    version_str = '.'.join(map(str, current_version[:3]))
    
    result = current_version >= required_version
    print_status("Python Version", result, f"v{version_str} (Required: {required_version[0]}.{required_version[1]}+)")
    return result

def check_import(module_name, package_name=None):
    """Try to import a module and return whether it was successful."""
    if package_name is None:
        package_name = module_name
        
    try:
        module = importlib.import_module(module_name)
        version = getattr(module, '__version__', 'unknown')
        print_status(f"Module: {module_name}", True, f"v{version}")
        return True
    except ImportError:
        print_status(f"Module: {module_name}", False, f"Not found. Install with: pip install {package_name}")
        return False

def check_system_packages():
    """Check for required system packages."""
    system = platform.system().lower()
    
    # System-specific package checks
    if system == 'linux':
        packages = {
            "v4l-utils": "video4linux utilities",
            "curl": "HTTP client",
            "libcamera-apps": "Camera interface library",
        }
        
        # Raspberry Pi specific check
        is_raspberry_pi = os.path.exists('/proc/device-tree/model') and 'raspberry pi' in open('/proc/device-tree/model').read().lower()
        if is_raspberry_pi:
            print_status("Raspberry Pi Detected", True, "Hardware platform supported")
        else:
            print_status("Raspberry Pi Detected", False, "Not running on a Raspberry Pi")
        
        # Check for packages
        for package, description in packages.items():
            is_installed = shutil.which(package) is not None or subprocess.call(['which', package], stdout=subprocess.PIPE, stderr=subprocess.PIPE) == 0
            print_status(f"System Package: {package}", is_installed, description)
    
    elif system == 'darwin':
        print_status("macOS Detected", True, "Development platform (Note: Camera functionality limited)")
        
        # Check for Homebrew as it's common on macOS
        is_brew_installed = shutil.which('brew') is not None
        print_status("Homebrew", is_brew_installed, "Package manager")
        
    elif system == 'windows':
        print_status("Windows Detected", True, "Development platform (Note: Camera functionality limited)")
        
        # Check for opencv binaries
        opencv_installed = check_import('cv2', 'opencv-python')
        if not opencv_installed:
            print_status("OpenCV on Windows", False, "Additional configuration may be needed")

def check_camera_devices():
    """Check for available camera devices."""
    system = platform.system().lower()
    
    if system == 'linux':
        # Check for video devices using v4l2
        try:
            video_devices = list(Path('/dev').glob('video*'))
            if video_devices:
                print_status("Camera Devices", True, f"Found {len(video_devices)} video device(s) ({', '.join(str(d) for d in video_devices)})")
                
                # Try to get more info about the first device
                try:
                    cmd = ['v4l2-ctl', '--device', str(video_devices[0]), '--all']
                    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    if result.returncode == 0:
                        lines = result.stdout.strip().split('\n')
                        for line in lines[:10]:  # Just show the first few lines
                            if 'driver' in line.lower() or 'card type' in line.lower() or 'bus info' in line.lower():
                                print(f"  {line.strip()}")
                except Exception as e:
                    print(f"  Could not get camera details: {e}")
            else:
                print_status("Camera Devices", False, "No video devices found in /dev")
        except Exception as e:
            print_status("Camera Devices", False, f"Error checking for devices: {e}")
    
    elif system == 'darwin':
        # On macOS, we can't easily list devices without permissions
        print_status("Camera Devices", None, "Cannot enumerate on macOS without permissions")
        
    elif system == 'windows':
        # On Windows, try to list DirectShow devices with OpenCV
        try:
            import cv2
            idx = 0
            cameras = []
            while True:
                cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
                if not cap.isOpened():
                    break
                cameras.append(idx)
                cap.release()
                idx += 1
                
            if cameras:
                print_status("Camera Devices", True, f"Found {len(cameras)} camera device(s)")
            else:
                print_status("Camera Devices", False, "No camera devices found")
        except Exception as e:
            print_status("Camera Devices", False, f"Error checking for devices: {e}")

def check_network_connectivity():
    """Check connectivity to ntfy.sh service."""
    try:
        import requests
        timeout = 5
        try:
            response = requests.get("https://ntfy.sh/healthz", timeout=timeout)
            if response.status_code == 200:
                print_status("ntfy.sh Service", True, "Service reachable (status: 200)")
                return True
            else:
                print_status("ntfy.sh Service", False, f"Service returned status code: {response.status_code}")
                return False
        except requests.exceptions.RequestException as e:
            print_status("ntfy.sh Service", False, f"Connection error: {e}")
            return False
    except ImportError:
        print_status("Requests module", False, "Not installed. Cannot check network connectivity.")
        return False

def check_opencv_support():
    """Check OpenCV installation and available codecs."""
    try:
        import cv2
        
        # Get OpenCV version
        version = cv2.__version__
        print_status("OpenCV", True, f"Version {version}")
        
        # Check available codecs
        codecs = [
            ('h264', 'H264'),
            ('h265', 'H265'),
            ('mjpg', 'MJPG'),
            ('avc1', 'AVC1'),
            ('mp4v', 'MP4V')
        ]
        
        supported_codecs = []
        for codec_id, codec_name in codecs:
            try:
                # Create a temporary file to test writing with this codec
                with tempfile.NamedTemporaryFile(suffix=f'.{codec_id}.mp4', delete=True) as temp:
                    # Try to create a video writer with this codec
                    fourcc = cv2.VideoWriter_fourcc(*codec_name)
                    writer = cv2.VideoWriter(temp.name, fourcc, 30, (640, 480))
                    if writer.isOpened():
                        supported_codecs.append(codec_id)
                        writer.release()
            except Exception:
                # If it fails, codec is not supported
                pass
        
        if supported_codecs:
            print_status("Video Codecs", True, f"Supported: {', '.join(supported_codecs)}")
        else:
            print_status("Video Codecs", False, "No supported codecs found")
    
    except ImportError:
        print_status("OpenCV", False, "Not installed")

def check_lsl_support():
    """Check Lab Streaming Layer (LSL) support."""
    try:
        import pylsl
        
        # Get pylsl version
        version = pylsl.__version__
        print_status("pylsl", True, f"Version {version}")
        
        # Try to create a test LSL stream
        try:
            from pylsl import StreamInfo, StreamOutlet
            info = StreamInfo(name='TestStream', type='Markers', channel_count=1, 
                              nominal_srate=100, channel_format='int32', source_id='test')
            outlet = StreamOutlet(info)
            
            # Wait a moment and check if we can resolve our own stream
            time.sleep(0.1)
            streams = pylsl.resolve_streams(0.5)
            
            found = any(s.name() == 'TestStream' for s in streams)
            if found:
                print_status("LSL Stream Creation", True, "Successfully created and resolved test stream")
            else:
                print_status("LSL Stream Creation", False, "Created stream but could not resolve it")
        except Exception as e:
            print_status("LSL Stream Creation", False, f"Error: {e}")
    
    except ImportError:
        print_status("pylsl", False, "Not installed")

def check_picamera2_support():
    """Check picamera2 support for Raspberry Pi."""
    system = platform.system().lower()
    if system != 'linux':
        print_status("picamera2", None, "Not applicable on this platform")
        return
    
    try:
        import picamera2
        # Use getattr to safely get version with a fallback
        version = getattr(picamera2, '__version__', 'unknown')
        print_status("picamera2", True, f"Version {version}")
        
        # Check for libcamera presence
        libcamera_present = os.path.exists('/usr/lib/libcamera.so') or os.path.exists('/usr/lib/arm-linux-gnueabihf/libcamera.so')
        print_status("libcamera", libcamera_present, "Required library for picamera2")
        
    except ImportError:
        print_status("picamera2", False, "Not installed")

def check_permissions():
    """Check for necessary permissions."""
    system = platform.system().lower()
    
    if system == 'linux':
        # Check video group membership
        try:
            user = os.environ.get('USER', 'unknown')
            groups_output = subprocess.check_output(['groups', user], text=True)
            
            if 'video' in groups_output:
                print_status("Video Group Membership", True, f"User '{user}' is in the video group")
            else:
                print_status("Video Group Membership", False, f"User '{user}' is not in the video group. Run: sudo usermod -a -G video {user}")
        except Exception as e:
            print_status("Group Check", False, f"Error checking groups: {e}")
            
        # Check camera device permissions
        video_devices = list(Path('/dev').glob('video*'))
        if video_devices:
            try:
                perms = os.stat(video_devices[0]).st_mode & 0o777
                readable = perms & 0o004 > 0
                print_status("Camera Device Permissions", readable, f"{video_devices[0]} has permissions: {perms:o}")
            except Exception as e:
                print_status("Camera Device Permissions", False, f"Error checking permissions: {e}")

def check_storage():
    """Check for sufficient storage space."""
    try:
        path = '.'  # Current directory
        
        # Get disk usage statistics
        total, used, free = shutil.disk_usage(path)
        
        # Convert to GB
        total_gb = total / (1024 ** 3)
        free_gb = free / (1024 ** 3)
        used_percent = (used / total) * 100
        
        # Check if there's enough free space (2GB minimum)
        enough_space = free_gb >= 2
        
        print_status("Storage Space", enough_space, 
                    f"Total: {total_gb:.1f}GB, Free: {free_gb:.1f}GB ({100-used_percent:.1f}% free)")
        
        # Calculate video storage requirements
        width, height = 400, 400  # Default resolution
        fps = 100  # Default fps
        duration_minutes = 60  # 1 hour of recording
        
        # Calculate with MJPG (very rough estimate - depends on compression)
        mjpg_bitrate = width * height * fps * 0.1 / 8  # bits per second
        mjpg_size_gb = mjpg_bitrate * 60 * duration_minutes / (8 * 1024 ** 3)
        
        print(f"  Estimated storage for 1 hour of {width}x{height}@{fps}fps video: ~{mjpg_size_gb:.1f}GB")
        print(f"  Available recording time: ~{free_gb/mjpg_size_gb:.1f} hours")
        
    except Exception as e:
        print_status("Storage Space", False, f"Error checking storage: {e}")

def check_platform():
    """Check the platform we're running on."""
    system = platform.system()
    if system == "Linux":
        # Check if we're on a Raspberry Pi
        is_rpi = False
        try:
            with open("/proc/cpuinfo", "r") as f:
                cpuinfo = f.read()
                if "Raspberry Pi" in cpuinfo or "BCM" in cpuinfo:
                    is_rpi = True
                    # Extract Pi version
                    model_line = next((line for line in cpuinfo.split('\n') if "Model" in line), "")
                    if model_line:
                        print_status("Platform", True, f"Raspberry Pi ({model_line.split(':')[1].strip()})")
                    else:
                        print_status("Platform", True, "Raspberry Pi")
                    return True
                else:
                    print_status("Platform", False, "Linux but not a Raspberry Pi")
        except Exception as e:
            print_status("Platform", False, f"Error checking Raspberry Pi: {e}")
    else:
        print_status("Platform", False, f"{system} is not supported")
    
    return False

def check_camera_modules():
    """Check which camera modules are installed."""
    try:
        # Try to import picamera2
        import picamera2
        # Use getattr to safely get version with a fallback
        version = getattr(picamera2, '__version__', 'unknown')
        print_status("picamera2", True, f"Version {version}")
    except ImportError:
        print_status("picamera2", False, "Not installed")
        print("Please install picamera2 with: sudo apt install -y python3-picamera2")
        return False
    
    return True

def check_standard_camera():
    """Check for a standard Raspberry Pi camera."""
    try:
        # Use vcgencmd to check for camera
        result = subprocess.run(
            ["vcgencmd", "get_camera"],
            capture_output=True,
            text=True,
            check=False
        )
        
        if "detected=1" in result.stdout:
            print_status("Camera", True, "Detected")
            return True
        else:
            print_status("Camera", False, "Not detected")
            return False
    except Exception as e:
        print_status("Camera", False, f"Error checking camera: {e}")
        return False

def check_global_shutter_camera():
    """Check specifically for a Global Shutter Camera."""
    try:
        # First check if any camera is detected
        camera_result = subprocess.run(
            ["vcgencmd", "get_camera"],
            capture_output=True,
            text=True,
            check=False
        )
        
        if "detected=1" not in camera_result.stdout:
            print_status("Global Shutter Camera", False, "No camera detected")
            return False
            
        # Check for IMX296 sensor which is used in Global Shutter Camera
        gs_detected = False
        for m in range(6):  # Try media devices 0-5
            try:
                cmd = ["media-ctl", "-d", f"/dev/media{m}", "-p"]
                media_result = subprocess.run(cmd, capture_output=True, text=True, check=False)
                if "imx296" in media_result.stdout.lower():
                    print_status("Global Shutter Camera", True, f"Detected on /dev/media{m}")
                    gs_detected = True
                    # Display additional info about the device
                    try:
                        # Get supported formats
                        formats_cmd = ["v4l2-ctl", "--list-formats-ext", "-d", f"/dev/video{m*2}"]
                        formats_result = subprocess.run(formats_cmd, capture_output=True, text=True, check=False)
                        print("\nSupported formats:")
                        print(formats_result.stdout)
                        
                        # Show current crop settings
                        crop_cmd = ["media-ctl", "-d", f"/dev/media{m}", "--get-v4l2", "'imx296 10-001a':0"]
                        crop_result = subprocess.run(" ".join(crop_cmd), shell=True, capture_output=True, text=True, check=False)
                        print("\nCurrent settings:")
                        print(crop_result.stdout)
                        
                    except Exception as e:
                        print(f"Error getting device details: {e}")
                    
                    # Show high frame rate crop examples
                    print("\nExample crop configurations for high frame rates:")
                    print("  688x136 pixels @ ~400fps")
                    print("  224x96 pixels @ ~500fps")
                    print("  1456x96 pixels @ ~536fps (full width, very thin height)")
                    print("\nTo use these configurations, run camera_capture with:")
                    print("  --width 688 --height 136 --fps 400")
                    print("\nThe system will automatically detect and configure the Global Shutter Camera.")
                    
                    return True
            except Exception as e:
                continue
                
        if not gs_detected:
            print_status("Global Shutter Camera", False, "Not detected, standard Pi Camera likely connected")
            
        return gs_detected
        
    except Exception as e:
        print_status("Global Shutter Camera", False, f"Error checking Global Shutter Camera: {e}")
        return False

def check_media_ctl():
    """Check if media-ctl is installed (needed for Global Shutter Camera)."""
    try:
        result = subprocess.run(["which", "media-ctl"], capture_output=True, text=True, check=False)
        if result.returncode == 0:
            print_status("media-ctl", True, "Installed (required for Global Shutter Camera)")
            return True
        else:
            print_status("media-ctl", False, "Not installed")
            print("Please install media-ctl with: sudo apt install -y v4l-utils")
            return False
    except Exception as e:
        print_status("media-ctl", False, f"Error checking media-ctl: {e}")
        return False

def check_libcamera_tools():
    """Check if libcamera tools are installed."""
    tools = [
        "libcamera-hello",
        "libcamera-still",
        "libcamera-vid",
        "rpicam-hello",
        "rpicam-still",
        "rpicam-vid"
    ]
    
    all_installed = True
    for tool in tools:
        try:
            result = subprocess.run(["which", tool], capture_output=True, text=True, check=False)
            if result.returncode == 0:
                print_status(tool, True, "Installed")
            else:
                print_status(tool, False, "Not installed")
                all_installed = False
        except Exception as e:
            print_status(tool, False, f"Error checking: {e}")
            all_installed = False
    
    if not all_installed:
        print("Please install libcamera tools with: sudo apt install -y libcamera-apps")
    
    return all_installed

def print_global_shutter_info():
    """Print Global Shutter Camera information and recommendations."""
    print("\n📋 Global Shutter Camera Configurations:")
    print("   Based on Hermann-SW's research (https://gist.github.com/Hermann-SW/e6049fe1a24fc2b5a53c654e0e9f6b9c)")
    
    print("\n   Standard configurations:")
    print("   • 688x136 @ ~400fps")
    print("   • 224x96 @ ~500fps")
    print("   • 1456x96 @ ~536fps (full width)")
    print("   • 600x600 @ ~200fps (square)")
    
    print("\n   To use these configurations:")
    print("   python3 -m src.raspberry_pi_lsl_stream.camera_capture --width 688 --height 136 --fps 400")
    print("   The camera will auto-configure for high frame rates based on your dimensions.")
    
    print("\n   Example crop configurations for different use cases:")
    print("   1. Maximum frame rate (536fps):")
    print("      python3 -m src.raspberry_pi_lsl_stream.camera_capture --width 1456 --height 96 --fps 536")
    print("   2. Square crop for general use (200fps):")
    print("      python3 -m src.raspberry_pi_lsl_stream.camera_capture --width 600 --height 600 --fps 200")
    print("   3. Balanced size/speed (400fps):")
    print("      python3 -m src.raspberry_pi_lsl_stream.camera_capture --width 688 --height 136 --fps 400")
    print("   4. Small ROI for maximum speed (500fps):")
    print("      python3 -m src.raspberry_pi_lsl_stream.camera_capture --width 224 --height 96 --fps 500")

def check_for_global_shutter_camera():
    """Specifically check for the Global Shutter Camera."""
    print_header("Global Shutter Camera Detection")
    
    global_shutter_detected = False
    
    # Method 1: Check using v4l2-ctl
    try:
        v4l2_result = subprocess.run(["v4l2-ctl", "--list-devices"], capture_output=True, text=True)
        if v4l2_result.returncode == 0:
            if "imx296" in v4l2_result.stdout.lower():
                print("✅ Global Shutter Camera (IMX296) detected using v4l2-ctl")
                global_shutter_detected = True
    except Exception as e:
        print(f"Error checking v4l2 devices: {e}")
    
    # Method 2: Check using media-ctl
    try:
        for i in range(5):
            media_result = subprocess.run(["media-ctl", "-d", f"/dev/media{i}", "-p"], capture_output=True, text=True)
            if media_result.returncode == 0:
                if "imx296" in media_result.stdout.lower():
                    print(f"✅ Global Shutter Camera (IMX296) detected on /dev/media{i}")
                    global_shutter_detected = True
                    break
    except Exception as e:
        print(f"Error checking media devices: {e}")
    
    # Method 3: Check using libcamera
    try:
        libcamera_result = subprocess.run(["libcamera-hello", "--list-cameras"], capture_output=True, text=True)
        if libcamera_result.returncode == 0:
            if "imx296" in libcamera_result.stdout.lower() or "global" in libcamera_result.stdout.lower():
                print("✅ Global Shutter Camera detected using libcamera-hello")
                global_shutter_detected = True
    except Exception as e:
        print(f"Error checking with libcamera: {e}")
    
    if global_shutter_detected:
        print("\n✅ Global Shutter Camera has been detected on your system")
        print("   This camera is capable of high frame rates with the right configuration")
        print_global_shutter_info()
    else:
        print("\n❌ No Global Shutter Camera detected")
        print("   The system does not appear to have a Raspberry Pi Global Shutter Camera connected")
        print("   If you believe this is an error, ensure your camera is properly connected and enabled")
    
    return global_shutter_detected

def check_status_file_support():
    """Check if the status file capability is available."""
    try:
        import os
        from src.raspberry_pi_lsl_stream.status_file import StatusFileWriter
        
        # Verify the status file module imported correctly
        print_status("Status File Support", True, "Available for terminal fallback display")
        
        # Check if we can write to the temp status file location
        temp_status_file = "/tmp/raspie_camera_status"
        try:
            with open(temp_status_file, 'w') as f:
                f.write("Test status\n")
            os.remove(temp_status_file)
            print_status("Status File Write", True, f"Can write to {temp_status_file}")
        except Exception as e:
            print_status("Status File Write", False, f"Cannot write to {temp_status_file}: {e}")
    
    except ImportError:
        print_status("Status File Support", False, "Module not found")

def red(text):
    return f"\033[91m{text}\033[0m"

def green(text):
    return f"\033[92m{text}\033[0m"

def yellow(text):
    return f"\033[93m{text}\033[0m"

def info(label, status, message=""):
    """Print an info line with colored status."""
    if status in (True, "PASS"):
        status_str = green("✓ PASS")
    elif status in (False, "FAIL"):
        status_str = red("✗ FAIL")
    else:
        status_str = yellow("! WARN")
        
    print(f"{label.ljust(30)} {status_str} {message}")

def check_module_available(module_name):
    """Check if a Python module is available."""
    try:
        spec = importlib.util.find_spec(module_name)
        return spec is not None
    except (ImportError, AttributeError):
        return False
    
def get_module_version(module_name):
    """Get the version of an installed module."""
    try:
        module = importlib.import_module(module_name)
        if hasattr(module, "__version__"):
            return module.__version__
        elif hasattr(module, "version"):
            return module.version
        else:
            return "unknown"
    except (ImportError, AttributeError):
        return None

def check_command_available(command):
    """Check if a command is available in the PATH."""
    return shutil.which(command) is not None

def run_command(command, shell=False):
    """Run a command and return its output."""
    try:
        if isinstance(command, str) and not shell:
            command = command.split()
        result = subprocess.run(command, capture_output=True, text=True, shell=shell)
        return result.stdout.strip()
    except (subprocess.SubprocessError, FileNotFoundError):
        return ""

def get_opencv_info():
    """Get information about OpenCV."""
    try:
        import cv2
        version = cv2.__version__
        # Test creating a video writer to check codec support
        codecs = []
        test_output = "/tmp/test_opencv_codec.mp4"
        
        # Test MJPG
        try:
            writer = cv2.VideoWriter(
                test_output, 
                cv2.VideoWriter_fourcc(*'MJPG'), 
                30, 
                (640, 480)
            )
            if writer.isOpened():
                codecs.append("mjpg")
            writer.release()
        except Exception as e:
            print(f"OpenCV: {e}")
        
        # Test H264
        try:
            writer = cv2.VideoWriter(
                test_output, 
                cv2.VideoWriter_fourcc(*'H264'), 
                30, 
                (640, 480)
            )
            if writer.isOpened():
                codecs.append("h264")
            writer.release()
        except Exception as e:
            print(f"OpenCV: {e}")
            
        # Test MP4V
        try:
            writer = cv2.VideoWriter(
                test_output, 
                cv2.VideoWriter_fourcc(*'MP4V'), 
                30, 
                (640, 480)
            )
            if writer.isOpened():
                codecs.append("mp4v")
            writer.release()
        except Exception as e:
            print(f"OpenCV: {e}")
            
        if os.path.exists(test_output):
            try:
                os.remove(test_output)
            except:
                pass
                
        return version, codecs
    except ImportError:
        return None, []

def is_raspberry_pi():
    """Check if running on Raspberry Pi."""
    try:
        with open('/proc/device-tree/model', 'r') as f:
            model = f.read()
        return 'raspberry pi' in model.lower()
    except:
        return False

def get_raspberry_pi_model():
    """Get Raspberry Pi model."""
    try:
        with open('/proc/device-tree/model', 'r') as f:
            return f.read().strip('\0')
    except:
        return None

def check_camera_detected():
    """Check if camera is detected."""
    # Try using vcgencmd
    camera_detected = False
    camera_info = ""
    
    try:
        result = run_command("vcgencmd get_camera")
        if "detected=1" in result:
            camera_detected = True
            camera_info = result
    except:
        pass
        
    # Try using v4l2-ctl
    if not camera_detected:
        try:
            result = run_command("v4l2-ctl --list-devices")
            if result and "video" in result.lower():
                camera_detected = True
                camera_info = result
        except:
            pass
            
    # Check video devices
    video_devices = glob.glob("/dev/video*")
    if video_devices and not camera_detected:
        try:
            for device in video_devices:
                result = run_command(f"v4l2-ctl --device={device} --all")
                if "Video Capture" in result:
                    camera_detected = True
                    camera_info = f"Found capture device at {device}"
                    break
        except:
            pass
            
    return camera_detected, camera_info, video_devices

def check_global_shutter_camera():
    """Check if Global Shutter Camera is detected."""
    # Try using media-ctl to detect IMX296 sensor
    try:
        for m in range(6):  # Try media devices 0-5
            result = run_command(f"media-ctl -d /dev/media{m} -p")
            if "imx296" in result.lower():
                return True, f"Found IMX296 sensor on /dev/media{m}"
    except:
        pass
        
    # Try using v4l2-ctl to check for IMX296
    try:
        result = run_command("v4l2-ctl --list-devices")
        if "imx296" in result.lower():
            return True, "Found IMX296 sensor in device list"
    except:
        pass
        
    return False, "No Global Shutter Camera (IMX296) detected"

def check_video_permissions():
    """Check permissions on video devices."""
    devices = glob.glob("/dev/video*")
    if not devices:
        return False, "No video devices found"
        
    all_correct = True
    device_info = []
    
    for device in devices[:5]:  # Check first 5 devices
        try:
            stats = os.stat(device)
            mode = stats.st_mode & 0o777  # Get permission bits
            mode_str = oct(mode)[-3:]     # Convert to octal string
            if mode != 0o666:
                all_correct = False
                device_info.append(f"{device} has permissions: {mode_str}")
        except:
            all_correct = False
            device_info.append(f"{device} could not check permissions")
            
    return all_correct, ", ".join(device_info) if not all_correct else f"All devices have correct permissions (666)"

def check_user_in_groups():
    """Check if current user is in necessary groups."""
    username = os.environ.get('USER') or os.environ.get('LOGNAME')
    if not username:
        return False, "Could not determine current user"
        
    try:
        result = run_command(f"groups {username}")
        groups = result.split()
        in_video = "video" in groups
        in_input = "input" in groups
        
        if in_video and in_input:
            return True, f"User '{username}' is in video and input groups"
        elif in_video:
            return True, f"User '{username}' is in the video group"
        else:
            return False, f"User '{username}' is not in the video group. Run: sudo usermod -a -G video {username}"
    except:
        return False, "Could not check group membership"

def check_disk_space(path="/"):
    """Check available disk space."""
    try:
        stats = os.statvfs(path)
        total = stats.f_blocks * stats.f_frsize
        free = stats.f_bavail * stats.f_frsize
        free_gb = free / (1024**3)
        total_gb = total / (1024**3)
        percent_free = (free / total) * 100
        
        # Calculate storage requirements based on camera resolution
        # Assume 400x400@100fps with MJPG codec
        fps = 100
        width = 400
        height = 400
        bpp = 8  # bits per pixel for MJPG (approximation)
        hours = 1
        
        # Calculate bytes per frame
        bytes_per_frame = (width * height * bpp) / 8
        
        # Calculate bytes per hour
        bytes_per_hour = bytes_per_frame * fps * 3600
        
        # Convert to GB
        gb_per_hour = bytes_per_hour / (1024**3)
        
        # Calculate available recording time
        available_hours = free_gb / gb_per_hour if gb_per_hour > 0 else 0
        
        status = "PASS" if free_gb > 1 else "FAIL"
        return status, f"Total: {total_gb:.1f}GB, Free: {free_gb:.1f}GB ({percent_free:.1f}% free)\n  Estimated storage for 1 hour of {width}x{height}@{fps}fps video: ~{gb_per_hour:.1f}GB\n  Available recording time: ~{available_hours:.1f} hours"
    except:
        return "FAIL", "Could not check disk space"

def check_ntfy_service():
    """Check if ntfy.sh service is reachable."""
    try:
        import requests
        response = requests.get("https://ntfy.sh", timeout=5)
        return response.status_code == 200, f"Service reachable (status: {response.status_code})"
    except:
        return False, "Could not connect to ntfy.sh"

def check_status_file_support():
    """Check if status file can be created."""
    try:
        path = "/tmp/raspie_camera_status"
        with open(path, "w") as f:
            f.write("test")
        os.remove(path)
        return True, "Available for terminal fallback display"
    except:
        return False, "Cannot create status file in /tmp"

def suggest_fixes(failed_checks):
    """Suggest fixes for failed checks."""
    if not failed_checks:
        return []
        
    fixes = []
    
    if "Camera Devices" in failed_checks:
        fixes.append("sudo apt update && sudo apt install -y v4l-utils libcamera-apps")
        
    if "Camera Device Permissions" in failed_checks:
        fixes.append("sudo chmod 666 /dev/video*")
        
    if "Video Group Membership" in failed_checks:
        user = os.environ.get('USER') or os.environ.get('LOGNAME') or "pi"
        fixes.append(f"sudo usermod -a -G video {user}")
        fixes.append(f"sudo usermod -a -G input {user}")
        fixes.append("Log out and log back in for group changes to take effect")
        
    if "Camera" in failed_checks:
        fixes.append("sudo raspi-config  # Enable camera in Interface Options")
        fixes.append("sudo modprobe bcm2835-v4l2  # Load camera module")
        fixes.append("sudo reboot  # Reboot to apply changes")
        
    if "Global Shutter Camera" in failed_checks and "Camera" not in failed_checks:
        fixes.append("sudo apt install -y libcamera-tools media-ctl")
        
    if "picamera2" in failed_checks:
        fixes.append("sudo apt install -y python3-picamera2")
        
    return fixes

def main():
    """Main function."""
    print("=" * 60)
    print(" Raspberry Pi Camera System - Environment Check")
    print("=" * 60)
    
    # Track failed checks
    failed_checks = []
    
    # Check Python version
    python_version = platform.python_version()
    python_version_check = tuple(map(int, python_version.split('.'))) >= (3, 7)
    info("Python Version", python_version_check, f"v{python_version} (Required: 3.7+)")
    
    # Check platform
    is_rpi = is_raspberry_pi()
    info("Raspberry Pi Detected", is_rpi, "Hardware platform supported")
    
    # Check system commands
    v4l_utils_available = check_command_available("v4l2-ctl")
    info("System Package: v4l-utils", v4l_utils_available, "video4linux utilities")
    if not v4l_utils_available:
        failed_checks.append("System Package: v4l-utils")
        
    curl_available = check_command_available("curl")
    info("System Package: curl", curl_available, "HTTP client")
    
    libcamera_available = check_command_available("libcamera-still")
    info("System Package: libcamera-apps", libcamera_available, "Camera interface library")
    if not libcamera_available:
        failed_checks.append("System Package: libcamera-apps")
    
    # Check camera devices
    camera_detected, camera_info, video_devices = check_camera_detected()
    if video_devices:
        info("Camera Devices", True, f"Found {len(video_devices)} video device(s) ({', '.join(video_devices[:10])})")
        
        # Check driver info
        driver_info = run_command("v4l2-ctl --info", shell=True)
        if driver_info:
            print("  Driver Info:")
            for line in driver_info.split("\n"):
                if any(key in line for key in ["Driver name", "Card type", "Bus info", "Driver version"]):
                    print(f"  {line.strip()}")
    else:
        info("Camera Devices", False, "No video devices found")
        failed_checks.append("Camera Devices")
    
    # Check Raspberry Pi model
    rpi_model = get_raspberry_pi_model()
    info("Platform", rpi_model is not None, rpi_model or "Not a Raspberry Pi")
    
    # Check picamera2
    picamera2_available = check_module_available("picamera2")
    picamera2_version = get_module_version("picamera2") if picamera2_available else None
    picamera2_msg = f"Version {picamera2_version}" if picamera2_version else "Version unknown"
    info("picamera2", picamera2_available, picamera2_msg)
    if not picamera2_available:
        failed_checks.append("picamera2")
    
    # Check user groups
    user_in_video, group_msg = check_user_in_groups()
    info("Video Group Membership", user_in_video, group_msg)
    if not user_in_video:
        failed_checks.append("Video Group Membership")
    
    # Check device permissions
    permissions_ok, permission_msg = check_video_permissions()
    info("Camera Device Permissions", permissions_ok, permission_msg)
    if not permissions_ok:
        failed_checks.append("Camera Device Permissions")
    
    # Check if camera is detected
    info("Camera", camera_detected, camera_info if camera_detected else "Not detected")
    if not camera_detected:
        failed_checks.append("Camera")
    
    # Check for Global Shutter Camera
    gs_camera_detected, gs_camera_info = check_global_shutter_camera()
    info("Global Shutter Camera", gs_camera_detected, gs_camera_info)
    if not gs_camera_detected:
        failed_checks.append("Global Shutter Camera")
    
    # Python package dependencies section
    print("=" * 60)
    print(" Python Package Dependencies")
    print("=" * 60)
    
    # Check numpy
    numpy_available = check_module_available("numpy")
    numpy_version = get_module_version("numpy") if numpy_available else None
    numpy_msg = f"v{numpy_version}" if numpy_version else "Not installed"
    info("Module: numpy", numpy_available, numpy_msg)
    
    # Check OpenCV
    cv2_available = check_module_available("cv2")
    cv2_version = get_module_version("cv2") if cv2_available else None
    cv2_msg = f"v{cv2_version}" if cv2_version else "Not installed"
    info("Module: cv2", cv2_available, cv2_msg)
    
    # Get OpenCV details
    if cv2_available:
        opencv_version, supported_codecs = get_opencv_info()
        info("OpenCV", bool(opencv_version), f"Version {opencv_version}")
        
        # Show supported codecs
        codecs_str = ", ".join(supported_codecs) if supported_codecs else "None detected"
        info("Video Codecs", bool(supported_codecs), f"Supported: {codecs_str}")
    
    # Check YAML
    yaml_available = check_module_available("yaml")
    yaml_version = get_module_version("yaml") if yaml_available else None
    yaml_msg = f"v{yaml_version}" if yaml_version else "Not installed"
    info("Module: yaml", yaml_available, yaml_msg)
    
    # Check pylsl
    pylsl_available = check_module_available("pylsl")
    pylsl_version = get_module_version("pylsl") if pylsl_available else None
    pylsl_msg = f"v{pylsl_version}" if pylsl_version else "Not installed"
    info("Module: pylsl", pylsl_available, pylsl_msg)
    
    # Check requests
    requests_available = check_module_available("requests")
    requests_version = get_module_version("requests") if requests_available else None
    requests_msg = f"v{requests_version}" if requests_version else "Not installed"
    info("Module: requests", requests_available, requests_msg)
    
    # Check psutil
    psutil_available = check_module_available("psutil")
    psutil_version = get_module_version("psutil") if psutil_available else None
    psutil_msg = f"v{psutil_version}" if psutil_version else "Not installed"
    info("Module: psutil", psutil_available, psutil_msg)
    
    # Additional checks
    status_file_ok, status_file_msg = check_status_file_support()
    info("Status File Support", status_file_ok, status_file_msg)
    
    if status_file_ok:
        # Try to write to status file
        try:
            with open("/tmp/raspie_camera_status", "w") as f:
                f.write("Environment check: OK")
            info("Status File Write", True, "Can write to /tmp/raspie_camera_status")
        except:
            info("Status File Write", False, "Cannot write to status file")
    
    # Check disk space
    disk_status, disk_msg = check_disk_space()
    info("Storage Space", disk_status, disk_msg)
    
    # Check ntfy.sh
    ntfy_status, ntfy_msg = check_ntfy_service()
    info("ntfy.sh Service", ntfy_status, ntfy_msg)
    
    # If there are failed checks, suggest fixes
    fixes = suggest_fixes(failed_checks)
    if fixes:
        print("\n" + "=" * 60)
        print(" Suggested Fixes")
        print("=" * 60)
        for i, fix in enumerate(fixes, 1):
            print(f"{i}. {fix}")
    
    print("\nEnvironment check complete.")
    
    if not failed_checks:
        print(green("\nAll checks passed! The system is ready to use."))
        return 0
    else:
        if "Camera" in failed_checks:
            print(red("\nCamera not detected. Please check connections and run 'sudo raspi-config' to enable camera."))
        else:
            print(yellow("\nSome checks failed. Please fix the issues above and try again."))
        return 1

if __name__ == "__main__":
    # Run the main function
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nCheck cancelled by user.")
        sys.exit(130)
    except Exception as e:
        print(f"Error during environment check: {e}")
        sys.exit(1) 