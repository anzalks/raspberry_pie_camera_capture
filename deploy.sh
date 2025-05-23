#!/bin/bash
# Deploy script for IMX296 camera fixes
# By: Anzal KS <anzal.ks@gmail.com>

# Default values
PI_USER="pi"
PI_HOST=""
PI_PATH="/home/dawg/Downloads/insha_rpie/raspberry_pie_camera_capture"
REMOTE_INSTALL=false

# Display help
show_help() {
    echo "Usage: $0 [OPTIONS]"
    echo "Deploy fixes for IMX296 camera to a Raspberry Pi"
    echo ""
    echo "Options:"
    echo "  -h, --host HOST     Specify the remote Raspberry Pi hostname/IP"
    echo "  -u, --user USER     Specify the SSH username (default: pi)"
    echo "  -p, --path PATH     Remote path where the code is located"
    echo "                      (default: /home/dawg/Downloads/insha_rpie/raspberry_pie_camera_capture)"
    echo "  -i, --install       Run install.sh on the remote machine"
    echo "  --help              Display this help message"
    echo ""
    echo "Example:"
    echo "  $0 -h 192.168.1.100 -u pi -i"
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    key="$1"
    case $key in
        -h|--host)
            PI_HOST="$2"
            shift
            shift
            ;;
        -u|--user)
            PI_USER="$2"
            shift
            shift
            ;;
        -p|--path)
            PI_PATH="$2"
            shift
            shift
            ;;
        -i|--install)
            REMOTE_INSTALL=true
            shift
            ;;
        --help)
            show_help
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Check if host is specified
if [ -z "$PI_HOST" ]; then
    echo "Error: Raspberry Pi hostname/IP not specified."
    show_help
    exit 1
fi

# Create a temporary directory for bundling
TEMP_DIR=$(mktemp -d)
echo "Creating deployment package in $TEMP_DIR..."

# Copy necessary files
mkdir -p "$TEMP_DIR/bin"
mkdir -p "$TEMP_DIR/src/imx296_gs_capture"

# Copy key files
cp install.sh "$TEMP_DIR/"
cp config.yaml "$TEMP_DIR/"
cp README.md "$TEMP_DIR/"
cp bin/fix_camera_issues.sh "$TEMP_DIR/bin/"

# Copy main fix script
cat > "$TEMP_DIR/fix_all_issues.sh" << 'EOF'
#!/bin/bash
# Fix all IMX296 camera issues in one go
# By: Anzal KS <anzal.ks@gmail.com>

echo "Running comprehensive fix for IMX296 camera..."

# Create necessary directories
sudo mkdir -p /home/dawg/recordings
sudo chmod 777 /home/dawg/recordings

sudo mkdir -p /var/log/imx296-camera
sudo chmod 777 /var/log/imx296-camera

# Fix LSL numeric values
python3 -c '
import os
import re
path = "/opt/imx296-camera/src/imx296_gs_capture/imx296_capture.py"
if os.path.exists(path):
    with open(path, "r") as f:
        content = f.read()
    # Ensure lsl_has_string_support is False
    content = re.sub(r"lsl_has_string_support\s*=\s*True", "lsl_has_string_support = False", content)
    # Add vsync 0 to ffmpeg command if needed
    if "-c:v copy" in content and not "-vsync 0" in content:
        content = re.sub(r"("-c:v", "copy",)", r"\1\n        "-vsync", "0",", content)
    with open(path, "w") as f:
        f.write(content)
    print("✓ Fixed IMX296 camera code")
'

# Fix config file
if [ -f "/opt/imx296-camera/config.yaml" ]; then
    sudo cp config.yaml /opt/imx296-camera/
    echo "✓ Updated config file"
fi

# Restart the service
sudo systemctl restart imx296-camera
echo "✓ Restarted imx296-camera service"

# Check status
echo "Service status:"
sudo systemctl status imx296-camera | head -20

echo "Done! To check logs: sudo journalctl -u imx296-camera -f"
EOF

chmod +x "$TEMP_DIR/fix_all_issues.sh"

# Create the bundle
BUNDLE_FILE="imx296_fixes.tar.gz"
tar -czf "$BUNDLE_FILE" -C "$TEMP_DIR" .
echo "Created deployment package: $BUNDLE_FILE"

# Deploy to Raspberry Pi
echo "Deploying to $PI_USER@$PI_HOST..."
scp "$BUNDLE_FILE" "$PI_USER@$PI_HOST:/tmp/"

# Extract and run on remote machine
ssh "$PI_USER@$PI_HOST" "mkdir -p $PI_PATH && tar -xzf /tmp/$BUNDLE_FILE -C $PI_PATH && cd $PI_PATH && chmod +x *.sh bin/*.sh && ./fix_all_issues.sh"

if [ "$REMOTE_INSTALL" = true ]; then
    echo "Running installation on remote machine..."
    ssh "$PI_USER@$PI_HOST" "cd $PI_PATH && sudo ./install.sh"
fi

# Clean up
rm -rf "$TEMP_DIR" "$BUNDLE_FILE"
echo "Deployment completed!" 