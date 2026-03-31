"""
Daemon manager lifecycle tests.

Tests subprocess spawning, configuration, startup/shutdown, and error handling.
"""

import os
import sys
import unittest
import tempfile
from unittest.mock import MagicMock, patch, call
import subprocess

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "swap-service"))


class TestDaemonManagerInitialization(unittest.TestCase):
    """Test DaemonManager initialization and configuration."""

    def setUp(self):
        """Set up test fixtures."""
        from daemon_manager import DaemonManager
        self.DaemonManager = DaemonManager
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)

    def test_daemon_manager_initialization(self):
        """DaemonManager should initialize with credentials and paths."""
        dm = self.DaemonManager(
            coind_path="/path/to/coind",
            goldd_path="/path/to/goldd",
            oxc_rpc_user="user1",
            oxc_rpc_password="pass1",
            oxg_rpc_user="user2",
            oxg_rpc_password="pass2",
            coind_datadir="/data/coind",
            goldd_datadir="/data/goldd",
        )
        self.assertEqual(dm.coind_path, "/path/to/coind")
        self.assertEqual(dm.goldd_path, "/path/to/goldd")
        self.assertEqual(dm.oxc_rpc_user, "user1")
        self.assertEqual(dm.oxg_rpc_user, "user2")
        self.assertIsNone(dm.coind_proc)
        self.assertIsNone(dm.goldd_proc)

    def test_daemon_manager_without_datadirs(self):
        """DaemonManager should work without explicit datadirs."""
        dm = self.DaemonManager(
            coind_path="/path/to/coind",
            goldd_path="/path/to/goldd",
            oxc_rpc_user="user1",
            oxc_rpc_password="pass1",
            oxg_rpc_user="user2",
            oxg_rpc_password="pass2",
        )
        self.assertIsNone(dm.coind_datadir)
        self.assertIsNone(dm.goldd_datadir)

    def test_write_conf_creates_config_file(self):
        """_write_conf should create configuration file with correct content."""
        dm = self.DaemonManager(
            coind_path="/path/to/coind",
            goldd_path="/path/to/goldd",
            oxc_rpc_user="testuser",
            oxc_rpc_password="testpass",
            oxg_rpc_user="user2",
            oxg_rpc_password="pass2",
        )

        conf_path = dm._write_conf(
            self.tmpdir.name,
            "testcoin",
            25174,
            25173,
            "testuser",
            "testpass",
        )

        self.assertTrue(os.path.exists(conf_path))
        self.assertEqual(conf_path, os.path.join(self.tmpdir.name, "testcoin.conf"))

        with open(conf_path, "r") as f:
            content = f.read()
        self.assertIn("server=1", content)
        self.assertIn("daemon=1", content)
        self.assertIn("rpcuser=testuser", content)
        self.assertIn("rpcpassword=testpass", content)
        self.assertIn("port=25174", content)
        self.assertIn("rpcport=25173", content)

    def test_build_args_generates_correct_command(self):
        """_build_args should generate correct daemon command arguments."""
        dm = self.DaemonManager(
            coind_path="/path/to/coind",
            goldd_path="/path/to/goldd",
            oxc_rpc_user="user1",
            oxc_rpc_password="pass1",
            oxg_rpc_user="user2",
            oxg_rpc_password="pass2",
        )

        args = dm._build_args(
            "/path/to/daemon",
            25174,
            25173,
            "/path/to/conf",
            "testuser",
            "testpass",
            "/data/dir",
        )

        self.assertEqual(args[0], "/path/to/daemon")
        self.assertIn("-daemon", args)
        self.assertIn("-server=1", args)
        self.assertIn("-bind=127.0.0.1", args)
        self.assertIn("-rpcuser=testuser", args)
        self.assertIn("-rpcpassword=testpass", args)
        self.assertIn("-port=25174", args)
        self.assertIn("-rpcport=25173", args)
        self.assertIn("-conf=/path/to/conf", args)
        self.assertIn("-datadir=/data/dir", args)

    def test_build_args_without_datadir(self):
        """_build_args should work without datadir parameter."""
        dm = self.DaemonManager(
            coind_path="/path/to/coind",
            goldd_path="/path/to/goldd",
            oxc_rpc_user="user1",
            oxc_rpc_password="pass1",
            oxg_rpc_user="user2",
            oxg_rpc_password="pass2",
        )

        args = dm._build_args(
            "/path/to/daemon",
            25174,
            25173,
            "/path/to/conf",
            "testuser",
            "testpass",
        )

        self.assertEqual(args[0], "/path/to/daemon")
        # Should not contain datadir
        datadir_args = [a for a in args if a.startswith("-datadir")]
        self.assertEqual(len(datadir_args), 0)


