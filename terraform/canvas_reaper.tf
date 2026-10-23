# Package the reaper source into a zip for Lambda.
data "archive_file" "canvas_reaper" {
  type        = "zip"
  source_file = "${path.module}/lambda/canvas_reaper.py"
  output_path = "${path.module}/build/canvas_reaper.zip"
}

resource "aws_lambda_function" "canvas_reaper" {
  count = var.canvas_reaper_enabled ? 1 : 0

  function_name    = "${var.name_prefix}-canvas-reaper"
  role             = aws_iam_role.canvas_reaper.arn
  runtime          = "python3.12"
  handler          = "canvas_reaper.handler"
  filename         = data.archive_file.canvas_reaper.output_path
  source_code_hash = data.archive_file.canvas_reaper.output_base64sha256
  # Sweeping several regions and calling DescribeApp per app takes longer than
  # the single-region list-only version did.
  timeout     = 180
  memory_size = 128

  environment {
    variables = {
      WATCH_ALL_DOMAINS = "true" # covers both the SMUS domain and the AI domain
      DOMAIN_ID         = var.sagemaker_domain_id
      KILL_APP_TYPES    = var.kill_app_types
      # Canvas is region-scoped, so the reaper has to be told where to look.
      REAPER_REGIONS          = var.canvas_reaper_regions
      CANVAS_MAX_IDLE_MINUTES = tostring(var.canvas_max_idle_minutes)
      CANVAS_MAX_AGE_MINUTES  = tostring(var.canvas_max_age_minutes)
      DRY_RUN                 = var.canvas_reaper_dry_run ? "true" : "false"
    }
  }
}

resource "aws_cloudwatch_log_group" "canvas_reaper" {
  count             = var.canvas_reaper_enabled ? 1 : 0
  name              = "/aws/lambda/${var.name_prefix}-canvas-reaper"
  retention_in_days = 14
}

resource "aws_cloudwatch_event_rule" "canvas_reaper" {
  count               = var.canvas_reaper_enabled ? 1 : 0
  name                = "${var.name_prefix}-canvas-reaper"
  description         = "Periodically delete idle SageMaker Canvas apps (cost guard)."
  schedule_expression = var.canvas_reaper_schedule
}

resource "aws_cloudwatch_event_target" "canvas_reaper" {
  count     = var.canvas_reaper_enabled ? 1 : 0
  rule      = aws_cloudwatch_event_rule.canvas_reaper[0].name
  target_id = "canvas-reaper-lambda"
  arn       = aws_lambda_function.canvas_reaper[0].arn
}

resource "aws_lambda_permission" "canvas_reaper_events" {
  count         = var.canvas_reaper_enabled ? 1 : 0
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.canvas_reaper[0].function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.canvas_reaper[0].arn
}
