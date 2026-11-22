#!/usr/bin/env python3
"""lambdakali-scan: one scanner (one CodeBuild build). Takes tasks from the queue all scanners share, one at a time,
until its lease runs out or it has been idle for IDLE_SHUTDOWN_MINUTES; Shut down in the web UI stops the build.

    s3://<BUCKET>/tasks/<task id>.json      the queue, written by the Lambda (tool installed, target on the allowlist)
    s3://<BUCKET>/claims/<task id>.json     a scanner takes a task by creating its claim with If-None-Match: *;
                                            S3 lets one writer win, so no task runs twice. Rewritten at the end
                                            with the result. A cancelled task's claim is the Lambda's.
    s3://<BUCKET>/leases/<scanner id>.json  {"until": ISO time}: when this scanner shuts down; the web UI's +1h
                                            moves it. Checked every LEASE_CHECK_SECONDS, a running tool included.
    s3://<BUCKET>/reports/<task id>/output.txt   the tool's full output

A task is one shell command line, run with `bash -lc` in /work. /work persists for the scanner's life, so commands
build on each other (`aws s3 cp …`, `keepass2john x.kdbx > hash`, `john hash`). Grant what a command needs (e.g. read
an S3 path) through the module's scanner_policy_statements; the role's credentials are available to the aws CLI.

Environment (the CodeBuild project sets them; CodeBuild adds CODEBUILD_BUILD_ID = <project>:<scanner id>):
    BUCKET, IDLE_SHUTDOWN_MINUTES
    SECRETS, SECRETS_PATH   comma-separated names: each SSM SecureString <SECRETS_PATH><name> becomes the environment
                            variable <name> of every run; their values are replaced by *** in everything printed

Log lines (read by the web UI; a task's lines carry its id, so the UI can follow one task among several scanners):
    ::ready   ::task <id> start|end <result>   ::run <id> <command>   ::out <id> <text>   ::done <id> <exit code>
    ::shutdown <idle|lease|secrets>
result = pass (exit 0) | fail (any other exit) | error (the tool could not be run).
"""
import datetime
import json
import os
import subprocess
import sys
import threading
import time

import boto3
from botocore.exceptions import ClientError

WORK = "/work"                               # the tool's working directory and where output.txt is written
PLACEHOLDER = "CHANGE-ME"                    # what Terraform creates a secret with
POLL_SECONDS = 2
LEASE_CHECK_SECONDS = 10
OUTPUT_LIMIT = 20_000_000                    # bytes of output kept per task (a runaway tool cannot fill the disk)


def say(text):
    print(text, flush=True)


def now():
    return datetime.datetime.now(datetime.timezone.utc)


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


