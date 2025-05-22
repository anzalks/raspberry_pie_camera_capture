#!/bin/bash
# Helper script to manage the Raspberry Pi Camera Service
# Author: Anzal (anzal.ks@gmail.com)

# Define colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get today's date for recordings directory
TODAY=$(date +%Y-%m-%d)
RECORDINGS_DIR="$HOME/raspberry_pie_camera_capture/recordings/$TODAY"

# Script and service paths
SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
SERVICE_NAME="rpi-camera.service"

# Function to check service status
check_status() {
    echo -e "${BLUE}Checking camera service status...${NC}"
    
    if systemctl is-active --quiet $SERVICE_NAME; then
        echo -e "${GREEN}● Camera service is running${NC}"
        echo -e "${YELLOW}Recordings are being saved to:${NC}"
        echo -e "  ${RECORDINGS_DIR}"
        echo -e "${YELLOW}Files will be named:${NC}"
        echo -e "  recording_YYYYMMDD_HHMMSS.mkv"
    else
        echo -e "${RED}● Camera service is not running${NC}"
    fi
    
    echo -e "\n${YELLOW}Detailed status:${NC}"
    systemctl status $SERVICE_NAME
}

# Function to show recent recordings
show_recordings() {
    echo -e "${BLUE}Recent recordings:${NC}"
    
    # Check if recordings directory exists
    if [ -d "$RECORDINGS_DIR" ]; then
        # Count recordings
        COUNT=$(find "$RECORDINGS_DIR" -name "*.mkv" | wc -l)
        TOTAL_SIZE=$(du -sh "$RECORDINGS_DIR" | cut -f1)
        
        echo -e "${GREEN}Found $COUNT recordings ($TOTAL_SIZE) in:${NC}"
        echo -e "  $RECORDINGS_DIR"
        echo -e "\n${YELLOW}Most recent recordings:${NC}"
        
        # List most recent recordings
        find "$RECORDINGS_DIR" -name "*.mkv" -type f -printf "%T@ %T+ %p\n" | \
            sort -nr | head -5 | cut -d' ' -f2- | \
            sed 's|'"$RECORDINGS_DIR/"'||g' | \
            awk '{print "  " $2 " (" $1 ")"}'
    else
        echo -e "${RED}No recordings found for today in:${NC}"
        echo -e "  $RECORDINGS_DIR"
        
        # Check for recordings from other days
        OTHER_DAYS=$(find "$ROOT_DIR/recordings" -type d -name "????-??-??" | wc -l)
        if [ $OTHER_DAYS -gt 0 ]; then
            echo -e "\n${YELLOW}Found recordings from other days:${NC}"
            find "$ROOT_DIR/recordings" -type d -name "????-??-??" | \
                sort -r | head -5 | \
                xargs -I{} bash -c 'echo "  {} ($(find "{}" -name "*.mkv" | wc -l) files)"'
        fi
    fi
}

# Main command processing
case "$1" in
    start)
        echo -e "${GREEN}Starting camera service...${NC}"
        sudo systemctl start $SERVICE_NAME
        sleep 2
        check_status
        ;;
    stop)
        echo -e "${YELLOW}Stopping camera service...${NC}"
        sudo systemctl stop $SERVICE_NAME
        sleep 2
        check_status
        ;;
    restart)
        echo -e "${YELLOW}Restarting camera service...${NC}"
        sudo systemctl restart $SERVICE_NAME
        sleep 2
        check_status
        ;;
    status)
        check_status
        ;;
    enable)
        echo -e "${GREEN}Enabling camera service to start at boot...${NC}"
        sudo systemctl enable $SERVICE_NAME
        ;;
    disable)
        echo -e "${YELLOW}Disabling camera service from starting at boot...${NC}"
        sudo systemctl disable $SERVICE_NAME
        ;;
    recordings)
        show_recordings
        ;;
    logs)
        echo -e "${BLUE}Showing logs:${NC}"
        sudo journalctl -u $SERVICE_NAME -f
        ;;
    install)
        echo -e "${GREEN}Installing camera service...${NC}"
        sudo cp "$ROOT_DIR/rpi-camera.service" /etc/systemd/system/
        sudo systemctl daemon-reload
        echo -e "${GREEN}Service installed. You can now enable and start it:${NC}"
        echo -e "  $0 enable"
        echo -e "  $0 start"
        ;;
    check)
        echo -e "${BLUE}Running camera environment check...${NC}"
        "$ROOT_DIR/bin/check_camera_env.py"
        ;;
    *)
        echo -e "${BLUE}Raspberry Pi Camera Service Management${NC}"
        echo -e "Usage: $0 {start|stop|restart|status|enable|disable|recordings|logs|install|check}"
        echo -e ""
        echo -e "  start       Start the camera service"
        echo -e "  stop        Stop the camera service"
        echo -e "  restart     Restart the camera service"
        echo -e "  status      Check service status"
        echo -e "  enable      Enable service to start at boot"
        echo -e "  disable     Disable service from starting at boot"
        echo -e "  recordings  Show recent recordings"
        echo -e "  logs        Show service logs"
        echo -e "  install     Install the service file"
        echo -e "  check       Run camera environment check"
        echo -e ""
        echo -e "Recordings are saved to: ${RECORDINGS_DIR}"
        exit 1
esac

exit 0 