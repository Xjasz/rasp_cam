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

The unit name carries the version from the `VERSION` file, for example `codalata-rasp-cam-1.4.2`.

```bash
sudo systemctl status codalata-rasp-cam-<version>
journalctl -u codalata-rasp-cam-<version> -f
sudo systemctl restart codalata-rasp-cam-<version>
sudo systemctl stop codalata-rasp-cam-<version>
./uninstall_service.sh
```

`uninstall_service.sh` removes the unit and then deletes this install folder, including `.env` with the device key, five seconds later.

The service install also writes `/etc/sudoers.d/codalata-rasp-cam` so the headless self-update and remote reboot can run `reboot`, `systemctl`, `tee` and `rm` without a password.

## Repo files

```text
cam_main.py
VERSION
requirements.txt
install.sh
uninstall_service.sh
run.sh
scripts/
  stop_existing.sh
helpers/
  colormod.py
  main_logger.py
  rasp_audio.py
  rasp_servo.py
  update_runner.py
  version_manager.py
```

## Device key

The installer creates a local `.env` file:

```env
RASP_DEVICE_KEY=YOUR_DEVICE_KEY
```

## Dependencies

The installer creates a `.venv` with system site packages and pip-installs `requirements.txt` into it. It does not install picamera2, OpenCV or numpy; those come from Raspberry Pi OS (`sudo apt install python3-picamera2 python3-opencv python3-numpy` if they are missing):

```text
python3-picamera2
python3-opencv
python3-numpy
requests
adafruit-circuitpython-servokit
```
