"""Check which Bedrock models your credentials can actually invoke, to pick model IDs for .env.

    .venv/bin/python scripts/list_models.py

Being *listed* is not the same as being *invokable*: Marketplace-backed models (Anthropic, Stability) fail with
INVALID_PAYMENT_INSTRUMENT until the account has a valid payment method, and retired models (e.g. Nova Canvas)
still appear in some places. So this script sends one tiny request to each configured model.
"""

from __future__ import annotations

import base64
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from crayon.config import settings  # noqa: E402

import boto3  # noqa: E402
from botocore.exceptions import ClientError  # noqa: E402
from PIL import Image  # noqa: E402

cfg = settings()
bedrock = boto3.client("bedrock", region_name=cfg.region)
print(f"Region: {cfg.region}\n\nInference profiles:")
for p in bedrock.list_inference_profiles(maxResults=500)["inferenceProfileSummaries"]:
    if any(k in p["inferenceProfileId"] for k in ("anthropic", "nova", "stability")):
        print(f"  {p['inferenceProfileId']:60} {p['status']}")


def check(label: str, model_id: str, region: str, fn) -> None:
    try:
        fn(boto3.client("bedrock-runtime", region_name=region))
        print(f"  OK    {label:9} {model_id} ({region})")
    except ClientError as e:
        print(f"  FAIL  {label:9} {model_id} ({region}): {e.response['Error']['Code']} - {e.response['Error']['Message'][:120]}")


def converse(model_id: str):
    return lambda br: br.converse(modelId=model_id, messages=[{"role": "user", "content": [{"text": "Say hi."}]}], inferenceConfig={"maxTokens": 10})


buf = io.BytesIO()
Image.new("RGB", (256, 256), "white").save(buf, "PNG")
tiny_png = base64.b64encode(buf.getvalue()).decode()

print("\nConfigured models (one tiny request each):")
check("story", cfg.story_model_id, cfg.region, converse(cfg.story_model_id))
check("casting", cfg.casting_model_id, cfg.region, converse(cfg.casting_model_id))
check("cutout", cfg.cutout_model_id, cfg.region, lambda br: br.invoke_model(
    modelId=cfg.cutout_model_id, body=json.dumps({"image": tiny_png, "output_format": "png"})))
check("scene", cfg.scene_model_id, cfg.scene_region, lambda br: br.invoke_model(
    modelId=cfg.scene_model_id, body=json.dumps({"prompt": "a crayon drawing of a meadow", "mode": "text-to-image", "aspect_ratio": "16:9", "output_format": "jpeg"})))
