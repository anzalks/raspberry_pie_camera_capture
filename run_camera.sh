#!/bin/bash
# Run script for IMX296 High-FPS Camera Recorder

# Default configuration
WIDTH=400
HEIGHT=400
FPS=100
DURATION=0 # Run indefinitely
TOPIC="rpi_camera_trigger"
EXPOSURE=9000
BUFFER_DURATION=15
USE_CAM1=""

# Parse command line arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --width=*)
      WIDTH="${1#*=}"
      shift
      ;;
    --height=*)
      HEIGHT="${1#*=}"
      shift
      ;;
    --fps=*)
      FPS="${1#*=}"
      shift
      ;;
    --topic=*)
      TOPIC="${1#*=}"
      shift
      ;;
    --exposure=*)
      EXPOSURE="${1#*=}"
      shift
      ;;
    --buffer=*)
      BUFFER_DURATION="${1#*=}"
      shift
      ;;
    --cam1)
      USE_CAM1="1"
      shift
      ;;
    --help)
      echo "Usage: $0 [options]"
      echo "Options:"
      echo "  --width=WIDTH       Set capture width (default: 400)"
      echo "  --height=HEIGHT     Set capture height (default: 400)"
      echo "  --fps=FPS           Set frames per second (default: 100)"
      echo "  --topic=TOPIC       Set ntfy topic name (default: rpi_camera_trigger)"
      echo "  --exposure=US       Set exposure time in microseconds (default: 9000)"
      echo "  --buffer=SECONDS    Set RAM buffer duration in seconds (default: 15)"
      echo "  --cam1              Use camera 1 instead of default camera 0"
      echo "  --help              Show this help"
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      echo "Use --help for usage information"
      exit 1
      ;;
  esac
done

# Check for required tools
check_command() {
  if ! command -v "$1" &> /dev/null; then
    echo "Error: $1 is not installed. Please install it first."
    exit 1
  fi
}

check_command media-ctl
check_command libcamera-hello
check_command python3

# Create config file
CONFIG_FILE="config.json"
cat > "$CONFIG_FILE" << EOF
{
  "TARGET_WIDTH": $WIDTH,
  "TARGET_HEIGHT": $HEIGHT,
  "TARGET_FPS": $FPS,
  "EXPOSURE_TIME_US": $EXPOSURE,
  "RAM_BUFFER_DURATION_SECONDS": $BUFFER_DURATION,
  "NTFY_TOPIC": "$TOPIC",
  "RECORDING_PATH": "recordings"
}
EOF

echo "Created configuration file $CONFIG_FILE"
echo "Width: $WIDTH, Height: $HEIGHT, FPS: $FPS"
echo "Exposure: $EXPOSURE μs, Buffer: $BUFFER_DURATION seconds"
echo "NTFY Topic: $TOPIC"
if [ -n "$USE_CAM1" ]; then
  echo "Using Camera 1"
fi

# Make sure recordings directory exists
mkdir -p recordings

# Set environment variable for camera selection
if [ -n "$USE_CAM1" ]; then
  export cam1="1"
fi

# Check if Python virtual environment exists, create if not
if [ ! -d "venv" ]; then
  echo "Creating Python virtual environment..."
  python3 -m venv venv
  source venv/bin/activate
  pip install requests pylsl
else
  source venv/bin/activate
fi

# Run the camera script
python3 high_fps_camera_recorder.py --config "$CONFIG_FILE" 