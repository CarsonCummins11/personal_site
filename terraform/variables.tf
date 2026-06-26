variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "github_token" {
  type        = string
  sensitive   = true
  description = "GitHub PAT with repo write scope"
}

variable "repo_owner" {
  type    = string
  default = "CarsonCummins11"
}

variable "repo_name" {
  type    = string
  default = "personal_site"
}
