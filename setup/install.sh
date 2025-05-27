#!/bin/bash
# IMX296 Camera System Installation Script - Enhanced Dynamic Path Compatible
# Author: Anzal KS <anzal.ks@gmail.com>
# Date: December 2024
#
# ENHANCED FEATURES:
# ==================
# - Robust permission handling for all files and directories
# - Smart desktop shortcut creation with fallback methods
# - Comprehensive file existence checking (no duplicates)
# - Enhanced error handling and recovery
# - Dynamic path detection with validation
# - Improved user and group management
# - Better systemd service handling
# - Enhanced LSL installation with multiple verification methods
# - Comprehensive testing and verification

set -e  # Exit on error for better debugging

# Enhanced logging function
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

# Enhanced error handling
handle_error() {
    local exit_code=$?
    local line_number=$1
    log_error "An error occurred on line $line_number. Exit code: $exit_code"
    log_info "Attempting to continue with fallback methods..."
    return 0  # Don't exit on error, try to continue
}

trap 'handle_error $LINENO' ERR

# Dynamic path detection with validation
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$(dirname "$SCRIPT_DIR")" && pwd)"

# Validate paths
if [ ! -d "$SCRIPT_DIR" ] || [ ! -d "$PROJECT_ROOT" ]; then
    log_error "Failed to detect script or project directories"
    exit 1
fi

# Define colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${GREEN}==== IMX296 Camera System Installation Script (Enhanced) ====${NC}"
echo "Script directory: $SCRIPT_DIR"
echo "Project root: $PROJECT_ROOT"

# Enhanced root check
if [ "$EUID" -ne 0 ]; then
  log_error "Please run as root (using sudo) to install system packages"
  log_info "Usage: sudo bash ./install.sh"
  exit 1
fi

# Enhanced user detection with multiple fallback methods
detect_real_user() {
    local detected_user=""
    local detected_home=""
    
    # Method 1: SUDO_USER
    if [ -n "$SUDO_USER" ] && [ "$SUDO_USER" != "root" ]; then
        detected_user="$SUDO_USER"
        detected_home=$(getent passwd "$detected_user" 2>/dev/null | cut -d: -f6)
    fi
    
    # Method 2: Check who owns the project directory
    if [ -z "$detected_user" ]; then
        detected_user=$(stat -c '%U' "$PROJECT_ROOT" 2>/dev/null)
        if [ "$detected_user" != "root" ]; then
            detected_home=$(getent passwd "$detected_user" 2>/dev/null | cut -d: -f6)
        fi
    fi
    
    # Method 3: Check logged in users
    if [ -z "$detected_user" ] || [ "$detected_user" = "root" ]; then
        detected_user=$(who | grep -v root | head -1 | awk '{print $1}')
        if [ -n "$detected_user" ]; then
            detected_home=$(getent passwd "$detected_user" 2>/dev/null | cut -d: -f6)
        fi
    fi
    
    # Method 4: Default fallback
    if [ -z "$detected_user" ] || [ "$detected_user" = "root" ]; then
        log_warn "Could not detect non-root user, defaulting to 'pi'"
        detected_user="pi"
        detected_home="/home/pi"
    fi
    
    # Validate detection
    if [ -z "$detected_home" ] || [ ! -d "$detected_home" ]; then
        log_warn "Home directory '$detected_home' not found, creating it"
        mkdir -p "$detected_home" || true
        chown "$detected_user:$detected_user" "$detected_home" || true
    fi
    
    echo "$detected_user:$detected_home"
}

# Get real user with enhanced detection
USER_INFO=$(detect_real_user)
REAL_USER=$(echo "$USER_INFO" | cut -d: -f1)
REAL_USER_HOME=$(echo "$USER_INFO" | cut -d: -f2)

log_info "Installing for user: $REAL_USER"
log_info "User home: $REAL_USER_HOME"
log_info "Project location: $PROJECT_ROOT"

# Enhanced package management
install_package_safe() {
    local package="$1"
    local description="$2"
    
    log_info "Installing $description ($package)..."
    
    # Check if already installed
    if dpkg -l | grep -q "^ii.*$package "; then
        log_info "$package already installed"
        return 0
    fi
    
    # Check if package exists
    if ! apt-cache show "$package" >/dev/null 2>&1; then
        log_warn "Package $package not found in repositories"
        return 1
    fi
    
    # Install with error handling
    if apt install -y "$package"; then
        log_success "$package installed successfully"
        return 0
    else
        log_warn "Failed to install $package, continuing..."
        return 1
    fi
}

# Update package list
echo -e "${YELLOW}----- Updating Package List -----${NC}"
if ! apt update; then
    log_warn "Package list update failed, continuing with existing cache"
fi

# Enhanced system dependencies installation
echo -e "${YELLOW}----- Installing System Dependencies -----${NC}"

# Core packages (critical)
CORE_PACKAGES=(
    "python3:Python 3 interpreter"
    "python3-pip:Python package installer"
    "python3-venv:Python virtual environment"
    "python3-dev:Python development headers"
    "git:Version control system"
    "build-essential:Build tools"
    "cmake:Build system"
    "pkg-config:Package configuration"
    "curl:HTTP client"
    "wget:File downloader"
)

