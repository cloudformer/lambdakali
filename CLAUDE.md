# lambdakali — working notes for Claude

**This project is an IdleFree app** (cloudformer.github.io): a Kali command-line console, ≈ $0 when idle. Sister app
of lambdazap — the same scanners, queue, leases and page; its task is tool + target + arguments instead of a URL and
a mode. Not an AWS service behind its client: no driver, no compatibility tests.

- `client/` is the pip package `lambdakali`: `lambdakali/server/` = the Lambda (web console `index.html` + API,
  handler `lambdakali.server.lambda_function.lambda_handler`); `lambdakali/image/` = the scan image's build context
  (`Dockerfile`: Kali rolling + `APT_TOOLS`; `scan.py` installed as `lambdakali-scan`, the scanner loop).
- Deployment: the Registry module cloudformer/infra/aws//modules/lambdakali installs a released lambdakali from PyPI,
  builds the image with Docker, pushes it to ECR, and creates the CodeBuild project (component codebuild_project).
  Its README is the usage docs; this README only links to it.
- A scanner is one CodeBuild build, started from the page with a size and a lease (`leases/<scanner id>.json`, +1h
  from the page, at most `max_session_minutes` = the build timeout), stopped from the page, by the lease or by idle
  shutdown. Tasks are one queue, `tasks/<task id>.json`; a scanner takes a task by creating `claims/<task id>.json`
  with `If-None-Match: *` and rewrites it with the result.
- A task is {tool, target, args}. The Lambda checks the tool is in `TOOLS`, the target is on the allowlist, and args
  hold `{target}` and no shell characters. The scanner runs `[tool, *shlex.split(args with {target} filled in)]`
  with NO shell: a target cannot inject a second command. The tool must also be installed in the image — keep
  `TOOLS` (the module variable) and the Dockerfile's `APT_TOOLS` in step.
- Log contract between the image and the page (a task's lines carry its id): `::ready`, `::task <id> start|end
  <result>`, `::run <id> <command>`, `::out <id> <text>`, `::done <id> <exit code>`, `::shutdown <idle|lease|secrets>`.
  Output file: `reports/<task id>/output.txt`. result = pass (exit 0) | fail (other) | error (could not run).
- The page uses the idlefree console shell (the CSS block shared with s3rds and the other consoles), unchanged.
- Tests: `python3 -m pytest tests -q`, fakes for CodeBuild, CloudWatch Logs, S3 and SSM; no AWS, no Docker.
- Frank runs every command (git, tags, PyPI, terraform). Versions are Frank's call. English in code and docs.
