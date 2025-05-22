#!/bin/bash
# Script to view IMX296 camera service status and logs
# Author: Anzal KS <anzal.ks@gmail.com>

# Project paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
RECORDINGS_DIR="$PROJECT_ROOT/recordings"
SERVICE_NAME="imx296-camera.service"
MAX_TEXT_WIDTH=80  # Maximum width for text display

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
        for i in {1..3}; do
            sleep 1
            new_status=$(sudo journalctl -u $SERVICE_NAME -n 5 2>/dev/null | grep -iE "recording|started|notification received" | tail -1)
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
        for i in {1..3}; do
            sleep 1
            new_status=$(sudo journalctl -u $SERVICE_NAME -n 5 2>/dev/null | grep -iE "recording stopped|notification received|stop" | tail -1)
            if [ -n "$new_status" ]; then
                echo "Recording status update: $new_status"
                break
            fi
        done
    else
        echo "No ntfy topic configured. Cannot stop recording."
    fi
}

# Function to truncate text to a specified width
truncate_text() {
    local text="$1"
    local max_length=${2:-$MAX_TEXT_WIDTH}
    
    if [ ${#text} -gt $max_length ]; then
        echo "${text:0:$((max_length-3))}..."
    else
        echo "$text"
    fi
}

# Extract numeric value from log line
extract_number() {
    echo "$1" | grep -oE "[0-9]+" | head -1
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
    trap 'stty sane; echo "Dashboard closed."; exit 0' SIGINT SIGTERM EXIT

    # Flag to track if dashboard should keep running
    KEEP_RUNNING=true
    
    # Last file tracking
    LAST_FILE=""
    
    # Make the terminal not wait for Enter key
    if [ -t 0 ]; then
        stty -echo -icanon time 0 min 0
    fi
    
    while $KEEP_RUNNING; do
        # Clear screen and draw header
        clear
        echo "========== IMX296 CAMERA STATUS DASHBOARD =========="
        echo "$(date '+%Y-%m-%d %H:%M:%S')"
        echo
        
        # Get service status
        service_status=$(sudo systemctl is-active $SERVICE_NAME 2>/dev/null || echo "unknown")
        pid=$(sudo systemctl show -p MainPID $SERVICE_NAME 2>/dev/null | cut -d= -f2 || echo "0")
        
        #
        # SERVICE STATUS SECTION
        #
        echo "=== SERVICE STATUS ==="
        if [ "$service_status" = "active" ] && [ "$pid" != "0" ]; then
            printf "%-20s %s\n" "Status:" "✓ RUNNING"
            
            # Runtime info
            start_time=$(ps -o lstart= -p "$pid" 2>/dev/null || echo "Unknown")
            runtime=$(ps -o etime= -p "$pid" 2>/dev/null || echo "Unknown")
            printf "%-20s %s\n" "Running since:" "$(truncate_text "$start_time" 55)"
            printf "%-20s %s\n" "Uptime:" "$runtime"
            
            # Resource usage
            cpu_usage=$(ps -p $pid -o %cpu --no-headers 2>/dev/null || echo "N/A")
            mem_usage=$(ps -p $pid -o %mem --no-headers 2>/dev/null || echo "N/A")
            printf "%-20s %s\n" "CPU Usage:" "${cpu_usage}%"
            printf "%-20s %s\n" "Memory Usage:" "${mem_usage}%"
        else
            printf "%-20s %s\n" "Status:" "✗ STOPPED"
            printf "%-20s %s\n" "Start command:" "sudo systemctl start $SERVICE_NAME"
            
            # If in auto mode and service is not running, try to start it
            if $AUTO_MODE; then
                echo "Service not running. Attempting to start..."
                sudo systemctl start $SERVICE_NAME 2>/dev/null
                sleep 2
            fi
        fi
        
        echo
        
        #
        # BUFFER INFORMATION SECTION
        #
        echo "=== BUFFER INFORMATION ==="
        
        # Get buffer information - focus on essential metrics only
        frame_info=$(sudo journalctl -u $SERVICE_NAME -n 150 2>/dev/null | grep -iE "buffer.*frames|captured.*frames|total.*frames|current.*fps" | grep -v "Error" | tail -3)
        fps_info=$(sudo journalctl -u $SERVICE_NAME -n 150 2>/dev/null | grep -iE "framerate.*|fps:" | grep -v "command" | tail -1)
        camera_config=$(sudo journalctl -u $SERVICE_NAME -n 150 2>/dev/null | grep -iE "width.*height|resolution|crop" | grep -v "Error" | tail -1)
        
        if [ -n "$frame_info" ]; then
            # Extract and display important metrics
            total_frames=$(echo "$frame_info" | grep -iE "total|captured" | grep -oE "[0-9]+" | tail -1)
            buffer_frames=$(echo "$frame_info" | grep -iE "buffer" | grep -oE "[0-9]+" | tail -1)
            
            if [ -n "$total_frames" ]; then
                printf "%-20s %s\n" "Total Frames:" "$total_frames"
            fi
            
            if [ -n "$buffer_frames" ]; then
                printf "%-20s %s\n" "Buffered Frames:" "$buffer_frames"
            fi
            
            if [ -n "$fps_info" ]; then
                fps_value=$(echo "$fps_info" | grep -oE "[0-9]+" | head -1)
                if [ -n "$fps_value" ]; then
                    printf "%-20s %s\n" "Current FPS:" "$fps_value"
                else
                    printf "%-20s %s\n" "Frame Rate:" "$(truncate_text "$(echo "$fps_info" | cut -d':' -f2-)" 55)"
                fi
            fi
            
            if [ -n "$camera_config" ]; then
                config_text=$(echo "$camera_config" | sed -E 's/.*INFO - //g' | sed -E 's/.*: //g')
                printf "%-20s %s\n" "Camera Mode:" "$(truncate_text "$config_text" 55)"
            fi
        else
            # Capture settings from startup
            buffer_size=$(sudo journalctl -u $SERVICE_NAME -n 300 2>/dev/null | grep -iE "ram buffer|buffer.*seconds|buffer.*frames" | grep -v "Error" | tail -1)
            camera_cmd=$(sudo journalctl -u $SERVICE_NAME -n 300 2>/dev/null | grep -iE "starting libcamera|libcamera-vid" | grep -v "Error" | tail -1)
            
            if [ -n "$buffer_size" ]; then
                printf "%-20s %s\n" "Buffer Config:" "$(truncate_text "$(echo "$buffer_size" | sed -E 's/.*INFO - //g')" 55)"
            fi
            
            if [ -n "$camera_cmd" ]; then
                # Extract key parameters
                width=$(echo "$camera_cmd" | grep -oE "width [0-9]+" | tail -1 | awk '{print $2}')
                height=$(echo "$camera_cmd" | grep -oE "height [0-9]+" | tail -1 | awk '{print $2}')
                fps=$(echo "$camera_cmd" | grep -oE "framerate [0-9]+" | tail -1 | awk '{print $2}')
                
                if [ -n "$width" ] && [ -n "$height" ] && [ -n "$fps" ]; then
                    printf "%-20s %s\n" "Camera Settings:" "${width}x${height} @ ${fps}fps"
                else
                    printf "%-20s %s\n" "Camera Command:" "$(truncate_text "$(echo "$camera_cmd" | grep -oE "libcamera-vid.*" | tail -1)" 55)"
                fi
            else
                echo "No buffer information available"
            fi
        fi
        
        echo
        
        #
        # RECORDING STATUS SECTION
        #
        echo "=== RECORDING STATUS ==="
        
        # Get recording information - filter out timeout errors
        recording_indicators=$(sudo journalctl -u $SERVICE_NAME -n 200 2>/dev/null | grep -iE "recording active|started recording|notification.*start|saving to file" | grep -v "Error|timed out" | tail -1)
        stop_indicators=$(sudo journalctl -u $SERVICE_NAME -n 50 2>/dev/null | grep -iE "recording stopped|notification.*stop" | grep -v "Error|timed out" | tail -1)
        
        # Check if recording is active
        if [ -n "$recording_indicators" ] && [[ "$(date +%s)" -lt "$(date -d "$(echo "$stop_indicators" | grep -oE "[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}" | tail -1)" +%s 2>/dev/null || echo 0)" ]]; then
            printf "%-20s %s\n" "Status:" "⚫ ACTIVE [Press P to stop]"
            printf "%-20s %s\n" "Recording Info:" "$(truncate_text "$(echo "$recording_indicators" | sed -E 's/.*INFO - //g')" 55)"
            
            # Current recording file with expanded search
            current_file_info=$(sudo journalctl -u $SERVICE_NAME -n 50 2>/dev/null | grep -iE "current.*file|recording to|writing to|saving to" | grep -v "Error" | tail -1)
            if [ -n "$current_file_info" ]; then
                file_text=$(echo "$current_file_info" | sed -E 's/.*INFO - //g')
                printf "%-20s %s\n" "Current File:" "$(truncate_text "$file_text" 55)"
                
                # Extract filename for last file tracking
                file_match=$(echo "$current_file_info" | grep -oE "[a-zA-Z0-9_]+\.mkv")
                if [ -n "$file_match" ]; then
                    LAST_FILE="$RECORDINGS_DIR/$file_match"
                fi
            fi
            
            # Get frame counts
            frame_count=$(sudo journalctl -u $SERVICE_NAME -n 50 2>/dev/null | grep -iE "frames written|session frame" | grep -v "Error" | tail -1)
            if [ -n "$frame_count" ]; then
                count_value=$(echo "$frame_count" | grep -oE "[0-9]+" | tail -1)
                if [ -n "$count_value" ]; then
                    printf "%-20s %s\n" "Frames Recorded:" "$count_value"
                fi
            fi
        else
            printf "%-20s %s\n" "Status:" "○ INACTIVE [Press S to start]"
            
            # Show recent stop event if exists
            if [ -n "$stop_indicators" ]; then
                printf "%-20s %s\n" "Last Stop:" "$(truncate_text "$(echo "$stop_indicators" | sed -E 's/.*INFO - //g')" 55)"
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
                printf "%-20s %s\n" "Next File:" "$(truncate_text "$next_file" 55)"
            fi
            
            # Show last file saved
            if [ -n "$LAST_FILE" ]; then
                printf "%-20s %s\n" "Last File:" "$(truncate_text "$(basename "$LAST_FILE")" 55)"
                if [ -f "$LAST_FILE" ]; then
                    file_size=$(sudo du -h "$LAST_FILE" 2>/dev/null | cut -f1 || echo "Unknown")
                    printf "%-20s %s\n" "Last File Size:" "$file_size"
                fi
            fi
        fi
        
        # Get disk space info
        disk_info=$(sudo journalctl -u $SERVICE_NAME -n 50 2>/dev/null | grep -iE "free space|disk space" | grep -v "Error" | tail -1)
        if [ -n "$disk_info" ]; then
            space_value=$(echo "$disk_info" | grep -oE "[0-9]+(\.[0-9]+)? [GkMT]B" | tail -1)
            if [ -n "$space_value" ]; then
                printf "%-20s %s\n" "Free Disk Space:" "$space_value"
            fi
        else
            # Try to get disk space directly
            if [ -d "$RECORDINGS_DIR" ]; then
                free_space=$(df -h "$RECORDINGS_DIR" | awk 'NR==2 {print $4}')
                printf "%-20s %s\n" "Free Disk Space:" "$free_space"
            fi
        fi
        
        echo
        
        #
        # RECENT RECORDINGS SECTION
        #
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
                echo "No recordings found"
            fi
        else
            echo "Recordings directory not found: $RECORDINGS_DIR"
        fi
        
        echo
        
        #
        # LSL STREAM DATA SECTION
        #
        echo "=== LSL STREAM DATA ==="
        
        # Get LSL information - show key setup information only
        lsl_setup=$(sudo journalctl -u $SERVICE_NAME -n 300 2>/dev/null | grep -iE "created lsl stream|setting up lsl" | grep -v "Error" | tail -1)
        if [ -n "$lsl_setup" ]; then
            lsl_text=$(echo "$lsl_setup" | sed -E 's/.*INFO - //g')
            printf "%-20s %s\n" "LSL Stream:" "$(truncate_text "$lsl_text" 55)"
            
            # Try to find actual LSL data transmissions
            lsl_data=$(sudo journalctl -u $SERVICE_NAME -n 1000 2>/dev/null | grep -iE "lsl output|lsl marker|sending lsl" | grep -v "Error" | tail -3)
            if [ -n "$lsl_data" ]; then
                echo
                echo "Recent LSL data transmissions:"
                echo "$lsl_data" | while read line; do
                    # Extract and display concise information
                    data_text=$(echo "$line" | sed -E 's/.*INFO - //g')
                    echo "  $(truncate_text "$data_text" 75)"
                done
            else
                echo "No recent LSL data transmissions found in logs"
            fi
        else
            echo "No LSL stream configuration found"
        fi
        
        echo
        
        #
        # REMOTE CONTROL SECTION
        #
        echo "=== REMOTE CONTROL ==="
        
        # Get ntfy information
        ntfy_topic=$(grep -E "topic:" "$PROJECT_ROOT/config/config.yaml" | awk '{print $2}' | tr -d '"')
        if [ -n "$ntfy_topic" ]; then
            printf "%-20s %s\n" "Topic:" "$ntfy_topic"
            printf "%-20s %s\n" "Start Recording:" "Press S or curl -d \"start\" https://ntfy.sh/$ntfy_topic"
            printf "%-20s %s\n" "Stop Recording:" "Press P or curl -d \"stop\" https://ntfy.sh/$ntfy_topic"
        else
            echo "No ntfy topic configured"
        fi
        
        echo
        echo "KEYBOARD: [ S ] Start Recording  [ P ] Stop Recording  [ Q ] Quit"
        echo "Press Ctrl+C to exit. Dashboard refreshes every 2 seconds."
        
        # Check for keyboard input
        check_keyboard
        
        # Brief pause before refreshing
        for i in {1..10}; do
            sleep 0.2
            check_keyboard
        done
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