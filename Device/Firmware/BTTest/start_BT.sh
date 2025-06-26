#!/bin/bash

# Move to home directory
cd ~

sudo apt-get update
sudo apt install -y bluetooth bluez pi-bluetooth rfkill python3-gpiozero python3-requests



# Remove existing Scribe directory
sudo rm -rf Scribe


# Clone the GitHub repo
git clone https://github.com/BuckDaTruck/Scribe.git 

# Change to the firmware directory
cd Scribe/Device/Firmware/BTTest/

# Install Python requirements
pip3 install -r requirements.txt 

# Run the recorder script with lolcat-ized output
python3 btpair.py 



