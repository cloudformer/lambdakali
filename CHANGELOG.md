# Changelog

## 0.1.0

- First release: a web console on a Lambda Function URL starts and shuts down scanners (CodeBuild instances with a
  Kali rolling image; a size and a duration each, +1h from the page, up to `max_scanners` at once) and adds tasks —
  a tool (installed in the image), a target (on the allowlist), and arguments with `{target}` — to one queue. A free
  scanner takes the next task (an S3 claim) and runs the tool with no shell, its output live and saved to S3. A
  scanner shuts down by itself when its time is up or after `idle_shutdown_minutes` without a task.
