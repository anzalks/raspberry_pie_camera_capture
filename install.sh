#!/bin/bash
# IMX296 Camera Service Installer
# By: Anzal KS <anzal.ks@gmail.com>
set -e

# Identify OS and architecture
OS=$(uname -s)
ARCH=$(uname -m)
echo "Detected OS: $OS, Architecture: $ARCH"

# Check Python version
PYTHON_VERSION=$(python3 --version)
echo "Detected $PYTHON_VERSION"

# Create and organize the bin directory
if [ ! -d "bin" ]; then
    mkdir -p bin
    echo "Created bin directory"
fi

# Function to check if requirements are installed
check_requirements() {
    echo "Checking requirements..."
    
    # Check for libcamera
    if ! command -v libcamera-vid &> /dev/null; then
        echo "ERROR: libcamera-vid not found. Please install libcamera-apps package first."
        return 1
    fi
    
    # Check for ffmpeg
    if ! command -v ffmpeg &> /dev/null; then
        echo "ERROR: ffmpeg not found. Please install ffmpeg package first."
        return 1
    fi
    
    # Check for pip
    if ! command -v pip3 &> /dev/null; then
        echo "ERROR: pip3 not found. Please install python3-pip package first."
        return 1
    fi
    
    echo "✓ All required packages are installed."
    return 0
}

# Function to install Python packages
install_python_packages() {
    echo "Installing Python packages..."
    pip3 install --upgrade pip
    pip3 install pylsl numpy pyyaml pillow opencv-python flask
    echo "✓ Python packages installed."
}

