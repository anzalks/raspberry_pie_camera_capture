#!/bin/bash
#
# Daily initialization script for camera and audio recording
#
# Author: Anzal
# Email: anzal.ks@gmail.com
# GitHub: https://github.com/anzalks/
#

# Set error handling
set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

# Get the script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
VENV_PATH="$SCRIPT_DIR/.venv"

# Import YAML config
if [ ! -f "$SCRIPT_DIR/config.yaml" ]; then
    echo -e "${RED}Error: config.yaml file not found${NC}"
    exit 1
fi

# Function to print header
print_header() {
    echo -e "${BLUE}=======================================================${NC}"
    echo -e "${BLUE}= $1${NC}"
    echo -e "${BLUE}=======================================================${NC}"
}

# Function to print success message
print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

# Function to print error message
print_error() {
    echo -e "${RED}✗ $1${NC}"
}

# Create date-based folder structure
TODAY=$(date +%Y_%m_%d)
BASE_DIR="$SCRIPT_DIR/recordings"
DATE_DIR="$BASE_DIR/$TODAY"
VIDEO_DIR="$DATE_DIR/video"
AUDIO_DIR="$DATE_DIR/audio"

mkdir -p "$VIDEO_DIR"
mkdir -p "$AUDIO_DIR"

print_success "Created recording directories:"
echo "  - $VIDEO_DIR"
echo "  - $AUDIO_DIR"

# Activate virtual environment
if [[ -z "$VIRTUAL_ENV" || "$VIRTUAL_ENV" != "$VENV_PATH" ]]; then
    echo -e "${BLUE}Activating virtual environment...${NC}"
    source "$VENV_PATH/bin/activate"
    print_success "Virtual environment activated"
fi

# Check camera availability
print_header "Checking camera"
if ! ls /dev/video* > /dev/null 2>&1; then
    print_error "No camera devices found! Please check your camera connection."
    exit 1
else
    CAMERA_DEVICES=$(ls -la /dev/video* | grep -c "")
    print_success "Found $CAMERA_DEVICES camera device(s)"
fi

# Check USB microphone
print_header "Checking audio devices"
AUDIO_DEVICES=$(arecord -l | grep -c "")
if [ "$AUDIO_DEVICES" -gt 0 ]; then
    print_success "Found $AUDIO_DEVICES audio device(s)"
    echo -e "${YELLOW}Available audio devices:${NC}"
    arecord -l
else
    print_error "No audio devices found! Please check your microphone connection."
fi

# Kill any existing camera processes
print_header "Cleaning up existing processes"
pkill -f "python.*camera_capture" > /dev/null 2>&1 || true
print_success "Cleaned up any existing camera processes"

# Start the camera capture process with today's date folder
print_header "Starting camera capture"

nohup python -m src.raspberry_pi_lsl_stream.camera_capture \
    --width 400 \
    --height 400 \
    --fps 100 \
    --save-video \
    --output-dir "$VIDEO_DIR" \
    --codec mjpg \
    --buffer-size 20 \
    --ntfy-topic raspie-camera-test \
    --capture-cpu-core 2 \
    --writer-cpu-core 3 > "$DATE_DIR/camera.log" 2>&1 &

CAMERA_PID=$!
echo $CAMERA_PID > "$DATE_DIR/camera.pid"
print_success "Camera capture started with PID $CAMERA_PID"
print_success "Log file: $DATE_DIR/camera.log"

# Start audio capture process
print_header "Starting audio capture"

nohup python -m src.raspberry_pi_lsl_stream.audio_stream \
    --device default \
    --save-audio \
    --output-dir "$AUDIO_DIR" \
    --ntfy-topic raspie-camera-test > "$DATE_DIR/audio.log" 2>&1 &

AUDIO_PID=$!
echo $AUDIO_PID > "$DATE_DIR/audio.pid"
print_success "Audio capture started with PID $AUDIO_PID"
print_success "Log file: $DATE_DIR/audio.log"

# Print usage instructions
print_header "Remote Control Instructions"
echo "Use ntfy to control recording:"
echo "  - START: curl -d \"Start Recording\" ntfy.sh/raspie-camera-test"
echo "  - STOP:  curl -d \"Stop Recording\" ntfy.sh/raspie-camera-test"
echo ""
echo -e "${GREEN}Camera and audio system initialized successfully for $TODAY${NC}"
echo -e "${YELLOW}System is now listening for remote start/stop triggers...${NC}" 