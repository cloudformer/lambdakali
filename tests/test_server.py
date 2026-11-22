"""The Lambda: sign-in, scanners (start with instance/image/lease, extend, stop), command tasks, the queue, logs,
output links."""
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


def add(command="nmap -sV scanme.example.com"):
    return call("POST", "/api/tasks", {"command": command})


def queued(aws):
    return [json.loads(v) for k, v in sorted(aws[2].objects.items()) if k.startswith("tasks/")]


def test_page_is_public_and_carries_the_version():
    status, r = call("GET", "/", auth=False)
    assert status == 200 and lf.VERSION in r["body"] and "lambdakali" in r["body"]


def test_api_needs_sign_in():
    assert call("GET", "/api/scanners", auth=False)[0] == 401


def test_config():
    status, r = call("GET", "/api/config")
    assert status == 200 and r["durations"] == [60, 120, 240, 480] and r["max_scanners"] == 2
    assert r["default_instance"] == "BUILD_GENERAL1_SMALL" and "BUILD_GENERAL1_LARGE" in r["instances"]
    assert set(r["images"]) == {"slim", "common"} and r["default_image"] == "common"
    assert "tools" not in r and "allowed_targets" not in r   # a free console: no tool list, no allowlist


def test_start_with_instance_image_and_lease(aws):
    status, r = call("POST", "/api/scanners", {"compute_type": "BUILD_GENERAL1_MEDIUM", "image": "slim", "minutes": 60})
    assert status == 201 and r["id"] == SCANNER_ID and r["compute_type"] == "BUILD_GENERAL1_MEDIUM" and r["image"] == "slim" and r["until"]
    assert aws[0].started[0]["compute_type"] == "BUILD_GENERAL1_MEDIUM" and aws[0].started[0]["image"] == "repo:slim-arm64"


def test_bad_image_is_rejected(aws):
    assert call("POST", "/api/scanners", {"image": "huge"})[0] == 400 and not aws[0].started


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


def test_any_command_is_added(aws):
    for cmd in ["nmap -sV scanme.example.com", "keepass2john x.kdbx > hash", "aws s3 cp s3://b/x.kdbx .",
                "nikto -h https://example.com/ | tee out"]:
        status, r = add(cmd)
        assert status == 201 and r["command"] == cmd and r["by"] == "admin" and r["claim"] is None
    assert len(queued(aws)) == 4


@pytest.mark.parametrize("command", ["", "   ", None, 123, "x" * 5000])
def test_bad_commands_are_rejected(command, aws):
    assert call("POST", "/api/tasks", {"command": command})[0] == 400 and not queued(aws)


def test_tasks_sort_in_order_and_list_newest_first(aws):
    ids = [add(f"echo {i}")[1]["id"] for i in range(3)]
    assert ids == sorted(ids)
    status, r = call("GET", "/api/tasks")
    assert [t["id"] for t in r["tasks"]] == ids[::-1]


def test_task_with_claim_log_and_output(aws):
    call("POST", "/api/scanners", {})
    t = add("nmap scanme.example.com")[1]
    aws[2].objects[f"claims/{t['id']}.json"] = json.dumps({"scanner": SCANNER_ID, "started": "2026-11-21T10:01:00Z"}).encode()
    aws[1].streams[SCANNER_ID] = ["::ready", f"::task {t['id']} start", f"::run {t['id']} nmap scanme.example.com",
                                  f"::out {t['id']} 80/tcp open", "noise from another task"]
    status, r = call("GET", f"/api/tasks/{t['id']}")
    assert status == 200 and r["claim"]["scanner"] == SCANNER_ID
    assert [e["line"] for e in r["log"]] == aws[1].streams[SCANNER_ID][1:4]
    aws[2].objects[f"reports/{t['id']}/output.txt"] = b"80/tcp open"
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
