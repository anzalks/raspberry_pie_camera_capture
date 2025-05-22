#!/bin/bash
# Script to attach to the IMX296 camera tmux session to view status
# Author: Anzal KS <anzal.ks@gmail.com>

# Define colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== IMX296 Global Shutter Camera Status Viewer ===${NC}"
echo

# Check if tmux is installed
if ! command -v tmux >/dev/null 2>&1; then
    echo -e "${RED}Error: tmux is not installed.${NC}"
    echo "Please install tmux with: sudo apt install tmux"
    exit 1
fi

# Check if the imx296-camera session exists
if ! tmux has-session -t imx296-camera 2>/dev/null; then
    echo -e "${YELLOW}No camera session found.${NC}"
    echo "The camera service might not be running."
    echo
    echo "To start the service manually:"
    echo "  sudo systemctl start imx296-camera.service"
    echo
    echo "To check service status:"
    echo "  sudo systemctl status imx296-camera.service"
    exit 1
fi

# Attach to the tmux session
echo -e "${GREEN}Attaching to camera status session...${NC}"
echo -e "${YELLOW}(Press Ctrl+B then D to detach without stopping the camera)${NC}"
echo

exec tmux attach-session -t imx296-camera 