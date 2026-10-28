"""How the live evals hand cases to ADK, checked with a fake evaluator: no LLM, no MCP servers."""

from pathlib import Path

from google.adk.evaluation.agent_evaluator import AgentEvaluator

from evals.adk_evals import evaluate_file

SHARES = Path(__file__).parent.parent / "evals" / "shares" / "scan_then_share.evalset.json"


async def test_cases_run_one_at_a_time_with_their_folder_config(monkeypatch):
    # ADK runs up to 4 cases of one set at once on the same agent, and each finished case closes the MCP
    # connections the others are still using ("Connection closed"). One case per call avoids that.
    calls = []

    async def fake_evaluate_eval_set(*, agent_module, eval_set, eval_config, num_runs, **kwargs):
        calls.append((agent_module, [c.eval_id for c in eval_set.eval_cases], eval_config.criteria["tool_trajectory_avg_score"].model_dump()["match_type"], num_runs))

    monkeypatch.setattr(AgentEvaluator, "evaluate_eval_set", staticmethod(fake_evaluate_eval_set))
    await evaluate_file(SHARES)

    assert calls == [
        ("snippet_agent", ["clean"], "IN_ORDER", 1),
        ("snippet_agent", ["secret_then_redacted"], "IN_ORDER", 1),
        ("snippet_agent", ["placeholder"], "IN_ORDER", 1),
    ]
