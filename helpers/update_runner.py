"""Device self-update runner (v1.1.0+).

Triggered by the `update` command. The server hands the device the payload URL
to clone from (keeps devices redirectable if the repo ever moves). Clones the
latest version into a sibling dir, installs it as its own systemd unit
(enabled, not started), marks this old version for delayed startup, reboots.
On any failure the device stays on the current version. See version_manager
for the post-reboot handoff.
"""
import os
import shutil
import subprocess
import time

from helpers.main_logger import logger
from helpers import version_manager

def handle_update_command(payload_url):
    try:
        _install_update(payload_url)
    except Exception as ex:
        logger.error("update_runner: update aborted -- %s", ex, exc_info=True)
        _cleanup_pending()

def _pending_dir():
    return os.path.join(version_manager.parent_dir(), "rasp_cam_pending")

def _cleanup_pending():
    pending = _pending_dir()
    if os.path.isdir(pending):
        try:
            shutil.rmtree(pending)
        except Exception:
            pass

def _install_update(payload_url):
    payload_url = (payload_url or "").strip()
    if not payload_url:
        logger.error("update_runner: server sent no payload_url -- aborting")
        return
    if version_manager.detect_device_mode() != "service":
        logger.warning("update_runner: not a service install -- auto-update skipped")
        return
    own_install_dir = version_manager.install_dir()
    parent = version_manager.parent_dir()
    own_version = version_manager.current_version()
    _cleanup_pending()
    pending = _pending_dir()
    logger.info("update_runner: cloning %s", payload_url)
    subprocess.run(["git", "clone", "--depth", "1", payload_url, pending],check=True, timeout=300)
    new_version = version_manager.read_version(pending)
    if new_version is None:
        logger.error("update_runner: cloned payload has no valid VERSION -- aborting")
        _cleanup_pending()
        return
    if new_version == own_version:
        logger.info("update_runner: already on %s -- nothing to do", own_version)
        _cleanup_pending()
        return
    if version_manager.version_tuple(new_version) < version_manager.version_tuple(own_version):
        logger.warning("update_runner: payload %s older than current %s -- aborting",new_version, own_version)
        _cleanup_pending()
        return
    target = os.path.join(parent, "rasp_cam_" + new_version)
    if os.path.exists(target):
        logger.info("update_runner: %s already staged -- skipping", target)
        _cleanup_pending()
        return
    os.rename(pending, target)
    env_src = os.path.join(own_install_dir, ".env")
    if os.path.isfile(env_src):
        shutil.copy2(env_src, os.path.join(target, ".env"))
    else:
        logger.warning("update_runner: no .env to carry over -- new version may ""be missing its device key")
    for script in ("install.sh", "run.sh", "uninstall_service.sh","scripts/stop_existing.sh"):
        script_path = os.path.join(target, script)
        if os.path.isfile(script_path):
            os.chmod(script_path, 0o755)

    # --no-start: starting the new unit now would fight the running version for
    # the camera. The reboot starts it cleanly.
    device_key = os.getenv("RASP_DEVICE_KEY", "")
    logger.info("update_runner: installing %s as a service", new_version)
    subprocess.run(["bash", os.path.join(target, "install.sh"),device_key, "--service", "--no-start"],cwd=target, check=True, timeout=600)
    marker = os.path.join(own_install_dir, version_manager.DELAY_STARTUP_MARKER)
    try:
        with open(marker, "w") as f:
            f.write(str(int(time.time())))
    except Exception as ex:
        logger.error("update_runner: could not write delay marker: %s", ex)
    logger.info("update_runner: update staged (%s -> %s). Rebooting now.",own_version, new_version)
    subprocess.Popen(["sudo", "/sbin/reboot"], start_new_session=True)
    os._exit(0)
