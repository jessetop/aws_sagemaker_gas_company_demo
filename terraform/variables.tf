variable "profile" {
  description = "AWS CLI profile to use."
  type        = string
  default     = "default"
}

variable "region" {
  description = "Region that holds the live SageMaker + Unified Studio domains."
  type        = string
  default     = "us-east-1"
}

variable "account_id" {
  description = "AWS account ID (used to build ARNs / bucket names)."
  type        = string
  default     = "000000000000"
}

variable "project_tag" {
  description = "Project tag applied to every resource for discovery + cleanup."
  type        = string
  default     = "sagemaker-unified-studio-demos"
}

variable "name_prefix" {
  description = "Prefix for every resource name Terraform creates. Keep this in step with SMDEMO_PREFIX in demo.env so the cleanup scripts find what Terraform made."
  type        = string
  default     = "roi-smdemo-gas"
}

variable "data_bucket_name" {
  description = "New in-region data bucket to hold the project dataset."
  type        = string
  default     = "roi-smdemo-000000000000-us-east-1"
}

variable "exec_role_name" {
  description = "Existing SageMaker execution role for the demo (created out-of-band). Terraform references it and grants it access to the new bucket; it does NOT recreate it."
  type        = string
  default     = "roi-smdemo-exec-role"
}

# ---- Pre-existing domains. Terraform only REFERENCES these; it never creates
#      or modifies a SageMaker or Unified Studio domain.
#
#      Both default to empty ON PURPOSE. The ids previously hardcoded here
#      (d-jjtgqqdxjtqe / dzd-b6xs075popdjhj) point at domains that no longer
#      exist — verified 2026-10-23: `list-domains` returns nothing in either
#      us-east-1 or us-east-2. Leaving dead ids as defaults makes a fresh apply
#      look like it is wired up when it is not.
#
#      The Canvas reaper does not need these: it runs with
#      WATCH_ALL_DOMAINS=true and enumerates whatever domains exist. ----------
variable "sagemaker_domain_id" {
  description = "Pre-existing SageMaker domain id, for outputs/reference only. Leave empty unless you have one; the reaper discovers domains itself."
  type        = string
  default     = ""
}

variable "datazone_domain_id" {
  description = "Pre-existing Unified Studio (DataZone) domain id — recorded for reference/outputs only. Leave empty unless you have one."
  type        = string
  default     = ""
}

# ---- Standalone SageMaker AI Studio domain ("old way" experience) -----------
variable "create_sagemaker_ai_domain" {
  description = "Create a standalone SageMaker AI Studio domain so the classic experience shows the project data. Not a Unified Studio."
  type        = bool
  default     = true
}

variable "sagemaker_ai_domain_name" {
  description = "Name for the standalone SageMaker AI Studio domain."
  type        = string
  default     = "roi-smdemo-gas-ai-studio"
}

variable "sagemaker_ai_user_profile" {
  description = "User profile created in the standalone domain."
  type        = string
  default     = "roi-smdemo-gas-user"
}

# ---- Canvas reaper knobs ----------------------------------------------------
variable "canvas_reaper_enabled" {
  description = "Whether to schedule the Canvas auto-kill Lambda."
  type        = bool
  default     = true
}

variable "canvas_reaper_schedule" {
  description = "EventBridge schedule expression for the reaper. Default: hourly."
  type        = string
  default     = "rate(1 hour)"
}

variable "canvas_max_idle_minutes" {
  description = "Delete a Canvas app after this many minutes with no user activity. Read from DescribeApp's LastUserActivityTimestamp, so an app in active use is NOT killed."
  type        = number
  default     = 60
}

variable "canvas_max_age_minutes" {
  description = "Hard cap: delete a Canvas app this many minutes after creation even if it still looks active. The backstop for a session left open on a second monitor. 0 disables. Keep it comfortably longer than your longest teaching block."
  type        = number
  default     = 600
}

variable "canvas_reaper_regions" {
  description = "Comma-separated regions the reaper sweeps. Canvas is region-scoped: the June 2026 overrun was in us-east-2, so list every region you might open Canvas in, not just the deploy region."
  type        = string
  default     = "us-east-1,us-east-2"
}

variable "canvas_reaper_dry_run" {
  description = "Log what the reaper would delete without deleting it. Useful for one sweep after changing thresholds."
  type        = bool
  default     = false
}

variable "kill_app_types" {
  description = "Comma-separated SageMaker AppTypes the reaper will delete. Canvas is the $50/day culprit; JupyterLab/KernelGateway intentionally excluded by default."
  type        = string
  default     = "Canvas"
}

# ---- Spend guardrails (see budget.tf) --------------------------------------
variable "budget_notification_email" {
  description = "Email for budget + cost-anomaly alerts. REQUIRED for any of the guardrails in budget.tf to be created; leave empty to skip them entirely."
  type        = string
  default     = ""
}

variable "daily_budget_usd" {
  description = "Daily total-spend alert threshold. A forgotten Canvas session (~$32-64/day) should trip this within a day rather than at month end."
  type        = number
  default     = 15
}

variable "sagemaker_monthly_budget_usd" {
  description = "Monthly SageMaker-only alert threshold. The whole demo series run end to end costs a few dollars, so this is deliberately far below the $218 June 2026 bill."
  type        = number
  default     = 40
}

variable "anomaly_alert_threshold_usd" {
  description = "Minimum absolute impact before a cost-anomaly alert is sent. Below this it is noise."
  type        = number
  default     = 10
}
