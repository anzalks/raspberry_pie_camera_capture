#!/bin/bash
# Create simple dashboard for IMX296 camera monitoring
# By: Anzal KS <anzal.ks@gmail.com>
set -e

echo "===== Creating IMX296 Camera Dashboard ====="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SRC_DIR="$REPO_ROOT/src/dashboard"

# Create directory if it doesn't exist
mkdir -p "$SRC_DIR"

# Create dashboard.py
cat > "$SRC_DIR/dashboard.py" << 'EOL'
#!/usr/bin/env python3
"""
Simple dashboard for IMX296 camera monitoring
By: Anzal KS <anzal.ks@gmail.com>
"""

import argparse
import os
import subprocess
import time
import json
import threading
import logging
from datetime import datetime
from flask import Flask, render_template, jsonify

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("camera_dashboard")

# Check for LSL
try:
    import pylsl
    has_pylsl = True
    logger.info("LSL support detected")
except ImportError:
    has_pylsl = False
    logger.warning("LSL not available - LSL monitoring disabled")

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)

# Global state
camera_status = {
    "camera_connected": False,
    "recording_active": False,
    "last_frame_time": None,
    "recording_file": None,
    "recording_size": 0,
    "lsl_stream_found": False,
    "lsl_stream_name": None,
    "lsl_frame_count": 0,
    "frame_rate": 0,
    "last_update": datetime.now().isoformat(),
    "media_pipeline_configured": False,
}

def check_camera_connection():
    """Check if the IMX296 camera is connected"""
    try:
        result = subprocess.run(
            ["v4l2-ctl", "--list-devices"],
            check=False, capture_output=True, text=True
        )
        if "imx296" in result.stdout.lower():
            camera_status["camera_connected"] = True
            # Get the device path
            lines = result.stdout.split('\n')
            for i, line in enumerate(lines):
                if "imx296" in line.lower() and i + 1 < len(lines):
                    device = lines[i + 1].strip()
                    camera_status["camera_device"] = device
                    return True
        else:
            camera_status["camera_connected"] = False
        return camera_status["camera_connected"]
    except Exception as e:
        logger.error(f"Error checking camera connection: {e}")
        camera_status["camera_connected"] = False
        return False

def check_media_pipeline():
    """Check if media pipeline is configured for IMX296"""
    try:
        result = subprocess.run(
            ["media-ctl", "--device=/dev/media0", "--print-topology"],
            check=False, capture_output=True, text=True
        )
        
        if "imx296" in result.stdout.lower():
            # Try to get the current format
            format_result = subprocess.run(
                ["media-ctl", "--device=/dev/media0", "--get-v4l2", '"imx296":0'],
                check=False, capture_output=True, text=True, shell=True
            )
            
            if "SBGGR10_1X10" in format_result.stdout and "400x400" in format_result.stdout:
                camera_status["media_pipeline_configured"] = True
                camera_status["camera_format"] = "SBGGR10_1X10/400x400"
            else:
                camera_status["media_pipeline_configured"] = False
                camera_status["camera_format"] = "Unknown"
        else:
            camera_status["media_pipeline_configured"] = False
        
        return camera_status["media_pipeline_configured"]
    except Exception as e:
        logger.error(f"Error checking media pipeline: {e}")
        camera_status["media_pipeline_configured"] = False
        return False

def check_recording_status():
    """Check if recording is active and get file info"""
    try:
        # Check if ffmpeg process is running
        ps_result = subprocess.run(
            ["ps", "-ef"],
            check=True, capture_output=True, text=True
        )
        
        if "ffmpeg" in ps_result.stdout and "v4l2" in ps_result.stdout:
            camera_status["recording_active"] = True
            
            # Try to find the output file
            lines = ps_result.stdout.split('\n')
            for line in lines:
                if "ffmpeg" in line and "v4l2" in line:
                    parts = line.split()
                    for i, part in enumerate(parts):
                        if part.endswith(".mp4") or part.endswith(".h264"):
                            camera_status["recording_file"] = part
                            # Check file size
                            if os.path.exists(part):
                                camera_status["recording_size"] = os.path.getsize(part)
                            break
        else:
            camera_status["recording_active"] = False
            
        return camera_status["recording_active"]
    except Exception as e:
        logger.error(f"Error checking recording status: {e}")
        camera_status["recording_active"] = False
        return False

