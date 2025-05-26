#!/bin/bash
# 
# IMX296 Camera System - Clean Start Script
# ========================================
#
# Simple wrapper script for cleaning up and starting the camera system
# without conflicts from previous installations.
#
# Author: Anzal KS <anzal.ks@gmail.com>
# Date: December 2024
#

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo -e "${BLUE}🎥 IMX296 Camera System - Clean Start${NC}"
echo -e "${BLUE}=====================================${NC}"
echo ""

# Change to project directory
cd "$PROJECT_ROOT" || {
    echo -e "${RED}❌ Error: Could not change to project directory${NC}"
    exit 1
}

# Function to show usage
show_usage() {
    echo "Usage: $0 [options]"
    echo ""
    echo "Options:"
    echo "  -m, --monitor          Start with status monitor"
    echo "  -c, --cleanup-only     Cleanup only, don't start service"
    echo "  -n, --no-cleanup       Skip cleanup, start directly"
    echo "  -l, --logs             Include log files in cleanup"
    echo "  -v, --verify           Verify system state only"
    echo "  -h, --help             Show this help"
    echo ""
    echo "Examples:"
    echo "  $0                     # Clean start (service only)"
    echo "  $0 -m                  # Clean start with monitor"
    echo "  $0 -c                  # Cleanup only"
    echo "  $0 -v                  # Check current state"
    echo ""
}

# Parse command line arguments
ARGS=""
while [[ $# -gt 0 ]]; do
    case $1 in
        -m|--monitor)
            ARGS="$ARGS --monitor"
            shift
            ;;
        -c|--cleanup-only)
            ARGS="$ARGS --cleanup-only"
            shift
            ;;
        -n|--no-cleanup)
            ARGS="$ARGS --no-cleanup"
            shift
            ;;
        -l|--logs)
            ARGS="$ARGS --logs"
            shift
            ;;
        -v|--verify)
            ARGS="$ARGS --verify-only"
            shift
            ;;
        -h|--help)
            show_usage
            exit 0
            ;;
        *)
            echo -e "${RED}❌ Unknown option: $1${NC}"
            show_usage
            exit 1
            ;;
    esac
done

# Check if Python 3 is available
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Error: Python 3 is not installed${NC}"
    exit 1
fi

# Check if the cleanup script exists
CLEANUP_SCRIPT="bin/cleanup_and_start.py"
if [[ ! -f "$CLEANUP_SCRIPT" ]]; then
    echo -e "${RED}❌ Error: Cleanup script not found: $CLEANUP_SCRIPT${NC}"
    exit 1
fi

# Show what we're about to do
if [[ "$ARGS" == *"--verify-only"* ]]; then
    echo -e "${YELLOW}🔍 Verifying system state...${NC}"
elif [[ "$ARGS" == *"--cleanup-only"* ]]; then
    echo -e "${YELLOW}🧹 Performing cleanup only...${NC}"
elif [[ "$ARGS" == *"--no-cleanup"* ]]; then
    echo -e "${YELLOW}🚀 Starting service directly (no cleanup)...${NC}"
else
    echo -e "${YELLOW}🧹 Cleaning up and starting camera system...${NC}"
fi

echo ""

# Run the Python cleanup script
echo -e "${BLUE}Executing: python3 $CLEANUP_SCRIPT $ARGS${NC}"
echo ""

python3 "$CLEANUP_SCRIPT" $ARGS
EXIT_CODE=$?

echo ""
if [[ $EXIT_CODE -eq 0 ]]; then
    echo -e "${GREEN}✅ Operation completed successfully${NC}"
else
    echo -e "${RED}❌ Operation failed with exit code $EXIT_CODE${NC}"
fi

exit $EXIT_CODE 