"""
IMX296 Global Shutter Camera Capture System
==========================================

Complete camera capture system for IMX296 Global Shutter camera featuring:
- GScrop-based hardware cropping and frame markers
- 3-channel LSL streaming (CaptureTimeUnix, ntfy_notification_active, session_frame_no)
- ntfy.sh remote control integration
- Video recording pipeline with organized folder structure

Author: Anzal KS <anzal.ks@gmail.com>
Date: May 23, 2025
"""

from .imx296_capture import GSCropCameraCapture, main, load_config, setup_logging
from .ntfy_handler import NtfyHandler
from .video_recorder import VideoRecorder

__version__ = "2.0.0"
__author__ = "Anzal KS <anzal.ks@gmail.com>"

__all__ = [
    'GSCropCameraCapture', 
    'NtfyHandler', 
    'VideoRecorder',
    'main', 
    'load_config', 
    'setup_logging'
] 