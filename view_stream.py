import cv2
import numpy as np
from pylsl import StreamInlet, resolve_byprop
import sys
import xml.etree.ElementTree as ET
import time

# --- Configuration ---
# Name of the LSL stream to connect to (must match the streamer's setting)
STREAM_NAME = 'RaspberryPiCamera' 
# How long (in seconds) to search for the stream on the network
TIMEOUT_SECONDS = 5 
# ---

def main():
    """Finds the LSL stream, connects to it, reads metadata, 
       and displays the received frames in an OpenCV window with overlays.
    """
    
    # --- LSL Stream Discovery ---
    print(f"Looking for LSL stream named '{STREAM_NAME}'...")
    # Search for streams on the network matching the specified name.
    # resolve_byprop returns a list of matching StreamInfo objects.
    streams = resolve_byprop('name', STREAM_NAME, timeout=TIMEOUT_SECONDS)

    # Check if any streams were found
    if not streams:
        print(f"Error: Could not find LSL stream '{STREAM_NAME}'.", file=sys.stderr)
        print("Make sure the rpi-lsl-stream script is running.", file=sys.stderr)
        sys.exit(1)

    # --- LSL Inlet Creation ---
    print(f"Found stream '{STREAM_NAME}'. Creating inlet...")
    # Create an inlet connected to the first found stream.
    # The inlet is used to receive data and metadata from the stream.
    inlet = StreamInlet(streams[0])

    # --- Metadata Parsing ---
    # Initialize variables for storing metadata retrieved from the stream.
    width = 0
    height = 0
    num_channels = 0 # Estimated number of channels for reshaping
    pixel_format_lsl = "Unknown"

    try:
        # Get the stream's metadata as an XML string.
        info_xml = inlet.info().as_xml()
        # Parse the XML string.
        root = ET.fromstring(info_xml)
        # Find the <resolution> element within the <desc> element.
        # This custom element should be added by the streamer (LSLCameraStreamer).
        res_node = root.find('./desc/resolution')
        if res_node is not None:
            # Extract width, height, estimated channels, and pixel format.
            width_node = res_node.find('width')
            height_node = res_node.find('height')
            # The 'num_channels_estimated' is crucial for reshaping the flattened data.
            num_channels_node = res_node.find('num_channels_estimated') 
            pixel_format_node = res_node.find('pixel_format_lsl')

            # Convert extracted text values to integers/strings.
            if width_node is not None: width = int(width_node.text)
            if height_node is not None: height = int(height_node.text)
            if num_channels_node is not None: num_channels = int(num_channels_node.text)
            if pixel_format_node is not None: pixel_format_lsl = pixel_format_node.text
            
            # Basic validation of parsed dimensions.
            if not (width > 0 and height > 0 and num_channels > 0):
                 raise ValueError("Invalid dimensions parsed from LSL stream info.")
                 
            print(f"Stream Info: {width}x{height}, Channels (estimated): {num_channels}, Format: {pixel_format_lsl}")
            
        else:
            # Error if the crucial <resolution> metadata is missing.
            raise ValueError("Could not find 'resolution' node in LSL stream info.")

    except Exception as e:
        # Catch errors during XML parsing or metadata extraction.
        print(f"Error parsing LSL stream metadata: {e}", file=sys.stderr)
        print("Ensure the stream metadata includes width, height, num_channels_estimated under <desc><resolution>.", file=sys.stderr)
        inlet.close_stream() # Close the inlet before exiting
        sys.exit(1)
        
    # --- OpenCV Window Setup ---
    window_name = f"LSL Stream Viewer: {STREAM_NAME}"
    # Create a resizable window.
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)

    print("\nReceiving and displaying frames... Press 'q' to quit.")
    frames_received = 0
    
    # --- FPS Calculation Variables ---
    fps_update_interval = 1.0 # How often to update the displayed FPS (seconds)
    fps_frame_count = 0 # Frames received within the current interval
    fps_start_time = time.time() # Start time of the current interval
    calculated_fps = 0.0 # The calculated FPS to display
    # ---
    
    try:
        # --- Main Display Loop ---
        while True:
            # Pull a sample (flattened frame data) and its timestamp from the LSL inlet.
            # pull_sample() blocks until a sample is available or the timeout occurs.
            sample, timestamp = inlet.pull_sample(timeout=1.0) # Timeout after 1 second

            # Check if a sample was actually received (it's None on timeout)
            if sample:
                frames_received += 1
                # Convert the received list/tuple sample into a NumPy array of uint8.
                frame_data = np.array(sample, dtype=np.uint8)
                
                # --- Frame Reshaping ---
                # Reshape the flattened 1D array back into a 3D image array (H x W x C)
                # using the dimensions obtained from the LSL metadata.
                try:
                    # Verify if the received data size matches the expected size.
                    expected_size = height * width * num_channels
                    if frame_data.size != expected_size:
                         print(f"Warning: Received frame size ({frame_data.size}) does not match expected ({expected_size}). Skipping frame.")
                         continue # Skip processing this corrupted/mismatched frame
                         
                    frame = frame_data.reshape((height, width, num_channels))
                except ValueError as e:
                     # Catch errors during reshaping (e.g., if expected_size was calculated incorrectly)
                     print(f"Error reshaping frame: {e}. Expected shape ({height}, {width}, {num_channels}), got size {frame_data.size}. Skipping.")
                     continue # Skip processing this frame

                # --- FPS Calculation ---
                # Calculate the frame rate based on how many frames are received by this script.
                current_time = time.time()
                fps_frame_count += 1
                elapsed_time = current_time - fps_start_time
                # Update the displayed FPS value periodically.
                if elapsed_time >= fps_update_interval:
                    calculated_fps = fps_frame_count / elapsed_time
                    # Reset counters for the next interval.
                    fps_frame_count = 0
                    fps_start_time = current_time
                # ---

                # --- Overlay Text Information ---
                # Define font properties for the overlay text.
                font = cv2.FONT_HERSHEY_SIMPLEX
                font_scale = 0.6
                font_color = (255, 255, 255) # White color
                bg_color = (0, 0, 0) # Black background for better readability
                thickness = 1
                line_type = cv2.LINE_AA # Anti-aliased line

                # Prepare the text strings to display.
                text_res = f"Res: {width}x{height}"
                text_fmt = f"Format: {pixel_format_lsl}"
                text_ts = f"LSL ts: {timestamp:.4f}"
                text_fps = f"Recv FPS: {calculated_fps:.2f}" 

                # Calculate the size of each text string to draw appropriate background rectangles.
                (res_w, res_h), _ = cv2.getTextSize(text_res, font, font_scale, thickness)
                (fmt_w, fmt_h), _ = cv2.getTextSize(text_fmt, font, font_scale, thickness)
                (ts_w, ts_h), _ = cv2.getTextSize(text_ts, font, font_scale, thickness)
                (fps_w, fps_h), _ = cv2.getTextSize(text_fps, font, font_scale, thickness) 
                
                # Define positioning variables for the overlay text.
                y_offset = 10 # Padding from the top edge
                x_offset = 10 # Padding from the left edge
                line_spacing = 5 # Vertical space between text lines
                
                # Draw text with background rectangles for each line of info.
                # Position 1 (Resolution)
                y1 = y_offset + res_h
                cv2.rectangle(frame, (x_offset - 2, y_offset), (x_offset + res_w + 2, y1 + 2), bg_color, -1)
                cv2.putText(frame, text_res, (x_offset, y1), font, font_scale, font_color, thickness, line_type)
                
                # Position 2 (Format)
                y2 = y1 + line_spacing + fmt_h
                cv2.rectangle(frame, (x_offset - 2, y1 + line_spacing), (x_offset + fmt_w + 2, y2 + 2), bg_color, -1)
                cv2.putText(frame, text_fmt, (x_offset, y2), font, font_scale, font_color, thickness, line_type)

                # Position 3 (Timestamp)
                y3 = y2 + line_spacing + ts_h
                cv2.rectangle(frame, (x_offset - 2, y2 + line_spacing), (x_offset + ts_w + 2, y3 + 2), bg_color, -1)
                cv2.putText(frame, text_ts, (x_offset, y3), font, font_scale, font_color, thickness, line_type)

                # Position 4 (FPS)
                y4 = y3 + line_spacing + fps_h
                cv2.rectangle(frame, (x_offset - 2, y3 + line_spacing), (x_offset + fps_w + 2, y4 + 2), bg_color, -1)
                cv2.putText(frame, text_fps, (x_offset, y4), font, font_scale, font_color, thickness, line_type)
                # --- End Overlay ---

                # Display the final frame (with overlays) in the OpenCV window.
                cv2.imshow(window_name, frame)

            else:
                # Handle the case where pull_sample timed out (no sample received).
                # Print a message without a newline to indicate waiting.
                print("No frame received (timeout)...", end='\\r')
                pass

            # --- User Input Handling ---
            # Check for user input (e.g., pressing 'q').
            # cv2.waitKey(1) waits 1ms for a key press and returns the key code, or -1 if no key.
            if cv2.waitKey(1) & 0xFF == ord('q'):
                print("\n'q' pressed, exiting.")
                break # Exit the main loop
                
    except KeyboardInterrupt:
         # Handle Ctrl+C interruption gracefully.
         print("\nCtrl+C pressed, exiting.")
    finally:
        # --- Cleanup ---
        # This block executes whether the loop finished normally or was interrupted.
        print(f"Closing LSL inlet and OpenCV window. Total frames received: {frames_received}")
        # Close the LSL inlet to release its connection.
        inlet.close_stream()
        # Destroy the OpenCV display window.
        cv2.destroyAllWindows()

# Standard Python entry point check.
if __name__ == '__main__':
    main() 