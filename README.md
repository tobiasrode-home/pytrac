___AB hier ist neu_____

```
echo " video=DSI-2:720x1280@60,rotate=270" >> /boot/firmware/cmdline.txt

apt update
apt install -y python3 python3-pip python3-venv python3-pyproj python3-shapely python3-dev build-essential git pkg-config libgl1-mesa-dev libgles2-mesa-dev libgles-dev libmtdev-dev libinput-dev libavformat-dev libavcodec-dev libswscale-dev libjpeg-dev zlib1g-dev sqlite3 python3-serial python3-kivy python3-uvicorn python3-fastapi python3-pydantic-settings

pip install kivy-garden.mapview adafruit-circuitpython-bno08x-rvc sqlalchemy pynmea2  --break-system-packages


cd /opt

git clone https://github.com/tobiasrode-home/pytrac





cd /opt
rm -r pytrac/
git clone https://github.com/tobiasrode-home/pytrac
cp -r data pytrac/
cp .env pytrac/
cd pytrac/
/usr/bin/python3 -m uvicorn pytrac_backend:app --host 0.0.0.0 --port 8000 --reload --no-access-log
/usr/bin/python3 /opt/pytrac/pytrac_kivy/main.py

```
