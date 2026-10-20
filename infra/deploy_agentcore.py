"""Deploy the story pipeline (Strands Casting + Director agents) to Amazon Bedrock AgentCore Runtime,
and create the AgentCore Memory used for the household story universe.

Run AFTER infra/deploy.py (needs the bucket + guardrail it creates):

    .venv/bin/python infra/deploy_agentcore.py
    # then add the printed AGENTCORE_RUNTIME_ARN / AGENTCORE_MEMORY_ID to .env and re-run:
    .venv/bin/python infra/deploy.py --skip-build

Uses the AgentCore starter toolkit with direct code deploy (no Docker needed).
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from crayon.config import settings  # noqa: E402

import boto3  # noqa: E402

OUTPUTS = ROOT / "infra" / "outputs.json"
STAGE = ROOT / "build" / "agentcore"
AGENT_NAME = "crayon_director"


def ensure_memory(region: str) -> str:
    from bedrock_agentcore.memory import MemoryClient

    existing = os.environ.get("AGENTCORE_MEMORY_ID", "").strip()
    if existing:
        print(f"  • memory {existing} (from .env)")
        return existing
    client = MemoryClient(region_name=region)
    for mem in client.list_memories():
        if mem.get("id", "").startswith("crayon_universe"):
            print(f"  • memory {mem['id']} exists")
            return mem["id"]
    mem = client.create_memory_and_wait(
        name="crayon_universe",
        description="Crayon Cinema household story universe: heroes, adventures, favourite things.",
        strategies=[{"semanticMemoryStrategy": {"name": "heroFacts", "namespaces": ["crayon/{actorId}/facts"]}}],
        event_expiry_days=30,
    )
    print(f"  • created memory {mem['id']}")
    return mem["id"]


def main() -> None:
    cfg = settings()
    outputs = json.loads(OUTPUTS.read_text()) if OUTPUTS.exists() else {}
    bucket = outputs.get("bucket") or cfg.bucket
    if not bucket:
        raise SystemExit("Run infra/deploy.py first (bucket/guardrail needed).")
    region = cfg.region
    account = boto3.client("sts", region_name=region).get_caller_identity()["Account"]

    memory_id = ensure_memory(region)

    if STAGE.exists():
        shutil.rmtree(STAGE)
    STAGE.mkdir(parents=True)
    shutil.copytree(ROOT / "backend" / "crayon", STAGE / "crayon", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy(ROOT / "backend" / "agentcore_app.py", STAGE / "agentcore_app.py")
    shutil.copy(ROOT / "backend" / "requirements.txt", STAGE / "requirements.txt")

    from bedrock_agentcore_starter_toolkit import Runtime

    os.chdir(STAGE)
    runtime = Runtime()
    runtime.configure(
        entrypoint="agentcore_app.py",
        agent_name=AGENT_NAME,
        requirements_file="requirements.txt",
        region=region,
        auto_create_execution_role=True,
        auto_create_s3=True,
        deployment_type="direct_code_deploy",
        runtime_type="PYTHON_3_12",
        memory_mode="NO_MEMORY",  # we manage our own memory resource above
        idle_timeout=900,
        non_interactive=True,
    )
    result = runtime.launch(
        auto_update_on_conflict=True,
        env_vars={
            "CRAYON_MODE": "aws",
            "CRAYON_STORAGE": "s3",
            "CRAYON_BUCKET": bucket,
            "GUARDRAIL_ID": outputs.get("guardrail_id", cfg.guardrail_id),
            "GUARDRAIL_VERSION": outputs.get("guardrail_version", cfg.guardrail_version),
            **cfg.model_env(),
            "AGENTCORE_MEMORY_ID": memory_id,
            "CRAYON_DATA_DIR": "/tmp/crayon",
        },
    )
    agent_arn = result.agent_arn
    status = runtime.status()
    role_arn = status.config.execution_role
    print(f"  • runtime {agent_arn}")

    # Give the auto-created execution role access to the app's own resources.
    if role_arn:
        role_name = role_arn.rsplit("/", 1)[-1]
        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {"Effect": "Allow", "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"], "Resource": f"arn:aws:s3:::{bucket}/*"},
                # ListBucket makes S3 answer "no such key" (instead of AccessDenied) for not-yet-written objects.
                {"Effect": "Allow", "Action": ["s3:ListBucket"], "Resource": f"arn:aws:s3:::{bucket}"},
                {"Effect": "Allow", "Action": ["polly:SynthesizeSpeech"], "Resource": "*"},
                {"Effect": "Allow", "Action": ["bedrock:ApplyGuardrail"], "Resource": f"arn:aws:bedrock:{region}:{account}:guardrail/*"},
                {"Effect": "Allow", "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream", "bedrock:Converse", "bedrock:ConverseStream"],
                 "Resource": ["arn:aws:bedrock:*::foundation-model/*", f"arn:aws:bedrock:*:{account}:inference-profile/*"]},
                {"Effect": "Allow", "Action": ["bedrock-agentcore:CreateEvent", "bedrock-agentcore:RetrieveMemoryRecords", "bedrock-agentcore:ListEvents"],
                 "Resource": f"arn:aws:bedrock-agentcore:{region}:{account}:memory/{memory_id}"},
            ],
        }
        boto3.client("iam").put_role_policy(RoleName=role_name, PolicyName="crayon-app-access", PolicyDocument=json.dumps(policy))
        print(f"  • granted app permissions to {role_name}")

    outputs.update(agentcore_runtime_arn=agent_arn, agentcore_memory_id=memory_id)
    OUTPUTS.write_text(json.dumps(outputs, indent=2))
    print(
        "\nAdd to .env, then run `.venv/bin/python infra/deploy.py --skip-build`:\n"
        f"  AGENTCORE_RUNTIME_ARN={agent_arn}\n  AGENTCORE_MEMORY_ID={memory_id}\n"
    )


if __name__ == "__main__":
    main()
