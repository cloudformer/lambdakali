# ---- deploy credentials ----
variable "region" {
  type    = string
  default = "us-east-2"
}

variable "aws_profile" {
  description = "Local AWS CLI profile; \"\" = default credential chain"
  type        = string
  default     = ""
}

variable "assume_role_arn" {
  description = "Deploy role to assume; \"\" = none. Pick this OR aws_profile."
  type        = string
  default     = ""

  validation {
    condition     = !(var.assume_role_arn != "" && var.aws_profile != "")
    error_message = "Set either aws_profile or assume_role_arn, not both."
  }
}

variable "env" {
  type    = string
  default = "dev"
}

variable "project_name" {
  type    = string
  default = "lambdakali"
}

# ---- extra permissions for a command (e.g. read a vault path) ----
variable "scanner_policy_statements" {
  description = "Extra IAM statements for every scanner's role; [] = none. e.g. read your kdbx: [{Effect=\"Allow\",Action=[\"s3:GetObject\"],Resource=\"arn:aws:s3:::my-vaults/*\"}]"
  type        = any
  default     = []
}

variable "http_auth" {
  type = object({
    enabled  = bool
    username = optional(string, "")
    password = optional(string, "")
  })
  default   = { enabled = false }
  sensitive = true
}

variable "cloudflare_auth" {
  type = object({
    enabled = bool
    team    = optional(string, "")
    aud     = optional(string, "")
  })
  default = { enabled = false }
}

variable "function_url_auth" {
  type    = string
  default = "NONE"
}

variable "secrets" {
  description = "Secret names a command may use (e.g. [\"API_TOKEN\"]); set each value with aws ssm put-parameter after apply, reaches commands as $NAME"
  type        = list(string)
  default     = []
}

variable "compute_type" {
  type    = string
  default = "BUILD_GENERAL1_SMALL"
}

variable "image_variants" {
  description = "Kali image tiers to build and offer: slim, common, full"
  type        = list(string)
  default     = ["slim", "common"]
}

variable "default_image" {
  type    = string
  default = "common"
}

variable "max_scanners" {
  type    = number
  default = 2
}

variable "idle_shutdown_minutes" {
  type    = number
  default = 15
}

variable "max_session_minutes" {
  type    = number
  default = 480
}

variable "report_retention_days" {
  type    = number
  default = 30
}

variable "log_retention_days" {
  type    = number
  default = 14
}

variable "architecture" {
  type    = string
  default = "arm64"
}

variable "force_destroy" {
  type    = bool
  default = true
}

variable "lambdakali_version" {
  description = "The lambdakali release to deploy from PyPI. Bump this per release during testing; the module is not touched."
  type        = string
  default     = "0.1.5"
}
