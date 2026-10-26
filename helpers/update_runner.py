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
import signal
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

def _run_installer(target):
    command = ["bash", os.path.join(target, "install.sh"), "--service", "--no-start"]
    process = subprocess.Popen(command, cwd=target, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True, start_new_session=True)
    try:
        stdout, stderr = process.communicate(timeout=600)
    except BaseException:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.communicate()
        raise
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)

def _cleanup_failed_install(target, new_unit=None):
    if new_unit is not None:
        commands = [
            ["sudo", "systemctl", "disable", new_unit],
            ["sudo", "rm", "-f", "/etc/systemd/system/%s.service" % new_unit],
            ["sudo", "systemctl", "daemon-reload"],
        ]
        for command in commands:
            try:
                subprocess.run(command, capture_output=True, timeout=30, check=True)
            except Exception as ex:
                logger.error("update_runner: cleanup command failed: %s", ex)
    try:
        shutil.rmtree(target)
    except Exception as ex:
        logger.error("update_runner: could not remove failed install %s: %s", target, ex)

def _install_update(payload_url):
    payload_url = (payload_url or "").strip()
    if not payload_url:
        logger.error("update_runner: server sent no payload_url -- aborting")
        return
    if payload_url.lower().rstrip("/") not in ("https://github.com/xjasz/rasp_cam", "https://github.com/xjasz/rasp_cam.git"):
        logger.error("update_runner: payload_url is not the Xjasz/rasp_cam GitHub repo -- aborting: %s", payload_url)
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
    new_unit = version_manager.unit_name(new_version)
    unit_path = "/etc/systemd/system/%s.service" % new_unit
    if os.path.lexists(target) or os.path.lexists(unit_path):
        logger.info("update_runner: %s already staged -- skipping", target)
        _cleanup_pending()
        return
    env_src = os.path.join(own_install_dir, ".env")
    if not os.path.isfile(env_src):
        raise RuntimeError("current install has no .env to carry over")
    os.rename(pending, target)
    installer_started = False
    try:
        shutil.copy2(env_src, os.path.join(target, ".env"))
        os.chmod(os.path.join(target, ".env"), 0o600)
        for script in ("install.sh", "run.sh", "uninstall_service.sh","scripts/stop_existing.sh"):
            script_path = os.path.join(target, script)
            if os.path.isfile(script_path):
                os.chmod(script_path, 0o755)
        logger.info("update_runner: installing %s as a service", new_version)
        installer_started = True
        result = _run_installer(target)
        if result.stdout and result.stdout.strip():
            logger.info("update_runner: install.sh output:\n%s", result.stdout.strip())
        if result.returncode != 0:
            logger.error("update_runner: install.sh FAILED (exit %s):\n%s", result.returncode, (result.stderr or "").strip())
            raise RuntimeError("install.sh exited %s" % result.returncode)
    except Exception:
        _cleanup_failed_install(target, new_unit if installer_started else None)
        raise
    marker = os.path.join(own_install_dir, version_manager.DELAY_STARTUP_MARKER)
    try:
        with open(marker, "w") as f:
            f.write(str(int(time.time())))
    except Exception as ex:
        logger.error("update_runner: could not write delay marker: %s", ex)
    logger.info("update_runner: update staged (%s -> %s). Rebooting now.",own_version, new_version)
    subprocess.Popen(["sudo", "/sbin/reboot"], start_new_session=True)
    os._exit(0)
