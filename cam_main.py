import os
import subprocess
import threading
import time
import cv2
import requests
from picamera2 import Picamera2

from helpers.colormod import (ColorFinder, bump_color_tolerance, cycle_channel, apply_center_change, mask_values_from_center, overlay_legend_on_frame, legend_block)
from helpers.main_logger import logger, application_error_handler

try:
    from helpers.rasp_servo import ServoKit, ServoUnavailableError
except Exception as ex:
    ServoKit = None
    ServoUnavailableError = Exception
    logger.info("Servo module unavailable: %s", ex)

DEVICE_KEY = os.getenv("RASP_DEVICE_KEY", "").strip() # Add your DEVICE_KEY generated from the server in the double quotes as an environment variable or in the double quotes.
if not DEVICE_KEY:
    raise RuntimeError("Missing RASP_DEVICE_KEY. Run ./install.sh YOUR_DEVICE_KEY before starting.")

SERVER_BASE_URL = "https://www.codalata.com/modules/rasp"
UPLOAD_URL = f"{SERVER_BASE_URL}/upload_frame.php"
POLL_EVENT_URL = f"{SERVER_BASE_URL}/poll_event.php"
UPLOAD_PICTURE_URL = f"{SERVER_BASE_URL}/upload_picture.php"
UPLOAD_TIMELINE24_URL = f"{SERVER_BASE_URL}/upload_timeline24.php"


stream_enabled = True
viewer_active = False
last_command_id = 0
last_transient_seq = 0
poll_failures = 0

manual_control_enabled = True
opencv_tracking_enabled = False
lock_object_enabled = False
debug_enabled = False
basic_detection_enabled = False
color_filter_enabled = False
show_color_legend = False

# ---------------------------
# Color Filtering and Tolerance
# ---------------------------
color_space = "HSV"
color_center = (120, 120, 120)
color_tol = 0
color_channel_selected = "ALL"
color_finder = ColorFinder(color_type=color_space)
color_finder.set_center(color_center)
color_finder.set_tolerance((color_tol, color_tol, color_tol))
color_finder.enable_tolerance(True)
# ---------------------------
# Initialize Frame Lock
# ---------------------------
shutdown_event = threading.Event()
frame_lock = threading.Lock()
latest_jpeg = None
latest_frame_id = 0
# ---------------------------
# Initialize Camera
# ---------------------------
picam2 = Picamera2()
config = picam2.create_video_configuration(main={"format": "RGB888", "size": (800, 600)})
picam2.configure(config)
picam2.set_controls({"FrameRate": 60})
picam2.start()
# ---------------------------
# Initialize Sessions
# ---------------------------
upload_session = requests.Session()
poll_session = requests.Session()
# ---------------------------
# Initialize Servo
# ---------------------------
servo_lock = threading.Lock()
try:
    rasp_servokit = ServoKit(2) if ServoKit else None
except ServoUnavailableError as ex:
    rasp_servokit = None
    logger.info("Servo unavailable: %s", ex)
except Exception:
    rasp_servokit = None
    logger.exception("Servo initialization failed")
PAN_ANGLE = 0
TILT_ANGLE = 0

def build_session():
    global DEVICE_KEY
    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(pool_connections=2,pool_maxsize=2,max_retries=0)
    session.mount("https://", adapter)
    session.headers.update({"X-Device-Key": DEVICE_KEY,"User-Agent": "cam-client/1.0","Connection": "keep-alive"})
    return session

def reset_poll_session():
    global poll_session
    try:
        poll_session.close()
    except Exception:
        pass
    poll_session = build_session()

def reboot_device():
    logger.info("reboot_device received — rebooting now")
    try:
        subprocess.Popen(['/usr/bin/sudo', '/sbin/reboot'])
    except Exception as e:
        logger.error(f"Failed to reboot: {e}", exc_info=True)

def seconds_to_next_hour():
    return 3600 - int(time.time()) % 3600

