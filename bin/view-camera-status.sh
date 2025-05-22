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

# Function to start recording
start_recording() {
    local ntfy_topic=$(grep -E "topic:" "$PROJECT_ROOT/config/config.yaml" | awk '{print $2}' | tr -d '"')
    if [ -n "$ntfy_topic" ]; then
        echo "Starting recording..."
        curl -s -d "start" https://ntfy.sh/$ntfy_topic
        echo "Start signal sent!"
        
        # Direct verification of recording state
        echo "Checking for recording status changes..."
        for i in {1..5}; do
            echo "Check attempt $i..."
            sleep 1
            new_status=$(sudo journalctl -u $SERVICE_NAME -n 10 2>/dev/null | grep -iE "recording|started|notification received" | tail -1)
            if [ -n "$new_status" ]; then
                echo "Recording status update: $new_status"
                break
            fi
        done
    else
        echo "No ntfy topic configured. Cannot start recording."
    fi
}

# Function to stop recording
stop_recording() {
    local ntfy_topic=$(grep -E "topic:" "$PROJECT_ROOT/config/config.yaml" | awk '{print $2}' | tr -d '"')
    if [ -n "$ntfy_topic" ]; then
        echo "Stopping recording..."
        curl -s -d "stop" https://ntfy.sh/$ntfy_topic
        echo "Stop signal sent!"
        
        # Direct verification of recording state
        echo "Checking for recording status changes..."
        for i in {1..5}; do
            echo "Check attempt $i..."
            sleep 1
            new_status=$(sudo journalctl -u $SERVICE_NAME -n 10 2>/dev/null | grep -iE "recording stopped|notification received|stop" | tail -1)
            if [ -n "$new_status" ]; then
                echo "Recording status update: $new_status"
                break
            fi
        done
    else
        echo "No ntfy topic configured. Cannot stop recording."
    fi
}

# Function to directly check recording state
check_recording_state() {
    # Print the result of a direct check on the recording status
    echo "Current recording status from logs:"
    sudo journalctl -u $SERVICE_NAME -n 30 | grep -E "Recording active:|Recording started|Recording stopped|ntfy message received" | tail -3
}

# Function to check for keyboard input without blocking
check_keyboard() {
    local key
    # Raspberry Pi/Bookworm OS supports fractional timeouts
    read -t 0.1 -n 1 key 2>/dev/null || return 0
    
    case "$key" in
        s|S)
            start_recording
            ;;
        p|P)
            stop_recording
            ;;
        q|Q)
            echo "Dashboard closed."
            exit 0
            ;;
    esac
}

