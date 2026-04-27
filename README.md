# Raspberry Pi Camera Client

Raspberry Pi camera client for Codalata RASP.

## Install options

Use the normal install if you want to start the camera manually.

Use the service install if you want the camera to start automatically when the Raspberry Pi boots.

## Step-by-step manual install

```bash
git clone https://github.com/xjasz/rasp_cam.git
cd rasp_cam
./install.sh "YOUR_DEVICE_KEY"
./run.sh
```
Add service later after manual install
```bash
./install.sh --service
```

## One-line installs
manual:
```bash
git clone https://github.com/xjasz/rasp_cam.git && cd rasp_cam && bash ./install.sh "YOUR_DEVICE_KEY" && bash ./run.sh
```
service:
```bash
git clone https://github.com/xjasz/rasp_cam.git && cd rasp_cam && bash ./install.sh "YOUR_DEVICE_KEY" --service
```

## Service commands

```bash
sudo systemctl status codalata-rasp-cam
journalctl -u codalata-rasp-cam -f
sudo systemctl restart codalata-rasp-cam
sudo systemctl stop codalata-rasp-cam
./uninstall_service.sh
```

## Repo files

```text
cam_main.py
requirements.txt
install.sh
install_service.sh
uninstall_service.sh
run.sh
scripts/
  stop_existing.sh
helpers/
  __init__.py
  colormod.py
  main_logger.py
  rasp_servo.py
```

## Device key

The installer creates a local `.env` file:

```env
RASP_DEVICE_KEY=YOUR_DEVICE_KEY
```

## Dependencies

The installer installs the Raspberry Pi camera/OpenCV packages through apt and app-specific Python packages through pip:

```text
python3-picamera2
python3-opencv
python3-numpy
requests
adafruit-circuitpython-servokit
```