class TestDaemonManagerLifecycle(unittest.TestCase):
    """Test daemon startup, shutdown, and status monitoring."""

    def setUp(self):
        """Set up test fixtures."""
        from daemon_manager import DaemonManager
        self.DaemonManager = DaemonManager
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)

    @patch("daemon_manager.subprocess.Popen")
    @patch("daemon_manager.os.path.exists")
    @patch("daemon_manager.time.sleep")
    def test_start_daemons_success(self, mock_sleep, mock_exists, mock_popen):
        """start_daemons should spawn both daemon processes."""
        mock_exists.return_value = True
        mock_proc = MagicMock()
        mock_proc.pid = 1234
        mock_popen.return_value = mock_proc

        dm = self.DaemonManager(
            coind_path="/path/to/coind",
            goldd_path="/path/to/goldd",
            oxc_rpc_user="user1",
            oxc_rpc_password="pass1",
            oxg_rpc_user="user2",
            oxg_rpc_password="pass2",
            coind_datadir=self.tmpdir.name,
            goldd_datadir=self.tmpdir.name,
        )

        dm.start_daemons()

        # Should have called Popen twice (once for each daemon)
        self.assertEqual(mock_popen.call_count, 2)
        # Sleep should be called once (3 second wait)
        self.assertEqual(mock_sleep.call_count, 1)
        mock_sleep.assert_called_with(3)
        # Processes should be assigned
        self.assertIsNotNone(dm.coind_proc)
        self.assertIsNotNone(dm.goldd_proc)

    @patch("daemon_manager.os.path.exists")
    def test_start_daemons_missing_coind(self, mock_exists):
        """start_daemons should handle missing ordexcoind gracefully."""
        mock_exists.side_effect = [False, True]  # coind missing, goldd exists

        dm = self.DaemonManager(
            coind_path="/path/to/coind",
            goldd_path="/path/to/goldd",
            oxc_rpc_user="user1",
            oxc_rpc_password="pass1",
            oxg_rpc_user="user2",
            oxg_rpc_password="pass2",
        )

        with patch("daemon_manager.subprocess.Popen") as mock_popen:
            dm.start_daemons()
            # Should not spawn any processes
            mock_popen.assert_not_called()
            # Procs should remain None
            self.assertIsNone(dm.coind_proc)
            self.assertIsNone(dm.goldd_proc)

    @patch("daemon_manager.os.path.exists")
    def test_start_daemons_missing_goldd(self, mock_exists):
        """start_daemons should handle missing ordexgoldd gracefully."""
        mock_exists.side_effect = [True, False]  # coind exists, goldd missing

        dm = self.DaemonManager(
            coind_path="/path/to/coind",
            goldd_path="/path/to/goldd",
            oxc_rpc_user="user1",
            oxc_rpc_password="pass1",
            oxg_rpc_user="user2",
            oxg_rpc_password="pass2",
        )

        with patch("daemon_manager.subprocess.Popen") as mock_popen:
            dm.start_daemons()
            # Should not spawn any processes
            mock_popen.assert_not_called()

    @patch("daemon_manager.subprocess.Popen")
    @patch("daemon_manager.os.path.exists")
    @patch("daemon_manager.time.sleep")
    def test_start_daemons_spawn_error(self, mock_sleep, mock_exists, mock_popen):
        """start_daemons should handle subprocess spawn errors gracefully."""
        mock_exists.return_value = True
        mock_popen.side_effect = OSError("Failed to spawn")

        dm = self.DaemonManager(
            coind_path="/path/to/coind",
            goldd_path="/path/to/goldd",
            oxc_rpc_user="user1",
            oxc_rpc_password="pass1",
            oxg_rpc_user="user2",
            oxg_rpc_password="pass2",
            coind_datadir=self.tmpdir.name,
            goldd_datadir=self.tmpdir.name,
        )

        # Should not raise, just log error
        dm.start_daemons()
        self.assertIsNone(dm.coind_proc)
        self.assertIsNone(dm.goldd_proc)

    def test_stop_daemons_no_processes(self):
        """stop_daemons should handle case where no processes are running."""
        dm = self.DaemonManager(
            coind_path="/path/to/coind",
            goldd_path="/path/to/goldd",
            oxc_rpc_user="user1",
            oxc_rpc_password="pass1",
            oxg_rpc_user="user2",
            oxg_rpc_password="pass2",
        )

        # Should not raise
        dm.stop_daemons()

    def test_stop_daemons_with_running_processes(self):
        """stop_daemons should terminate running processes gracefully."""
        dm = self.DaemonManager(
            coind_path="/path/to/coind",
            goldd_path="/path/to/goldd",
            oxc_rpc_user="user1",
            oxc_rpc_password="pass1",
            oxg_rpc_user="user2",
            oxg_rpc_password="pass2",
        )

        # Mock process objects
        mock_coind = MagicMock()
        mock_coind.poll.return_value = None
        mock_goldd = MagicMock()
        mock_goldd.poll.return_value = None

        dm.coind_proc = mock_coind
        dm.goldd_proc = mock_goldd

        dm.stop_daemons()

        # Both processes should have terminate called
        mock_coind.terminate.assert_called_once()
        mock_goldd.terminate.assert_called_once()
        # Both processes should have wait called
        mock_coind.wait.assert_called_once()
        mock_goldd.wait.assert_called_once()

    def test_stop_daemons_terminate_timeout(self):
        """stop_daemons should call kill if terminate times out."""
        dm = self.DaemonManager(
            coind_path="/path/to/coind",
            goldd_path="/path/to/goldd",
            oxc_rpc_user="user1",
            oxc_rpc_password="pass1",
            oxg_rpc_user="user2",
            oxg_rpc_password="pass2",
        )

        # Mock process that times out on terminate
        mock_proc = MagicMock()
        mock_proc.terminate.side_effect = None
        mock_proc.wait.side_effect = subprocess.TimeoutExpired("cmd", 10)

        dm.coind_proc = mock_proc
        dm.goldd_proc = MagicMock()
        dm.goldd_proc.poll.return_value = None

        dm.stop_daemons()

        # Should call kill after timeout
        mock_proc.kill.assert_called_once()