def check_lsl_stream():
    """Check for LSL stream from the camera"""
    if not has_pylsl:
        camera_status["lsl_stream_found"] = False
        return False
    
    try:
        # Look for camera streams
        streams = pylsl.resolve_streams(wait_time=1.0)
        camera_streams = [s for s in streams if "camera" in s.name().lower() or "imx296" in s.source_id().lower()]
        
        if camera_streams:
            stream = camera_streams[0]
            camera_status["lsl_stream_found"] = True
            camera_status["lsl_stream_name"] = stream.name()
            
            # Try to receive a sample
            inlet = pylsl.StreamInlet(stream)
            sample, timestamp = inlet.pull_sample(timeout=0.5)
            if sample:
                camera_status["last_frame_time"] = timestamp
                camera_status["lsl_frame_count"] += 1
            
            return True
        else:
            camera_status["lsl_stream_found"] = False
            return False
    except Exception as e:
        logger.error(f"Error checking LSL stream: {e}")
        camera_status["lsl_stream_found"] = False
        return False

def update_status_thread():
    """Background thread to update camera status"""
    last_frame_count = 0
    last_check_time = time.time()
    
    while True:
        try:
            # Update all status fields
            check_camera_connection()
            check_media_pipeline()
            check_recording_status()
            check_lsl_stream()
            
            # Calculate frame rate
            current_time = time.time()
            time_diff = current_time - last_check_time
            if time_diff > 0:
                frame_diff = camera_status["lsl_frame_count"] - last_frame_count
                camera_status["frame_rate"] = round(frame_diff / time_diff, 1)
                
            last_frame_count = camera_status["lsl_frame_count"]
            last_check_time = current_time
            
            # Update timestamp
            camera_status["last_update"] = datetime.now().isoformat()
            
            # Sleep before next update
            time.sleep(1.0)
        except Exception as e:
            logger.error(f"Error in status update thread: {e}")
            time.sleep(1.0)

# Routes
@app.route('/')
def index():
    """Main dashboard page"""
    return render_template('index.html')

@app.route('/api/status')
def get_status():
    """API endpoint for status data"""
    return jsonify(camera_status)

@app.route('/api/configure')
def configure_camera():
    """Configure the camera with correct settings"""
    try:
        # Run the configuration script
        subprocess.run(
            ["sudo", "media-ctl", "-d", "/dev/media0", "--set-v4l2", '"imx296":0[fmt:SBGGR10_1X10/400x400]'],
            check=False, shell=True
        )
        subprocess.run(
            ["sudo", "media-ctl", "-d", "/dev/media0", "--set-v4l2", '"*rp1_csi2":0[fmt:SBGGR10_1X10/400x400]'],
            check=False, shell=True
        )
        
        return jsonify({
            "success": True,
            "message": "Camera configured with native 400x400 SBGGR10_1X10 format"
        })
    except Exception as e:
        logger.error(f"Error configuring camera: {e}")
        return jsonify({
            "success": False,
            "message": f"Error: {str(e)}"
        })

