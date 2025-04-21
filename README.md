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

Setting up this project on a Raspberry Pi involves two main phases: installing system dependencies using the provided script, and then installing the Python package within a virtual environment.

**Why the two-phase installation?** This project relies on both standard Python packages (installable via `pip`) and system-level libraries or Python packages with complex system dependencies (`picamera2`). Standard Python packaging tools like `pip` cannot manage system libraries or run system package managers like `apt` for security and technical reasons. The `picamera2` library, in particular, depends heavily on the Pi's `libcamera` system stack and its dependencies are best handled by Raspberry Pi OS's `apt` package manager. Therefore, we first use the `setup_pi.sh` script (run with `sudo`) to prepare the system, and then use standard `pip` commands within a virtual environment to install the core Python package and its pure-Python dependencies.

**1. System Setup (Run as root):**

*   Clone this repository or download the source code onto your Raspberry Pi.
*   Navigate to the project's root directory in the terminal.
*   Run the provided setup script using `sudo`. This installs system libraries (like `liblsl-dev`, `libcap-dev`), Python tools (`pip`, `venv`), and `python3-picamera2` using `apt`.
    ```bash
    cd /path/to/your/raspberry_pi_lsl_stream # Navigate to project root
    sudo bash setup_pi.sh
    ```
*   Follow the instructions printed by the script regarding camera configuration:
    *   Use `sudo raspi-config` to **Enable** the camera interface.
    *   Ensure the **Legacy Camera** interface is **Disabled**.
    *   **Reboot** (`sudo reboot`) if you changed camera settings.

**2. Python Environment and Package Installation (Run as normal user):**

*   After running `setup_pi.sh` and rebooting (if needed), create and activate a Python virtual environment (recommended):
    ```bash
    # Example using venv in ~/.virtualenvs/
    python3 -m venv ~/.virtualenvs/dognosis
    source ~/.virtualenvs/dognosis/bin/activate
    ```
*   Navigate back to the project's root directory (where `setup.cfg` is located):
    ```bash
    cd /path/to/your/raspberry_pi_lsl_stream
    ```
*   Install the package. This command will also automatically install the required Python dependencies (`pylsl`, `numpy`, `opencv-python`) listed in `setup.cfg`. Use the `-e` flag for an editable install if you plan to modify the code.
    ```bash
    pip install --upgrade pip
    pip install -e .
    ```
    *(Note: `picamera2` should already be available from the system install performed by `setup_pi.sh` and is not installed by pip here).*

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
