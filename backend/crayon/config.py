"""Runtime configuration, loaded from environment (and .env for local dev)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
# Repo root locally (backend/crayon -> repo). In Lambda/AgentCore the code is flat, so allow override.
ROOT = Path(os.environ.get("CRAYON_ROOT", PACKAGE_DIR.parents[1]))


def _load_dotenv() -> None:
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    try:
        from dotenv import load_dotenv
    except ImportError:  # python-dotenv is optional in cloud runtimes
        return
    load_dotenv(env_file, override=False)


_load_dotenv()


def _env(name: str, default: str = "", *aliases: str) -> str:
    for key in (name, *aliases):
        value = os.environ.get(key, "").strip()
        if value:
            return value
    return default


@dataclass(frozen=True)
class Settings:
    mode: str
    region: str
    story_model_id: str
    casting_model_id: str
    scene_model_id: str
    scene_region: str
    cutout_model_id: str
    guardrail_id: str
    guardrail_version: str
    storage: str
    bucket: str
    agentcore_runtime_arn: str
    agentcore_memory_id: str
    port: int
    public_url: str
    data_dir: Path
    web_dir: Path
    image_concurrency: int

    @property
    def use_aws(self) -> bool:
        return self.mode == "aws"

    def model_env(self) -> dict[str, str]:
        """Model settings to forward to cloud runtimes (Lambda, AgentCore)."""
        return {
            "STORY_MODEL_ID": self.story_model_id,
            "CASTING_MODEL_ID": self.casting_model_id,
            "SCENE_MODEL_ID": self.scene_model_id,
            "SCENE_REGION": self.scene_region,
            "CUTOUT_MODEL_ID": self.cutout_model_id,
            "IMAGE_CONCURRENCY": str(self.image_concurrency),
        }


@lru_cache(maxsize=1)
def settings() -> Settings:
    return Settings(
        mode=_env("CRAYON_MODE", "mock").lower(),
        region=_env("AWS_REGION", _env("AWS_DEFAULT_REGION", "us-east-1")),
        # Any Bedrock Converse model with vision + tool use works (Amazon Nova, Anthropic Claude, ...).
        # Nova 2 Lite: ~6s for a full branching story with a tool call; Nova Pro was slower and broke tool-use format.
        story_model_id=_env("STORY_MODEL_ID", "us.amazon.nova-2-lite-v1:0", "CLAUDE_MODEL_ID"),
        casting_model_id=_env("CASTING_MODEL_ID", "us.amazon.nova-2-lite-v1:0", "CLAUDE_FAST_MODEL_ID"),
        # Stability AI on Bedrock (Nova Canvas reached end of life). SD3.5 Large is served from us-west-2.
        scene_model_id=_env("SCENE_MODEL_ID", "stability.sd3-5-large-v1:0"),
        scene_region=_env("SCENE_REGION", "us-west-2"),
        cutout_model_id=_env("CUTOUT_MODEL_ID", "us.stability.stable-image-remove-background-v1:0"),
        guardrail_id=_env("GUARDRAIL_ID"),
        guardrail_version=_env("GUARDRAIL_VERSION", "DRAFT"),
        storage=_env("CRAYON_STORAGE", "local").lower(),
        bucket=_env("CRAYON_BUCKET"),
        agentcore_runtime_arn=_env("AGENTCORE_RUNTIME_ARN"),
        agentcore_memory_id=_env("AGENTCORE_MEMORY_ID"),
        port=int(_env("CRAYON_PORT", "8787")),
        public_url=_env("CRAYON_PUBLIC_URL").rstrip("/"),
        data_dir=Path(_env("CRAYON_DATA_DIR", str(ROOT / ".data"))),
        web_dir=Path(_env("CRAYON_WEB_DIR", str(ROOT / "web"))),
        image_concurrency=max(1, int(_env("IMAGE_CONCURRENCY", "2", "NOVA_CONCURRENCY"))),
    )
