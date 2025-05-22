#!/bin/bash
# Script to view IMX296 camera service status and logs
# Author: Anzal KS <anzal.ks@gmail.com>

# Define colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== IMX296 Global Shutter Camera Status Viewer ===${NC}"
echo

# Check if the service is installed
if [ ! -f "/etc/systemd/system/imx296-camera.service" ]; then
    echo -e "${RED}Error: IMX296 camera service is not installed.${NC}"
    echo "Please run: sudo bin/install.sh"
    exit 1
fi

# Check service status
echo -e "${YELLOW}Checking service status...${NC}"
sudo systemctl status imx296-camera.service

# Ask user what they want to do
echo
echo -e "${YELLOW}Options:${NC}"
echo "1. View live logs"
echo "2. Start service"
echo "3. Stop service"
echo "4. Restart service"
echo "5. Run manually (not as service)"
echo "6. Test camera directly"
echo "7. Exit"
echo

read -p "Enter your choice [1-7]: " choice

case $choice in
    1)
        echo -e "${YELLOW}Viewing live logs (Ctrl+C to exit)...${NC}"
        sudo journalctl -u imx296-camera.service -f
        ;;
    2)
        echo -e "${YELLOW}Starting service...${NC}"
        sudo systemctl start imx296-camera.service
        sleep 2
        sudo systemctl status imx296-camera.service
        ;;
    3)
        echo -e "${YELLOW}Stopping service...${NC}"
        sudo systemctl stop imx296-camera.service
        sleep 2
        sudo systemctl status imx296-camera.service
        ;;
    4)
        echo -e "${YELLOW}Restarting service...${NC}"
        sudo systemctl restart imx296-camera.service
        sleep 2
        sudo systemctl status imx296-camera.service
        ;;
    5)
        echo -e "${YELLOW}Running camera script manually with full debug output...${NC}"
        # Set default directory and run script
        script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
        project_root="$(dirname "$script_dir")"
        
        cd "$project_root"
        source .venv/bin/activate
        PYTHONPATH="$project_root" python3 -u bin/run_imx296_capture.py
        ;;
    6)
        echo -e "${YELLOW}Testing camera directly with libcamera-vid...${NC}"
        # Test if libcamera-vid works directly
        echo -e "${GREEN}1. Testing libcamera-hello --list-cameras${NC}"
        libcamera-hello --list-cameras
        
        echo
        echo -e "${GREEN}2. Testing simple 5-second capture to file...${NC}"
        echo "This will record a 5-second test video to /tmp/test.h264"
        read -p "Press Enter to continue..."
        
        libcamera-vid --width 400 --height 400 --framerate 100 -t 5000 -o /tmp/test.h264
        
        echo
        echo -e "${GREEN}3. File information:${NC}"
        ls -la /tmp/test.h264
        
        echo
        echo -e "${GREEN}4. Testing streaming output...${NC}"
        echo "This will display stdout/stderr output from libcamera-vid for 3 seconds"
        read -p "Press Enter to continue..."
        
        # Run with timeout to capture output
        timeout 3 libcamera-vid --width 400 --height 400 --framerate 100 -o - | hexdump -C | head -10
        
        echo
        echo -e "${GREEN}Tests completed.${NC}"
        ;;
    7|*)
        echo "Exiting."
        exit 0
        ;;
esac

exit 0 