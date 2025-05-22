"""Simple status file writer for terminal fallback."""

import os
import threading
import time

class StatusFileWriter:
    """Writes camera status to a file for terminal fallback display."""
    
    def __init__(self, camera=None, buffer_manager=None):
        """Initialize the status file writer.
        
        Args:
            camera: LSLCameraStreamer instance
            buffer_manager: BufferTriggerManager instance
        """
        self.camera = camera
        self.buffer_manager = buffer_manager
        self.running = False
        self.status_file = "/tmp/raspie_camera_status"
        self.thread = None
        print(f"StatusFileWriter initialized! Will write to {self.status_file}")
    
    def start(self):
        """Start the status file writer thread."""
        if self.thread and self.thread.is_alive():
            return
            
        self.running = True
        self.thread = threading.Thread(target=self._update_loop, daemon=True)
        self.thread.start()
        print("StatusFileWriter thread started")
    
    def stop(self):
        """Stop the status file writer thread."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)
        
        # Clean up the status file
        try:
            if os.path.exists(self.status_file):
                os.remove(self.status_file)
        except Exception:
            pass
    
    def _update_loop(self):
        """Main update loop for writing status."""
        while self.running:
            try:
                self._write_status()
            except Exception as e:
                print(f"Error writing status file: {e}")
            
            # Sleep for a short interval
            time.sleep(1.0)
    
    def _write_status(self):
        """Write current status to the file."""
        if not self.camera:
            return
            
        with open(self.status_file, 'w') as f:
            # Camera status
            f.write(f"FPS: {self.camera.current_fps:.1f}/{self.camera.target_fps}\n")
            f.write(f"Frames captured: {self.camera.frames_captured}\n")
            
            if hasattr(self.camera, 'recording') and self.camera.recording:
                f.write("Status: RECORDING\n")
                f.write(f"Frames written: {self.camera.frames_written}\n")
            else:
                f.write("Status: BUFFERING\n")
            
            # Buffer status
            if self.buffer_manager and hasattr(self.buffer_manager, 'frame_buffer'):
                buffer = self.buffer_manager.frame_buffer
                if buffer:
                    buffer_size = len(buffer)
                    max_size = buffer.maxlen if hasattr(buffer, 'maxlen') else 0
                    if max_size > 0:
                        percent_full = int((buffer_size / max_size) * 100)
                        f.write(f"Buffer: {buffer_size}/{max_size} frames ({percent_full}% full)\n")
                    else:
                        f.write(f"Buffer: {buffer_size} frames\n") 