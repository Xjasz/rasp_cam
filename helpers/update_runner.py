"""Device self-update command handler.

v1.0.1 — stub.

This file exists to make the `update` command in cam_main.py's `command_map`
land here when the server queues an update event. The real install logic
(clone, install.sh, reboot) ships in v1.1.0.

v1.0.1 devices that receive an `update` command from poll_event will log a
warning here and return. The server-side `update_started_at` lock will then
auto-clear after RASP_UPDATE_TIMEOUT_SECONDS (5 min) so controls unlock.

When v1.1.0 ships, this file gets replaced with the real implementation:
  - confirm device_mode == "service"
  - clone RASP_PAYLOAD_URL → rasp_cam_pending
  - read pending/VERSION → target_version
  - rename to rasp_cam_<target_version>
  - copy .env over
  - run install.sh --service synchronously
  - write .delay_startup marker in own dir
  - sudo reboot, os._exit(0)

See `.docs/plans/device-self-update.md` in the codalata repo for full spec.
"""
from helpers.main_logger import logger


def handle_update_command():
    """Called from cam_main.py's command_map when an `update` event arrives."""
    logger.warning(
        "update command received but update logic ships in v1.1.0; "
        "please reinstall this device manually for now (git pull + restart service)."
    )
