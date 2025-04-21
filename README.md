# Raspberry Pi Camera LSL Streamer

A Python package to capture video frames from a Raspberry Pi camera and stream them over LabStreamingLayer (LSL).

## Features

*   Captures frames using `picamera2`.
*   Streams video data (flattened frames) via LSL.
*   Includes timestamps and frame numbers.
*   Configurable resolution, frame rate, and LSL stream parameters.

## Prerequisites

*   Raspberry Pi (tested with Pi 4) running Raspberry Pi OS (Bullseye or later, 64-bit recommended).
*   Raspberry Pi Camera Module (v1, v2, v3, HQ, Noir, etc.) connected.
*   Python 3.7+
*   Git (for cloning this repository).

## Installation on Raspberry Pi

Installing this project on a Raspberry Pi involves two phases because it depends on both standard Python packages (managed by `pip`) and system-level libraries (managed by `apt`), including the special `picamera2` library which is best installed via the Raspberry Pi OS package manager. `pip` cannot manage system libraries or run `apt` for security reasons, hence the two-step process.

**Phase 1: System Setup (Run as root/using `sudo`)**

1.  **Clone the Repository:**
    ```bash
    git clone https://github.com/Dognosis/raspberry_pie_camera_capture.git
    cd raspberry_pie_camera_capture
    ```
2.  **Run Setup Script:** This script installs system libraries (`liblsl-dev`, `libcap-dev`, etc.) and `python3-picamera2` using `apt`. It will attempt to install `liblsl-dev` via `apt` and fall back to building from source if `apt` fails.
    ```bash
    sudo bash setup_pi.sh
    ```
3.  **Enable Camera Interface:** Use the Raspberry Pi configuration tool.
    ```bash
    sudo raspi-config
    ```
    Navigate to `Interface Options` -> `Camera`. Ensure the camera is **Enabled**. Importantly, ensure the **Legacy Camera** option is **Disabled** if you are using a recent Pi OS and `picamera2`.
4.  **Reboot (If Required):** If you made changes in `raspi-config`, reboot the Pi:
    ```bash
    sudo reboot
    ```

**Phase 2: Python Environment and Package Installation (Run as normal user)**

1.  **Create Virtual Environment:** Create a Python virtual environment. **Crucially, use the `--system-site-packages` flag** to allow the environment to access the system-installed `python3-picamera2`.
    ```bash
    # Ensure you are in a suitable location, e.g., your home directory or the project directory
    python3 -m venv --system-site-packages ~/.virtualenvs/dognosis 
    ```
    *(Replace `~/.virtualenvs/dognosis` with your preferred location if desired)*
2.  **Activate Environment:**
    ```bash
    source ~/.virtualenvs/dognosis/bin/activate
    ```
    *(Your prompt should now start with `(dognosis)`)*
3.  **Navigate to Project Directory:**
    ```bash
    cd /path/to/your/raspberry_pie_camera_capture 
    ```
4.  **Install Python Dependencies:** Install the package and its Python dependencies (`pylsl`, `numpy`, `opencv-python`) into the active virtual environment.
    ```bash
    pip install --upgrade pip
    pip install -e .
    ```
    *(Note: `picamera2` should already be available from the system install and accessible due to `--system-site-packages`)*

After these steps, the `rpi-lsl-stream` command should be available in your terminal while the `dognosis` virtual environment is active.

## Usage

Make sure your virtual environment is active (`source ~/.virtualenvs/dognosis/bin/activate`).

Run the streamer from the command line:

```bash
rpi-lsl-stream [OPTIONS]
```

**Options:**

*   `--width`: Video width (default: 640).
*   `--height`: Video height (default: 480).
*   `--fps`: Frames per second (default: 30).
*   `--stream-name`: LSL stream name (default: 'RaspberryPiCamera').
*   `--source-id`: Unique LSL source ID (default: 'RPiCam_UniqueID').
*   `--format`: Camera capture format (default: 'RGB888') - used by PiCamera backend.
*   `--show-preview`: Show a live preview window (requires graphical environment).
*   `--use-max-settings`: [Webcam Only] Attempt to use the highest resolution and FPS reported by the webcam. Overrides `--width`, `--height`, `--fps`.
*   `--duration DURATION`: Record for a fixed duration (in seconds) then stop automatically.
*   `--threaded-writer`: Use a separate thread for writing video frames (recommended for high resolution/fps like 4K@30fps).
*   `--version`: Show program's version number and exit.
*   `-h`, `--help`: Show help message and exit.

**Examples:**

```bash
# Stream at 1080p 30fps indefinitely
rpi-lsl-stream --width 1920 --height 1080 --fps 30

# Stream using max webcam settings (e.g., 4K@30fps) with threaded writer for 60s
rpi-lsl-stream --use-max-settings --duration 60 --threaded-writer
```

## LSL Stream Details

*   **Name:** As specified by `--stream-name`.
*   **Type:** 'Video'
*   **Channels:** `width * height * number_of_color_channels` (e.g., `640 * 480 * 3` for RGB888).
*   **Format:** `cf_uint8` (unsigned 8-bit integers).
*   **Nominal Rate:** As specified by `--fps`.
*   **Source ID:** As specified by `--source-id`.
*   **Metadata:** Includes:
    *   Resolution (width, height)
    *   Color Format (e.g., 'RGB888')
    *   Frame Number (in channel description)

## Troubleshooting

*   **Camera not detected:** Ensure the camera is securely connected and enabled via `raspi-config`.
*   **`liblsl` not found:** Verify `liblsl-dev` is installed or that the library path is configured correctly if built from source.
*   **Permission errors:** Check permissions for accessing the camera device.
*   **Performance issues:** Lower resolution or frame rate might be necessary depending on the Pi model and workload.

## Contributing

(Add contribution guidelines if desired)

## License

(Specify your chosen license, e.g., MIT License)
