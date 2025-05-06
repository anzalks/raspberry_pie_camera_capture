"""Module for capturing audio from USB microphones with buffer and LSL integration."""

import os
import time
import threading
import queue
import numpy as np
import collections
import datetime
import wave
import pylsl
import cv2
from typing import Optional, Tuple, Deque, List, Dict, Any, Union

# These will be imported at runtime
# import sounddevice as sd
# from scipy.io import wavfile

# Try to import psutil for CPU affinity management
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    print("Warning: psutil not available. CPU core affinity will not be managed.")


class AudioVisualizer:
    """Real-time audio waveform and spectrum visualizer."""
    
    def __init__(self, sample_rate=48000, chunk_size=1024, channels=1, 
                 window_name="Audio Visualizer", window_size=(800, 400)):
        """Initialize the audio visualizer.
        
        Args:
            sample_rate: Audio sampling rate in Hz
            chunk_size: Number of samples per audio chunk
            channels: Number of audio channels (1=mono, 2=stereo)
            window_name: Name of the visualization window
            window_size: Size of the visualization window (width, height)
        """
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.channels = channels
        self.window_name = window_name
        self.window_width, self.window_height = window_size
        
        # Visualization state
        self.running = False
        self.vis_thread = None
        self.audio_data_queue = queue.Queue(maxsize=10)  # Buffer recent audio chunks
        self.lock = threading.Lock()
        
        # Visualization buffers and settings
        self.waveform_buffer = np.zeros((chunk_size, channels))
        self.spectrum_history = np.zeros((50, chunk_size//2))  # Store 50 frames of spectrum data
        self.spectrum_pos = 0
        self.db_range = 80  # dB range for spectrum display
        self.cpu_core = None  # CPU core for visualization (set later)
    
    def start(self, cpu_core=None):
        """Start the visualization in a separate thread.
        
        Args:
            cpu_core: Specific CPU core to use for visualization
        """
        if self.running:
            return
            
        self.running = True
        self.cpu_core = cpu_core
        
        # Create window
        cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(self.window_name, self.window_width, self.window_height)
        
        # Start visualization thread
        self.vis_thread = threading.Thread(
            target=self._visualization_thread,
            name="AudioVisualizationThread",
            daemon=True
        )
        self.vis_thread.start()
        print(f"Audio visualizer started on core {cpu_core if cpu_core is not None else 'any'}")
    
    def stop(self):
        """Stop the visualization."""
        if not self.running:
            return
            
        self.running = False
        
        # Wait for thread to end
        if self.vis_thread and self.vis_thread.is_alive():
            self.vis_thread.join(timeout=1.0)
        
        # Destroy window
        try:
            cv2.destroyWindow(self.window_name)
        except:
            pass
        
        print("Audio visualizer stopped")
    
    def update(self, audio_chunk):
        """Update with new audio data.
        
        Args:
            audio_chunk: NumPy array containing audio data
        """
        if not self.running:
            return
            
        try:
            # Put in queue but don't block if full
            self.audio_data_queue.put(audio_chunk.copy(), block=False)
        except queue.Full:
            # Skip frame if queue is full
            pass
    
    def _visualization_thread(self):
        """Thread function that handles visualization."""
        # Set CPU affinity if requested and available
        if PSUTIL_AVAILABLE and self.cpu_core is not None:
            try:
                p = psutil.Process()
                p.cpu_affinity([self.cpu_core])
                print(f"Set visualizer thread affinity to core {self.cpu_core}")
            except Exception as e:
                print(f"Failed to set CPU affinity: {e}")
        
        # Prepare visualization canvas
        canvas = np.zeros((self.window_height, self.window_width, 3), dtype=np.uint8)
        waveform_height = self.window_height // 2
        spectrum_height = self.window_height // 2
        
        # Processing loop
        while self.running:
            try:
                # Get latest audio data
                try:
                    audio_chunk = self.audio_data_queue.get(timeout=0.05)
                    
                    # Update internal buffers with new data
                    with self.lock:
                        self.waveform_buffer = audio_chunk
                        
                        # Compute spectrum
                        if audio_chunk.ndim > 1 and audio_chunk.shape[1] > 1:
                            # Average channels for spectrum calculation
                            data_for_fft = np.mean(audio_chunk, axis=1)
                        else:
                            data_for_fft = audio_chunk.flatten()
                        
                        # Apply window function to reduce spectral leakage
                        windowed_data = data_for_fft * np.hanning(len(data_for_fft))
                        
                        # Calculate FFT
                        fft_data = np.abs(np.fft.rfft(windowed_data))
                        
                        # Convert to dB scale (with floor)
                        fft_data = 20 * np.log10(fft_data + 1e-10)
                        
                        # Normalize to 0-1 range for display
                        fft_data = np.clip((fft_data + self.db_range) / self.db_range, 0, 1)
                        
                        # Store in history buffer
                        self.spectrum_history[self.spectrum_pos] = fft_data
                        self.spectrum_pos = (self.spectrum_pos + 1) % self.spectrum_history.shape[0]
                    
                    self.audio_data_queue.task_done()
                except queue.Empty:
                    # No new data, just refresh the display
                    pass
                
                # Clear canvas
                canvas.fill(0)
                
                # Draw waveform
                with self.lock:
                    # Get a copy of the current waveforms
                    waveform_data = self.waveform_buffer.copy()
                
                # Process the waveform for each channel
                for ch in range(min(self.channels, 2)):  # Limit to 2 channels for display
                    if waveform_data.ndim > 1:
                        channel_data = waveform_data[:, ch]
                    else:
                        channel_data = waveform_data
                    
                    # Normalize to -1 to 1
                    max_val = np.max(np.abs(channel_data)) or 1
                    normalized = channel_data / max_val
                    
                    # Scale to fit in window
                    scaled = normalized * (waveform_height // 2 - 10)
                    
                    # Draw the waveform
                    color = (0, 255, 0) if ch == 0 else (0, 255, 255)  # Green for ch1, Yellow for ch2
                    points = []
                    
                    for i, val in enumerate(scaled):
                        x = int(i * self.window_width / len(scaled))
                        y = int(waveform_height // 2 - val)
                        points.append((x, y))
                    
                    for i in range(1, len(points)):
                        cv2.line(canvas, points[i-1], points[i], color, 1)
                
                # Draw spectrum
                with self.lock:
                    # Get a copy of the current spectrum
                    spectrum_data = self.spectrum_history.copy()
                
                # Draw spectrum as a waterfall display (scrolling spectrogram)
                for i in range(spectrum_data.shape[0]):
                    row_idx = (self.spectrum_pos - 1 - i) % spectrum_data.shape[0]
                    row = spectrum_data[row_idx]
                    
                    for j in range(min(len(row), 256)):  # Limit to 256 frequency bins
                        # Map the frequency bin to x position
                        x = int(j * self.window_width / 256)
                        
                        # Calculate color based on magnitude (blue to red)
                        magnitude = row[j]
                        b = int(255 * (1 - magnitude))
                        r = int(255 * magnitude)
                        g = int(r * 0.6)  # Some green mixed in
                        
                        # Draw a colored pixel for each frequency bin
                        y = waveform_height + i * (spectrum_height // spectrum_data.shape[0])
                        if 0 <= x < self.window_width and 0 <= y < self.window_height:
                            canvas[y, x] = (b, g, r)
                
                # Draw dividing line between waveform and spectrum
                cv2.line(canvas, (0, waveform_height), (self.window_width, waveform_height), (128, 128, 128), 1)
                
                # Display level meter
                with self.lock:
                    if self.waveform_buffer.size > 0:
                        if self.waveform_buffer.ndim > 1:
                            level = np.max(np.abs(np.mean(self.waveform_buffer, axis=1)))
                        else:
                            level = np.max(np.abs(self.waveform_buffer))
                    else:
                        level = 0
                
                # Draw level meter
                meter_width = int(level * self.window_width)
                meter_color = (0, 255, 0)  # Green
                if level > 0.8:
                    meter_color = (0, 0, 255)  # Red (clipping warning)
                elif level > 0.5:
                    meter_color = (0, 255, 255)  # Yellow (approaching peaks)
                
                cv2.rectangle(canvas, (0, self.window_height - 10), 
                             (meter_width, self.window_height), meter_color, -1)
                
                # Show the visualization
                cv2.imshow(self.window_name, canvas)
                key = cv2.waitKey(1)
                
                # Check for quit key (q or ESC)
                if key in [ord('q'), 27]:  # 27 is ESC key
                    break
                
            except Exception as e:
                print(f"Error in visualization thread: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(0.5)  # Avoid tight loop on error
        
        # Clean up
        try:
            cv2.destroyWindow(self.window_name)
        except:
            pass


class LSLAudioStreamer:
    """Captures audio from a USB microphone and streams timestamps via LSL.
    
    Features:
    - Rolling buffer to capture audio before triggers
    - Synchronized with video triggers (ntfy.sh or manual)
    - Sends LSL markers with audio chunks for synchronization
    - Processes audio capture on a separate thread/core
    """
    
    def __init__(
        self,
        sample_rate: int = 48000,
        channels: int = 1,
        device_index: Union[int, str] = None,
        stream_name: str = 'RaspieAudio',
        source_id: str = 'RaspieCapture_Audio',
        output_path: Optional[str] = None,
        bit_depth: int = 16,
        buffer_size_seconds: int = 20,
        use_buffer: bool = True,
        chunk_size: int = 1024,
        threaded_writer: bool = True,
        save_audio: bool = True,
        audio_format: str = 'wav',
        show_preview: bool = False,
        capture_cpu_core: Optional[int] = None,
        writer_cpu_core: Optional[int] = None,
        visualizer_cpu_core: Optional[int] = None
    ):
        """Initialize the audio streamer.
        
        Args:
            sample_rate: Sampling frequency in Hz
            channels: Number of audio channels (1=mono, 2=stereo)
            device_index: Audio device index or name
            stream_name: LSL stream name
            source_id: Unique LSL source ID
            output_path: Directory to save audio files
            bit_depth: Audio bit depth (16 or 24)
            buffer_size_seconds: Size of rolling buffer in seconds
            use_buffer: Enable rolling buffer mode
            chunk_size: Audio processing chunk size
            threaded_writer: Use a separate thread for writing audio
            save_audio: Whether to save audio to file
            audio_format: Audio file format ('wav' only currently supported)
            show_preview: Whether to show audio visualization
            capture_cpu_core: Specific CPU core for capture thread
            writer_cpu_core: Specific CPU core for writer thread
            visualizer_cpu_core: Specific CPU core for visualizer thread
        """
        try:
            # Import audio libraries on demand to prevent import errors
            # on systems without audio dependencies
            import sounddevice as sd
            self.sd = sd
        except ImportError:
            raise RuntimeError(
                "sounddevice library not found. Please install with: "
                "pip install sounddevice numpy scipy"
            )
        
        # Core parameters
        self.sample_rate = sample_rate
        self.channels = channels
        self.device_index = device_index
        self.bit_depth = bit_depth
        self.chunk_size = chunk_size
        self.save_audio = save_audio
        self.audio_format = audio_format
        self.show_preview = show_preview
        
        # CPU core assignments
        self.capture_cpu_core = capture_cpu_core
        self.writer_cpu_core = writer_cpu_core
        self.visualizer_cpu_core = visualizer_cpu_core
        
        # Validate bit depth
        if self.bit_depth not in [16, 24, 32]:
            raise ValueError("Bit depth must be 16, 24, or 32")
        
        # Set numpy dtype based on bit depth
        if bit_depth == 16:
            self.dtype = np.int16
            self.max_value = 32767
        elif bit_depth == 24:
            # 24-bit audio is handled as 32-bit with scale adjustment
            self.dtype = np.int32
            self.max_value = 8388607
        else:  # bit_depth == 32
            self.dtype = np.int32
            self.max_value = 2147483647
        
        # Buffer settings
        self.use_buffer = use_buffer
        self.buffer_size_seconds = buffer_size_seconds
        self.buffer_size_samples = int(self.sample_rate * self.buffer_size_seconds)
        self.is_recording = False
        
        # LSL stream configuration
        self.stream_name = stream_name
        self.source_id = source_id
        self._setup_lsl_outlet()
        
        # File saving configuration
        self.output_path = output_path or os.getcwd()
        os.makedirs(self.output_path, exist_ok=True)
        self.auto_output_filename = None
        
        # Threading configuration
        self.threaded_writer = threaded_writer
        self.running = False
        self.recording_lock = threading.Lock()
        
        # Set up buffers and queues
        self.audio_buffer = collections.deque(maxlen=self.buffer_size_samples)
        self.write_queue = queue.Queue(maxsize=100)  # Limit queue size
        
        # Stats tracking
        self.frame_count = 0
        self.frames_written = 0
        self.frames_dropped = 0
        
        # Thread handles
        self.capture_thread = None
        self.writer_thread = None
        
        # Visualizer (optional)
        self.visualizer = None
        if self.show_preview:
            self.visualizer = AudioVisualizer(
                sample_rate=self.sample_rate,
                chunk_size=self.chunk_size,
                channels=self.channels,
                window_name=f"Audio Visualizer: {self.stream_name}"
            )
        
        # Audio device detection and info
        self._detect_audio_device()
    
    def _detect_audio_device(self):
        """Detect and select audio device."""
        try:
            # Get all devices
            devices = self.sd.query_devices()
            
            # Print available devices for debugging
            print("\nAvailable audio devices:")
            for i, device in enumerate(devices):
                print(f"  {i}: {device['name']} (Channels: {device['max_input_channels']})")
            
            # If no specific device requested, try to find a suitable one
            if self.device_index is None:
                for i, device in enumerate(devices):
                    if device['max_input_channels'] > 0:
                        self.device_index = i
                        break
                
                if self.device_index is None:
                    raise RuntimeError("No input audio devices found")
            
            # If string name provided, find the matching device
            if isinstance(self.device_index, str):
                found = False
                for i, device in enumerate(devices):
                    if self.device_index.lower() in device['name'].lower():
                        self.device_index = i
                        found = True
                        break
                if not found:
                    raise ValueError(f"No audio device matching '{self.device_index}' found")
            
            # Verify selected device
            device_info = self.sd.query_devices(self.device_index)
            if device_info['max_input_channels'] < self.channels:
                raise ValueError(f"Device {self.device_index} doesn't support {self.channels} channels")
            
            # Store device info
            self.device_name = device_info['name']
            self.device_info = device_info
            print(f"Selected audio device: {self.device_name} (index: {self.device_index})")
            
        except Exception as e:
            raise RuntimeError(f"Error detecting audio device: {e}")
    
    def _setup_lsl_outlet(self):
        """Set up LSL stream outlet for audio data markers."""
        # Create LSL stream info and outlet
        # We'll stream audio chunk indices and timestamps for synchronization
        # Channel format: [chunk_index, timestamp]
        info = pylsl.StreamInfo(
            name=self.stream_name,
            type='AudioChunkMarker',
            channel_count=2,
            nominal_srate=self.sample_rate / self.chunk_size,
            channel_format='cf_double',
            source_id=self.source_id
        )
        
        # Add metadata to the LSL stream
        info.desc().append_child_value("device_name", self.device_name if hasattr(self, 'device_name') else "Unknown")
        info.desc().append_child_value("sampling_rate", str(self.sample_rate))
        info.desc().append_child_value("channels", str(self.channels))
        info.desc().append_child_value("bit_depth", str(self.bit_depth))
        info.desc().append_child_value("acquisition_software", "RaspieCapture")
        
        # Create channel labels
        channels = info.desc().append_child("channels")
        channels.append_child("channel").append_child_value("label", "ChunkIndex")
        channels.append_child("channel").append_child_value("label", "Timestamp")
        
        # Create LSL outlet
        self.outlet = pylsl.StreamOutlet(info)
        print(f"Created LSL outlet: {self.stream_name}")
    
    def start(self):
        """Start audio capture."""
        if self.running:
            return
        
        self.running = True
        
        # Start the visualizer if preview is enabled
        if self.show_preview and self.visualizer:
            self.visualizer.start(cpu_core=self.visualizer_cpu_core)
        
        # Start the audio capture thread
        self.capture_thread = threading.Thread(
            target=self._audio_capture_thread,
            name="AudioCaptureThread",
            daemon=True
        )
        self.capture_thread.start()
        
        # Start writer thread if using threaded writer
        if self.threaded_writer and self.save_audio:
            self.writer_thread = threading.Thread(
                target=self._audio_writer_thread, 
                name="AudioWriterThread",
                daemon=True
            )
            self.writer_thread.start()
        
        print(f"Audio capture started: {self.sample_rate} Hz, {self.channels} channels, {self.bit_depth}-bit")
    
    def stop(self):
        """Stop audio capture and clean up resources."""
        if not self.running:
            return
        
        # Stop capture thread
        self.running = False
        
        # Close any open audio files
        self._close_current_file()
        
        # Stop visualizer if enabled
        if self.show_preview and self.visualizer:
            self.visualizer.stop()
        
        # Wait for threads to clean up
        if self.capture_thread and self.capture_thread.is_alive():
            self.capture_thread.join(timeout=2.0)
            if self.capture_thread.is_alive():
                print("Warning: Audio capture thread did not exit cleanly")
        
        if self.writer_thread and self.writer_thread.is_alive():
            # Put None in the queue to signal writer to exit
            try:
                self.write_queue.put(None, block=False)
            except queue.Full:
                pass
            
            self.writer_thread.join(timeout=2.0)
            if self.writer_thread.is_alive():
                print("Warning: Audio writer thread did not exit cleanly")
        
        print("Audio capture stopped")
    
    def _set_thread_affinity(self, thread_name, cpu_core):
        """Set CPU affinity for the current thread if psutil is available."""
        if not PSUTIL_AVAILABLE or cpu_core is None:
            return
            
        try:
            p = psutil.Process()
            p.cpu_affinity([cpu_core])
            print(f"Set {thread_name} affinity to core {cpu_core}")
        except Exception as e:
            print(f"Failed to set CPU affinity for {thread_name}: {e}")
    
    def _audio_capture_thread(self):
        """Thread function for continuous audio capture."""
        # Set CPU affinity if requested
        self._set_thread_affinity("audio capture thread", self.capture_cpu_core)
        
        try:
            # Configure audio capture callback
            def audio_callback(indata, frames, time_info, status):
                """Callback function for audio capture."""
                if status:
                    print(f"Audio status: {status}")
                
                # Get current timestamp
                timestamp = pylsl.local_clock()
                
                # Process the captured audio chunk
                audio_chunk = indata.copy()  # Make a copy to avoid buffer reuse issues
                
                # Always append to the rolling buffer
                if self.use_buffer:
                    for sample in audio_chunk:
                        self.audio_buffer.append(sample)
                
                # If visualization is enabled, update the visualizer
                if self.show_preview and self.visualizer:
                    self.visualizer.update(audio_chunk)
                
                # If we're recording, send to write queue
                if self.is_recording and self.save_audio:
                    # Either save directly or put in queue for threaded writer
                    if self.threaded_writer:
                        try:
                            self.write_queue.put((audio_chunk, timestamp), block=False)
                        except queue.Full:
                            self.frames_dropped += 1
                    else:
                        self._write_audio_chunk(audio_chunk, timestamp)
                
                # Push sample index and timestamp to LSL
                self.outlet.push_sample([self.frame_count, timestamp])
                self.frame_count += 1
            
            # Create and start the input stream
            self.audio_stream = self.sd.InputStream(
                samplerate=self.sample_rate,
                blocksize=self.chunk_size,
                device=self.device_index,
                channels=self.channels,
                dtype=self.dtype,
                callback=audio_callback
            )
            
            self.audio_stream.start()
            
            # Keep thread alive while running flag is True
            while self.running:
                time.sleep(0.1)
                
        except Exception as e:
            print(f"Audio capture error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # Clean up audio stream
            if hasattr(self, 'audio_stream') and self.audio_stream:
                self.audio_stream.stop()
                self.audio_stream.close()
    
    def _audio_writer_thread(self):
        """Thread function for writing audio chunks to file."""
        # Set CPU affinity if requested
        self._set_thread_affinity("audio writer thread", self.writer_cpu_core)
        
        while self.running:
            try:
                # Get chunk from queue (with timeout to check running flag periodically)
                item = self.write_queue.get(timeout=0.5)
                
                # None is a signal to exit
                if item is None:
                    break
                
                # Unpack audio chunk and timestamp
                audio_chunk, timestamp = item
                
                # Write the chunk to file
                self._write_audio_chunk(audio_chunk, timestamp)
                
                # Mark as done
                self.write_queue.task_done()
                
            except queue.Empty:
                # Timeout, check running flag and continue
                continue
            except Exception as e:
                print(f"Audio writer error: {e}")
    
    def _write_audio_chunk(self, audio_chunk, timestamp):
        """Write an audio chunk to the current file."""
        if self.save_audio and hasattr(self, 'audio_file') and self.audio_file:
            # Write raw PCM data
            self.audio_file.writeframes(audio_chunk.tobytes())
            self.frames_written += 1
    
    def _create_new_file(self):
        """Create a new audio file for recording."""
        if not self.save_audio:
            return
        
        # Create filename based on current time
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"raspie_audio_{timestamp}.wav"
        filepath = os.path.join(self.output_path, filename)
        
        # Create WAV file
        self.audio_file = wave.open(filepath, 'wb')
        self.audio_file.setnchannels(self.channels)
        self.audio_file.setsampwidth(self.bit_depth // 8)
        self.audio_file.setframerate(self.sample_rate)
        
        # Store filename
        self.auto_output_filename = filepath
        print(f"Created audio file: {filepath}")
    
    def _close_current_file(self):
        """Close the current audio file."""
        with self.recording_lock:
            if hasattr(self, 'audio_file') and self.audio_file:
                self.audio_file.close()
                self.audio_file = None
                print(f"Closed audio file: {self.auto_output_filename}")
    
    def start_recording(self):
        """Start recording audio to file.
        
        If buffer mode is enabled, dumps the buffer first.
        """
        with self.recording_lock:
            if self.is_recording:
                return  # Already recording
            
            # Create new file
            self._create_new_file()
            
            # If using buffer, write buffer contents first
            if self.use_buffer and self.save_audio:
                buffer_array = np.array(list(self.audio_buffer))
                if len(buffer_array) > 0:
                    # Write buffer to file
                    if hasattr(self, 'audio_file') and self.audio_file:
                        self.audio_file.writeframes(buffer_array.tobytes())
                        print(f"Wrote {len(buffer_array)} buffered audio samples")
            
            # Set recording flag
            self.is_recording = True
            print("Audio recording started")
    
    def stop_recording(self):
        """Stop recording audio to file."""
        with self.recording_lock:
            if not self.is_recording:
                return  # Not recording
            
            # Clear recording flag
            self.is_recording = False
            
            # Close file
            self._close_current_file()
            print("Audio recording stopped")
    
    def get_info(self) -> Dict[str, Any]:
        """Get information about the audio stream."""
        return {
            'device_name': self.device_name if hasattr(self, 'device_name') else "Unknown",
            'device_index': self.device_index,
            'sample_rate': self.sample_rate,
            'channels': self.channels,
            'bit_depth': self.bit_depth,
            'stream_name': self.stream_name,
            'source_id': self.source_id,
            'output_path': self.output_path,
            'buffer_size_seconds': self.buffer_size_seconds,
            'use_buffer': self.use_buffer,
            'is_recording': self.is_recording,
            'threaded_writer': self.threaded_writer,
            'show_preview': self.show_preview,
            'capture_cpu_core': self.capture_cpu_core,
            'writer_cpu_core': self.writer_cpu_core,
            'visualizer_cpu_core': self.visualizer_cpu_core
        }
    
    def get_frame_count(self) -> int:
        """Get the total number of audio chunks processed."""
        return self.frame_count
    
    def get_frames_written(self) -> int:
        """Get the number of audio chunks written to file."""
        return self.frames_written
    
    def get_frames_dropped(self) -> int:
        """Get the number of audio chunks dropped."""
        return self.frames_dropped 