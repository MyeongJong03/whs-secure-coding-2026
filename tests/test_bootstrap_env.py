import os
import stat
from pathlib import Path

import pytest

from scripts import bootstrap_env


TEMPLATE = """\
# local settings
SECRET_KEY=replace-with-a-long-random-local-value
FLASK_CONFIG=development
FLASK_DEBUG=0
"""


def read_secret_key(target: Path) -> str:
    settings = dict(
        line.split("=", 1)
        for line in target.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    )
    return settings["SECRET_KEY"]


def test_create_environment_file_with_default_paths(tmp_path, capsys, monkeypatch):
    example = tmp_path / ".env.example"
    target = tmp_path / ".env"
    example.write_text(TEMPLATE, encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    result = bootstrap_env.create_environment_file()
    captured = capsys.readouterr()
    secret_key = read_secret_key(target)

    assert result == Path(".env")
    assert target.exists()
    assert bootstrap_env.ENV_VALUE_MARKER not in target.read_text(encoding="utf-8")
    assert len(secret_key) >= 32
    assert "FLASK_CONFIG=development" in target.read_text(encoding="utf-8")
    assert "FLASK_DEBUG=0" in target.read_text(encoding="utf-8")
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert secret_key not in captured.out
    assert secret_key not in captured.err


def test_cli_success_does_not_print_generated_secret(tmp_path, capsys):
    example = tmp_path / "example"
    target = tmp_path / "target"
    example.write_text(TEMPLATE, encoding="utf-8")

    result = bootstrap_env.main(
        ["--example", os.fspath(example), "--target", os.fspath(target)]
    )
    captured = capsys.readouterr()
    secret_key = read_secret_key(target)

    assert result == 0
    assert os.fspath(target) in captured.out
    assert "db upgrade" in captured.out
    assert secret_key not in captured.out
    assert secret_key not in captured.err


def test_existing_target_is_not_overwritten(tmp_path, capsys):
    example = tmp_path / "example"
    target = tmp_path / "target"
    original = b"existing private settings\n"
    example.write_text(TEMPLATE, encoding="utf-8")
    target.write_bytes(original)

    result = bootstrap_env.main(
        ["--example", os.fspath(example), "--target", os.fspath(target)]
    )

    assert result != 0
    assert target.read_bytes() == original
    assert "오류:" in capsys.readouterr().err


@pytest.mark.parametrize(
    "template",
    [
        "SECRET_KEY=missing-placeholder\n",
        (
            "SECRET_KEY=replace-with-a-long-random-local-value\n"
            "SECOND=replace-with-a-long-random-local-value\n"
        ),
    ],
)
def test_invalid_placeholder_count_fails_without_target(tmp_path, template):
    example = tmp_path / "example"
    target = tmp_path / "target"
    example.write_text(template, encoding="utf-8")

    with pytest.raises(bootstrap_env.BootstrapEnvironmentError):
        bootstrap_env.create_environment_file(example, target)

    assert not target.exists()


def test_missing_example_fails_without_target(tmp_path):
    target = tmp_path / "target"

    with pytest.raises(bootstrap_env.BootstrapEnvironmentError):
        bootstrap_env.create_environment_file(tmp_path / "missing", target)

    assert not target.exists()


def test_partial_write_failure_removes_target(tmp_path, monkeypatch):
    example = tmp_path / "example"
    target = tmp_path / "target"
    example.write_text(TEMPLATE, encoding="utf-8")
    original_write = bootstrap_env.os.write
    calls = 0

    def fail_after_partial_write(descriptor, content):
        nonlocal calls
        calls += 1
        if calls == 1:
            return original_write(descriptor, content[:8])
        raise OSError("simulated partial write failure")

    monkeypatch.setattr(bootstrap_env.os, "write", fail_after_partial_write)

    with pytest.raises(bootstrap_env.BootstrapEnvironmentError):
        bootstrap_env.create_environment_file(example, target)

    assert calls == 2
    assert not target.exists()


def test_custom_target_does_not_modify_repository_env(tmp_path):
    repository_env = Path(__file__).resolve().parents[1] / ".env"
    existed_before = repository_env.exists()
    content_before = repository_env.read_bytes() if existed_before else None
    example = tmp_path / "example"
    target = tmp_path / "target"
    example.write_text(TEMPLATE, encoding="utf-8")

    bootstrap_env.create_environment_file(example, target)

    assert repository_env.exists() is existed_before
    if existed_before:
        assert repository_env.read_bytes() == content_before
