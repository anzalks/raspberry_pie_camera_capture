#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Enhanced IMX296 Camera Capture Entry Point
==========================================
This script provides the main entry point for the enhanced IMX296 Global Shutter camera
capture system that integrates the proven simplified approach from simple_camera_lsl.py
with all the advanced features of the main branch.

Author: Anzal KS <anzal.ks@gmail.com>
Date: May 29, 2025
"""

import os
import sys
import time
import signal
import logging
from pathlib import Path

# Dynamic path detection
script_path = Path(__file__).resolve()
project_root = script_path.parent.parent
bin_dir = script_path.parent

# Change to project root for consistent operation
os.chdir(project_root)

# Add to Python path
sys.path.insert(0, str(project_root))

# Setup basic logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('imx296_main')

# Global capture instance for signal handling
capture_instance = None


def signal_handler(sig, frame):
    """Handle shutdown signals gracefully."""
    global capture_instance
    
    logger.info(f"Received signal {sig}, shutting down...")
    
    if capture_instance:
        try:
            capture_instance.cleanup()
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
    
    sys.exit(0)


def main():
    """Main entry point."""
    global capture_instance
    
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    logger.info("Enhanced IMX296 Camera Capture System")
    logger.info(f"Project root: {project_root}")
    logger.info(f"Working directory: {os.getcwd()}")
    
    try:
        # Import and run the main capture system
        from src.imx296_gs_capture.imx296_capture import main as capture_main
        
        # Run the enhanced capture system
        capture_main()
        
    except ImportError as e:
        logger.error(f"Failed to import capture system: {e}")
        logger.error("Make sure all dependencies are installed")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main() 