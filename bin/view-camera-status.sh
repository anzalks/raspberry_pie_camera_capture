#!/bin/bash
# Script to view IMX296 camera service status and logs
# Author: Anzal KS <anzal.ks@gmail.com>

# Project paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
RECORDINGS_DIR="$PROJECT_ROOT/recordings"
SERVICE_NAME="imx296-camera.service"

# Parse command line arguments
AUTO_MODE=false
for arg in "$@"; do
    case $arg in
        --auto)
            AUTO_MODE=true
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo "Options:"
            echo "  --auto     Auto-start mode (no menu, directly launch dashboard)"
            echo "  --help     Show this help message"
            echo "  --menu     Show menu instead of directly launching dashboard"
            exit 0
            ;;
        --menu)
            SHOW_MENU=true
            ;;
    esac
done

# Simple text-based dashboard
show_dashboard() {
    # Trap for clean exit
    trap 'echo "Dashboard closed."; exit 0' SIGINT SIGTERM

    # Flag to track if dashboard should keep running
    KEEP_RUNNING=true
    
    while $KEEP_RUNNING; do
        # Clear screen
        clear
        
        echo "========== IMX296 CAMERA STATUS DASHBOARD =========="
        echo "$(date '+%Y-%m-%d %H:%M:%S')"
        echo
        
        # Get service status
        service_status=$(systemctl is-active $SERVICE_NAME 2>/dev/null)
        pid=$(systemctl show -p MainPID $SERVICE_NAME | cut -d= -f2)
        
        echo "=== SERVICE STATUS ==="
        if [ "$service_status" = "active" ] && [ "$pid" != "0" ]; then
            echo "Status: RUNNING"
            start_time=$(ps -o lstart= -p "$pid")
            runtime=$(ps -o etime= -p "$pid")
            echo "Running since: $start_time"
            echo "Uptime: $runtime"
            
            # Get CPU and memory usage
            cpu_usage=$(ps -p $pid -o %cpu --no-headers 2>/dev/null | awk '{printf "%.1f", $1}')
            mem_usage=$(ps -p $pid -o %mem --no-headers 2>/dev/null | awk '{printf "%.1f", $1}')
            echo "CPU Usage: ${cpu_usage}%"
            echo "Memory Usage: ${mem_usage}%"
        else
            echo "Status: STOPPED"
            echo "Start the service with: sudo systemctl start $SERVICE_NAME"
            
            # If in auto mode and service is not running, try to start it
            if $AUTO_MODE; then
                echo "Service not running. Attempting to start..."
                sudo systemctl start $SERVICE_NAME
                sleep 2
            fi
        fi
        
        echo
        echo "=== BUFFER INFORMATION ==="
        
        # Get buffer information
        buffer_info=$(journalctl -u $SERVICE_NAME -n 100 | grep -E "Captured|buffer contains" | tail -1)
        if [ -n "$buffer_info" ]; then
            total_frames=$(echo "$buffer_info" | grep -oE "Captured [0-9]+" | grep -oE "[0-9]+")
            buffer_frames=$(echo "$buffer_info" | grep -oE "buffer contains [0-9]+" | grep -oE "[0-9]+")
            
            echo "Total Frames: $total_frames"
            echo "Buffered Frames: $buffer_frames"
            
            if [ -n "$total_frames" ] && [ -n "$buffer_frames" ]; then
                buffer_percent=$((buffer_frames * 100 / total_frames))
                echo "Buffer Fullness: ${buffer_percent}%"
            fi
            
            # Get FPS information
            fps_info=$(journalctl -u $SERVICE_NAME -n 30 | grep -E "Current FPS:" | tail -1)
            if [ -n "$fps_info" ]; then
                current_fps=$(echo "$fps_info" | grep -oE "Current FPS: [0-9]+" | grep -oE "[0-9]+")
                echo "Current FPS: $current_fps"
            fi
        else
            echo "No recent buffer information available"
        fi
        
        echo
        echo "=== RECORDING STATUS ==="
        
        # Get recording information
        is_recording=$(journalctl -u $SERVICE_NAME -n 50 | grep -E "Recording active:|Recording started|Recording stopped" | tail -1)
        if [[ "$is_recording" == *"Recording active"* ]] || [[ "$is_recording" == *"Recording started"* ]]; then
            echo "Status: ACTIVE"
            
            # Extract session frame count 
            session_frame_info=$(echo "$is_recording" | grep -oE "session frame [0-9]+" | grep -oE "[0-9]+")
            if [ -n "$session_frame_info" ]; then
                echo "Current session frames: $session_frame_info"
            fi
            
            # Extract queue size
            queue_info=$(echo "$is_recording" | grep -oE "queue size [0-9]+" | grep -oE "[0-9]+")
            if [ -n "$queue_info" ]; then
                echo "Frames queued for writing: $queue_info"
            fi
            
            # Current recording file
            current_file_info=$(journalctl -u $SERVICE_NAME -n 50 | grep -E "Current output file:|Recording to file" | tail -1)
            if [ -n "$current_file_info" ]; then
                if [[ "$current_file_info" == *"Current output file:"* ]]; then
                    current_file=$(echo "$current_file_info" | grep -oE "recording_[0-9]+_[0-9]+\.mkv")
                else
                    current_file=$(echo "$current_file_info" | grep -oE "recording_[0-9]+_[0-9]+\.mkv")
                fi
                if [ -n "$current_file" ]; then
                    echo "Current file: $current_file"
                fi
            fi
            
            # Get frame count for this recording
            frames_written=$(journalctl -u $SERVICE_NAME -n 50 | grep "frames written" | tail -1 | grep -oE "[0-9]+ frames written" | grep -oE "[0-9]+")
            if [ -n "$frames_written" ]; then
                echo "Frames written: $frames_written"
            fi
            
            # Disk space info
            disk_info=$(journalctl -u $SERVICE_NAME -n 50 | grep "free space" | tail -1)
            if [ -n "$disk_info" ]; then
                free_space=$(echo "$disk_info" | grep -oE "free space: [0-9]+\.[0-9]+ GB" | grep -oE "[0-9]+\.[0-9]+")
                if [ -n "$free_space" ]; then
                    echo "Free disk space: ${free_space} GB"
                fi
            fi
        else
            echo "Status: INACTIVE"
            
            # Show next recording file
            timestamp=$(date +%s)
            config_file="$PROJECT_ROOT/config/config.yaml"
            if [ -f "$config_file" ]; then
                session_id=$(grep -E "session_id:" "$config_file" | awk '{print $2}' | tr -d '"')
                if [ -z "$session_id" ]; then
                    session_id=$timestamp
                fi
                next_file="recording_${session_id}_${timestamp}.mkv"
                echo "Next file: $next_file"
            fi
        fi
        
        echo
        echo "=== RECENT RECORDINGS ==="
        
        # Get recent recordings
        if [ -d "$RECORDINGS_DIR" ]; then
            recent_files=$(find "$RECORDINGS_DIR" -name "*.mkv" -type f -printf "%T@ %p\n" | sort -rn | head -3 | cut -d' ' -f2-)
            if [ -n "$recent_files" ]; then
                printf "%-30s %-10s %s\n" "FILENAME" "SIZE" "TIMESTAMP"
                echo "---------------------------------------------------------------"
                echo "$recent_files" | while read file; do
                    file_size=$(du -h "$file" | cut -f1)
                    file_time=$(stat -c "%y" "$file" | cut -d'.' -f1)
                    filename=$(basename "$file")
                    # Truncate filename if too long
                    if [ ${#filename} -gt 25 ]; then
                        filename="${filename:0:22}..."
                    fi
                    printf "%-30s %-10s %s\n" "$filename" "$file_size" "$file_time"
                done
            else
                echo "No recordings found"
            fi
        else
            echo "Recordings directory not found"
        fi
        
        echo
        echo "=== LSL STREAM DATA ==="
        
        # Get LSL information
        lsl_info=$(journalctl -u $SERVICE_NAME -n 100 | grep -E "LSL output:" | tail -3)
        if [ -n "$lsl_info" ]; then
            printf "%-10s %-10s %-10s\n" "TIME" "RECORDING" "FRAME"
            echo "------------------------------"
            echo "$lsl_info" | while read line; do
                data=$(echo "$line" | grep -oE "\[.*\]")
                timestamp=$(echo "$data" | grep -oE "[0-9]+\.[0-9]+" | head -1)
                is_recording=$(echo "$data" | grep -oE "[0-9]+\.[0-9]+" | sed -n '2p')
                frame_num=$(echo "$data" | grep -oE "[0-9]+\.[0-9]+" | sed -n '3p')
                
                if [ -n "$timestamp" ] && [ -n "$is_recording" ] && [ -n "$frame_num" ]; then
                    readable_time=$(date -d "@$timestamp" '+%H:%M:%S' 2>/dev/null)
                    if [ -z "$readable_time" ]; then
                        readable_time="$(date '+%H:%M:%S')"
                    fi
                    
                    rec_status="NO"
                    if [ "$is_recording" = "1" ]; then
                        rec_status="YES"
                    fi
                    
                    printf "%-10s %-10s %-10s\n" "$readable_time" "$rec_status" "$frame_num"
                fi
            done
        else
            # Check if LSL is active at all
            lsl_setup=$(journalctl -u $SERVICE_NAME | grep -E "Setting up LSL stream" | tail -1)
            if [ -n "$lsl_setup" ]; then
                echo "Stream Name: IMX296_Metadata"
                echo "Channels: CaptureTimeUnix, ntfy_notification_active, session_frame_no"
                echo "No recent LSL data available in logs"
            else
                echo "No LSL stream information available"
            fi
        fi
        
        echo
        echo "=== REMOTE CONTROL ==="
        
        # Get ntfy information
        ntfy_topic=$(grep -E "topic:" "$PROJECT_ROOT/config/config.yaml" | awk '{print $2}' | tr -d '"')
        if [ -n "$ntfy_topic" ]; then
            echo "Topic: $ntfy_topic"
            echo "Start Recording: curl -d \"start\" https://ntfy.sh/$ntfy_topic"
            echo "Stop Recording: curl -d \"stop\" https://ntfy.sh/$ntfy_topic"
        else
            echo "No ntfy topic configured"
        fi
        
        echo
        echo "Press Ctrl+C to exit. Dashboard refreshes every 2 seconds."
        
        # Brief pause before refreshing
        sleep 2
    done
}

# Function to display menu
show_menu() {
    echo "=== IMX296 Global Shutter Camera Status Viewer ==="
    echo

    # Check if the service is installed
    if [ ! -f "/etc/systemd/system/imx296-camera.service" ]; then
        echo "Error: IMX296 camera service is not installed."
        echo "Please run: sudo bin/install.sh"
        exit 1
    fi

    # Check service status
    echo "Checking service status..."
    sudo systemctl status imx296-camera.service

    # Ask user what they want to do
    echo
    echo "Options:"
    echo "1. View live logs"
    echo "2. Start service"
    echo "3. Stop service"
    echo "4. Restart service"
    echo "5. Run manually (not as service)"
    echo "6. Test camera directly"
    echo "7. Show dashboard view"
    echo "8. Exit"
    echo

    read -p "Enter your choice [1-8]: " choice

    case $choice in
        1)
            echo "Viewing live logs (Ctrl+C to exit)..."
            sudo journalctl -u imx296-camera.service -f
            ;;
        2)
            echo "Starting service..."
            sudo systemctl start imx296-camera.service
            sleep 2
            sudo systemctl status imx296-camera.service
            ;;
        3)
            echo "Stopping service..."
            sudo systemctl stop imx296-camera.service
            sleep 2
            sudo systemctl status imx296-camera.service
            ;;
        4)
            echo "Restarting service..."
            sudo systemctl restart imx296-camera.service
            sleep 2
            sudo systemctl status imx296-camera.service
            ;;
        5)
            echo "Running camera script manually with full debug output..."
            # Set default directory and run script
            script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
            project_root="$(dirname "$script_dir")"
            
            cd "$project_root"
            source .venv/bin/activate
            PYTHONPATH="$project_root" python3 -u bin/run_imx296_capture.py
            ;;
        6)
            echo "Testing camera directly with libcamera-vid..."
            # Test if libcamera-vid works directly
            echo "1. Testing libcamera-hello --list-cameras"
            libcamera-hello --list-cameras
            
            echo
            echo "2. Testing simple 5-second capture to file..."
            echo "This will record a 5-second test video to /tmp/test.h264"
            read -p "Press Enter to continue..."
            
            libcamera-vid --width 400 --height 400 --framerate 100 -t 5000 -o /tmp/test.h264
            
            echo
            echo "3. File information:"
            ls -la /tmp/test.h264
            
            echo
            echo "4. Testing streaming output..."
            echo "This will display stdout/stderr output from libcamera-vid for 3 seconds"
            read -p "Press Enter to continue..."
            
            # Run with timeout to capture output
            timeout 3 libcamera-vid --width 400 --height 400 --framerate 100 -o - | hexdump -C | head -10
            
            echo
            echo "Tests completed."
            ;;
        7)
            show_dashboard
            ;;
        8|*)
            echo "Exiting."
            exit 0
            ;;
    esac
}

# Setup auto-launch on service start
setup_auto_launch() {
    # Create a systemd drop-in directory for the camera service
    SYSTEMD_DIR="/etc/systemd/system/${SERVICE_NAME}.d"
    
    sudo mkdir -p $SYSTEMD_DIR
    
    # Create file to launch dashboard when service starts
    cat << EOF | sudo tee $SYSTEMD_DIR/dashboard.conf > /dev/null
[Service]
ExecStartPost=/bin/bash -c "nohup /usr/bin/x-terminal-emulator -e ${SCRIPT_DIR}/view-camera-status.sh --auto > /dev/null 2>&1 &"
EOF

    sudo systemctl daemon-reload
    echo "Auto-launch configured. Dashboard will open when service starts."
}

# Main logic - determine what to do based on arguments
if [[ "$1" == "--setup-auto-launch" ]]; then
    setup_auto_launch
    exit 0
elif [[ "$SHOW_MENU" == "true" ]]; then
    show_menu
else
    # Default behavior: go straight to dashboard
    show_dashboard
fi

exit 0 