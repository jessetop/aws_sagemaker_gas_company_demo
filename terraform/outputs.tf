output "data_bucket" {
  description = "In-region data bucket the project data is synced into."
  value       = data.aws_s3_bucket.data.bucket
}

output "exec_role_arn" {
  description = "Execution role granted access to the data bucket."
  value       = data.aws_iam_role.exec.arn
}

output "canvas_reaper_function" {
  description = "Name of the Canvas auto-kill Lambda (empty if disabled)."
  value       = var.canvas_reaper_enabled ? aws_lambda_function.canvas_reaper[0].function_name : ""
}

output "sagemaker_domain_id" {
  value = var.sagemaker_domain_id
}

output "sagemaker_ai_domain_id" {
  description = "Standalone SageMaker AI Studio domain (empty if not created)."
  value       = var.create_sagemaker_ai_domain ? aws_sagemaker_domain.ai[0].id : ""
}

output "sagemaker_ai_domain_url" {
  description = "Studio URL for the standalone SageMaker AI domain."
  value       = var.create_sagemaker_ai_domain ? aws_sagemaker_domain.ai[0].url : ""
}

output "datazone_domain_id" {
  value = var.datazone_domain_id
}
