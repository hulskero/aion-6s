#!/bin/bash
# Set AION daemon memory priority higher to avoid jetsam kills
# Usage: bash scripts/jetsam_setup.sh
# Requires: jetsamctl from Sileo/Cydia

echo "Configuring jetsam for AION-6S daemon..."

# Check for jetsamctl
if ! command -v jetsamctl &> /dev/null; then
    echo "jetsamctl not found. Install from Sileo:"
    echo "  Add repo: https://apt.procurs.us"
    echo "  Package: jetsamctl"
    exit 1
fi

# Set memory limit to 512MB (default is ~150MB for daemons)
echo "  Setting memory limit to 512MB..."
jetsamctl -l 512 com.aion.daemon 2>/dev/null || \
    echo "  (will apply when daemon is running)"

# Set priority to 16 (same as SpringBoard band)
# Ensures AION is killed after SpringBoard, not before
echo "  Setting jetsam priority to 16..."
jetsamctl -p 16 com.aion.daemon 2>/dev/null || \
    echo "  (will apply when daemon is running)"

echo ""
echo "Done. Verify with: jetsamctl com.aion.daemon"
echo ""
echo "To manually check current jetsam state:"
echo "  sysctl kern.memorystatus_pressure"
echo "  log stream --predicate 'eventMessage contains \"Jetsam\"'"
