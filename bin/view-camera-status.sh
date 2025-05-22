#!/bin/bash
# Script to view IMX296 camera service status and logs
# Author: Anzal KS <anzal.ks@gmail.com>

# Define colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
WHITE='\033[1;37m'
BOLD='\033[1m'
NC='\033[0m' # No Color
BG_GREEN='\033[42m'
BG_RED='\033[41m'
BG_BLUE='\033[44m'

# Project paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
RECORDINGS_DIR="$PROJECT_ROOT/recordings"
SERVICE_NAME="imx296-camera.service"
DIALOG_HEIGHT=30
DIALOG_WIDTH=100
TEMP_FILE="/tmp/camera_dashboard_$$.tmp"

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

# Function to draw a box with title
draw_box() {
    local title="$1"
    local width=80
    local title_len=${#title}
    local padding=$(( (width - title_len - 4) / 2 ))
    local padding_right=$padding
    
    if [ $(( title_len % 2 )) -ne $(( width % 2 )) ]; then
        padding_right=$((padding + 1))
    fi
    
    echo -e "┌$( printf '─%.0s' $(seq 1 $width) )┐"
    echo -e "│$( printf ' %.0s' $(seq 1 $padding) )${BOLD}${WHITE}$title${NC}$( printf ' %.0s' $(seq 1 $padding_right) )│"
    echo -e "└$( printf '─%.0s' $(seq 1 $width) )┘"
}

# Function to draw a section header
section_header() {
    local title="$1"
    local color="${2:-$BLUE}"
    echo -e "${color}┌─── ${BOLD}$title${NC} ${color}$( printf '─%.0s' $(seq 1 $(( 76 - ${#title} )) ) )┐${NC}"
}

# Function to draw section footer
section_footer() {
    local color="${1:-$BLUE}"
    echo -e "${color}└$( printf '─%.0s' $(seq 1 80) )┘${NC}"
}

# Function to draw a progress bar
draw_progress_bar() {
    local percent=$1
    local width=50
    local num_bars=$(( percent * width / 100 ))
    local color=$GREEN
    
    # Color based on fullness
    if [ $percent -gt 80 ]; then
        color=$RED
    elif [ $percent -gt 50 ]; then
        color=$YELLOW
    fi
    
    echo -ne "["
    for i in $(seq 1 $width); do
        if [ $i -le $num_bars ]; then
            echo -ne "${color}█${NC}"
        else
            echo -ne " "
        fi
    done
    echo -ne "] ${percent}%"
}

# Ensure dialog is installed
check_dialog() {
    if ! command -v dialog >/dev/null 2>&1; then
        echo "Dialog not installed. Installing..."
        sudo apt-get update
        sudo apt-get install -y dialog
        if [ $? -ne 0 ]; then
            echo "Failed to install dialog. Falling back to text mode."
            return 1
        fi
    fi
    return 0
}

# Function to display dashboard view
show_dashboard() {
    # Check if dialog is available
    if ! check_dialog; then
        show_text_dashboard
        return
    fi
    
    # Trap cleanup for graceful exit
    trap cleanup_dashboard SIGINT SIGTERM EXIT
    
    # Loop to continuously update the dashboard
    while true; do
        # Get service status
        service_status=$(systemctl is-active $SERVICE_NAME 2>/dev/null)
        pid=$(systemctl show -p MainPID $SERVICE_NAME | cut -d= -f2)
        
        # Start building dashboard content
        if [ "$service_status" = "active" ] && [ "$pid" != "0" ]; then
            # Get uptime info
            start_time=$(ps -o lstart= -p "$pid")
            runtime=$(ps -o etime= -p "$pid")
            
            # Get CPU and memory usage
            cpu_usage=$(ps -p $pid -o %cpu --no-headers 2>/dev/null | awk '{printf "%.1f", $1}')
            mem_usage=$(ps -p $pid -o %mem --no-headers 2>/dev/null | awk '{printf "%.1f", $1}')
            
            status_text="Status: RUNNING\n"
            status_text+="Running since: $start_time\n"
            status_text+="Uptime: $runtime\n"
            status_text+="CPU Usage: ${cpu_usage}%\n"
            status_text+="Memory Usage: ${mem_usage}%\n"
        else
            status_text="Status: STOPPED\n"
            status_text+="Start the service with: sudo systemctl start $SERVICE_NAME\n"
            
            # If in auto mode and service is not running, try to start it
            if $AUTO_MODE; then
                echo "Service not running. Attempting to start..."
                sudo systemctl start $SERVICE_NAME
                sleep 2
                # Continue to show dashboard - it will reflect new status on next iteration
            fi
        fi
        
        # Get buffer information
        buffer_info=$(journalctl -u $SERVICE_NAME -n 100 | grep -E "Captured|buffer contains" | tail -1)
        if [ -n "$buffer_info" ]; then
            total_frames=$(echo "$buffer_info" | grep -oE "Captured [0-9]+" | grep -oE "[0-9]+")
            buffer_frames=$(echo "$buffer_info" | grep -oE "buffer contains [0-9]+" | grep -oE "[0-9]+")
            
            buffer_text="Total Frames: $total_frames\n"
            buffer_text+="Buffered Frames: $buffer_frames\n"
            
            if [ -n "$total_frames" ] && [ -n "$buffer_frames" ]; then
                buffer_percent=$((buffer_frames * 100 / total_frames))
                buffer_text+="Buffer Fullness: ${buffer_percent}%\n"
            fi
            
            # Get FPS information
            fps_info=$(journalctl -u $SERVICE_NAME -n 30 | grep -E "Current FPS:" | tail -1)
            if [ -n "$fps_info" ]; then
                current_fps=$(echo "$fps_info" | grep -oE "Current FPS: [0-9]+" | grep -oE "[0-9]+")
                buffer_text+="Current FPS: $current_fps\n"
            fi
        else
            buffer_text="No recent buffer information available\n"
        fi
        
        # Get recording information
        is_recording=$(journalctl -u $SERVICE_NAME -n 50 | grep -E "Recording active:|Recording started|Recording stopped" | tail -1)
        if [[ "$is_recording" == *"Recording active"* ]] || [[ "$is_recording" == *"Recording started"* ]]; then
            recording_text="Status: ACTIVE\n"
            
            # Extract session frame count 
            session_frame_info=$(echo "$is_recording" | grep -oE "session frame [0-9]+" | grep -oE "[0-9]+")
            if [ -n "$session_frame_info" ]; then
                recording_text+="Current session frames: $session_frame_info\n"
            fi
            
            # Extract queue size
            queue_info=$(echo "$is_recording" | grep -oE "queue size [0-9]+" | grep -oE "[0-9]+")
            if [ -n "$queue_info" ]; then
                recording_text+="Frames queued for writing: $queue_info\n"
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
                    recording_text+="Current file: $current_file\n"
                fi
            fi
            
            # Get frame count for this recording
            frames_written=$(journalctl -u $SERVICE_NAME -n 50 | grep "frames written" | tail -1 | grep -oE "[0-9]+ frames written" | grep -oE "[0-9]+")
            if [ -n "$frames_written" ]; then
                recording_text+="Frames written: $frames_written\n"
            fi
            
            # Disk space info
            disk_info=$(journalctl -u $SERVICE_NAME -n 50 | grep "free space" | tail -1)
            if [ -n "$disk_info" ]; then
                free_space=$(echo "$disk_info" | grep -oE "free space: [0-9]+\.[0-9]+ GB" | grep -oE "[0-9]+\.[0-9]+")
                if [ -n "$free_space" ]; then
                    recording_text+="Free disk space: ${free_space} GB\n"
                fi
            fi
        else
            recording_text="Status: INACTIVE\n"
            
            # Show next recording file
            timestamp=$(date +%s)
            config_file="$PROJECT_ROOT/config/config.yaml"
            if [ -f "$config_file" ]; then
                session_id=$(grep -E "session_id:" "$config_file" | awk '{print $2}' | tr -d '"')
                if [ -z "$session_id" ]; then
                    session_id=$timestamp
                fi
                next_file="recording_${session_id}_${timestamp}.mkv"
                recording_text+="Next file: $next_file\n"
            fi
        fi
        
        # Get recent recordings
        recordings_text=""
        if [ -d "$RECORDINGS_DIR" ]; then
            recent_files=$(find "$RECORDINGS_DIR" -name "*.mkv" -type f -printf "%T@ %p\n" | sort -rn | head -3 | cut -d' ' -f2-)
            if [ -n "$recent_files" ]; then
                recordings_text="FILENAME                    SIZE       TIMESTAMP\n"
                recordings_text+="----------------------------------------------------------------\n"
                echo "$recent_files" | while read file; do
                    file_size=$(du -h "$file" | cut -f1)
                    file_time=$(stat -c "%y" "$file" | cut -d'.' -f1)
                    filename=$(basename "$file")
                    # Truncate filename if too long
                    if [ ${#filename} -gt 30 ]; then
                        filename="${filename:0:27}..."
                    fi
                    recordings_text+="$filename $(printf '%*s' $((8 - ${#file_size})) '')${file_size} ${file_time}\n"
                done
            else
                recordings_text="No recordings found\n"
            fi
        else
            recordings_text="Recordings directory not found\n"
        fi
        
        # Get LSL information
        lsl_text=""
        lsl_info=$(journalctl -u $SERVICE_NAME -n 100 | grep -E "LSL output:" | tail -3)
        if [ -n "$lsl_info" ]; then
            lsl_text="TIME        RECORDING   FRAME\n"
            lsl_text+="-------------------------------\n"
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
                    
                    lsl_text+="$readable_time   $rec_status        $frame_num\n"
                fi
            done
        else
            # Check if LSL is active at all
            lsl_setup=$(journalctl -u $SERVICE_NAME | grep -E "Setting up LSL stream" | tail -1)
            if [ -n "$lsl_setup" ]; then
                lsl_text="Stream Name: IMX296_Metadata\n"
                lsl_text+="Channels: CaptureTimeUnix, ntfy_notification_active, session_frame_no\n"
                lsl_text+="No recent LSL data available in logs\n"
            else
                lsl_text="No LSL stream information available\n"
            fi
        fi
        
        # Get ntfy information
        ntfy_text=""
        ntfy_topic=$(grep -E "topic:" "$PROJECT_ROOT/config/config.yaml" | awk '{print $2}' | tr -d '"')
        if [ -n "$ntfy_topic" ]; then
            ntfy_text="Topic: $ntfy_topic\n"
            ntfy_text+="Start Recording: curl -d \"start\" https://ntfy.sh/$ntfy_topic\n"
            ntfy_text+="Stop Recording: curl -d \"stop\" https://ntfy.sh/$ntfy_topic\n"
        else
            ntfy_text="No ntfy topic configured\n"
        fi
        
        # Calculate relative sizes for the widgets based on content
        gauge_val=0
        if [ "$service_status" = "active" ]; then
            gauge_val=100
        fi
        
        # Update temporary file with dashboard data
        cat > $TEMP_FILE <<EOF
<service>
$status_text
</service>

<buffer>
$buffer_text
</buffer>

<recording>
$recording_text
</recording>

<recordings>
$recordings_text
</recordings>

<lsl>
$lsl_text
</lsl>

<ntfy>
$ntfy_text
</ntfy>
EOF
        
        # Create a dialog dashboard with multiple widgets
        dialog --clear --colors --title "IMX296 Camera Status Dashboard" \
               --begin 2 1 --gauge "Service Status" 5 $DIALOG_WIDTH $gauge_val \
               --and-widget --begin 7 1 --title "Service Information" --cr-wrap --tailboxbg "$TEMP_FILE" 20 $DIALOG_WIDTH 0 "$TEMP_FILE" "service" \
               --and-widget --begin 7 50 --title "Buffer Status" --cr-wrap --tailboxbg "$TEMP_FILE" 8 50 0 "$TEMP_FILE" "buffer" \
               --and-widget --begin 15 50 --title "Recording Status" --cr-wrap --tailboxbg "$TEMP_FILE" 8 50 0 "$TEMP_FILE" "recording" \
               --and-widget --begin 23 1 --title "Recent Recordings" --cr-wrap --tailboxbg "$TEMP_FILE" 10 50 0 "$TEMP_FILE" "recordings" \
               --and-widget --begin 23 50 --title "LSL Stream Data" --cr-wrap --tailboxbg "$TEMP_FILE" 6 50 0 "$TEMP_FILE" "lsl" \
               --and-widget --begin 29 50 --title "Remote Control" --cr-wrap --tailboxbg "$TEMP_FILE" 4 50 0 "$TEMP_FILE" "ntfy" \
               --no-cancel --no-shadow --no-collapse --sleep 2
        
        # Add key commands at the bottom
        dialog --title "Key Commands" --infobox "Press 'q' to quit, 's' to start recording, 'p' to stop recording" 3 50
        
        # Check for Ctrl+C or other exit
        if [ $? -ne 0 ]; then
            break
        fi
    done
}

# Fallback function in case dialog is not available
show_text_dashboard() {
    clear
    echo "======= IMX296 CAMERA STATUS DASHBOARD ======="
    echo "$(date '+%Y-%m-%d %H:%M:%S')"
    echo
    
    # Loop to continuously update the dashboard
    while true; do
        # Get service status
        service_status=$(systemctl is-active $SERVICE_NAME 2>/dev/null)
        if [ "$service_status" = "active" ]; then
            echo "Service Status: RUNNING"
        else
            echo "Service Status: STOPPED"
            echo "Start the service first with: sudo systemctl start $SERVICE_NAME"
            sleep 2
            return
        fi
        
        # Get process uptime
        pid=$(systemctl show -p MainPID $SERVICE_NAME | cut -d= -f2)
        if [ "$pid" != "0" ]; then
            start_time=$(ps -o lstart= -p "$pid")
            runtime=$(ps -o etime= -p "$pid")
            echo "Running since: $start_time (Uptime: $runtime)"
        fi
        
        echo 
        echo "--- BUFFER INFORMATION ---"
        
        # Get total frames captured and current buffer size
        buffer_info=$(journalctl -u $SERVICE_NAME -n 100 | grep -E "Captured|buffer contains" | tail -1)
        if [ -n "$buffer_info" ]; then
            echo "$buffer_info"
        else
            echo "No recent buffer information available"
        fi
        
        echo
        echo "--- RECORDING INFORMATION ---"
        
        # Check if currently recording
        is_recording=$(journalctl -u $SERVICE_NAME -n 50 | grep -E "Recording active:|Recording started|Recording stopped" | tail -1)
        if [[ "$is_recording" == *"Recording active"* ]] || [[ "$is_recording" == *"Recording started"* ]]; then
            echo "Recording Status: ACTIVE"
            
            # Current recording file
            current_file_info=$(journalctl -u $SERVICE_NAME -n 50 | grep -E "Current output file:|Recording to file" | tail -1)
            if [ -n "$current_file_info" ]; then
                current_file=$(echo "$current_file_info" | grep -oE "recording_[0-9]+_[0-9]+\.mkv")
                if [ -n "$current_file" ]; then
                    echo "Current file: $RECORDINGS_DIR/$current_file"
                fi
            fi
        else
            echo "Recording Status: INACTIVE"
        fi
        
        echo
        echo "--- LSL STREAM INFORMATION ---"
        # Extract LSL information from logs
        lsl_info=$(journalctl -u $SERVICE_NAME -n 100 | grep -E "LSL output:" | tail -1)
        if [ -n "$lsl_info" ]; then
            echo "$lsl_info"
        else
            echo "No recent LSL stream information available"
        fi
        
        echo
        echo "Press Ctrl+C to exit dashboard view"
        sleep 2
        clear
        echo "======= IMX296 CAMERA STATUS DASHBOARD ======="
        echo "$(date '+%Y-%m-%d %H:%M:%S')"
        echo
    done
}

# Cleanup function
cleanup_dashboard() {
    # Remove temporary file
    rm -f "$TEMP_FILE"
    clear
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