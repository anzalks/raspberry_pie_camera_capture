#!/bin/bash
# Simple launcher for the IMX296 Camera Dashboard
# Author: Anzal KS <anzal.ks@gmail.com>

# Get the directory of this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Check if service is running
if ! systemctl is-active --quiet imx296-camera.service; then
    echo "IMX296 camera service is not running."
    read -p "Would you like to start it now? (y/n): " choice
    if [[ "$choice" =~ ^[Yy]$ ]]; then
        echo "Starting camera service..."
        sudo systemctl start imx296-camera.service
        sleep 2
    fi
fi

# Launch the dashboard directly
exec "$SCRIPT_DIR/view-camera-status.sh" "$@" 