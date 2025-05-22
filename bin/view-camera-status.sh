#!/bin/bash
# Script to view IMX296 camera service status and logs
# Author: Anzal KS <anzal.ks@gmail.com>

# Define colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Project paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
RECORDINGS_DIR="$PROJECT_ROOT/recordings"
SERVICE_NAME="imx296-camera.service"

echo -e "${GREEN}=== IMX296 Global Shutter Camera Status Viewer ===${NC}"
echo

# Function to display dashboard view
show_dashboard() {
    clear
    echo -e "${GREEN}========== IMX296 Camera Status Dashboard ==========${NC}"
    echo -e "${YELLOW}Press Ctrl+C to exit dashboard view${NC}"
    echo
    
    # Loop to continuously update the dashboard
    while true; do
        # Get service status
        service_status=$(systemctl is-active $SERVICE_NAME 2>/dev/null)
        if [ "$service_status" = "active" ]; then
            echo -e "${GREEN}Service Status: RUNNING${NC}"
        else
            echo -e "${RED}Service Status: STOPPED${NC}"
            echo -e "${YELLOW}Start the service first with: sudo systemctl start $SERVICE_NAME${NC}"
            sleep 2
            return
        fi
        
        # Get process uptime
        pid=$(systemctl show -p MainPID $SERVICE_NAME | cut -d= -f2)
        if [ "$pid" != "0" ]; then
            start_time=$(ps -o lstart= -p "$pid")
            runtime=$(ps -o etime= -p "$pid")
            echo -e "${BLUE}Running since:${NC} $start_time (Uptime: $runtime)"
        fi
        
        echo 
        echo -e "${GREEN}--- Buffer Information ---${NC}"
        
        # Get total frames captured and current buffer size
        buffer_info=$(journalctl -u $SERVICE_NAME -n 100 | grep -E "Captured|buffer contains" | tail -1)
        if [ -n "$buffer_info" ]; then
            echo -e "$buffer_info"
            
            # Extract exact frame counts
            total_frames=$(echo "$buffer_info" | grep -oE "Captured [0-9]+" | grep -oE "[0-9]+")
            buffer_frames=$(echo "$buffer_info" | grep -oE "buffer contains [0-9]+" | grep -oE "[0-9]+")
            if [ -n "$total_frames" ] && [ -n "$buffer_frames" ]; then
                buffer_percent=$((buffer_frames * 100 / total_frames))
                echo -e "${BLUE}Buffer fullness:${NC} ${buffer_frames} frames (${buffer_percent}% of total captured)"
            fi
            
            # Get FPS information
            fps_info=$(journalctl -u $SERVICE_NAME -n 30 | grep -E "Current FPS:" | tail -1)
            if [ -n "$fps_info" ]; then
                current_fps=$(echo "$fps_info" | grep -oE "Current FPS: [0-9]+" | grep -oE "[0-9]+")
                echo -e "${BLUE}Current FPS:${NC} $current_fps"
            fi
        else
            echo -e "${YELLOW}No recent buffer information available${NC}"
        fi
        
        echo
        echo -e "${GREEN}--- Recording Information ---${NC}"
        
        # Check if currently recording and get detailed recording stats
        is_recording=$(journalctl -u $SERVICE_NAME -n 50 | grep -E "Recording active:|Recording started|Recording stopped" | tail -1)
        if [[ "$is_recording" == *"Recording active"* ]] || [[ "$is_recording" == *"Recording started"* ]]; then
            echo -e "${BLUE}Recording Status:${NC} ${GREEN}ACTIVE${NC}"
            
            # Extract session frame count 
            session_frame_info=$(echo "$is_recording" | grep -oE "session frame [0-9]+" | grep -oE "[0-9]+")
            if [ -n "$session_frame_info" ]; then
                echo -e "${BLUE}Current session frames:${NC} $session_frame_info"
            fi
            
            # Extract queue size
            queue_info=$(echo "$is_recording" | grep -oE "queue size [0-9]+" | grep -oE "[0-9]+")
            if [ -n "$queue_info" ]; then
                echo -e "${BLUE}Frames queued for writing:${NC} $queue_info"
            fi
            
            # Try to get current recording file
            current_file_info=$(journalctl -u $SERVICE_NAME -n 50 | grep -E "Current output file:|Recording to file" | tail -1)
            if [ -n "$current_file_info" ]; then
                if [[ "$current_file_info" == *"Current output file:"* ]]; then
                    current_file=$(echo "$current_file_info" | grep -oE "recording_[0-9]+_[0-9]+\.mkv")
                else
                    current_file=$(echo "$current_file_info" | grep -oE "recording_[0-9]+_[0-9]+\.mkv")
                fi
                if [ -n "$current_file" ]; then
                    echo -e "${BLUE}Current file:${NC} $RECORDINGS_DIR/$current_file"
                fi
            fi
            
            # Get frame count for this recording
            frames_written=$(journalctl -u $SERVICE_NAME -n 50 | grep "frames written" | tail -1 | grep -oE "[0-9]+ frames written" | grep -oE "[0-9]+")
            if [ -n "$frames_written" ]; then
                echo -e "${BLUE}Frames written in this recording:${NC} $frames_written"
            fi
            
            # Get disk space info
            disk_info=$(journalctl -u $SERVICE_NAME -n 50 | grep "free space" | tail -1)
            if [ -n "$disk_info" ]; then
                free_space=$(echo "$disk_info" | grep -oE "free space: [0-9]+\.[0-9]+ GB" | grep -oE "[0-9]+\.[0-9]+")
                if [ -n "$free_space" ]; then
                    echo -e "${BLUE}Free disk space:${NC} ${free_space} GB"
                fi
            fi
        else
            echo -e "${BLUE}Recording Status:${NC} ${YELLOW}INACTIVE${NC}"
        fi
        
        # List most recent recordings
        echo
        echo -e "${GREEN}--- Recent Recordings ---${NC}"
        if [ -d "$RECORDINGS_DIR" ]; then
            recent_files=$(find "$RECORDINGS_DIR" -name "*.mkv" -type f -printf "%T@ %p\n" | sort -rn | head -3 | cut -d' ' -f2-)
            if [ -n "$recent_files" ]; then
                echo "$recent_files" | while read file; do
                    file_size=$(du -h "$file" | cut -f1)
                    file_time=$(stat -c "%y" "$file")
                    echo -e "${BLUE}$(basename "$file")${NC} - $file_size - $file_time"
                done
            else
                echo -e "${YELLOW}No recordings found${NC}"
            fi
            
            # Add info about expected next recording file
            if [[ "$is_recording" != *"Recording active"* ]] && [[ "$is_recording" != *"Recording started"* ]]; then
                timestamp=$(date +%s)
                config_file="$PROJECT_ROOT/config/config.yaml"
                if [ -f "$config_file" ]; then
                    session_id=$(grep -E "session_id:" "$config_file" | awk '{print $2}' | tr -d '"')
                    if [ -z "$session_id" ]; then
                        session_id=$timestamp
                    fi
                    next_file="recording_${session_id}_${timestamp}.mkv"
                    echo -e "\n${BLUE}Next recording will be saved as:${NC} $RECORDINGS_DIR/$next_file"
                fi
            fi
        else
            echo -e "${YELLOW}Recordings directory not found${NC}"
        fi
        
        echo
        echo -e "${GREEN}--- LSL Stream Information ---${NC}"
        # Try to extract LSL information from logs
        lsl_info=$(journalctl -u $SERVICE_NAME -n 100 | grep -E "LSL output:" | tail -3)
        if [ -n "$lsl_info" ]; then
            echo -e "${BLUE}Current LSL Data:${NC}"
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
                    echo -e "  Time: $readable_time | Recording: $rec_status | Frame: $frame_num"
                fi
            done
        else
            # Check if LSL is active at all
            lsl_setup=$(journalctl -u $SERVICE_NAME | grep -E "Setting up LSL stream" | tail -1)
            if [ -n "$lsl_setup" ]; then
                echo -e "${BLUE}LSL Stream:${NC} Active (stream name: IMX296_Metadata)"
                echo -e "${BLUE}LSL channels:${NC} CaptureTimeUnix, ntfy_notification_active, session_frame_no"
                echo -e "${YELLOW}No recent LSL data visible in logs${NC}"
            else
                echo -e "${YELLOW}No LSL stream information available${NC}"
            fi
        fi
        
        echo
        echo -e "${GREEN}--- System Resources ---${NC}"
        # Get CPU and memory usage
        cpu_usage=$(ps -p $pid -o %cpu --no-headers 2>/dev/null)
        mem_usage=$(ps -p $pid -o %mem --no-headers 2>/dev/null)
        if [ -n "$cpu_usage" ] && [ -n "$mem_usage" ]; then
            echo -e "${BLUE}CPU Usage:${NC} ${cpu_usage}%"
            echo -e "${BLUE}Memory Usage:${NC} ${mem_usage}%"
        fi
        
        echo
        echo -e "${GREEN}--- Remote Control (ntfy.sh) ---${NC}"
        ntfy_topic=$(grep -E "topic:" "$PROJECT_ROOT/config/config.yaml" | awk '{print $2}' | tr -d '"')
        if [ -n "$ntfy_topic" ]; then
            echo -e "${BLUE}Notification Topic:${NC} $ntfy_topic"
            echo -e "${BLUE}Start Recording:${NC} curl -d \"start\" https://ntfy.sh/$ntfy_topic"
            echo -e "${BLUE}Stop Recording:${NC} curl -d \"stop\" https://ntfy.sh/$ntfy_topic"
        else
            echo -e "${YELLOW}No ntfy topic configured${NC}"
        fi
        
        # Brief pause before refreshing
        sleep 2
        clear
        echo -e "${GREEN}========== IMX296 Camera Status Dashboard ==========${NC}"
        echo -e "${YELLOW}Press Ctrl+C to exit dashboard view${NC}"
        echo
    done
}

