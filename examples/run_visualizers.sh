#!/bin/bash
# Script to run Raspie Capture with both audio and video visualizers

# Set the default ntfy topic
NTFY_TOPIC="raspie_trigger"

# Detect if we're running on Raspberry Pi
if [ -f /proc/device-tree/model ] && grep -q "Raspberry Pi" /proc/device-tree/model; then
    RASPBERRY_PI=true
    echo "Running on Raspberry Pi"
else
    RASPBERRY_PI=false
    echo "Not running on Raspberry Pi"
fi

# Default command
CMD="python -m raspberry_pi_lsl_stream.cli --enable-audio --show-preview --show-audio-preview --use-buffer --buffer-size 20 --ntfy-topic $NTFY_TOPIC"

# Add optimized settings for Raspberry Pi if detected
if [ "$RASPBERRY_PI" = true ]; then
    # Lower resolution and framerate on Pi for better performance
    CMD="$CMD --width 320 --height 240 --fps 15 --threaded-writer"
    
    # Try to use hardware-accelerated h264 codec on Pi
    CMD="$CMD --codec h264"
    
    # Check number of cores
    NUM_CORES=$(nproc)
    echo "Detected $NUM_CORES CPU cores"
    
    if [ $NUM_CORES -ge 4 ]; then
        # Quad-core Pi (Pi 4, etc.)
        CMD="$CMD --video-capture-core 0 --video-writer-core 1 --video-vis-core 2 --audio-capture-core 3"
    elif [ $NUM_CORES -ge 2 ]; then
        # Dual-core Pi (older models)
        CMD="$CMD --video-capture-core 0 --video-writer-core 1 --audio-capture-core 0 --audio-vis-core 1"
    fi
else
    # Higher quality for desktop systems
    CMD="$CMD --width 640 --height 480 --fps 30 --threaded-writer"
fi

# Print help message about ntfy control
echo "-------------------------------------------------------------"
echo "Ntfy.sh Trigger Control:"
echo "- Start recording: curl -d \"start recording\" ntfy.sh/$NTFY_TOPIC"
echo "- Stop recording:  curl -d \"stop recording\" ntfy.sh/$NTFY_TOPIC"
echo "-------------------------------------------------------------"
echo "Keyboard Controls (when preview window has focus):"
echo "- Press 't' to trigger recording manually"
echo "- Press 's' to stop recording manually"
echo "- Press 'q' or ESC to quit visualizers"
echo "-------------------------------------------------------------"

# Print the command
echo "Running command: $CMD"
echo "Press Ctrl+C to stop"

# Execute the command
eval $CMD 