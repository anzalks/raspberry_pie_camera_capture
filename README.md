# Raspberry Pi Camera LSL Streamer

> **Note:** You are currently viewing the `vanila-lsl-stream` branch. This branch provides the core LSL streaming functionality with a simplified codebase.

A Python package to capture video frames from a Raspberry Pi camera and stream them over LabStreamingLayer (LSL).

**Author:** Anzal  
**Contact:** anzal.ks@gmail.com

## Features

*   Captures frames using `picamera2` or a standard webcam (`OpenCV`).
*   Captures audio from USB microphones using `sounddevice`.
*   Saves captured video to a local file (`.mkv`).
*   Saves captured audio to a separate local file (`.wav`).
*   Streams **frame numbers** and timestamps via LSL for video.
*   Streams **audio chunk markers** and timestamps via LSL for audio.
*   Configurable resolution, frame rate, and LSL stream parameters.
*   Configurable audio sampling rate, bit depth, and channels.
*   Includes optional live preview and threaded video writing.
*   Supports rolling buffer mode to capture footage before a trigger event.
*   Integrates with ntfy.sh for remote trigger notifications.
*   Synchronized start/stop for both audio and video using the same triggers.
*   Real-time visualization of audio waveforms and spectrum.
*   CPU core affinity management for optimized performance.
*   Auto-start at boot with systemd service.
*   Standardized "Raspie" naming convention throughout (filenames, services, LSL streams, ntfy topics).
*   **Video Analysis Tools**: Includes utilities to analyze frame rates and interframe intervals.

## Quick Start

See [QUICKSTART.md](QUICKSTART.md) for a quick guide to setting up auto-start and remote triggering via ntfy.sh.

## Prerequisites

