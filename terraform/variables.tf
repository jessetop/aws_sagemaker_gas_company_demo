variable "profile" {
  description = "AWS CLI profile to use."
  type        = string
  default     = "roitraining"
}

variable "region" {
  description = "Region that holds the live SageMaker + Unified Studio domains."
  type        = string
  default     = "us-east-1"
}

variable "account_id" {
  description = "AWS account ID (used to build ARNs / bucket names)."
  type        = string
  default     = "029331796573"
}

variable "project_tag" {
  description = "Project tag applied to every resource for discovery + cleanup."
  type        = string
  default     = "sagemaker-unified-studio-demos"
}

variable "data_bucket_name" {
  description = "New in-region data bucket to hold the project dataset."
  type        = string
  default     = "roi-smdemo-029331796573-us-east-1"
}

variable "exec_role_name" {
  description = "Existing SageMaker execution role for the demo (created out-of-band). Terraform references it and grants it access to the new bucket; it does NOT recreate it."
  type        = string
  default     = "roi-smdemo-exec-role"
}

# ---- The live domains. Terraform only REFERENCES these; it never creates or
#      modifies a SageMaker or Unified Studio domain. -------------------------
variable "sagemaker_domain_id" {
  description = "Existing SageMaker domain the Canvas reaper watches."
  type        = string
  default     = "d-jjtgqqdxjtqe"
}

variable "datazone_domain_id" {
  description = "Existing Unified Studio (DataZone) domain — recorded for reference/outputs only."
  type        = string
  default     = "dzd-b6xs075popdjhj"
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
  default     = "roi-smdemo-ai-studio"
}

variable "sagemaker_ai_user_profile" {
  description = "User profile created in the standalone domain."
  type        = string
  default     = "roi-smdemo-user"
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
  description = "Delete a Canvas app after this many minutes of no user activity (falls back to age if activity is unknown)."
  type        = number
  default     = 60
}

variable "kill_app_types" {
  description = "Comma-separated SageMaker AppTypes the reaper will delete. Canvas is the $50/day culprit; JupyterLab/KernelGateway intentionally excluded by default."
  type        = string
  default     = "Canvas"
}