class TestDaemonManagerStatus(unittest.TestCase):
    """Test daemon status monitoring."""

    def setUp(self):
        """Set up test fixtures."""
        from daemon_manager import DaemonManager
        self.DaemonManager = DaemonManager

    def test_is_running_false_initially(self):
        """is_running should return False initially."""
        dm = self.DaemonManager(
            coind_path="/path/to/coind",
            goldd_path="/path/to/goldd",
            oxc_rpc_user="user1",
            oxc_rpc_password="pass1",
            oxg_rpc_user="user2",
            oxg_rpc_password="pass2",
        )
        self.assertFalse(dm.is_running())

    def test_is_running_true_when_both_processes_exist(self):
        """is_running should return True when both processes are set."""
        dm = self.DaemonManager(
            coind_path="/path/to/coind",
            goldd_path="/path/to/goldd",
            oxc_rpc_user="user1",
            oxc_rpc_password="pass1",
            oxg_rpc_user="user2",
            oxg_rpc_password="pass2",
        )
        dm.coind_proc = MagicMock()
        dm.goldd_proc = MagicMock()
        self.assertTrue(dm.is_running())

    def test_is_running_false_with_only_coind(self):
        """is_running should return False if only coind is running."""
        dm = self.DaemonManager(
            coind_path="/path/to/coind",
            goldd_path="/path/to/goldd",
            oxc_rpc_user="user1",
            oxc_rpc_password="pass1",
            oxg_rpc_user="user2",
            oxg_rpc_password="pass2",
        )
        dm.coind_proc = MagicMock()
        self.assertFalse(dm.is_running())

    def test_get_status_no_processes(self):
        """get_status should return False for both daemons when not running."""
        dm = self.DaemonManager(
            coind_path="/path/to/coind",
            goldd_path="/path/to/goldd",
            oxc_rpc_user="user1",
            oxc_rpc_password="pass1",
            oxg_rpc_user="user2",
            oxg_rpc_password="pass2",
        )
        status = dm.get_status()
        self.assertFalse(status["ordexcoind_running"])
        self.assertFalse(status["ordexgoldd_running"])

    def test_get_status_with_running_processes(self):
        """get_status should return True for running daemons."""
        dm = self.DaemonManager(
            coind_path="/path/to/coind",
            goldd_path="/path/to/goldd",
            oxc_rpc_user="user1",
            oxc_rpc_password="pass1",
            oxg_rpc_user="user2",
            oxg_rpc_password="pass2",
        )

        # Mock running processes
        mock_coind = MagicMock()
        mock_coind.poll.return_value = None  # Process still running
        mock_goldd = MagicMock()
        mock_goldd.poll.return_value = None

        dm.coind_proc = mock_coind
        dm.goldd_proc = mock_goldd

        status = dm.get_status()
        self.assertTrue(status["ordexcoind_running"])
        self.assertTrue(status["ordexgoldd_running"])

    def test_get_status_with_terminated_process(self):
        """get_status should return False for terminated processes."""
        dm = self.DaemonManager(
            coind_path="/path/to/coind",
            goldd_path="/path/to/goldd",
            oxc_rpc_user="user1",
            oxc_rpc_password="pass1",
            oxg_rpc_user="user2",
            oxg_rpc_password="pass2",
        )

        # Mock: coind terminated, goldd still running
        mock_coind = MagicMock()
        mock_coind.poll.return_value = 1  # Process terminated
        mock_goldd = MagicMock()
        mock_goldd.poll.return_value = None  # Process still running

        dm.coind_proc = mock_coind
        dm.goldd_proc = mock_goldd

        status = dm.get_status()
        self.assertFalse(status["ordexcoind_running"])
        self.assertTrue(status["ordexgoldd_running"])


