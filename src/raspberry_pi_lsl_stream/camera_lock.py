"""
Camera lock mechanism to ensure exclusive access to the camera.

This module provides a simple lock mechanism based on file locks to ensure
that only one instance of the camera capture process can access the camera
at a time.

Author: Anzal
Email: anzal.ks@gmail.com
GitHub: https://github.com/anzalks/
"""

import os
import fcntl
import time
import atexit
import logging

logger = logging.getLogger("CameraLock")

class CameraLock:
    """File-based lock for camera exclusive access."""
    
    def __init__(self, lock_file="/tmp/raspie_camera.lock", timeout=5):
        """
        Initialize the camera lock.
        
        Args:
            lock_file: Path to the lock file
            timeout: Maximum time to wait for lock acquisition
        """
        self.lock_file = lock_file
        self.timeout = timeout
        self.lock_handle = None
        self.is_locked = False
        
        # Register cleanup on exit
        atexit.register(self.release)
        
    def acquire(self):
        """
        Acquire the camera lock.
        
        Returns:
            bool: True if lock acquired, False otherwise
        """
        if self.is_locked:
            return True
            
        start_time = time.time()
        
        try:
            # Create the lock file if it doesn't exist
            self.lock_handle = open(self.lock_file, 'w+')
            
            # Try to acquire the lock with timeout
            while time.time() - start_time < self.timeout:
                try:
                    fcntl.flock(self.lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    self.is_locked = True
                    
                    # Write the current PID to the lock file
                    self.lock_handle.seek(0)
                    self.lock_handle.write(f"{os.getpid()}")
                    self.lock_handle.flush()
                    
                    logger.info(f"Acquired camera lock (PID: {os.getpid()})")
                    return True
                except IOError:
                    # Lock is held by another process
                    time.sleep(0.1)
            
            logger.error(f"Failed to acquire camera lock after {self.timeout} seconds")
            self.lock_handle.close()
            self.lock_handle = None
            return False
            
        except Exception as e:
            logger.error(f"Error acquiring camera lock: {e}")
            if self.lock_handle:
                self.lock_handle.close()
                self.lock_handle = None
            return False
    
    def release(self):
        """Release the camera lock if held."""
        if self.is_locked and self.lock_handle:
            try:
                fcntl.flock(self.lock_handle, fcntl.LOCK_UN)
                self.lock_handle.close()
                self.lock_handle = None
                self.is_locked = False
                logger.info("Released camera lock")
            except Exception as e:
                logger.error(f"Error releasing camera lock: {e}")
    
    def __enter__(self):
        """Context manager entry point."""
        self.acquire()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit point."""
        self.release()
        
    @staticmethod
    def get_lock_status():
        """
        Get information about the current lock.
        
        Returns:
            dict: Lock status information
        """
        lock_file = "/tmp/raspie_camera.lock"
        status = {
            "exists": os.path.exists(lock_file),
            "pid": None,
            "age": None
        }
        
        if status["exists"]:
            try:
                # Get the file stats
                stat = os.stat(lock_file)
                status["age"] = time.time() - stat.st_mtime
                
                # Try to read the PID
                with open(lock_file, 'r') as f:
                    content = f.read().strip()
                    if content and content.isdigit():
                        status["pid"] = int(content)
                        
                        # Check if the process is still running
                        status["running"] = os.path.exists(f"/proc/{status['pid']}")
            except Exception as e:
                logger.error(f"Error checking lock status: {e}")
                
        return status
        
    @staticmethod
    def force_release():
        """
        Force release of the camera lock.
        
        This is useful in case a process died without releasing the lock.
        """
        lock_file = "/tmp/raspie_camera.lock"
        if os.path.exists(lock_file):
            try:
                status = CameraLock.get_lock_status()
                pid = status.get("pid")
                
                # If process not running but lock exists, remove it
                if pid and not status.get("running", False):
                    os.remove(lock_file)
                    logger.info(f"Forcibly removed stale lock from PID {pid}")
                    return True
                elif pid:
                    # Try to kill the process
                    try:
                        os.kill(pid, 9)  # SIGKILL
                        time.sleep(0.5)
                        os.remove(lock_file)
                        logger.info(f"Killed process {pid} and removed lock")
                        return True
                    except ProcessLookupError:
                        # Process doesn't exist
                        os.remove(lock_file)
                        logger.info(f"Removed stale lock (PID {pid} doesn't exist)")
                        return True
                    except PermissionError:
                        logger.error(f"Cannot kill PID {pid} (permission denied)")
                        return False
                else:
                    # Lock file exists but no PID - just remove it
                    os.remove(lock_file)
                    logger.info("Removed lock file with no PID")
                    return True
            except Exception as e:
                logger.error(f"Error force releasing lock: {e}")
                return False
        return True  # No lock to release 