def move_servo(label, port, delta):
    global PAN_ANGLE, TILT_ANGLE
    if rasp_servokit is None:
        logger.debug("%s ignored. Servo unavailable.", label)
        return
    try:
        with servo_lock:
            fallback = PAN_ANGLE if port == 0 else TILT_ANGLE
            current_angle = rasp_servokit.getAngle(port)
            new_angle = (fallback if current_angle is None else current_angle) + delta
            rasp_servokit.setAngle(port, new_angle)
        if port == 0:
            PAN_ANGLE = new_angle
            logger.debug("%s pan=%s", label, PAN_ANGLE)
        else:
            TILT_ANGLE = new_angle
            logger.debug("%s tilt=%s", label, TILT_ANGLE)
    except Exception:
        logger.exception("Servo move failed. label=%s port=%s delta=%s", label, port, delta)

def move_left():
    move_servo("LEFT", 1, -5)

def move_right():
    move_servo("RIGHT", 1, 5)

def move_up():
    move_servo("UP", 0, 5)

def move_down():
    move_servo("DOWN", 0, -5)

def reset_servos():
    global PAN_ANGLE, TILT_ANGLE
    if rasp_servokit is None:
        logger.info("Manual: Reset servos ignored. Servo unavailable.")
        return
    try:
        logger.info("Manual: Reset servos.")
        with servo_lock:
            rasp_servokit.resetAll()
            PAN_ANGLE = rasp_servokit.getAngle(0) or PAN_ANGLE
            TILT_ANGLE = rasp_servokit.getAngle(1) or TILT_ANGLE
    except Exception:
        logger.exception("Servo reset failed")

def toggle_stream():
    global stream_enabled
    stream_enabled = not stream_enabled
    logger.info(f"STREAM toggled to {'ON' if stream_enabled else 'OFF'}")

def toggle_tracking():
    global opencv_tracking_enabled
    if stream_enabled:
        opencv_tracking_enabled = not opencv_tracking_enabled
        logger.info(f"OpenCV tracking toggled to {'ON' if opencv_tracking_enabled else 'OFF'}")
    else:
        logger.info("Cannot toggle tracking because stream is OFF")

def toggle_manual_control():
    global manual_control_enabled, opencv_tracking_enabled
    manual_control_enabled = not manual_control_enabled
    if manual_control_enabled:
        opencv_tracking_enabled = False
        logger.info("Manual control enabled; OpenCV tracking disabled")
    else:
        logger.info("Manual control disabled; automatic tracking allowed")

def toggle_debug():
    global debug_enabled
    debug_enabled = not debug_enabled
    logger.info(f"Debug mode toggled to {'ON' if debug_enabled else 'OFF'}")

def toggle_lock_object():
    global lock_object_enabled
    lock_object_enabled = not lock_object_enabled
    logger.info(f"Object lock toggled to {'ON' if lock_object_enabled else 'OFF'}")

def toggle_basic_detection():
    global basic_detection_enabled
    basic_detection_enabled = not basic_detection_enabled
    logger.info(f"Basic detection toggled to {'ON' if basic_detection_enabled else 'OFF'}")

def toggle_color_filter():
    global color_filter_enabled
    color_filter_enabled = not color_filter_enabled
    logger.info(f"Color filter toggled to {'ON' if color_filter_enabled else 'OFF'}")

def toggle_color_legend():
    global show_color_legend
    show_color_legend = not show_color_legend
    logger.info(f"Color legend toggled to {'ON' if show_color_legend else 'OFF'}")

def cycle_color_space():
    global color_space, color_center
    order = ["HSV", "BGR", "LAB"]
    try:
        idx = order.index(color_space)
    except ValueError:
        idx = 0
    next_space = order[(idx + 1) % len(order)]
    color_finder.set_color_type(next_space)
    color_space = next_space
    a, b, c = color_center
    if color_space == "HSV":
        a = min(a, 179)
    color_center = (a, b, c)
    color_finder.set_center(color_center)
    logger.info(f"Color space set to {color_space} center={color_center}")

def cycle_color_channel():
    global color_channel_selected
    color_channel_selected = cycle_channel(color_channel_selected)
    logger.info(f"Channel selected: {color_channel_selected}")

