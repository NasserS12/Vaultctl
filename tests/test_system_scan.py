from unittest.mock import MagicMock, patch

from modules.system_scan import get_os_pretty_name, get_package_counts


def test_get_os_pretty_name_extracts_correct_value(tmp_path):
    fake_file = tmp_path / "os-release"
    fake_file.write_text('PRETTY_NAME="Ubuntu 24.04.1 LTS"\n')

    result = get_os_pretty_name(str(fake_file))

    assert result == "Ubuntu 24.04.1 LTS"


@patch("modules.system_scan.subprocess.run")
def test_get_package_counts_parses_dpkg_and_snap(mock_run):
    dpkg_result = MagicMock()
    dpkg_result.stdout = "installed\ninstalled\ninstalled\n"

    snap_result = MagicMock()
    snap_result.stdout = "Name  Version  Rev\npkg1  1.0  1\npkg2  2.0  2\n"

    mock_run.side_effect = [dpkg_result, snap_result]

    result = get_package_counts()

    assert result == "3 (dpkg), 2 (snap)"