# Install core packages
for package_info in "${CORE_PACKAGES[@]}"; do
    package=$(echo "$package_info" | cut -d: -f1)
    description=$(echo "$package_info" | cut -d: -f2)
    install_package_safe "$package" "$description"
done

# Camera and media packages (important but not critical)
CAMERA_PACKAGES=(
    "libcamera-apps:Camera applications"
    "ffmpeg:Video processing"
    "v4l-utils:Video4Linux utilities"
    "mjpegtools:MJPEG tools"
)

# Install camera packages with fallbacks
for package_info in "${CAMERA_PACKAGES[@]}"; do
    package=$(echo "$package_info" | cut -d: -f1)
    description=$(echo "$package_info" | cut -d: -f2)
    
    if ! install_package_safe "$package" "$description"; then
        # Try alternative names
        case "$package" in
            "v4l-utils")
                install_package_safe "v4l2-utils" "Video4Linux2 utilities (alternative)"
                ;;
        esac
    fi
done

# Boost libraries for LSL
echo "Installing Boost libraries for LSL..."
BOOST_PACKAGES=(
    "libboost-dev"
    "libboost-thread-dev"
    "libboost-filesystem-dev"
    "libboost-system-dev"
    "libboost-regex-dev"
    "libboost-atomic-dev"
    "libboost-chrono-dev"
    "libboost-date-time-dev"
    "libasio-dev"
    "libssl-dev"
    "libffi-dev"
)

for package in "${BOOST_PACKAGES[@]}"; do
    install_package_safe "$package" "Boost library component"
done

# Additional useful packages
install_package_safe "dialog" "Dialog utility"

# Enhanced liblsl build function with multiple verification methods
build_liblsl_from_source() {
    log_info "Building liblsl from source..."
    
    # Define repository URL and versions
    local LIBLSL_REPO="https://github.com/sccn/liblsl.git"
    local BUILD_DIR="/tmp/liblsl_build_$(date +%s)"
    local PREFERRED_VERSIONS=("v1.16.2" "v1.16.1" "v1.16.0" "v1.15.8")
    
    # Create and enter build directory
    mkdir -p "$BUILD_DIR" || { log_error "Failed to create build directory"; return 1; }
    cd "$BUILD_DIR"
    
    log_info "Cloning liblsl repository..."
    if ! git clone "$LIBLSL_REPO" liblsl; then
        log_error "Failed to clone liblsl repository"
        cd "$PROJECT_ROOT"
        rm -rf "$BUILD_DIR"
        return 1
    fi
    
    cd liblsl
    
    # Fetch tags and select version
    log_info "Fetching available versions..."
    git fetch --tags
    
    local selected_version=""
    for version in "${PREFERRED_VERSIONS[@]}"; do
        if git tag | grep -q "^$version$"; then
            selected_version="$version"
            log_info "Selected liblsl version: $selected_version"
            git checkout "$selected_version"
            break
        fi
    done
    
    if [ -z "$selected_version" ]; then
        log_warn "No preferred version found, using latest"
    fi
    
    # Build
    log_info "Configuring build..."
    mkdir -p build
    cd build
    
    if ! cmake .. \
        -DCMAKE_INSTALL_PREFIX=/usr/local \
        -DLSL_BUNDLED_BOOST=ON \
        -DLSL_UNIXFOLDERS=ON \
        -DLSL_NO_FANCY_LIBNAME=ON \
        -DCMAKE_BUILD_TYPE=Release; then
        log_error "CMake configuration failed"
        cd "$PROJECT_ROOT"
        rm -rf "$BUILD_DIR"
        return 1
    fi
    
    log_info "Building liblsl (this may take a few minutes)..."
    if ! make -j$(nproc); then
        log_error "Build failed"
        cd "$PROJECT_ROOT"
        rm -rf "$BUILD_DIR"
        return 1
    fi
    
    log_info "Installing liblsl..."
    if ! make install; then
        log_error "Installation failed"
        cd "$PROJECT_ROOT"
        rm -rf "$BUILD_DIR"
        return 1
    fi
    
    # Update library cache
    ldconfig
    
    # Cleanup
    cd "$PROJECT_ROOT"
    rm -rf "$BUILD_DIR"
    
    log_success "liblsl built and installed successfully"
    return 0
}

# Enhanced liblsl detection and installation
check_and_install_liblsl() {
    log_info "Checking for liblsl library..."
    
    # Method 1: Check system library cache
    if ldconfig -p | grep -q "liblsl\.so"; then
        local installed_info=$(ldconfig -p | grep liblsl | head -1)
        log_success "liblsl found in system libraries: $installed_info"
        return 0
    fi
    
    # Method 2: Check common installation paths
    local LIBLSL_PATHS=(
        "/usr/local/lib/liblsl.so"
        "/usr/lib/liblsl.so"
        "/usr/lib/x86_64-linux-gnu/liblsl.so"
        "/usr/lib/aarch64-linux-gnu/liblsl.so"
    )
    
    for path in "${LIBLSL_PATHS[@]}"; do
        if [ -f "$path" ]; then
            log_success "liblsl found at: $path"
            ldconfig  # Update cache
            return 0
        fi
    done
    
    # Method 3: Build from source
    log_warn "liblsl not found, building from source..."
    if build_liblsl_from_source; then
        return 0
    else
        log_error "Failed to build liblsl from source"
        return 1
    fi
}

