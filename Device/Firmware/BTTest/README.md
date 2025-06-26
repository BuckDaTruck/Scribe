# Bluetooth Pairing Utility

This folder contains a small script to pair your Raspberry Pi with a mobile phone and use the phone's internet connection via Bluetooth PAN. A single button triggers pairing or connecting depending on whether a paired device is already saved.

## Prerequisites

Install the required packages once:

```bash
sudo apt update
sudo apt install -y bluetooth bluez pi-bluetooth rfkill python3-gpiozero python3-requests
```

(Optional) Change the advertised Bluetooth name by editing `/etc/bluetooth/main.conf` and setting:

```ini
Name = Buckley-Scribe
```

Restart Bluetooth to apply the change:

```bash
sudo systemctl restart bluetooth
```

## Usage

1. Run the helper script to clone the repository and start the pairing utility:

```bash
bash start_BT.sh
```

   This installs dependencies, pulls the repository and launches `btpair.py`.
2. Once running, press the connected button to initiate pairing. If the Pi already knows a device, it attempts to reconnect via PAN instead.
3. The script gives feedback through the RGB LED:
   - **Yellow** – pairing mode active
   - **Blue pulse** – waiting for user action
   - **Green** – internet connection detected
   - **Red** – connection failed

The MAC address of the paired phone is stored at `/etc/scribe/phone_mac.conf` for future connections.

## Files

- `btpair.py` – main script handling pairing, connection and LED feedback
- `start_BT.sh` – helper script that clones this repository and runs `btpair.py`
- `instructions.md` – brief setup notes


