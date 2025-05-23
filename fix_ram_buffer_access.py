#!/usr/bin/env python3

"""
Fix for high_fps_camera_recorder.py
This patch addresses the issue where ram_buffer is incorrectly accessed in ntfy_listener_thread.
"""

import sys

def apply_fix():
    # Path to the original file
    file_path = "high_fps_camera_recorder.py"
    
    try:
        # Read the original file content
        with open(file_path, 'r') as file:
            content = file.readlines()
            
        # Find the camera_buffer_thread function and add ram_buffer as a class attribute
        for i, line in enumerate(content):
            if "def camera_buffer_thread(camera_process):" in line:
                # Add a comment above for clarity
                content.insert(i, "    # Make ram_buffer accessible as an attribute for the ntfy_listener_thread\n")
                # Next line after the function definition should be where we're setting the ram_buffer
                buffer_line_idx = i + 6  # Approximate location of buffer initialization
                ram_buffer_assign_line = "    # Make ram_buffer accessible as an attribute\n    camera_buffer_thread.ram_buffer = ram_buffer\n"
                
                # Find the exact location to insert the attribute assignment
                for j in range(i+1, min(i+20, len(content))):
                    if "ram_buffer = deque" in content[j]:
                        buffer_line_idx = j + 1
                        break
                
                content.insert(buffer_line_idx, ram_buffer_assign_line)
                break
        
        # Fix ntfy_listener_thread function to use the correct ram_buffer access
        for i, line in enumerate(content):
            if "ram_buffer = list(main_buffer_thread.ram_buffer)" in line:
                content[i] = "                         # Get current RAM buffer from camera buffer thread\n                         ram_buffer = list(camera_buffer_thread.ram_buffer)\n"
                break
        
        # Save the changes
        with open(file_path, 'w') as file:
            file.writelines(content)
        
        print(f"Fix applied successfully to {file_path}")
        print("The script now correctly accesses the RAM buffer in the ntfy_listener_thread function.")
        
    except FileNotFoundError:
        print(f"Error: Could not find {file_path}")
        return 1
    except Exception as e:
        print(f"Error applying fix: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(apply_fix()) 