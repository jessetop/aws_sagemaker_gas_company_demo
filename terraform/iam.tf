# Reference the EXISTING demo execution role — do not recreate it (it was made
# out-of-band on 2026-06-22 and is account-global, so it works in us-east-1 too).
data "aws_iam_role" "exec" {
  name = var.exec_role_name
}

# Grant that role read/write on the new in-region data bucket.
resource "aws_iam_role_policy" "exec_bucket_access" {
  name = "roi-smdemo-use1-bucket-access"
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

# ---- Canvas reaper Lambda execution role -----------------------------------
resource "aws_iam_role" "canvas_reaper" {
  name = "roi-smdemo-canvas-reaper"

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
  name = "roi-smdemo-canvas-reaper-policy"
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
        # Apps in any domain in this region (there are now two: the SMUS domain
        # and the standalone SageMaker AI domain).
        Resource = "arn:aws:sagemaker:${var.region}:${var.account_id}:app/*/*"
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
