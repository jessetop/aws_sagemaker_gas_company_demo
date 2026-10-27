# The demo data bucket is deliberately NOT managed by Terraform.
#
# It used to be an aws_s3_bucket resource, which meant `terraform destroy` took
# the bucket with it -- and with the bucket went 720 MB of staged GHCN/CEC data,
# the processed pipeline output, the ML splits and the Clarify reports. About 25
# minutes and a dollar of Glue to rebuild.
#
# Teardown happens constantly in a teaching repo: after every class, and every
# time the Studio domain needs recreating. Tying "tear down the compute" to
# "delete the data" is the wrong default. So the bucket now lives outside
# Terraform's lifecycle entirely:
#
#   create it   -> python 00-setup/create_bucket.py   (idempotent, once)
#   reference it -> the data source below
#   destroy it  -> never, by Terraform. Only by hand, or by
#                  cleanup/cleanup.ps1 -IncludeBucket if you really mean it.
#
# `terraform destroy` is therefore safe to run freely now. It removes the Studio
# domain, the Canvas reaper, the budgets and the IAM policies, and leaves every
# dataset where it is.
#
# NOTE: prevent_destroy was the obvious alternative and is the wrong tool here.
# It does not protect the data so much as make `terraform destroy` fail
# outright, which blocks teardown of everything ELSE in the stack -- including
# the things that actually cost money.
data "aws_s3_bucket" "data" {
  bucket = var.data_bucket_name
}