# Simple text-based dashboard
show_dashboard() {
    # Trap for clean exit
    trap 'echo "Dashboard closed."; exit 0' SIGINT SIGTERM

    # Flag to track if dashboard should keep running
    KEEP_RUNNING=true
    
    # Last file tracking
    LAST_FILE=""
    
    # Make the terminal not wait for Enter key
    if [ -t 0 ]; then
        stty -echo -icanon time 0 min 0
    fi
    
    # Set up to restore terminal settings on exit
    trap 'stty sane; echo "Dashboard closed."; exit 0' SIGINT SIGTERM EXIT
    
    while $KEEP_RUNNING; do
        # Clear screen
        clear
        
        echo "========== IMX296 CAMERA STATUS DASHBOARD =========="
        echo "$(date '+%Y-%m-%d %H:%M:%S')"
        echo
        
        # Get service status with sudo
        service_status=$(sudo systemctl is-active $SERVICE_NAME 2>/dev/null || echo "unknown")
        pid=$(sudo systemctl show -p MainPID $SERVICE_NAME 2>/dev/null | cut -d= -f2 || echo "0")
        
        echo "=== SERVICE STATUS ==="
        if [ "$service_status" = "active" ] && [ "$pid" != "0" ]; then
            echo "Status: RUNNING"
            start_time=$(ps -o lstart= -p "$pid" 2>/dev/null || echo "Unknown")
            runtime=$(ps -o etime= -p "$pid" 2>/dev/null || echo "Unknown")
            echo "Running since: $start_time"
            echo "Uptime: $runtime"
            
            # Get CPU and memory usage
            cpu_usage=$(ps -p $pid -o %cpu --no-headers 2>/dev/null || echo "N/A")
            mem_usage=$(ps -p $pid -o %mem --no-headers 2>/dev/null || echo "N/A")
            echo "CPU Usage: ${cpu_usage}%"
            echo "Memory Usage: ${mem_usage}%"
        else
            echo "Status: STOPPED"
            echo "Start the service with: sudo systemctl start $SERVICE_NAME"
            
            # If in auto mode and service is not running, try to start it
            if $AUTO_MODE; then
                echo "Service not running. Attempting to start..."
                sudo systemctl start $SERVICE_NAME 2>/dev/null
                sleep 2
            fi
        fi
        
        echo
        echo "=== BUFFER INFORMATION ==="
        
        # Get buffer information - FURTHER EXPANDED SEARCH
        buffer_info=$(sudo journalctl -u $SERVICE_NAME -n 300 2>/dev/null | grep -iE "buffer|fps|frame|captured|libcamera" | grep -v "LSL" | tail -10)
        if [ -n "$buffer_info" ]; then
            # Display raw buffer info for debugging
            echo "Buffer log entries (last 10):"
            echo "$buffer_info" | sed 's/^/  /'
            echo
            
            # Try to extract buffer stats from camera logs
            camera_stats=$(sudo journalctl -u $SERVICE_NAME -n 600 2>/dev/null | grep -i "statistics" | tail -1)
            if [ -n "$camera_stats" ]; then
                echo "Camera statistics: $camera_stats"
            fi
            
            # Try to find frame rate information
            fps_info=$(echo "$buffer_info" | grep -iE "fps|framerate|rate" | tail -1)
            if [ -n "$fps_info" ]; then
                echo "FPS information: $fps_info"
            fi
        else
            echo "No buffer information available in logs"
            echo "Running command to check for any relevant entries:"
            relevant_entries=$(sudo journalctl -u $SERVICE_NAME -n 30 2>/dev/null | grep -iE "camera|buffer|frame|fps|capture" | tail -5)
            if [ -n "$relevant_entries" ]; then
                echo "$relevant_entries" | sed 's/^/  /'
            else
                echo "  No relevant entries found in recent logs"
            fi
        fi
        
        echo
        echo "=== RECORDING STATUS ==="
        
        # Get recording information with expanded search
        is_recording_raw=$(sudo journalctl -u $SERVICE_NAME -n 300 2>/dev/null | grep -iE "recording|started|active|notify|notification|ntfy" | tail -15)
        if [ -n "$is_recording_raw" ]; then
            echo "Recent recording-related log entries (last 15):"
            echo "$is_recording_raw" | sed 's/^/  /'
            echo
        fi

        # Check for positive indicators of an active recording
        recording_indicators=$(echo "$is_recording_raw" | grep -iE "recording active|started recording|notification.+start|ntfy.+start" | tail -3)
        if [ -n "$recording_indicators" ] && ! echo "$is_recording_raw" | grep -iE "recording stopped|notification.+stop|ntfy.+stop" | tail -1 > /dev/null; then
            echo "Status: ACTIVE [Press P to stop recording]"
            
            # Try to extract session frame count with very flexible pattern matching
            session_frame_info=$(echo "$is_recording_raw" | grep -iE "session frame|frame count|frames:" | grep -oE "[0-9]+" | tail -1 || echo "N/A")
            if [ -n "$session_frame_info" ] && [ "$session_frame_info" != "N/A" ]; then
                echo "Current session frames: $session_frame_info"
            fi
            
            # Extract queue size with more flexible patterns
            queue_info=$(echo "$is_recording_raw" | grep -iE "queue size|frame.+queue|queue.+frame" | grep -oE "[0-9]+" | tail -1 || echo "N/A")
            if [ -n "$queue_info" ] && [ "$queue_info" != "N/A" ]; then
                echo "Frames queued for writing: $queue_info"
            fi
            
            # Show all frames written info from logs
            frames_info=$(sudo journalctl -u $SERVICE_NAME -n 100 2>/dev/null | grep -iE "frames written|written.+frames|frame count" | tail -3)
            if [ -n "$frames_info" ]; then
                echo "Frames written info:"
                echo "$frames_info" | sed 's/^/  /'
            fi
            
            # Current recording file with expanded search
            current_file_info=$(sudo journalctl -u $SERVICE_NAME -n 100 2>/dev/null | grep -iE "current output file:|recording to file|writing to|saving to|output file" | tail -1)
            if [ -n "$current_file_info" ]; then
                echo "Current output file: $current_file_info"
                file_match=$(echo "$current_file_info" | grep -oE "[a-zA-Z0-9_]+\.mkv")
                if [ -n "$file_match" ]; then
                    echo "Extracted filename: $file_match"
                    LAST_FILE="$RECORDINGS_DIR/$file_match"
                fi
            fi
        else
            echo "Status: INACTIVE [Press S to start recording]"
            echo "To start recording, press S or use: curl -d \"start\" https://ntfy.sh/$(grep -E "topic:" "$PROJECT_ROOT/config/config.yaml" | awk '{print $2}' | tr -d '"')"
            
            # Show any recent stop indicators
            stop_indicators=$(echo "$is_recording_raw" | grep -iE "recording stopped|notification.+stop|ntfy.+stop" | tail -1)
            if [ -n "$stop_indicators" ]; then
                echo "Recent stop event: $stop_indicators"
            fi
            
            # Show next recording file
            timestamp=$(date +%s)
            config_file="$PROJECT_ROOT/config/config.yaml"
            if [ -f "$config_file" ]; then
                session_id=$(grep -E "session_id:" "$config_file" | awk '{print $2}' | tr -d '"')
                if [ -z "$session_id" ]; then
                    session_id=$timestamp
                fi
                next_file="recording_${session_id}_${timestamp}.mkv"
                echo "Next file will be: $RECORDINGS_DIR/$next_file"
            fi
            
            # Show last file saved
            if [ -n "$LAST_FILE" ]; then
                echo "Last file saved: $LAST_FILE"
                if [ -f "$LAST_FILE" ]; then
                    file_size=$(sudo du -h "$LAST_FILE" 2>/dev/null | cut -f1 || echo "Unknown")
                    echo "Last file size: $file_size"
                fi
            fi
        fi
        
        echo
        echo "=== RECENT RECORDINGS ==="
        
        # Get recent recordings
        if [ -d "$RECORDINGS_DIR" ]; then
            recent_files=$(sudo find "$RECORDINGS_DIR" -name "*.mkv" -type f -printf "%T@ %p\n" 2>/dev/null | sort -rn | head -3 | cut -d' ' -f2- || echo "")
            if [ -n "$recent_files" ]; then
                printf "%-30s %-10s %s\n" "FILENAME" "SIZE" "TIMESTAMP"
                echo "---------------------------------------------------------------"
                echo "$recent_files" | while read file; do
                    file_size=$(sudo du -h "$file" 2>/dev/null | cut -f1 || echo "?")
                    file_time=$(sudo stat -c "%y" "$file" 2>/dev/null | cut -d'.' -f1 || echo "?")
                    filename=$(basename "$file")
                    # Truncate filename if too long
                    if [ ${#filename} -gt 25 ]; then
                        filename="${filename:0:22}..."
                    fi
                    printf "%-30s %-10s %s\n" "$filename" "$file_size" "$file_time"
                done
            else
                echo "No recordings found at path: $RECORDINGS_DIR"
                echo "Check directory exists with: ls -l $RECORDINGS_DIR"
            fi
        else
            echo "Recordings directory not found: $RECORDINGS_DIR"
            echo "Create it with: mkdir -p $RECORDINGS_DIR"
        fi
        
        echo
        echo "=== LSL STREAM DATA ==="
        
        # Get LSL information - COMPLETELY REVISED APPROACH
        lsl_info=$(sudo journalctl -u $SERVICE_NAME -n 300 2>/dev/null | grep -iE "LSL|lsl|stream|metadata" | tail -10)
        if [ -n "$lsl_info" ]; then
            echo "Recent LSL log entries (last 10):"
            echo "$lsl_info" | sed 's/^/  /'
            echo
            
            # Check for actual data pattern in logs
            lsl_data=$(sudo journalctl -u $SERVICE_NAME -n 1000 2>/dev/null | grep -E "LSL output:|IMX296_Metadata" | grep -E "\[[0-9\.]+," | tail -3)
            if [ -n "$lsl_data" ]; then
                echo "Parsed LSL data:"
                echo "$lsl_data" | sed 's/^/  /'
            else
                # If we can't find standard data patterns, check for any numeric data
                lsl_numbers=$(echo "$lsl_info" | grep -Eo "[0-9]+\.[0-9]+" | tail -3)
                if [ -n "$lsl_numbers" ]; then
                    echo "LSL numeric data found (timestamps or values):"
                    echo "$lsl_numbers" | sed 's/^/  /'
                else
                    echo "No structured LSL data found in logs"
                fi
            fi
        else
            # Report on LSL setup
            lsl_setup=$(sudo journalctl -u $SERVICE_NAME 2>/dev/null | grep -E "Setting up LSL|Created LSL|LSL stream" | tail -1)
            if [ -n "$lsl_setup" ]; then
                echo "LSL setup detected: $lsl_setup"
                echo "No recent LSL data transmission found in logs"
            else
                echo "No LSL stream setup detected in logs"
            fi
        fi
        
        echo
        echo "=== REMOTE CONTROL ==="
        
        # Get ntfy information
        ntfy_topic=$(grep -E "topic:" "$PROJECT_ROOT/config/config.yaml" | awk '{print $2}' | tr -d '"')
        if [ -n "$ntfy_topic" ]; then
            echo "Topic: $ntfy_topic"
            echo "Start Recording: Press S or curl -d \"start\" https://ntfy.sh/$ntfy_topic"
            echo "Stop Recording: Press P or curl -d \"stop\" https://ntfy.sh/$ntfy_topic"
        else
            echo "No ntfy topic configured"
        fi
        
        echo
        echo "KEYBOARD CONTROLS: S = Start Recording, P = Stop Recording, Q = Quit"
        echo "Press Ctrl+C to exit. Dashboard refreshes every 2 seconds."
        
        # Check for keyboard input
        check_keyboard
        
        # Brief pause before refreshing (divided into smaller intervals to check keyboard more frequently)
        for i in {1..10}; do
            sleep 0.2
            check_keyboard
        done

        # Get disk information
        disk_info=$(sudo journalctl -u $SERVICE_NAME -n 200 2>/dev/null | grep -iE "free space|disk space|available space|space left" | tail -1)
        if [ -n "$disk_info" ]; then
            echo "Disk information: $disk_info"
        else
            # Try to get disk space directly
            if [ -d "$RECORDINGS_DIR" ]; then
                free_space=$(df -h "$RECORDINGS_DIR" | awk 'NR==2 {print $4}')
                echo "Free space in recordings directory: $free_space"
            fi
        fi
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