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
        
        try:    
            with open(self.status_file, 'w') as f:
                # Get camera info
                info = self.camera.get_info() if hasattr(self.camera, 'get_info') else {}
                
                # Write camera model and resolution
                f.write(f"Camera: {info.get('camera_model', 'Unknown')}\n")
                f.write(f"Resolution: {info.get('width', 0)}x{info.get('height', 0)} @ {info.get('fps', 0)} fps\n")
                
                # Write frame counts
                frame_count = self.camera.get_frame_count() if hasattr(self.camera, 'get_frame_count') else 0
                frames_written = self.camera.get_frames_written() if hasattr(self.camera, 'get_frames_written') else 0
                
                f.write(f"Frames captured: {frame_count}\n")
                f.write(f"Frames written: {frames_written}\n")
                
                # Write recording status
                recording = info.get('recording', False)
                if recording:
                    f.write("Status: RECORDING\n")
                else:
                    f.write("Status: WAITING FOR TRIGGER\n")
                
                # Buffer status
                if self.buffer_manager:
                    buffer_size = self.buffer_manager.get_buffer_size() if hasattr(self.buffer_manager, 'get_buffer_size') else 0
                    buffer_duration = self.buffer_manager.get_buffer_duration() if hasattr(self.buffer_manager, 'get_buffer_duration') else 0
                    f.write(f"Buffer: {buffer_size} frames ({buffer_duration:.1f}s)\n")
                    
                # Write commands
                f.write("\nCommands:\n")
                f.write("  - Start recording: curl -d 'Start Recording' ntfy.sh/raspie-camera-test\n")
                f.write("  - Stop recording: curl -d 'Stop Recording' ntfy.sh/raspie-camera-test\n")
                f.write("  - Press Ctrl+C to exit\n")
                
        except Exception as e:
            print(f"Error writing status: {e}") 