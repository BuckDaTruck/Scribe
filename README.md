# Scribe Audio Logger

Scribe transforms a Raspberry Pi Zero 2 W into a compact field recorder. Audio is captured continuously and each press of a hardware button marks highlights. Files can be queued for upload to a web server so recordings remain safe even if the Pi is lost.

This repository is organised into two main parts:

- **Device/** – firmware, wiring guides and setup instructions for the Raspberry Pi.
- **WebServer/** – a minimal PHP endpoint and helper scripts to receive uploads.

---

## Features

- Continuous audio capture split into timestamped chunks
- Highlight logging via a physical button
- Manual or automated upload of recordings to a server
- RGB LED status feedback and simple push‑button controls
- Old files are pruned after a successful upload to free space

---

## Hardware Overview

The hardware build uses the following components:

- Raspberry Pi Zero 2 W
- INMP441 I²S microphone
- Two push buttons: one for highlights and one for initiating uploads
- RGB LED with resistors for visual feedback

Wiring diagrams and a detailed parts list are provided in
[Device/wiring_instructions.md](Device/wiring_instructions.md).

## 3D-Printed Case

All enclosure files live in the `Device/Cad/` directory. The STL models were
printed on an **Anycubic S1** and should be compatible with most desktop
printers. If you want to modify the design, the original Onshape project
is available at [this link](https://cad.onshape.com/documents/3eb0c03f667fd218b6465f3e/w/64f544e1ef4dcc4bc9220305/e/b0f011cba6411f833e96eb2d?renderMode=0&uiState=686c31687eb09201081bcbbc).
A preconfigured `Scribe.3mf` file is also included for quick slicing.

---

## Quick Start

1. Assemble the hardware as described in the wiring instructions.
2. Follow the steps in
   [Device/Firmware/setup_instructions.md](Device/Firmware/setup_instructions.md)
   to flash the operating system and install dependencies.
3. Boot the Pi—recording starts automatically.
4. Press the highlight button to log an interesting moment.
5. Press the upload button or wait for automatic uploads to send files to the
   server configured in `recorder.py`.

Recordings are stored as `.opus` files and highlight timestamps are saved to
CSV. Successful uploads remove the local copies to keep the SD card clean.

---

## Web Server

The `WebServer` directory contains `upload.php`, a small PHP script that accepts
incoming audio and CSV files. Set `$apiKey` and `$uploadBaseDir` inside the
script to match your environment. A Python utility, `test.py`, demonstrates how
to POST files to the server for testing without the device.

---

## Repository Layout

```
Device/Cad/     # 3D models and CAD files for the case
Device/         # Firmware, setup scripts and hardware docs
WebServer/      # PHP endpoint and test client
README.md       # Project overview (this file)
```

---

## Contributing

Bug reports and pull requests are welcome. Feel free to open an issue if you run
into problems while building your own logger.

---

## License

This project is released under the MIT license. See individual source files for
full license text.

---

## Credits

Created and maintained by Buckley Wiley.
