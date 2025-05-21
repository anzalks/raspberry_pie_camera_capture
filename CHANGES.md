# Changes in the `vanila-lsl-stream` Branch

This branch provides a simplified, lean implementation of the Raspberry Pi Camera LSL Stream system. The following changes were made from the original implementation:

## Bug Fixes

1. **Fixed Video Recording Issues**:
   - Fixed initialization of `frame_queue` in camera_stream.py
   - Properly implemented `VideoWriter` codec selection and initialization
   - Ensured videos are saved to the `recordings` directory by default

## Added Functionality

1. **Environment Check Tool**:
   - Added `rpi-check-env` command to verify the environment
   - Checks for required Python packages and system libraries
   - Creates necessary directories (`recordings`, `analysis_reports`)
   - Tests camera and LSL functionality

2. **Standardized Recording Location**:
   - All recordings now save to the `recordings` directory by default
   - Added code to create this directory automatically if it doesn't exist

## Documentation Updates

1. **Simplified README**:
   - Focused on core functionality with clearer examples
   - Added troubleshooting section for common issues
   - Added instructions for the new environment check tool

2. **Project Structure Documentation**:
   - Added explanation of the modular architecture
   - Clarified which modules handle which functionality

## Dependencies

1. **Updated Requirements**:
   - Added missing dependencies (scipy, sounddevice, matplotlib)
   - Ensured all dependencies are documented in requirements.txt

## Overall Improvements

1. **Streamlined Code Base**:
   - Maintained full functionality while simplifying the implementation
   - Improved error handling for more robust operation
   - Better organization of code with clear responsibilities for each module

These changes create a more robust, user-friendly implementation while maintaining all the core functionality of the original system. 