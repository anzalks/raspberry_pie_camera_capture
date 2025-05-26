#!/usr/bin/env python3
"""
Video Recording Pipeline for IMX296 Camera - Dynamic Path Compatible
===================================================================

Handles video recording using ffmpeg with MKV output format.
Creates organized folder structure: recordings/yyyy_mm_dd/video/

Author: Anzal KS <anzal.ks@gmail.com>
Date: May 23, 2025
"""

import os
import subprocess
import threading
import time
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
import shutil


class VideoRecorder:
    """Handles video recording pipeline with ffmpeg using dynamic paths."""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize video recorder with dynamic path detection.
        
        Args:
            config: Recording configuration dictionary
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Dynamic path detection for project root
        project_root = Path(__file__).resolve().parent.parent.parent
        
        # Recording configuration with dynamic path resolution
        output_dir = self.config.get('output_dir', 'recordings')
        if os.path.isabs(output_dir):
            self.base_dir = Path(output_dir)
        else:
            # Make relative paths relative to project root
            self.base_dir = project_root / output_dir
        
        self.video_format = self.config.get('video_format', 'mkv')
        self.codec = self.config.get('codec', 'mjpeg')
        self.quality = self.config.get('quality', 90)
        
        # System paths with dynamic detection
        system_config = self.config.get('system', {})
        self.ffmpeg_path = system_config.get('ffmpeg_path', '/usr/bin/ffmpeg')
        
        # Also check for ffmpeg in PATH
        if not Path(self.ffmpeg_path).exists():
            ffmpeg_in_path = shutil.which('ffmpeg')
            if ffmpeg_in_path:
                self.ffmpeg_path = ffmpeg_in_path
                self.logger.info(f"Using ffmpeg from PATH: {self.ffmpeg_path}")
        
        # State tracking
        self.recording = False
        self.current_output_file = None
        self.current_process = None
        self.recording_thread = None
        self.start_time = None
        self.frame_count = 0
        
        # Ensure base directory exists
        self.base_dir.mkdir(parents=True, exist_ok=True)
        
        self.logger.info(f"Video recorder initialized with dynamic paths:")
        self.logger.info(f"  Project root: {project_root}")
        self.logger.info(f"  Output directory: {self.base_dir}")
        self.logger.info(f"  ffmpeg path: {self.ffmpeg_path}")
    
    def _get_recording_path(self, timestamp: Optional[datetime] = None) -> Path:
        """
        Get the full recording path with organized folder structure.
        
        Args:
            timestamp: Optional timestamp, defaults to current time
            
        Returns:
            Path object for the recording file
        """
        if timestamp is None:
            timestamp = datetime.now()
        
        # Create date folder (yyyy_mm_dd)
        date_folder = timestamp.strftime("%Y_%m_%d")
        date_path = self.base_dir / date_folder
        
        # Create video subfolder
        video_path = date_path / "video"
        video_path.mkdir(parents=True, exist_ok=True)
        
        # Generate filename (yyyy_mm_dd_hh_mm_ss.mkv)
        filename = timestamp.strftime(f"%Y_%m_%d_%H_%M_%S.{self.video_format}")
        
        return video_path / filename
    
    def _check_ffmpeg(self) -> bool:
        """Check if ffmpeg is available."""
        try:
            result = subprocess.run([self.ffmpeg_path, '-version'], 
                                   capture_output=True, timeout=10)
            return result.returncode == 0
        except (subprocess.SubprocessError, FileNotFoundError):
            return False
    
    def start_recording(self, input_source: str, duration: Optional[float] = None) -> Optional[str]:
        """
        Start video recording.
        
        Args:
            input_source: Input source for ffmpeg (e.g., '/dev/video0' or file path)
            duration: Optional recording duration in seconds
            
        Returns:
            Output file path if successful, None otherwise
        """
        if self.recording:
            self.logger.warning("Recording already in progress")
            return None
        
        # Check ffmpeg availability
        if not self._check_ffmpeg():
            self.logger.error(f"ffmpeg not found at {self.ffmpeg_path}")
            return None
        
        try:
            # Generate output path
            self.current_output_file = self._get_recording_path()
            
            # Build ffmpeg command
            cmd = self._build_ffmpeg_command(input_source, self.current_output_file, duration)
            
            self.logger.info(f"Starting video recording: {self.current_output_file}")
            self.logger.debug(f"ffmpeg command: {' '.join(cmd)}")
            
            # Start recording process
            self.current_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=os.environ.copy()
            )
            
            self.recording = True
            self.start_time = time.time()
            self.frame_count = 0
            
            # Start monitoring thread
            self.recording_thread = threading.Thread(
                target=self._monitor_recording, 
                args=(duration,), 
                daemon=True
            )
            self.recording_thread.start()
            
            self.logger.info(f"Video recording started: {self.current_output_file}")
            return str(self.current_output_file)
            
        except Exception as e:
            self.logger.error(f"Failed to start video recording: {e}")
            self.recording = False
            self.current_output_file = None
            return None
    
    def start_continuous_recording(self, input_source: str) -> Optional[str]:
        """
        Start continuous video recording that runs independently of triggers.
        
        Args:
            input_source: Input source for ffmpeg (e.g., '/dev/video0')
            
        Returns:
            Output file path if successful, None otherwise
        """
        if self.recording:
            self.logger.warning("Recording already in progress")
            return None
        
        # Check ffmpeg availability
        if not self._check_ffmpeg():
            self.logger.error(f"ffmpeg not found at {self.ffmpeg_path}")
            return None
        
        try:
            # Generate output path for continuous recording
            self.current_output_file = self._get_recording_path()
            
            # Build ffmpeg command for continuous recording (no duration limit)
            cmd = self._build_continuous_ffmpeg_command(input_source, self.current_output_file)
            
            self.logger.info(f"Starting continuous video recording: {self.current_output_file}")
            self.logger.debug(f"ffmpeg command: {' '.join(cmd)}")
            
            # Start recording process
            self.current_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=os.environ.copy()
            )
            
            self.recording = True
            self.start_time = time.time()
            self.frame_count = 0
            
            # Start monitoring thread for continuous recording
            self.recording_thread = threading.Thread(
                target=self._monitor_continuous_recording, 
                daemon=True
            )
            self.recording_thread.start()
            
            self.logger.info(f"Continuous video recording started: {self.current_output_file}")
            return str(self.current_output_file)
            
        except Exception as e:
            self.logger.error(f"Failed to start continuous video recording: {e}")
            self.recording = False
            self.current_output_file = None
            return None
    
    def _build_ffmpeg_command(self, input_source: str, output_file: Path, duration: Optional[float] = None) -> list:
        """Build ffmpeg command based on configuration."""
        cmd = [self.ffmpeg_path]
        
        # Input options
        if input_source.startswith('/dev/video'):
            # Video device input
            cmd.extend([
                '-f', 'v4l2',
                '-input_format', 'mjpeg',
                '-video_size', '900x600',  # Updated resolution
                '-framerate', '100',
                '-i', input_source
            ])
        else:
            # File input (from GScrop raw output)
            cmd.extend(['-i', input_source])
        
        # Duration if specified
        if duration:
            cmd.extend(['-t', str(duration)])
        
        # Video encoding options
        if self.codec == 'mjpeg':
            cmd.extend([
                '-c:v', 'mjpeg',
                '-q:v', str(100 - self.quality)  # ffmpeg uses inverse quality scale for MJPEG
            ])
        elif self.codec == 'h264':
            cmd.extend([
                '-c:v', 'libx264',
                '-preset', 'fast',
                '-crf', str(51 - int(self.quality * 0.51))  # Convert quality to CRF
            ])
        else:
            cmd.extend(['-c:v', self.codec])
        
        # Output options
        cmd.extend([
            '-f', self.video_format,
            '-y',  # Overwrite output file
            str(output_file)
        ])
        
        return cmd
    
    def _build_continuous_ffmpeg_command(self, input_source: str, output_file: Path) -> list:
        """Build ffmpeg command for continuous recording."""
        cmd = [self.ffmpeg_path]
        
        # Input options for continuous recording
        if input_source.startswith('/dev/video'):
            # Video device input with updated resolution
            cmd.extend([
                '-f', 'v4l2',
                '-input_format', 'mjpeg',
                '-video_size', '900x600',  # Updated resolution
                '-framerate', '100',
                '-i', input_source
            ])
        else:
            # File input
            cmd.extend(['-i', input_source])
        
        # Video encoding options for continuous recording
        if self.codec == 'mjpeg':
            cmd.extend([
                '-c:v', 'mjpeg',
                '-q:v', str(100 - self.quality)
            ])
        elif self.codec == 'h264':
            cmd.extend([
                '-c:v', 'libx264',
                '-preset', 'ultrafast',  # Faster preset for continuous recording
                '-crf', str(51 - int(self.quality * 0.51))
            ])
        else:
            cmd.extend(['-c:v', self.codec])
        
        # Output options for continuous recording
        cmd.extend([
            '-f', self.video_format,
            '-segment_time', '300',  # 5-minute segments
            '-segment_format', self.video_format,
            '-reset_timestamps', '1',
            '-y',  # Overwrite output file
            str(output_file)
        ])
        
        return cmd
    
    def _monitor_recording(self, duration: Optional[float] = None):
        """Monitor the recording process."""
        try:
            if duration:
                # Wait for specified duration
                self.current_process.wait(timeout=duration + 10)  # Extra time for processing
            else:
                # Wait indefinitely
                self.current_process.wait()
            
            # Check if process completed successfully
            if self.current_process.returncode == 0:
                self.logger.info("Video recording completed successfully")
            else:
                stderr_output = self.current_process.stderr.read().decode('utf-8')
                self.logger.warning(f"Video recording ended with return code {self.current_process.returncode}")
                self.logger.debug(f"ffmpeg stderr: {stderr_output}")
            
        except subprocess.TimeoutExpired:
            self.logger.warning("Video recording process timed out")
        except Exception as e:
            self.logger.error(f"Error monitoring video recording: {e}")
        finally:
            self.recording = False
    
    def _monitor_continuous_recording(self):
        """Monitor continuous recording process."""
        self.logger.info("Starting continuous recording monitor")
        
        try:
            while self.recording and self.current_process:
                # Check if process is still running
                if self.current_process.poll() is not None:
                    self.logger.warning("Continuous recording process ended unexpectedly")
                    break
                
                # Update frame count estimation
                if self.start_time:
                    duration = time.time() - self.start_time
                    self.frame_count = int(duration * 100)  # Estimate at 100 fps
                
                time.sleep(1)
                
        except Exception as e:
            self.logger.error(f"Error in continuous recording monitor: {e}")
        
        finally:
            self.logger.info("Continuous recording monitor finished")
    
    def stop_recording(self) -> Dict[str, Any]:
        """
        Stop current recording.
        
        Returns:
            Dict with recording statistics
        """
        if not self.recording:
            self.logger.warning("No recording in progress to stop")
            return {}
        
        stats = {}
        try:
            # Calculate duration
            if self.start_time:
                stats['duration'] = time.time() - self.start_time
            
            # Terminate ffmpeg process gracefully
            if self.current_process and self.current_process.poll() is None:
                self.logger.info("Stopping video recording...")
                self.current_process.terminate()
                
                try:
                    self.current_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.logger.warning("ffmpeg process didn't terminate gracefully, killing...")
                    self.current_process.kill()
                    self.current_process.wait()
            
            # Wait for monitoring thread to finish
            if self.recording_thread and self.recording_thread.is_alive():
                self.recording_thread.join(timeout=3)
            
            # Get file statistics
            if self.current_output_file and os.path.exists(self.current_output_file):
                file_stat = os.stat(self.current_output_file)
                stats.update({
                    'output_file': str(self.current_output_file),
                    'file_size_bytes': file_stat.st_size,
                    'file_size_mb': file_stat.st_size / (1024 * 1024)
                })
                
                self.logger.info(f"Recording saved: {self.current_output_file} ({stats['file_size_mb']:.1f} MB)")
            else:
                self.logger.warning("Output file not found after recording")
            
            self.recording = False
            return stats
            
        except Exception as e:
            self.logger.error(f"Error stopping video recording: {e}")
            self.recording = False
            return stats
    
    def is_recording(self) -> bool:
        """Check if currently recording."""
        return self.recording
    
    def get_current_file(self) -> Optional[str]:
        """Get current recording file path."""
        return str(self.current_output_file) if self.current_output_file else None
    
    def get_stats(self) -> Dict[str, Any]:
        """Get current recording statistics."""
        stats = {
            'recording': self.recording,
            'current_file': str(self.current_output_file) if self.current_output_file else None,
            'duration': time.time() - self.start_time if self.start_time else 0,
            'frame_count': self.frame_count
        }
        return stats
    
    def cleanup(self):
        """Clean up resources."""
        if self.recording:
            self.stop_recording()
        
        self.logger.info("Video recorder cleanup completed")
    
    def list_recordings(self, days: int = 7) -> list:
        """
        List recent recordings.
        
        Args:
            days: Number of days to look back
            
        Returns:
            List of recording file information
        """
        recordings = []
        
        try:
            # Look through date folders
            for date_folder in self.base_dir.iterdir():
                if not date_folder.is_dir():
                    continue
                
                video_folder = date_folder / "video"
                if not video_folder.exists():
                    continue
                
                # List video files
                for video_file in video_folder.glob(f"*.{self.video_format}"):
                    try:
                        stat = video_file.stat()
                        recordings.append({
                            'file': str(video_file),
                            'date': date_folder.name,
                            'size_mb': stat.st_size / (1024 * 1024),
                            'modified': datetime.fromtimestamp(stat.st_mtime)
                        })
                    except OSError:
                        continue
            
            # Sort by modification time (newest first)
            recordings.sort(key=lambda x: x['modified'], reverse=True)
            
            return recordings[:days * 10]  # Reasonable limit
            
        except Exception as e:
            self.logger.error(f"Error listing recordings: {e}")
            return [] 