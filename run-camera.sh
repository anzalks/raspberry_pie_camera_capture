#!/bin/bash
#
# Wrapper script for camera capture to ensure virtual environment is activated
#
# Author: Anzal
# Email: anzal.ks@gmail.com
# GitHub: https://github.com/anzalks/
#

# Get the script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
VENV_PATH="$SCRIPT_DIR/.venv"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Activate virtual environment if not already active
if [[ -z "$VIRTUAL_ENV" || "$VIRTUAL_ENV" != "$VENV_PATH" ]]; then
    echo -e "${BLUE}Activating virtual environment...${NC}"
    source "$VENV_PATH/bin/activate"
fi

# Run the test script first to check environment
echo -e "${BLUE}Checking environment setup...${NC}"
python "$SCRIPT_DIR/check-camera-env.py" > /dev/null 2>&1

# Check if camera devices exist
if ! ls /dev/video* > /dev/null 2>&1; then
    echo -e "${RED}No camera devices found! Please check your camera connection.${NC}"
    exit 1
fi

# Run the camera capture script with all arguments passed to this script
echo -e "${GREEN}Starting camera capture...${NC}"
echo -e "${BLUE}Command: python -m src.raspberry_pi_lsl_stream.camera_capture $@${NC}"
python -m src.raspberry_pi_lsl_stream.camera_capture "$@" 