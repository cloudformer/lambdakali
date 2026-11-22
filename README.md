# lambdakali

**A serverless Kali command console on a Lambda Function URL — start a scanner (a CodeBuild instance), type shell
commands, they run on it. ≈ $0 while no scanner is on.** Part of [IdleFree](https://cloudformer.github.io/) · 中文：[README.zh.md](README.zh.md)

Your own Kali box that costs nothing when off. Start a scanner (an instance size, an image tier, a duration), then
type any shell command — it runs on the next free scanner and streams its output back. `/work` lasts the scanner's
life, so commands build on each other (`aws s3 cp …`, then `keepass2john`, then `john`). The gate is sign-in; there
is no target allowlist (a free shell cannot enforce one), so run only against what you may.

| | |
|---|---|
| Web console + API | one Lambda behind a Function URL; sign-in with a password or Cloudflare Access |
| Scanners | one CodeBuild build each, on a fresh Kali instance; take the queued commands (S3) in order, one at a time |
| Image tiers | `slim` (common tools, ~1 min to start) and `common` (~80% of the tools, 2–3 GB) — picked at Start, like the instance size; `full` is an opt-in build |
| A task | one shell command, run with `bash -lc` in `/work` |
| Output | streamed live, saved to S3 as `output.txt`, presigned download link |
| Secrets | SSM SecureStrings, set outside Terraform; reach commands as environment variables, masked as `***` |
| Permissions | the scanner's role is least-privilege; grant it more (e.g. read an S3 path) through `scanner_policy_statements` |
| Idle cost | ≈ $0 while no scanner is on (CodeBuild bills per minute while one is) |

## Example: test a KeePass vault's master password

With `scanner_policy_statements` granting `s3:GetObject` on your vault path, start a `common` scanner and run:

```
aws s3 cp s3://my-vaults/keepass/x.kdbx .
keepass2john x.kdbx > hash
john hash
```

Anything not in the image installs on demand — it is a root shell with apt and network:

```
apt-get update && apt-get install -y hydra && hydra -h
```

## Deploy

With the Terraform module — usage, variables, image tiers and outputs:
[cloudformer/infra/aws//modules/lambdakali](https://registry.terraform.io/modules/cloudformer/infra/aws/latest/submodules/lambdakali).
Docker must be running where Terraform runs: it builds each image tier (arm64) and pushes it to ECR (the `common`
tier is 2–3 GB, so the first apply takes a while).

## Run only what you may run

This runs arbitrary commands on a machine with your AWS role, reachable (behind sign-in) over the internet. Use it
on your own account, against hosts you own or have written permission to test. Keep sign-in on.

## License

MIT
