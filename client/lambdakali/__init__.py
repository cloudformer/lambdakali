"""lambdakali — a serverless Kali command console on a Lambda Function URL; scanners are CodeBuild instances started
and shut down from the page, running shell commands you type from one queue. ≈ $0 while none is on.

lambdakali.server is the Lambda (the web console and its API); lambdakali/image is the scan image's build context
(Kali rolling, the tier chosen by a build arg, + the scanner loop). The Terraform module
cloudformer/infra/aws//modules/lambdakali deploys both from this package.
"""

__version__ = "0.1.5"
