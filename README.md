# Raspberry Pi Camera Client

Raspberry Pi camera client for Codalata RASP.

## One-line intial install

```bash
git clone https://github.com/xjasz/rasp_cam.git && cd rasp_cam && chmod +x install.sh run.sh && ./install.sh "YOUR_DEVICE_KEY"
```
## One-line service install
```bash
git clone https://github.com/xjasz/rasp_cam.git && cd rasp_cam && chmod +x install_service.sh && ./install_service.sh "YOUR_DEVICE_KEY"
```

## Optional setp by step Install

Clone the repo:

```bash
git clone https://github.com/xjasz/rasp_cam.git
cd rasp_cam
```

Install with your generated device key:

```bash
chmod +x install.sh run.sh
./install.sh "YOUR_DEVICE_KEY"
```

Start the camera:

```bash
./run.sh
```

Useful commands:

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
run.sh
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

## Run again later

```bash
cd rasp_cam
./run.sh
```
