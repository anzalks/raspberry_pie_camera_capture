#!/bin/bash
#
# Script to clear camera locks and resolve conflicts
#
# Author: Anzal
# Email: anzal.ks@gmail.com
# GitHub: https://github.com/anzalks/
#

# Text formatting
BOLD=$(tput bold)
GREEN=$(tput setaf 2)
RED=$(tput setaf 1)
YELLOW=$(tput setaf 3)
BLUE=$(tput setaf 4)
RESET=$(tput sgr0)

print_header() {
  echo "${BOLD}${BLUE}=== $1 ===${RESET}"
}

print_success() {
  echo "${GREEN}✓ $1${RESET}"
}

print_error() {
  echo "${RED}✗ $1${RESET}"
}

print_warning() {
  echo "${YELLOW}! $1${RESET}"
}

print_info() {
  echo "${BLUE}ℹ $1${RESET}"
}

# Check if running as root
check_root() {
  if [[ $EUID -ne 0 ]]; then
    print_warning "You are not running as root. Some operations may fail."
    print_info "Try running with sudo for full functionality."
    echo
  fi
}

# Function to check the camera lock file
check_lock_file() {
  print_header "Checking Camera Lock File"
  
  LOCK_FILE="/tmp/raspie_camera.lock"
  
  if [ -f "$LOCK_FILE" ]; then
    print_warning "Lock file exists: $LOCK_FILE"
    
    # Read PID from lock file
    if PID=$(cat "$LOCK_FILE" 2>/dev/null); then
      print_info "Lock file contains PID: $PID"
      
      # Check if process is running
      if ps -p "$PID" > /dev/null 2>&1; then
        print_warning "Process with PID $PID is running"
        ps -f -p "$PID"
      else
        print_info "No process with PID $PID is running"
      fi
    else
      print_error "Could not read PID from lock file"
    fi
  else
    print_success "No lock file found"
  fi
}

# Function to clear the camera lock file
clear_lock_file() {
  print_header "Clearing Camera Lock File"
  
  LOCK_FILE="/tmp/raspie_camera.lock"
  
  if [ -f "$LOCK_FILE" ]; then
    if rm "$LOCK_FILE" 2>/dev/null; then
      print_success "Lock file removed successfully"
    else
      print_error "Failed to remove lock file (permission denied)"
      print_info "Try running with sudo"
    fi
  else
    print_info "No lock file to remove"
  fi
}

# Function to check running camera processes
check_camera_processes() {
  print_header "Checking Camera Processes"
  
  # Look for python processes that might be using the camera
  print_info "Searching for camera-related processes..."
  
  pgrep -fa "python.*camera" || print_info "No Python camera processes found"
  echo
  
  pgrep -fa "libcamera" || print_info "No libcamera processes found"
  echo
  
  ps aux | grep -i "v4l2" | grep -v grep || print_info "No v4l2 processes found"
}

# Function to kill camera processes
kill_camera_processes() {
  print_header "Killing Camera Processes"
  
  # Kill python processes related to the camera
  PIDS=$(pgrep -f "python.*camera")
  
  if [ -n "$PIDS" ]; then
    echo "Found the following camera-related processes:"
    ps -f -p "$PIDS"
    echo
    
    read -p "Kill these processes? (y/n): " confirm
    if [[ $confirm == [yY] ]]; then
      for pid in $PIDS; do
        if kill -9 "$pid" 2>/dev/null; then
          print_success "Killed process $pid"
        else
          print_error "Failed to kill process $pid (permission denied)"
        fi
      done
    else
      print_info "Skipping process termination"
    fi
  else
    print_info "No Python camera processes to kill"
  fi
  
  # Kill any other camera-related processes
  PIDS=$(pgrep -f "libcamera|v4l2")
  
  if [ -n "$PIDS" ]; then
    echo "Found other camera-related processes:"
    ps -f -p "$PIDS"
    echo
    
    read -p "Kill these processes too? (y/n): " confirm
    if [[ $confirm == [yY] ]]; then
      for pid in $PIDS; do
        if kill -9 "$pid" 2>/dev/null; then
          print_success "Killed process $pid"
        else
          print_error "Failed to kill process $pid (permission denied)"
        fi
      done
    else
      print_info "Skipping process termination"
    fi
  else
    print_info "No other camera-related processes to kill"
  fi
}

# Function to check camera device status
check_camera_devices() {
  print_header "Checking Camera Devices"
  
  if command -v v4l2-ctl &> /dev/null; then
    print_info "Camera devices:"
    v4l2-ctl --list-devices
    
    print_info "Testing access to camera device(s):"
    for dev in /dev/video*; do
      if [ -e "$dev" ]; then
        if [ -r "$dev" ] && [ -w "$dev" ]; then
          print_success "$dev is readable and writable"
        else
          print_error "$dev is not accessible (permission issue)"
          ls -la "$dev"
        fi
      fi
    done
  else
    print_warning "v4l2-ctl not found. Install it with: sudo apt install v4l-utils"
  fi
}

# Function to restart the camera service
restart_camera_service() {
  print_header "Restarting Camera Service"
  
  if systemctl is-active --quiet raspie-camera; then
    print_info "Stopping raspie-camera service..."
    if sudo systemctl stop raspie-camera; then
      print_success "Service stopped"
    else
      print_error "Failed to stop service"
    fi
  else
    print_info "raspie-camera service is not running"
  fi
  
  # Clear any locks or processes
  clear_lock_file
  
  # Kill any remaining Python processes
  pkill -9 -f "python.*camera" 2>/dev/null
  
  # Wait a moment
  sleep 2
  
  # Try to start the service
  print_info "Starting raspie-camera service..."
  if sudo systemctl start raspie-camera; then
    print_success "Service started successfully"
    systemctl status raspie-camera --no-pager
  else
    print_error "Failed to start service"
  fi
}

# Function to show usage
show_usage() {
  echo "${BOLD}Raspberry Pi Camera Lock Clearing Tool${RESET}"
  echo
  echo "Usage: $0 [OPTION]"
  echo
  echo "Options:"
  echo "  -c, --check     Check camera locks and processes"
  echo "  -k, --kill      Kill camera processes"
  echo "  -l, --clear     Clear camera lock file"
  echo "  -r, --restart   Restart camera service"
  echo "  -a, --all       Perform all operations"
  echo "  -h, --help      Show this help message"
  echo
  echo "Examples:"
  echo "  $0 --check      Check camera status"
  echo "  $0 --all        Clear all locks and restart"
  echo
}

# Main script

# Check for arguments
if [ $# -eq 0 ]; then
  show_usage
  exit 0
fi

# Process arguments
case "$1" in
  -c|--check)
    check_root
    check_lock_file
    check_camera_processes
    check_camera_devices
    ;;
  -k|--kill)
    check_root
    kill_camera_processes
    ;;
  -l|--clear)
    check_root
    clear_lock_file
    ;;
  -r|--restart)
    check_root
    restart_camera_service
    ;;
  -a|--all)
    check_root
    check_lock_file
    check_camera_processes
    kill_camera_processes
    clear_lock_file
    check_camera_devices
    restart_camera_service
    ;;
  -h|--help)
    show_usage
    ;;
  *)
    print_error "Unknown option: $1"
    show_usage
    exit 1
    ;;
esac

exit 0 