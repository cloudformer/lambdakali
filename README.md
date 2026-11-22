# lambdakali

**A Kali command-line console on a Lambda Function URL — scanners are CodeBuild instances you start and shut down
like machines, ≈ $0 while none is on.** Part of [IdleFree](https://cloudformer.github.io/) · 中文：[README.zh.md](README.zh.md)

Start a scanner (an instance size and a duration), then add tasks: a tool, a target, and arguments. Any free
scanner takes the next one; the console shows its output live and links the saved output when it finishes. Shut a
scanner down when done; it also shuts down by itself when its time is up or after 15 minutes without a task. Only
hosts on the allowlist can be targeted.

| | |
|---|---|
| Web console + API | one Lambda behind a Function URL; sign-in with a password or Cloudflare Access |
| Scanners | one CodeBuild build each, on a fresh Kali instance; take the queued tasks (S3) in order, one at a time |
| Image | Kali rolling plus a chosen set of tools, and the scanner; in your ECR |
| A task | a tool (installed in the image), a target (on the allowlist), and arguments with `{target}` |
| Output | shown live, saved to S3 as `output.txt`, presigned download link |
| Secrets | SSM SecureStrings, set outside Terraform; reach tools as environment variables, masked as `***` |
| Idle cost | ≈ $0 while no scanner is on (CodeBuild bills per minute while one is) |

## A task runs one tool, no shell

The scanner fills `{target}` into the arguments and runs the tool directly — no shell — so a target cannot start a
second command. Arguments with shell characters (`;` `&` `|` `` ` `` `$` `>` `<` `\`) are refused, and the target
must be a single host, `host:port` or URL on the allowlist.

```
nmap    scanme.example.com     -sV -p 1-1000 {target}
nikto   https://example.com/   -h {target}
sslscan example.com:443        {target}
```

## Deploy

With the Terraform module — usage, variables, tools and outputs:
[cloudformer/infra/aws//modules/lambdakali](https://registry.terraform.io/modules/cloudformer/infra/aws/latest/submodules/lambdakali).
Docker must be running where Terraform runs: it builds the Kali image and pushes it to ECR (it is large, so the
first apply takes a while).

## Run only what you may run

Running these tools against a host you are not authorized to test may be illegal. The allowlist (`allowed_targets`)
is checked before any task is queued; keep it to hosts you own or have written permission to test.

## License

MIT
