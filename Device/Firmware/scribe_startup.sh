#!/bin/bash

# === CONFIG ===
REPO_URL="https://github.com/BuckDaTruck/Scribe.git"
CLONE_DIR="$HOME/Scribe"
SCRIPT_PATH="Device/Firmware/recorder.py"
REQS_PATH="Device/Firmware/requirements.txt"

echo "[SCRIBE SETUP] Starting..."

# Remove existing clone if it exists
if [ -d "$CLONE_DIR" ]; then
    echo "[SCRIBE SETUP] Removing existing repo..."
    rm -rf "$CLONE_DIR"
fi

# Clone the latest repo
echo "[SCRIBE SETUP] Cloning repo..."
git clone "$REPO_URL" "$CLONE_DIR"

# Install Python requirements
echo "[SCRIBE SETUP] Installing Python dependencies..."
pip3 install -r "$CLONE_DIR/$REQS_PATH"

# Run the recorder
echo "[SCRIBE SETUP] Running recorder..."
python3 "$CLONE_DIR/$SCRIPT_PATH"
