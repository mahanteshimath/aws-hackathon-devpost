"""One-command AWS deployment for Crayon Cinema (idempotent - safe to re-run).

Creates / updates, in your AWS account and region (credentials from .env or your AWS profile):
  - S3 bucket (private, encrypted, 30-day lifecycle)          stories, cut-outs, narration
  - Bedrock Guardrail (kid-safe content, PII blocking)         applied to every model input/output
  - IAM role (least privilege)                                 for the Lambda function
  - Lambda function (Python 3.12, arm64) + public Function URL TV app, phone app, API, async story jobs
  - Optional AWS Budget alarm                                  if BUDGET_EMAIL is set

    .venv/bin/python infra/deploy.py            # deploy
    .venv/bin/python infra/deploy.py --skip-build   # config-only update

Outputs are written to infra/outputs.json (git-ignored).
"""

from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from crayon.config import settings  # noqa: E402  (loads .env)

import boto3  # noqa: E402
from botocore.exceptions import ClientError  # noqa: E402

NAME = "crayon-cinema"
BUILD = ROOT / "build" / "lambda"
OUTPUTS = ROOT / "infra" / "outputs.json"

cfg = settings()
session = boto3.session.Session(region_name=cfg.region)
REGION = session.region_name
ACCOUNT = session.client("sts").get_caller_identity()["Account"]
BUCKET = os.environ.get("CRAYON_BUCKET") or f"{NAME}-{ACCOUNT}-{REGION}"


def log(msg: str) -> None:
    print(f"  • {msg}", flush=True)


# ------------------------------------------------------------------ S3
def ensure_bucket() -> None:
    s3 = session.client("s3")
    try:
        s3.head_bucket(Bucket=BUCKET)
        log(f"bucket {BUCKET} exists")
    except ClientError:
        kwargs = {"Bucket": BUCKET}
        if REGION != "us-east-1":
            kwargs["CreateBucketConfiguration"] = {"LocationConstraint": REGION}
        s3.create_bucket(**kwargs)
        log(f"created bucket {BUCKET}")
    s3.put_public_access_block(
        Bucket=BUCKET,
        PublicAccessBlockConfiguration={k: True for k in ("BlockPublicAcls", "IgnorePublicAcls", "BlockPublicPolicy", "RestrictPublicBuckets")},
    )
    s3.put_bucket_encryption(
        Bucket=BUCKET,
        ServerSideEncryptionConfiguration={"Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]},
    )
    s3.put_bucket_lifecycle_configuration(
        Bucket=BUCKET,
        LifecycleConfiguration={
            "Rules": [
                {"ID": "expire-everything-30d", "Status": "Enabled", "Filter": {"Prefix": ""}, "Expiration": {"Days": 30}},
                {"ID": "drawings-1d", "Status": "Enabled", "Filter": {"Prefix": "drawings/"}, "Expiration": {"Days": 1}},
            ]
        },
    )


# ------------------------------------------------------------------ Guardrail
def ensure_guardrail() -> tuple[str, str]:
    bedrock = session.client("bedrock")
    gname = f"{NAME}-kids"
    existing = next((g for g in bedrock.list_guardrails()["guardrails"] if g["name"] == gname), None)
    if existing:
        gid = existing["id"]
        versions = [g["version"] for g in bedrock.list_guardrails(guardrailIdentifier=gid)["guardrails"] if g["version"] != "DRAFT"]
        version = max(versions, key=int) if versions else bedrock.create_guardrail_version(guardrailIdentifier=gid)["version"]
        log(f"guardrail {gname} exists ({gid} v{version})")
        return gid, version

    filters = [
        {"type": t, "inputStrength": "HIGH", "outputStrength": "HIGH"}
        for t in ("SEXUAL", "VIOLENCE", "HATE", "INSULTS", "MISCONDUCT")
    ] + [{"type": "PROMPT_ATTACK", "inputStrength": "HIGH", "outputStrength": "NONE"}]
    resp = bedrock.create_guardrail(
        name=gname,
        description="Keeps Crayon Cinema stories gentle and age-appropriate for children aged 3-8.",
        contentPolicyConfig={"filtersConfig": filters},
        topicPolicyConfig={
            "topicsConfig": [
                {
                    "name": "ScaryContent",
                    "definition": "Frightening, violent, gory or threatening situations, villains hurting someone, death, or horror themes.",
                    "examples": ["The monster ate the children.", "The dragon burned the village and everyone screamed."],
                    "type": "DENY",
                },
                {
                    "name": "PersonalDetails",
                    "definition": "Requests for or mentions of a child's home address, school name, phone number or other identifying details.",
                    "examples": ["What school do you go to?", "Tell me where you live."],
                    "type": "DENY",
                },
            ]
        },
        sensitiveInformationPolicyConfig={
            "piiEntitiesConfig": [{"type": t, "action": "BLOCK"} for t in ("ADDRESS", "PHONE", "EMAIL")]
        },
        blockedInputMessaging="Let's draw something else!",
        blockedOutputsMessaging="Let's make a different story!",
    )
    gid = resp["guardrailId"]
    version = bedrock.create_guardrail_version(guardrailIdentifier=gid, description="hackathon")["version"]
    log(f"created guardrail {gname} ({gid} v{version})")
    return gid, version


# ------------------------------------------------------------------ IAM
def ensure_role(guardrail_id: str) -> str:
    iam = session.client("iam")
    role_name = f"{NAME}-lambda"
    trust = {
        "Version": "2012-10-17",
        "Statement": [{"Effect": "Allow", "Principal": {"Service": "lambda.amazonaws.com"}, "Action": "sts:AssumeRole"}],
    }
    try:
        arn = iam.get_role(RoleName=role_name)["Role"]["Arn"]
        log(f"role {role_name} exists")
        created = False
    except iam.exceptions.NoSuchEntityException:
        arn = iam.create_role(RoleName=role_name, AssumeRolePolicyDocument=json.dumps(trust))["Role"]["Arn"]
        log(f"created role {role_name}")
        created = True
    fn_arn = f"arn:aws:lambda:{REGION}:{ACCOUNT}:function:{NAME}"
    statements = [
        {"Effect": "Allow", "Action": ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"], "Resource": "*"},
        {"Effect": "Allow", "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"], "Resource": f"arn:aws:s3:::{BUCKET}/*"},
        {"Effect": "Allow", "Action": ["s3:ListBucket"], "Resource": f"arn:aws:s3:::{BUCKET}"},
        {
            "Effect": "Allow",
            "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream", "bedrock:Converse", "bedrock:ConverseStream"],
            "Resource": [
                "arn:aws:bedrock:*::foundation-model/*",
                f"arn:aws:bedrock:*:{ACCOUNT}:inference-profile/*",
            ],
        },
        {"Effect": "Allow", "Action": ["bedrock:ApplyGuardrail"], "Resource": f"arn:aws:bedrock:{REGION}:{ACCOUNT}:guardrail/{guardrail_id}"},
        {"Effect": "Allow", "Action": ["polly:SynthesizeSpeech"], "Resource": "*"},
        {"Effect": "Allow", "Action": ["lambda:InvokeFunction"], "Resource": fn_arn},
        {
            "Effect": "Allow",
            "Action": ["bedrock-agentcore:InvokeAgentRuntime", "bedrock-agentcore:CreateEvent", "bedrock-agentcore:RetrieveMemoryRecords"],
            "Resource": f"arn:aws:bedrock-agentcore:{REGION}:{ACCOUNT}:*",
        },
    ]
    iam.put_role_policy(RoleName=role_name, PolicyName=f"{NAME}-inline", PolicyDocument=json.dumps({"Version": "2012-10-17", "Statement": statements}))
    if created:
        log("waiting for IAM propagation…")
        time.sleep(12)
    return arn


