"""PySide6 GUI for viewing the LSL Camera Stream."""

import sys
import time
from PySide6.QtWidgets import (QApplication, QWidget, QLabel, QVBoxLayout, QPushButton,
                             QHBoxLayout, QSizePolicy, QGridLayout)
from PySide6.QtGui import QPixmap, QImage
from PySide6.QtCore import Qt, QTimer, Slot

# Assuming LSLCameraStreamer is in the same directory for now
# We might need to adjust imports based on final structure
try:
    from .camera_stream import LSLCameraStreamer
except ImportError:
    print("Warning: Could not import LSLCameraStreamer. Ensure camera_stream.py is accessible.")
    # Define a dummy class if import fails, so GUI can load partially
    class LSLCameraStreamer:
        def __init__(self, *args, **kwargs): pass
        def start(self): pass
        def stop(self): pass
        def capture_frame(self): return None, None
        def get_info(self): return {}
        def get_frame_count(self): return 0


class StreamViewerWindow(QWidget):
    def __init__(self, streamer_args=None):
        super().__init__()
        self.streamer_args = streamer_args if streamer_args else {}
        self.streamer = None
        self.capture_timer = QTimer(self)
        self.capture_timer.timeout.connect(self.update_frame)
        self.last_frame_time = time.time()
        self.frame_update_count = 0
        self.calculated_fps = 0.0

        self.init_ui()
        # Attempt to start automatically, or add a button
        # self.start_stream() 

    def init_ui(self):
        self.setWindowTitle("LSL Camera Stream Viewer")
        self.setGeometry(100, 100, 800, 600) # x, y, width, height

        main_layout = QVBoxLayout(self)

        # --- Video Display ---
        self.video_label = QLabel("Video feed will appear here")
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.video_label.setStyleSheet("border: 1px solid black; background-color: #333;")
        main_layout.addWidget(self.video_label, stretch=1) # Allow video to stretch

        # --- Controls ---
        control_layout = QHBoxLayout()
        self.start_button = QPushButton("Start Stream")
        self.start_button.clicked.connect(self.start_stream)
        self.stop_button = QPushButton("Stop Stream")
        self.stop_button.clicked.connect(self.stop_stream)
        self.stop_button.setEnabled(False) # Disabled initially
        control_layout.addWidget(self.start_button)
        control_layout.addWidget(self.stop_button)
        control_layout.addStretch(1) # Push buttons to left
        main_layout.addLayout(control_layout)

        # --- Status Info ---
        status_layout = QGridLayout()
        self.status_labels = {}
        labels_to_create = [
            ("Stream Name:", "stream_name", ""), 
            ("Source ID:", "source_id", ""),
            ("Resolution:", "resolution", ""),
            ("Format:", "lsl_format", ""),
            ("Nominal FPS:", "nominal_fps", ""),
            ("Source Type:", "source_type", ""),
            ("LSL Timestamp:", "lsl_time", ""),
            ("Frames Sent:", "frames_sent", ""),
            ("Display FPS:", "display_fps", ""),
            ("Status:", "run_status", "Stopped")
        ]

        row = 0
        col = 0
        for label_text, key, default in labels_to_create:
            desc_label = QLabel(label_text)
            value_label = QLabel(default)
            self.status_labels[key] = value_label
            status_layout.addWidget(desc_label, row, col * 2)
            status_layout.addWidget(value_label, row, col * 2 + 1)
            col += 1
            if col >= 3: # Adjust number of columns
                col = 0
                row += 1
        
        main_layout.addLayout(status_layout)

        self.setLayout(main_layout)

    @Slot()
    def start_stream(self):
        print("Attempting to start stream...")
        if self.streamer is None:
            try:
                # Pass arguments used to start the GUI eventually
                self.streamer = LSLCameraStreamer(**self.streamer_args) 
                self.streamer.start()
                if not self.streamer._is_running:
                    print("Streamer failed to start.")
                    self.streamer = None # Reset if start failed
                    self.status_labels["run_status"].setText("Error starting")
                    return
                    
                self.status_labels["run_status"].setText("Running")
                self.start_button.setEnabled(False)
                self.stop_button.setEnabled(True)
                self.update_static_info()
                self.capture_timer.start(0) # Try to run as fast as possible
                self.last_frame_time = time.time()
                self.frame_update_count = 0
                print("Stream started, timer activated.")
            except Exception as e:
                print(f"Error creating or starting streamer: {e}")
                self.status_labels["run_status"].setText(f"Error: {e}")
                self.streamer = None # Ensure it's reset
        else:
            print("Streamer already exists.")

    @Slot()
    def stop_stream(self):
        print("Stopping stream...")
        self.capture_timer.stop()
        if self.streamer:
            self.streamer.stop()
            self.streamer = None # Release the object
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.status_labels["run_status"].setText("Stopped")
        self.video_label.setText("Video feed stopped.") # Clear video display
        print("Stream stopped.")

    def update_static_info(self):
        """Update labels that don't change per frame."""
        if self.streamer:
            info = self.streamer.get_info()
            self.status_labels["stream_name"].setText(info.get("stream_name", "N/A"))
            self.status_labels["source_id"].setText(info.get("source_id", "N/A"))
            self.status_labels["resolution"].setText(f"{info.get('width', '?')}x{info.get('height', '?')}")
            self.status_labels["lsl_format"].setText(info.get("lsl_pixel_format", "N/A"))
            self.status_labels["nominal_fps"].setText(f"{info.get('actual_fps', 0.0):.2f}")
            self.status_labels["source_type"].setText(info.get("source_type", "N/A"))


    @Slot()
    def update_frame(self):
        if not self.streamer or not self.streamer._is_running:
            return

        frame_data, timestamp = self.streamer.capture_frame()

        if frame_data is not None and timestamp is not None:
            # Update dynamic status labels
            self.status_labels["lsl_time"].setText(f"{timestamp:.4f}")
            self.status_labels["frames_sent"].setText(str(self.streamer.get_frame_count()))

            # Calculate and display approximate UI update FPS
            current_time = time.time()
            self.frame_update_count += 1
            delta_time = current_time - self.last_frame_time
            if delta_time >= 1.0: # Update FPS display every second
                self.calculated_fps = self.frame_update_count / delta_time
                self.status_labels["display_fps"].setText(f"{self.calculated_fps:.2f}")
                self.last_frame_time = current_time
                self.frame_update_count = 0
            
            # Convert frame to QImage/QPixmap for display
            try:
                if self.streamer.lsl_pixel_format == 'BGR888':
                    # OpenCV uses BGR, convert to RGB for QImage
                    if frame_data.ndim == 3 and frame_data.shape[2] == 3:
                         image = QImage(frame_data.data, frame_data.shape[1], frame_data.shape[0], 
                                        frame_data.strides[0], QImage.Format_BGR888)
                         # Maybe convert to RGB explicitly if BGR888 doesn't render right
                         # image = QImage(frame_data.data, frame_data.shape[1], frame_data.shape[0], 
                         #                frame_data.strides[0], QImage.Format_RGB888).rgbSwapped() 
                    else: # Handle grayscale or unexpected shapes
                         image = QImage(frame_data.data, frame_data.shape[1], frame_data.shape[0],
                                        frame_data.strides[0], QImage.Format_Grayscale8)
                elif self.streamer.lsl_pixel_format == 'RGB888':
                     image = QImage(frame_data.data, frame_data.shape[1], frame_data.shape[0], 
                                    frame_data.strides[0], QImage.Format_RGB888)
                # Add more format handlers if needed (e.g., Grayscale, RGBA)
                else: 
                    # Default/fallback: try Grayscale if single channel, else show error text
                    if frame_data.ndim == 2 or (frame_data.ndim == 3 and frame_data.shape[2] == 1):
                         image = QImage(frame_data.data, frame_data.shape[1], frame_data.shape[0], 
                                    frame_data.strides[0], QImage.Format_Grayscale8)
                    else:
                         self.video_label.setText(f"Unsupported format: {self.streamer.lsl_pixel_format}")
                         return 

                # Display the image, scaling it to fit the label
                pixmap = QPixmap.fromImage(image)
                self.video_label.setPixmap(pixmap.scaled(self.video_label.size(), 
                                                        Qt.KeepAspectRatio, Qt.SmoothTransformation))
            except Exception as e:
                print(f"Error converting/displaying frame: {e}")
                self.video_label.setText("Error displaying frame.") # Show error in UI

    def closeEvent(self, event):
        """Ensure the stream is stopped when the window closes."""
        print("Close event triggered.")
        self.stop_stream()
        event.accept() # Accept the close event


# --- Main execution ---
# This is temporary for testing. We'll create a proper entry point script later.
if __name__ == '__main__':
    
    # Basic argument parsing (can be expanded)
    use_webcam_arg = '--webcam' in sys.argv
    width_arg = 640
    height_arg = 480
    fps_arg = 30
    # Add more arg parsing if needed

    streamer_params = {
        'use_webcam': use_webcam_arg,
        'width': width_arg,
        'height': height_arg,
        'fps': fps_arg
        # Add stream_name, source_id etc. if parsed
    }

    app = QApplication(sys.argv)
    viewer = StreamViewerWindow(streamer_args=streamer_params)
    viewer.show()
    sys.exit(app.exec()) 