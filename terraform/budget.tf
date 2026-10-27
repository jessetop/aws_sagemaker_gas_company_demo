# Spend guardrails.
#
# Context: June 2026 billed $218 for SageMaker, $202 of it a single Canvas
# session left running after class (USE2-Canvas:Session-Hrs). An account-wide
# $50 budget already existed and did not help, for two reasons worth being
# explicit about:
#
#   1. A budget NOTIFIES. It never stops spend. It is a smoke alarm, not a
#      sprinkler. The sprinkler is canvas_reaper.tf.
#   2. A single account-wide monthly budget is too coarse and too late. By the
#      time a $50 monthly threshold trips, a $50/day resource has already been
#      running for a day.
#
# So this file adds narrower, earlier alarms: a DAILY budget (a Canvas session
# trips it within hours, not weeks) and a SageMaker-specific monthly budget, in
# addition to whatever account-wide budget already exists.
#
# Cost of these guardrails: the first two budgets per account are free, then
# $0.02/day each. Cost Anomaly Detection is free.

locals {
  # Budgets are a global (us-east-1) service but the provider region does not
  # matter for them. Alerts go nowhere useful if this is empty, so every budget
  # resource is gated on it.
  budget_emails = var.budget_notification_email == "" ? [] : [var.budget_notification_email]
}

# ---- Daily total-spend budget ----------------------------------------------
# The point of a DAILY budget is speed. A forgotten $50/day app shows up here
# tomorrow instead of at month end.
resource "aws_budgets_budget" "daily_total" {
  count = var.budget_notification_email == "" ? 0 : 1

  name         = "${var.name_prefix}-daily-total"
  budget_type  = "COST"
  limit_amount = tostring(var.daily_budget_usd)
  limit_unit   = "USD"
  time_unit    = "DAILY"

  # Actual spend crossing the daily limit: something is running that should not be.
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = local.budget_emails
  }

  # Early warning at 50% so a demo day that is trending hot is visible before
  # it becomes a surprise.
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 50
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = local.budget_emails
  }
}

# ---- SageMaker-only monthly budget -----------------------------------------
# Scoped to the service that actually blew up, so it cannot be masked by a
# quiet month elsewhere in the account.
resource "aws_budgets_budget" "sagemaker_monthly" {
  count = var.budget_notification_email == "" ? 0 : 1

  name         = "${var.name_prefix}-sagemaker-monthly"
  budget_type  = "COST"
  limit_amount = tostring(var.sagemaker_monthly_budget_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  cost_filter {
    name   = "Service"
    values = ["Amazon SageMaker"]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = local.budget_emails
  }

  # FORECASTED is the one that would have caught June: two days into a $50/day
  # burn, the month-end projection is already far over budget.
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = local.budget_emails
  }
}

# ---- Cost anomaly detection -------------------------------------------------
# Free, and better than a fixed threshold for "this does not look like how you
# normally spend". Catches the next expensive service we have not thought of.
resource "aws_ce_anomaly_monitor" "sagemaker" {
  count = var.budget_notification_email == "" ? 0 : 1

  name              = "${var.name_prefix}-sagemaker-anomalies"
  monitor_type      = "DIMENSIONAL"
  monitor_dimension = "SERVICE"
}

resource "aws_ce_anomaly_subscription" "sagemaker" {
  count = var.budget_notification_email == "" ? 0 : 1

  name      = "${var.name_prefix}-anomaly-alerts"
  frequency = "DAILY"
  monitor_arn_list = [
    aws_ce_anomaly_monitor.sagemaker[0].arn,
  ]

  subscriber {
    type    = "EMAIL"
    address = var.budget_notification_email
  }

  # Only shout about anomalies worth a look; below this it is noise.
  threshold_expression {
    dimension {
      key           = "ANOMALY_TOTAL_IMPACT_ABSOLUTE"
      match_options = ["GREATER_THAN_OR_EQUAL"]
      values        = [tostring(var.anomaly_alert_threshold_usd)]
    }
  }
}
