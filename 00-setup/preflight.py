"""
Module 0 - Preflight: is this repo configured for YOUR AWS account?

Run this FIRST, before anything else in the series. It makes no changes and
costs nothing; it just answers "will the demos work here, and if not, which one
line do I have to edit?"

Two audiences, same check:

  * The instructor, before class, confirming the account still looks the way
    CLASS_PREP.md assumes.
  * Anyone who cloned this repo to try it in their own account. demo.env ships
    with the original author's account id and CLI profile baked in, so without
    this check the first failure is an opaque AccessDenied several steps deep
    rather than "edit these two lines."

Usage:
    python 00-setup/preflight.py
    python 00-setup/preflight.py --profile my-profile --region us-west-2

Exit code is 0 only if every required check passed.
"""

import argparse
import sys

import boto3
from botocore.exceptions import (
    ClientError,
    NoCredentialsError,
    ProfileNotFound,
    TokenRetrievalError,
)

# Make the repo root importable so `shared.config` resolves no matter which
# directory this script is launched from.
import os as _os, sys as _sys
_root = _os.path.abspath(_os.path.dirname(__file__))
while not _os.path.isdir(_os.path.join(_root, "shared")) and _root != _os.path.dirname(_root):
    _root = _os.path.dirname(_root)
_sys.path.insert(0, _root)
from shared import config
from shared.config import add_common_args

# The values demo.env ships with. If the caller's real identity disagrees with
# these, they almost certainly cloned the repo and have not edited demo.env yet.
AUTHOR_ACCOUNT = "029331796573"
AUTHOR_PROFILE = "roitraining"

OK = "  [ OK ]"
BAD = "  [FAIL]"
WARN = "  [warn]"


class Report:
    def __init__(self) -> None:
        self.failed: list[str] = []
        self.warned: list[str] = []

    def ok(self, msg: str) -> None:
        print(f"{OK} {msg}")

    def fail(self, msg: str, fix: str) -> None:
        print(f"{BAD} {msg}")
        print(f"         fix: {fix}")
        self.failed.append(msg)

    def warn(self, msg: str, note: str = "") -> None:
        print(f"{WARN} {msg}")
        if note:
            print(f"         note: {note}")
        self.warned.append(msg)


def check_profile(rep: Report, profile: str, region: str):
    """Can we even build a session with this profile?"""
    try:
        session = boto3.Session(profile_name=profile, region_name=region)
        session.get_credentials()
    except ProfileNotFound:
        available = ", ".join(boto3.Session().available_profiles) or "(none found)"
        rep.fail(
            f"AWS profile '{profile}' does not exist",
            f"set SMDEMO_PROFILE in demo.env to one of: {available}",
        )
        return None
    if session.get_credentials() is None:
        rep.fail(
            f"AWS profile '{profile}' has no usable credentials",
            f"run: aws configure --profile {profile}   (or aws sso login --profile {profile})",
        )
        return None
    rep.ok(f"AWS profile '{profile}' resolves")
    return session


def check_identity(rep: Report, session, expected_account: str) -> str | None:
    """Who are we really? This is the check that catches an unedited demo.env."""
    try:
        ident = session.client("sts").get_caller_identity()
    except (ClientError, NoCredentialsError, TokenRetrievalError) as exc:
        rep.fail(
            f"could not call sts:GetCallerIdentity ({exc.__class__.__name__})",
            "check your credentials are valid and not expired",
        )
        return None

    actual = ident["Account"]
    rep.ok(f"authenticated as {ident['Arn']}")

    if actual != expected_account:
        detail = (
            f"demo.env says SMDEMO_ACCOUNT={expected_account} but your credentials "
            f"are for account {actual}"
        )
        if expected_account == AUTHOR_ACCOUNT:
            rep.fail(
                detail + " -- this looks like a fresh clone",
                f"edit demo.env: set SMDEMO_ACCOUNT={actual}, set SMDEMO_PROFILE to "
                f"your profile, and set SMDEMO_BUCKET to a bucket name you own "
                f"(convention: roi-smdemo-{actual}-<region>)",
            )
        else:
            rep.fail(detail, f"set SMDEMO_ACCOUNT={actual} in demo.env")
        return actual

    rep.ok(f"account {actual} matches demo.env")
    return actual


