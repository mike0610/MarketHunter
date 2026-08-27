import json, math, sys, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path

OBJECT_ID = "SL-VAL-RISK-009"
START_MS = 1546300800000  # 2019-01-01 UTC
END_MS = 1767225600000    # 2026-01-01 UTC exclusive
ENTER_DD = 0.20
RELEASE_DD = 0.10
REDUCED_M = 0.5
LOCKED_START = "2022-01-01"
MAX_EVENT_DAYS = 30


def emit(outdir, state, payload):
    p = Path(outdir)
    p.mkdir(parents=True, exist_ok=True)
    result = {
        "object_id": OBJECT_ID,
        "terminal_state": state,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        **payload,
    }
    (p / "terminal_result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True), encoding="utf-8"
    )


def fetch_klines():
    rows = []
    cur = START_MS
    while cur < END_MS:
        q = urllib.parse.urlencode(
            {
                "symbol": "BTCUSDT",
                "interval": "1d",
                "startTime": cur,
                "endTime": END_MS - 1,
                "limit": 1000,
            }
        )
        url = "https://data-api.binance.vision/api/v3/klines?" + q
        with urllib.request.urlopen(url, timeout=20) as r:
            batch = json.loads(r.read().decode())
        if not batch:
            break
        rows.extend(batch)
        nxt = int(batch[-1][0]) + 86400000
        if nxt <= cur:
            raise RuntimeError("non-advancing provider cursor")
        cur = nxt
    return rows


def main(outdir):
    try:
        rows = fetch_klines()
    except Exception as e:
        emit(outdir, "BLOCKED-PROVIDER", {"reason": repr(e)})
        return

    opens = [int(r[0]) for r in rows]
    if (
        len(rows) != 2557
        or len(set(opens)) != len(opens)
        or any(b - a != 86400000 for a, b in zip(opens, opens[1:]))
    ):
        emit(
            outdir,
            "DATA-INTEGRITY-FAIL",
            {
                "row_count": len(rows),
                "first_open": opens[0] if opens else None,
                "last_open": opens[-1] if opens else None,
            },
        )
        return

    closes = [float(r[4]) for r in rows]
    dates = [
        datetime.fromtimestamp(t / 1000, timezone.utc).date().isoformat()
        for t in opens
    ]
    logrets = [None] + [
        math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))
    ]

    # Frozen controller state. State applied to return on day i uses equity only through i-1.
    equity = 1.0
    peak = 1.0
    state = "NORMAL"
    states = [None]
    multipliers = [None]
    transitions = []

    for i in range(1, len(closes)):
        prior_eq = equity
        peak = max(peak, prior_eq)
        dd = 1.0 - prior_eq / peak
        prior_state = state
        if state == "NORMAL" and dd >= ENTER_DD:
            state = "REDUCED"
        elif state == "REDUCED" and dd <= RELEASE_DD:
            state = "NORMAL"
        m = REDUCED_M if state == "REDUCED" else 1.0
        if state != prior_state:
            transitions.append(
                {
                    "index": i,
                    "date": dates[i],
                    "from_state": prior_state,
                    "to_state": state,
                    "prior_close_drawdown": dd,
                }
            )
        states.append(state)
        multipliers.append(m)
        equity = prior_eq * math.exp(m * logrets[i])

    locked_transitions = [t for t in transitions if t["date"] >= LOCKED_START]

    events = []
    for k, t in enumerate(locked_transitions):
        i = t["index"]
        next_i = (
            locked_transitions[k + 1]["index"]
            if k + 1 < len(locked_transitions)
            else len(closes)
        )
        end_i = min(i + MAX_EVENT_DAYS, next_i, len(closes))
        # Returns from transition day i through day end_i-1, capped before next state change.
        window_lrs = [logrets[j] for j in range(i, end_i)]
        actual_m = REDUCED_M if t["to_state"] == "REDUCED" else 1.0
        counterfactual_m = REDUCED_M if t["from_state"] == "REDUCED" else 1.0
        underlying_lr = sum(window_lrs)
        action_effect_lr = (actual_m - counterfactual_m) * underlying_lr
        events.append(
            {
                "transition_date": t["date"],
                "from_state": t["from_state"],
                "to_state": t["to_state"],
                "prior_close_drawdown": t["prior_close_drawdown"],
                "window_days": len(window_lrs),
                "window_end_exclusive": dates[end_i] if end_i < len(dates) else "2026-01-01",
                "underlying_return": math.exp(underlying_lr) - 1.0,
                "actual_state_return": math.exp(actual_m * underlying_lr) - 1.0,
                "prior_state_counterfactual_return": math.exp(counterfactual_m * underlying_lr) - 1.0,
                "action_effect_log_return": action_effect_lr,
                "action_helped": action_effect_lr > 0,
                "action_hurt": action_effect_lr < 0,
            }
        )

    sum_effect = sum(e["action_effect_log_return"] for e in events)
    helped = sum(1 for e in events if e["action_helped"])
    hurt = sum(1 for e in events if e["action_hurt"])
    neutral = len(events) - helped - hurt

    emit(
        outdir,
        "ATTRIBUTION-RESULT",
        {
            "contract": {
                "enter_dd": ENTER_DD,
                "release_dd": RELEASE_DD,
                "reduced_m": REDUCED_M,
                "locked_start": LOCKED_START,
                "event_window": "transition day forward, max 30 daily returns, capped before next transition",
                "counterfactual": "keep immediately prior state multiplier unchanged over the same event window",
                "no_tuning": True,
            },
            "row_count": len(rows),
            "locked_transition_count": len(locked_transitions),
            "events": events,
            "summary": {
                "helped_count": helped,
                "hurt_count": hurt,
                "neutral_count": neutral,
                "sum_action_effect_log_return": sum_effect,
                "compound_action_effect": math.exp(sum_effect) - 1.0,
            },
            "interpretation_guardrail": "Local event attribution only. Do not infer whole-window timing alpha, live sizing parameters, or causal market timing from six transitions.",
        },
    )


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".")
