#!/usr/bin/env python3
"""
IMX296 Camera System Cleanup and Launcher
=========================================

Comprehensive cleanup script that stops existing services, removes conflicting
files, and provides a clean start for the IMX296 camera system.

Author: Anzal KS <anzal.ks@gmail.com>
Date: December 2024
"""

import os
import sys
import time
import signal
import subprocess
import argparse
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

class CameraSystemCleanup:
    """Handles comprehensive cleanup of camera system."""
    
    def __init__(self):
        self.project_root = project_root
        self.systemd_services = [
            'imx296-camera',
            'imx296-camera-monitor', 
            'raspberry-pi-camera',
            'camera-service',
            'lsl-camera',
            'gscrop-camera'
        ]
        self.shared_memory_files = [
            '/dev/shm/imx296_status.json',
            '/dev/shm/camera_markers.txt',
            '/dev/shm/buffer_markers.txt',
            '/dev/shm/camera_status.json',
            '/dev/shm/lsl_stream.lock'
        ]
        self.process_names = [
            'imx296_capture',
            'status_monitor',
            'camera_stream',
            'GScrop',
            'ffmpeg'
        ]
        
    def print_section(self, title):
        """Print a formatted section header."""
        print(f"\n{'=' * 60}")
        print(f"  {title}")
        print(f"{'=' * 60}")
    
    def run_command(self, cmd, description, ignore_errors=True):
        """Run a command with description and error handling."""
        print(f"  → {description}...")
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                shell=isinstance(cmd, str)
            )
            if result.returncode == 0 or ignore_errors:
                if result.stdout.strip():
                    print(f"    ✅ {result.stdout.strip()}")
                else:
                    print(f"    ✅ Done")
                return True
            else:
                print(f"    ❌ Error: {result.stderr.strip()}")
                return False
        except Exception as e:
            if ignore_errors:
                print(f"    ⚠️  Warning: {e}")
                return False
            else:
                print(f"    ❌ Error: {e}")
                return False
    
    def stop_systemd_services(self):
        """Stop all related systemd services."""
        self.print_section("STOPPING SYSTEMD SERVICES")
        
        stopped_any = False
        for service in self.systemd_services:
            # Check if service exists and is active
            check_cmd = f"systemctl is-active {service}"
            result = subprocess.run(check_cmd, shell=True, capture_output=True, text=True)
            
            if result.returncode == 0:  # Service is active
                print(f"  🔴 Stopping active service: {service}")
                self.run_command(f"sudo systemctl stop {service}", f"Stop {service}")
                stopped_any = True
            else:
                print(f"  ⚪ Service not active: {service}")
        
        if not stopped_any:
            print("  ✅ No active services found")
    
    def disable_systemd_services(self):
        """Disable and remove systemd service files."""
        self.print_section("REMOVING SYSTEMD SERVICE FILES")
        
        removed_any = False
        for service in self.systemd_services:
            service_file = f"/etc/systemd/system/{service}.service"
            if os.path.exists(service_file):
                print(f"  🗑️  Removing service file: {service}.service")
                self.run_command(f"sudo systemctl disable {service}", f"Disable {service}")
                self.run_command(f"sudo rm {service_file}", f"Remove {service_file}")
                removed_any = True
            else:
                print(f"  ⚪ Service file not found: {service}.service")
        
        if removed_any:
            self.run_command("sudo systemctl daemon-reload", "Reload systemd daemon")
        else:
            print("  ✅ No service files to remove")
    
    def kill_related_processes(self):
        """Kill any running camera-related processes."""
        self.print_section("TERMINATING RELATED PROCESSES")
        
        killed_any = False
        for process_name in self.process_names:
            # Find processes by name
            find_cmd = f"pgrep -f {process_name}"
            result = subprocess.run(find_cmd, shell=True, capture_output=True, text=True)
            
            if result.returncode == 0 and result.stdout.strip():
                pids = result.stdout.strip().split('\n')
                for pid in pids:
                    if pid.strip():
                        print(f"  🔪 Killing process: {process_name} (PID: {pid})")
                        self.run_command(f"kill -TERM {pid}", f"Terminate PID {pid}")
                        killed_any = True
        
        if killed_any:
            print("  ⏳ Waiting for processes to terminate...")
            time.sleep(2)
            
            # Force kill any remaining processes
            for process_name in self.process_names:
                find_cmd = f"pgrep -f {process_name}"
                result = subprocess.run(find_cmd, shell=True, capture_output=True, text=True)
                if result.returncode == 0 and result.stdout.strip():
                    pids = result.stdout.strip().split('\n')
                    for pid in pids:
                        if pid.strip():
                            print(f"  💥 Force killing: {process_name} (PID: {pid})")
                            self.run_command(f"kill -KILL {pid}", f"Force kill PID {pid}")
        else:
            print("  ✅ No related processes found")
    
    def cleanup_shared_memory(self):
        """Clean up shared memory files."""
        self.print_section("CLEANING UP SHARED MEMORY")
        
        cleaned_any = False
        for shm_file in self.shared_memory_files:
            if os.path.exists(shm_file):
                print(f"  🗑️  Removing shared memory file: {shm_file}")
                self.run_command(f"rm {shm_file}", f"Remove {shm_file}")
                cleaned_any = True
            else:
                print(f"  ⚪ File not found: {shm_file}")
        
        if not cleaned_any:
            print("  ✅ No shared memory files to clean")
    
    def cleanup_old_configs(self):
        """Clean up old configuration files that might conflict."""
        self.print_section("CLEANING UP OLD CONFIGURATIONS")
        
        # Old config locations that might conflict
        old_configs = [
            "config.yaml",  # Old location in root
            "/etc/imx296-camera/",
            "/home/pi/.camera_config/",
            "old_config/",
            "backup_config/"
        ]
        
        cleaned_any = False
        for config_path in old_configs:
            full_path = self.project_root / config_path if not config_path.startswith('/') else Path(config_path)
            
            if full_path.exists():
                if full_path.is_file():
                    print(f"  🗑️  Removing old config file: {full_path}")
                    self.run_command(f"rm {full_path}", f"Remove {full_path}")
                elif full_path.is_dir():
                    print(f"  🗑️  Removing old config directory: {full_path}")
                    self.run_command(f"rm -rf {full_path}", f"Remove {full_path}")
                cleaned_any = True
            else:
                print(f"  ⚪ Config not found: {full_path}")
        
        if not cleaned_any:
            print("  ✅ No old configurations to clean")
    
    def cleanup_log_files(self, keep_current=True):
        """Clean up old log files."""
        self.print_section("CLEANING UP LOG FILES")
        
        log_dirs = [
            self.project_root / "logs",
            Path("/var/log/imx296-camera"),
            Path("/tmp/camera_logs")
        ]
        
        cleaned_any = False
        for log_dir in log_dirs:
            if log_dir.exists():
                if keep_current:
                    # Keep current log, remove old ones
                    for log_file in log_dir.glob("*.log.*"):  # Rotated logs
                        print(f"  🗑️  Removing old log: {log_file}")
                        self.run_command(f"rm {log_file}", f"Remove {log_file}")
                        cleaned_any = True
                else:
                    # Remove all logs
                    for log_file in log_dir.glob("*.log*"):
                        print(f"  🗑️  Removing log: {log_file}")
                        self.run_command(f"rm {log_file}", f"Remove {log_file}")
                        cleaned_any = True
        
        if not cleaned_any:
            print("  ✅ No log files to clean")
    
    def cleanup_python_cache(self):
        """Clean up Python cache files."""
        self.print_section("CLEANING UP PYTHON CACHE")
        
        # Find and remove __pycache__ directories
        cache_dirs = list(self.project_root.rglob("__pycache__"))
        
        if cache_dirs:
            for cache_dir in cache_dirs:
                print(f"  🗑️  Removing cache: {cache_dir}")
                self.run_command(f"rm -rf {cache_dir}", f"Remove {cache_dir}")
        else:
            print("  ✅ No Python cache to clean")
    
    def verify_clean_state(self):
        """Verify the system is in a clean state."""
        self.print_section("VERIFYING CLEAN STATE")
        
        issues = []
        
        # Check for active services
        for service in self.systemd_services:
            result = subprocess.run(
                f"systemctl is-active {service}",
                shell=True, capture_output=True, text=True
            )
            if result.returncode == 0:
                issues.append(f"Service still active: {service}")
        
        # Check for running processes
        for process_name in self.process_names:
            result = subprocess.run(
                f"pgrep -f {process_name}",
                shell=True, capture_output=True, text=True
            )
            if result.returncode == 0:
                issues.append(f"Process still running: {process_name}")
        
        # Check for shared memory files
        for shm_file in self.shared_memory_files:
            if os.path.exists(shm_file):
                issues.append(f"Shared memory file exists: {shm_file}")
        
        if issues:
            print("  ⚠️  Issues found:")
            for issue in issues:
                print(f"    - {issue}")
            return False
        else:
            print("  ✅ System is clean and ready")
            return True
    
    def full_cleanup(self, include_logs=False):
        """Perform full system cleanup."""
        print("🧹 IMX296 CAMERA SYSTEM CLEANUP")
        print("🎯 Preparing for clean start...")
        
        self.stop_systemd_services()
        self.disable_systemd_services()
        self.kill_related_processes()
        self.cleanup_shared_memory()
        self.cleanup_old_configs()
        self.cleanup_log_files(keep_current=not include_logs)
        self.cleanup_python_cache()
        
        return self.verify_clean_state()


