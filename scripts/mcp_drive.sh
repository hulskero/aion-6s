#!/bin/bash
# mcp_drive.sh — Drive iPhone via iOS MCP from command line
# Usage: ./scripts/mcp_drive.sh <tool> [args...]
#
# Examples:
#   ./scripts/mcp_drive.sh screenshot
#   ./scripts/mcp_drive.sh get_screen_info
#   ./scripts/mcp_drive.sh get_frontmost_app
#   ./scripts/mcp_drive.sh tap_screen '{"x":200,"y":300}'
#   ./scripts/mcp_drive.sh run_command '{"command":"uname -a"}'
#   ./scripts/mcp_drive.sh launch_app '{"bundle_id":"com.apple.mobilesafari"}'
#   ./scripts/mcp_drive.sh describe_screen '{"include_ocr":true}'

MCP_HOST="${MCP_HOST:-192.168.1.250}"
MCP_PORT="${MCP_PORT:-8090}"
MCP_URL="http://${MCP_HOST}:${MCP_PORT}"
ID=1

if [ $# -lt 1 ]; then
    echo "Usage: $0 <tool> [json_args]"
    echo ""
    echo "Available tools (use list_tools to see all):"
    echo "  list_tools"
    echo "  describe_screen"
    echo "  screenshot"
    echo "  get_screen_info"
    echo "  get_frontmost_app"
    echo "  get_device_info"
    echo "  get_ui_elements"
    echo "  ocr_screen"
    echo "  tap_screen"
    echo "  swipe_screen"
    echo "  input_text"
    echo "  press_home"
    echo "  wake_and_home"
    echo "  run_command"
    echo "  launch_app"
    echo "  get_clipboard"
    exit 1
fi

TOOL="$1"
shift

if [ "$TOOL" = "list_tools" ]; then
    curl -sS --connect-timeout 5 --max-time 10 \
        -X POST "${MCP_URL}/mcp" \
        -H "Content-Type: application/json" \
        -d "{\"jsonrpc\":\"2.0\",\"id\":$ID,\"method\":\"tools/list\"}" | \
        python3 -m json.tool 2>/dev/null || \
        curl -sS --connect-timeout 5 --max-time 10 \
            -X POST "${MCP_URL}/mcp" \
            -H "Content-Type: application/json" \
            -d "{\"jsonrpc\":\"2.0\",\"id\":$ID,\"method\":\"tools/list\"}"
    exit $?
fi

if [ "$TOOL" = "health" ]; then
    curl -sS --connect-timeout 5 --max-time 10 "${MCP_URL}/health" | python3 -m json.tool 2>/dev/null || \
    curl -sS --connect-timeout 5 --max-time 10 "${MCP_URL}/health"
    exit $?
fi

ARGS="${1:-{}}"

curl -sS --connect-timeout 5 --max-time 15 \
    -X POST "${MCP_URL}/mcp" \
    -H "Content-Type: application/json" \
    -d "{\"jsonrpc\":\"2.0\",\"id\":$ID,\"method\":\"tools/call\",\"params\":{\"name\":\"$TOOL\",\"arguments\":$ARGS}}" | \
    python3 -m json.tool 2>/dev/null || \
    curl -sS --connect-timeout 5 --max-time 15 \
        -X POST "${MCP_URL}/mcp" \
        -H "Content-Type: application/json" \
        -d "{\"jsonrpc\":\"2.0\",\"id\":$ID,\"method\":\"tools/call\",\"params\":{\"name\":\"$TOOL\",\"arguments\":$ARGS}}"
