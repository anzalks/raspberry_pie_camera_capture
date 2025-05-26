#!/bin/bash
# IMX296 Camera Recording Test Script
# Author: Anzal KS <anzal.ks@gmail.com>
# Date: May 22, 2025

set -e

# Get script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "==== IMX296 Camera Recording Test Tool ===="
echo "Project root: $PROJECT_ROOT"

# First, kill any existing camera processes
echo "Stopping any existing camera processes..."
"$SCRIPT_DIR/diagnose_camera.sh" > /dev/null

# Test direct recording with libcamera-vid
echo "Testing direct recording with libcamera-vid..."
test_file="/tmp/test_recording_$(date +%s).h264"
echo "Recording to: $test_file"

# Run a 3-second test recording
libcamera-vid --width 400 --height 400 --timeout 3000 --nopreview --output "$test_file"

# Check if file exists and has content
if [ -f "$test_file" ]; then
    size=$(du -h "$test_file" | cut -f1)
    echo "Test recording result: $size"
    
    if [ -s "$test_file" ]; then
        echo "✓ SUCCESS: Camera recording test passed!"
    else
        echo "✗ FAILED: Camera recorded a zero-byte file"
    fi
else
    echo "✗ FAILED: No output file was created"
fi

# Test recording with ffmpeg
echo "Testing ffmpeg recording pipeline..."
ffmpeg_test_file="/tmp/ffmpeg_test_$(date +%s).mp4"
echo "Recording to: $ffmpeg_test_file"

echo "Generating test content with ffmpeg..."
ffmpeg -f lavfi -i testsrc=duration=2:size=400x400:rate=30 -c:v libx264 "$ffmpeg_test_file" -y

# Check if file exists and has content
if [ -f "$ffmpeg_test_file" ]; then
    size=$(du -h "$ffmpeg_test_file" | cut -f1)
    echo "ffmpeg test result: $size"
    
    if [ -s "$ffmpeg_test_file" ]; then
        echo "✓ SUCCESS: ffmpeg test passed!"
    else
        echo "✗ FAILED: ffmpeg created a zero-byte file"
    fi
else
    echo "✗ FAILED: No ffmpeg output file was created"
fi

# Try libcamera-vid piped to ffmpeg
echo "Testing libcamera-vid piped to ffmpeg..."
pipe_test_file="/tmp/pipe_test_$(date +%s).mp4"
echo "Recording to: $pipe_test_file"

# Run for 3 seconds
echo "Running combined pipeline test..."
libcamera-vid --width 400 --height 400 --timeout 3000 --codec h264 --inline --nopreview -o - | \
    ffmpeg -f h264 -i - -c:v copy "$pipe_test_file" -y

# Check if file exists and has content
if [ -f "$pipe_test_file" ]; then
    size=$(du -h "$pipe_test_file" | cut -f1)
    echo "Pipeline test result: $size"
    
    if [ -s "$pipe_test_file" ]; then
        echo "✓ SUCCESS: Pipeline test passed!"
    else
        echo "✗ FAILED: Pipeline created a zero-byte file"
    fi
else
    echo "✗ FAILED: No pipeline output file was created"
fi

echo "----- File Permissions Check -----"
echo "Checking recordings directory permissions..."
mkdir -p "$PROJECT_ROOT/recordings"
chmod -R 777 "$PROJECT_ROOT/recordings"
touch "$PROJECT_ROOT/recordings/test_file.txt"
if [ -f "$PROJECT_ROOT/recordings/test_file.txt" ]; then
    echo "✓ Recordings directory is writable"
    rm "$PROJECT_ROOT/recordings/test_file.txt"
else
    echo "✗ Cannot write to recordings directory"
fi

echo "----- System Load Check -----"
echo "Checking system load..."
uptime

echo "----- Disk Space Check -----"
echo "Checking disk space..."
df -h

echo "----- Recommendations -----"
echo "Based on the test results:"
echo "1. If libcamera-vid direct test passed but pipeline failed:"
echo "   - The issue is in the pipeline from libcamera-vid to ffmpeg"
echo "2. If all tests failed:"
echo "   - Check camera physical connection and power"
echo "   - Verify camera is enabled in raspi-config"
echo "   - Try rebooting the system"
echo "3. If file permissions test failed:"
echo "   - Fix permissions on the recordings directory"
echo ""
echo "To restart the camera service: run bin/restart_camera.sh" 