# ------------------------------------------------------------------ build
def build_zip() -> bytes:
    if BUILD.exists():
        shutil.rmtree(BUILD)
    BUILD.mkdir(parents=True)
    uv = shutil.which("uv") or str(ROOT / ".tools" / "bin" / "uv")
    log("installing Linux arm64 dependencies…")
    subprocess.run(
        [uv, "pip", "install", "--quiet", "--target", str(BUILD), "--python-platform", "aarch64-manylinux2014",
         "--python-version", "3.12", "--only-binary", ":all:", "-r", str(ROOT / "backend" / "requirements.txt")],
        check=True,
    )
    shutil.copytree(ROOT / "backend" / "crayon", BUILD / "crayon", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy(ROOT / "backend" / "lambda_handler.py", BUILD / "lambda_handler.py")
    shutil.copytree(ROOT / "web", BUILD / "web")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in BUILD.rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts and not path.name.endswith(".pyc"):
                zf.write(path, path.relative_to(BUILD))
    data = buf.getvalue()
    log(f"lambda package {len(data) / 1e6:.1f} MB")
    return data


# ------------------------------------------------------------------ Lambda
def ensure_function(role_arn: str, guardrail: tuple[str, str], package: bytes | None) -> str:
    lam = session.client("lambda")
    env = {
        "CRAYON_MODE": "aws",
        "CRAYON_STORAGE": "s3",
        "CRAYON_BUCKET": BUCKET,
        "CRAYON_ROOT": "/var/task",
        "CRAYON_WEB_DIR": "/var/task/web",
        "CRAYON_DATA_DIR": "/tmp/crayon",
        "GUARDRAIL_ID": guardrail[0],
        "GUARDRAIL_VERSION": guardrail[1],
        **cfg.model_env(),
        "AGENTCORE_RUNTIME_ARN": cfg.agentcore_runtime_arn,
        "AGENTCORE_MEMORY_ID": cfg.agentcore_memory_id,
        "CRAYON_DAILY_LIMIT": os.environ.get("CRAYON_DAILY_LIMIT", "150"),
    }
    common = dict(
        Role=role_arn,
        Handler="lambda_handler.handler",
        Runtime="python3.12",
        Timeout=900,
        MemorySize=2048,
        Environment={"Variables": env},
    )
    code_key = f"deploy/{NAME}-{int(time.time())}.zip"
    if package is not None:
        session.client("s3").put_object(Bucket=BUCKET, Key=code_key, Body=package)
    try:
        lam.get_function(FunctionName=NAME)
        if package is not None:
            lam.update_function_code(FunctionName=NAME, S3Bucket=BUCKET, S3Key=code_key, Architectures=["arm64"])
            lam.get_waiter("function_updated_v2").wait(FunctionName=NAME)
        lam.update_function_configuration(FunctionName=NAME, **common)
        lam.get_waiter("function_updated_v2").wait(FunctionName=NAME)
        log(f"updated function {NAME}")
    except lam.exceptions.ResourceNotFoundException:
        if package is None:
            raise SystemExit("function does not exist yet - run without --skip-build")
        for attempt in range(5):
            try:
                lam.create_function(FunctionName=NAME, Code={"S3Bucket": BUCKET, "S3Key": code_key}, Architectures=["arm64"], **common)
                break
            except lam.exceptions.InvalidParameterValueException as exc:  # role not yet assumable
                if attempt == 4:
                    raise
                log(f"waiting for role ({exc.response['Error']['Message'][:60]}…)")
                time.sleep(8)
        lam.get_waiter("function_active_v2").wait(FunctionName=NAME)
        log(f"created function {NAME}")

    try:
        url = lam.get_function_url_config(FunctionName=NAME)["FunctionUrl"]
    except lam.exceptions.ResourceNotFoundException:
        url = lam.create_function_url_config(FunctionName=NAME, AuthType="NONE")["FunctionUrl"]
        log("created function URL")
    # Since Oct 2025 a public function URL needs both statements.
    for sid, kwargs in (
        ("PublicUrlInvoke", {"Action": "lambda:InvokeFunctionUrl", "FunctionUrlAuthType": "NONE"}),
        ("PublicUrlInvokeFunction", {"Action": "lambda:InvokeFunction", "InvokedViaFunctionUrl": True}),
    ):
        try:
            lam.add_permission(FunctionName=NAME, StatementId=sid, Principal="*", **kwargs)
        except lam.exceptions.ResourceConflictException:
            pass
    return url.rstrip("/")


# ------------------------------------------------------------------ Budget
def ensure_budget() -> None:
    email = os.environ.get("BUDGET_EMAIL", "").strip()
    if not email:
        log("BUDGET_EMAIL not set - skipping budget alarm (recommended!)")
        return
    budgets = session.client("budgets", region_name="us-east-1")
    try:
        budgets.create_budget(
            AccountId=ACCOUNT,
            Budget={"BudgetName": f"{NAME}-monthly", "BudgetLimit": {"Amount": os.environ.get("BUDGET_USD", "25"), "Unit": "USD"},
                    "TimeUnit": "MONTHLY", "BudgetType": "COST"},
            NotificationsWithSubscribers=[
                {"Notification": {"NotificationType": "ACTUAL", "ComparisonOperator": "GREATER_THAN", "Threshold": pct, "ThresholdType": "PERCENTAGE"},
                 "Subscribers": [{"SubscriptionType": "EMAIL", "Address": email}]}
                for pct in (50.0, 80.0, 100.0)
            ],
        )
        log(f"budget alarm created -> {email}")
    except budgets.exceptions.DuplicateRecordException:
        log("budget alarm exists")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-build", action="store_true")
    args = ap.parse_args()
    print(f"\nDeploying Crayon Cinema to account {ACCOUNT} in {REGION}\n")
    ensure_bucket()
    guardrail = ensure_guardrail()
    role = ensure_role(guardrail[0])
    package = None if args.skip_build else build_zip()
    url = ensure_function(role, guardrail, package)
    ensure_budget()
    outputs = {"url": url, "tv_url": f"{url}/tv/", "bucket": BUCKET, "guardrail_id": guardrail[0], "guardrail_version": guardrail[1], "region": REGION}
    OUTPUTS.write_text(json.dumps(outputs, indent=2))
    print(f"\nDone.\n  TV app:   {url}/tv/\n  Fire TV:  cd firetv-app && ./gradlew assembleRelease -PcrayonUrl={url}/tv/\n")


if __name__ == "__main__":
    main()
