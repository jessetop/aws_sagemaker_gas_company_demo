"""
Render the Data Wrangler .flow templates with your bucket, and upload them.

WHY THIS EXISTS
---------------
A Data Wrangler flow is JSON that Canvas imports. It cannot read demo.env, so
the S3 paths inside it have to be literal strings. That leaves two bad options
and one good one:

  - commit the author's bucket name  -> nobody else can import it
  - commit a placeholder             -> nobody can import it, including you
  - commit a placeholder and render it from demo.env  <- this

The committed .flow files carry `YOUR-BUCKET-NAME`. This script swaps in the
real bucket from shared.config, writes the rendered copies to `.rendered/`
(gitignored), and uploads them to s3://<bucket>/flows/ so Canvas can import
straight from S3.

Usage:
    python 01-data-prep/old-data-wrangler/build_flows.py
    python 01-data-prep/old-data-wrangler/build_flows.py --no-upload

Then in Canvas: Data Wrangler -> Data flows -> Import -> point at
s3://<bucket>/flows/gas_demand.flow
"""

import argparse
import json
import pathlib
import sys

import boto3

# Make the repo root importable so `shared.config` resolves no matter which
# directory this script is launched from.
import os as _os, sys as _sys
_root = _os.path.abspath(_os.path.dirname(__file__))
while not _os.path.isdir(_os.path.join(_root, "shared")) and _root != _os.path.dirname(_root):
    _root = _os.path.dirname(_root)
_sys.path.insert(0, _root)
from shared.config import add_common_args

HERE = pathlib.Path(_os.path.dirname(_os.path.abspath(__file__)))
PLACEHOLDER = "YOUR-BUCKET-NAME"
FLOWS = ["gas_demand.flow", "gas_demand_no_leak.flow"]


def main() -> int:
    p = argparse.ArgumentParser(
        description="Render the .flow templates with your bucket and upload them."
    )
    add_common_args(p, role=False)
    p.add_argument("--no-upload", action="store_true", help="Render locally only")
    args = p.parse_args()

    if PLACEHOLDER in args.bucket:
        print(f"ERROR: bucket is still the placeholder ({args.bucket}).")
        print("Copy demo.env.example to demo.env and set SMDEMO_BUCKET.")
        return 1

    out_dir = HERE / ".rendered"
    out_dir.mkdir(exist_ok=True)
    s3 = boto3.Session(profile_name=args.profile, region_name=args.region).client("s3")

    for name in FLOWS:
        src = HERE / name
        if not src.exists():
            print(f"  ! missing template {name}")
            continue
        text = src.read_text(encoding="utf-8")
        if PLACEHOLDER not in text:
            print(f"  ! {name} has no {PLACEHOLDER} to replace -- already rendered?")
        rendered = text.replace(PLACEHOLDER, args.bucket)

        # Fail loudly rather than uploading something Canvas will reject.
        try:
            doc = json.loads(rendered)
        except json.JSONDecodeError as exc:
            print(f"  ! {name} is not valid JSON after rendering: {exc}")
            return 1

        # Every node's inputs must appear EARLIER in the array or Canvas throws
        # KeyError: '<node-id>#default'. Cheap to check, expensive to debug live.
        seen = set()
        for node in doc["nodes"]:
            for inp in node.get("inputs", []):
                if inp["node_id"] not in seen:
                    print(f"  ! {name}: node {node['node_id']} references "
                          f"{inp['node_id']} before it is defined")
                    return 1
            seen.add(node["node_id"])

        dest = out_dir / name
        dest.write_text(rendered, encoding="utf-8")
        print(f"  rendered {name}  ({len(doc['nodes'])} nodes, dependency order OK)")

        if not args.no_upload:
            key = f"flows/{name}"
            s3.upload_file(str(dest), args.bucket, key)
            print(f"    -> s3://{args.bucket}/{key}")

    print()
    print("In Canvas: Data Wrangler -> Data flows -> Import -> from S3:")
    print(f"  s3://{args.bucket}/flows/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
