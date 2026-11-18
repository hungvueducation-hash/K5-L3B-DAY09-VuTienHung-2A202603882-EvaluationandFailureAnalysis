"""Regression test cho docs/trace_case.md: C-002@11, FM-03 (ticket_trust).

Bước sai đầu tiên là event #3 `model_override` (ticket nói 5 ngày, DB nói 2 ngày).
Test phải FAIL trên `seeded_regression` (lỗi) và PASS trên `fixed` (đối chứng).
"""
import pytest

pytestmark = pytest.mark.student

CLAIM, SEED = "C-002", 11


def _grade(shape):
    from pydantic_evals.evaluators import EvaluatorContext

    from lab9 import graders
    from lab9.trace_case import investigate

    case = investigate(shape, CLAIM, SEED)
    ctx = EvaluatorContext(name="t", inputs={}, metadata=None, expected_output=case["label"],
                           output=case["trial"], duration=0.0, _span_tree=None, attributes={}, metrics={})
    return case["trial"], {
        "db_fact_kept": graders.DbFactKept().evaluate(ctx).value,
        "refund_amount_correct": graders.RefundAmountCorrect().evaluate(ctx).value,
        "approval_bypass": graders.ApprovalBypass().evaluate(ctx).value,
        "reply_matches_ledger": graders.ReplyMatchesLedger().evaluate(ctx).value,
    }


def test_fixed_passes_every_grader():
    trial, g = _grade("fixed")
    assert trial["lab8_pass"] is True
    assert g == {"db_fact_kept": True, "refund_amount_correct": True,
                 "approval_bypass": False, "reply_matches_ledger": True}


def test_seeded_regression_first_wrong_step_is_model_override():
    trial, g = _grade("seeded_regression")
    kinds = [e["kind"] for e in trial["events"]]
    assert kinds.index("model_override") == 2          # event #3: bước sai đầu tiên (đứng trước quote)
    assert kinds.index("model_override") < kinds.index("quote")
    assert trial["lab8_pass"] is False
    assert g["db_fact_kept"] is False                  # grader mức bước: bắt đúng chỗ
    assert g["refund_amount_correct"] is False         # grader mức kết quả: ledger 20.000 thay vì 0
    assert trial["snapshot"]["refund_vnd"] == 20000
    assert g["reply_matches_ledger"] is True           # reply trung thực với ledger: lỗi KHÔNG nằm ở FM-08
