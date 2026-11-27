# The deployment calls the lambdakali module, which deploys a released lambdakali from PyPI and builds the Kali image
# tiers with Docker on this machine (Docker must be running; the common tier is 2-3 GB). Before a Registry release,
# use the local source line.
module "lambdakali" {
  # source  = "cloudformer/infra/aws//modules/lambdakali"  # stable: a released version
  # version = "0.2.0"
  source = "../../terraform-aws-infra/modules/lambdakali" # local: this repo's working-tree module

  project_name              = var.project_name
  http_auth                 = var.http_auth
  cloudflare_auth           = var.cloudflare_auth
  function_url_auth         = var.function_url_auth
  scanner_policy_statements = var.scanner_policy_statements
  secrets                   = var.secrets
  compute_type              = var.compute_type
  image_variants            = var.image_variants
  default_image             = var.default_image
  max_scanners              = var.max_scanners
  idle_shutdown_minutes     = var.idle_shutdown_minutes
  max_session_minutes       = var.max_session_minutes
  report_retention_days     = var.report_retention_days
  log_retention_days        = var.log_retention_days
  architecture              = var.architecture
  force_destroy             = var.force_destroy
  lambdakali_version        = var.lambdakali_version # set in the tfvars file; bump it per release, module untouched
}

output "console_url" {
  value = module.lambdakali.console_url
}

output "bucket" {
  value = module.lambdakali.bucket
}

output "secret_parameters" {
  value = module.lambdakali.secret_parameters
}
