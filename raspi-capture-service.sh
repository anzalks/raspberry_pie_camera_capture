#!/bin/bash
# Installation script for Raspie Capture auto-start service
# This script creates a systemd service for starting Raspie Capture on boot
# with rolling buffer mode and ntfy.sh-based start/stop control

# Root check
if [ "$(id -u)" -ne 0 ]; then
    echo "This script must be run as root. Please use sudo."
    exit 1
fi

# Get the current user (the one who called sudo)
CURRENT_USER=${SUDO_USER:-$USER}
echo "Setting up service for user: $CURRENT_USER"

# Get the path to the script
INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "Installation directory: $INSTALL_DIR"

# Create the systemd service file
cat > /etc/systemd/system/raspie-capture.service << EOF
[Unit]
Description=Raspie Capture Service
After=network.target

[Service]
Type=simple
User=$CURRENT_USER
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/.venv/bin/python -m raspberry_pi_lsl_stream.cli --enable-audio --use-buffer --buffer-size 20 --ntfy-topic raspie_trigger --threaded-writer --codec h264
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
EOF

echo "Created systemd service file at /etc/systemd/system/raspie-capture.service"

# Create management script
cat > $INSTALL_DIR/raspie-service.sh << EOF
#!/bin/bash
# Management script for the Raspie Capture Service

# Define the ntfy topic
NTFY_TOPIC="raspie_trigger"

case "\$1" in
    start)
        echo "Starting Raspie Capture service..."
        sudo systemctl start raspie-capture.service
        ;;
    stop)
        echo "Stopping Raspie Capture service..."
        sudo systemctl stop raspie-capture.service
        ;;
    status)
        echo "Checking Raspie Capture service status..."
        sudo systemctl status raspie-capture.service
        ;;
    enable)
        echo "Enabling Raspie Capture service to start at boot..."
        sudo systemctl enable raspie-capture.service
        ;;
    disable)
        echo "Disabling Raspie Capture service from starting at boot..."
        sudo systemctl disable raspie-capture.service
        ;;
    restart)
        echo "Restarting Raspie Capture service..."
        sudo systemctl restart raspie-capture.service
        ;;
    logs)
        echo "Viewing Raspie Capture service logs..."
        sudo journalctl -fu raspie-capture.service
        ;;
    trigger)
        echo "Sending trigger to start recording..."
        curl -d "start recording" ntfy.sh/\$NTFY_TOPIC
        echo "Recording started."
        ;;
    stop-recording)
        echo "Sending trigger to stop recording..."
        curl -d "stop recording" ntfy.sh/\$NTFY_TOPIC
        echo "Recording stopped."
        ;;
    *)
        echo "Usage: \$0 {start|stop|status|enable|disable|restart|logs|trigger|stop-recording}"
        exit 1
        ;;
esac

exit 0
EOF

# Make the management script executable
chmod +x $INSTALL_DIR/raspie-service.sh
echo "Created management script at $INSTALL_DIR/raspie-service.sh"

# Reload systemd and enable the service
systemctl daemon-reload
systemctl enable raspie-capture.service

echo "Raspie Capture service has been installed and enabled."
echo "The service will start automatically at boot."
echo "You can control it using: ./raspie-service.sh {start|stop|status|logs|trigger|stop-recording}"
echo "To start recording: curl -d \"start recording\" ntfy.sh/raspie_trigger"
echo "To stop recording: curl -d \"stop recording\" ntfy.sh/raspie_trigger"
echo "To start the service now, run: sudo systemctl start raspie-capture.service" 