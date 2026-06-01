#!/bin/bash
# Install AION-6S as a launchd daemon (run on jailbroken iPhone via NewTerm)
# Usage: bash scripts/install_daemon.sh
# Requires: palera1n/checkra1n jailbreak, python3 from Procursus/Sileo

AION_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DAEMON_PLIST="/Library/LaunchDaemons/com.aion.daemon.plist"
DAEMON_LOG="/var/tmp/aion-daemon.log"
DAEMON_ERR="/var/tmp/aion-daemon.err"

echo "Installing AION-6S daemon from $AION_DIR"

# Write launchd plist
cat > "$DAEMON_PLIST" << 'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.aion.daemon</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>PLACEHOLDER</string>
        <string>--headless</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>ThrottleInterval</key>
    <integer>10</integer>
    <key>UserName</key>
    <string>mobile</string>
    <key>SessionCreate</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/var/tmp/aion-daemon.log</string>
    <key>StandardErrorPath</key>
    <string>/var/tmp/aion-daemon.err</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>NVIDIA_API_KEY</key>
        <string>__API_KEY__</string>
        <key>PATH</key>
        <string>/var/jb/usr/bin:/usr/bin:/usr/local/bin:/bin</string>
        <key>PYTHONUNBUFFERED</key>
        <string>1</string>
        <key>AION_DAEMON</key>
        <string>1</string>
    </dict>
</dict>
</plist>
PLIST

# Replace placeholders
sed -i '' "s|PLACEHOLDER|${AION_DIR}/aion.py|g" "$DAEMON_PLIST"

# Prompt for API key
echo ""
echo "Enter your NVIDIA_API_KEY (nvapi-...):"
read -r API_KEY
if [ -n "$API_KEY" ]; then
    sed -i '' "s|__API_KEY__|$API_KEY|g" "$DAEMON_PLIST"
else
    echo "WARNING: No API key set. Set NVIDIA_API_KEY env var before starting."
    sed -i '' "s|__API_KEY__||g" "$DAEMON_PLIST"
fi

# Set permissions and load
chown root:wheel "$DAEMON_PLIST"
chmod 644 "$DAEMON_PLIST"

echo "Loading daemon..."
launchctl load "$DAEMON_PLIST"

echo ""
echo "Done! AION-6S daemon installed."
echo "  Logs: $DAEMON_LOG"
echo "  Stop: launchctl unload $DAEMON_PLIST"
echo "  Status: launchctl list com.aion.daemon"
