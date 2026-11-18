"""Bonus: Inspect AI scorers must agree with the pydantic-evals graders, trial by trial."""
import pytest

pytestmark = pytest.mark.student
pytest.importorskip("inspect_ai")


@pytest.mark.parametrize("shape,fired", [("bug:leaky_trace", "secret_leak"), ("bug:sibling_refund", "approval_bypass"),
                                         ("bug:pre_deducted+misreport", "reply_matches_ledger")])
def test_inspect_port_agrees_and_actually_fires(shape, fired):
    from lab9.eval import load_spec
    from lab9.inspect_port import compare
    from pathlib import Path

    agree, total, bad, means = compare(shape, load_spec(Path("config/metric_spec.yaml")), [11])
    assert bad == [] and agree == total == 56
    py, ins = means[fired]
    assert py == ins and py != (1.0 if fired == "reply_matches_ledger" else 0.0)   # the bug is visible to both
