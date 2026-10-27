# Reference the EXISTING demo execution role — do not recreate it (it was made
# out-of-band on 2026-06-22 and is account-global, so it works in us-east-1 too).
data "aws_iam_role" "exec" {
  name = var.exec_role_name
}

# Grant that role read/write on the new in-region data bucket.
resource "aws_iam_role_policy" "exec_bucket_access" {
  name = "${var.name_prefix}-bucket-access"
  role = data.aws_iam_role.exec.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ListBucket"
        Effect = "Allow"
        # GetBucketAcl is required by SageMaker Feature Store's offline store.
        Action   = ["s3:ListBucket", "s3:GetBucketLocation", "s3:GetBucketAcl"]
        Resource = aws_s3_bucket.data.arn
      },
      {
        Sid      = "ObjectRW"
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
        Resource = "${aws_s3_bucket.data.arn}/*"
      }
    ]
  })
}

# Canvas needs its own managed permissions on the exec role to launch + run
# AutoML from the Canvas UI (where the Autopilot leaderboard is viewed).
resource "aws_iam_role_policy_attachment" "exec_canvas" {
  count      = var.create_sagemaker_ai_domain ? 1 : 0
  role       = data.aws_iam_role.exec.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSageMakerCanvasFullAccess"
}

# ---- Canvas reaper Lambda execution role -----------------------------------
resource "aws_iam_role" "canvas_reaper" {
  name = "${var.name_prefix}-canvas-reaper"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "canvas_reaper" {
  name = "${var.name_prefix}-canvas-reaper-policy"
  role = aws_iam_role.canvas_reaper.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "Logs"
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:${var.region}:${var.account_id}:*"
      },
      {
        Sid    = "ReapAppsAnyDomain"
        Effect = "Allow"
        Action = [
          "sagemaker:DescribeApp",
          "sagemaker:DeleteApp"
        ]
        # Apps in any domain in ANY region. Canvas is region-scoped and the
        # June 2026 overrun happened in us-east-2 while the guard was scoped to
        # us-east-1, so the reaper now sweeps several regions (see
        # var.canvas_reaper_regions) and needs permission in all of them.
        Resource = "arn:aws:sagemaker:*:${var.account_id}:app/*/*"
      },
      {
        # List ops don't accept a resource ARN; the reaper enumerates domains + apps.
        Sid    = "ListDomainWide"
        Effect = "Allow"
        Action = [
          "sagemaker:ListDomains",
          "sagemaker:ListApps",
          "sagemaker:ListUserProfiles",
          "sagemaker:ListSpaces"
        ]
        Resource = "*"
      }
    ]
  })
}

# ---- Glue Interactive Sessions (Demo 3: serverless PySpark notebook) -------
# A Studio notebook on the Glue PySpark kernel asks Glue to start a session and
# PASSES this role to it. Without iam:PassRole the kernel fails to start, and
# the error surfaces in the notebook as a session-creation failure rather than
# anything that names the missing permission.
#
# Scoped two ways: only this role may be passed, and only to Glue.
resource "aws_iam_role_policy" "exec_pass_role_to_glue" {
  name = "${var.name_prefix}-pass-role-to-glue"
  role = data.aws_iam_role.exec.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "PassSelfToGlueForInteractiveSessions"
        Effect   = "Allow"
        Action   = "iam:PassRole"
        Resource = data.aws_iam_role.exec.arn
        Condition = {
          StringEquals = {
            "iam:PassedToService" = "glue.amazonaws.com"
          }
        }
      },
      {
        # Interactive Sessions also need to tag the session it creates.
        Sid    = "GlueInteractiveSessionTagging"
        Effect = "Allow"
        Action = [
          "glue:TagResource",
          "glue:ListSessions",
          "glue:CancelStatement",
          "glue:GetStatement",
        ]
        Resource = "*"
      }
    ]
  })
}
