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
    
    # Check if the service is installed
    if [ -f "/etc/systemd/system/imx296-camera.service" ]; then
        # Check service status
        echo -e "${YELLOW}Checking service status...${NC}"
        sudo systemctl status imx296-camera.service
        
        echo
        echo "To start the service manually:"
        echo "  sudo systemctl start imx296-camera.service"
        echo
        echo "To check detailed logs:"
        echo "  sudo journalctl -u imx296-camera.service -f"
    else
        echo -e "${RED}Service not installed.${NC}"
        echo "Please run: sudo bin/install.sh"
    fi
    
    # Offer to start the service or run manually
    echo
    read -p "Would you like to (s)tart the service, (r)un manually, or (q)uit? [s/r/q]: " choice
    
    case $choice in
        s|S)
            echo -e "${YELLOW}Starting IMX296 camera service...${NC}"
            sudo systemctl start imx296-camera.service
            echo "Waiting for service to start..."
            sleep 5
            
            # Check if tmux session exists now
            if tmux has-session -t imx296-camera 2>/dev/null; then
                echo -e "${GREEN}Service started successfully. Attaching to session...${NC}"
                exec tmux attach-session -t imx296-camera
            else
                echo -e "${RED}Service started but no tmux session found. Check logs with:${NC}"
                echo "  sudo journalctl -u imx296-camera.service -f"
                exit 1
            fi
            ;;
        r|R)
            echo -e "${YELLOW}Running camera script manually...${NC}"
            # Create a new tmux session
            tmux new-session -d -s imx296-camera
            
            # Set default directory and run script
            script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
            project_root="$(dirname "$script_dir")"
            
            tmux send-keys -t imx296-camera "cd $project_root && sudo python3 bin/run_imx296_capture.py --sudo" C-m
            
            # Attach to session
            exec tmux attach-session -t imx296-camera
            ;;
        *)
            echo "Exiting."
            exit 0
            ;;
    esac
    
    exit 1
fi

# Attach to the tmux session
echo -e "${GREEN}Attaching to camera status session...${NC}"
echo -e "${YELLOW}(Press Ctrl+B then D to detach without stopping the camera)${NC}"
echo

exec tmux attach-session -t imx296-camera 