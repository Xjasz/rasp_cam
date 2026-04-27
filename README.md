# Raspberry Pi Camera Client

Raspberry Pi camera client for Codalata RASP.

## Install

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

Stop it:

```bash
CTRL+C
```

## One-line install after boot

```bash
git clone https://github.com/xjasz/rasp_cam.git && cd rasp_cam && chmod +x install.sh run.sh && ./install.sh "YOUR_DEVICE_KEY"
```

Then start it:

```bash
./run.sh
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

Do not commit `.env`.

`cam_main.py` reads the key from `RASP_DEVICE_KEY`.

## Dependencies

The installer installs the Raspberry Pi camera/OpenCV packages through apt:

```text
python3-picamera2
python3-opencv
python3-numpy
```

The installer installs app-specific Python packages through pip:

```text
requests
adafruit-circuitpython-servokit
```

## Run again later

```bash
cd rasp_cam
./run.sh
```
