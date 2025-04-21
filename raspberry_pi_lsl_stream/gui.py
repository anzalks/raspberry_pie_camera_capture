"""PySide6 GUI for controlling and viewing the LSL Camera Stream.

This GUI provides a simple interface to start/stop the LSLCameraStreamer,
view the video feed (either from PiCamera or Webcam via the streamer class),
and display status information.
"""

import sys
import time
# Import necessary PySide6 components for widgets, layout, images, and timers.
from PySide6.QtWidgets import (QApplication, QWidget, QLabel, QVBoxLayout, QPushButton,
                             QHBoxLayout, QSizePolicy, QGridLayout)
from PySide6.QtGui import QPixmap, QImage
from PySide6.QtCore import Qt, QTimer, Slot

# Attempt to import the LSLCameraStreamer class.
# This assumes camera_stream.py is in the same package directory.
try:
    from .camera_stream import LSLCameraStreamer
except ImportError:
    # If the import fails (e.g., running GUI without full installation or missing dependencies),
    # define a dummy class. This allows the GUI to load and display its structure,
    # although the streaming functionality will not work.
    print("Warning: Could not import LSLCameraStreamer. Ensure camera_stream.py is accessible and dependencies are met.")
    class LSLCameraStreamer:
        def __init__(self, *args, **kwargs): 
            print("Using dummy LSLCameraStreamer: Streaming will not function.")
            self._is_running = False # Need this attribute for GUI checks
        def start(self): pass
        def stop(self): pass
        def capture_frame(self): return None, None
        def get_info(self): return { # Provide default structure for get_info
            "stream_name": "N/A", "source_id": "N/A", "width": 0, "height": 0, 
            "lsl_pixel_format": "N/A", "actual_fps": 0.0, "source_type": "N/A",
            "is_running": False, "camera_model": "N/A"
        }
        def get_frame_count(self): return 0


