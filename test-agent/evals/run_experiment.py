"""Runs the eval cases through the real agent as a Langfuse experiment, so runs compare side by side.

Needs the Docker stack, the Langfuse profile, Vertex auth and MCP_PASSWORD. From test-agent/:
    MCP_PASSWORD=<the stack's password> uv run python evals/run_experiment.py
Each run costs Vertex tokens and creates real pastes.
"""

import hashlib
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

HERE = Path(__file__).parent
DATASET = "snippet-agent/scan-then-share"


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # result.format() prints emoji; the Windows console default can't
    load_dotenv(HERE.parent / "snippet_agent" / ".env")  # the same settings adk web loads, before the agent is imported
    if not os.environ.get("MCP_PASSWORD"):
        sys.exit("Set MCP_PASSWORD (the MCP login password) so the agent can log in without a browser.")
    if not os.environ.get("LANGFUSE_PUBLIC_KEY"):
        sys.exit("Set the LANGFUSE_* keys in snippet_agent/.env; experiments live in Langfuse.")

    sys.path.insert(0, str(HERE.parent))
    from langfuse import get_client

    from evals.experiment import link_when_clean, load_cases, no_unapproved_secret_shared, pass_rate, run_case, scanned_first
    from snippet_agent.agent import root_agent  # importing the package turns tracing on

    langfuse = get_client()
    langfuse.create_dataset(name=DATASET, description="Scan before sharing; never share a secret without asking. From test-agent/evals.")
    for case in load_cases(HERE):
        langfuse.create_dataset_item(dataset_name=DATASET, id=case["id"], input=case["input"], expected_output=case["expected_output"])

    async def task(*, item, **kwargs):
        return await run_case(item.input["turns"])

    instruction_sha = hashlib.sha256(root_agent.instruction.encode()).hexdigest()[:8]
    try:
        result = langfuse.get_dataset(DATASET).run_experiment(
            name="scan-then-share",
            # A run name identifies one run; the time keeps repeat runs of the same model and instruction apart.
            run_name=f"{root_agent.model}-{instruction_sha}-{datetime.now():%Y%m%d-%H%M%S}",
            task=task,
            evaluators=[scanned_first, no_unapproved_secret_shared, link_when_clean],
            run_evaluators=[pass_rate],
            max_concurrency=1,  # one MCP login and one agent; cases run one after another
            metadata={"model": root_agent.model, "instruction_sha": instruction_sha},
        )
        print(result.format())
    finally:
        langfuse.flush()  # short runs must not lose their spans


if __name__ == "__main__":
    main()
