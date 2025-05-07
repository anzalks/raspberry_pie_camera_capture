"""Raspberry Pi LSL Stream package."""

# Standard library imports first
import os
import sys
import platform
import importlib.util

# --- Environment setup code ---
def _setup_environment():
    """
    Set up the environment for the Raspberry Pi camera module.
    This function runs when the package is first imported.
    """
    print("Setting up Raspberry Pi camera environment...")
    
    # Check if we're running in a virtual environment
    if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
        venv_path = sys.prefix
        print(f"Found virtual environment: {venv_path}")
    else:
        venv_path = None
        
    # Add system Python paths for accessing system-installed modules like picamera2
    # This is necessary since the picamera2 module is installed system-wide
    if platform.system() == "Linux":
        # Only add these paths on Linux systems
        system_paths = [
            "/usr/lib/python3/dist-packages",
            "/usr/local/lib/python3/dist-packages"
        ]
        
        for path in system_paths:
            if os.path.exists(path) and path not in sys.path:
                sys.path.append(path)
                print(f"Added path: {path}")
    
    # Print some debug info
    print(f"Platform: {platform.platform()}")
    print(f"Python: {platform.python_version()}")
    print(f"Architecture: {platform.machine()}")

    # Detect Raspberry Pi hardware
    is_raspberry_pi = False
    try:
        with open('/proc/cpuinfo', 'r') as f:
            cpuinfo = f.read()
        is_raspberry_pi = 'Raspberry Pi' in cpuinfo or 'BCM' in cpuinfo
        if is_raspberry_pi:
            print("Detected Raspberry Pi hardware")
            
            # Check for picamera2 installation
            if importlib.util.find_spec('picamera2'):
                print("picamera2 is already installed.")
            else:
                print("Warning: picamera2 not found in system path.")
                print("Please install picamera2 using: sudo apt install python3-picamera2")
                
    except Exception as e:
        print(f"Error checking Raspberry Pi hardware: {e}")
    
    return is_raspberry_pi

# Run environment setup before any other imports
IS_RASPBERRY_PI = _setup_environment()

# Now import components
from ._version import __version__
from .camera_stream_fixed import LSLCameraStreamer
from .camera_capture import main as camera_capture_main
from .buffer_trigger import BufferTriggerManager

__all__ = [
    '__version__',
    'LSLCameraStreamer',
    'camera_capture_main',
    'BufferTriggerManager',
    'IS_RASPBERRY_PI'
] 