def check_bucket(rep: Report, session, bucket: str, region: str) -> None:
    s3 = session.client("s3")
    try:
        s3.head_bucket(Bucket=bucket)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in ("404", "NoSuchBucket"):
            rep.fail(
                f"bucket s3://{bucket} does not exist",
                "create it with terraform/ (see terraform/README.md), or point "
                "SMDEMO_BUCKET at a bucket you already own",
            )
        elif code in ("403", "AccessDenied"):
            rep.fail(
                f"bucket s3://{bucket} exists but you cannot access it",
                "this bucket probably belongs to someone else -- set SMDEMO_BUCKET "
                "in demo.env to a bucket in your own account",
            )
        else:
            rep.fail(f"bucket s3://{bucket} check failed: {exc}", "see the error above")
        return
    rep.ok(f"bucket s3://{bucket} is reachable")

    # A bucket in the wrong region makes Glue/EMR jobs fail in confusing ways.
    loc = s3.get_bucket_location(Bucket=bucket).get("LocationConstraint") or "us-east-1"
    if loc != region:
        rep.fail(
            f"bucket is in {loc} but demo.env region is {region}",
            f"use a bucket in {region}, or set SMDEMO_REGION={loc}",
        )
    else:
        rep.ok(f"bucket region matches ({region})")


def check_role(rep: Report, session, role_arn: str) -> None:
    role_name = role_arn.rsplit("/", 1)[-1]
    try:
        session.client("iam").get_role(RoleName=role_name)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code == "NoSuchEntity":
            rep.fail(
                f"execution role '{role_name}' does not exist",
                "create it with terraform/ (see terraform/README.md)",
            )
        elif code == "AccessDenied":
            rep.warn(
                f"cannot read role '{role_name}' (iam:GetRole denied)",
                "the role may still exist and work; only the check is blocked",
            )
        else:
            rep.fail(f"role check failed: {exc}", "see the error above")
        return
    rep.ok(f"execution role '{role_name}' exists")


def check_public_data(rep: Report, session) -> None:
    """The NOAA bucket is the one dependency that is outside the user's account."""
    from botocore import UNSIGNED
    from botocore.client import Config

    try:
        public = session.client("s3", config=Config(signature_version=UNSIGNED))
        public.head_object(Bucket="noaa-ghcn-pds", Key="ghcnd-stations.txt")
    except Exception as exc:  # network, DNS, or a bucket policy change
        rep.warn(
            f"public NOAA GHCN bucket not reachable ({exc.__class__.__name__})",
            "00-setup/stage_dataset.py needs s3://noaa-ghcn-pds; check egress/proxy",
        )
        return
    rep.ok("public NOAA GHCN bucket (noaa-ghcn-pds) is reachable")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check this repo is configured for your AWS account. Makes no changes."
    )
    add_common_args(parser)
    args = parser.parse_args()

    print("=" * 68)
    print("Preflight - resolved configuration")
    print("=" * 68)
    print(f"  account : {config.ACCOUNT}")
    print(f"  region  : {args.region}")
    print(f"  profile : {args.profile}")
    print(f"  bucket  : {args.bucket}")
    print(f"  role    : {args.role_arn}")
    print(f"  prefix  : {config.PREFIX}*")
    print()

    rep = Report()

    session = check_profile(rep, args.profile, args.region)
    if session is None:
        # Nothing else can be checked without credentials.
        print()
        print("=" * 68)
        print("PREFLIGHT FAILED - fix the profile above, then re-run.")
        return 1

    check_identity(rep, session, config.ACCOUNT)
    check_bucket(rep, session, args.bucket, args.region)
    check_role(rep, session, args.role_arn)
    check_public_data(rep, session)

    print()
    print("=" * 68)
    if rep.failed:
        print(f"PREFLIGHT FAILED - {len(rep.failed)} problem(s):")
        for f in rep.failed:
            print(f"  - {f}")
        print()
        print("Edit demo.env (repo root) and re-run. Nothing was changed.")
        return 1
    if rep.warned:
        print(f"Preflight passed with {len(rep.warned)} warning(s). Safe to continue.")
        return 0
    print("Preflight passed. Run 00-setup/stage_dataset.py next.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
