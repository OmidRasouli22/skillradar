import pytest

from skillradar.schedule import cli
from skillradar.schedule.launchd import LaunchAgent
from tests.test_launchd import FakeLaunchctl


@pytest.fixture
def agent(tmp_path):
    return LaunchAgent(tmp_path / "agents", runner=FakeLaunchctl())


def test_install_and_uninstall(agent, capsys):
    assert cli.main(["install", "--check-every", "30"], agent=agent) == 0
    assert "every 30 min" in capsys.readouterr().out
    assert agent.plist_path.exists()

    assert cli.main(["uninstall"], agent=agent) == 0
    assert "removed" in capsys.readouterr().out


def test_invalid_interval_is_rejected(agent, capsys):
    assert cli.main(["install", "--check-every", "1"], agent=agent) == 1
    assert "invalid check interval" in capsys.readouterr().err
    assert not agent.plist_path.exists()


def test_missing_uv(agent, monkeypatch, capsys):
    monkeypatch.setattr(cli.shutil, "which", lambda name: None)

    assert cli.main(["install"], agent=agent) == 1
    assert "uv not found" in capsys.readouterr().err


def test_command_is_required():
    with pytest.raises(SystemExit):
        cli.main([])
