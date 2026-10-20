"""Amazon Bedrock AgentCore Runtime entry point.

The Lambda API invokes this runtime with {"story_id": ...}. Generation runs as an AgentCore async task so the
invocation returns immediately while the microVM keeps working (ping reports HealthyBusy until done).
"""

from __future__ import annotations

import logging
import threading

from bedrock_agentcore.runtime import BedrockAgentCoreApp

from crayon import generator

logging.basicConfig(level=logging.INFO)
app = BedrockAgentCoreApp()


@app.entrypoint
def invoke(payload: dict) -> dict:
    story_id = str(payload.get("story_id", ""))
    if not story_id:
        return {"error": "story_id required"}
    task_id = app.add_async_task("generate_story", {"story_id": story_id})

    def work() -> None:
        try:
            generator.generate_story(story_id)
        finally:
            app.complete_async_task(task_id)

    threading.Thread(target=work, daemon=True).start()
    return {"accepted": True, "story_id": story_id}


if __name__ == "__main__":
    app.run()