def adjust_color_center(delta):
    global color_center
    color_center = apply_center_change(color_finder=color_finder,color_space=color_space,color_center=color_center,which=color_channel_selected,delta=delta)
    logger.info(f"Color center now: {color_center} selected={color_channel_selected}")

def bump_tolerance(step=1):
    global color_tol
    color_tol = bump_color_tolerance(color_finder, color_tol, tol_step=step)
    logger.info(f"Tolerance now: {color_tol}")

def execute_command(command):
    normalized = (command or "").strip().lower()
    command_map = {
        "left": move_left,
        "right": move_right,
        "up": move_up,
        "down": move_down,
        "w": move_up,
        "a": move_left,
        "s": move_down,
        "d": move_right,
        "r": reset_servos,
        "1": toggle_stream,
        "2": toggle_tracking,
        "3": toggle_manual_control,
        "4": toggle_debug,
        "5": toggle_lock_object,
        "6": toggle_basic_detection,
        "7": toggle_color_filter,
        "8": toggle_color_legend,
        "9": cycle_color_space,
        "y": cycle_color_channel,
        "i": lambda: adjust_color_center(2),
        "u": lambda: adjust_color_center(-2),
        "t": bump_tolerance,
        "toggle_stream": toggle_stream,
        "toggle_tracking": toggle_tracking,
        "toggle_manual": toggle_manual_control,
        "toggle_debug": toggle_debug,
        "toggle_lock": toggle_lock_object,
        "toggle_basic_detection": toggle_basic_detection,
        "toggle_color_filter": toggle_color_filter,
        "toggle_color_legend": toggle_color_legend,
        "cycle_color_space": cycle_color_space,
        "cycle_color_channel": cycle_color_channel,
        "color_center_up": lambda: adjust_color_center(2),
        "color_center_down": lambda: adjust_color_center(-2),
        "tolerance_up": bump_tolerance,
        "reset": reset_servos,
        "snap": take_still,
        "reboot": reboot_device
    }
    action = command_map.get(normalized)
    if action is None:
        logger.warning(f"Unknown command received: {command}")
        return
    action()

def attempt_restart_wifi(retries):
    for attempt in range(1, retries + 1):
        logger.info(f"Attempt {attempt} to restart WiFi...")
        try:
            restart_wifi_event()
            logger.info("WiFi restarted successfully")
            return
        except Exception as e:
            logger.error(f"Failed to restart WiFi on attempt {attempt}: {e}")
            if attempt < retries:
                logger.info("Retrying WiFi restart...")
                time.sleep(5)
            else:
                logger.critical("All attempts to restart WiFi have failed.")

def restart_wifi_event():
    logger.info("restart_wifi_event...")
    try:
        result = subprocess.run(['/usr/bin/sudo', 'ifconfig', 'wlan0', 'down'], capture_output=True, text=True)
        time.sleep(10)
        result = subprocess.run(['/usr/bin/sudo', 'ifconfig', 'wlan0', 'up'], capture_output=True, text=True)
        time.sleep(5)
    except Exception as e:
        logger.error(f"Failed to restart WiFi: {e}", exc_info=True)

