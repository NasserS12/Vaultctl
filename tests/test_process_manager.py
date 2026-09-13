from modules.process_manager import is_kernel_protected_pid


def test_pid_at_threshold_is_protected():
    assert is_kernel_protected_pid(100) is True


def test_pid_just_above_threshold_is_not_protected():
    assert is_kernel_protected_pid(101) is False


def test_pid_well_below_threshold_is_protected():
    assert is_kernel_protected_pid(1) is True


def test_pid_well_above_threshold_is_not_protected():
    assert is_kernel_protected_pid(9999) is False
