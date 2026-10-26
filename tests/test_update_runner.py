import builtins
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from helpers import update_runner


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.current = self.root / 'rasp_cam'
        self.current.mkdir()
        self.key = 'fake-device-key-for-tests'
        (self.current / '.env').write_text('RASP_DEVICE_KEY=' + self.key + '\n')
        self.target = self.root / 'rasp_cam_1.4.3'
        self.pending = self.root / 'rasp_cam_pending'
        self.unit = 'codalata-rasp-cam-1.4.3'
        self.payload_version = '1.4.3'
        for name, value in [('parent_dir', str(self.root)), ('install_dir', str(self.current)),
                            ('current_version', '1.4.2'), ('detect_device_mode', 'service')]:
            self.start_patch(update_runner.version_manager, name, return_value=value)
        self.run = self.start_patch(update_runner.subprocess, 'run', side_effect=self.run_command)
        self.installer = self.start_patch(update_runner, '_run_installer', return_value=subprocess.CompletedProcess([], 0, '', ''))
        self.reboot = self.start_patch(update_runner.subprocess, 'Popen')
        self.exit = self.start_patch(update_runner.os, '_exit')

    def start_patch(self, obj, name, **kwargs):
        p = patch.object(obj, name, **kwargs)
        self.addCleanup(p.stop)
        return p.start()

    def run_command(self, command, **kwargs):
        if command[0] == 'git':
            self.pending.mkdir()
            (self.pending / 'VERSION').write_text(self.payload_version)
            (self.pending / 'install.sh').write_text('exit 0\n')
        return subprocess.CompletedProcess(command, 0, '', '')

    def update(self):
        update_runner.handle_update_command('https://github.com/Xjasz/rasp_cam.git')

    def assert_preserved(self):
        self.assertEqual((self.current / '.env').read_text(), 'RASP_DEVICE_KEY=' + self.key + '\n')
        self.assertFalse((self.current / '.delay_startup').exists())
        self.reboot.assert_not_called()
        self.exit.assert_not_called()

    def test_success_reuses_private_env_and_reboots(self):
        self.update()
        self.assertEqual((self.target / '.env').read_text(), (self.current / '.env').read_text())
        self.assertEqual((self.target / '.env').stat().st_mode & 0o777, 0o600)
        self.installer.assert_called_once_with(str(self.target))
        self.assertTrue((self.current / '.delay_startup').is_file())
        self.run.assert_any_call(['sudo', '-n', '/sbin/reboot'], capture_output=True,
                                 text=True, timeout=15, check=True)
        self.reboot.assert_not_called()
        self.exit.assert_not_called()

    def test_nonzero_exit_cleans_and_allows_retry(self):
        self.installer.return_value = subprocess.CompletedProcess([], 1, '', 'failed')
        self.update()
        self.assertFalse(self.target.exists())
        self.assert_preserved()
        self.installer.return_value = subprocess.CompletedProcess([], 0, '', '')
        self.update()
        self.assertEqual(self.installer.call_count, 2)
        self.exit.assert_not_called()

    def test_timeout_cleans_and_does_not_log_key(self):
        self.installer.side_effect = subprocess.TimeoutExpired(['bash', 'install.sh', '--service', '--no-start'], 600)
        with self.assertLogs(update_runner.logger, level='ERROR') as captured:
            self.update()
        self.assertNotIn(self.key, '\n'.join(captured.output))
        self.assertFalse(self.target.exists())
        self.assert_preserved()
        self.installer.side_effect = None
        self.update()
        self.assertEqual(self.installer.call_count, 2)

    def test_cleanup_failure_does_not_skip_remaining_steps(self):
        for error in (subprocess.TimeoutExpired(['sudo', 'systemctl'], 30),
                      subprocess.CalledProcessError(1, ['sudo', 'systemctl'])):
            with self.subTest(error=type(error).__name__):
                self.run.reset_mock()
                def run(command, **kwargs):
                    if command[:3] == ['sudo', 'systemctl', 'disable']:
                        raise error
                    return self.run_command(command, **kwargs)
                self.run.side_effect = run
                self.installer.side_effect = RuntimeError('install failed')
                self.update()
                commands = [call.args[0] for call in self.run.call_args_list]
                self.assertIn(['sudo', 'rm', '-f', '/etc/systemd/system/' + self.unit + '.service'], commands)
                self.assertIn(['sudo', 'systemctl', 'daemon-reload'], commands)
                self.assertFalse(self.target.exists())
                self.assert_preserved()

    def test_missing_env_aborts_before_staging(self):
        (self.current / '.env').unlink()
        self.update()
        self.assertFalse(self.pending.exists())
        self.assertFalse(self.target.exists())
        self.installer.assert_not_called()
        self.reboot.assert_not_called()

    def test_copy_failure_removes_only_new_directory(self):
        self.start_patch(update_runner.shutil, 'copy2', side_effect=OSError('copy failed'))
        self.update()
        self.assertFalse(self.target.exists())
        self.assert_preserved()
        self.assertFalse(any(c.args[0][0] == 'sudo' for c in self.run.call_args_list))

    def test_existing_target_is_preserved(self):
        self.target.mkdir()
        (self.target / 'keep').write_text('existing installation')
        self.update()
        self.assertEqual((self.target / 'keep').read_text(), 'existing installation')
        self.installer.assert_not_called()
        self.assert_preserved()

    def test_existing_unit_is_preserved(self):
        real_lexists = os.path.lexists
        unit_path = '/etc/systemd/system/' + self.unit + '.service'
        self.start_patch(update_runner.os.path, 'lexists', side_effect=lambda p: p == unit_path or real_lexists(p))
        self.update()
        self.assertFalse(self.target.exists())
        self.installer.assert_not_called()
        self.assert_preserved()
        self.assertFalse(any(c.args[0][0] == 'sudo' for c in self.run.call_args_list))

    def test_same_older_and_invalid_versions_are_skipped(self):
        for version in ('1.4.2', '1.4.1', 'invalid'):
            with self.subTest(version=version):
                self.payload_version = version
                self.update()
                self.assertFalse(self.pending.exists())
                self.installer.assert_not_called()
                self.assert_preserved()

    def test_foreign_repo_is_rejected(self):
        update_runner.handle_update_command('https://github.com/other/rasp_cam.git')
        self.run.assert_not_called()
        self.assert_preserved()

    def test_marker_creation_failure_rolls_back_without_reboot(self):
        marker = self.current / '.delay_startup'
        real_open = builtins.open
        def open_file(path, *args, **kwargs):
            if str(path) == str(marker):
                raise OSError('disk full')
            return real_open(path, *args, **kwargs)
        with patch('builtins.open', side_effect=open_file):
            self.update()
        self.assertFalse(self.target.exists())
        self.assert_preserved()
        self.assertNotIn(['sudo', '-n', '/sbin/reboot'], [c.args[0] for c in self.run.call_args_list])

    def test_marker_flush_failure_removes_partial_marker(self):
        self.start_patch(update_runner.os, 'fsync', side_effect=OSError('disk full'))
        self.update()
        self.assertFalse(self.target.exists())
        self.assert_preserved()
        self.assertNotIn(['sudo', '-n', '/sbin/reboot'], [c.args[0] for c in self.run.call_args_list])

    def test_existing_marker_is_not_overwritten_or_deleted(self):
        marker = self.current / '.delay_startup'
        marker.write_text('existing handoff')
        self.update()
        self.assertEqual(marker.read_text(), 'existing handoff')
        self.assertFalse(self.target.exists())
        self.assertNotIn(['sudo', '-n', '/sbin/reboot'], [c.args[0] for c in self.run.call_args_list])
        self.exit.assert_not_called()

    def test_failed_reboot_rolls_back_and_can_retry(self):
        reboot_command = ['sudo', '-n', '/sbin/reboot']
        for error in (subprocess.CalledProcessError(1, reboot_command), OSError('spawn failed')):
            with self.subTest(error=type(error).__name__):
                def run(command, **kwargs):
                    if command == reboot_command:
                        raise error
                    return self.run_command(command, **kwargs)
                self.run.side_effect = run
                self.update()
                self.assertFalse(self.target.exists())
                self.assert_preserved()
        self.run.side_effect = self.run_command
        self.update()
        self.assertTrue(self.target.is_dir())
        self.assertTrue((self.current / '.delay_startup').is_file())
        self.exit.assert_not_called()

    def test_reboot_timeout_preserves_uncertain_handoff(self):
        reboot_command = ['sudo', '-n', '/sbin/reboot']
        def run(command, **kwargs):
            if command == reboot_command:
                raise subprocess.TimeoutExpired(command, 15)
            return self.run_command(command, **kwargs)
        self.run.side_effect = run
        with self.assertLogs(update_runner.logger, level='CRITICAL') as captured:
            self.update()
        self.assertTrue(self.target.is_dir())
        self.assertTrue((self.current / '.delay_startup').is_file())
        self.assertTrue(any('may already be queued' in message for message in captured.output))
        self.assertFalse(any(c.args[0][:3] == ['sudo', 'systemctl', 'disable'] for c in self.run.call_args_list))
        self.exit.assert_not_called()

    def test_unconfirmed_installer_shutdown_preserves_stage(self):
        self.installer.side_effect = update_runner.InstallerCleanupError('still running')
        with self.assertLogs(update_runner.logger, level='CRITICAL') as captured:
            self.update()
        self.assertTrue(self.target.is_dir())
        self.assertTrue(any('before retrying or rebooting' in message for message in captured.output))
        self.assert_preserved()
        self.assertFalse(any(c.args[0][0] == 'sudo' for c in self.run.call_args_list))