def poll_event():
    global last_command_id, last_transient_seq, viewer_active, poll_failures
    try:
        response = poll_session.get(POLL_EVENT_URL,params={"since": last_transient_seq, "_": str(int(time.time() * 1000))},timeout=(3, 5))
        if response.status_code >= 500:
            logger.error(f"poll_event server error: status={response.status_code}, body={response.text[:500]}")
            poll_failures = min(poll_failures + 1, 6)
            time.sleep(min(30, 2 ** poll_failures))
            return
        response.raise_for_status()
        data = response.json()
        poll_failures = 0
        viewer_active = bool(data.get("viewer_active", False))
        command_id = int(data.get("command_id", 0))
        command = data.get("command", "none")
        if command_id > last_command_id:
            last_command_id = command_id
            if command != "none":
                execute_command(command)

        entries = data.get("transient_entries", []) or []
        now = time.time()
        for entry in entries:
            seq = int(entry.get("seq", 0))
            if seq <= last_transient_seq:
                continue
            last_transient_seq = seq
            ts = int(entry.get("ts", 0))
            if ts and now - ts > 5:
                continue
            cmd = entry.get("cmd", "")
            if cmd:
                execute_command(cmd)
    except requests.exceptions.JSONDecodeError as ex:
        logger.error(f"poll_event invalid json: {ex}")
        poll_failures = min(poll_failures + 1, 6)
        time.sleep(min(30, 2 ** poll_failures))
    except requests.exceptions.HTTPError as ex:
        response = ex.response
        body = response.text[:500] if response is not None else ""
        status = response.status_code if response is not None else "unknown"
        logger.error(f"poll_event http error: status={status}, body={body}")
        poll_failures = min(poll_failures + 1, 6)
        time.sleep(min(30, 2 ** poll_failures))
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as ex:
        logger.warning(f"poll_event network error: {ex}")
        reset_poll_session()
        poll_failures = min(poll_failures + 1, 6)
        time.sleep(min(30, 2 ** poll_failures))
    except Exception as ex:
        logger.error(f"poll_event unexpected error: {ex}", exc_info=True)
        poll_failures = min(poll_failures + 1, 6)
        time.sleep(min(30, 2 ** poll_failures))

def upload_frame_event(jpeg_bytes, frame_id, enabled, pan, tilt):
    try:
        response = upload_session.post(
            url=UPLOAD_URL,
            params={"frame_id": frame_id,"enabled": "1" if enabled else "0","pan": pan ,"tilt": tilt},
            data=jpeg_bytes,
            headers={"Content-Type": "image/jpeg"},
            timeout=(3, 10)
        )
        response.raise_for_status()
        return True
    except Exception as ex:
        logger.error(f"upload_frame_request error: {ex}")
        time.sleep(5)
        return False

def upload_timeline24_event(jpeg_bytes):
    try:
        response = upload_session.post(
            url=UPLOAD_TIMELINE24_URL,
            data=jpeg_bytes,
            headers={"Content-Type": "image/jpeg"},
            timeout=(3, 10),
        )
        if response.status_code == 429:
            try:
                retry_after = int((response.json() or {}).get("retry_after", 60))
            except Exception:
                retry_after = 60
            logger.info(f"timeline24 rate limited, retry_after={retry_after}s")
            return max(retry_after, 60)
        if response.status_code == 403:
            logger.info(f"timeline24 disabled by server: {response.text[:200]}")
            return seconds_to_next_hour() + 30
        response.raise_for_status()
        logger.info(f"timeline24 uploaded: {response.text[:200]}")
        return seconds_to_next_hour() + 30
    except Exception as ex:
        logger.error(f"upload_timeline24 error: {ex}")
        return 120

def timeline_upload_process():
    logger.info("Starting timeline_upload_process")
    wait = 30
    while not shutdown_event.wait(wait):
        if not stream_enabled:
            wait = 60
            continue
        with frame_lock:
            jpeg_bytes = latest_jpeg
        if jpeg_bytes is None:
            wait = 60
            continue
        wait = max(60, upload_timeline24_event(jpeg_bytes))
    logger.info("timeline_upload_process exiting")

def take_still():
    logger.info("take_still requested")
    if not viewer_active:
        logger.warning("take_still: no active viewer, skipping")
        return
    with frame_lock:
        jpeg_bytes = latest_jpeg
    if jpeg_bytes is None:
        logger.warning("take_still: no frame available yet")
        return
    try:
        response = upload_session.post(url=UPLOAD_PICTURE_URL,data=jpeg_bytes,headers={"Content-Type": "image/jpeg"},timeout=(3, 10))
        response.raise_for_status()
        logger.info(f"take_still stored: {response.text}")
    except Exception as ex:
        logger.error(f"take_still error: {ex}")

def poll_command_process():
    logger.info("Starting poll_command_process")
    try:
        last_poll_time = 0.0
        poll_interval = 1.0
        while True:
            now = time.time()
            if now - last_poll_time >= poll_interval:
                poll_event()
                last_poll_time = now
            time.sleep(0.1)
    except Exception as e:
        logger.error(f"Error in poll_command_process loop: {e}", exc_info=True)

