# In-region data bucket for the whole series: raw/ staged sources, processed/
# pipeline output, ml/ train-val-test splits, clarify/ reports, canvas/.
#
# 00-setup/stage_dataset.py populates raw/ directly from the public sources
# (NOAA GHCN is itself an S3 bucket, so that part is a server-side copy). There
# is no cross-region sync step any more -- the previous comment here described
# copying from a us-east-2 bucket that no longer exists.
resource "aws_s3_bucket" "data" {
  bucket = var.data_bucket_name

  # Let `terraform destroy` remove the bucket even with objects in it.
  #
  # Normally this flag is dangerous and should not be set. It is correct HERE
  # for one specific reason: everything in this bucket is disposable and
  # re-creatable. 00-setup/stage_dataset.py rebuilds the whole raw/ tree from
  # public sources (NOAA, Census, CEC) in a few minutes, and processed/ and ml/
  # are derived from raw/. Nothing here is a system of record.
  #
  # Without it, teardown is a three-step dance -- empty the bucket by hand,
  # then destroy, then discover the state is now stale -- and a teardown that
  # is awkward is a teardown that gets skipped, which is how resources get left
  # running after class.
  force_destroy = true
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
