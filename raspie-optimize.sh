#!/bin/bash
# Optimization script for Raspie Capture on Raspberry Pi
# This script adjusts system settings to improve video capture performance

# Root check
if [ "$(id -u)" -ne 0 ]; then
    echo "This script must be run as root. Please use sudo."
    exit 1
fi

echo "Applying performance optimizations for Raspie Capture..."

# 1. Set CPU governor to performance mode
echo "Setting CPU governor to performance mode..."
for cpu in /sys/devices/system/cpu/cpu[0-9]*; do
    echo performance > $cpu/cpufreq/scaling_governor
done
echo "CPU governor set to performance"

# 2. Increase GPU memory allocation
echo "Increasing GPU memory..."
if grep -q "gpu_mem=" /boot/config.txt; then
    # Update existing gpu_mem value
    sed -i 's/gpu_mem=[0-9]*/gpu_mem=256/' /boot/config.txt
else
    # Add gpu_mem if it doesn't exist
    echo "gpu_mem=256" >> /boot/config.txt
fi
echo "GPU memory set to 256MB"

# 3. Increase USB bus power for USB microphones
echo "Increasing USB bus power for more stable audio capture..."
if grep -q "max_usb_current=1" /boot/config.txt; then
    echo "USB current already set to maximum"
else
    echo "max_usb_current=1" >> /boot/config.txt
    echo "USB current setting added"
fi

# 4. Disable unnecessary services
echo "Disabling unnecessary services..."
SERVICES_TO_DISABLE=(
    "bluetooth.service"
    "cups.service"
    "avahi-daemon.service"
)

for service in "${SERVICES_TO_DISABLE[@]}"; do
    if systemctl is-active --quiet "$service"; then
        systemctl stop "$service"
        systemctl disable "$service"
        echo "Disabled $service"
    else
        echo "$service is already disabled or not installed"
    fi
done

# 5. Set process priorities
echo "Setting process priority rules..."
cat > /etc/security/limits.d/raspie-capture.conf << EOF
# Higher priority for raspie-capture processes
$SUDO_USER hard nice -10
$SUDO_USER hard rtprio 99
EOF
echo "Process priority rules created"

# 6. Create a RAM disk for temporary files (helps with high bitrate recordings)
echo "Creating RAM disk for temporary files..."
mkdir -p /mnt/ramdisk
if grep -q "/mnt/ramdisk" /etc/fstab; then
    echo "RAM disk already configured in fstab"
else
    echo "tmpfs /mnt/ramdisk tmpfs defaults,noatime,size=512M 0 0" >> /etc/fstab
    mount -a
    echo "RAM disk created and mounted at /mnt/ramdisk"
fi

# 7. Update the service configuration to use the RAM disk
if [ -f /etc/systemd/system/raspie-capture.service ]; then
    echo "Updating raspie-capture service to use RAM disk..."
    # This uses temp files in RAM, then moves completed recordings to permanent storage
    sed -i 's/ExecStart=.*/ExecStart=\/bin\/bash -c "TMPDIR=\/mnt\/ramdisk '$INSTALL_DIR'\/.venv\/bin\/python -m raspberry_pi_lsl_stream.cli --enable-audio --use-buffer --buffer-size 20 --ntfy-topic raspie_trigger --threaded-writer --codec h264 --output-path \/mnt\/ramdisk"/' /etc/systemd/system/raspie-capture.service
    systemctl daemon-reload
    echo "Service updated to use RAM disk"
else
    echo "Warning: raspie-capture service not found. Run raspie-capture-service.sh first."
fi

echo "Performance optimizations applied. A reboot is recommended."
echo "To reboot now, enter: sudo reboot" 