def frame_capture_process():
    global latest_jpeg, latest_frame_id
    logger.info("Starting frame_capture_process")
    encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), 80]
    target_fps = 12
    frame_interval = 1.0 / target_fps
    try:
        while True:
            started = time.time()
            frame = picam2.capture_array()
            if stream_enabled:

                if show_color_legend:
                    vals = mask_values_from_center(color_center, color_tol, color_space)
                    legend = legend_block(color_space, vals, center=color_center, tol=(color_tol, color_tol, color_tol))
                    frame = overlay_legend_on_frame(frame, legend, anchor="bl")

                ok, encoded = cv2.imencode(".jpg", frame, encode_params)
                if ok:
                    jpeg_bytes = encoded.tobytes()
                    with frame_lock:
                        latest_frame_id += 1
                        latest_jpeg = jpeg_bytes
            elapsed = time.time() - started
            remaining = frame_interval - elapsed
            if remaining > 0:
                time.sleep(remaining)
    except Exception as e:
        logger.error(f"Error in frame_capture_process loop: {e}", exc_info=True)

def frame_upload_process():
    logger.info("Starting frame_upload_process")
    last_uploaded_frame_id = 0
    try:
        while True:
            if not stream_enabled or not viewer_active:
                time.sleep(1)
                continue
            with frame_lock:
                current_frame_id = latest_frame_id
                jpeg_bytes = latest_jpeg
                pan = PAN_ANGLE
                tilt = TILT_ANGLE
                enabled = stream_enabled
            if jpeg_bytes is None or current_frame_id == last_uploaded_frame_id:
                time.sleep(0.01)
                continue
            ok = upload_frame_event(jpeg_bytes=jpeg_bytes,frame_id=current_frame_id,enabled=enabled,pan=pan,tilt=tilt)
            if ok:
                last_uploaded_frame_id = current_frame_id
            else:
                time.sleep(0.25)
    except Exception as e:
        logger.error(f"Error in frame_upload_process loop: {e}", exc_info=True)

def connectivity_check_process():
    logger.info("Starting connectivity_check_process")
    max_retries = 3
    while True:
        try:
            response = requests.get("https://www.google.com", timeout=10)
            if response.status_code == 200:
                logger.debug("Internet connectivity is fine")
        except requests.exceptions.RequestException as e:
            logger.warning(f"No internet connectivity detected: {e}")
            attempt_restart_wifi(max_retries)
        except Exception as e:
            logger.error(f"Unexpected error in connectivity check: {e}", exc_info=True)
            attempt_restart_wifi(max_retries)
        time.sleep(60)

def monitor_threads(threads):
    while True:
        for thread_name, thread in threads.items():
            if not thread.is_alive():
                logger.critical(f"Thread {thread_name} has stopped unexpectedly. Restarting...")
                threads[thread_name] = start_thread(thread._target, thread_name)
        time.sleep(60)

def start_thread(target_function, thread_name):
    try:
        thread = threading.Thread(target=target_function, daemon=True, name=thread_name)
        thread.start()
        return thread
    except Exception as e:
        logger.critical(f"Failed to start thread {thread_name}: {e}", exc_info=True)
        return None

def main():
    global upload_session, poll_session
    logger.info("Starting main")
    upload_session = build_session()
    poll_session = build_session()
    if rasp_servokit is not None:
        reset_servos()
    threads = {
        "frame_upload_process": start_thread(frame_upload_process, "FrameUpload"),
        "frame_capture_process": start_thread(frame_capture_process, "FrameCapture"),
        "poll_command_process": start_thread(poll_command_process, "PollCommand"),
        "connectivity_check_process": start_thread(connectivity_check_process, "ConnectivityCheck"),
        "timeline_upload_process": start_thread(timeline_upload_process, "TimelineUpload")
    }
    threading.Thread(target=monitor_threads, args=(threads,), daemon=True).start()
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received, shutting down.")
    finally:
        picam2.stop()
        logger.info("Application exiting...\n.....................................................................")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        application_error_handler(e)
