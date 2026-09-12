"""Unit tests for modules/ssh_audit.py

Priority target: get_smart_val() (parses sshd_config-style directives)
and the historical two-factor "OR" bug in audit_ssh_security(), now
extracted into the pure, testable helper is_2fa_ssh_ready().
"""
import pytest

from modules.ssh_audit import get_smart_val, is_2fa_ssh_ready

# ---------------------------------------------------------------------------
# get_smart_val
# ---------------------------------------------------------------------------

class TestGetSmartVal:
    def test_active_directive_found(self):
        content = "PermitRootLogin no\n"
        value, active = get_smart_val(content, "PermitRootLogin")
        assert value == "no"
        assert active is True

    def test_commented_directive_used_as_hint_when_no_active(self):
        content = "#PermitRootLogin prohibit-password\n"
        value, active = get_smart_val(content, "PermitRootLogin")
        assert value == "prohibit-password"
        assert active is False

    def test_active_wins_over_commented(self):
        content = (
            "#PermitRootLogin prohibit-password\n"
            "PermitRootLogin no\n"
        )
        value, active = get_smart_val(content, "PermitRootLogin")
        assert value == "no"
        assert active is True

    def test_missing_directive_returns_none(self):
        content = "Port 22\n"
        value, active = get_smart_val(content, "PermitRootLogin")
        assert value is None
        assert active is False

    def test_first_active_occurrence_wins(self):
        # sshd applies the FIRST active occurrence it sees (e.g. an
        # Include'd drop-in file taking precedence over the main file).
        content = "Port 2222\nPort 22\n"
        value, active = get_smart_val(content, "Port")
        assert value == "2222"
        assert active is True

    def test_case_insensitive_key_and_value(self):
        content = "permitrootlogin YES\n"
        value, active = get_smart_val(content, "PermitRootLogin")
        assert value == "yes"
        assert active is True

    def test_ignores_indentation_and_extra_whitespace(self):
        content = "   PasswordAuthentication    no   \n"
        value, active = get_smart_val(content, "PasswordAuthentication")
        assert value == "no"
        assert active is True

    def test_commented_with_hash_and_space_variants(self):
        content = "# PasswordAuthentication yes\n"
        value, active = get_smart_val(content, "PasswordAuthentication")
        assert value == "yes"
        assert active is False

    def test_multiline_config_picks_correct_key(self):
        content = (
            "Port 22\n"
            "PermitRootLogin no\n"
            "PasswordAuthentication yes\n"
        )
        assert get_smart_val(content, "PasswordAuthentication") == ("yes", True)
        assert get_smart_val(content, "PermitRootLogin") == ("no", True)

    def test_does_not_match_similarly_prefixed_key(self):
        # "PermitRootLogin" must not falsely match a lookup for "Permit"
        content = "PermitRootLogin no\n"
        value, active = get_smart_val(content, "Permit")
        assert value is None
        assert active is False


# ---------------------------------------------------------------------------
# The 2FA "OR" bug: KbdInteractiveAuthentication / ChallengeResponseAuthentication
# ---------------------------------------------------------------------------

class TestTwoFactorOrBugRegression:
    """Regression tests for the historical bug that lived in
    `audit_ssh_security`:

        is_ssh_ready = (v_kbd or v_chall) == 'yes'

    `or` between two strings returns the first *truthy* string, so if
    v_kbd == 'no' (a non-empty, truthy string), it short-circuits and
    is returned as-is -- v_chall is never even inspected, even when
    v_chall == 'yes'. The fix lives in is_2fa_ssh_ready().
    """

    def test_old_buggy_expression_documented(self):
        # Not calling production code here on purpose -- this test just
        # documents, in isolation, exactly how the old inline expression
        # used to fail, so the failure mode stays legible without
        # reintroducing the bug into ssh_audit.py itself.
        v_kbd, v_chall = "no", "yes"
        buggy_result = (v_kbd or v_chall) == 'yes'
        assert buggy_result is False  # WRONG: chall says 'yes' but was ignored

    @pytest.mark.parametrize(
        "v_kbd, v_chall, expected",
        [
            ("yes", "no", True),   # kbd=yes, chall=no  -> ready
            ("no", "yes", True),   # kbd=no,  chall=yes  -> ready (the bug case)
            ("no", "no", False),   # both no             -> not ready
            ("yes", "yes", True),  # both yes            -> ready
            (None, "yes", True),   # directive absent, other set
            (None, None, False),   # neither directive present
        ],
    )
    def test_is_2fa_ssh_ready_all_combinations(self, v_kbd, v_chall, expected):
        assert is_2fa_ssh_ready(v_kbd, v_chall) is expected

    def test_is_2fa_ssh_ready_matches_end_to_end_via_get_smart_val(self):
        # kbd is inactive/no while chall is active/yes -- the exact
        # config shape that used to trip the bug.
        content = (
            "KbdInteractiveAuthentication no\n"
            "ChallengeResponseAuthentication yes\n"
        )
        v_kbd, _ = get_smart_val(content, "KbdInteractiveAuthentication")
        v_chall, _ = get_smart_val(content, "ChallengeResponseAuthentication")
        assert is_2fa_ssh_ready(v_kbd, v_chall) is True
