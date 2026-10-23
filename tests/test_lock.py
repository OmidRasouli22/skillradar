import pytest

from skillradar.lock import AlreadyRunning, run_lock


def test_second_run_is_blocked(tmp_path):
    lock = tmp_path / ".lock"

    with run_lock(lock):
        with pytest.raises(AlreadyRunning):
            with run_lock(lock):
                pass


def test_lock_is_released_after_run(tmp_path):
    lock = tmp_path / ".lock"

    with run_lock(lock):
        pass
    with run_lock(lock):
        pass


def test_lock_is_released_after_error(tmp_path):
    lock = tmp_path / ".lock"

    with pytest.raises(RuntimeError):
        with run_lock(lock):
            raise RuntimeError("boom")
    with run_lock(lock):
        pass


def test_lock_file_is_private(tmp_path):
    lock = tmp_path / "new_dir" / ".lock"

    with run_lock(lock):
        assert lock.stat().st_mode & 0o777 == 0o600
