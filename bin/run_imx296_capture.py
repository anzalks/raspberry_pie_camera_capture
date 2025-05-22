#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Run IMX296 Global Shutter Camera Capture System

This script is a simple launcher for the IMX296 camera capture system.
It ensures the correct environment and handles command-line arguments.

Author: Anzal KS <anzal.ks@gmail.com>
Date: May 22, 2025
"""

import os
import sys
import argparse
import subprocess
from pathlib import Path

def get_project_root():
    """Get the project root directory."""
    # This script is in the bin directory, so go up one level
    return os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

def main():
    """Main function to run the camera capture system."""
    project_root = get_project_root()
    
    # Add the project root to the Python path
    sys.path.insert(0, project_root)
    
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Run IMX296 Global Shutter Camera Capture System")
    parser.add_argument("--config", default=os.path.join(project_root, "config/config.yaml"),
                      help="Path to config file")
    parser.add_argument("--check-only", action="store_true",
                      help="Only check the environment and configuration, don't start the system")
    parser.add_argument("--sudo", action="store_true",
                      help="Run the media-ctl commands with sudo (required for hardware cropping)")
    args = parser.parse_args()
    
    # Check if we need to run with sudo for media-ctl
    if args.sudo and os.geteuid() != 0:
        print("Re-running with sudo to access media controller...")
        cmd = ["sudo", sys.executable] + sys.argv
        os.execvp("sudo", cmd)
    
    # Check for required tools
    print("Checking for required tools...")
    required_tools = {
        "libcamera-vid": "libcamera-apps",
        "libcamera-hello": "libcamera-apps",
        "media-ctl": "v4l-utils",
        "ffmpeg": "ffmpeg"
    }
    
    missing_tools = []
    for tool, package in required_tools.items():
        if not check_tool_exists(tool):
            missing_tools.append((tool, package))
    
    if missing_tools:
        print("ERROR: Missing required tools:")
        for tool, package in missing_tools:
            print(f"  - {tool} (install package: {package})")
        print("\nPlease install the missing tools and try again.")
        print("Example: sudo apt install libcamera-apps v4l-utils ffmpeg")
        return 1
    
    # Check for required Python packages
    print("Checking for required Python packages...")
    required_packages = [
        ("yaml", "pyyaml", "YAML parsing"),
        ("requests", "requests", "HTTP requests for ntfy.sh"),
        ("pylsl", "pylsl", "Lab Streaming Layer support")
    ]
    
    missing_packages = []
    for import_name, pip_name, description in required_packages:
        try:
            # For yaml, we need to try importing PyYAML
            if import_name == "yaml":
                try:
                    import yaml
                except ImportError:
                    missing_packages.append((pip_name, description))
            else:
                __import__(import_name)
        except ImportError:
            missing_packages.append((pip_name, description))
    
    if missing_packages:
        print("ERROR: Missing required Python packages:")
        for package, description in missing_packages:
            print(f"  - {package} ({description})")
        
        # Check if we're in a virtual environment
        in_venv = sys.prefix != sys.base_prefix
        if in_venv:
            print("\nYou are in a virtual environment. Install the missing packages with:")
            print(f"pip install {' '.join([p[0] for p in missing_packages])}")
        else:
            print("\nYou are not in a virtual environment. Consider creating one:")
            print(f"python3 -m venv .venv")
            print("source .venv/bin/activate")
            print(f"pip install {' '.join([p[0] for p in missing_packages])}")
        
        return 1
    
    # Check for the config file
    if not os.path.isfile(args.config):
        print(f"ERROR: Config file not found: {args.config}")
        
        # Check if example config exists
        example_config = os.path.join(project_root, "config/config.yaml.example")
        if os.path.isfile(example_config):
            print(f"An example config file is available at: {example_config}")
            print("You can copy and modify it:")
            print(f"cp {example_config} {args.config}")
        else:
            print("No example config found. Please create a config file.")
        
        return 1
    
    # If check-only flag is set, exit here
    if args.check_only:
        print("Environment check passed. All required tools and packages are available.")
        return 0
    
    # Import and run the main module
    try:
        from src.imx296_gs_capture.imx296_capture import main as run_camera
        return run_camera()
    except ImportError as e:
        print(f"ERROR: Failed to import IMX296 camera module: {e}")
        print("\nTry running with the project root in your Python path:")
        print(f"PYTHONPATH={project_root} python3 bin/run_imx296_capture.py")
        return 1
    except Exception as e:
        print(f"ERROR: Unexpected error running camera module: {e}")
        import traceback
        traceback.print_exc()
        return 1

def check_tool_exists(tool_name):
    """Check if a command-line tool exists."""
    try:
        subprocess.run(["which", tool_name], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        return True
    except subprocess.CalledProcessError:
        return False

if __name__ == "__main__":
    sys.exit(main()) 