# Check if the service is installed
if [ ! -f "/etc/systemd/system/imx296-camera.service" ]; then
    echo -e "${RED}Error: IMX296 camera service is not installed.${NC}"
    echo "Please run: sudo bin/install.sh"
    exit 1
fi

# Check service status
echo -e "${YELLOW}Checking service status...${NC}"
sudo systemctl status imx296-camera.service

# Ask user what they want to do
echo
echo -e "${YELLOW}Options:${NC}"
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
        echo -e "${YELLOW}Viewing live logs (Ctrl+C to exit)...${NC}"
        sudo journalctl -u imx296-camera.service -f
        ;;
    2)
        echo -e "${YELLOW}Starting service...${NC}"
        sudo systemctl start imx296-camera.service
        sleep 2
        sudo systemctl status imx296-camera.service
        ;;
    3)
        echo -e "${YELLOW}Stopping service...${NC}"
        sudo systemctl stop imx296-camera.service
        sleep 2
        sudo systemctl status imx296-camera.service
        ;;
    4)
        echo -e "${YELLOW}Restarting service...${NC}"
        sudo systemctl restart imx296-camera.service
        sleep 2
        sudo systemctl status imx296-camera.service
        ;;
    5)
        echo -e "${YELLOW}Running camera script manually with full debug output...${NC}"
        # Set default directory and run script
        script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
        project_root="$(dirname "$script_dir")"
        
        cd "$project_root"
        source .venv/bin/activate
        PYTHONPATH="$project_root" python3 -u bin/run_imx296_capture.py
        ;;
    6)
        echo -e "${YELLOW}Testing camera directly with libcamera-vid...${NC}"
        # Test if libcamera-vid works directly
        echo -e "${GREEN}1. Testing libcamera-hello --list-cameras${NC}"
        libcamera-hello --list-cameras
        
        echo
        echo -e "${GREEN}2. Testing simple 5-second capture to file...${NC}"
        echo "This will record a 5-second test video to /tmp/test.h264"
        read -p "Press Enter to continue..."
        
        libcamera-vid --width 400 --height 400 --framerate 100 -t 5000 -o /tmp/test.h264
        
        echo
        echo -e "${GREEN}3. File information:${NC}"
        ls -la /tmp/test.h264
        
        echo
        echo -e "${GREEN}4. Testing streaming output...${NC}"
        echo "This will display stdout/stderr output from libcamera-vid for 3 seconds"
        read -p "Press Enter to continue..."
        
        # Run with timeout to capture output
        timeout 3 libcamera-vid --width 400 --height 400 --framerate 100 -o - | hexdump -C | head -10
        
        echo
        echo -e "${GREEN}Tests completed.${NC}"
        ;;
    7)
        show_dashboard
        ;;
    8|*)
        echo "Exiting."
        exit 0
        ;;
esac

exit 0 