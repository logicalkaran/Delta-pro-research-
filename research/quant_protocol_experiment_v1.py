"""Protocol-driven, research-only probability experiment for BTC perpetuals."""
from __future__ import annotations
import json, math, statistics
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data/processed/live_multi_timeframe_candles_v1.json"
OUT = ROOT / "data/processed/quant_protocol_experiment_v1.json"
HORIZON = 5
PURGE = HORIZON
BASE_COST_BPS = 14.0
THRESHOLD_LOW, THRESHOLD_HIGH = 0.45, 0.55
SEED = 20261010

def load_candles():
    raw = json.loads(CACHE.read_text())
    frames = raw.get("candles", {})
    rows = frames.get("1m", []) if isinstance(frames, dict) else []
    rows = sorted(rows, key=lambda x: float(x["timestamp"]))
    out = []
    for r in rows:
        try:
            ts, close = float(r["timestamp"]), float(r["close"])
            if math.isfinite(ts) and math.isfinite(close) and close > 0:
                out.append((ts, close))
        except (KeyError, TypeError, ValueError):
            continue
    dedup = {}
    for ts, close in out:
        dedup[ts] = close
    return sorted(dedup.items())

def sigmoid(z):
    z = np.clip(z, -30.0, 30.0)
    return 1.0 / (1.0 + np.exp(-z))

def fit_logistic(x, y, steps=1200, lr=0.08, l2=0.02):
    mu = float(np.mean(x)); sd = float(np.std(x))
    if not math.isfinite(sd) or sd < 1e-12:
        return (0.0, 0.0, mu, max(sd, 1.0))
    z = (x - mu) / sd
    w, b = 0.0, math.log((float(np.mean(y)) + 1e-5) / (1.0 - float(np.mean(y)) + 1e-5))
    for _ in range(steps):
        p = sigmoid(w*z+b)
        gw = float(np.mean((p-y)*z)) + l2*w
        gb = float(np.mean(p-y))
        w -= lr*gw; b -= lr*gb
    return w, b, mu, sd

def prob_metrics(y, p):
    p = np.clip(np.asarray(p, dtype=float), 1e-6, 1-1e-6)
    y = np.asarray(y, dtype=float)
    bins = []
    for lo in np.arange(0.0, 1.0, 0.2):
        mask = (p >= lo) & (p < lo+0.2 if lo < 0.8 else p <= 1.0)
        if np.any(mask):
            bins.append({"range": [round(float(lo),1), round(float(lo+0.2),1)],
                         "n": int(mask.sum()), "mean_probability": float(np.mean(p[mask])),
                         "observed_positive_rate": float(np.mean(y[mask]))})
    return {"n": int(len(y)), "brier": float(np.mean((p-y)**2)),
            "log_loss": float(-np.mean(y*np.log(p)+(1-y)*np.log(1-p))),
            "calibration_bins": bins}

def trade_metrics(net):
    net = np.asarray(net, dtype=float)
    wins = net[net > 0]; losses = net[net < 0]
    eq = np.cumsum(net)
    peak = np.maximum.accumulate(np.concatenate(([0.0], eq)))[1:] if len(eq) else np.array([])
    dd = peak-eq if len(eq) else np.array([])
    return {"independent_trade_count": int(len(net)),
            "mean_net_bps": float(np.mean(net)) if len(net) else None,
            "win_rate": float(np.mean(net > 0)) if len(net) else None,
            "profit_factor": float(np.sum(wins)/abs(np.sum(losses))) if len(losses) and np.sum(losses) else (None if not len(wins) else None),
            "max_drawdown_bps": float(np.max(dd)) if len(dd) else None}

def block_bootstrap_ci(values, block=HORIZON, n_boot=1000):
    a = np.asarray(values, dtype=float)
    if len(a) < 20: return {"low_95": None, "high_95": None, "method": "block bootstrap; insufficient n<20"}
    rng = np.random.default_rng(SEED)
    means = []
    n = len(a)
    for _ in range(n_boot):
        sample = []
        while len(sample) < n:
            start = int(rng.integers(0, n))
            sample.extend(a[(start+j) % n] for j in range(block))
        means.append(float(np.mean(sample[:n])))
    return {"low_95": float(np.quantile(means, .025)),
            "high_95": float(np.quantile(means, .975)),
            "method": f"circular moving-block bootstrap, block={block}, resamples={n_boot}"}

