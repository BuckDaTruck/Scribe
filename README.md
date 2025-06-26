# Scribe Audio Logger

Scribe turns a Raspberry Pi Zero 2 W into a self contained field recorder. The device records audio
continuously, lets you mark highlights with a button and can upload everything to a web server for
safe keeping.

This repository contains two major components:

- **Device/** – firmware, wiring instructions and setup scripts for the Pi based recorder.
- **WebServer/** – a small PHP endpoint that accepts uploads from the device.

---

## Features

- Continuous audio capture split into manageable chunks
- Highlight logging with a single button press
- Manual or automatic uploads to a remote server
- RGB LED feedback for recording, highlighting and errors
- Old files are removed after successful upload to conserve space

---

## Quick Start
1. Assemble the hardware as shown in [Device/wiring_instructions.md](Device/wiring_instructions.md).
2. Prepare a micro‑SD card following
   [Device/Firmware/setup_instructions.md](Device/Firmware/setup_instructions.md).
3. Boot the Pi – it will begin recording automatically.
4. Use the highlight button to mark moments of interest. Press the upload button to send files to
the server defined in `recorder.py`.

---

## Repository Layout

```
Device/          # Firmware, wiring and setup for the Pi recorder
WebServer/       # PHP upload endpoint and test client
README.md        # This file
```

---

## Server Configuration
The PHP script in `WebServer/upload.php` accepts `.opus` audio and highlight CSV files. Update
`$apiKey` and `$uploadBaseDir` to suit your environment. A simple Python test client is also
provided in `WebServer/test.py`.

---

## License
This project is released under the MIT license. See the source files for details.

---

## Credits
Created and maintained by Buckley Wiley.
