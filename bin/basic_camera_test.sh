#!/bin/bash
# Basic camera test for IMX296
# By: Anzal KS <anzal.ks@gmail.com>
set -e

echo "===== IMX296 Camera Basic Test ====="
echo "This script will try different settings to find what works"

# Check if running as root
if [ "$EUID" -ne 0 ]; then
  echo "Please run with sudo for camera access"
  exit 1
fi

# Test directory
TEST_DIR="/tmp/camera_test"
mkdir -p "$TEST_DIR"
chmod 777 "$TEST_DIR"
echo "Using test directory: $TEST_DIR"

# Check available camera apps
echo "Checking for camera apps..."
for cmd in libcamera-vid libcamera-still rpicam-vid rpicam-still v4l2-ctl; do
  if command -v $cmd &>/dev/null; then
    echo "✓ Found $cmd"
  else
    echo "✗ Missing $cmd"
  fi
done

# Check for camera devices
echo "Checking camera devices..."
ls -l /dev/video* 2>/dev/null || echo "No /dev/video* devices found"

if command -v v4l2-ctl &>/dev/null; then
  echo "Listing available cameras..."
  v4l2-ctl --list-devices || echo "Failed to list devices"
  
  echo "Getting camera capabilities..."
  for dev in /dev/video*; do
    echo "--- $dev ---"
    v4l2-ctl --device=$dev --all || echo "Failed to get info for $dev"
    echo ""
  done
fi

# Try libcamera-hello as a simple test
if command -v libcamera-hello &>/dev/null; then
  echo "Testing with libcamera-hello (basic test)..."
  timeout 5 libcamera-hello || echo "libcamera-hello failed"
fi

# Function to test basic capture
test_basic_capture() {
  local format="$1"
  local output="$TEST_DIR/test_${format}_$(date +%Y%m%d_%H%M%S)"
  
  echo "Testing ${format} format..."
  
  # Try libcamera-vid
  if command -v libcamera-vid &>/dev/null; then
    local cmd="libcamera-vid --timeout 2000 --codec ${format} --width 400 --height 400 --output ${output}.${format}"
    echo "Command: $cmd"
    $cmd || echo "libcamera-vid with ${format} failed"
    
    if [ -f "${output}.${format}" ]; then
      local size=$(stat -c%s "${output}.${format}")
      echo "✓ File created: ${output}.${format} (${size} bytes)"
    else
      echo "✗ No file created"
    fi
  fi
  
  # Try rpicam-vid
  if command -v rpicam-vid &>/dev/null; then
    local cmd="rpicam-vid --timeout 2000 --codec ${format} --width 400 --height 400 --output ${output}_rpi.${format}"
    echo "Command: $cmd"
    $cmd || echo "rpicam-vid with ${format} failed"
    
    if [ -f "${output}_rpi.${format}" ]; then
      local size=$(stat -c%s "${output}_rpi.${format}")
      echo "✓ File created: ${output}_rpi.${format} (${size} bytes)"
    else
      echo "✗ No file created"
    fi
  fi
  
  echo ""
}

# Function to test raw capture
test_raw_capture() {
  local output="$TEST_DIR/test_raw_$(date +%Y%m%d_%H%M%S).raw"
  
  echo "Testing raw format..."
  
  # Try libcamera-vid with raw output
  if command -v libcamera-vid &>/dev/null; then
    local cmd="libcamera-vid --timeout 2000 --width 400 --height 400 --output ${output}"
    echo "Command: $cmd"
    $cmd || echo "libcamera-vid with raw format failed"
    
    if [ -f "${output}" ]; then
      local size=$(stat -c%s "${output}")
      echo "✓ File created: ${output} (${size} bytes)"
    else
      echo "✗ No file created"
    fi
  fi
  
  echo ""
}

# Try with various formats
for format in h264 mjpeg yuv420; do
  test_basic_capture "$format"
done

# Try with raw format
test_raw_capture

# Try with different resolutions and formats
echo "Testing with different resolution combinations..."
for width in 400 320 640; do
  for height in 400 320 480; do
    echo "Testing ${width}x${height} with h264..."
    output="$TEST_DIR/test_${width}x${height}_$(date +%Y%m%d_%H%M%S).h264"
    
    libcamera-vid --timeout 2000 --codec h264 --width $width --height $height --output "$output" || echo "Failed with ${width}x${height}"
    
    if [ -f "$output" ]; then
      size=$(stat -c%s "$output")
      echo "✓ ${width}x${height} worked! File: $output (${size} bytes)"
    else
      echo "✗ ${width}x${height} failed"
    fi
    
    echo ""
  done
done

# Try with libcamera directly with minimal options
echo "Testing libcamera with minimal options..."
min_output="$TEST_DIR/minimal_test_$(date +%Y%m%d_%H%M%S).h264"
libcamera-vid --timeout 2000 --output "$min_output" || echo "Failed with minimal options"

if [ -f "$min_output" ]; then
  size=$(stat -c%s "$min_output")
  echo "✓ Minimal options worked! File: $min_output (${size} bytes)"
else
  echo "✗ Minimal options failed"
fi

# List all created files
echo ""
echo "Files created during testing:"
ls -lh "$TEST_DIR" | sort -k 9

echo ""
echo "If any of these tests worked, note the successful settings and update your configuration accordingly."
echo "Check the file sizes to verify which tests actually captured video successfully." 