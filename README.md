# Raspberry Pi Camera LSL Streamer

A Python package to capture video frames from a Raspberry Pi camera and stream them over LabStreamingLayer (LSL).

## Features

*   Captures frames using `picamera2` or a standard webcam (`OpenCV`).
*   Saves captured video to a local file (`.mp4` or `.avi`).
*   Streams **frame numbers** and timestamps via LSL.
*   Configurable resolution, frame rate, and LSL stream parameters.
*   Includes optional live preview and threaded video writing.

## Prerequisites

*   Raspberry Pi (tested with Pi 4/5) running Raspberry Pi OS (Bookworm or later, 64-bit recommended).
*   Raspberry Pi Camera Module (v1, v2, v3, HQ, Noir, etc.) connected and enabled via `raspi-config`.
*   Python 3.9+ (aligns with Bookworm's default)
*   Git (for cloning this repository).

## Installation on Raspberry Pi

This project utilizes a `src` layout for better packaging. Installation involves running a single setup script.

**Setup Steps:**

1.  **Clone the Repository:**
    ```bash
    git clone https://github.com/Dognosis/raspberry_pie_camera_capture.git # Replace with your actual repo URL if different
    cd raspberry_pie_camera_capture
    ```
2.  **Run Setup Script (Requires `sudo`):** This script performs the following actions:
    *   Installs essential system libraries (`liblsl-dev`, `libcap-dev`, `libcamera-apps`, etc.) using `apt`.
    *   Installs `python3-picamera2` using `apt` (the recommended way).
    *   Creates a Python virtual environment named `.venv` within the project directory (using `--system-site-packages` to access the system `picamera2`).
    *   Installs the project (`raspberry-pi-lsl-stream`) and its Python dependencies (`pylsl`, `numpy`, `opencv-python`) into the `.venv` using `pip`.
    
    ```bash
    sudo bash setup_pi.sh
    ```
    *Review the script (`setup_pi.sh`) beforehand to see exactly what it does. Ensure you run it from the project's root directory.*
3.  **Enable Camera Interface (If not already done):** If you haven't already, use the Raspberry Pi configuration tool:
    ```bash
    sudo raspi-config
    ```
    Navigate to `Interface Options` -> `Camera`. Ensure the camera is **Enabled**. Make sure the **Legacy Camera** option is **Disabled**.
4.  **Reboot (Recommended):** Especially if you changed camera settings in `raspi-config`.
    ```bash
    sudo reboot
    ```

**Running the Streamer:**

1.  **Navigate to Project Directory:** 
    ```bash
    cd /path/to/your/raspberry_pie_camera_capture 
    ```
2.  **Activate Virtual Environment:** Activate the environment created by the setup script.
    ```bash
    source .venv/bin/activate
    ```
    *(Your terminal prompt should now start with `(.venv)`)*
3.  **Run Command:** The `rpi-lsl-stream` command is now available.
    ```bash
    rpi-lsl-stream --help
    rpi-lsl-stream --width 1920 --height 1080 # Example run
    ```

## Usage

Make sure you are in the project directory and the virtual environment is active (`source .venv/bin/activate`).

Run the streamer from the command line:

```bash
rpi-lsl-stream [OPTIONS]
```

**Command-Line Options:**

*   `--width`: Video width (default: 640).
*   `--height`: Video height (default: 480).
*   `--fps`: Frames per second (default: 30).
*   `--format`: Camera pixel format (default: 'RGB888') - used by PiCamera backend.
*   `--output-path`: Directory path to save the output video file (default: current directory).
*   `--stream-name`: LSL stream name (default: 'RaspberryPiCamera').
*   `--source-id`: Unique LSL source ID (default: 'RPiCam_UniqueID').
*   `--show-preview`: Show a live preview window (requires graphical environment).
*   `--use-max-settings`: [Webcam Only] Attempt to use the highest resolution and FPS reported by the webcam. Overrides `--width`, `--height`, `--fps`.
*   `--duration DURATION`: Record for a fixed duration (in seconds) then stop automatically.
*   `--threaded-writer`: Use a separate thread for writing video frames (recommended for high resolution/fps).
*   `--version`: Show program's version number and exit.
*   `-h`, `--help`: Show help message and exit.

**Examples:**

```bash
# Basic usage (default 640x480 @ 30fps)
rpi-lsl-stream

# Stream at 1920x1080 resolution at 30 fps indefinitely
rpi-lsl-stream --width 1920 --height 1080 --fps 30

# Stream at 1280x720 resolution at 60 fps for 2 minutes (120 seconds)
rpi-lsl-stream --width 1280 --height 720 --fps 60 --duration 120

# Stream at 1080p, 30fps for 5 minutes, saving video to /home/pi/Videos
rpi-lsl-stream --width 1920 --height 1080 --fps 30 --duration 300 --output-path /home/pi/Videos

# Stream using PiCamera default settings but enable preview window for 30 seconds
rpi-lsl-stream --show-preview --duration 30

# Stream at high resolution (e.g., 3840x2160 if supported) at 15 fps using threaded writer for 10 minutes
rpi-lsl-stream --width 3840 --height 2160 --fps 15 --threaded-writer --duration 600

# Attempt to use max settings for a connected WEBCAM for 1 minute with preview
rpi-lsl-stream --use-max-settings --duration 60 --show-preview

# Stream with a custom LSL stream name and source ID
rpi-lsl-stream --stream-name MyExperimentCam --source-id Cam01_Session02
```

## LSL Stream Details

## Troubleshooting

*   **Camera not detected:** Ensure the camera is securely connected and enabled via `raspi-config`. Also check the output of `libcamera-hello --list-cameras`.
*   **`picamera2` not found (after running setup):** Make sure you activated the correct virtual environment (`source .venv/bin/activate`) created by the setup script. This environment uses `--system-site-packages` to link to the system-installed `picamera2`.
*   **Video Frame Rate Issues:** If the saved video doesn't seem to have the expected frame rate, use the verification tool (see below).
*   **`liblsl` not found:** Verify `liblsl-dev` is installed (the `setup_pi.sh` script handles this).
*   **Permission errors:** Check permissions for accessing camera devices (`/dev/video*`). Running the main stream command usually doesn't require `sudo` if setup was done correctly.
*   **Performance issues:** Lower resolution or frame rate might be necessary depending on the Pi model and workload. Using `--threaded-writer` is recommended for high-resolution/FPS streams.

## Verifying Saved Video Files

A utility script is included to check the metadata of saved video files.

1.  **Activate Environment:** Make sure your virtual environment is active (`source .venv/bin/activate`).
2.  **Run Verification:**
    ```bash
    verify-lsl-video /path/to/your/video/lsl_capture_YYYYMMDD_HHMMSS.mkv
    ```

This will print the resolution, frame rate (as stored in the file metadata), frame count, and calculated duration.

## Contributing
