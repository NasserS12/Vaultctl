"""Unit tests for modules/service_optimizer.py

Focus: CRITICAL_BLACKLIST must always protect core system services from
secure_stop_service(), regardless of what a user selects in the menu.
subprocess.run is mocked throughout -- these tests must never touch a
real system.
"""
from unittest.mock import MagicMock, patch

import pytest

from modules.service_optimizer import CRITICAL_BLACKLIST, secure_stop_service


class TestCriticalBlacklistContents:
    @pytest.mark.parametrize(
        "expected",
        [
            "systemd-",
            "dbus",
            "display-manager",
            "gdm",
            "lightdm",
            "sddm",
            "poweroff",
            "reboot",
            "halt",
            "default.target",
            "rescue.target",
            "emergency.target",
        ],
    )
    def test_expected_entries_present(self, expected):
        assert expected in CRITICAL_BLACKLIST


class TestSecureStopServiceBlacklistProtection:
    @pytest.mark.parametrize(
        "service_name",
        [
            "systemd-resolved",
            "systemd-journald",
            "dbus",
            "dbus.socket",
            "display-manager",
            "gdm",
            "gdm3",  # substring match: 'gdm' in 'gdm3'
            "lightdm",
            "sddm",
            "poweroff",
            "reboot",
            "halt",
            "default.target",
            "rescue.target",
            "emergency.target",
        ],
    )
    @patch("modules.service_optimizer.subprocess.run")
    def test_blacklisted_service_never_touches_subprocess(
        self, mock_run, service_name
    ):
        result = secure_stop_service(service_name)
        assert result is False
        mock_run.assert_not_called()

    @patch("modules.service_optimizer.os.name", "posix")
    @patch("modules.service_optimizer.subprocess.run")
    def test_non_blacklisted_service_is_stopped_and_masked(self, mock_run):
        scan_result = MagicMock(returncode=0, stdout="bluetooth.service enabled\n")
        stop_result = MagicMock(returncode=0)
        mask_result = MagicMock(returncode=0)
        mock_run.side_effect = [scan_result, stop_result, mask_result]

        result = secure_stop_service("bluetooth")

        assert result is True
        calls = mock_run.call_args_list
        assert calls[1].args[0][:3] == ["sudo", "systemctl", "stop"]
        assert calls[2].args[0][:3] == ["sudo", "systemctl", "mask"]

    @patch("modules.service_optimizer.os.name", "posix")
    @patch("modules.service_optimizer.subprocess.run")
    def test_blacklisted_unit_from_scan_is_never_stopped_or_masked(self, mock_run):
        # Even if the systemctl scan happens to surface a unit whose name
        # matches the blacklist alongside a legitimate one, the filter
        # inside secure_stop_service must strip it before acting on it.
        scan_result = MagicMock(
            returncode=0,
            stdout="cups.service enabled\nsystemd-timesyncd.service enabled\n",
        )
        stop_result = MagicMock(returncode=0)
        mask_result = MagicMock(returncode=0)
        mock_run.side_effect = [scan_result, stop_result, mask_result]

        result = secure_stop_service("cups")

        assert result is True
        acted_on_units = [
            call.args[0][3]
            for call in mock_run.call_args_list[1:]
            if len(call.args[0]) > 3
        ]
        assert "systemd-timesyncd.service" not in acted_on_units
        assert "cups.service" in acted_on_units

    @patch("modules.service_optimizer.os.name", "nt")
    @patch("modules.service_optimizer.subprocess.run")
    def test_non_posix_returns_false_without_running_anything(self, mock_run):
        result = secure_stop_service("bluetooth")
        assert result is False
        mock_run.assert_not_called()

    @patch("modules.service_optimizer.os.name", "posix")
    @patch("modules.service_optimizer.subprocess.run")
    def test_scan_failure_returns_false(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        result = secure_stop_service("bluetooth")
        assert result is False

    @patch("modules.service_optimizer.os.name", "posix")
    @patch("modules.service_optimizer.subprocess.run")
    def test_no_matching_units_falls_back_to_service_name(self, mock_run):
        # If the scan returns no matching unit files, secure_stop_service
        # falls back to trying "<service_name>.service" directly.
        scan_result = MagicMock(returncode=0, stdout="")
        stop_result = MagicMock(returncode=0)
        mask_result = MagicMock(returncode=0)
        mock_run.side_effect = [scan_result, stop_result, mask_result]

        result = secure_stop_service("whoopsie")

        assert result is True
        calls = mock_run.call_args_list
        assert calls[1].args[0][3] == "whoopsie.service"
