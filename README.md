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
    git clone https://github.com/anzalks/raspberry_pie_camera_capture.git
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
*   `--camera-index`: Camera to use: 'auto' (default: PiCam then Webcams), 'pi' (PiCam only), or an integer index (e.g., 0, 1) for a specific webcam. (default: auto).
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

These examples show various combinations of options. Remember to replace `/path/to/save/videos` with your desired output directory if using `--output-path`.

```bash
# Default: Auto-detect camera (PiCam first), 640x480, 30fps, run indefinitely
rpi-lsl-stream

# Auto-detect camera, 1080p (1920x1080), 30fps, run indefinitely
rpi-lsl-stream --width 1920 --height 1080 --fps 30

# Auto-detect camera, 720p (1280x720), 60fps, run for 2 minutes (120s)
rpi-lsl-stream --width 1280 --height 720 --fps 60 --duration 120

# Auto-detect camera, 1080p, 30fps, run for 5 minutes (300s), save to specific path
rpi-lsl-stream --width 1920 --height 1080 --fps 30 --duration 300 --output-path /path/to/save/videos

# Auto-detect camera, default settings, show preview window for 30 seconds
rpi-lsl-stream --show-preview --duration 30

# Explicitly use PiCamera, 4K resolution (if supported), 15fps, threaded writer, 10 minutes (600s)
rpi-lsl-stream --camera-index pi --width 3840 --height 2160 --fps 15 --threaded-writer --duration 600

# Explicitly use Webcam index 0, 1080p, 30fps, show preview, 1 minute (60s)
rpi-lsl-stream --camera-index 0 --width 1920 --height 1080 --fps 30 --show-preview --duration 60

# Explicitly use Webcam index 1, attempt max settings, run for 2 minutes, save to specific path
rpi-lsl-stream --camera-index 1 --use-max-settings --duration 120 --output-path /path/to/save/videos

# Auto-detect camera, default settings, custom LSL stream name and source ID
rpi-lsl-stream --stream-name MyExperimentCam --source-id Cam01_Session02

# Explicitly use PiCamera, default settings, custom LSL stream name
rpi-lsl-stream --camera-index pi --stream-name PiCam_Test_Stream

### Saving to an External USB Drive (Recommended for Performance)

Saving high-resolution or high-framerate video can be demanding on the Raspberry Pi's microSD card, potentially leading to dropped frames. For better performance and reliability, it is highly recommended to save the video output directly to an external USB drive (SSD or fast flash drive) connected to one of the Pi's USB 3.0 ports.

1.  **Connect and Format the USB Drive:**
    *   Connect your USB drive to the Raspberry Pi.
    *   If the drive is not already formatted with a compatible filesystem, you may need to format it. `exFAT` is a good choice for compatibility between Linux, Windows, and macOS. `NTFS` is also usable (tools installed by `setup_pi.sh`). Use tools like `gparted` (install with `sudo apt install gparted`) or command-line tools (`mkfs.exfat`, `mkfs.ntfs`) carefully.
    *   **Example formatting as exFAT (WARNING: Destroys all data on the drive! Replace `/dev/sdX1` with the correct partition for your USB drive - check with `lsblk`):**
        ```bash
        sudo mkfs.exfat /dev/sdX1 
        ```

2.  **Create a Mount Point:** Create a directory where the USB drive will be mounted.
    ```bash
    sudo mkdir /media/usb_drive 
    # Optional: Change ownership to your user if needed (replace 'pi' with your username)
    # sudo chown pi:pi /media/usb_drive 
    ```

3.  **Mount the USB Drive:** Mount the drive's partition to the created mount point. You might need to identify the correct partition name (e.g., `/dev/sda1`, `/dev/sdb1`) using `lsblk`.
    *   **For exFAT:**
        ```bash
        # Replace /dev/sdX1 with your drive's partition
        sudo mount -t exfat /dev/sdX1 /media/usb_drive 
        ```
    *   **For NTFS:**
        ```bash
        # Replace /dev/sdX1 with your drive's partition
        sudo mount -t ntfs-3g /dev/sdX1 /media/usb_drive 
        ```
    *   **(Optional) Auto-Mounting:** To automatically mount the drive on boot, you can add an entry to `/etc/fstab`. This is recommended for permanent setups. Search online for guides on editing `/etc/fstab` for USB drives on Raspberry Pi.

4.  **Run the Streamer with `--output-path`:** Use the mount point directory as the output path.
    ```bash
    # Activate environment first: source .venv/bin/activate
    rpi-lsl-stream --width 1920 --height 1080 --fps 30 --output-path /media/usb_drive
    ```
    The video file (`lsl_capture_...mkv`) will now be saved directly to the USB drive.

5.  **Unmount When Finished (If not using fstab):** Before physically disconnecting the drive, it's important to unmount it to ensure all data is written.
    ```bash
    sudo umount /media/usb_drive
    ```

Using a USB drive significantly reduces the chance of dropped frames caused by slow storage write speeds.

### Saving Directly to a Network Mount Point (Advanced / Experimental)

While saving locally (to SD card or preferably USB drive) and uploading afterwards is the most reliable method, it is technically possible to save directly to a network location if you mount it to your Raspberry Pi's local filesystem first. **This method is highly discouraged for FTP due to performance limitations.**

**Using NFS or Samba/CIFS (Recommended Network Approach):**

1.  Set up an NFS or Samba share on your network server.
2.  Mount the share on your Raspberry Pi (e.g., to `/mnt/server_share`). Refer to NFS/Samba client setup guides for Raspberry Pi.
3.  Run the script using the mount point:
    ```bash
    rpi-lsl-stream [...] --output-path /mnt/server_share
    ```
    *Performance will depend heavily on network speed and stability. Use `--threaded-writer`.* 

**Using FTP via `curlftpfs` (Not Recommended for Video):**

The `setup_pi.sh` script attempts to install `curlftpfs`. If successful, you can mount an FTP location, but **expect poor performance and potentially corrupted/choppy video**.

1.  **Create a local mount point:** `mkdir ~/my_ftp_mount`
2.  **Mount the FTP directory** (ensure the FTP path is writable):
    ```bash
    # For anonymous FTP (replace server IP/path):
    curlftpfs ftp://anonymous:guest@YOUR_SERVER_IP/path/to/writable_dir ~/my_ftp_mount -o allow_other
    
    # For authenticated FTP (replace user, pass, server IP/path - insecure pass):
    # curlftpfs ftp://YOUR_USER:YOUR_PASS@YOUR_SERVER_IP/path/to/writable_dir ~/my_ftp_mount -o allow_other
    ```
3.  **Run the script:**
    ```bash
    # Activate environment first: source .venv/bin/activate
    rpi-lsl-stream [...] --output-path ~/my_ftp_mount
    ```
4.  **Unmount when finished:** `fusermount -u ~/my_ftp_mount`

**Warning:** Direct video recording over FTP via `curlftpfs` is extremely likely to be too slow and unreliable, leading to significant frame drops and unusable video, especially with higher resolutions/framerates or the MJPG codec. Use local storage or NFS/Samba instead.

## Core Technologies Used

Understanding the libraries and system components involved:

*   **Pi Camera Module Access:**
    *   **Library:** `picamera2`
    *   **Backend:** Uses the modern `libcamera` stack provided by Raspberry Pi OS. This is the standard way to interact with Pi Camera Modules on recent systems (Bookworm+).
    *   **Usage:** Selected via `--camera-index pi` or automatically if detected and no specific index is given.

*   **USB Webcam Access:**
    *   **Library:** OpenCV (`cv2.VideoCapture`)
    *   **Backend:** On Linux, OpenCV typically uses the **V4L2 (Video4Linux2)** kernel subsystem to communicate with standard USB video devices (UVC).
    *   **Usage:** Selected by providing an integer `--camera-index` (e.g., `0`, `1`) or automatically if a Pi Camera is not found/used.

*   **Video Saving (Encoding):**
    *   **Library:** OpenCV (`cv2.VideoWriter`)
    *   **Backend:** `cv2.VideoWriter` acts as a frontend. It relies on underlying multimedia frameworks installed on the system (like FFmpeg or GStreamer, if available with appropriate plugins) to perform the actual video encoding.
    *   **Codec Selection:** The script attempts to use hardware-accelerated codecs (H.264/AVC, H.265/HEVC) first for efficiency. If these are unavailable or fail to initialize (often due to missing GStreamer plugins or incompatible hardware/drivers), it falls back to `MJPG` (Motion JPEG), which is less efficient but more broadly compatible.
    *   **Format:** Saved video files use the `.mkv` (Matroska) container format.

*   **LSL Streaming:**
    *   **Library:** `pylsl` (Python bindings for `liblsl`).
    *   **Functionality:** Used to create the LSL stream outlet and push `[frame_number, timestamp]` pairs.

## LSL Stream Details

**Note:** The current implementation streams only the frame number, not the full video frame data. The video is saved locally to a file.

*   **Name:** As specified by `--stream-name`.
*   **Type:** 'FrameCounter' (Indicates only frame numbers are streamed)
*   **Channels:** 1 (for the frame number).
*   **Format:** `cf_int32` (32-bit integer for the frame number).
*   **Nominal Rate:** As specified by `--fps` (or the actual rate achieved by the camera).
*   **Source ID:** As specified by `--source-id`.
*   **Metadata:** Includes:
    *   Camera Model (`camera_model`)
    *   Source Type (`source_type`: PiCamera or Webcam)
    *   Acquisition Software (`acquisition_software`)
    *   Channel Label (`label`: FrameNumber)

**Timestamp Information:**

*   **Source:** Timestamps are generated using `pylsl.local_clock()`.
*   **Timing:** For each frame, the LSL timestamp is captured *immediately before* the call to acquire the frame data from the camera (i.e., before `picamera2.capture_array()` or `cv2.VideoCapture.read()`). This timestamp is then paired with the corresponding frame number and pushed to LSL.
*   **Clock:** `pylsl.local_clock()` provides high-resolution, monotonic time based on the underlying LSL library (`liblsl`). It aims to use the best monotonic clock source available on the OS (e.g., `CLOCK_MONOTONIC` on Linux). This clock is designed for accurate interval measurement and event ordering within LSL and is not generally affected by system wall-clock changes (e.g., NTP updates) after the stream starts.
*   **Synchronization:** The timestamps represent the time on the local Raspberry Pi running the script. They will automatically become synchronized with other LSL streams on the network **if** LSL time synchronization is active on the network (e.g., via LabRecorder or another synchronization tool). This script itself does not initiate network time synchronization.

## Troubleshooting

*   **Camera not detected:** Ensure the camera is securely connected and enabled via `raspi-config`. Also check the output of `libcamera-hello --list-cameras`.
*   **`picamera2` not found (after running setup):** Make sure you activated the correct virtual environment (`source .venv/bin/activate`) created by the setup script. This environment uses `--system-site-packages` to link to the system-installed `picamera2`.
*   **Video Frame Rate Issues:** If the saved video doesn't seem to have the expected frame rate, use the verification tool (see below).
*   **`liblsl` not found:** Verify `liblsl-dev` is installed (the `setup_pi.sh` script handles this).
*   **Permission errors:** Check permissions for accessing camera devices (`/dev/video*`). Running the main stream command usually doesn't require `sudo` if setup was done correctly.
*   **Performance issues:** Lower resolution or frame rate might be necessary depending on the Pi model and workload. Using `--threaded-writer` is recommended for high-resolution/FPS streams.

## Verifying Saved Video Files

The metadata (resolution, FPS, frame count, duration) of the video file saved during a run is automatically printed to the console when the `rpi-lsl-stream` command finishes.

If you need to check a video file manually at a later time, a separate utility script is also available:

1.  **Activate Environment:** Make sure your virtual environment is active (`source .venv/bin/activate`).
2.  **Run Verification:**
    ```bash
    verify-lsl-video /path/to/your/video/lsl_capture_YYYYMMDD_HHMMSS.mkv
    ```

This will print the resolution, frame rate (as stored in the file metadata), frame count, and calculated duration.

## Viewing Live Frame Numbers (LSL Client)

A separate command is available to connect to the LSL stream created by `rpi-lsl-stream` and view the frame numbers and timestamps being broadcast in real-time. This can be useful for monitoring the stream or synchronizing with other LSL-aware applications without needing the saved video file.

1.  **Start the Streamer:** In one terminal (with the `.venv` activated), run `rpi-lsl-stream` with your desired options.
2.  **Start the Viewer:** In another terminal (with the `.venv` activated):
    ```bash
    view-lsl-framenumbers
    ```
    *Optional arguments: `--stream-name YourStreamName` and `--timeout N` if you changed the defaults on the streamer.*

This viewer will print the received frame number and LSL timestamp to the console until you stop it with `Ctrl+C`.

## Converting Saved Videos to RGB

The videos saved by `rpi-lsl-stream` are in BGR format, which is standard for OpenCV. If you specifically need a video file with the RGB color order, a conversion utility is provided. 

**Warning:** Converting to RGB and saving with common codecs (like MJPG used here) can lead to larger file sizes and potential color/playback issues in some video players. It's often better to perform BGR-to-RGB conversion during analysis if needed.

To convert a video:

1.  **Activate Environment:** Make sure your virtual environment is active (`source .venv/bin/activate`).
2.  **Run Conversion:**
    ```bash
    # Example: Convert input.mkv to input_RGB.mkv (default output name)
    convert-video-rgb input.mkv
    
    # Example: Specify output filename
    convert-video-rgb input.mkv -o output_rgb_video.mkv 
    ```

## Contributing
