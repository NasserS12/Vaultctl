"""Unit tests for modules/network_audit.py -> parse_ss_line()."""
from modules.network_audit import parse_ss_line


class TestParseSsLine:
    def test_extracts_process_name(self):
        line = (
            'tcp   LISTEN 0      128      0.0.0.0:22        0.0.0.0:*    '
            'users:(("sshd",pid=1234,fd=3))'
        )
        data = parse_ss_line(line)
        assert data["process"] == "sshd"

    def test_extracts_local_and_peer_for_listening_socket(self):
        line = (
            'tcp   LISTEN 0      128      0.0.0.0:22        0.0.0.0:*    '
            'users:(("sshd",pid=1234,fd=3))'
        )
        data = parse_ss_line(line)
        assert data["local"] == "0.0.0.0:22"
        assert data["peer"] == "0.0.0.0:*"

    def test_extracts_local_and_peer_for_established_connection(self):
        line = (
            'tcp   ESTAB  0      0        192.168.1.5:54321  '
            '93.184.216.34:443  users:(("firefox",pid=2222,fd=45))'
        )
        data = parse_ss_line(line)
        assert data["process"] == "firefox"
        assert data["local"] == "192.168.1.5:54321"
        assert data["peer"] == "93.184.216.34:443"

    def test_missing_users_field_returns_unknown_process(self):
        line = 'tcp   LISTEN 0      128      127.0.0.1:631      0.0.0.0:*'
        data = parse_ss_line(line)
        assert data["process"] == "Unknown"
        assert data["local"] == "127.0.0.1:631"
        assert data["peer"] == "0.0.0.0:*"

    def test_ipv6_addresses(self):
        line = (
            'tcp   LISTEN 0      128      [::]:22            [::]:*       '
            'users:(("sshd",pid=1,fd=3))'
        )
        data = parse_ss_line(line)
        assert data["local"] == "[::]:22"
        assert data["peer"] == "[::]:*"

    def test_no_colon_bearing_tokens_returns_na_for_both_addresses(self):
        line = "garbage line with no addresses in it"
        data = parse_ss_line(line)
        assert data["local"] == "N/A"
        assert data["peer"] == "N/A"

    def test_only_local_address_present_peer_is_na(self):
        line = 'tcp   LISTEN 0      128      127.0.0.1:631'
        data = parse_ss_line(line)
        assert data["local"] == "127.0.0.1:631"
        assert data["peer"] == "N/A"

    def test_users_suffix_excluded_from_parts(self):
        line = (
            'tcp   LISTEN 0      128      0.0.0.0:22        0.0.0.0:*    '
            'users:(("sshd",pid=1234,fd=3))'
        )
        data = parse_ss_line(line)
        assert all("users:" not in p for p in data["parts"])

    def test_process_name_with_special_characters(self):
        line = (
            'tcp   LISTEN 0      128      0.0.0.0:8080       0.0.0.0:*    '
            'users:(("node-server.sh",pid=555,fd=9))'
        )
        data = parse_ss_line(line)
        assert data["process"] == "node-server.sh"
