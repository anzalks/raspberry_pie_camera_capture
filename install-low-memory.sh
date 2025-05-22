#!/bin/bash
# Low memory installation script for Raspberry Pi Camera Capture
# This script breaks down the installation into smaller steps to avoid memory issues

set -e  # Exit on error

echo "=========================================================="
echo "Raspberry Pi Camera Capture - Low Memory Installation"
echo "=========================================================="

# Function to check if we're running on a Raspberry Pi
check_raspberry_pi() {
    if [ -f /proc/device-tree/model ]; then
        model=$(cat /proc/device-tree/model)
        if [[ $model == *"Raspberry Pi"* ]]; then
            echo "Detected Raspberry Pi: $model"
            return 0
        fi
    fi
    echo "Warning: This doesn't appear to be a Raspberry Pi."
    echo "This software is designed for Raspberry Pi."
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Installation aborted."
        exit 1
    fi
    return 1
}

# Install system dependencies one by one to reduce memory usage
install_system_dependencies() {
    echo "Installing system dependencies..."
    
    # Update package lists
    sudo apt-get update
    
    # Install each package separately to minimize memory usage
    for pkg in python3-dev python3-venv python3-pip libopencv-dev media-ctl v4l-utils libcamera-dev libcamera-apps; do
        echo "Installing $pkg..."
        sudo apt-get install -y $pkg
        # Sleep to allow system to recover between installations
        sleep 2
    done
    
    # Check for picamera2
    if ! python3 -c "import picamera2" &>/dev/null; then
        echo "Installing picamera2..."
        sudo apt-get install -y python3-picamera2
    fi
}

# Create virtual environment if it doesn't exist
setup_virtual_env() {
    echo "Setting up Python virtual environment..."
    
    if [ ! -d ".venv" ]; then
        python3 -m venv .venv
        echo "Virtual environment created."
    else
        echo "Virtual environment already exists."
    fi
    
    # Activate virtual environment
    source .venv/bin/activate
    
    # Upgrade basic packages - smaller memory footprint
    pip install --upgrade pip
}

# Install Python dependencies in batches to reduce memory usage
install_python_dependencies() {
    echo "Installing Python dependencies in small batches..."
    
    # Activate virtual environment if not already activated
    if [[ "$VIRTUAL_ENV" == "" ]]; then
        source .venv/bin/activate
    fi
    
    # Basic dependencies
    echo "Installing basic dependencies..."
    pip install pyyaml requests
    sleep 2
    
    # Core dependencies - batch 1
    echo "Installing core dependencies (batch 1)..."
    pip install numpy
    sleep 2
    
    # Core dependencies - batch 2
    echo "Installing core dependencies (batch 2)..."
    pip install opencv-python-headless
    sleep 2
    
    # Core dependencies - batch 3
    echo "Installing core dependencies (batch 3)..."
    pip install pylsl
    sleep 2
    
    # Additional dependencies - batch 4
    echo "Installing additional dependencies..."
    pip install ntfy psutil
    sleep 2
}

# Install the package in development mode
install_package() {
    echo "Installing package in development mode..."
    
    # Activate virtual environment if not already activated
    if [[ "$VIRTUAL_ENV" == "" ]]; then
        source .venv/bin/activate
    fi
    
    # Install in development mode with minimal build
    pip install -e . --no-build-isolation
}

# Create systemd service for auto-start
setup_service() {
    echo "Setting up systemd service for auto-start..."
    
    # Create service file
    SERVICE_FILE="raspberry-pi-camera.service"
    
    # Check if service file already exists
    if [ -f "/etc/systemd/system/$SERVICE_FILE" ]; then
        echo "Service file already exists. Skipping creation."
    else
        # Get current user
        CURRENT_USER=$(whoami)
        INSTALL_DIR=$(pwd)
        
        # Create service file content
        cat > "$SERVICE_FILE" << EOF
[Unit]
Description=Raspberry Pi Camera LSL Stream Service
After=network.target

[Service]
User=$CURRENT_USER
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/.venv/bin/python -m raspberry_pi_lsl_stream
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
EOF
        
        # Move service file to system directory
        sudo mv "$SERVICE_FILE" "/etc/systemd/system/"
        
        # Reload systemd
        sudo systemctl daemon-reload
        
        echo "Service file created at /etc/systemd/system/$SERVICE_FILE"
        echo "To enable the service to start at boot: sudo systemctl enable $SERVICE_FILE"
        echo "To start the service manually: sudo systemctl start $SERVICE_FILE"
    fi
}

# Main installation process
main() {
    check_raspberry_pi
    
    install_system_dependencies
    
    setup_virtual_env
    
    install_python_dependencies
    
    install_package
    
    setup_service
    
    echo "=========================================================="
    echo "Installation complete!"
    echo "To run the application:"
    echo "  1. Activate the virtual environment: source .venv/bin/activate"
    echo "  2. Run the application: python -m raspberry_pi_lsl_stream"
    echo "=========================================================="
}

# Run the main function
main 