class Scanner:
    def __init__(self):
        self.bucket = os.environ["BUCKET"]
        self.id = os.environ["CODEBUILD_BUILD_ID"].split(":", 1)[1]
        self.idle_limit = int(os.environ.get("IDLE_SHUTDOWN_MINUTES", "15")) * 60
        self.s3 = boto3.client("s3")
        self.values = {}      # secrets: name -> value
        self.taken = set()    # task keys known to be claimed (by anyone)
        self.proc = None      # the running tool, killed when the lease runs out

    # ---- secrets ----
    def load_secrets(self):
        """False (after saying why) when a configured secret still holds the placeholder."""
        names = [n for n in os.environ.get("SECRETS", "").split(",") if n]
        if not names:
            return True
        path = os.environ["SECRETS_PATH"]
        r = boto3.client("ssm").get_parameters(Names=[path + n for n in names], WithDecryption=True)
        self.values = {p["Name"][len(path):]: p["Value"] for p in r["Parameters"]}
        unset = [n for n in names if self.values.get(n, PLACEHOLDER) == PLACEHOLDER]
        if unset:
            say("secrets not set yet: " + ", ".join(path + n for n in unset)
                + " — aws ssm put-parameter --name <name> --type SecureString --overwrite --value '...'")
            return False
        return True

    def masked(self, text):
        for v in self.values.values():
            text = text.replace(v, "***")
        return text

    # ---- the lease ----
    def expired(self):
        """True once the lease's time has passed; no lease yet (the Lambda writes it right after Start) = not expired."""
        try:
            lease = json.loads(self.s3.get_object(Bucket=self.bucket, Key=f"leases/{self.id}.json")["Body"].read())
        except self.s3.exceptions.NoSuchKey:
            return False
        return iso(now()) >= lease["until"]

    def watch_lease(self):
        """In the background: when the lease runs out, stop whatever runs and end the build."""
        while True:
            time.sleep(LEASE_CHECK_SECONDS)
            try:
                if self.expired():
                    say("::shutdown lease")
                    if self.proc:
                        self.proc.kill()
                    os._exit(0)
            except Exception as e:  # noqa: BLE001 - a failed check is retried, never fatal
                say(f"lease check failed: {type(e).__name__}: {e}")

    # ---- the queue ----
    def keys(self, prefix):
        out = []
        for page in self.s3.get_paginator("list_objects_v2").paginate(Bucket=self.bucket, Prefix=prefix):
            out += [o["Key"] for o in page.get("Contents", [])]
        return out

    def claim(self, key):
        """Take the task at key; False when another scanner (or a cancel) has it."""
        task_id = key[len("tasks/"):-len(".json")]
        body = json.dumps({"scanner": self.id, "started": iso(now())}).encode()
        try:
            self.s3.put_object(Bucket=self.bucket, Key=f"claims/{task_id}.json", Body=body,
                               ContentType="application/json", IfNoneMatch="*")
            return True
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code")
            if code == "PreconditionFailed":
                self.taken.add(key)
                return False
            if code == "ConditionalRequestConflict":   # a write of the same claim in flight: look again next round
                return False
            raise

    def next_task(self):
        """The oldest task nobody has taken, now claimed by this scanner; None when there is none."""
        for key in sorted(k for k in self.keys("tasks/") if k not in self.taken):
            if self.claim(key):
                self.taken.add(key)
                return json.loads(self.s3.get_object(Bucket=self.bucket, Key=key)["Body"].read())
        return None

    # ---- one task: run one tool ----
    def run(self, task):
        tid, started, command = task["id"], iso(now()), task["command"]
        say(f"::task {tid} start")
        say(f"::run {tid} {self.masked(command)}")
        output, size = os.path.join(WORK, "output.txt"), 0
        result = "error"
        try:
            with open(output, "w", encoding="utf-8") as out:
                self.proc = subprocess.Popen(["bash", "-lc", command], cwd=WORK, env=dict(os.environ, **self.values),
                                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace")
                for line in self.proc.stdout:
                    line = self.masked(line.rstrip("\n"))
                    say(f"::out {tid} {line}")
                    if size < OUTPUT_LIMIT:
                        out.write(line + "\n")
                        size += len(line) + 1
                code, self.proc = self.proc.wait(), None
            say(f"::done {tid} {code}")
            result = "pass" if code == 0 else "fail"
            self.s3.upload_file(output, self.bucket, f"reports/{tid}/output.txt", ExtraArgs={"ContentType": "text/plain; charset=utf-8"})
        except Exception as e:  # noqa: BLE001 - reported in the log, the scanner keeps going
            say(f"::out {tid} {self.masked(f'{type(e).__name__}: {e}')}")
        say(f"::task {tid} end {result}")
        claim = {"scanner": self.id, "started": started, "ended": iso(now()), "result": result, "command": command}
        self.s3.put_object(Bucket=self.bucket, Key=f"claims/{tid}.json", Body=json.dumps(claim).encode(),
                           ContentType="application/json")

    def main(self):
        if not self.load_secrets():
            say("::shutdown secrets")
            sys.exit(1)
        os.makedirs(WORK, exist_ok=True)
        self.taken = {"tasks/" + k[len("claims/"):] for k in self.keys("claims/")}   # taken or cancelled before
        threading.Thread(target=self.watch_lease, daemon=True).start()
        say("::ready")
        idle_since = time.monotonic()
        while True:
            task = self.next_task()
            if task:
                self.run(task)
                idle_since = time.monotonic()
            elif time.monotonic() - idle_since >= self.idle_limit:
                say("::shutdown idle")
                return
            else:
                time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    Scanner().main()
