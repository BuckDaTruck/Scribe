# Raspberry Pi Audio Logger Setup Instructions

## Step 1: Download Minimal OS

Download Raspberry Pi OS Lite (64-bit) from: [https://www.raspberrypi.com/software/operating-systems/#raspberry-pi-os-64-bit](https://www.raspberrypi.com/software/operating-systems/#raspberry-pi-os-64-bit)

Flash it to an SD card using Raspberry Pi Imager or Balena Etcher.

---

## Step 2: Configure Boot Settings (Wi-Fi, SSH)

After flashing, mount the **boot** partition and add:

### Enable SSH:

Create a blank file:

```bash
touch ssh
```

### Wi-Fi Configuration:

Create a file named `wpa_supplicant.conf` with:

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

## Step 3: Add Project Files

Copy the following to the **boot** partition:

- `recorder.py`
- `setup.sh` (installer script)

---

## Step 4: Auto-Run Installer on First Boot

Add to `/etc/rc.local` before `exit 0`:

```bash
bash /boot/setup.sh && rm /boot/setup.sh
```

This will run the installer script once, set everything up, and delete it afterward.

---

## Step 5: Script Installer (`setup.sh`)

This script installs dependencies and enables the audio logger as a system service:

```bash
#!/bin/bash

apt update
apt install -y python3 python3-pip alsa-utils git
pip3 install requests gpiozero

mkdir -p /home/pi/audio
mv /boot/recorder.py /home/pi/recorder.py
chmod +x /home/pi/recorder.py

cat <<EOF | tee /etc/systemd/system/recorder.service
[Unit]
Description=Audio Recorder
After=network.target

[Service]
ExecStart=/usr/bin/python3 /home/pi/recorder.py
WorkingDirectory=/home/pi
StandardOutput=inherit
StandardError=inherit
Restart=always
User=pi

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable recorder.service
systemctl start recorder.service
```
To stop the Scribe service immediately and prevent it from coming back on reboot, you can use systemd’s stop/disable commands:

bash
Copy
Edit
# Stop it right now
sudo systemctl stop scribe.service

# Prevent it from starting at boot
sudo systemctl disable scribe.service
If you ever want to re-enable it:

bash
Copy
Edit
sudo systemctl enable scribe.service
sudo systemctl start  scribe.service
---

## Step 6: Boot and Deploy

Insert the SD card into your Pi and power on. It will connect to Wi-Fi, install everything, and begin logging automatically.