class InstallerTests(unittest.TestCase):
    def test_command_has_no_device_key_and_timeout_reaps_before_raising(self):
        command = ['bash', '/staging/install.sh', '--service', '--no-start']
        process = Mock(pid=12345)
        process.communicate.side_effect = [subprocess.TimeoutExpired(command, 600), ('', '')]
        with patch.object(update_runner.subprocess, 'Popen', return_value=process) as popen, \
             patch.object(update_runner.os, 'killpg') as kill, \
             patch.dict(os.environ, {'RASP_DEVICE_KEY': 'fake-secret'}):
            with self.assertRaises(subprocess.TimeoutExpired) as raised:
                update_runner._run_installer('/staging')
        self.assertEqual(popen.call_args.args[0], command)
        self.assertTrue(popen.call_args.kwargs['start_new_session'])
        kill.assert_called_once_with(12345, signal.SIGKILL)
        self.assertEqual(process.communicate.call_count, 2)
        self.assertEqual(process.communicate.call_args.kwargs, {"timeout": 10})
        self.assertNotIn('fake-secret', str(raised.exception))

    def test_unconfirmed_shutdown_closes_pipes_without_unbounded_wait(self):
        process = Mock(pid=12345)
        process.communicate.side_effect = subprocess.TimeoutExpired(['bash', 'install.sh'], 10)
        with patch.object(update_runner.subprocess, 'Popen', return_value=process), \
             patch.object(update_runner.os, 'killpg'):
            with self.assertRaises(update_runner.InstallerCleanupError):
                update_runner._run_installer('/staging')
        self.assertEqual([c.kwargs['timeout'] for c in process.communicate.call_args_list], [600, 10])
        process.stdout.close.assert_called_once_with()
        process.stderr.close.assert_called_once_with()
        process.poll.assert_called_once_with()

    @unittest.skipUnless(sys.platform.startswith('linux'), 'Linux process group check')
    def test_real_timeout_stops_installer_child(self):
        self.run_timeout_fixture(detach=False)

    @unittest.skipUnless(sys.platform.startswith('linux'), 'Linux process group check')
    def test_real_escaped_child_does_not_hang_cleanup(self):
        self.run_timeout_fixture(detach=True)

    def run_timeout_fixture(self, detach):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            child_pid_file = root / 'child.pid'
            child_code = 'import os, pathlib, time\n'
            if detach:
                child_code += 'os.setsid()\n'
            child_code += 'pathlib.Path("child.pid").write_text(str(os.getpid()))\ntime.sleep(60)\n'
            (root / 'child.py').write_text(child_code)
            import shlex
            (root / 'install.sh').write_text(shlex.quote(sys.executable) + ' child.py &\nwait\n')
            real_popen = subprocess.Popen
            processes = []
            def spawn(*args, **kwargs):
                process = real_popen(*args, **kwargs)
                processes.append(process)
                communicate = process.communicate
                def bounded(timeout=None):
                    if timeout is not None:
                        deadline = time.monotonic() + 5
                        while not child_pid_file.exists() and time.monotonic() < deadline:
                            time.sleep(0.01)
                        return communicate(timeout=0.1)
                    return communicate(timeout=5)
                process.communicate = bounded
                return process
            try:
                with patch.object(update_runner.subprocess, 'Popen', side_effect=spawn):
                    expected_error = update_runner.InstallerCleanupError if detach else subprocess.TimeoutExpired
                    with self.assertRaises(expected_error):
                        update_runner._run_installer(td)
                self.assertEqual(processes[0].returncode, -signal.SIGKILL)
                child_stat = Path('/proc') / child_pid_file.read_text() / 'stat'
                if child_stat.exists() and not detach:
                    self.assertIn(child_stat.read_text().split(') ', 1)[1].split()[0], ('Z', 'X'))
                if detach:
                    self.assertTrue(processes[0].stdout.closed)
                    self.assertTrue(processes[0].stderr.closed)
            finally:
                if child_pid_file.exists():
                    try:
                        os.kill(int(child_pid_file.read_text()), signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                for process in processes:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    process.wait(timeout=5)


if __name__ == '__main__':
    unittest.main()