def start_camera_service(with_monitor=False):
    """Start the camera service after cleanup."""
    print("\n🚀 STARTING CAMERA SERVICE")
    print("=" * 60)
    
    os.chdir(project_root)
    
    if with_monitor:
        print("  → Starting camera service with status monitor...")
        cmd = [sys.executable, "bin/start_camera_with_monitor.py", "--monitor"]
    else:
        print("  → Starting camera service only...")
        cmd = [sys.executable, "bin/start_camera_with_monitor.py"]
    
    try:
        print(f"  → Command: {' '.join(cmd)}")
        print("  → Press Ctrl+C to stop")
        print("=" * 60)
        
        # Start the service
        process = subprocess.Popen(cmd)
        process.wait()
        
    except KeyboardInterrupt:
        print("\n  🛑 Service stopped by user")
        return 0
    except Exception as e:
        print(f"\n  ❌ Error starting service: {e}")
        return 1


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Clean up and start IMX296 camera system",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                           # Cleanup and start service only
  %(prog)s --monitor                 # Cleanup and start with monitor
  %(prog)s --cleanup-only            # Cleanup only, don't start
  %(prog)s --cleanup-only --logs     # Cleanup including all logs
  %(prog)s --no-cleanup --monitor    # Skip cleanup, start with monitor
        """
    )
    
    parser.add_argument(
        '--monitor', '-m',
        action='store_true',
        help='Start with status monitor after cleanup'
    )
    
    parser.add_argument(
        '--cleanup-only', '-c',
        action='store_true',
        help='Perform cleanup only, do not start service'
    )
    
    parser.add_argument(
        '--no-cleanup', '-n',
        action='store_true',
        help='Skip cleanup, start service directly'
    )
    
    parser.add_argument(
        '--logs', '-l',
        action='store_true',
        help='Include log files in cleanup (use with --cleanup-only)'
    )
    
    parser.add_argument(
        '--verify-only', '-v',
        action='store_true',
        help='Only verify current state, no cleanup or start'
    )
    
    args = parser.parse_args()
    
    cleanup = CameraSystemCleanup()
    
    if args.verify_only:
        cleanup.verify_clean_state()
        return 0
    
    if not args.no_cleanup:
        # Perform cleanup
        clean_success = cleanup.full_cleanup(include_logs=args.logs)
        
        if not clean_success:
            print("\n⚠️  WARNING: Cleanup completed with issues")
            print("   You may want to investigate before proceeding")
            
            response = input("\nContinue anyway? (y/N): ")
            if response.lower() != 'y':
                print("Aborting...")
                return 1
        else:
            print("\n✅ CLEANUP SUCCESSFUL")
    
    if not args.cleanup_only:
        # Start the service
        return start_camera_service(with_monitor=args.monitor)
    else:
        print("\n🏁 Cleanup complete. System ready for fresh start.")
        print("   Use 'python bin/start_camera_with_monitor.py' to start")
        return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n🛑 Cleanup interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        sys.exit(1) 