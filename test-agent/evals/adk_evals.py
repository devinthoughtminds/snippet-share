"""Runs an ADK eval-set file through AgentEvaluator one case at a time.

AgentEvaluator.evaluate() runs up to 4 cases of a set at once, all on the same root_agent. When one case
finishes, its Runner closes the agent's MCP toolsets, cutting the connections the other cases are still
using ("MCPError: Connection closed"). Handing it one case per call keeps the cases from sharing them.
"""

from pathlib import Path

from google.adk.evaluation.agent_evaluator import AgentEvaluator
from google.adk.evaluation.eval_set import EvalSet


async def evaluate_file(path: Path) -> None:
    """Fails (AssertionError from ADK) if any case misses a threshold in the test_config.json next to the file."""
    config = AgentEvaluator.find_config_for_test_file(str(path))
    eval_set = EvalSet.model_validate_json(path.read_text(encoding="utf-8"))
    for case in eval_set.eval_cases:
        one = eval_set.model_copy(update={"eval_cases": [case]})
        await AgentEvaluator.evaluate_eval_set(agent_module="snippet_agent", eval_set=one, eval_config=config, num_runs=1)
