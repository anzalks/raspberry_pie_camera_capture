#!/bin/bash
#
# Test script for Raspberry Pi camera capture
# This will test the camera detection, ntfy integration, and recording
#
# Author: Anzal
# Email: anzal.ks@gmail.com
# GitHub: https://github.com/anzalks/
#

# Exit on error
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test directory
TEST_DIR="test_recordings"
NTFY_TOPIC="raspie-camera-test"

# Print header
echo -e "${BLUE}=========================================${NC}"
echo -e "${BLUE}    Raspberry Pi Camera Capture Test     ${NC}"
echo -e "${BLUE}=========================================${NC}"
echo

# Check Python and virtual environment
echo -e "${YELLOW}Checking Python installation...${NC}"
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Python 3 is not installed. Please install Python 3.${NC}"
    exit 1
fi

# Check if we're in a virtual environment
if [ -z "$VIRTUAL_ENV" ]; then
    echo -e "${YELLOW}Not running in a virtual environment. Creating and activating one...${NC}"
    if [ ! -d ".venv" ]; then
        python3 -m venv .venv
    fi
    source .venv/bin/activate
    echo -e "${GREEN}Virtual environment activated.${NC}"
else
    echo -e "${GREEN}Already in virtual environment: $VIRTUAL_ENV${NC}"
fi

# Install package
echo -e "${YELLOW}Installing package...${NC}"
pip install -e .
echo -e "${GREEN}Package installed.${NC}"

# Create test directory
echo -e "${YELLOW}Creating test directory...${NC}"
mkdir -p $TEST_DIR
echo -e "${GREEN}Test directory created: $TEST_DIR${NC}"

# Check for camera
echo -e "${YELLOW}Checking for cameras...${NC}"
ls -la /dev/video* 2>/dev/null || echo -e "${YELLOW}No video devices found in /dev/video*${NC}"

# Test camera detection
echo -e "${YELLOW}Testing camera detection...${NC}"
echo -e "${BLUE}Running camera detection test for 5 seconds...${NC}"
timeout 5s python3 -m src.raspberry_pi_lsl_stream.camera_capture --no-preview --output-dir $TEST_DIR || true
echo -e "${GREEN}Camera detection test completed.${NC}"

# Test ntfy
echo -e "${YELLOW}Testing ntfy integration...${NC}"
echo -e "${BLUE}Sending test notification to ntfy topic: $NTFY_TOPIC${NC}"
curl -d "Test notification from $(hostname)" ntfy.sh/$NTFY_TOPIC
echo -e "${GREEN}Notification sent. Check if it was received.${NC}"

# Check installation of raspie-camera-service.sh
echo -e "${YELLOW}Checking service installation script...${NC}"
if [ -f "raspie-camera-service.sh" ]; then
    echo -e "${GREEN}Service installation script found.${NC}"
    echo -e "${YELLOW}To install as a service, run:${NC}"
    echo -e "${BLUE}sudo bash raspie-camera-service.sh${NC}"
else
    echo -e "${RED}Service installation script not found.${NC}"
fi

# Test complete
echo
echo -e "${BLUE}=========================================${NC}"
echo -e "${GREEN}          Testing completed!            ${NC}"
echo -e "${BLUE}=========================================${NC}"
echo
echo -e "${YELLOW}To start the camera capture manually:${NC}"
echo -e "${BLUE}python3 -m src.raspberry_pi_lsl_stream.camera_capture --save-video --output-dir recordings${NC}"
echo
echo -e "${YELLOW}To trigger recording via ntfy:${NC}"
echo -e "${BLUE}curl -d \"Start Recording\" ntfy.sh/$NTFY_TOPIC${NC}"
echo
echo -e "${YELLOW}To stop recording via ntfy:${NC}"
echo -e "${BLUE}curl -d \"Stop Recording\" ntfy.sh/$NTFY_TOPIC${NC}"
echo 