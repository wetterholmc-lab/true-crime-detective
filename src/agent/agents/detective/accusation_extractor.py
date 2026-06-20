"""Extract a structured accusation (name + verdict) from natural language.

The player might type anything: "I think it was Müller, definitely guilty",
"Franz Müller. Not guilty actually.", "Adelaide Bartlett did it, she's guilty".
We use a fast LLM to pull out the name and the verdict reliably.
"""

from __future__ import annotations

from loguru import logger
from pydantic_ai import Agent

from agent.agents.detective.models import AccusationExtract
from agent.services.llm import build_model

_extractor: Agent[None, AccusationExtract] = Agent(
    build_model("fast"),
    output_type=AccusationExtract,
    system_prompt=(
        "Extract the accused person's name and the player's verdict from a detective game "
        "accusation. The player may write in any language or style.\n"
        "- name: the person they are accusing (surname alone is fine)\n"
        "- verdict: 'guilty' if they believe the accused did it and should be convicted; "
        "'not_guilty' if they believe the accused is innocent or should be acquitted.\n"
        "If no verdict is stated, assume 'guilty' (the default accusation stance)."
    ),
)


async def extract_accusation(text: str) -> AccusationExtract | None:
    try:
        result = await _extractor.run(text)
        return result.output
    except Exception as exc:
        logger.warning("Accusation extraction failed: {}", exc)
        return None
