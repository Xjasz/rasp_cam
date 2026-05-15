"""Device self-update version manager (v1.1.0+).

Multi-version coexistence model: each version lives in its own sibling dir
(rasp_cam, rasp_cam_1.2.0, ...) with its own venv, .env, and systemd unit
codalata-rasp-cam-<version>. The dir's VERSION file is the source of truth.

Reboot handoff: update_runner installs the new version's unit (enabled, not
started), drops a .delay_startup marker in the OLD dir, reboots. On boot
cam_main.py calls startup_decision() BEFORE camera init -- the new version
runs; the old version waits, then steps aside if the new one is healthy or
takes over (fallback) if it is not.
"""
import os
import re
import subprocess
import time

from helpers.main_logger import logger

SERVICE_PREFIX = "codalata-rasp-cam"
PAYLOAD_DIR_RE = re.compile(r"^rasp_cam(?:_(\d+\.\d+\.\d+))?$")
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
DELAY_STARTUP_MARKER = ".delay_startup"
STARTUP_DELAY_SECONDS = 60
HEALTH_MAX_RESTARTS = 2

def install_dir():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def parent_dir():
    return os.path.dirname(install_dir())

def read_version(directory):
    try:
        with open(os.path.join(directory, "VERSION"), "r") as f:
            value = f.read().strip()
        return value if SEMVER_RE.match(value) else None
    except Exception:
        return None

def current_version():
    return read_version(install_dir()) or "0.0.0"

def version_tuple(version):
    return tuple(int(part) for part in version.split("."))

def unit_name(version):
    return SERVICE_PREFIX + "-" + version

def detect_device_mode():
    for unit in (unit_name(current_version()), SERVICE_PREFIX):
        try:
            result = subprocess.run(["systemctl", "is-enabled", unit],capture_output=True, text=True, timeout=3)
            if result.returncode == 0 and result.stdout.strip().startswith("enabled"):
                return "service"
        except Exception:
            pass
    return "manual"


def scan_siblings():
    me = install_dir()
    parent = parent_dir()
    found = []
    try:
        entries = os.listdir(parent)
    except Exception:
        return found
    for name in entries:
        directory = os.path.join(parent, name)
        if directory == me or not os.path.isdir(directory):
            continue
        if not PAYLOAD_DIR_RE.match(name):
            continue
        version = read_version(directory)
        if version is None:
            continue
        found.append({"dir": directory,"version": version,"vtuple": version_tuple(version),"unit": unit_name(version)})
    return found


def is_unit_healthy(unit):
    try:
        result = subprocess.run(["systemctl", "show", unit,"--property=ActiveState", "--property=NRestarts"],capture_output=True, text=True, timeout=5)
    except Exception:
        return False
    if result.returncode != 0:
        return False
    state = ""
    restarts = 0
    for line in result.stdout.splitlines():
        if line.startswith("ActiveState="):
            state = line.split("=", 1)[1].strip()
        elif line.startswith("NRestarts="):
            try:
                restarts = int(line.split("=", 1)[1].strip())
            except ValueError:
                restarts = 0
    return state == "active" and restarts <= HEALTH_MAX_RESTARTS

def uninstall_sibling(sibling):
    script = os.path.join(sibling["dir"], "uninstall_service.sh")
    if not os.path.isfile(script):
        logger.warning("version_manager: no uninstall script in %s", sibling["dir"])
        return
    try:
        subprocess.run(["bash", script, sibling["unit"]], timeout=60)
        logger.info("version_manager: uninstalled sibling %s (%s)",
                    sibling["version"], sibling["dir"])
    except Exception as ex:
        logger.error("version_manager: uninstall of %s failed: %s",
                     sibling["dir"], ex)

def startup_decision():
    """Returns "run" or "exit_silently". Called before camera init."""
    marker = os.path.join(install_dir(), DELAY_STARTUP_MARKER)
    if not os.path.isfile(marker):
        return "run"
    logger.info("version_manager: .delay_startup present -- waiting %ds for the newer version to come up", STARTUP_DELAY_SECONDS)
    time.sleep(STARTUP_DELAY_SECONDS)
    mine = version_tuple(current_version())
    newer = [s for s in scan_siblings() if s["vtuple"] > mine]
    healthy = [s for s in newer if is_unit_healthy(s["unit"])]
    if healthy:
        logger.info("version_manager: newer version healthy (%s) -- stepping aside",
                    ", ".join(s["version"] for s in healthy))
        return "exit_silently"
    logger.warning("version_manager: no healthy newer version -- taking over (fallback). Removing %d failed newer install(s).", len(newer))
    for sibling in newer:
        uninstall_sibling(sibling)
    try:
        os.remove(marker)
    except Exception:
        pass
    return "run"


def cleanup_older_siblings():
    mine = version_tuple(current_version())
    older = [s for s in scan_siblings() if s["vtuple"] < mine]
    if not older:
        return
    logger.info("version_manager: retiring %d older sibling install(s)", len(older))
    for sibling in older:
        uninstall_sibling(sibling)
