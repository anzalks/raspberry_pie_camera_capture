#!/bin/bash
#
# Script to install the Raspberry Pi camera capture service
# This will set up the camera capture to start automatically on boot
#
# Author: Anzal
# Email: anzal.ks@gmail.com
# GitHub: https://github.com/anzalks/
#

# Exit on any error
set -e

# Check if running as root
if [ "$EUID" -ne 0 ]; then
  echo "Please run as root (use sudo)"
  exit 1
fi

# Define variables
SERVICE_NAME="raspie-camera"
PROJECT_DIR="$HOME/Downloads/raspberry_pie_camera_capture"
VENV_PATH="$PROJECT_DIR/.venv"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
LOG_DIR="/var/log/${SERVICE_NAME}"

# Create log directory
echo "Creating log directory at $LOG_DIR"
mkdir -p $LOG_DIR
chmod 755 $LOG_DIR

# Get current user
CURRENT_USER=$(logname || whoami)
echo "Setting up service for user: $CURRENT_USER"

# Create the systemd service file
echo "Creating systemd service file at $SERVICE_FILE"
cat > $SERVICE_FILE << EOL
[Unit]
Description=Raspberry Pi Camera Capture Service
After=network.target

[Service]
User=$CURRENT_USER
WorkingDirectory=$PROJECT_DIR
ExecStart=$VENV_PATH/bin/python -m src.raspberry_pi_lsl_stream.camera_capture --save-video --output-dir $PROJECT_DIR/recordings --ntfy-topic raspie-camera-test
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOL

# Create a manager script
MANAGER_SCRIPT="$PROJECT_DIR/raspie-service-manager.sh"
echo "Creating service manager script at $MANAGER_SCRIPT"
cat > $MANAGER_SCRIPT << EOL
#!/bin/bash
#
# Management script for Raspberry Pi Camera Capture service
#
# Author: Anzal
# Email: anzal.ks@gmail.com
# GitHub: https://github.com/anzalks/
#

SERVICE_NAME="raspie-camera"
NTFY_TOPIC="raspie-camera-test"

case "\$1" in
  start)
    echo "Starting $SERVICE_NAME service..."
    sudo systemctl start $SERVICE_NAME
    ;;
  stop)
    echo "Stopping $SERVICE_NAME service..."
    sudo systemctl stop $SERVICE_NAME
    ;;
  restart)
    echo "Restarting $SERVICE_NAME service..."
    sudo systemctl restart $SERVICE_NAME
    ;;
  status)
    echo "Status of $SERVICE_NAME service:"
    sudo systemctl status $SERVICE_NAME
    ;;
  logs)
    echo "Displaying logs for $SERVICE_NAME service:"
    sudo journalctl -u $SERVICE_NAME -f
    ;;
  trigger)
    echo "Sending start recording trigger..."
    curl -d "Start Recording" ntfy.sh/\$NTFY_TOPIC
    ;;
  stop-recording)
    echo "Sending stop recording trigger..."
    curl -d "Stop Recording" ntfy.sh/\$NTFY_TOPIC
    ;;
  enable)
    echo "Enabling $SERVICE_NAME service to start at boot..."
    sudo systemctl enable $SERVICE_NAME
    ;;
  disable)
    echo "Disabling $SERVICE_NAME service from starting at boot..."
    sudo systemctl disable $SERVICE_NAME
    ;;
  *)
    echo "Usage: \$0 {start|stop|restart|status|logs|trigger|stop-recording|enable|disable}"
    exit 1
    ;;
esac

exit 0
EOL

# Make script executable
chmod +x $MANAGER_SCRIPT

# Enable and start the service
echo "Enabling and starting the service"
systemctl daemon-reload
systemctl enable $SERVICE_NAME
systemctl start $SERVICE_NAME

# Show status
echo ""
echo "Service installed successfully!"
echo ""
echo "To manage the service, use:"
echo "  $MANAGER_SCRIPT start - Start the service"
echo "  $MANAGER_SCRIPT stop - Stop the service"
echo "  $MANAGER_SCRIPT status - Check service status"
echo "  $MANAGER_SCRIPT logs - View service logs"
echo "  $MANAGER_SCRIPT trigger - Start recording"
echo "  $MANAGER_SCRIPT stop-recording - Stop recording"
echo ""
echo "Service will start automatically on boot." 