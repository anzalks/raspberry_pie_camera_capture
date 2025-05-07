"""Raspberry Pi LSL Stream package."""

# Standard library imports first
import os
import sys
import platform
import subprocess
from pathlib import Path

# --- Environment setup code ---
def _setup_environment():
    """
    Set up the Python environment to ensure proper library paths.
    This function runs when the package is first imported.
    """
    print("Setting up Raspberry Pi camera environment...")
    
    # Find the probable project root (where .venv would be located)
    current_file = Path(__file__).resolve()
    # Navigate up from src/raspberry_pi_lsl_stream/__init__.py to project root
    project_root = current_file.parent.parent.parent
    
    # Detect the virtual environment - try different possible locations
    potential_venv_paths = [
        project_root / ".venv",                   # Standard venv in project root
        Path.home() / ".venv",                    # User home venv
        Path.home() / "Downloads" / "raspberry_pie_camera_capture" / ".venv",  # Downloaded project path
        Path("/home") / "pi" / "raspberry_pie_camera_capture" / ".venv",       # Common Pi username path
    ]
    
    venv_path = None
    for path in potential_venv_paths:
        if (path / "bin" / "python").exists():
            venv_path = path
            print(f"Found virtual environment: {venv_path}")
            
            # Add the venv site-packages to the path
            site_packages_paths = list(venv_path.glob("lib/python*/site-packages"))
            if site_packages_paths:
                site_packages = str(site_packages_paths[0])
                if site_packages not in sys.path:
                    sys.path.insert(0, site_packages)
                    print(f"Added venv site-packages to path: {site_packages}")
            break
            
    if not venv_path:
        print("Warning: Could not find virtual environment.")
    
    # Add potential library paths to system path for system-level packages
    sys_lib_paths = [
        '/usr/lib/python3/dist-packages',
        '/usr/lib/python3.9/site-packages',
        '/usr/lib/python3.10/site-packages',
        '/usr/lib/python3.11/site-packages', 
        '/usr/local/lib/python3/dist-packages',
    ]
    
    # Add any existing paths that aren't already in sys.path
    for path in sys_lib_paths:
        if os.path.exists(path) and path not in sys.path:
            sys.path.append(path)
            print(f"Added path: {path}")
    
    # Set environment variables for Raspberry Pi camera libraries
    os.environ["PICAMERA2_CONFIG_PATH"] = os.environ.get("PICAMERA2_CONFIG_PATH", "/usr/share/picamera2")
    
    # Set library path for camera libraries
    ld_path = os.environ.get("LD_LIBRARY_PATH", "")
    if "/usr/lib" not in ld_path:
        if ld_path:
            os.environ["LD_LIBRARY_PATH"] = f"{ld_path}:/usr/lib:/usr/local/lib"
        else:
            os.environ["LD_LIBRARY_PATH"] = "/usr/lib:/usr/local/lib"
    
    # Print platform information for debugging
    print(f"Platform: {platform.platform()}")
    print(f"Python: {platform.python_version()}")
    print(f"Architecture: {platform.machine()}")
    
    # Check if we're on Raspberry Pi
    is_raspberry_pi = False
    try:
        if os.path.exists('/proc/cpuinfo'):
            with open('/proc/cpuinfo', 'r') as f:
                cpuinfo = f.read()
            is_raspberry_pi = 'Raspberry Pi' in cpuinfo or 'BCM' in cpuinfo
            if is_raspberry_pi:
                print("Detected Raspberry Pi hardware")
                
                # On Raspberry Pi, try to install picamera2 if not present
                try:
                    # Check if picamera2 can be imported
                    __import__('picamera2')
                    print("picamera2 is already installed.")
                except ImportError:
                    print("picamera2 not found, attempting to install via pip...")
                    try:
                        # Try to install picamera2 using pip in the current environment
                        subprocess.check_call([sys.executable, "-m", "pip", "install", "picamera2"])
                        print("Successfully installed picamera2 via pip")
                    except subprocess.CalledProcessError:
                        print("Warning: Failed to install picamera2 via pip. You may need to install it manually.")
                        print("Try: 'sudo apt install python3-picamera2' or 'pip install picamera2'")
    except Exception as e:
        print(f"Error checking Raspberry Pi hardware: {e}")
        pass
    
    return is_raspberry_pi

# Run environment setup before any other imports
IS_RASPBERRY_PI = _setup_environment()

# Now import components
from ._version import __version__
from .camera_stream import LSLCameraStreamer
from .camera_capture import main as camera_capture_main
from .buffer_trigger import BufferTriggerManager

__all__ = [
    '__version__',
    'LSLCameraStreamer',
    'camera_capture_main',
    'BufferTriggerManager',
    'IS_RASPBERRY_PI'
] 