# Function to create systemd service
create_service() {
    echo "Setting up systemd service..."
    
    # Create the service file
    sudo bash -c "cat > /etc/systemd/system/imx296-camera.service << EOF
[Unit]
Description=IMX296 Global Shutter Camera Service
After=network.target
StartLimitIntervalSec=0

[Service]
Type=simple
Restart=always
RestartSec=5
User=root
WorkingDirectory=$(pwd)
ExecStart=/usr/bin/python3 -m src.imx296_gs_capture.imx296_capture
StandardOutput=append:/var/log/imx296-camera/imx296_capture.log
StandardError=append:/var/log/imx296-camera/imx296_capture.log

[Install]
WantedBy=multi-user.target
EOF"
    
    # Create log directory
    sudo mkdir -p /var/log/imx296-camera
    sudo chmod 777 /var/log/imx296-camera
    
    # Create recordings directory
    sudo mkdir -p /home/dawg/recordings
    sudo chmod 777 /home/dawg/recordings
    
    # Create config directory in /opt
    sudo mkdir -p /opt/imx296-camera
    sudo cp -r ./* /opt/imx296-camera/
    sudo chmod -R 755 /opt/imx296-camera
    
    # Enable and restart service
    sudo systemctl daemon-reload
    sudo systemctl enable imx296-camera.service
    sudo systemctl restart imx296-camera.service
    
    echo "✓ System service installed."
}

# Function to create default configuration
create_config() {
    echo "Creating default configuration..."
    
    # Create config file with default values
    cat > config.yaml << EOF
# IMX296 Camera Configuration
camera:
  width: 400
  height: 400
  fps: 100
  format: "SBGGR10_1X10"
  libcamera_path: "/usr/bin/libcamera-vid"
  ffmpeg_path: "/usr/bin/ffmpeg"

recording:
  enabled: true
  output_dir: "/home/dawg/recordings"
  codec: "mjpeg"
  format: "mkv"
  compression_level: 5
  
lsl:
  enabled: true
  stream_name: "IMX296Camera"
  stream_type: "VideoEvents"
  stream_id: "imx296_01"
  
web:
  enabled: true
  host: "0.0.0.0"
  port: 8080
  update_interval_ms: 500
EOF
    
    echo "✓ Default configuration created."
}

# Function to fix common issues
fix_common_issues() {
    echo "Fixing common issues..."
    
    # Add fixes for LSL numeric values
    cat > /tmp/fix_lsl_numeric.py << 'EOF'
#!/usr/bin/env python3
import sys
import os
import re

def fix_lsl_in_file(filepath):
    """Fix LSL string values in the IMX296 capture code."""
    print(f"Examining file: {filepath}")
    
    if not os.path.exists(filepath):
        print(f"Error: File not found: {filepath}")
        return False
    
    with open(filepath, 'r') as f:
        content = f.read()
    
    # Check if lsl_has_string_support is True anywhere
    if re.search(r'lsl_has_string_support\s*=\s*True', content):
        print("Found lsl_has_string_support = True, fixing to False")
        content = re.sub(r'lsl_has_string_support\s*=\s*True', 'lsl_has_string_support = False', content)
        modified = True
    else:
        modified = False
    
    # Find instances of string values in LSL samples
    if "get_trigger_source_string" in content and "if lsl_has_string_support:" in content:
        print("Found string values in LSL sample pushing, fixing...")
        
        # Fix the problematic section where trigger_source might be a string
        string_pattern = re.compile(r'if lsl_has_string_support:.*?else:.*?sample = \[(.*?)\]', re.DOTALL)
        match = string_pattern.search(content)
        
        if match:
            # Replace the entire conditional block with just the numeric version
            fixed_block = (
                "# Always use numeric values for LSL\n"
                "                    sample = [float(current_time), float(recording_event.is_set()), -1.0, float(last_trigger_source)]"
            )
            content = re.sub(r'if lsl_has_string_support:.*?else:.*?# All numeric version', fixed_block, content, flags=re.DOTALL)
            modified = True
    
    # Look for any place where string values might be used
    if "trigger_str" in content and "lsl_outlet.push_sample" in content:
        # Find and fix any places where trigger_str might be used in sample data
        triggers_pattern = re.compile(r'sample = \[(.*?)trigger_str(.*?)\]')
        if triggers_pattern.search(content):
            print("Found potential string in LSL sample, fixing...")
            # Replace with numeric version
            content = re.sub(r'sample = \[(.*?)trigger_str(.*?)\]', 
                            r'sample = [\1float(last_trigger_source)\2]', 
                            content)
            modified = True
    
    if modified:
        # Backup the original file
        backup_path = filepath + ".bak"
        with open(backup_path, 'w') as f:
            f.write(content)
        print(f"Created backup at {backup_path}")
        
        # Write the fixed content
        with open(filepath, 'w') as f:
            f.write(content)
        print("✓ LSL numeric values fixed in file")
        return True
    else:
        print("No LSL string issues found in the file")
        return False

# Find all possible imx296_capture.py files
for path in [
    "./src/imx296_gs_capture/imx296_capture.py"
]:
    if os.path.exists(path):
        fix_lsl_in_file(path)
EOF

    # Add fixes for empty recording files
    cat > /tmp/fix_empty_recordings.py << 'EOF'
#!/usr/bin/env python3
import sys
import os
import re

def fix_recording_in_file(filepath):
    """Fix empty recording files issue in the IMX296 capture code."""
    print(f"Examining file for recording issues: {filepath}")
    
    if not os.path.exists(filepath):
        print(f"Error: File not found: {filepath}")
        return False
    
    with open(filepath, 'r') as f:
        content = f.read()
    
    modified = False
    
    # Check for ffmpeg command construction
    ffmpeg_section = re.search(r'cmd = \[(.*?)ffmpeg_path(.*?)]', content, re.DOTALL)
    if ffmpeg_section:
        # Ensure the ffmpeg command is correctly formed
        if "-c:v copy" in content and not "-vsync 0" in content:
            print("Found ffmpeg command without -vsync 0, adding it...")
            # Add -vsync 0 after the copy command
            content = re.sub(
                r'("-c:v", "copy",)',
                r'\1\n        "-vsync", "0",  # Add frame sync option to prevent empty files',
                content
            )
            modified = True
    
    # Ensure output directory exists and has correct permissions
    if 'output_dir = config' in content:
        # Add code to ensure output directory exists
        dir_check_code = """
        # Ensure output directory exists with proper permissions
        try:
            output_dir = os.path.abspath(os.path.expanduser(output_dir))
            os.makedirs(output_dir, exist_ok=True)
            os.chmod(output_dir, 0o777)  # Full permissions
            logger.info(f"Ensured output directory exists with permissions: {output_dir}")
        except Exception as e:
            logger.error(f"Error ensuring output directory: {e}")
            # Try using /tmp as fallback
            output_dir = "/tmp"
            logger.warning(f"Using fallback directory: {output_dir}")
        """
        
        # Find where to insert the code
        dir_setup_match = re.search(r'output_dir = .*?\n', content)
        if dir_setup_match and dir_check_code not in content:
            print("Adding directory permission check code...")
            insert_pos = dir_setup_match.end()
            content = content[:insert_pos] + dir_check_code + content[insert_pos:]
            modified = True
    
    # Fix the output file creation to ensure it can be written by ffmpeg
    if 'output_file = ' in content and "os.open" not in content:
        # Add file creation code with proper permissions
        file_create_code = """
        # Create empty file with proper permissions first
        try:
            # Use low-level os.open to ensure file exists with correct permissions
            fd = os.open(output_file, os.O_CREAT | os.O_WRONLY, 0o666)
            os.close(fd)
            logger.info(f"Created empty file with permissions: {output_file}")
        except Exception as e:
            logger.error(f"Error creating output file: {e}")
            # Try alternative location
            output_file = f"/tmp/recording_{timestamp}.{format_ext}"
            logger.warning(f"Using alternative path: {output_file}")
            try:
                fd = os.open(output_file, os.O_CREAT | os.O_WRONLY, 0o666)
                os.close(fd)
            except Exception as e2:
                logger.error(f"Error creating alternative file: {e2}")
        """
        
        output_file_match = re.search(r'output_file = .*?\n', content)
        if output_file_match and file_create_code not in content:
            print("Adding file creation with proper permissions...")
            insert_pos = output_file_match.end()
            content = content[:insert_pos] + file_create_code + content[insert_pos:]
            modified = True
    
    if modified:
        # Backup the original file
        backup_path = filepath + ".rec_fix.bak"
        with open(backup_path, 'w') as f:
            f.write(content)
        print(f"Created backup at {backup_path}")
        
        # Write the fixed content
        with open(filepath, 'w') as f:
            f.write(content)
        print("✓ Empty recording files issue fixed")
        return True
    else:
        print("No recording issues found that need fixing")
        return False

# Find all possible imx296_capture.py files
for path in [
    "./src/imx296_gs_capture/imx296_capture.py"
]:
    if os.path.exists(path):
        fix_recording_in_file(path)
EOF

    # Run the fix scripts
    echo "Running LSL numeric values fix..."
    python3 /tmp/fix_lsl_numeric.py
    
    echo "Running empty recording files fix..."
    python3 /tmp/fix_empty_recordings.py
    
    echo "✓ Common issues fixed."
}

# Main installation procedure
main() {
    echo "Starting IMX296 Camera installation"
    
    # Check if requirements are met
    if ! check_requirements; then
        echo "Please install required packages and try again."
        exit 1
    fi
    
    # Install Python packages
    install_python_packages
    
    # Create default configuration
    create_config
    
    # Fix common issues before installation
    fix_common_issues
    
    # Create systemd service
    create_service
    
    echo "Installation complete! The service is running in the background."
    echo "To view logs: sudo journalctl -u imx296-camera -f"
    echo "Service status: sudo systemctl status imx296-camera"
    echo "To restart service: sudo systemctl restart imx296-camera"
    echo "Web interface available at: http://localhost:8080"
    
    return 0
}

# Run main installation
main 