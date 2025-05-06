#!/bin/bash
# Setup script to install the camera capture service to start on boot

# Define colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Ensure script is run as root
if [ "$(id -u)" -ne 0 ]; then
    echo -e "${RED}This script must be run as root (use sudo).${NC}"
    exit 1
fi

# Get the current username (the user running sudo)
if [ -n "$SUDO_USER" ]; then
    CURRENT_USER="$SUDO_USER"
else
    CURRENT_USER="$(whoami)"
fi

echo -e "${GREEN}Setting up automatic camera service for user: ${YELLOW}$CURRENT_USER${NC}"

# Get absolute path to the project
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo -e "${GREEN}Project directory: ${YELLOW}$PROJECT_DIR${NC}"

# Path to the virtual environment
VENV_PATH="$PROJECT_DIR/.venv"

# Check if virtual environment exists
if [ ! -d "$VENV_PATH" ]; then
    echo -e "${RED}Virtual environment not found at $VENV_PATH${NC}"
    echo -e "${YELLOW}Please run the setup_pi.sh script first to setup the environment.${NC}"
    exit 1
fi

# Get the absolute path to the Python binary in the virtual environment
PYTHON_BIN="$VENV_PATH/bin/python"
if [ ! -f "$PYTHON_BIN" ]; then
    echo -e "${RED}Python binary not found in virtual environment.${NC}"
    exit 1
fi

# Create the systemd service file
echo -e "${GREEN}Creating systemd service file...${NC}"

# Service file path
SERVICE_FILE="/etc/systemd/system/raspie-capture.service"

# Create the file with appropriate permissions
cat << EOF > "$SERVICE_FILE"
[Unit]
Description=Raspberry Pi Audio/Video Capture Service
After=network.target

[Service]
Type=simple
User=$CURRENT_USER
WorkingDirectory=$PROJECT_DIR
ExecStart=$VENV_PATH/bin/rpi-lsl-stream --width 400 --height 400 --fps 100 --codec h264 --bitrate 4000 --quality-preset ultrafast --ntfy-topic raspie_trigger --buffer-size 20 --enable-audio --sample-rate 48000 --bit-depth 16 --channels 1
Environment="PATH=$VENV_PATH/bin:/usr/local/bin:/usr/bin:/bin"
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
EOF

# Set appropriate permissions
chmod 644 "$SERVICE_FILE"

# Enable the service
echo -e "${GREEN}Enabling the service...${NC}"
systemctl daemon-reload
systemctl enable raspie-capture.service

# Create a convenient script to manage the service
MANAGEMENT_SCRIPT="$PROJECT_DIR/raspie-service.sh"

cat << 'EOF' > "$MANAGEMENT_SCRIPT"
#!/bin/bash

# Define colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Function to check if the service is running
check_status() {
    status=$(systemctl is-active raspie-capture.service)
    if [ "$status" = "active" ]; then
        echo -e "${GREEN}Capture service is running.${NC}"
    else
        echo -e "${RED}Capture service is not running.${NC}"
    fi
    
    # Show detailed status
    echo -e "${YELLOW}Detailed status:${NC}"
    systemctl status raspie-capture.service
}

# Main command processing
case "$1" in
    start)
        echo -e "${GREEN}Starting capture service...${NC}"
        sudo systemctl start raspie-capture.service
        check_status
        ;;
    stop)
        echo -e "${YELLOW}Stopping capture service...${NC}"
        sudo systemctl stop raspie-capture.service
        check_status
        ;;
    restart)
        echo -e "${YELLOW}Restarting capture service...${NC}"
        sudo systemctl restart raspie-capture.service
        check_status
        ;;
    status)
        check_status
        ;;
    logs)
        echo -e "${GREEN}Showing logs:${NC}"
        sudo journalctl -u raspie-capture.service -f
        ;;
    enable)
        echo -e "${GREEN}Enabling capture service to start on boot...${NC}"
        sudo systemctl enable raspie-capture.service
        echo -e "${GREEN}Service will now start automatically on boot.${NC}"
        ;;
    disable)
        echo -e "${YELLOW}Disabling capture service from starting on boot...${NC}"
        sudo systemctl disable raspie-capture.service
        echo -e "${YELLOW}Service will no longer start automatically on boot.${NC}"
        ;;
    trigger)
        echo -e "${GREEN}Sending start trigger notification...${NC}"
        ntfy_topic="raspie_trigger"
        curl -d "start recording" ntfy.sh/$ntfy_topic
        echo -e "${GREEN}Trigger sent. Audio/video capture should start recording.${NC}"
        ;;
    stop-recording)
        echo -e "${YELLOW}Sending stop recording notification...${NC}"
        ntfy_topic="raspie_trigger"
        curl -d "stop recording" ntfy.sh/$ntfy_topic
        echo -e "${YELLOW}Stop signal sent. Audio/video capture should stop recording.${NC}"
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|logs|enable|disable|trigger|stop-recording}"
        exit 1
        ;;
esac

exit 0
EOF

# Make the management script executable
chmod +x "$MANAGEMENT_SCRIPT"

# Provide user information
echo -e "${GREEN}=============================================================${NC}"
echo -e "${GREEN}Audio/Video capture service has been installed and enabled!${NC}"
echo -e "${GREEN}The service will start automatically on next boot.${NC}"
echo -e ""
echo -e "${YELLOW}To start the service now:${NC}"
echo -e "    sudo systemctl start raspie-capture.service"
echo -e ""
echo -e "${YELLOW}To control the service, use the management script:${NC}"
echo -e "    $MANAGEMENT_SCRIPT start      - Start the capture service"
echo -e "    $MANAGEMENT_SCRIPT stop       - Stop the capture service"
echo -e "    $MANAGEMENT_SCRIPT restart    - Restart the capture service"
echo -e "    $MANAGEMENT_SCRIPT status     - Check service status"
echo -e "    $MANAGEMENT_SCRIPT logs       - View service logs"
echo -e "    $MANAGEMENT_SCRIPT trigger    - Send start recording notification"
echo -e "    $MANAGEMENT_SCRIPT stop-recording - Send stop recording notification"
echo -e ""
echo -e "${YELLOW}To trigger recording from any device:${NC}"
echo -e "    curl -d \"start recording\" ntfy.sh/raspie_trigger"
echo -e "${YELLOW}To stop recording from any device:${NC}"
echo -e "    curl -d \"stop recording\" ntfy.sh/raspie_trigger"
echo -e "${GREEN}=============================================================${NC}"
EOF 