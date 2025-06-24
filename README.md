# Raspberry Pi Audio Logger

## Overview
This project transforms a Raspberry Pi Zero 2 W into a field-deployable audio recording and highlight-logging device. It continuously records microphone input, logs highlight windows via button press, and uploads all data to a remote web server at regular intervals.

---

## Features

- **Continuous audio recording** in 30-minute chunks
- **Highlight logging**: capture 2 minutes before + 5 minutes after button press
- **Automatic and manual upload** to a web server
- **LED status indicator**:
  - Solid Green: Recording
  - Pulsing Green: Highlight window active
  - Pulsing Blue: Uploading
  - Solid Red: Error state
- **Auto-deletes old recordings** after upload to save space
- **Headless bootable setup** from SD card

---

## Hardware Required

- Raspberry Pi Zero 2 W
- INMP441 I2S Microphone
- Common Cathode RGB LED (with 3x 330Ω resistors)
- 2x Push Buttons
- 18650 Battery (or USB power)

Wiring details can be found in [`Wiring Instructions`](./Wiring%20Instructions.md).

---

## Software & Setup

All setup can be done by preparing an SD card with:

- Raspberry Pi OS Lite
- Preloaded project files
- Wi-Fi and SSH configured

Detailed steps are provided in [`Setup Instructions`](./Setup%20Instructions.md).

---

## Files

- `recorder.py`: Main script to record, highlight, and upload
- `setup.sh`: One-time setup script to install dependencies and enable systemd service
- `requirements.txt`: Python dependencies (`requests`, `gpiozero`)

---

## Server Configuration

- Upload URL: `https://buckleywiley.com/Scribe/upload.php`
- Accepts only `.wav`, `.mp3`, and `.csv`
- Requires `api_key` = `@YourPassword123`
- Logs upload IP, filename, and timestamps to a separate `.csv`

---

## License
MIT or similar open license. Customize and deploy freely.

---

## Credits
Project created and maintained by Buckley Wiley.

