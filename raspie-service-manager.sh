#!/bin/bash
#
# Service manager script for Raspberry Pi camera capture
# Manages starting, stopping, status checking, and log viewing
#
# Author: Anzal
# Email: anzal.ks@gmail.com
# GitHub: https://github.com/anzalks/
#

# Exit on error
set -e

# Get script directory (where it's physically located)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
SERVICE_NAME="raspie-camera"
LOG_FILE="/var/log/${SERVICE_NAME}/camera.log"

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

print_warn() {
  echo "${YELLOW}! $1${RESET}"
}

print_info() {
  echo "${BLUE}ℹ $1${RESET}"
}

show_help() {
  echo "${BOLD}Raspberry Pi Camera Service Manager${RESET}"
  echo
  echo "Usage: $0 {start|stop|restart|status|logs|test|ntfy}"
  echo
  echo "Commands:"
  echo "  start     - Start the camera service"
  echo "  stop      - Stop the camera service"
  echo "  restart   - Restart the camera service"
  echo "  status    - Check service status"
  echo "  logs      - View service logs"
  echo "  test      - Test the virtual environment and camera setup"
  echo "  ntfy      - Send a test notification"
  echo "  trigger   - Trigger a recording (save buffer)"
  echo
}

check_env() {
  print_header "Environment Check"
  
  # Ensure project directory exists
  if [ ! -d "$SCRIPT_DIR" ]; then
    print_error "Script directory not found: $SCRIPT_DIR"
    exit 1
  fi
  
  # Ensure virtual environment exists
  if [ ! -d "$SCRIPT_DIR/.venv" ]; then
    print_error "Virtual environment not found. Please run setup_pi.sh first."
    exit 1
  fi
  
  print_success "Environment looks good"
}

activate_venv() {
  # Ensure virtual environment is activated
  if [ -z "$VIRTUAL_ENV" ] || [[ "$VIRTUAL_ENV" != *".venv"* ]]; then
    print_info "Activating virtual environment..."
    source "$SCRIPT_DIR/.venv/bin/activate"
  else
    print_info "Virtual environment already active: $VIRTUAL_ENV"
  fi
}

start_service() {
  print_header "Starting $SERVICE_NAME service"
  
  if ! systemctl is-active --quiet "$SERVICE_NAME"; then
    # Start service
    sudo systemctl start "$SERVICE_NAME"
    sleep 2
    
    if systemctl is-active --quiet "$SERVICE_NAME"; then
      print_success "Service started successfully"
    else
      print_error "Failed to start service"
      echo "Check logs with: $0 logs"
    fi
  else
    print_info "Service is already running"
  fi
}

stop_service() {
  print_header "Stopping $SERVICE_NAME service"
  
  if systemctl is-active --quiet "$SERVICE_NAME"; then
    # Stop service
    sudo systemctl stop "$SERVICE_NAME"
    sleep 2
    
    if ! systemctl is-active --quiet "$SERVICE_NAME"; then
      print_success "Service stopped successfully"
    else
      print_error "Failed to stop service"
    fi
  else
    print_info "Service is not running"
  fi
}

restart_service() {
  print_header "Restarting $SERVICE_NAME service"
  sudo systemctl restart "$SERVICE_NAME"
  sleep 2
  
  if systemctl is-active --quiet "$SERVICE_NAME"; then
    print_success "Service restarted successfully"
  else
    print_error "Failed to restart service"
    echo "Check logs with: $0 logs"
  fi
}

check_status() {
  print_header "Service Status"
  
  if systemctl is-active --quiet "$SERVICE_NAME"; then
    print_success "$SERVICE_NAME service is running"
    echo
    systemctl status "$SERVICE_NAME" --no-pager
  else
    print_error "$SERVICE_NAME service is not running"
  fi
  
  echo
  print_header "Recent Log Entries"
  if [ -f "$LOG_FILE" ]; then
    sudo tail -n 10 "$LOG_FILE"
  else
    print_warn "Log file not found: $LOG_FILE"
  fi
}

view_logs() {
  print_header "Service Logs"
  
  if [ -f "$LOG_FILE" ]; then
    sudo tail -n 50 "$LOG_FILE"
  else
    print_warn "Log file not found: $LOG_FILE"
    echo "Checking journal logs instead:"
    sudo journalctl -u "$SERVICE_NAME" --no-pager -n 50
  fi
}

test_setup() {
  print_header "Testing Camera Setup"
  
  # Activate the virtual environment
  activate_venv
  
  # Run the test script
  if [ -f "$SCRIPT_DIR/check-camera-env.py" ]; then
    python "$SCRIPT_DIR/check-camera-env.py"
  else
    print_error "Test script not found: $SCRIPT_DIR/check-camera-env.py"
    
    # Test imports and camera access directly
    python -c "
import sys
import os
import platform
print(f'Python version: {platform.python_version()}')
print(f'Virtual env: {os.environ.get(\"VIRTUAL_ENV\")}')
print('Testing imports...')
try:
    import cv2
    print(f'OpenCV version: {cv2.__version__}')
    import numpy as np
    print(f'NumPy version: {np.__version__}')
    try:
        from picamera2 import Picamera2
        print('PiCamera2 imported successfully')
    except ImportError:
        print('PiCamera2 not available')
    from src.raspberry_pi_lsl_stream import LSLCameraStreamer
    print('LSLCameraStreamer imported successfully')
    
    # Try to access camera
    print('Testing camera access...')
    cap = cv2.VideoCapture(0)
    if cap.isOpened():
        ret, frame = cap.read()
        if ret:
            print('Successfully captured a frame')
        else:
            print('Failed to read frame')
        cap.release()
    else:
        print('Failed to open camera')
except Exception as e:
    print(f'Error: {e}')
"
  fi
}

send_ntfy() {
  print_header "Sending Test Notification"
  
  # Check if curl is installed
  if ! command -v curl &> /dev/null; then
    print_error "curl is not installed. Please install it with: sudo apt install curl"
    return 1
  fi
  
  # Send test notification
  echo "Sending notification to trigger camera recording..."
  curl -s -d "Camera test triggered at $(date)" ntfy.sh/raspicamera-test
  
  if [ $? -eq 0 ]; then
    print_success "Notification sent successfully"
  else
    print_error "Failed to send notification"
  fi
}

trigger_recording() {
  print_header "Triggering Camera Recording"
  
  # Send notification to trigger recording
  curl -s -d "Camera recording triggered manually at $(date)" ntfy.sh/raspicamera-trigger
  
  if [ $? -eq 0 ]; then
    print_success "Recording trigger sent successfully"
    print_info "Check recordings directory for captured video"
  else
    print_error "Failed to send trigger"
  fi
}

# Main logic
case "$1" in
  start)
    check_env
    start_service
    ;;
  stop)
    stop_service
    ;;
  restart)
    restart_service
    ;;
  status)
    check_status
    ;;
  logs)
    view_logs
    ;;
  test)
    check_env
    test_setup
    ;;
  ntfy)
    send_ntfy
    ;;
  trigger)
    trigger_recording
    ;;
  *)
    show_help
    exit 1
    ;;
esac

exit 0 