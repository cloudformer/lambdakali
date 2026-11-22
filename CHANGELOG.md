# Changelog

## 0.1.2

- Sign-in and the console CSS now come from the shared packages `idlefree-auth` and `idlefree-ui` instead of a
  copy carried here; behavior and the page are unchanged.

## 0.1.1

- Reworked into a serverless Kali **command console**: a task is now a free-form shell command (run with `bash -lc`
  in `/work`, which lasts the scanner's life, so commands build on each other) instead of a fixed tool + target +
  args. No target allowlist — the gate is sign-in; grant a command extra IAM via the module's
  `scanner_policy_statements`.
- Image tiers picked at Start, like the instance size: `slim` (common tools) and `common` (~80% of the tools) are
  built and offered; `full` (kali-linux-headless) is an opt-in build. Anything else installs on demand with apt.
  The image carries the AWS CLI and `john`/`keepass2john`.

## 0.1.0

- First release (tool + target + arguments form); superseded by the 0.1.1 command console.
