"""
Create the demo S3 bucket. Run once, before Terraform.

WHY THIS IS NOT TERRAFORM
-------------------------
The bucket used to be a Terraform resource, which meant `terraform destroy`
deleted it -- and with it the 720 MB of staged GHCN/CEC data, the processed
pipeline output, the ML splits, and the Clarify reports. Rebuilding all of that
takes about 25 minutes and a dollar of Glue.

Teardown happens often in a teaching repo: after every class, and every time
the domain needs recreating. Coupling "tear down the compute" to "delete the
data" is the wrong default, so the bucket now lives OUTSIDE Terraform's
lifecycle. Terraform reads it as a data source and grants the execution role
access to it, but can never destroy it.

That means `terraform destroy` is now safe to run freely: it removes the Studio
domain, the Canvas reaper, the budgets and the IAM policies, and leaves every
dataset untouched.

Idempotent -- safe to re-run. Applies the same settings Terraform used to:
block all public access, enforce bucket-owner ownership, and AES256 encryption
at rest.

Usage:
    python 00-setup/create_bucket.py
    python 00-setup/create_bucket.py --bucket some-other-name
"""

import argparse
import sys

import boto3
from botocore.exceptions import ClientError

# Make the repo root importable so `shared.config` resolves no matter which
# directory this script is launched from.
import os as _os, sys as _sys
_root = _os.path.abspath(_os.path.dirname(__file__))
while not _os.path.isdir(_os.path.join(_root, "shared")) and _root != _os.path.dirname(_root):
    _root = _os.path.dirname(_root)
_sys.path.insert(0, _root)
from shared.config import add_common_args


def main() -> int:
    p = argparse.ArgumentParser(
        description="Create the demo S3 bucket (idempotent). Lives outside Terraform."
    )
    add_common_args(p, role=False)
    args = p.parse_args()

    s3 = boto3.Session(profile_name=args.profile, region_name=args.region).client("s3")
    b, region = args.bucket, args.region

    # ---- the bucket itself ------------------------------------------------
    try:
        s3.head_bucket(Bucket=b)
        print(f"bucket already exists: s3://{b}")
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code == "403":
            print(f"ERROR: s3://{b} exists but belongs to another account.")
            print("Pick a different SMDEMO_BUCKET in demo.env.")
            return 1
        if code not in ("404", "NoSuchBucket"):
            print(f"ERROR checking s3://{b}: {exc}")
            return 1
        # us-east-1 is the one region that rejects a LocationConstraint.
        kwargs = {"Bucket": b}
        if region != "us-east-1":
            kwargs["CreateBucketConfiguration"] = {"LocationConstraint": region}
        s3.create_bucket(**kwargs)
        print(f"created s3://{b} in {region}")

    # ---- the settings Terraform used to apply ----------------------------
    s3.put_public_access_block(
        Bucket=b,
        PublicAccessBlockConfiguration={
            "BlockPublicAcls": True,
            "IgnorePublicAcls": True,
            "BlockPublicPolicy": True,
            "RestrictPublicBuckets": True,
        },
    )
    print("  public access: fully blocked")

    s3.put_bucket_ownership_controls(
        Bucket=b,
        OwnershipControls={"Rules": [{"ObjectOwnership": "BucketOwnerEnforced"}]},
    )
    print("  object ownership: BucketOwnerEnforced")

    s3.put_bucket_encryption(
        Bucket=b,
        ServerSideEncryptionConfiguration={
            "Rules": [
                {"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}
            ]
        },
    )
    print("  encryption: AES256 at rest")

    print(f"\nReady. Next: cd terraform && terraform apply")
    print("Terraform reads this bucket as a data source and can never destroy it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
