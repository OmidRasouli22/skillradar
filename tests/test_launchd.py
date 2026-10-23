import plistlib
import subprocess
from pathlib import Path

import pytest

from skillradar.schedule.launchd import LABEL, Job, LaunchAgent, build_plist


def make_job(tmp_path, **changes):
    values = {
        "uv": Path("/opt/homebrew/bin/uv"),
        "project_dir": tmp_path / "project",
        "log_file": tmp_path / "logs" / "snapshot.log",
    }
    return Job(**(values | changes))


class FakeLaunchctl:
    def __init__(self, fail: str | None = None) -> None:
        self.calls: list[list[str]] = []
        self.fail = fail

    def __call__(self, args):
        self.calls.append(list(args))
        code = 1 if self.fail and self.fail in args else 0
        return subprocess.CompletedProcess(args, code, stdout="", stderr="error text")

    def commands(self):
        return [call[1] for call in self.calls]


class TestJob:
    def test_plist_content(self, tmp_path):
        job = make_job(tmp_path, hour=7, minute=30)

        plist = plistlib.loads(build_plist(job))

        assert plist["Label"] == LABEL
        assert plist["ProgramArguments"] == [
            "/opt/homebrew/bin/uv",
            "run",
            "--project",
            str(job.project_dir),
            "skillradar-snapshot",
            "--notify",
        ]
        assert plist["StartCalendarInterval"] == {"Hour": 7, "Minute": 30}
        assert plist["StandardOutPath"] == str(job.log_file)

    def test_special_characters_in_paths_are_escaped(self, tmp_path):
        job = make_job(tmp_path, project_dir=tmp_path / "a&b <c>")

        plist = plistlib.loads(build_plist(job))

        assert plist["WorkingDirectory"].endswith("a&b <c>")

    @pytest.mark.parametrize("hour, minute", [(24, 0), (-1, 0), (6, 60)])
    def test_rejects_invalid_time(self, tmp_path, hour, minute):
        with pytest.raises(ValueError, match="invalid time"):
            make_job(tmp_path, hour=hour, minute=minute)

    def test_rejects_relative_paths(self, tmp_path):
        with pytest.raises(ValueError, match="absolute"):
            make_job(tmp_path, uv=Path("uv"))


class TestLaunchAgent:
    def test_install_writes_plist_and_loads_it(self, tmp_path):
        launchctl = FakeLaunchctl()
        agent = LaunchAgent(tmp_path / "agents", runner=launchctl)
        job = make_job(tmp_path)

        path = agent.install(job)

        assert path.read_bytes() == build_plist(job)
        assert path.stat().st_mode & 0o777 == 0o644
        assert launchctl.commands() == ["bootout", "bootstrap"]
        assert job.log_file.parent.is_dir()

    def test_install_twice_replaces_the_job(self, tmp_path):
        launchctl = FakeLaunchctl()
        agent = LaunchAgent(tmp_path / "agents", runner=launchctl)

        agent.install(make_job(tmp_path, hour=6))
        agent.install(make_job(tmp_path, hour=8))

        assert plistlib.loads(agent.plist_path.read_bytes())["StartCalendarInterval"]["Hour"] == 8
        assert launchctl.commands() == ["bootout", "bootstrap", "bootout", "bootstrap"]

    def test_install_reports_launchctl_error(self, tmp_path):
        agent = LaunchAgent(tmp_path / "agents", runner=FakeLaunchctl(fail="bootstrap"))

        with pytest.raises(RuntimeError, match="error text"):
            agent.install(make_job(tmp_path))

    def test_uninstall(self, tmp_path):
        launchctl = FakeLaunchctl()
        agent = LaunchAgent(tmp_path / "agents", runner=launchctl)
        agent.install(make_job(tmp_path))

        assert agent.uninstall() is True
        assert not agent.plist_path.exists()
        assert launchctl.commands()[-1] == "bootout"

    def test_uninstall_when_not_installed(self, tmp_path):
        launchctl = FakeLaunchctl()

        assert LaunchAgent(tmp_path / "agents", runner=launchctl).uninstall() is False
        assert launchctl.calls == []

    def test_run_now(self, tmp_path):
        launchctl = FakeLaunchctl()

        LaunchAgent(tmp_path / "agents", runner=launchctl).run_now()

        assert launchctl.calls[0][1] == "kickstart"
        assert launchctl.calls[0][2].endswith(f"/{LABEL}")
