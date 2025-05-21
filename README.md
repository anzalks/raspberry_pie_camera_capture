# Raspberry Pi Camera LSL Streamer

> **Note:** You are currently viewing the `vanila-lsl-stream` branch. This branch provides the core LSL streaming functionality with a simplified codebase.

A Python package to capture video frames from a Raspberry Pi camera and stream them over LabStreamingLayer (LSL).

**Author:** Anzal  
**Contact:** anzal.ks@gmail.com

## Features

*   Captures frames using `picamera2` or a standard webcam (`OpenCV`).
*   Captures audio from USB microphones using `sounddevice`.
*   Saves captured video to a local file (`.mkv`) in the `recordings` folder.
*   Saves captured audio to a separate local file (`.wav`) in the `recordings` folder.
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
*   **Video Analysis Tools**: Includes utilities to analyze frame rates and interframe intervals.

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

### Environment Check

Before running the system, you can verify your environment has all necessary components:

```bash
# Check environment and create required directories
rpi-check-env
```

This command will:
- Verify all required Python packages are installed
- Check for required system libraries
- Create the `recordings` and `analysis_reports` directories if they don't exist
- Test camera detection
- Verify LSL is working properly

### Running the Streamer

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
*   `--camera-index`: Camera to use: 'auto' (default: PiCam then Webcams), 'pi' (PiCam only), or an integer index (e.g., 0, 1) for a specific webcam.
*   `--output-path`: Directory path to save the output files (default: 'recordings').
*   `--codec`: Preferred video codec ('h264', 'h265', 'mjpg', 'auto'). Default 'auto' attempts hardware-accelerated codecs first.
*   `--bitrate`: Constant bitrate in Kbps (0=codec default). Setting this enables CBR mode.
*   `--quality-preset`: Encoding quality preset (trade-off between speed and compression efficiency).
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
*   `--ntfy-topic`: The ntfy.sh topic to subscribe to for recording triggers (default: "rpi_camera_trigger").
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

```bash
# Default: Auto-detect camera (PiCam first), 400x400, 100fps, save to recordings/
rpi-lsl-stream

# Auto-detect camera, 1080p (1920x1080), 30fps, run indefinitely
rpi-lsl-stream --width 1920 --height 1080 --fps 30

# Auto-detect camera, 720p (1280x720), 60fps, run for 2 minutes (120s)
rpi-lsl-stream --width 1280 --height 720 --fps 60 --duration 120

# Auto-detect camera, default settings, show preview window for 30 seconds
rpi-lsl-stream --show-preview --duration 30

# Enable audio capture with default settings (48kHz, 16-bit, mono)
rpi-lsl-stream --enable-audio

# High-quality audio capture (48kHz, 24-bit, stereo)
rpi-lsl-stream --enable-audio --sample-rate 48000 --bit-depth 24 --channels 2
```

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

## Troubleshooting

*   **Camera not detected:** Ensure the camera is securely connected and enabled via `raspi-config`. Also check the output of `libcamera-hello --list-cameras`.
*   **`picamera2` not found (after running setup):** Make sure you activated the correct virtual environment (`source .venv/bin/activate`) created by the setup script.
*   **Video Frame Rate Issues:** Use the `rpi-analyze-videos` tool to diagnose issues with frame rates or dropped frames.
*   **No video files being saved:** Verify the `recordings` directory exists and has proper write permissions.
*   **Permission errors:** Check permissions for accessing camera devices (`/dev/video*`).
*   **Performance issues:** Lower resolution or frame rate might be necessary depending on the Pi model and workload. Using `--threaded-writer` is recommended for high-resolution/FPS streams.

## LSL Stream Details

**Note:** The current implementation streams only the frame number, not the full video frame data. The video is saved locally to a file.

*   **Name:** As specified by `--video-stream-name` (for video) or `--audio-stream-name` (for audio).
*   **Type:** 'FrameCounter' (Indicates only frame numbers are streamed)
*   **Channels:** 1 (for the frame number).
*   **Format:** `cf_int32` (32-bit integer for the frame number).
*   **Nominal Rate:** As specified by `--fps` (or the actual rate achieved by the camera).
*   **Source ID:** As specified by `--source-id`.

**Timestamp Information:**

*   **Source:** Timestamps are generated using `pylsl.local_clock()`.
*   **Timing:** For each frame, the LSL timestamp is captured *immediately before* the call to acquire the frame data from the camera.

## Project Structure

The project uses a modular approach:

- `camera_stream.py`: Core video capture and streaming functionality
- `audio_stream.py`: Audio capture and streaming functionality
- `buffer_trigger.py`: Rolling buffer and notification trigger system
- `cli.py`: Command-line interface and argument parsing
- `analyze_videos.py`: Video analysis utility
- `verify_video.py`: Simple video metadata verification

## Contributing

This project was developed by Anzal (anzal.ks@gmail.com). Contributions are welcome via pull requests.
