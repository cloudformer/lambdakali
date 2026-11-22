# lambdakali

**Lambda Function URL 上的 Kali 命令行控制台。扫描机是 CodeBuild 实例，像电脑一样手动开关，全部关机时 ≈ $0。**
[IdleFree](https://cloudformer.github.io/) 系列 · English: [README.md](README.md)

开一台扫描机（选机型和时长），然后添加任务：工具、目标、参数。哪台机器空了就接下一个；console 实时显示输出，
跑完给出保存的输出下载链接。用完点关机，时长用完或空闲 15 分钟也会自动关机。只有允许清单里的主机可以作为目标。

| | |
|---|---|
| 网页控制台 + API | 一个 Lambda，Function URL；用密码或 Cloudflare Access 登录 |
| 扫描机 | 每台一个 CodeBuild build，新的 Kali 实例；按顺序领取队列（S3）里的任务，一次一个 |
| 镜像 | Kali rolling 加选定的工具，以及扫描脚本；放在你的 ECR |
| 一个任务 | 一个工具（镜像里装好的）、一个目标（允许清单里的）、带 `{target}` 的参数 |
| 输出 | 实时显示，保存到 S3 的 `output.txt`，预签名下载链接 |
| 密钥 | SSM SecureString，在 Terraform 之外设置；以环境变量传给工具，输出里显示为 `***` |
| 空闲费用 | 全部关机时 ≈ $0（CodeBuild 按开机的分钟计费） |

## 一个任务只跑一个工具，不经过 shell

扫描机把 `{target}` 填进参数，直接运行工具，不经过 shell，所以目标无法启动第二条命令。参数里带 shell 字符
（`;` `&` `|` `` ` `` `$` `>` `<` `\`）会被拒绝；目标必须是允许清单里的单个主机、`host:port` 或 URL。

```
nmap    scanme.example.com     -sV -p 1-1000 {target}
nikto   https://example.com/   -h {target}
sslscan example.com:443        {target}
```

## 部署

用 Terraform module，用法、变量、工具和输出见
[cloudformer/infra/aws//modules/lambdakali](https://registry.terraform.io/modules/cloudformer/infra/aws/latest/submodules/lambdakali)。
运行 Terraform 的机器上要开着 Docker：它会构建 Kali 镜像并推到 ECR（镜像较大，第一次 apply 会比较久）。

## 只运行你有权运行的目标

对未经授权的主机运行这些工具可能违法。允许清单（`allowed_targets`）在任务入队前检查；只放你自己的，或有书面授权的主机。

## License

MIT
