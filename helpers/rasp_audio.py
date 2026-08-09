import re
import subprocess
import threading

from helpers.main_logger import logger

CLIP_PATH = "/tmp/rasp_cam_clip.wav"


def detect_speaker_card():
    # Prefer a USB card; bcm2835/vc4/hdmi are the Pi's built-in outputs.
    try:
        result = subprocess.run(["aplay", "-l"], capture_output=True, text=True, timeout=10)
    except Exception as ex:
        logger.error("detect_speaker_card: aplay -l failed: %s", ex)
        return None
    if result.returncode != 0:
        logger.error("detect_speaker_card: aplay -l rc=%s stderr=%s", result.returncode, result.stderr.strip()[:200])
        return None
    for line in result.stdout.splitlines():
        match = re.match(r"card (\d+): \S+ \[([^\]]+)\]", line)
        if not match:
            continue
        card = int(match.group(1))
        name = match.group(2).lower()
        if "bcm2835" in name or "vc4" in name or "hdmi" in name:
            continue
        logger.info("detect_speaker_card: using card %s (%s)", card, match.group(2))
        return card
    logger.info("detect_speaker_card: no USB playback device found")
    return None


class AudioPlayer(object):
    def __init__(self, session, base_url, card):
        self.session = session
        self.clip_url = base_url + "/audio_clip"
        self.card = card
        self.lock = threading.Lock()
        self.proc = None

    def play_token(self, token):
        if not re.match(r"^[0-9a-f]{16}$", token or ""):
            logger.warning("play_token: invalid token %r", token)
            return
        threading.Thread(target=self._fetch_and_play, args=(token,), daemon=True, name="AudioPlay").start()

    def _fetch_and_play(self, token):
        try:
            response = self.session.get(self.clip_url, params={"token": token}, timeout=(3, 8))
            response.raise_for_status()
        except Exception as ex:
            logger.error("audio clip fetch failed token=%s: %s", token, ex)
            return
        with self.lock:
            self._kill_locked()
            # Write only after killing the old aplay - it reads this same file.
            try:
                with open(CLIP_PATH, "wb") as f:
                    f.write(response.content)
            except Exception as ex:
                logger.error("audio clip write failed: %s", ex)
                return
            cmd = ["aplay", "-q", "-D", "plughw:%d,0" % self.card, CLIP_PATH]
            try:
                proc = subprocess.Popen(cmd, stderr=subprocess.PIPE)
            except Exception as ex:
                logger.error("aplay spawn failed: %s", ex)
                return
            self.proc = proc
        threading.Thread(target=self._reap, args=(proc,), daemon=True, name="AudioReap").start()

    def _reap(self, proc):
        # Surface ALSA failures loudly - EPERM on /dev/snd means the service user lacks the audio group.
        try:
            _, stderr = proc.communicate(timeout=30)
            if proc.returncode not in (0, None) and proc.returncode != -15:
                logger.error("aplay exited rc=%s stderr=%s", proc.returncode, (stderr or b"").decode(errors="replace").strip()[:300])
        except Exception as ex:
            logger.error("aplay reap failed: %s", ex)

    def stop(self):
        with self.lock:
            self._kill_locked()

    def _kill_locked(self):
        if self.proc is not None and self.proc.poll() is None:
            try:
                self.proc.terminate()
            except Exception as ex:
                logger.error("aplay terminate failed: %s", ex)
        self.proc = None
