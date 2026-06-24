#!/bin/bash
AION_DIR="$HOME/Documents/aion-6s"
cd "$AION_DIR" || exit 1
echo "TIP: Disable Auto-Lock in Settings > Display & Brightness"
python3 aion.py "$@"