class TestDaemonManagerConfiguration(unittest.TestCase):
    """Test configuration security and correctness."""

    def setUp(self):
        """Set up test fixtures."""
        from daemon_manager import DaemonManager
        self.DaemonManager = DaemonManager
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)

    def test_conf_file_has_restricted_ports(self):
        """Configuration should restrict RPC to localhost."""
        dm = self.DaemonManager(
            coind_path="/path/to/coind",
            goldd_path="/path/to/goldd",
            oxc_rpc_user="user1",
            oxc_rpc_password="pass1",
            oxg_rpc_user="user2",
            oxg_rpc_password="pass2",
        )

        conf_path = dm._write_conf(
            self.tmpdir.name,
            "testcoin",
            25174,
            25173,
            "testuser",
            "testpass",
        )

        with open(conf_path, "r") as f:
            content = f.read()
        self.assertIn("bind=127.0.0.1", content)
        self.assertIn("rpcbind=127.0.0.1", content)
        self.assertIn("rpcallowip=127.0.0.1", content)

    def test_build_args_has_localhost_bindings(self):
        """Command arguments should restrict to localhost."""
        dm = self.DaemonManager(
            coind_path="/path/to/coind",
            goldd_path="/path/to/goldd",
            oxc_rpc_user="user1",
            oxc_rpc_password="pass1",
            oxg_rpc_user="user2",
            oxg_rpc_password="pass2",
        )

        args = dm._build_args(
            "/path/to/daemon",
            25174,
            25173,
            "/path/to/conf",
            "testuser",
            "testpass",
        )

        self.assertIn("-bind=127.0.0.1", args)
        self.assertIn("-rpcbind=127.0.0.1", args)
        self.assertIn("-rpcallowip=127.0.0.1", args)
        # Should not have public IP bindings
        public_bind = [a for a in args if "0.0.0.0" in a or "bind=:" in a]
        self.assertEqual(len(public_bind), 0)


if __name__ == "__main__":
    unittest.main()