class StreamViewerWindow(QWidget):
    """Main window class for the LSL Stream Viewer GUI."""
    def __init__(self, streamer_args=None):
        """
        Initializes the GUI window, layout, widgets, and timer.

        Args:
            streamer_args (dict, optional): Dictionary of arguments to be passed
                                            to the LSLCameraStreamer constructor
                                            when the stream is started.
                                            Defaults to an empty dict.
        """
        super().__init__()
        # Store arguments intended for the streamer (e.g., width, fps, use_webcam)
        self.streamer_args = streamer_args if streamer_args else {}
        self.streamer = None # Holds the active LSLCameraStreamer instance
        
        # QTimer used to periodically call update_frame for live video display
        self.capture_timer = QTimer(self)
        self.capture_timer.timeout.connect(self.update_frame) # Connect timer timeout signal to update_frame slot
        
        # Variables for calculating and displaying UI update FPS
        self.last_frame_time = time.time()
        self.frame_update_count = 0
        self.calculated_fps = 0.0

        # Build the user interface
        self.init_ui()
        
        # Optional: Could attempt to start stream automatically on launch.
        # self.start_stream() 

    def init_ui(self):
        """Sets up the layout and widgets for the GUI window."""
        self.setWindowTitle("LSL Camera Stream Viewer")
        self.setGeometry(100, 100, 800, 600) # Initial position (x, y) and size (width, height)

        # Main vertical layout for the window
        main_layout = QVBoxLayout(self)

        # --- Video Display Area ---
        # QLabel will be used to display video frames as QPixmap images.
        self.video_label = QLabel("Video feed will appear here")
        self.video_label.setAlignment(Qt.AlignCenter) # Center placeholder text
        # Set size policy to allow the label to expand/shrink with the window
        self.video_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        # Basic styling for the video area
        self.video_label.setStyleSheet("border: 1px solid black; background-color: #333; color: white;")
        main_layout.addWidget(self.video_label, stretch=1) # Allow video label to take up more vertical space

        # --- Control Buttons --- 
        control_layout = QHBoxLayout() # Horizontal layout for buttons
        self.start_button = QPushButton("Start Stream")
        self.start_button.clicked.connect(self.start_stream) # Connect button click to start_stream method
        self.stop_button = QPushButton("Stop Stream")
        self.stop_button.clicked.connect(self.stop_stream) # Connect button click to stop_stream method
        self.stop_button.setEnabled(False) # Stop button is disabled until stream starts
        
        control_layout.addWidget(self.start_button)
        control_layout.addWidget(self.stop_button)
        control_layout.addStretch(1) # Add stretchable space to push buttons to the left
        main_layout.addLayout(control_layout)

        # --- Status Information Grid ---
        status_layout = QGridLayout() # Grid layout for status labels
        self.status_labels = {} # Dictionary to hold references to the value QLabels
        
        # Define the labels and their corresponding keys for the status_labels dictionary
        labels_to_create = [
            # (Display Text, Dictionary Key, Default Value)
            ("Stream Name:", "stream_name", "N/A"), 
            ("Source ID:", "source_id", "N/A"),
            ("Resolution:", "resolution", "N/A"),
            ("Format:", "lsl_format", "N/A"),
            ("Nominal FPS:", "nominal_fps", "N/A"),
            ("Source Type:", "source_type", "N/A"),
            ("LSL Timestamp:", "lsl_time", "N/A"),
            ("Frames Sent (LSL):", "frames_sent", "N/A"),
            ("Display FPS (UI):", "display_fps", "N/A"),
            ("Status:", "run_status", "Stopped")
        ]

        # Create and add descriptive labels and value labels to the grid layout
        row = 0
        col = 0
        max_cols = 3 # Number of columns for status info
        for label_text, key, default in labels_to_create:
            desc_label = QLabel(label_text)
            value_label = QLabel(default)
            self.status_labels[key] = value_label # Store reference to the value label
            # Add description label and value label to the grid
            status_layout.addWidget(desc_label, row, col * 2)
            status_layout.addWidget(value_label, row, col * 2 + 1)
            col += 1
            # Move to the next row if the current row is full
            if col >= max_cols:
                col = 0
                row += 1
        
        main_layout.addLayout(status_layout)

        # Set the main layout for the QWidget window
        self.setLayout(main_layout)

    # @Slot decorator indicates this method is a Qt slot, connectable to signals.
    @Slot()
    def start_stream(self):
        """Slot method called when the 'Start Stream' button is clicked."""
        print("Attempting to start stream...")
        # Only start if no streamer instance currently exists
        if self.streamer is None:
            try:
                # Instantiate the LSLCameraStreamer using stored arguments.
                print(f"Initializing streamer with args: {self.streamer_args}")
                self.streamer = LSLCameraStreamer(**self.streamer_args) 
                
                # Start the camera and LSL stream.
                self.streamer.start()
                
                # Check if the streamer actually started successfully.
                if not self.streamer._is_running:
                    print("Streamer failed to start (check logs/camera).")
                    self.streamer = None # Reset if start failed
                    self.status_labels["run_status"].setText("Error starting")
                    return
                    
                # Update UI state for running stream
                self.status_labels["run_status"].setText("Running")
                self.start_button.setEnabled(False) # Disable start button
                self.stop_button.setEnabled(True)   # Enable stop button
                self.update_static_info() # Update labels with info from the streamer
                
                # Start the QTimer to trigger frame updates.
                # A timeout of 0 means the timer will trigger as often as possible (event loop allows).
                self.capture_timer.start(0) 
                
                # Reset FPS calculation variables
                self.last_frame_time = time.time()
                self.frame_update_count = 0
                self.calculated_fps = 0.0
                print("Stream started, frame update timer activated.")
                
            except Exception as e:
                # Handle errors during streamer instantiation or start.
                print(f"Error creating or starting streamer: {e}")
                self.status_labels["run_status"].setText(f"Error: {e}")
                self.streamer = None # Ensure streamer reference is cleared on error
                self.start_button.setEnabled(True) # Re-enable start button
                self.stop_button.setEnabled(False)
        else:
            # Should not happen if UI state is correct, but log it.
            print("Streamer instance already exists. Stop the current stream first.")

    @Slot()
    def stop_stream(self):
        """Slot method called when the 'Stop Stream' button is clicked or window closes."""
        print("Stopping stream...")
        # Stop the QTimer that triggers frame updates.
        self.capture_timer.stop()
        
        # If a streamer instance exists, call its stop method.
        if self.streamer:
            self.streamer.stop() # This handles camera release and LSL cleanup.
            self.streamer = None # Clear the reference to the streamer object.
            
        # Update UI state for stopped stream
        self.start_button.setEnabled(True)  # Enable start button
        self.stop_button.setEnabled(False) # Disable stop button
        self.status_labels["run_status"].setText("Stopped")
        self.video_label.setText("Video feed stopped.") # Clear video display area
        self.video_label.setStyleSheet("border: 1px solid black; background-color: #333; color: white;") # Reset style
        print("Stream stopped.")

    def update_static_info(self):
        """Updates status labels that generally don't change each frame (e.g., resolution, name)."""
        if self.streamer:
            try:
                # Get the latest info dictionary from the streamer
                info = self.streamer.get_info()
                # Update corresponding QLabels, using .get() with defaults for safety
                self.status_labels["stream_name"].setText(info.get("stream_name", "N/A"))
                self.status_labels["source_id"].setText(info.get("source_id", "N/A"))
                self.status_labels["resolution"].setText(f"{info.get('width', '?')}x{info.get('height', '?')}")
                self.status_labels["lsl_format"].setText(info.get("lsl_pixel_format", "N/A"))
                self.status_labels["nominal_fps"].setText(f"{info.get('actual_fps', 0.0):.2f}")
                self.status_labels["source_type"].setText(info.get("source_type", "N/A"))
            except Exception as e:
                 print(f"Error updating static info labels: {e}")


    @Slot()
    def update_frame(self):
        """Slot method called periodically by the QTimer to fetch and display a new frame."""
        # Check if the streamer exists and is running
        if not self.streamer or not self.streamer._is_running:
            # print("Update frame called but streamer not running") # Debug print
            return

        # Attempt to capture a frame from the streamer
        frame_data, timestamp = self.streamer.capture_frame()

        # Check if a valid frame and timestamp were received
        if frame_data is not None and timestamp is not None:
            # Update dynamic status labels (timestamp, frame count)
            try:
                self.status_labels["lsl_time"].setText(f"{timestamp:.4f}")
                self.status_labels["frames_sent"].setText(str(self.streamer.get_frame_count()))
            except Exception as e:
                 print(f"Error updating dynamic info labels: {e}")

            # Calculate and display approximate UI update FPS
            current_time = time.time()
            self.frame_update_count += 1
            delta_time = current_time - self.last_frame_time
            # Update FPS display roughly every second
            if delta_time >= 1.0: 
                self.calculated_fps = self.frame_update_count / delta_time
                try:
                    self.status_labels["display_fps"].setText(f"{self.calculated_fps:.2f}")
                except Exception as e:
                    print(f"Error updating FPS label: {e}")
                # Reset counters for the next interval
                self.last_frame_time = current_time
                self.frame_update_count = 0
            
            # Convert the received NumPy frame data to a QImage for display in QLabel.
            try:
                # Determine the correct QImage format based on the LSL pixel format
                # reported by the streamer.
                q_image_format = None
                requires_swap = False # Flag if BGR->RGB swap is needed
                
                # Handle common formats
                if self.streamer.lsl_pixel_format == 'BGR888':
                    # OpenCV provides BGR, QImage might expect RGB depending on platform/version.
                    # QImage.Format_BGR888 exists but might not always render correctly.
                    # Often safer to use Format_RGB888 and swap channels if needed.
                    if frame_data.ndim == 3 and frame_data.shape[2] == 3:
                        q_image_format = QImage.Format_RGB888
                        requires_swap = True # Mark for BGR -> RGB conversion
                    elif frame_data.ndim == 2: # Handle potential grayscale case
                         q_image_format = QImage.Format_Grayscale8
                elif self.streamer.lsl_pixel_format == 'RGB888':
                     if frame_data.ndim == 3 and frame_data.shape[2] == 3:
                        q_image_format = QImage.Format_RGB888
                     elif frame_data.ndim == 2:
                         q_image_format = QImage.Format_Grayscale8
                # Add more format handlers here if the streamer supports them (e.g., RGBA, Grayscale explicitly)
                # elif self.streamer.lsl_pixel_format == 'RGBA8888':
                #      q_image_format = QImage.Format_RGBA8888
                elif frame_data.ndim == 2 or (frame_data.ndim == 3 and frame_data.shape[2] == 1):
                    # Fallback for single channel data
                    q_image_format = QImage.Format_Grayscale8
                
                # Check if a suitable format was found
                if q_image_format is None:
                    self.video_label.setText(f"Unsupported LSL format for display: {self.streamer.lsl_pixel_format}")
                    self.video_label.setStyleSheet("color: red;")
                    return

                # Create the QImage. 
                # Note: QImage constructor can often take numpy array data directly.
                # We need to provide the data buffer, width, height, bytes per line (strides[0]), and format.
                # Ensure data is contiguous if strides are causing issues: frame_data = np.ascontiguousarray(frame_data)
                image = QImage(frame_data.data, frame_data.shape[1], frame_data.shape[0], 
                               frame_data.strides[0], q_image_format)
                
                # Swap BGR to RGB if needed (common for OpenCV frames)
                if requires_swap:
                    image = image.rgbSwapped()

                # Convert QImage to QPixmap for display in QLabel.
                pixmap = QPixmap.fromImage(image)
                
                # Scale the pixmap to fit the video_label while preserving aspect ratio.
                # Qt.KeepAspectRatio prevents distortion.
                # Qt.SmoothTransformation provides better quality scaling.
                self.video_label.setPixmap(pixmap.scaled(self.video_label.size(), 
                                                        Qt.KeepAspectRatio, Qt.SmoothTransformation))
                self.video_label.setStyleSheet("") # Reset style if it was an error message
            except Exception as e:
                # Handle errors during image conversion or display.
                print(f"Error converting/displaying frame: {e}")
                traceback.print_exc()
                self.video_label.setText("Error displaying frame.") # Show error in UI
                self.video_label.setStyleSheet("color: red;") # Make error visible
        # else:
            # Optional: Handle case where capture_frame returned None (e.g., show a message)
            # self.video_label.setText("Waiting for frame...")
            # pass 

    def closeEvent(self, event):
        """Overrides the default close event handler for the window.
        Ensures the LSL stream is stopped gracefully when the user closes the GUI window.
        """
        print("GUI close event triggered. Stopping stream...")
        self.stop_stream() # Call the existing stop method
        event.accept() # Allow the window to close


# --- Main execution block (for testing the GUI directly) ---
# This allows running `python gui.py` to test the interface.
# For production use, a dedicated entry point script might be preferred.
if __name__ == '__main__':
    
    # Example of parsing simple command-line args for the GUI itself.
    # This could be expanded to pass all necessary args to LSLCameraStreamer.
    # For now, it just checks for a basic '--webcam' flag.
    use_webcam_arg = '--webcam' in sys.argv
    # Could add parsing for width, height, fps, name, id etc. here if needed
    # width_arg = 640 
    # ... 

    # Create a dictionary of arguments to pass to the StreamViewerWindow,
    # which will then pass them to LSLCameraStreamer on start.
    streamer_params = {
        'use_webcam': use_webcam_arg,
        # 'width': width_arg, # Add other parsed args here
        # 'height': height_arg,
        # 'fps': fps_arg
    }

    # Standard PySide6 application setup
    app = QApplication(sys.argv)
    # Create an instance of the main window, passing streamer args
    viewer = StreamViewerWindow(streamer_args=streamer_params)
    # Show the window
    viewer.show()
    # Start the Qt event loop. The application runs until this exits.
    sys.exit(app.exec()) 