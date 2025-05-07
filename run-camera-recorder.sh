#!/bin/bash
#
# Raspberry Pi Camera and Audio Recording Script
#
# This script activates the virtual environment, cleans up any existing camera/audio
# processes, and runs the capture scripts with proper parameters and CPU core assignment.
#
# Author: Anzal
# Email: anzal.ks@gmail.com
# GitHub: https://github.com/anzalks/
#

# Exit on error
set -e

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$SCRIPT_DIR"

# Configuration variables - modify these as needed
NTFY_TOPIC="raspie-camera-trigger"
RECORDINGS_DIR="$SCRIPT_DIR/recordings"
CAMERA_ID=0
AUDIO_DEVICE=0
RESOLUTION_WIDTH=640
RESOLUTION_HEIGHT=480
FPS=30
SAMPLE_RATE=48000
AUDIO_CHANNELS=1
BUFFER_SIZE=5.0  # Buffer size in seconds
VENV_PATH="$SCRIPT_DIR/.venv"
LOG_FILE="$SCRIPT_DIR/capture.log"

# CPU core assignments (adjust based on your Raspberry Pi model)
# For Raspberry Pi 4 with 4 cores: 0,1,2,3
# You may need to adjust these based on your specific device
VIDEO_CAPTURE_CORE=0
VIDEO_WRITER_CORE=1
AUDIO_CAPTURE_CORE=2
AUDIO_WRITER_CORE=3
LSL_CORE=0
NTFY_CORE=3

# ANSI colors for better readability
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to display messages
print_msg() {
  local color=$1
  local msg=$2
  echo -e "${color}[$(date '+%Y-%m-%d %H:%M:%S')] $msg${NC}"
}

# Create recordings directory if it doesn't exist
mkdir -p "$RECORDINGS_DIR/video"
mkdir -p "$RECORDINGS_DIR/audio"

# Ensure log directory exists
mkdir -p "$(dirname "$LOG_FILE")"

# Clean up any existing camera/audio processes
print_msg "$BLUE" "Checking for existing camera/audio processes..."
pkill -f "python.*camera_capture" || true
pkill -f "python.*audio_stream" || true
sleep 1

# Remove any existing lock files
if [ -f "/tmp/raspie_camera.lock" ]; then
  print_msg "$YELLOW" "Removing existing camera lock file..."
  rm -f "/tmp/raspie_camera.lock"
fi

if [ -f "/tmp/raspie_audio.lock" ]; then
  print_msg "$YELLOW" "Removing existing audio lock file..."
  rm -f "/tmp/raspie_audio.lock"
fi

# Activate virtual environment
if [ -f "$VENV_PATH/bin/activate" ]; then
  print_msg "$BLUE" "Activating virtual environment..."
  source "$VENV_PATH/bin/activate"
else
  print_msg "$RED" "Error: Virtual environment not found at $VENV_PATH"
  print_msg "$YELLOW" "Make sure you've run setup_pi.sh to create the virtual environment"
  exit 1
fi

# Check if the required modules can be imported
python -c "from src.raspberry_pi_lsl_stream import LSLCameraStreamer, LSLAudioStreamer" 2>/dev/null
if [ $? -ne 0 ]; then
  print_msg "$RED" "Error: Cannot import required modules. Check your installation."
  exit 1
fi

# Check for psutil package (required for CPU affinity)
python -c "import psutil" 2>/dev/null
if [ $? -ne 0 ]; then
  print_msg "$YELLOW" "Warning: psutil package not installed. CPU core pinning will be disabled."
  print_msg "$YELLOW" "To enable CPU pinning, run: pip install psutil"
fi

# Print startup information
print_msg "$GREEN" "Starting Raspberry Pi Camera and Audio Recorder"
print_msg "$BLUE" "Configuration:"
print_msg "$BLUE" "  • Camera ID: $CAMERA_ID"
print_msg "$BLUE" "  • Audio Device: $AUDIO_DEVICE"
print_msg "$BLUE" "  • Resolution: ${RESOLUTION_WIDTH}x${RESOLUTION_HEIGHT}"
print_msg "$BLUE" "  • FPS: $FPS"
print_msg "$BLUE" "  • Audio Sample Rate: $SAMPLE_RATE Hz"
print_msg "$BLUE" "  • Audio Channels: $AUDIO_CHANNELS"
print_msg "$BLUE" "  • Buffer Size: $BUFFER_SIZE seconds"
print_msg "$BLUE" "  • Recording Directory: $RECORDINGS_DIR"
print_msg "$BLUE" "  • NTFY Topic: $NTFY_TOPIC"
print_msg "$BLUE" "  • Log File: $LOG_FILE"
print_msg "$BLUE" "  • CPU Core Assignment:"
print_msg "$BLUE" "    - Video Capture: Core $VIDEO_CAPTURE_CORE"
print_msg "$BLUE" "    - Video Writer: Core $VIDEO_WRITER_CORE"
print_msg "$BLUE" "    - Audio Capture: Core $AUDIO_CAPTURE_CORE"
print_msg "$BLUE" "    - Audio Writer: Core $AUDIO_WRITER_CORE"

# Function to handle graceful exit
cleanup() {
  print_msg "$YELLOW" "Stopping capture processes..."
  pkill -f "python.*camera_capture" || true
  pkill -f "python.*audio_stream" || true
  kill -- -$$  # Kill all processes in the current process group
}

# Register trap for SIGINT and SIGTERM
trap cleanup SIGINT SIGTERM

# Start the camera capture script with logging (in background)
print_msg "$GREEN" "Starting camera capture. Press Ctrl+C to stop."
python -m src.raspberry_pi_lsl_stream.camera_capture \
  --camera-id "$CAMERA_ID" \
  --width "$RESOLUTION_WIDTH" \
  --height "$RESOLUTION_HEIGHT" \
  --fps "$FPS" \
  --buffer-size "$BUFFER_SIZE" \
  --ntfy-topic "$NTFY_TOPIC" \
  --save-video \
  --output-dir "$RECORDINGS_DIR/video" \
  --no-preview \
  --codec h264 \
  --capture-cpu-core "$VIDEO_CAPTURE_CORE" \
  --writer-cpu-core "$VIDEO_WRITER_CORE" \
  > >(tee -a "$LOG_FILE") 2>&1 &

# Small delay to ensure camera starts
sleep 2

# Start the audio capture script with logging
print_msg "$GREEN" "Starting audio capture. Press Ctrl+C to stop."
python -m src.raspberry_pi_lsl_stream.audio_stream \
  --device-index "$AUDIO_DEVICE" \
  --sample-rate "$SAMPLE_RATE" \
  --channels "$AUDIO_CHANNELS" \
  --buffer-size "$BUFFER_SIZE" \
  --ntfy-topic "$NTFY_TOPIC" \
  --save-audio \
  --output-dir "$RECORDINGS_DIR/audio" \
  --capture-cpu-core "$AUDIO_CAPTURE_CORE" \
  --writer-cpu-core "$AUDIO_WRITER_CORE" \
  2>&1 | tee -a "$LOG_FILE"

# Wait for processes to finish (should only happen on errors since we're using trap for Ctrl+C)
wait

# Exit message 
print_msg "$YELLOW" "Capture system exited."
exit 0 