*   Raspberry Pi (tested with Pi 4/5) running Raspberry Pi OS (Bookworm or later, 64-bit recommended).
*   Raspberry Pi Camera Module (v1, v2, v3, HQ, Noir, etc.) connected and enabled via `raspi-config`.
*   Python 3.9+ (aligns with Bookworm's default)
*   Git (for cloning this repository).

## Installation on Raspberry Pi

This project is installed using a single all-in-one setup script that handles everything automatically.

**One-Step Installation:**

```bash
# Clone the repository
git clone https://github.com/anzalks/raspberry_pie_camera_capture.git
cd raspberry_pie_camera_capture

# Run the setup script (requires sudo)
sudo bash setup_pi.sh
```

The setup script automatically:
- Installs all required system packages via apt
- Builds critical libraries from source when not available in repositories (liblsl, curlftpfs)
- Creates a Python virtual environment (.venv)
- Installs all Python dependencies inside the virtual environment
- Installs the project itself in development mode

After installation completes, you only need to:

1. **Enable Camera Interface (If not already done):**
   ```bash
   sudo raspi-config
   ```
   Navigate to `Interface Options` -> `Camera`. Ensure the camera is **Enabled** and **Legacy Camera** is **Disabled**.

2. **Reboot your Raspberry Pi:**
   ```bash
   sudo reboot
   ```

**Running the Streamer:**

After reboot, the installation is complete. To use the streamer:

```bash
# Navigate to project directory
cd raspberry_pie_camera_capture

# Activate the virtual environment
source .venv/bin/activate

# Run the streamer with your desired options
rpi-lsl-stream --help
rpi-lsl-stream --width 1920 --height 1080
```

## Usage

Make sure you are in the project directory and the virtual environment is active (`source .venv/bin/activate`).

Run the streamer from the command line:

```bash
rpi-lsl-stream [OPTIONS]
```

By default, all recordings are saved in the `recordings` folder in the current directory.

**Command-Line Options:**

*   `--width`: Video width (default: 400).
*   `--height`: Video height (default: 400).
*   `--fps`: Frames per second (default: 100).
*   `--format`: Camera pixel format (default: 'RGB888') - used by PiCamera backend.
*   `--camera-index`: Camera to use: 'auto' (default: PiCam then Webcams), 'pi' (PiCam only), or an integer index (e.g., 0, 1) for a specific webcam. (default: auto).
*   `--output-path`: Directory path to save the output files (default: current directory).
*   `--codec`: Preferred video codec ('h264', 'h265', 'mjpg', 'auto'). Default 'auto' attempts hardware-accelerated codecs first.
*   `--bitrate`: Constant bitrate in Kbps (0=codec default). Setting this enables CBR mode.
*   `--quality-preset`: Encoding quality preset (trade-off between speed and compression efficiency). Options: 'ultrafast', 'superfast', 'veryfast', 'faster', 'fast', 'medium', 'slow', 'slower', 'veryslow'. Default: 'medium'.
*   `--video-stream-name`: LSL stream name for video frames (default: 'RaspieVideo').
*   `--audio-stream-name`: LSL stream name for audio chunks (default: 'RaspieAudio').
*   `--source-id`: Base LSL source ID (default: 'RaspieCapture') - will be suffixed with _Video or _Audio.
*   `--show-preview`: Show a live preview window (requires graphical environment).
*   `--show-audio-preview`: Show audio visualization window with waveform and spectrum display.
*   `--use-max-settings`: [Webcam Only] Attempt to use the highest resolution and FPS reported by the webcam. Overrides `--width`, `--height`, `--fps`.
*   `--duration DURATION`: Record for a fixed duration (in seconds) then stop automatically.
*   `--threaded-writer`: Use a separate thread for writing video frames (recommended for high resolution/fps).
*   `--use-buffer`: Enable rolling buffer mode to capture frames before trigger (enabled by default).
*   `--buffer-size`: Size of the rolling buffer in seconds (default: 20).
*   `--ntfy-topic`: The ntfy.sh topic to subscribe to for recording triggers (default: "raspie_trigger").
*   `--no-ntfy`: Disable ntfy notifications and use manual triggering only.
*   `--enable-audio`: Enable audio capture from USB microphone.
*   `--audio-device`: Audio device index or name (default: auto-detect first input device).
*   `--sample-rate`: Audio sampling rate in Hz (default: 48000).
*   `--channels`: Number of audio channels (1=mono, 2=stereo) (default: 1).
*   `--bit-depth`: Audio bit depth (16, 24, or 32 bits) (default: 16).
*   `--chunk-size`: Audio processing chunk size (default: 1024).
*   `--no-save-video`: Disable saving video to file (keeps LSL).
*   `--no-save-audio`: Disable saving audio to file (keeps LSL).
*   `--threaded-audio-writer`: Use a separate thread for writing audio chunks (default: enabled).
*   `--no-lsl`: Disable pushing data to LSL.
*   `--video-capture-core`: Specific CPU core for video capture operations (requires psutil).
*   `--video-writer-core`: Specific CPU core for video writer thread (requires psutil).
*   `--video-vis-core`: Specific CPU core for video visualization (requires psutil).
*   `--audio-capture-core`: Specific CPU core for audio capture operations (requires psutil).
*   `--audio-writer-core`: Specific CPU core for audio writer thread (requires psutil).
*   `--audio-vis-core`: Specific CPU core for audio visualization (requires psutil).
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
rpi-lsl-stream --video-stream-name MyExperimentCam --audio-stream-name MyExperimentMic --source-id Cam01_Session02

# Force use of H.264 codec with constant bitrate of 2Mbps and fast preset for higher frame rates
rpi-lsl-stream --width 1280 --height 720 --fps 60 --codec h264 --bitrate 2000 --quality-preset veryfast

# Use MJPG codec for maximum compatibility (if H.264/H.265 not working)
rpi-lsl-stream --width 1280 --height 720 --fps 30 --codec mjpg

# Optimize for high performance with lower latency using H.264, CBR, and ultrafast preset
rpi-lsl-stream --width 640 --height 480 --fps 60 --codec h264 --bitrate 1500 --quality-preset ultrafast

# Default mode: 400x400 at 100fps, rolling buffer with ntfy start/stop control
rpi-lsl-stream

### Audio Capture Examples

These examples demonstrate how to use the audio capture functionality alongside video:

```bash
# Enable audio capture with default settings (48kHz, 16-bit, mono)
rpi-lsl-stream --enable-audio

# High-quality audio capture (48kHz, 24-bit, stereo)
rpi-lsl-stream --enable-audio --sample-rate 48000 --bit-depth 24 --channels 2

# Audio-only capture (no video)
rpi-lsl-stream --enable-audio --no-save-video

# Specify a particular audio device by name (partial match)
rpi-lsl-stream --enable-audio --audio-device "USB Audio"

# Specify a particular audio device by index
rpi-lsl-stream --enable-audio --audio-device 1

# Custom buffer size (30 seconds) for both video and audio
rpi-lsl-stream --enable-audio --buffer-size 30

# Custom stream names for better organization in LSL recordings
rpi-lsl-stream --enable-audio --video-stream-name "DogCam" --audio-stream-name "DogMic"
```

For optimal performance, audio capture processes run on a separate core when possible. Both audio and video use the same triggering mechanism (ntfy.sh notifications or manual keyboard triggers) and buffer settings, ensuring perfect synchronization.

### Auto-Start and Remote Control Examples

These examples show how to use the auto-start service and remote control functionality:

```bash
# Install the service for auto-start on boot
sudo bash raspie-capture-service.sh

# Apply performance optimizations (optional)
sudo bash raspie-optimize.sh

# Start the service immediately (without waiting for reboot)
sudo systemctl start raspie-capture.service

# Check service status and see if it's running correctly
./raspie-service.sh status

# Start recording remotely using curl
curl -d "start recording" ntfy.sh/raspie_trigger

# Stop recording remotely using curl
curl -d "stop recording" ntfy.sh/raspie_trigger

# Use the convenience script to trigger recording
./raspie-service.sh trigger

# Use the convenience script to stop recording
./raspie-service.sh stop-recording

# View the service logs to troubleshoot issues
./raspie-service.sh logs

# Run with visualizers for testing
source .venv/bin/activate
bash examples/run_visualizers.sh
```

These examples use the default `raspie_trigger` ntfy.sh topic. You can customize this by editing the service file or specifying a different topic with the `--ntfy-topic` option.

### Visualization and Performance Optimization

The system provides real-time visualization for both video and audio streams, allowing you to monitor capture quality during experiments.

#### Audio and Video Visualization

To enable visualization:

```bash
# Show video preview window
rpi-lsl-stream --show-preview

# Show audio visualization (waveform, spectrum analyzer, and level meter)
rpi-lsl-stream --enable-audio --show-audio-preview

# Show both video and audio visualizations together
rpi-lsl-stream --enable-audio --show-preview --show-audio-preview
```

The audio visualizer provides:
- A real-time waveform display of the incoming audio
- A spectrum analyzer showing frequency content as a waterfall display
- A level meter with color indicators (green=normal, yellow=approaching peak, red=clipping)

#### CPU Core Affinity Management

For optimal performance, especially on Raspberry Pi, you can assign different processing tasks to specific CPU cores using the `--*-core` options. This prevents resource contention between critical operations like video encoding and visualization.

```bash
# Assign video capture to core 0, writer to core 1, audio to core 2
rpi-lsl-stream --enable-audio --video-capture-core 0 --video-writer-core 1 --audio-capture-core 2

# Include visualization on different cores
rpi-lsl-stream --enable-audio --show-preview --show-audio-preview \
  --video-capture-core 0 --video-writer-core 1 --video-vis-core 2 \
  --audio-capture-core 3 --audio-writer-core 1 --audio-vis-core 2
```

All core assignment options:
- `--video-capture-core`: Core for video capture operations
- `--video-writer-core`: Core for video encoding/writing thread
- `--video-vis-core`: Core for video visualization
- `--audio-capture-core`: Core for audio capture operations
- `--audio-writer-core`: Core for audio writing thread
- `--audio-vis-core`: Core for audio visualization

Core affinity management requires the `psutil` package to be installed (`pip install psutil`).

#### Automatic Performance Optimization

For Raspberry Pi users, we provide an optimization script that automatically configures the system for better performance:

```bash
sudo bash raspie-optimize.sh
```

This script applies several optimizations:
1. Sets CPU governor to performance mode
2. Increases GPU memory allocation
3. Enables maximum USB bus power (for better microphone stability)
4. Disables unnecessary services (bluetooth, printing, etc.)
5. Sets high process priority for capture processes
6. Creates a RAM disk for temporary files

#### Example Scripts

The `examples` directory contains ready-to-use scripts demonstrating these features:

```bash
# Run visualizers with automatic core assignment
bash examples/run_visualizers.sh

# Run using Python with manual core control
python examples/run_with_visualizers.py
```

For more details about visualization options and CPU affinity management, see the examples README: `examples/README.md`

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
    The video file (`raspie_video_TIMESTAMP.mkv`) will now be saved directly to the USB drive.

5.  **Unmount When Finished (If not using fstab):** Before physically disconnecting the drive, it's important to unmount it to ensure all data is written.
    ```bash
    sudo umount /media/usb_drive
    ```

Using a USB drive significantly reduces the chance of dropped frames caused by slow storage write speeds.

## Auto-Start Service

The package includes scripts to set up Raspie Capture as a systemd service that starts automatically at boot and can be controlled remotely.

### Setting Up Auto-Start

1. Install the service (requires sudo):
   ```bash
   sudo bash raspie-capture-service.sh
   ```
   This creates:
   - A systemd service that starts Raspie Capture on boot
   - A management script (`raspie-service.sh`) for controlling the service
   - Uses a 20-second rolling buffer with ntfy.sh triggering

2. (Optional) Apply performance optimizations:
   ```bash
   sudo bash raspie-optimize.sh
   ```
   This script:
   - Sets CPU to performance mode
   - Allocates more memory to the GPU
   - Creates a RAM disk for temporary files
   - Disables unnecessary services
   - Sets process priorities

3. Reboot to start the service:
   ```bash
   sudo reboot
   ```

### Remote Control via ntfy.sh

Once the service is running, you can control recordings from any internet-connected device:

```bash
# Start recording
curl -d "start recording" ntfy.sh/raspie_trigger

# Stop recording
curl -d "stop recording" ntfy.sh/raspie_trigger
```

You can also use the management script:

```bash
# Start recording
./raspie-service.sh trigger

# Stop recording
./raspie-service.sh stop-recording

# View service status
./raspie-service.sh status

# View service logs
./raspie-service.sh logs
```

For more details, see [QUICKSTART.md](QUICKSTART.md).

## LSL Stream Details

**Note:** The current implementation streams only the frame number, not the full video frame data. The video is saved locally to a file.

*   **Name:** As specified by `--video-stream-name` (for video) or `--audio-stream-name` (for audio).
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
    verify-lsl-video /path/to/your/video/raspie_video_YYYYMMDD_HHMMSS.mkv
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

## High FPS Buffer Capture (Experimental - `buffercapture_high_fps` Branch)

This branch (`buffercapture_high_fps`) contains a modified capture implementation specifically for the **Pi Camera Module** aimed at achieving higher frame rates.

*   **Technique:** Instead of using `picam2.capture_array()` (which copies frame data), this version uses `picam2.capture_buffer()`. It then accesses the camera's memory buffer directly (via memory mapping, e.g., `picam2.map_buffer()` or `picamera2.helpers.mmap()`) and creates a zero-copy NumPy array view of the frame data.
*   **Benefit:** By avoiding the memory copy inherent in `capture_array()`, this method reduces CPU overhead per frame and can potentially allow for higher capture frame rates (e.g., > 60 FPS), limited primarily by the camera sensor's capabilities, MIPI bandwidth, and subsequent processing/saving speed.
*   **Requirement:** This method requires careful handling of the captured buffer, which *must* be released back to the camera system promptly using `picam2.release_buffer()` after the frame data is used (e.g., pushed to the queue or previewed). This is handled within the `capture_frame` method's `finally` block.
*   **Status:** Consider this an experimental optimization. While it may improve performance, test thoroughly for stability and potential issues, especially regarding buffer management at very high frame rates.

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

## Optimizing Performance and Frame Rates

To achieve the highest possible frame rates on Raspberry Pi, you can adjust several encoding parameters:

### Encoding Options for High Performance

1. **Codec Selection (`--codec`):**
   * `h264` - Hardware-accelerated H.264 encoding is available on Raspberry Pi and typically offers the best balance of quality and performance
   * `mjpg` - A highly compatible codec that works when H.264/H.265 fails, but typically results in larger file sizes

2. **Constant Bitrate Mode (`--bitrate`):**
   * Setting a specific bitrate (in Kbps) enables constant bitrate (CBR) mode
   * Lower bitrates reduce I/O bottlenecks but may affect quality
   * Recommended values: 1500-4000 Kbps for 720p, 4000-8000 Kbps for 1080p
   * Example: `--bitrate 2000` for 2 Mbps constant bitrate

3. **Quality Presets (`--quality-preset`):**
   * Faster presets use less CPU but produce larger files at the same bitrate
   * For maximum frame rates, use `ultrafast` or `superfast`
   * For balanced performance, use `fast` or `medium` (default)
   * Example: `--quality-preset veryfast` for better performance

### Example Configurations for High Frame Rates

For maximum frame rates on Raspberry Pi 4/5:
```bash
# Maximum performance at 720p60
rpi-lsl-stream --width 1280 --height 720 --fps 60 --codec h264 --bitrate 2000 --quality-preset ultrafast --threaded-writer

# Good performance at 1080p30
rpi-lsl-stream --width 1920 --height 1080 --fps 30 --codec h264 --bitrate 4000 --quality-preset veryfast --threaded-writer
```

If hardware-accelerated encoding is not working on your system:
```bash
# Fallback to MJPG for compatibility
rpi-lsl-stream --width 1280 --height 720 --fps 30 --codec mjpg --threaded-writer
```

### Performance Considerations:

* **Resolution vs. Frame Rate:** Lower resolutions (640x480, 1280x720) allow for higher frame rates
* **Saving to USB SSD/Flash Drive:** Use the `--output-path` option to save to a fast external drive
* **Memory/CPU Impact:** Lower resolutions, faster presets, and CBR mode all reduce CPU usage
* **Monitor Actual FPS:** Check the console output for the actual frame rate being achieved
* **Advanced:** Edit the video writer queue size with `queue_size_seconds` if you experience drops

## Rolling Buffer and Trigger Functionality

This package includes a rolling buffer system that can be used to capture footage before a trigger event occurs, ensuring you don't miss important events that happened just before recording was initiated.

### How the Rolling Buffer Works

1. When enabled (`--use-buffer`, on by default), the system continuously captures frames but only stores them in a temporary rolling buffer in RAM instead of saving to disk
2. The buffer maintains a fixed duration of recent frames (e.g., 15 seconds)
3. When a trigger event occurs, the system:
   - Saves all frames currently in the buffer (the pre-trigger footage)
   - Continues recording new frames directly to disk
4. When a stop command is received, the system:
   - Finalizes and closes the current video file
   - Returns to buffer mode, waiting for the next start trigger

### Trigger Methods

There are two ways to trigger recording when in buffer mode:

1. **Manual Trigger:**
   - Press the 't' key while the preview window is active to START recording
   - Press the 's' key while the preview window is active to STOP recording
   - Useful for testing or when monitoring the camera directly

2. **Remote Trigger via ntfy.sh:**
   - The system monitors the ntfy.sh topic "raspie_trigger" by default
   - Use the `--ntfy-topic` parameter to specify a different topic
   - Send notifications with keywords to control recording:
     - **Start recording**: Include words like "start", "begin", "record", "trigger", or "capture"
     - **Stop recording**: Include words like "stop", "end", "halt", "finish", or "terminate"
   - If no keywords are detected, the message is treated as a start command by default

### Example Usage

**Using default settings (400x400, 100fps, ntfy topic "raspie_trigger"):**
```bash
rpi-lsl-stream
```

**Set up a custom buffer size and ntfy topic:**
```bash
rpi-lsl-stream --width 1280 --height 720 --fps 30 --buffer-size 20 --ntfy-topic "my_camera_topic"
```

**Start recording remotely using curl:**
```bash
curl -d "start recording" ntfy.sh/raspie_trigger
```

**Stop recording remotely using curl:**
```bash
curl -d "stop recording" ntfy.sh/raspie_trigger
```

**Trigger with additional details:**
```bash
# Start with high priority notification
curl -H "Title: Motion Detected" -H "Tags: warning,camera" -H "Priority: high" -d "start recording" ntfy.sh/raspie_trigger

# Stop recording
curl -H "Title: Recording Complete" -d "stop recording" ntfy.sh/raspie_trigger
```

**Using only manual triggers (disable ntfy):**
```bash
rpi-lsl-stream --no-ntfy --show-preview
```
Then use 't' to start and 's' to stop recording in the preview window.

### Default Configuration

By default, the system is configured to:
- Capture at 400x400 resolution and 100fps
- Use a 20-second rolling buffer
- Listen for triggers on the "raspie_trigger" ntfy.sh topic
- Create a new video file each time recording is started/stopped
- Save files with names like `raspie_video_TIMESTAMP.mkv` and `raspie_audio_TIMESTAMP.wav`

### Buffer Size Considerations

- Higher resolution and frame rate will consume more memory in buffer mode
- The default buffer size (15 seconds) works well for most setups
- For high-resolution/high-fps recordings, you may need to reduce the buffer size
- For Raspberry Pi 4 with 8GB RAM, a 1080p30 buffer can typically hold 20-30 seconds
- For Raspberry Pi 4 with 4GB RAM, consider using 720p for longer buffers

## Video Analysis Tools

The system includes powerful tools for analyzing video recordings:

### 1. Basic Video Verification

Quickly check basic metadata about a video file:

```bash
rpi-verify-video recordings/your_video_file.mkv
```

This reports:
- Resolution
- Frame rate from metadata
- Frame count
- Calculated duration

### 2. Detailed Frame Analysis

For comprehensive analysis of frame rates and interframe intervals:

```bash
# Analyze a single video
rpi-analyze-videos recordings/your_video_file.mkv

# Analyze all videos in a directory
rpi-analyze-videos recordings/
```

This tool:
- Calculates actual frame rate by analyzing interframe intervals
- Reports detailed statistics on frame timing consistency
- Detects potential frame drops
- Generates histograms and timeline plots of frame intervals
- Exports comprehensive reports in text and visual formats

The analysis reports are saved in an `analysis_reports` subdirectory, including:
- Summary text files with all statistics
- Histogram plots showing the distribution of frame intervals
- Timeline plots showing frame timing consistency

These tools are valuable for validating recording quality and diagnosing performance issues.

## Contributing

This project was developed by Anzal (anzal.ks@gmail.com). Contributions are welcome via pull requests. 

Please ensure any contributions follow these guidelines:
1. Test thoroughly on actual Raspberry Pi hardware before submitting
2. Run in the appropriate virtual environment, never on base Python
3. Follow existing code style conventions
4. Add proper documentation for new features
5. Ensure unit tests are created or updated for your changes

For major changes, please open an issue first to discuss the proposed changes.
