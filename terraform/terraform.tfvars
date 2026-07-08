# Live values for account 029331796573. These match the domains created
# 2026-07-06 in us-east-1. Terraform references the domains; it never creates one.
profile             = "roitraining"
region              = "us-east-1"
account_id          = "029331796573"
data_bucket_name    = "roi-smdemo-029331796573-us-east-1"
exec_role_name      = "roi-smdemo-exec-role"
sagemaker_domain_id = "d-jjtgqqdxjtqe"
datazone_domain_id  = "dzd-b6xs075popdjhj"

# Canvas cost guard
canvas_reaper_enabled   = true
canvas_reaper_schedule  = "rate(1 hour)"
canvas_max_idle_minutes = 60
kill_app_types          = "Canvas"
