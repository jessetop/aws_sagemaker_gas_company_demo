# Standalone SageMaker AI Studio domain — the "old way" experience for the demo
# series. This is NOT a second Unified Studio: it's a plain SageMaker domain so
# the classic SageMaker AI Studio (Feature Store browser, Data Wrangler, Canvas,
# Autopilot, training, model registry) shows the project's in-region data.
#
# Region-scoped resources (the Feature Store group, model registry, training
# jobs) surface in this domain automatically; the exec role already has access to
# the data bucket (see iam.tf), so S3 data is browsable too.
#
# Cost: a domain at rest only carries a small EFS volume — real cost starts when
# a JupyterLab/Canvas app launches. The Canvas reaper (canvas_reaper.tf) watches
# THIS domain too, since it enumerates all domains in the region.

data "aws_vpc" "default" {
  count   = var.create_sagemaker_ai_domain ? 1 : 0
  default = true
}

data "aws_subnets" "default" {
  count = var.create_sagemaker_ai_domain ? 1 : 0
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default[0].id]
  }
}

resource "aws_sagemaker_domain" "ai" {
  count       = var.create_sagemaker_ai_domain ? 1 : 0
  domain_name = var.sagemaker_ai_domain_name
  auth_mode   = "IAM"
  # PublicInternetOnly avoids the VPC-endpoint/NAT setup that VpcOnly needs —
  # simplest working config for a classroom demo on the default VPC.
  app_network_access_type = "PublicInternetOnly"
  vpc_id                  = data.aws_vpc.default[0].id
  subnet_ids              = data.aws_subnets.default[0].ids

  default_user_settings {
    execution_role = data.aws_iam_role.exec.arn
  }

  # Keep teardown easy for a demo (no lingering EFS to clean up by hand).
  retention_policy {
    home_efs_file_system = "Delete"
  }
}

resource "aws_sagemaker_user_profile" "ai" {
  count             = var.create_sagemaker_ai_domain ? 1 : 0
  domain_id         = aws_sagemaker_domain.ai[0].id
  user_profile_name = var.sagemaker_ai_user_profile

  user_settings {
    execution_role = data.aws_iam_role.exec.arn
  }
}