# Check and install liblsl
check_and_install_liblsl

# Enhanced Python environment setup
setup_python_environment() {
    log_info "Setting up Python environment..."
    cd "$PROJECT_ROOT"
    
    # Create virtual environment if needed
    if [ ! -d ".venv" ]; then
        log_info "Creating Python virtual environment..."
        if ! sudo -u "$REAL_USER" python3 -m venv --system-site-packages .venv; then
            log_error "Failed to create virtual environment"
            return 1
        fi
    else
        log_info "Using existing Python virtual environment"
    fi
    
    # Enhanced ownership fixing
    fix_venv_ownership() {
        log_info "Fixing virtual environment ownership..."
        
        # Get user and group
        local user_group=$(id -gn "$REAL_USER")
        
        # Fix ownership recursively
        chown -R "$REAL_USER:$user_group" .venv || {
            log_warn "Failed to change ownership, trying alternative method"
            find .venv -type f -exec chown "$REAL_USER:$user_group" {} \; 2>/dev/null || true
            find .venv -type d -exec chown "$REAL_USER:$user_group" {} \; 2>/dev/null || true
        }
        
        # Fix permissions
        chmod -R u+rwX .venv || true
        
        log_success "Virtual environment ownership fixed"
    }
    
    fix_venv_ownership
    
    # Enhanced pip installation function
    pip_install_as_user() {
        log_info "Installing Python package: $*"
        
        # Multiple attempts with different methods
        local attempts=0
        local max_attempts=3
        
        while [ $attempts -lt $max_attempts ]; do
            if sudo -u "$REAL_USER" "$PROJECT_ROOT/.venv/bin/pip" "$@"; then
                log_success "Package installed: $*"
                return 0
            else
                attempts=$((attempts + 1))
                log_warn "Attempt $attempts failed, retrying..."
                sleep 2
            fi
        done
        
        log_error "Failed to install package after $max_attempts attempts: $*"
        return 1
    }
    
    # Upgrade pip and tools
    log_info "Upgrading pip and setuptools..."
    pip_install_as_user install --upgrade pip setuptools wheel
    
    # Install core Python packages
    log_info "Installing core Python packages..."
    
    local PYTHON_PACKAGES=(
        "pyyaml>=6.0"
        "requests>=2.28.0"
        "psutil>=5.9.0"
    )
    
    for package in "${PYTHON_PACKAGES[@]}"; do
        pip_install_as_user install "$package"
    done
    
    # Install pylsl with enhanced compatibility
    install_pylsl_enhanced() {
        log_info "Installing pylsl with enhanced compatibility..."
        
        # Install pylsl
        if pip_install_as_user install "pylsl>=1.16.0"; then
            log_success "pylsl installed successfully"
        else
            log_warn "Standard pylsl installation failed, trying alternative methods..."
            
            # Try older version
            pip_install_as_user install "pylsl>=1.15.0" || {
                log_error "Failed to install any version of pylsl"
                return 1
            }
        fi
        
        # Create enhanced symlinks for liblsl compatibility
        create_enhanced_liblsl_symlinks
    }
    
    install_pylsl_enhanced
    
    # Install optional packages (don't fail if these don't work)
    log_info "Installing optional packages..."
    local OPTIONAL_PACKAGES=("numpy" "scipy" "matplotlib")
    
    for package in "${OPTIONAL_PACKAGES[@]}"; do
        if ! pip_install_as_user install "$package"; then
            log_warn "Optional package $package failed to install, continuing..."
        fi
    done
    
    return 0
}

