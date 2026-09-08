from __future__ import annotations

from research.run_gil_breakout_promotion_gate import Metrics, classify_terminal


def m(expectancy: float, pf: float, trades: int = 100) -> Metrics:
    return Metrics(
        trades=trades,
        wins=50,
        losses=50,
        expectancy_r=expectancy,
        profit_factor_r=pf,
        max_cumulative_r_drawdown=-5.0,
        unresolved=0,
    )


def test_promotion_gate_passes_only_when_all_required_robustness_checks_survive():
    state, reasons = classify_terminal(
        oos=m(0.10, 1.20),
        leave_one_symbol_out={s: m(0.05, 1.10) for s in ("SPY","QQQ","AAPL","MSFT","NVDA")},
        leave_one_year_out={"2024": m(0.04, 1.08), "2025": m(0.06, 1.12), "2026": m(0.03, 1.05)},
        high_vol=m(0.02, 1.04, trades=30),
        deterministic=True,
    )
    assert state == "PROMOTION-ELIGIBLE"
    assert reasons == []


def test_leave_one_symbol_out_collapse_rejects():
    loso={s: m(0.05,1.10) for s in ("SPY","QQQ","AAPL","MSFT","NVDA")}
    loso["MSFT"]=m(-0.01,0.98)
    state,reasons=classify_terminal(
        oos=m(0.10,1.20),
        leave_one_symbol_out=loso,
        leave_one_year_out={"2025":m(0.05,1.10)},
        high_vol=m(0.03,1.05,30),
        deterministic=True,
    )
    assert state=="REJECTED"
    assert "leave-one-symbol-out-collapsed:MSFT" in reasons


def test_missing_high_vol_evidence_blocks_instead_of_guessing():
    state,reasons=classify_terminal(
        oos=m(0.10,1.20),
        leave_one_symbol_out={s:m(0.05,1.10) for s in ("SPY","QQQ","AAPL","MSFT","NVDA")},
        leave_one_year_out={"2025":m(0.05,1.10)},
        high_vol=m(0.03,1.05,trades=5),
        deterministic=True,
    )
    assert state=="BLOCKED-EVIDENCE"
    assert reasons==["insufficient-high-vol-evidence"]


def test_deterministic_reproduction_failure_rejects():
    state,reasons=classify_terminal(
        oos=m(0.10,1.20),
        leave_one_symbol_out={s:m(0.05,1.10) for s in ("SPY","QQQ","AAPL","MSFT","NVDA")},
        leave_one_year_out={"2025":m(0.05,1.10)},
        high_vol=m(0.03,1.05,30),
        deterministic=False,
    )
    assert state=="REJECTED"
    assert "deterministic-reproduction-failed" in reasons
