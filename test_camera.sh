#!/bin/bash
# Simple test script to debug the camera AWB issue

# Enable verbose output
set -x

# Define a simple test function
test_camera_cmd() {
    echo "Testing: $*"
    LOGFILE="/tmp/camera_test.log"
    # Execute the command and capture output
    $@ > "$LOGFILE" 2>&1 || {
        echo "Command failed with error code $?"
        cat "$LOGFILE"
        return 1
    }
    echo "Command succeeded"
    return 0
}

# Test simple rpicam-vid command without AWB
echo "Testing basic rpicam-vid command without AWB..."
test_camera_cmd rpicam-vid --list-cameras

# Test with just width and height
echo "Testing minimal rpicam-vid command..."
test_camera_cmd rpicam-vid --width 400 --height 400 -t 1 -o /dev/null

# Test with additional parameters one by one
echo "Testing with denoise parameter..."
test_camera_cmd rpicam-vid --width 400 --height 400 --denoise cdn_off -t 1 -o /dev/null

echo "Testing with framerate parameter..."
test_camera_cmd rpicam-vid --width 400 --height 400 --denoise cdn_off --framerate 100 -t 1 -o /dev/null

echo "Testing with shutter parameter..."
test_camera_cmd rpicam-vid --width 400 --height 400 --denoise cdn_off --framerate 100 --shutter 10000 -t 1 -o /dev/null

echo "Testing with no-raw parameter..."
test_camera_cmd rpicam-vid --width 400 --height 400 --denoise cdn_off --framerate 100 --shutter 10000 --no-raw -t 1 -o /dev/null

echo "Test complete." 