def run():
    candles = load_candles()
    if len(candles) < 300:
        result = {"experiment":"MOMENTUM_1M_TO_5M_V1","decision":"NEED_MORE_DATA",
                  "reason":"Fewer than 300 valid 1m candles", "candle_count":len(candles)}
        OUT.write_text(json.dumps(result, indent=2)); print(json.dumps(result, indent=2)); return
    ts = np.array([x[0] for x in candles], dtype=float)
    close = np.array([x[1] for x in candles], dtype=float)
    gaps = np.diff(ts)
    valid_gap_rate = float(np.mean((gaps >= 59) & (gaps <= 61))) if len(gaps) else 0.0
    x = np.full(len(close), np.nan)
    x[1:] = close[1:]/close[:-1]-1.0
    future = np.full(len(close), np.nan)
    future[:-HORIZON] = close[HORIZON:]/close[:-HORIZON]-1.0
    eligible = np.where(np.isfinite(x) & np.isfinite(future) & (np.arange(len(close)) >= 1))[0]
    # Three fixed chronological test folds. Each training label must mature before test.
    chunks = np.array_split(eligible, 4)
    folds = []
    all_net = []
    for fold_no in range(1,4):
        train, test = np.concatenate(chunks[:fold_no]), chunks[fold_no]
        if len(test) == 0: continue
        test_start = int(test[0])
        train = train[train + HORIZON < test_start]
        if len(train) < 100:
            folds.append({"fold":fold_no,"decision":"NEED_MORE_DATA","train_n":len(train),"test_n":len(test)})
            continue
        y_train = (future[train] > 0).astype(float)
        y_test = (future[test] > 0).astype(float)
        w,b,mu,sd = fit_logistic(x[train], y_train)
        p_model = sigmoid(w*((x[test]-mu)/sd)+b)
        p_base = np.full(len(test), float(np.mean(y_train)))
        # Fixed abstention band is declared before evaluating test outcomes.
        positions = np.where(p_model >= THRESHOLD_HIGH, 1.0,
                    np.where(p_model <= THRESHOLD_LOW, -1.0, 0.0))
        # PnL uses non-overlapping 5m entry cohorts; forecast scores still use all rows.
        independent = ((test - int(test[0])) % HORIZON) == 0
        trade_pos = positions[independent]
        trade_idx = test[independent]
        traded = trade_pos != 0
        gross_bps = future[trade_idx]*10000.0
        net = trade_pos[traded]*gross_bps[traded]-BASE_COST_BPS
        # Delayed entry sensitivity: one extra 1m bar, plus 2 bps execution cost.
        ok = trade_idx + 1 + HORIZON < len(close)
        delayed = np.full(len(trade_idx), np.nan)
        delayed[ok] = close[trade_idx[ok]+1+HORIZON]/close[trade_idx[ok]+1]-1.0
        delayed_net = trade_pos[ok & traded]*delayed[ok & traded]*10000.0-(BASE_COST_BPS+2.0)
        folds.append({"fold":fold_no,"train_n":int(len(train)),"test_n":int(len(test)),
            "test_start_ts":float(ts[test[0]]),"test_end_ts":float(ts[test[-1]]),
            "base_rate_train":float(np.mean(y_train)),
            "baseline":prob_metrics(y_test,p_base),"logistic":prob_metrics(y_test,p_model),
            "trade_metrics":trade_metrics(net.tolist()),
            "net_mean_block_bootstrap_95":block_bootstrap_ci(net.tolist()),
            "delayed_entry_plus_2bps":trade_metrics(delayed_net.tolist()),
            "thresholds":{"short_at_or_below":THRESHOLD_LOW,"long_at_or_above":THRESHOLD_HIGH},
            "cost_assumption_bps":BASE_COST_BPS})
        all_net.extend(net.tolist())
    model_briers = [f["logistic"]["brier"] for f in folds if "logistic" in f]
    base_briers = [f["baseline"]["brier"] for f in folds if "baseline" in f]
    means = [f["trade_metrics"]["mean_net_bps"] for f in folds if f.get("trade_metrics",{}).get("mean_net_bps") is not None]
    data_ok = valid_gap_rate >= 0.95
    ci = block_bootstrap_ci(all_net)
    if not data_ok or len(folds) < 3 or len(all_net) < 20:
        decision = "NEED_MORE_DATA"
    elif ci["high_95"] is not None and ci["high_95"] < 0:
        decision = "REJECT"
    elif means and all(v > 0 for v in means) and model_briers and all(m < b for m,b in zip(model_briers,base_briers)):
        decision = "SHADOW_ONLY"
    else:
        decision = "NEED_MORE_DATA"
    result = {"experiment":"MOMENTUM_1M_TO_5M_V1","decision":decision,
      "hypothesis":"The sign/magnitude of the last completed 1m return adds out-of-sample information about whether the next 5m close-to-close return is positive, beyond the training-fold base rate.",
      "causal_mechanism":"Short-lived price discovery and order-flow persistence may continue across adjacent minutes; this candle-only proxy does not establish the mechanism itself.",
      "prediction_horizon":"5 minutes after the feature timestamp",
      "label":"binary future close-to-close return > 0; gross return also measured in bps",
      "feature":{"name":"ret_1m","timestamp":"current 1m bar close; only prior/current completed close used"},
      "validation":{"method":"3 expanding chronological folds; train labels purge at least 5 bars before each test; model scaling fit on train only; no test tuning",
                    "valid_1m_gap_rate":valid_gap_rate,"timestamp_step_requirement_seconds":[59,61],
                    "candle_count":len(candles),"labeled_rows":int(len(eligible))},
      "baselines":{"probability":"training-fold positive-label base rate","model":"regularized one-feature logistic regression implemented with NumPy"},
      "metrics":{"folds":folds,"pooled_trade_metrics":trade_metrics(all_net),
                 "pooled_mean_net_block_bootstrap_95":ci},
      "cost_stress":{"base_round_trip_bps":BASE_COST_BPS,"delayed_entry_additional_bps":2.0,
                     "fill_assumption":"directional close-to-close mark-to-market; not an exchange fill simulation"},
      "limitations":["Candle-only feature; no causal order-flow attribution.",
        "Overlapping 5m labels remain correlated; block bootstrap is approximate and fold results are primary.",
        "This report does not yet estimate a formal confidence interval for Brier/log-loss differences.",
        "Profit factor is undefined when no positive net trades; missing trade data is not treated as zero.",
        "Timestamp convention must be verified against the source API.",
        "No exchange fees have been independently verified here; 14 bps is a conservative placeholder assumption, not a claim about account fees."],
      "policy":{"research_only":True,"production_logic_changed":False,"risk_limits_changed":False,"promotion_changed":False,"real_orders":False}}
    OUT.write_text(json.dumps(result,indent=2,allow_nan=False))
    print(json.dumps(result,indent=2,allow_nan=False))

if __name__ == "__main__":
    run()
