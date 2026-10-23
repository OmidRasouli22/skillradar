import subprocess

from skillradar.notify import notify


def test_text_is_passed_as_arguments_not_as_script(tmp_path):
    calls = []
    evil = '" & do shell script "touch /tmp/hacked" & "'

    notify("Title", evil, runner=calls.append, platform="darwin")

    [args] = calls
    assert args[0] == "/usr/bin/osascript"
    assert args[-2:] == ["Title", evil]
    script = " ".join(args[:-3])
    assert "hacked" not in script


def test_long_message_is_cut(tmp_path):
    calls = []

    notify("Title", "x" * 1000, runner=calls.append, platform="darwin")

    assert len(calls[0][-1]) == 200


def test_does_nothing_outside_macos():
    calls = []

    notify("Title", "msg", runner=calls.append, platform="linux")

    assert calls == []


def test_failure_to_notify_does_not_raise(caplog):
    def broken(args):
        raise subprocess.CalledProcessError(1, args)

    notify("Title", "msg", runner=broken, platform="darwin")

    assert "could not show notification" in caplog.text
