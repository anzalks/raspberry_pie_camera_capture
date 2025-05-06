# Raspie Capture Examples

This directory contains example scripts demonstrating how to use the Raspie Capture system.

## Audio and Video Visualizers

The system now supports real-time visualization for both video and audio:

- **Video Preview**: Shows the camera feed in real-time
- **Audio Visualization**: Displays audio waveform and spectrum analyzer

### Running with CPU Core Affinity

For optimal performance, you can assign different processing tasks to specific CPU cores. This ensures that intensive operations like video encoding don't interfere with each other.

To run the example with visualizers on different cores:

```bash
python examples/run_with_visualizers.py
```

This script automatically:
- Detects the number of available CPU cores
- Allocates cores for different tasks (capture, encoding, visualization)
- Enables both audio and video previews
- Sets up a rolling buffer for pre-trigger recording

### Manual Core Assignment

You can manually assign CPU cores using these command-line options:

```bash
python -m raspberry_pi_lsl_stream.cli \
    --enable-audio \
    --show-preview \
    --show-audio-preview \
    --video-capture-core 1 \
    --video-writer-core 2 \
    --video-vis-core 3 \
    --audio-capture-core 0 \
    --audio-writer-core 2 \
    --audio-vis-core 4
```

### Visualization Features

#### Audio Visualization
- **Waveform Display**: Shows the real-time audio waveform
- **Spectrum Analyzer**: Displays a frequency spectrum waterfall view
- **Level Meter**: Shows audio levels with color indicators (green/yellow/red)

#### Video Preview
- **Live Camera Feed**: Shows what the camera is capturing
- **Manual Trigger Controls**: Press 't' to start recording, 's' to stop

### Notes on Performance

- The visualization and buffer features are optional and can be disabled
- CPU core affinity requires the `psutil` package to be installed
- On Raspberry Pi with limited cores, assign critical functions (capture, writing) to different cores
- For development/testing, you can reduce frame rates and resolution to decrease CPU load 