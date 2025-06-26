#!/bin/bash

# Move to home directory
cd ~

sudo apt-get update


# Remove existing Scribe directory
sudo rm -rf Scribe

# Clone the GitHub repo
git clone https://github.com/BuckDaTruck/Scribe.git 

# Change to the firmware directory
cd Scribe/Device/Firmware/

# Install Python requirements
pip3 install -r requirements.txt 

# Run the recorder script with lolcat-ized output
python3 recorder.py 



