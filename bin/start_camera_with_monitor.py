#!/usr/bin/env python3
"""
IMX296 Camera Service Launcher with Status Monitor
==================================================

Launches the IMX296 camera service and optionally displays the real-time status monitor.
This script provides different launching options for the camera system.

Author: Anzal KS <anzal.ks@gmail.com>
Date: December 2024
"""

import os
import sys
import time
import signal
import argparse
import subprocess
import threading
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

def start_camera_service():
    """Start the IMX296 camera service."""
    print("Starting IMX296 camera service...")
    
    # Change to project directory
    os.chdir(project_root)
    
    # Start the camera service
    camera_cmd = [sys.executable, "-m", "src.imx296_gs_capture.imx296_capture"]
    camera_process = subprocess.Popen(
        camera_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True
    )
    
    return camera_process

def start_status_monitor():
    """Start the status monitor."""
    print("Starting status monitor...")
    
    # Path to status monitor script
    monitor_script = project_root / "bin" / "status_monitor.py"
    
    # Start the status monitor
    monitor_cmd = [sys.executable, str(monitor_script)]
    monitor_process = subprocess.Popen(
        monitor_cmd,
        stdout=sys.stdout,
        stderr=sys.stderr
    )
    
    return monitor_process

def monitor_camera_output(camera_process):
    """Monitor camera service output in background."""
    def output_reader():
        for line in iter(camera_process.stdout.readline, ''):
            if line:
                print(f"[CAMERA] {line.strip()}")
    
    thread = threading.Thread(target=output_reader, daemon=True)
    thread.start()
    return thread

def main():
    """Main launcher function."""
    parser = argparse.ArgumentParser(
        description="Launch IMX296 camera service with optional status monitor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                    # Start service only
  %(prog)s --monitor         # Start service with status monitor
  %(prog)s --monitor-only    # Start status monitor only (camera service must already be running)
  %(prog)s --help           # Show this help
        """
    )
    
    parser.add_argument(
        '--monitor', '-m',
        action='store_true',
        help='Launch with status monitor'
    )
    
    parser.add_argument(
        '--monitor-only', '-M',
        action='store_true',
        help='Launch status monitor only (camera service must already be running)'
    )
    
    parser.add_argument(
        '--no-output', '-q',
        action='store_true',
        help='Suppress camera service output when using monitor'
    )
    
    args = parser.parse_args()
    
    # Handle different launch modes
    camera_process = None
    monitor_process = None
    output_thread = None
    
    try:
        if args.monitor_only:
            # Just start the status monitor
            print("=" * 60)
            print("IMX296 CAMERA STATUS MONITOR ONLY")
            print("=" * 60)
            print("Note: Camera service must already be running")
            print("Press Ctrl+C to exit")
            print("=" * 60)
            
            monitor_process = start_status_monitor()
            monitor_process.wait()
            
        elif args.monitor:
            # Start both service and monitor
            print("=" * 60)
            print("IMX296 CAMERA SERVICE WITH STATUS MONITOR")
            print("=" * 60)
            print("Starting camera service and status monitor...")
            print("Press Ctrl+C to stop both")
            print("=" * 60)
            
            # Start camera service
            camera_process = start_camera_service()
            
            # Give camera service time to start
            time.sleep(3)
            
            if not args.no_output:
                # Monitor camera output in background
                output_thread = monitor_camera_output(camera_process)
            
            # Start status monitor
            monitor_process = start_status_monitor()
            
            # Wait for monitor to finish (user pressed 'q' or Ctrl+C)
            monitor_process.wait()
            
        else:
            # Start just the camera service
            print("=" * 60)
            print("IMX296 CAMERA SERVICE")
            print("=" * 60)
            print("Starting camera service...")
            print("Press Ctrl+C to stop")
            print("Use 'python bin/status_monitor.py' in another terminal for status")
            print("=" * 60)
            
            camera_process = start_camera_service()
            camera_process.wait()
    
    except KeyboardInterrupt:
        print("\nShutdown requested by user...")
    
    except Exception as e:
        print(f"Error: {e}")
        return 1
    
    finally:
        # Clean up processes
        if monitor_process and monitor_process.poll() is None:
            print("Stopping status monitor...")
            monitor_process.terminate()
            try:
                monitor_process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                monitor_process.kill()
        
        if camera_process and camera_process.poll() is None:
            print("Stopping camera service...")
            camera_process.terminate()
            try:
                camera_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                camera_process.kill()
        
        print("Shutdown complete.")
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 