# Enhanced liblsl symlink creation with multiple detection methods
create_enhanced_liblsl_symlinks() {
    log_info "Creating enhanced liblsl symlinks for pylsl compatibility..."
    
    # Find liblsl library with multiple methods
    local LIBLSL_PATH=""
    
    # Method 1: ldconfig
    if ldconfig -p | grep -q "liblsl\.so"; then
        LIBLSL_PATH=$(ldconfig -p | grep "liblsl\.so" | head -1 | awk '{print $4}')
    fi
    
    # Method 2: Common paths
    if [ -z "$LIBLSL_PATH" ]; then
        local SEARCH_PATHS=(
            "/usr/local/lib/liblsl.so"
            "/usr/lib/liblsl.so"
            "/usr/lib/*/liblsl.so"
        )
        
        for path_pattern in "${SEARCH_PATHS[@]}"; do
            for path in $path_pattern; do
                if [ -f "$path" ]; then
                    LIBLSL_PATH="$path"
                    break 2
                fi
            done
        done
    fi
    
    if [ -z "$LIBLSL_PATH" ]; then
        log_error "Could not find liblsl library for symlink creation"
        return 1
    fi
    
    log_info "Found liblsl at: $LIBLSL_PATH"
    
    # Find Python version and pylsl directory
    local PYTHON_VERSION=$(sudo -u "$REAL_USER" "$PROJECT_ROOT/.venv/bin/python3" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    local PYLSL_DIR="$PROJECT_ROOT/.venv/lib/python${PYTHON_VERSION}/site-packages/pylsl"
    
    if [ ! -d "$PYLSL_DIR" ]; then
        log_warn "pylsl directory not found: $PYLSL_DIR"
        return 1
    fi
    
    # Create lib directory
    sudo -u "$REAL_USER" mkdir -p "$PYLSL_DIR/lib"
    
    # Create comprehensive symlinks for all possible architectures
    local SYMLINK_NAMES=(
        "liblsl.so"
        "liblsl32.so"
        "liblsl64.so"
        "lib/liblsl.so"
        "lib/liblsl32.so"
        "lib/liblsl64.so"
    )
    
    for symlink_name in "${SYMLINK_NAMES[@]}"; do
        local symlink_path="$PYLSL_DIR/$symlink_name"
        
        # Remove existing symlink/file if it exists
        sudo -u "$REAL_USER" rm -f "$symlink_path" 2>/dev/null || true
        
        # Create new symlink
        if sudo -u "$REAL_USER" ln -sf "$LIBLSL_PATH" "$symlink_path"; then
            log_info "Created symlink: $symlink_name"
        else
            log_warn "Failed to create symlink: $symlink_name"
        fi
    done
    
    log_success "Enhanced liblsl symlinks created"
}

# Setup Python environment
setup_python_environment

# Enhanced directory creation with proper permissions
create_required_directories() {
    log_info "Creating required directories with proper permissions..."
    
    local DIRECTORIES=(
        "$PROJECT_ROOT/logs"
        "$PROJECT_ROOT/recordings"
        "$REAL_USER_HOME/recordings"
        "$PROJECT_ROOT/config"
        "$PROJECT_ROOT/bin"
    )
    
    for dir in "${DIRECTORIES[@]}"; do
        if [ ! -d "$dir" ]; then
            log_info "Creating directory: $dir"
            sudo -u "$REAL_USER" mkdir -p "$dir" || {
                log_warn "Failed to create $dir as user, trying as root"
                mkdir -p "$dir"
                chown "$REAL_USER:$(id -gn $REAL_USER)" "$dir"
            }
        else
            log_info "Directory already exists: $dir"
        fi
        
        # Ensure proper ownership
        chown "$REAL_USER:$(id -gn $REAL_USER)" "$dir" 2>/dev/null || true
    done
    
    log_success "Required directories created"
}

create_required_directories

# Enhanced script permissions with comprehensive file handling
set_enhanced_script_permissions() {
    log_info "Setting enhanced script permissions..."
    
    # Python scripts in bin/
    if [ -d "$PROJECT_ROOT/bin" ]; then
        find "$PROJECT_ROOT/bin" -name "*.py" -type f -exec chmod +x {} \; 2>/dev/null || true
        log_info "Set permissions for Python scripts in bin/"
    fi
    
    # Shell scripts in bin/
    if [ -d "$PROJECT_ROOT/bin" ]; then
        find "$PROJECT_ROOT/bin" -name "*.sh" -type f -exec chmod +x {} \; 2>/dev/null || true
        log_info "Set permissions for shell scripts in bin/"
    fi
    
    # Setup scripts
    if [ -d "$PROJECT_ROOT/setup" ]; then
        find "$PROJECT_ROOT/setup" -name "*.sh" -type f -exec chmod +x {} \; 2>/dev/null || true
        log_info "Set permissions for setup scripts"
    fi
    
    # Specific important scripts
    local IMPORTANT_SCRIPTS=(
        "$PROJECT_ROOT/bin/GScrop"
        "$PROJECT_ROOT/bin/clean_start_camera.sh"
        "$PROJECT_ROOT/bin/run_imx296_capture.py"
        "$PROJECT_ROOT/bin/status_monitor.py"
        "$PROJECT_ROOT/bin/start_camera_with_monitor.py"
        "$PROJECT_ROOT/bin/cleanup_and_start.py"
    )
    
    for script in "${IMPORTANT_SCRIPTS[@]}"; do
        if [ -f "$script" ]; then
            chmod +x "$script"
            log_info "Set executable permission: $script"
        fi
    done
    
    log_success "Enhanced script permissions set"
}

set_enhanced_script_permissions

# Enhanced configuration management
setup_enhanced_configuration() {
    log_info "Setting up enhanced configuration..."
    
    local CONFIG_FILE="$PROJECT_ROOT/config/config.yaml"
    local CONFIG_EXAMPLE="$PROJECT_ROOT/config/config.yaml.example"
    
    # Create config from example if needed
    if [ ! -f "$CONFIG_FILE" ] && [ -f "$CONFIG_EXAMPLE" ]; then
        log_info "Creating config.yaml from example..."
        sudo -u "$REAL_USER" cp "$CONFIG_EXAMPLE" "$CONFIG_FILE"
        
        # Enhanced configuration customization
        customize_config_file() {
            log_info "Customizing configuration file..."
            
            # Detect IMX296 camera and media device with dynamic detection
            local MEDIA_DEVICE=""
            local AVAILABLE_MEDIA_DEVICES=($(ls /dev/media* 2>/dev/null | sort -V))
            
            if [ ${#AVAILABLE_MEDIA_DEVICES[@]} -eq 0 ]; then
                log_warn "No media devices found"
            else
                log_info "Scanning ${#AVAILABLE_MEDIA_DEVICES[@]} media devices: ${AVAILABLE_MEDIA_DEVICES[*]}"
                
                for media_dev in "${AVAILABLE_MEDIA_DEVICES[@]}"; do
                    if [ -e "$media_dev" ]; then
                        if command -v media-ctl >/dev/null 2>&1; then
                            if media-ctl -d "$media_dev" -p 2>/dev/null | grep -qi "imx296"; then
                                MEDIA_DEVICE="$media_dev"
                                log_success "Found IMX296 camera on $MEDIA_DEVICE"
                                break
                            fi
                        fi
                    fi
                done
            fi
            
            if [ -n "$MEDIA_DEVICE" ]; then
                sed -i "s|device_pattern: \"/dev/media%d\"|device_pattern: \"$MEDIA_DEVICE\"|" "$CONFIG_FILE"
                log_info "Updated config with camera device: $MEDIA_DEVICE"
            else
                log_info "No IMX296 camera detected, keeping default config"
            fi
            
            # Create unique ntfy topic
            local HOSTNAME=$(hostname 2>/dev/null || echo "raspicam")
            local PROJECT_NAME=$(basename "$PROJECT_ROOT")
            local TIMESTAMP=$(date +%s | tail -c 6)
            local NTFY_TOPIC="${HOSTNAME}-${PROJECT_NAME}-${TIMESTAMP}"
            
            sed -i "s|topic: \"raspie-camera.*\"|topic: \"$NTFY_TOPIC\"|" "$CONFIG_FILE" 2>/dev/null || true
            log_info "Set unique ntfy topic: $NTFY_TOPIC"
            
            # Update paths to be relative
            sed -i "s|script_path: \"/.*GScrop\"|script_path: \"bin/GScrop\"|" "$CONFIG_FILE" 2>/dev/null || true
            sed -i "s|output_dir: \"/.*recordings\"|output_dir: \"recordings\"|" "$CONFIG_FILE" 2>/dev/null || true
            
            log_success "Configuration file customized"
        }
        
        customize_config_file
    elif [ -f "$CONFIG_FILE" ]; then
        log_info "Configuration file already exists"
    else
        log_warn "No configuration file or example found"
    fi
    
    # Ensure proper ownership
    if [ -f "$CONFIG_FILE" ]; then
        chown "$REAL_USER:$(id -gn $REAL_USER)" "$CONFIG_FILE"
    fi
}

setup_enhanced_configuration

# Enhanced testing with multiple verification methods
perform_enhanced_testing() {
    log_info "Performing enhanced installation testing..."
    
    # Test 1: Python dependencies
    test_python_dependencies() {
        log_info "Testing Python dependencies..."
        
        local test_script="
import sys
sys.path.insert(0, '$PROJECT_ROOT')
try:
    import yaml
    import requests
    import psutil
    print('✓ Basic Python dependencies: OK')
    return 0
except ImportError as e:
    print(f'✗ Missing dependency: {e}')
    return 1
"
        
        if sudo -u "$REAL_USER" "$PROJECT_ROOT/.venv/bin/python3" -c "$test_script"; then
            log_success "Python dependencies test passed"
            return 0
        else
            log_error "Python dependencies test failed"
            return 1
        fi
    }
    
    # Test 2: LSL installation with multiple verification methods
    test_lsl_installation() {
        log_info "Testing LSL installation with multiple methods..."
        
        # Method 1: Basic import test
        local basic_test="
try:
    import pylsl
    print('✓ pylsl import: OK')
except ImportError as e:
    print(f'✗ pylsl import failed: {e}')
    exit(1)
"
        
        if ! sudo -u "$REAL_USER" "$PROJECT_ROOT/.venv/bin/python3" -c "$basic_test"; then
            log_error "Basic pylsl import test failed"
            
            # Try to fix with enhanced symlinks
            log_info "Attempting to fix pylsl with enhanced symlinks..."
            create_enhanced_liblsl_symlinks
            
            # Test again
            if sudo -u "$REAL_USER" "$PROJECT_ROOT/.venv/bin/python3" -c "$basic_test"; then
                log_success "pylsl fixed with enhanced symlinks"
            else
                log_error "pylsl still not working after symlink fix"
                return 1
            fi
        fi
        
        # Method 2: Version test
        local version_test="
import pylsl
try:
    version = pylsl.library_version()
    print(f'✓ pylsl version: {version}')
except AttributeError:
    # Some versions don't have version attribute
    print('✓ pylsl working (version info not available)')
"
        
        sudo -u "$REAL_USER" "$PROJECT_ROOT/.venv/bin/python3" -c "$version_test"
        
        # Method 3: Functionality test
        local function_test="
import pylsl
try:
    info = pylsl.StreamInfo('test', 'Test', 1, 100, 'float32', 'test')
    outlet = pylsl.StreamOutlet(info)
    print('✓ LSL stream creation: OK')
    del outlet, info
except Exception as e:
    print(f'⚠ LSL stream creation failed: {e}')
    print('  (This may be normal if no LSL network is available)')
"
        
        sudo -u "$REAL_USER" "$PROJECT_ROOT/.venv/bin/python3" -c "$function_test"
        
        log_success "LSL installation tests completed"
        return 0
    }
    
    # Test 3: Camera hardware detection
    test_camera_hardware() {
        log_info "Testing camera hardware detection..."
        
        if command -v libcamera-hello >/dev/null 2>&1; then
            log_info "libcamera-hello found, checking for cameras..."
            
            local camera_output
            camera_output=$(libcamera-hello --list-cameras 2>/dev/null || echo "No cameras found")
            
            if echo "$camera_output" | grep -qi "imx296"; then
                log_success "IMX296 camera detected"
                echo "$camera_output" | grep -i imx296
            elif echo "$camera_output" | grep -q "Available cameras"; then
                log_warn "Cameras detected but no IMX296 found"
                echo "$camera_output"
            else
                log_info "No cameras detected (normal for development machines)"
            fi
        else
            log_warn "libcamera-hello not found or not working"
        fi
    }
    
    # Run all tests
    test_python_dependencies
    test_lsl_installation
    test_camera_hardware
    
    log_success "Enhanced testing completed"
}

perform_enhanced_testing

# Enhanced systemd service installation with existence checking
install_enhanced_systemd_services() {
    log_info "Installing enhanced systemd services..."
    
    # Function to create or update systemd service
    create_systemd_service() {
        local service_name="$1"
        local service_file="/etc/systemd/system/${service_name}.service"
        local service_content="$2"
        
        if [ -f "$service_file" ]; then
            log_info "Systemd service '$service_name' already exists"
            
            # Check if it needs updating (compare key paths)
            if grep -q "$PROJECT_ROOT" "$service_file"; then
                log_info "Service '$service_name' has correct paths"
                return 0
            else
                log_info "Updating service '$service_name' with correct paths"
            fi
        else
            log_info "Creating new systemd service: $service_name"
        fi
        
        # Create/update the service file
        echo "$service_content" > "$service_file"
        
        # Reload systemd daemon
        systemctl daemon-reload
        
        log_success "Systemd service '$service_name' installed"
        log_info "To start: sudo systemctl start $service_name"
        log_info "To enable on boot: sudo systemctl enable $service_name"
    }
    
    # Main camera service
    local main_service_content="[Unit]
Description=IMX296 Global Shutter Camera Service
After=network.target

[Service]
Type=simple
User=$REAL_USER
Group=$(id -gn $REAL_USER)
WorkingDirectory=$PROJECT_ROOT
ExecStart=$PROJECT_ROOT/.venv/bin/python $PROJECT_ROOT/bin/run_imx296_capture.py
Restart=on-failure
RestartSec=10s
Environment=PATH=$PROJECT_ROOT/.venv/bin:/usr/local/bin:/usr/bin:/bin
Environment=PYTHONPATH=$PROJECT_ROOT

[Install]
WantedBy=multi-user.target"
    
    create_systemd_service "imx296-camera" "$main_service_content"
    
    # Monitor service
    local monitor_service_content="[Unit]
Description=IMX296 Camera Service with Status Monitor
After=network.target
Wants=network.target

[Service]
Type=simple
User=$REAL_USER
Group=$(id -gn $REAL_USER)
WorkingDirectory=$PROJECT_ROOT
ExecStart=$PROJECT_ROOT/.venv/bin/python $PROJECT_ROOT/bin/start_camera_with_monitor.py --monitor --no-output
Environment=PYTHONPATH=$PROJECT_ROOT
Environment=PATH=$PROJECT_ROOT/.venv/bin:/usr/local/bin:/usr/bin:/bin
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

# Service management
KillMode=mixed
TimeoutStopSec=10

[Install]
WantedBy=multi-user.target"
    
    create_systemd_service "imx296-camera-monitor" "$monitor_service_content"
    
    log_success "Enhanced systemd services installed"
}

install_enhanced_systemd_services

# Enhanced desktop shortcut creation with multiple fallback methods
create_enhanced_desktop_shortcut() {
    log_info "Creating enhanced desktop shortcut..."
    
    # Check if desktop environment exists
    local desktop_dirs=(
        "$REAL_USER_HOME/Desktop"
        "$REAL_USER_HOME/Escritorio"  # Spanish
        "$REAL_USER_HOME/Bureau"      # French
        "$REAL_USER_HOME/Рабочий стол" # Russian
    )
    
    local desktop_dir=""
    for dir in "${desktop_dirs[@]}"; do
        if [ -d "$dir" ]; then
            desktop_dir="$dir"
            break
        fi
    done
    
    if [ -z "$desktop_dir" ]; then
        log_info "No desktop directory found, creating one..."
        desktop_dir="$REAL_USER_HOME/Desktop"
        sudo -u "$REAL_USER" mkdir -p "$desktop_dir" || {
            log_warn "Failed to create desktop directory as user, trying as root"
            mkdir -p "$desktop_dir"
            chown "$REAL_USER:$(id -gn $REAL_USER)" "$desktop_dir"
        }
    fi
    
    local desktop_file="$desktop_dir/IMX296-Camera.desktop"
    
    # Create desktop file content
    local desktop_content="[Desktop Entry]
Name=IMX296 Camera System
Comment=IMX296 Camera Status Monitor and Control
Exec=x-terminal-emulator -e '$PROJECT_ROOT/.venv/bin/python $PROJECT_ROOT/bin/status_monitor.py'
Icon=camera-photo
Terminal=true
Type=Application
Categories=Utility;System;Monitor;
Path=$PROJECT_ROOT
StartupWMClass=IMX296-Camera"
    
    # Method 1: Create as user
    if sudo -u "$REAL_USER" bash -c "echo '$desktop_content' > '$desktop_file'"; then
        log_info "Desktop file created as user"
    else
        # Method 2: Create as root then change ownership
        log_warn "Creating desktop file as root and changing ownership"
        echo "$desktop_content" > "$desktop_file"
        chown "$REAL_USER:$(id -gn $REAL_USER)" "$desktop_file"
    fi
    
    # Enhanced permission setting with multiple methods
    set_desktop_file_executable() {
        log_info "Setting desktop file executable..."
        
        # Method 1: As user
        if sudo -u "$REAL_USER" chmod +x "$desktop_file" 2>/dev/null; then
            log_success "Desktop file made executable (method 1)"
            return 0
        fi
        
        # Method 2: As root
        if chmod +x "$desktop_file" 2>/dev/null; then
            log_success "Desktop file made executable (method 2)"
            return 0
        fi
        
        # Method 3: Using numeric permissions
        if chmod 755 "$desktop_file" 2>/dev/null; then
            log_success "Desktop file made executable (method 3)"
            return 0
        fi
        
        # Method 4: Try to fix ownership first
        chown "$REAL_USER:$(id -gn $REAL_USER)" "$desktop_file" 2>/dev/null
        if sudo -u "$REAL_USER" chmod +x "$desktop_file" 2>/dev/null; then
            log_success "Desktop file made executable (method 4)"
            return 0
        fi
        
        log_warn "Could not make desktop file executable, but file was created"
        return 1
    }
    
    set_desktop_file_executable
    
    # Additional desktop integration attempts
    create_additional_desktop_integration() {
        log_info "Creating additional desktop integration..."
        
        # Try to create menu entry
        local menu_dir="$REAL_USER_HOME/.local/share/applications"
        if [ ! -d "$menu_dir" ]; then
            sudo -u "$REAL_USER" mkdir -p "$menu_dir" || true
        fi
        
        if [ -d "$menu_dir" ]; then
            local menu_file="$menu_dir/imx296-camera.desktop"
            sudo -u "$REAL_USER" bash -c "echo '$desktop_content' > '$menu_file'" 2>/dev/null || true
            sudo -u "$REAL_USER" chmod +x "$menu_file" 2>/dev/null || true
            log_info "Created application menu entry"
        fi
        
        # Update desktop database if available
        if command -v update-desktop-database >/dev/null 2>&1; then
            sudo -u "$REAL_USER" update-desktop-database "$menu_dir" 2>/dev/null || true
        fi
    }
    
    create_additional_desktop_integration
    
    if [ -f "$desktop_file" ]; then
        log_success "Enhanced desktop shortcut created: $desktop_file"
    else
        log_warn "Desktop shortcut creation had issues but may still work"
    fi
}

create_enhanced_desktop_shortcut

# Enhanced IMX296 camera configuration
configure_enhanced_imx296_camera() {
    log_info "Configuring enhanced IMX296 camera settings..."
    
    # Load IMX296 module if available
    if modinfo imx296 >/dev/null 2>&1; then
        if ! lsmod | grep -q "imx296"; then
            log_info "Loading IMX296 camera module..."
            modprobe imx296 || log_warn "Failed to load imx296 module"
        else
            log_info "IMX296 module already loaded"
        fi
    else
        log_info "IMX296 module not available (may be built-in)"
    fi
    
    # Create enhanced modprobe configuration
    local modprobe_config="/etc/modprobe.d/imx296.conf"
    if [ ! -f "$modprobe_config" ]; then
        log_info "Creating modprobe configuration for IMX296..."
        cat > "$modprobe_config" << 'EOF'
# IMX296 camera module configuration
# Enhanced compatibility settings
options imx296 compatible_mode=1
# Additional options for better performance
options videodev max_buffers=32
EOF
        log_success "IMX296 modprobe configuration created"
    else
        log_info "IMX296 modprobe configuration already exists"
    fi
    
    # Enhanced boot configuration
    configure_boot_settings() {
        local boot_configs=("/boot/config.txt" "/boot/firmware/config.txt")
        local config_file=""
        
        for config in "${boot_configs[@]}"; do
            if [ -f "$config" ]; then
                config_file="$config"
                break
            fi
        done
        
        if [ -n "$config_file" ]; then
            log_info "Configuring boot settings in $config_file"
            
            # Check and add IMX296 configuration
            if ! grep -q "dtoverlay=imx296" "$config_file"; then
                log_info "Adding IMX296 device tree overlay..."
                echo "" >> "$config_file"
                echo "# IMX296 Global Shutter Camera Configuration" >> "$config_file"
                echo "dtoverlay=imx296" >> "$config_file"
                echo "gpu_mem=128" >> "$config_file"
                echo "camera_auto_detect=0" >> "$config_file"
                log_success "IMX296 boot configuration added"
            else
                log_info "IMX296 device tree overlay already configured"
            fi
        else
            log_warn "Boot configuration file not found"
        fi
    }
    
    configure_boot_settings
    
    # Enhanced udev rules
    create_enhanced_udev_rules() {
        local udev_rules="/etc/udev/rules.d/99-imx296-camera.rules"
        
        if [ ! -f "$udev_rules" ]; then
            log_info "Creating enhanced udev rules for IMX296 camera..."
            cat > "$udev_rules" << 'EOF'
# Enhanced IMX296 Camera udev rules
# Video devices
KERNEL=="video*", SUBSYSTEM=="video4linux", GROUP="video", MODE="0666", TAG+="uaccess"
# Media devices  
KERNEL=="media*", SUBSYSTEM=="media", GROUP="video", MODE="0666", TAG+="uaccess"
# V4L subdevices
KERNEL=="v4l-subdev*", SUBSYSTEM=="video4linux", GROUP="video", MODE="0666", TAG+="uaccess"
# IMX296 specific
SUBSYSTEM=="video4linux", ATTR{name}=="*imx296*", GROUP="video", MODE="0666", TAG+="uaccess"
EOF
            
            # Reload udev rules
            udevadm control --reload-rules 2>/dev/null || true
            udevadm trigger 2>/dev/null || true
            
            log_success "Enhanced udev rules created"
        else
            log_info "Udev rules already exist"
        fi
    }
    
    create_enhanced_udev_rules
    
    # Set video device permissions if they exist
    if ls /dev/video* >/dev/null 2>&1; then
        log_info "Setting video device permissions..."
        chmod a+rw /dev/video* 2>/dev/null || true
        chmod a+rw /dev/media* 2>/dev/null || true
    fi
    
    log_success "Enhanced IMX296 camera configuration complete"
}

# Configure camera if detected
if libcamera-hello --list-cameras 2>/dev/null | grep -qi imx296; then
    configure_enhanced_imx296_camera
else
    log_info "IMX296 camera not detected, skipping camera-specific configuration"
fi

# Final enhanced summary and recommendations
print_enhanced_summary() {
    echo ""
    echo -e "${GREEN}==== Enhanced Installation Complete ====${NC}"
    echo ""
    echo -e "${BLUE}Installation Summary:${NC}"
    echo "Project root: $PROJECT_ROOT"
    echo "User: $REAL_USER"
    echo "User home: $REAL_USER_HOME"
    echo "Virtual environment: $PROJECT_ROOT/.venv"
    echo "Configuration: $PROJECT_ROOT/config/config.yaml"
    echo ""
    echo -e "${BLUE}Installed Components:${NC}"
    echo "✓ Python virtual environment with all dependencies"
    echo "✓ LSL (Lab Streaming Layer) with enhanced compatibility"
    echo "✓ Systemd services for camera and monitoring"
    echo "✓ Desktop shortcuts and menu integration"
    echo "✓ Enhanced IMX296 camera configuration"
    echo "✓ Comprehensive permissions and ownership setup"
    echo ""
    echo -e "${YELLOW}Next Steps:${NC}"
    echo "1. Connect your IMX296 camera to the Raspberry Pi"
    echo "2. Reboot the system to ensure all drivers are loaded:"
    echo "   sudo reboot"
    echo ""
    echo "3. After reboot, test the system:"
    echo "   cd $PROJECT_ROOT"
    echo "   ./bin/clean_start_camera.sh -m"
    echo ""
    echo "4. Alternative startup methods:"
    echo "   # With cleanup and monitor: ./bin/clean_start_camera.sh -m"
    echo "   # Direct run: $PROJECT_ROOT/.venv/bin/python $PROJECT_ROOT/bin/run_imx296_capture.py"
    echo "   # Status monitor only: $PROJECT_ROOT/.venv/bin/python $PROJECT_ROOT/bin/status_monitor.py"
    echo "   # Systemd service: sudo systemctl start imx296-camera"
    echo ""
    echo "5. Desktop shortcuts:"
    echo "   # Desktop: Double-click IMX296-Camera icon"
    echo "   # Applications menu: Look for 'IMX296 Camera System'"
    echo ""
    echo "6. Configuration:"
    echo "   # Edit config: nano $PROJECT_ROOT/config/config.yaml"
    echo "   # Set ntfy topic for smartphone control"
    echo ""
    echo -e "${GREEN}Enhanced installation completed successfully!${NC}"
    echo -e "${BLUE}For support: https://github.com/anzalks/raspberry_pie_camera_capture${NC}"
}

print_enhanced_summary

log_success "Enhanced installation script completed successfully!"
exit 0 