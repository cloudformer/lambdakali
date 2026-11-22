"""The scanner in the image: takes queued command tasks in order (S3 claims), runs each with bash -lc, markers,
result from the exit code, output to S3, secrets masked, idle shutdown, the lease."""
import json
import os
import subprocess

import pytest

import scan
from conftest import FakeS3

SESSION = "abc"


class FakeSSM:
    def __init__(self, values):
        self.values = values

    def get_parameters(self, Names, WithDecryption):
        return {"Parameters": [{"Name": n, "Value": self.values[n]} for n in Names if n in self.values]}


class FakeShell:
    """Stands in for `bash -lc <command>`: records the command, prints a line (with the secret, to test masking),
    exits with a code. exits is a list, one per task in order."""

    def __init__(self, exits):
        self.exits, self.commands = exits, []

    def __call__(self, cmd, cwd, env, **kw):
        assert cmd[:2] == ["bash", "-lc"]
        self.commands.append(cmd[2])
        code = self.exits[len(self.commands) - 1]

        class P:
            stdout = iter([f"ran: {cmd[2]} token={env.get('TOKEN', '-')}\n"])

            def wait(self):
                return code
        return P()


@pytest.fixture
def run(tmp_path, monkeypatch, capsys):
    s3 = FakeS3()
    ssm = FakeSSM({"/test/secrets/TOKEN": "s3cr3t-value"})
    monkeypatch.setattr(scan, "WORK", str(tmp_path))
    monkeypatch.setattr(scan.boto3, "client", lambda name: {"s3": s3, "ssm": ssm}[name])
    monkeypatch.setattr(scan.threading, "Thread", lambda **kw: type("T", (), {"start": lambda self: None})())
    monkeypatch.setenv("BUCKET", "test-reports")
    monkeypatch.setenv("CODEBUILD_BUILD_ID", f"test-scanner:{SESSION}")
    monkeypatch.setenv("IDLE_SHUTDOWN_MINUTES", "0")
    monkeypatch.delenv("SECRETS", raising=False)

    def go(commands, exits, secrets=None, value=None, claimed=()):
        if secrets:
            monkeypatch.setenv("SECRETS", secrets)
            monkeypatch.setenv("SECRETS_PATH", "/test/secrets/")
        if value:
            ssm.values["/test/secrets/TOKEN"] = value
        for i, command in enumerate(commands):
            s3.objects[f"tasks/{i:019d}-0000.json"] = json.dumps({"id": f"{i:019d}-0000", "command": command}).encode()
        for i in claimed:
            s3.objects[f"claims/{i:019d}-0000.json"] = json.dumps({"scanner": "other"}).encode()
        sh = FakeShell(exits)
        monkeypatch.setattr(subprocess, "Popen", sh)
        try:
            scan.Scanner().main()
            code = 0
        except SystemExit as e:
            code = e.code
        return code, capsys.readouterr().out.splitlines(), s3.objects, sh.commands
    return go


def test_commands_in_order_run_and_uploaded(run):
    code, out, objects, cmds = run(["nmap -sV scanme.example.com", "keepass2john x.kdbx > hash"], [0, 1])
    t0, t1 = f"{0:019d}-0000", f"{1:019d}-0000"
    assert code == 0 and out[0] == "::ready" and out[-1] == "::shutdown idle"
    assert f"::run {t0} nmap -sV scanme.example.com" in out and f"::task {t0} end pass" in out
    assert f"::run {t1} keepass2john x.kdbx > hash" in out and f"::task {t1} end fail" in out
    assert cmds == ["nmap -sV scanme.example.com", "keepass2john x.kdbx > hash"]   # run verbatim via bash -lc
    assert f"reports/{t0}/output.txt" in objects and f"reports/{t1}/output.txt" in objects
    claim = json.loads(objects[f"claims/{t0}.json"])
    assert claim["scanner"] == "abc" and claim["result"] == "pass" and claim["command"] == "nmap -sV scanme.example.com"


def test_a_task_another_scanner_claimed_is_skipped(run):
    code, out, objects, cmds = run(["echo a", "echo b"], [0], claimed=[0])
    assert cmds == ["echo b"]


def test_secret_reaches_the_command_and_is_masked(run):
    code, out, objects, cmds = run(["curl -H \"$TOKEN\" x"], [0], secrets="TOKEN")
    assert any("token=***" in l for l in out) and not any("s3cr3t" in l for l in out)


def test_unset_secret_shuts_down_before_any_run(run):
    code, out, objects, cmds = run(["echo x"], [0], secrets="TOKEN", value="CHANGE-ME")
    assert code == 1 and out[-1] == "::shutdown secrets" and cmds == []


def test_idle_with_no_task_shuts_down(run):
    code, out, objects, cmds = run([], [])
    assert code == 0 and out == ["::ready", "::shutdown idle"] and cmds == []


def test_lease(monkeypatch):
    s3 = FakeS3()
    monkeypatch.setattr(scan.boto3, "client", lambda name: s3)
    monkeypatch.setenv("BUCKET", "b")
    monkeypatch.setenv("CODEBUILD_BUILD_ID", "p:abc")
    s = scan.Scanner()
    assert s.expired() is False
    s3.objects["leases/abc.json"] = json.dumps({"until": "2000-01-01T00:00:00Z"}).encode()
    assert s.expired() is True
