"""
IMX296 Global Shutter Camera Capture System

This package provides the main camera capture functionality for the IMX296 Global Shutter camera
using the GScrop shell script for frame capture with precise LSL timestamping.

Author: Anzal KS <anzal.ks@gmail.com>
Date: May 26, 2025
"""

from .imx296_capture import GSCropCameraCapture, main, load_config, setup_logging

__all__ = ['GSCropCameraCapture', 'main', 'load_config', 'setup_logging'] 