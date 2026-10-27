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

    # Turn Canvas ON for this domain — it's the UI where Autopilot/AutoML jobs
    # are viewed (AWS moved the Autopilot UI into Canvas in Nov 2023). The Canvas
    # cost guard (canvas_reaper.tf) watches this domain, so idle apps get reaped.
    canvas_app_settings {
      workspace_settings {
        s3_artifact_path = "s3://${var.data_bucket_name}/canvas/"
      }
    }
  }

  # JupyterLab spaces need default_space_settings on the DOMAIN. Without this
  # block the "Create JupyterLab space" option is unavailable -- Studio has no
  # execution role or storage defaults to hand a new space, so it offers nothing
  # to create. Canvas still worked because canvas_app_settings above covers it,
  # which is exactly why the gap was easy to miss: one half of Studio worked.
  #
  # This is what Demo 3 (the serverless PySpark notebook) runs in.
  default_space_settings {
    execution_role = data.aws_iam_role.exec.arn

    # No sagemaker_image_arn: let SageMaker pick the current SageMaker
    # Distribution image, which is the one that ships the Glue PySpark kernel.
    # Pinning an ARN here means the kernel list silently ages out.
    jupyter_lab_app_settings {
      default_resource_spec {
        instance_type = "ml.t3.medium"
      }

      # SageMaker's OWN idle shutdown, which is the right tool for JupyterLab.
      #
      # The Canvas reaper deliberately does not touch JupyterLab: deleting a
      # notebook app kills the kernel and loses unsaved in-memory state. Native
      # idle shutdown is graceful by comparison -- it stops the app but the
      # space's files survive, so you reopen and your notebooks are there.
      #
      # It is not free to skip: ml.t3.medium is only ~$0.05/hr, but left running
      # a month that is ~$36 for an idle notebook.
      app_lifecycle_management {
        idle_settings {
          lifecycle_management = "ENABLED"
          # Two hours: long enough to survive a lunch break without killing a
          # session you are coming back to.
          idle_timeout_in_minutes = 120
          # Bounds on what a user may choose per-space in the Studio UI.
          min_idle_timeout_in_minutes = 60
          max_idle_timeout_in_minutes = 480
        }
      }
    }

    space_storage_settings {
      default_ebs_storage_settings {
        default_ebs_volume_size_in_gb = 20
        maximum_ebs_volume_size_in_gb = 100
      }
    }
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

    canvas_app_settings {
      workspace_settings {
        s3_artifact_path = "s3://${var.data_bucket_name}/canvas/"
      }
    }
  }
}
