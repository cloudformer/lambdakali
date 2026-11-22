"""The scanner in the image: takes queued tasks in order with S3 claims, runs one tool each, markers, result from the
exit code, output to S3, secrets masked, idle shutdown, the lease."""
import json
import os
import subprocess

import pytest

import scan
from conftest import FakeS3


class FakeSSM:
    def __init__(self, values):
        self.values = values

    def get_parameters(self, Names, WithDecryption):
        return {"Parameters": [{"Name": n, "Value": self.values[n]} for n in Names if n in self.values]}


class FakeTool:
    """Stands in for a tool: records the argv, prints a line (with the secret, to test masking), exits with a code.
    exits is a list, one per task in order; None raises FileNotFoundError (tool not installed)."""

    def __init__(self, exits):
        self.exits, self.calls = exits, []

    def __call__(self, cmd, cwd, env, **kw):
        self.calls.append(cmd)
        code = self.exits[len(self.calls) - 1]
        if code is None:
            raise FileNotFoundError(cmd[0])

        class P:
            stdout = iter([f"running {cmd[0]} against {cmd[-1]} token={env.get('TOKEN', '-')}\n"])

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
    monkeypatch.setenv("CODEBUILD_BUILD_ID", "test-scanner:abc")
    monkeypatch.setenv("IDLE_SHUTDOWN_MINUTES", "0")
    monkeypatch.delenv("SECRETS", raising=False)

    def go(tasks, exits, secrets=None, value=None, claimed=()):
        if secrets:
            monkeypatch.setenv("SECRETS", secrets)
            monkeypatch.setenv("SECRETS_PATH", "/test/secrets/")
        if value:
            ssm.values["/test/secrets/TOKEN"] = value
        for i, (tool, target, args) in enumerate(tasks):
            s3.objects[f"tasks/{i:019d}-0000.json"] = json.dumps(
                {"id": f"{i:019d}-0000", "tool": tool, "target": target, "args": args}).encode()
        for i in claimed:
            s3.objects[f"claims/{i:019d}-0000.json"] = json.dumps({"scanner": "other"}).encode()
        tool = FakeTool(exits)
        monkeypatch.setattr(subprocess, "Popen", tool)
        try:
            scan.Scanner().main()
            code = 0
        except SystemExit as e:
            code = e.code
        return code, capsys.readouterr().out.splitlines(), s3.objects, tool.calls
    return go


def test_tasks_in_order_claimed_run_and_uploaded(run):
    code, out, objects, calls = run([("nmap", "scanme.example.com", "-sV {target}"),
                                     ("nikto", "https://example.com/", "-h {target}")], [0, 1])
    t0, t1 = f"{0:019d}-0000", f"{1:019d}-0000"
    assert code == 0 and out[0] == "::ready" and out[-1] == "::shutdown idle"
    assert f"::run {t0} nmap -sV scanme.example.com" in out and f"::task {t0} end pass" in out
    assert f"::run {t1} nikto -h https://example.com/" in out and f"::task {t1} end fail" in out
    assert f"reports/{t0}/output.txt" in objects and f"reports/{t1}/output.txt" in objects
    assert calls[0] == ["nmap", "-sV", "scanme.example.com"] and calls[1] == ["nikto", "-h", "https://example.com/"]
    claim = json.loads(objects[f"claims/{t0}.json"])
    assert claim["scanner"] == "abc" and claim["result"] == "pass" and claim["tool"] == "nmap"


def test_target_is_substituted_not_split(run):
    # {target} is replaced after shlex.split, so a target cannot inject extra argv
    code, out, objects, calls = run([("nmap", "scanme.example.com", "-p 80 {target} -oN out")], [0])
    assert calls[0] == ["nmap", "-p", "80", "scanme.example.com", "-oN", "out"]


def test_a_task_another_scanner_claimed_is_skipped(run):
    code, out, objects, calls = run([("nmap", "a.example.com", "{target}"), ("nmap", "b.example.com", "{target}")], [0], claimed=[0])
    assert len(calls) == 1 and calls[0][-1] == "b.example.com"


def test_tool_not_installed_ends_in_error(run):
    code, out, objects, calls = run([("nmap", "a.example.com", "{target}")], [None])
    t = f"{0:019d}-0000"
    assert f"::task {t} end error" in out and any("not installed" in l for l in out)
    assert json.loads(objects[f"claims/{t}.json"])["result"] == "error"


def test_secret_reaches_the_tool_and_is_masked(run):
    code, out, objects, calls = run([("nmap", "a.example.com", "{target}")], [0], secrets="TOKEN")
    assert any("token=***" in l for l in out) and not any("s3cr3t" in l for l in out)


def test_unset_secret_shuts_down_before_any_run(run):
    code, out, objects, calls = run([("nmap", "a.example.com", "{target}")], [0], secrets="TOKEN", value="CHANGE-ME")
    assert code == 1 and out[-1] == "::shutdown secrets" and calls == []


def test_idle_with_no_task_shuts_down(run):
    code, out, objects, calls = run([], [])
    assert code == 0 and out == ["::ready", "::shutdown idle"] and calls == []


def test_lease(monkeypatch):
    s3 = FakeS3()
    monkeypatch.setattr(scan.boto3, "client", lambda name: s3)
    monkeypatch.setenv("BUCKET", "b")
    monkeypatch.setenv("CODEBUILD_BUILD_ID", "p:abc")
    s = scan.Scanner()
    assert s.expired() is False
    s3.objects["leases/abc.json"] = json.dumps({"until": "2000-01-01T00:00:00Z"}).encode()
    assert s.expired() is True
