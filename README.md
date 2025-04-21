# Raspberry Pi Camera LSL Streamer

A Python package to capture video frames from a Raspberry Pi camera and stream them over LabStreamingLayer (LSL).

## Features

*   Captures frames using `picamera2`.
*   Streams video data (flattened frames) via LSL.
*   Includes timestamps and frame numbers.
*   Configurable resolution, frame rate, and LSL stream parameters.

## Prerequisites

*   Raspberry Pi (tested with Pi 4) running Raspberry Pi OS (Bullseye or later recommended).
*   Raspberry Pi Camera Module (v1, v2, v3, HQ, Noir, etc.) connected and enabled.
*   Python 3.7+
*   Git (for cloning).
*   **System Dependencies (Install on Pi):**
    *   `liblsl-dev` (Core LSL library)
    *   `libcamera-apps` (Recommended for camera support and testing)
    ```bash
    sudo apt update && sudo apt install -y liblsl-dev libcamera-apps
    ```
*   **Camera Interface Enabled (Configure on Pi):**
    *   Use `sudo raspi-config`.
    *   Navigate to `Interface Options` -> `Camera`.
    *   Ensure the camera interface is **Enabled**.
    *   Crucially, ensure the **Legacy Camera** support is **Disabled** (as this package uses the newer `libcamera`/`picamera2` stack).
    *   A **reboot** (`sudo reboot`) is required after changing camera settings.

*(Alternatively, for dependency installation only, you can try running `sudo bash setup_pi.sh` from this repository on the Pi, but manual camera configuration via `raspi-config` is still recommended.)*

## Installation

1.  **Clone the repository (if not installing from PyPI):**
    ```bash
    git clone https://github.com/yourusername/raspberry_pi_lsl_stream # Replace with your repo URL
    cd raspberry_pi_lsl_stream
    ```

2.  **Install Python dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Install the package:**
    *   For development (editable install):
        ```bash
        pip install -e .
        ```
    *   For standard installation:
        ```bash
        pip install .
        ```
    *   (Optional) If published to PyPI:
        ```bash
        # pip install raspberry-pi-lsl-stream
        ```

## Usage

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
*   `--format`: Camera capture format (default: 'RGB888'). See `picamera2` documentation for options.

**Example:**

```bash
rpi-lsl-stream --width 1280 --height 720 --fps 60 --stream-name MyPiCam
```

This will start the camera capture and create an LSL stream named `MyPiCam`. You can then connect to this stream using an LSL client like LabRecorder.

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
