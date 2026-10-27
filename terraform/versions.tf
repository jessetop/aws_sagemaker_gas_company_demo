terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
  }

  # Local state by default. To share state, point this at one of the existing
  # tfstate buckets (e.g. demo-terraform-state-jat) — left local to keep this
  # self-contained.
}

provider "aws" {
  region  = var.region
  profile = var.profile

  default_tags {
    tags = {
      Project   = var.project_tag
      ManagedBy = "terraform"
      Module    = "sagemaker-demos-populate"
    }
  }
}
