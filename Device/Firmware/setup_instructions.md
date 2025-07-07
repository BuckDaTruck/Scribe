# Raspberry Pi Audio Logger Setup Instructions

## Step 1: Download Minimal OS

Download Raspberry Pi OS Lite (64-bit) from the [official Raspberry Pi website](https://www.raspberrypi.com/software/operating-systems/#raspberry-pi-os-64-bit) and flash it to a micro‑SD card using Raspberry Pi Imager or a similar tool.

---

## Step 2: Configure Boot Settings

After flashing the card, mount the **boot** partition and add the following files so that the Pi connects to your network and allows SSH on first boot:

### Enable SSH

Create an empty file named `ssh`:

```bash
touch ssh
```

### Wi‑Fi Configuration

Create a file named `wpa_supplicant.conf` with your network details:

```bash
country=US
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
network={
    ssid="YourWiFi"
    psk="YourPassword"
    key_mgmt=WPA-PSK
}
```

---

## Step 3: Install Scribe Firmware

1. Boot the Pi and log in via SSH.
2. Clone this repository:

```bash
git clone https://github.com/BuckDaTruck/Scribe.git
```

3. Move the startup script to your home directory (the main directory) so it can be used at boot:

```bash
cd Scribe/Device/Firmware
mv start_scribe.sh ~/start_scribe.sh
chmod +x ~/start_scribe.sh
```

4. Run the helper script to install dependencies and start the recorder:

```bash
bash ~/start_scribe.sh
```

`start_scribe.sh` installs required packages, uses `requirements.txt` to install Python dependencies, and launches `recorder.py`.

If you prefer a manual setup, run the following instead of the script:

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-pip alsa-utils git
pip3 install -r requirements.txt
python3 recorder.py
```

---

## Step 4: Optional – Run on Boot

After moving `start_scribe.sh` to your home directory, you can configure
systemd to run it automatically on boot:

```bash
sudo nano /etc/systemd/system/scribe.service
```

Insert:

```ini
[Unit]
Description=Scribe Recorder
After=network.target

[Service]
ExecStart=/bin/bash /home/pi/start_scribe.sh
Restart=always
User=pi

[Install]
WantedBy=multi-user.target
```

Enable and start the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable scribe.service
sudo systemctl start scribe.service
```

To stop the service and disable it from starting at boot:

```bash
sudo systemctl stop scribe.service
sudo systemctl disable scribe.service
```

---

## Step 5: Record

After running `start_scribe.sh` or enabling the service, the Pi begins recording immediately. Use the connected buttons to mark highlights and to upload recordings as defined in `recorder.py`.
