#!/bin/bash
#
# Script to set up auto-activation of the Python virtual environment
# when entering the raspberry_pie_camera_capture directory
#
# Author: Anzal
# Email: anzal.ks@gmail.com
# GitHub: https://github.com/anzalks/
#

# Define the project directory and venv
PROJECT_DIR="$HOME/raspberry_pie_camera_capture"
VENV_PATH="$PROJECT_DIR/.venv"

# Check if .bashrc exists
if [ ! -f "$HOME/.bashrc" ]; then
    echo "Error: $HOME/.bashrc not found"
    exit 1
fi

# Check if the code is already in .bashrc
if grep -q "cd $PROJECT_DIR" "$HOME/.bashrc"; then
    echo "Auto-activation already set up in .bashrc"
else
    # Add the following to .bashrc
    cat << EOL >> "$HOME/.bashrc"

# Auto-activate raspberry_pie_camera_capture virtual environment
raspberry_pie_auto_activate() {
  if [[ "\$PWD" == "$PROJECT_DIR"* ]]; then
    # Inside the project directory
    if [[ -f "$VENV_PATH/bin/activate" ]]; then
      if [[ -z "\$VIRTUAL_ENV" || "\$VIRTUAL_ENV" != "$VENV_PATH" ]]; then
        echo "Activating raspberry_pie_camera_capture environment..."
        source "$VENV_PATH/bin/activate"
      fi
    fi
  elif [[ -n "\$VIRTUAL_ENV" && "\$VIRTUAL_ENV" == "$VENV_PATH" ]]; then
    # Outside the project directory but env is active
    echo "Deactivating raspberry_pie_camera_capture environment..."
    deactivate
  fi
}

# Add hook to check directory change
cd() {
  builtin cd "\$@"
  raspberry_pie_auto_activate
}

# Check on startup in case you directly open terminal in project dir
raspberry_pie_auto_activate
EOL

    echo "Auto-activation set up successfully in .bashrc"
    echo "Please run 'source ~/.bashrc' or start a new terminal session for changes to take effect"
fi

# Add an alias for quick access to the project directory
if ! grep -q "alias raspi-camera=" "$HOME/.bashrc"; then
    echo "" >> "$HOME/.bashrc"
    echo "# Alias to quickly change to the raspberry pi camera project" >> "$HOME/.bashrc"
    echo "alias raspi-camera='cd $PROJECT_DIR && source $VENV_PATH/bin/activate'" >> "$HOME/.bashrc"
    echo "Added alias 'raspi-camera' to quickly navigate to the project directory"
fi

# Create a convenience wrapper script 
cat << 'EOF' > "$PROJECT_DIR/run-camera.sh"
#!/bin/bash
# Wrapper script to ensure virtual environment is activated

# Get the script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
VENV_PATH="$SCRIPT_DIR/.venv"

# Activate virtual environment if not already active
if [[ -z "$VIRTUAL_ENV" || "$VIRTUAL_ENV" != "$VENV_PATH" ]]; then
    echo "Activating virtual environment..."
    source "$VENV_PATH/bin/activate"
fi

# Run the camera capture script with all arguments passed to this script
python -m src.raspberry_pi_lsl_stream.camera_capture "$@"
EOF

# Make the wrapper script executable
chmod +x "$PROJECT_DIR/run-camera.sh"

echo
echo "Setup completed successfully!"
echo "Quick commands:"
echo "  raspi-camera  - Navigate to project and activate venv"
echo "  ./run-camera.sh  - Run the camera capture with automatic venv activation"
echo
echo "Next time you open a terminal in $PROJECT_DIR, the environment will activate automatically." 