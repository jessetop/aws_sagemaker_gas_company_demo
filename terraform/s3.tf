# In-region data bucket for the whole series: raw/ staged sources, processed/
# pipeline output, ml/ train-val-test splits, clarify/ reports, canvas/.
#
# 00-setup/stage_dataset.py populates raw/ directly from the public sources
# (NOAA GHCN is itself an S3 bucket, so that part is a server-side copy). There
# is no cross-region sync step any more -- the previous comment here described
# copying from a us-east-2 bucket that no longer exists.
resource "aws_s3_bucket" "data" {
  bucket = var.data_bucket_name
}

resource "aws_s3_bucket_public_access_block" "data" {
  bucket                  = aws_s3_bucket.data.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "data" {
  bucket = aws_s3_bucket.data.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "data" {
  bucket = aws_s3_bucket.data.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}
