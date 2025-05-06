#!/usr/bin/env python3
"""
Example script demonstrating how to run audio and video capture with visualizers.

This script shows how to:
1. Enable both video and audio previews
2. Distribute processing across different CPU cores (if psutil is available)
3. Capture synchronized audio-video with visualizations

Run with:
    python examples/run_with_visualizers.py

The script will automatically handle missing dependencies gracefully.
"""

import os
import sys
import signal
import time
import subprocess
import multiprocessing

# Get the number of available CPU cores
cpu_count = multiprocessing.cpu_count()
print(f"Detected {cpu_count} CPU cores")

# Define core assignments if there are enough cores
# We want to separate intensive tasks across different cores
if cpu_count >= 4:
    # 0: Reserved for OS
    # 1: Video capture
    # 2: Video writer
    # 3: Audio capture
    # 4+: Visualization (if available)
    video_capture_core = 1
    video_writer_core = 2
    video_vis_core = min(4, cpu_count-1)
    audio_capture_core = 3
    audio_writer_core = min(5, cpu_count-1)
    audio_vis_core = min(6, cpu_count-1)
elif cpu_count >= 2:
    # Simpler allocation for dual-core systems
    video_capture_core = 0
    video_writer_core = 1
    video_vis_core = 0
    audio_capture_core = 0
    audio_writer_core = 1
    audio_vis_core = 1
else:
    # Single core - no affinity needed
    video_capture_core = None
    video_writer_core = None
    video_vis_core = None
    audio_capture_core = None
    audio_writer_core = None
    audio_vis_core = None

# Build the command with appropriate arguments
cmd = [
    sys.executable, "-m", "raspberry_pi_lsl_stream.cli",
    "--enable-audio",                  # Enable audio capture
    "--show-preview",                  # Show video preview
    "--show-audio-preview",            # Show audio preview with visualization
    "--width", "640",                  # Set video width
    "--height", "480",                 # Set video height
    "--fps", "30",                     # Set video fps
    "--sample-rate", "48000",          # Set audio sample rate
    "--channels", "1",                 # Set audio channels (mono)
    "--use-buffer",                    # Enable buffer mode
    "--buffer-size", "20",             # Buffer size in seconds
    "--threaded-writer",               # Enable threaded video writer
    "--ntfy-topic", "raspie_trigger",  # Set ntfy topic for remote triggering
]

# Add CPU core affinity options if cores are available
if video_capture_core is not None:
    cmd.extend(["--video-capture-core", str(video_capture_core)])
if video_writer_core is not None:
    cmd.extend(["--video-writer-core", str(video_writer_core)])
if video_vis_core is not None:
    cmd.extend(["--video-vis-core", str(video_vis_core)])
if audio_capture_core is not None:
    cmd.extend(["--audio-capture-core", str(audio_capture_core)])
if audio_writer_core is not None:
    cmd.extend(["--audio-writer-core", str(audio_writer_core)])
if audio_vis_core is not None:
    cmd.extend(["--audio-vis-core", str(audio_vis_core)])

# Print ntfy instructions
print("\nNtfy.sh Trigger Control:")
print("- Start recording: curl -d \"start recording\" ntfy.sh/raspie_trigger")
print("- Stop recording: curl -d \"stop recording\" ntfy.sh/raspie_trigger")
print("- Also available: Press 't' in preview window to start, 's' to stop")

# Print the command
print("\nRunning command:")
print(" ".join(cmd))
print("\nPress Ctrl+C to stop the capture\n")

# Define signal handler for graceful shutdown
def signal_handler(sig, frame):
    print('\nStopping the capture process...')
    if proc:
        proc.terminate()
    sys.exit(0)

# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# Start the process
proc = None
try:
    proc = subprocess.Popen(cmd)
    proc.wait()
except KeyboardInterrupt:
    print("\nKeyboard interrupt received, stopping...")
    if proc:
        proc.terminate()
except Exception as e:
    print(f"Error: {e}")
    if proc:
        proc.terminate()
    sys.exit(1) 