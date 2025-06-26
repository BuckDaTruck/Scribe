✅ STEP 1: Install Required Packages
Run this once:

bash
Copy
Edit
sudo apt update
sudo apt install -y bluetooth bluez pi-bluetooth rfkill python3-gpiozero python3-requests
✅ STEP 2: Change the Bluetooth Name Only
Edit the Bluetooth config:

bash
Copy
Edit
sudo nano /etc/bluetooth/main.conf
Find (or add) the following line under [General]:

ini
Copy
Edit
Name = Buckley-Scribe
Then restart Bluetooth:

bash
Copy
Edit
sudo systemctl restart bluetooth
✅ Your Pi will now appear as Buckley-Scribe when other devices scan via Bluetooth.