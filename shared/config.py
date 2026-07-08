"""Single source of demo config — reads demo.env (repo root) with OS-env override.

Every module script calls :func:`add_common_args` so ``--profile`` / ``--region`` /
``--bucket`` / ``--role-arn`` all default to one place instead of being hardcoded
per file. Pass a flag to override for a one-off run; set an env var (or edit
``demo.env``) to change the default everywhere.

Resolution order (highest wins): CLI flag > OS env var > demo.env > built-in
fallback.

Usage in a script::

    from shared.config import add_common_args
    p = argparse.ArgumentParser()
    add_common_args(p)                 # --profile/--region/--bucket/--role-arn
    add_common_args(p, role=False)     # omit --role-arn for scripts that don't need it
    args = p.parse_args()
"""

import os


def _repo_root() -> str:
    # This file lives at <root>/shared/config.py.
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_env_file(path: str) -> dict:
    """Parse a KEY=VALUE .env file. Ignores blanks, comments, and inline quotes."""
    values: dict[str, str] = {}
    if not os.path.exists(path):
        return values
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            values[key.strip()] = val.strip().strip('"').strip("'")
    return values


_FILE = _load_env_file(os.path.join(_repo_root(), "demo.env"))


def _get(key: str, fallback: str) -> str:
    """OS env wins, then demo.env, then the built-in fallback."""
    return os.environ.get(key) or _FILE.get(key) or fallback


ACCOUNT = _get("SMDEMO_ACCOUNT", "029331796573")
REGION = _get("SMDEMO_REGION", "us-east-1")
PROFILE = _get("SMDEMO_PROFILE", "roitraining")
# Bucket follows the <prefix>-<account>-<region> convention unless pinned.
BUCKET = _get("SMDEMO_BUCKET", f"roi-smdemo-{ACCOUNT}-{REGION}")
ROLE_ARN = _get("SMDEMO_ROLE_ARN", f"arn:aws:iam::{ACCOUNT}:role/roi-smdemo-exec-role")


def add_common_args(parser, *, profile=True, region=True, bucket=True, role=True):
    """Add the standard AWS args to an argparse parser, defaulting from config.

    Each is optional now (previously several were required=True); omit the flag
    and the resolved config value is used.
    """
    if profile:
        parser.add_argument("--profile", default=PROFILE, help="AWS CLI profile")
    if region:
        parser.add_argument("--region", default=REGION, help="AWS region")
    if bucket:
        parser.add_argument("--bucket", default=BUCKET, help="Demo S3 bucket")
    if role:
        parser.add_argument("--role-arn", default=ROLE_ARN, help="SageMaker execution role ARN")
    return parser