def main():
    """Main function"""
    parser = argparse.ArgumentParser(description="IMX296 Camera Dashboard")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host IP")
    parser.add_argument("--port", type=int, default=8080, help="Port number")
    args = parser.parse_args()
    
    # Create templates directory
    os.makedirs(os.path.join(os.path.dirname(__file__), 'templates'), exist_ok=True)
    
    # Create index.html template
    with open(os.path.join(os.path.dirname(__file__), 'templates', 'index.html'), 'w') as f:
        f.write("""<!DOCTYPE html>
<html>
<head>
    <title>IMX296 Camera Dashboard</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
        }
        .container {
            max-width: 1000px;
            margin: 0 auto;
            background-color: white;
            padding: 20px;
            border-radius: 5px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        h1 {
            color: #333;
            margin-top: 0;
        }
        .status-card {
            background-color: #f9f9f9;
            border-left: 4px solid #ddd;
            margin-bottom: 15px;
            padding: 15px;
            border-radius: 3px;
        }
        .status-card.success {
            border-left-color: #4CAF50;
        }
        .status-card.warning {
            border-left-color: #FFC107;
        }
        .status-card.error {
            border-left-color: #F44336;
        }
        .status-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 15px;
            margin-top: 20px;
        }
        .status-item {
            background-color: white;
            border: 1px solid #ddd;
            padding: 10px;
            border-radius: 3px;
        }
        .status-label {
            font-weight: bold;
            margin-bottom: 5px;
            color: #555;
        }
        .status-value {
            font-size: 18px;
        }
        .actions {
            margin-top: 20px;
            padding-top: 20px;
            border-top: 1px solid #eee;
        }
        button {
            background-color: #4CAF50;
            color: white;
            border: none;
            padding: 10px 15px;
            text-align: center;
            text-decoration: none;
            display: inline-block;
            font-size: 16px;
            margin: 4px 2px;
            cursor: pointer;
            border-radius: 3px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>IMX296 Camera Dashboard</h1>
        
        <div id="camera-status" class="status-card">
            <h2>Camera Status</h2>
            <p id="status-message">Checking camera status...</p>
        </div>
        
        <div class="status-grid">
            <div class="status-item">
                <div class="status-label">Camera Connected</div>
                <div class="status-value" id="camera-connected">-</div>
            </div>
            <div class="status-item">
                <div class="status-label">Media Pipeline</div>
                <div class="status-value" id="media-pipeline">-</div>
            </div>
            <div class="status-item">
                <div class="status-label">Camera Format</div>
                <div class="status-value" id="camera-format">-</div>
            </div>
            <div class="status-item">
                <div class="status-label">Recording Active</div>
                <div class="status-value" id="recording-active">-</div>
            </div>
            <div class="status-item">
                <div class="status-label">Current File</div>
                <div class="status-value" id="recording-file">-</div>
            </div>
            <div class="status-item">
                <div class="status-label">File Size</div>
                <div class="status-value" id="recording-size">-</div>
            </div>
            <div class="status-item">
                <div class="status-label">LSL Stream</div>
                <div class="status-value" id="lsl-stream">-</div>
            </div>
            <div class="status-item">
                <div class="status-label">Frame Rate</div>
                <div class="status-value" id="frame-rate">-</div>
            </div>
            <div class="status-item">
                <div class="status-label">Frame Count</div>
                <div class="status-value" id="frame-count">-</div>
            </div>
        </div>
        
        <div class="actions">
            <button id="configure-btn">Configure Camera</button>
        </div>
    </div>
    
    <script>
        // Update status every second
        function updateStatus() {
            fetch('/api/status')
                .then(response => response.json())
                .then(data => {
                    // Update status card
                    const statusCard = document.getElementById('camera-status');
                    const statusMessage = document.getElementById('status-message');
                    
                    if (data.camera_connected) {
                        if (data.recording_active) {
                            statusCard.className = 'status-card success';
                            statusMessage.textContent = 'Camera is connected and recording';
                        } else if (data.media_pipeline_configured) {
                            statusCard.className = 'status-card warning';
                            statusMessage.textContent = 'Camera is connected but not recording';
                        } else {
                            statusCard.className = 'status-card warning';
                            statusMessage.textContent = 'Camera is connected but not properly configured';
                        }
                    } else {
                        statusCard.className = 'status-card error';
                        statusMessage.textContent = 'Camera is not connected';
                    }
                    
                    // Update status values
                    document.getElementById('camera-connected').textContent = data.camera_connected ? 'Yes' : 'No';
                    document.getElementById('media-pipeline').textContent = data.media_pipeline_configured ? 'Configured' : 'Not Configured';
                    document.getElementById('camera-format').textContent = data.camera_format || 'Unknown';
                    document.getElementById('recording-active').textContent = data.recording_active ? 'Yes' : 'No';
                    document.getElementById('recording-file').textContent = data.recording_file || 'None';
                    
                    // Format file size
                    let sizeText = 'None';
                    if (data.recording_size) {
                        if (data.recording_size < 1024) {
                            sizeText = `${data.recording_size} bytes`;
                        } else if (data.recording_size < 1024 * 1024) {
                            sizeText = `${(data.recording_size / 1024).toFixed(1)} KB`;
                        } else {
                            sizeText = `${(data.recording_size / (1024 * 1024)).toFixed(1)} MB`;
                        }
                    }
                    document.getElementById('recording-size').textContent = sizeText;
                    
                    document.getElementById('lsl-stream').textContent = data.lsl_stream_found ? data.lsl_stream_name : 'Not Found';
                    document.getElementById('frame-rate').textContent = `${data.frame_rate} fps`;
                    document.getElementById('frame-count').textContent = data.lsl_frame_count;
                })
                .catch(error => {
                    console.error('Error fetching status:', error);
                });
        }
        
        // Configure camera button
        document.getElementById('configure-btn').addEventListener('click', function() {
            fetch('/api/configure')
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        alert('Camera configured successfully!');
                    } else {
                        alert('Configuration failed: ' + data.message);
                    }
                    updateStatus();
                })
                .catch(error => {
                    console.error('Error configuring camera:', error);
                    alert('Configuration failed due to an error');
                });
        });
        
        // Initial update and start interval
        updateStatus();
        setInterval(updateStatus, 1000);
    </script>
</body>
</html>""")
    
    # Start the status update thread
    threading.Thread(target=update_status_thread, daemon=True).start()
    
    # Start Flask app
    logger.info(f"Starting IMX296 Camera Dashboard on {args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=False)

if __name__ == "__main__":
    main()
EOL

# Make dashboard.py executable
chmod +x "$SRC_DIR/dashboard.py"

# Create dashboard startup script
cat > "$SCRIPT_DIR/start_dashboard.sh" << 'EOL'
#!/bin/bash
# Start IMX296 Camera Dashboard
# By: Anzal KS <anzal.ks@gmail.com>
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "Starting IMX296 Camera Dashboard..."
cd "$REPO_ROOT"

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
  echo "Creating Python virtual environment..."
  python3 -m venv venv
  source venv/bin/activate
  pip install flask pylsl
else
  source venv/bin/activate
fi

# Install required packages
pip install flask pylsl

# Run the dashboard
python -m src.dashboard.dashboard --host 0.0.0.0 --port 8080

# This script will keep running until Ctrl+C is pressed
EOL

chmod +x "$SCRIPT_DIR/start_dashboard.sh"

# Create systemd service for dashboard
mkdir -p "$REPO_ROOT/config"
cat > "$REPO_ROOT/config/imx296_dashboard.service" << EOL
[Unit]
Description=IMX296 Camera Dashboard
After=network.target imx296_camera.service

[Service]
Type=simple
User=root
WorkingDirectory=$REPO_ROOT
ExecStart=$SCRIPT_DIR/start_dashboard.sh
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
EOL

echo "Dashboard created successfully!"
echo ""
echo "===== Usage Instructions ====="
echo "1. To start the dashboard manually:"
echo "   $SCRIPT_DIR/start_dashboard.sh"
echo ""
echo "2. To install as a system service:"
echo "   sudo cp $REPO_ROOT/config/imx296_dashboard.service /etc/systemd/system/"
echo "   sudo systemctl daemon-reload"
echo "   sudo systemctl enable imx296_dashboard.service"
echo "   sudo systemctl start imx296_dashboard.service"
echo ""
echo "3. Access the dashboard at:"
echo "   http://[raspberry-pi-ip]:8080" 