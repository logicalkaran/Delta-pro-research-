"""Research-only quantitative model validation gates. Never imports production strategy or execution code."""
from __future__ import annotations
import itertools, math, statistics
from typing import Sequence
import numpy as np

PROTOCOL_VERSION = "1.0"
RESEARCH_ONLY = True

def purged_combinatorial_splits(n_samples: int, n_groups: int = 6,
                                n_test_groups: int = 2, label_horizon: int = 1,
                                embargo: int | None = None):
    """Yield train/test integer indices; purge any train label window overlapping test and embargo."""
    if n_samples < 1 or n_groups < 2 or not 1 <= n_test_groups < n_groups:
        raise ValueError("invalid sample/group configuration")
    if label_horizon < 1:
        raise ValueError("label_horizon must be >= 1")
    embargo = label_horizon if embargo is None else int(embargo)
    if embargo < 0:
        raise ValueError("embargo must be >= 0")
    groups = [x for x in np.array_split(np.arange(n_samples), n_groups) if len(x)]
    if len(groups) < 2 or n_test_groups >= len(groups):
        raise ValueError("not enough non-empty groups")
    all_idx = np.arange(n_samples)
    for combo in itertools.combinations(range(len(groups)), n_test_groups):
        test = np.concatenate([groups[i] for i in combo])
        test_mask = np.zeros(n_samples, dtype=bool); test_mask[test] = True
        # A label at i consumes future observations through i + horizon.
        unsafe = np.zeros(n_samples, dtype=bool)
        for j in test:
            lo = max(0, int(j) - label_horizon + 1 - embargo)
            hi = min(n_samples, int(j) + label_horizon + embargo + 1)
            unsafe[lo:hi] = True
        train = all_idx[~test_mask & ~unsafe]
        if len(train) and len(test):
            yield train, np.sort(test)

def walk_forward_splits(n_samples: int, n_splits: int = 5,
                        min_train_fraction: float = 0.5, label_horizon: int = 1,
                        embargo: int | None = None):
    """Expanding chronological folds; train labels must mature before test starts."""
    if n_samples < 10 or n_splits < 1 or not 0 < min_train_fraction < 1:
        raise ValueError("invalid walk-forward configuration")
    embargo = label_horizon if embargo is None else embargo
    first = max(2, int(n_samples * min_train_fraction))
    edges = np.linspace(first, n_samples, n_splits + 1, dtype=int)
    for k in range(n_splits):
        start, end = int(edges[k]), int(edges[k + 1])
        train_end = max(0, start - int(embargo) - int(label_horizon))
        if train_end > 0 and end > start:
            yield np.arange(train_end), np.arange(start, end)

def probability_metrics(y: Sequence[float], p: Sequence[float]) -> dict:
    y, p = np.asarray(y, float), np.asarray(p, float)
    if len(y) == 0 or len(y) != len(p) or not np.isfinite(y).all() or not np.isfinite(p).all():
        raise ValueError("y/p must be non-empty, same length, finite arrays")
    if not np.isin(y, [0, 1]).all() or ((p < 0) | (p > 1)).any():
        raise ValueError("targets must be binary and probabilities in [0,1]")
    q = np.clip(p, 1e-8, 1-1e-8)
    return {"n": int(len(y)), "brier": float(np.mean((p-y)**2)),
            "log_loss": float(-np.mean(y*np.log(q)+(1-y)*np.log(1-q)))}

def conformal_interval_metrics(y, lower, upper, nominal: float = 0.9) -> dict:
    y, lo, hi = map(lambda a: np.asarray(a, float), (y, lower, upper))
    if not (len(y) and len(y) == len(lo) == len(hi)) or not all(np.isfinite(a).all() for a in (y,lo,hi)):
        raise ValueError("interval arrays must be non-empty, same length and finite")
    if ((lo > hi).any() or not 0 < nominal < 1):
        raise ValueError("invalid interval bounds or nominal coverage")
    covered = (y >= lo) & (y <= hi)
    return {"n": int(len(y)), "nominal_coverage": float(nominal),
            "empirical_coverage": float(covered.mean()), "mean_width": float(np.mean(hi-lo)),
            "coverage_shortfall": float(max(0.0, nominal-covered.mean()))}

def execution_cost_sensitivity(gross_bps: Sequence[float], base_cost_bps: float,
                               extra_slippage_ticks: float = 0.0, tick_value_bps: float = 0.0) -> dict:
    gross = np.asarray(gross_bps, float)
    if not len(gross) or not np.isfinite(gross).all() or min(base_cost_bps, extra_slippage_ticks, tick_value_bps) < 0:
        raise ValueError("finite gross returns and non-negative costs required")
    total_cost = float(base_cost_bps + extra_slippage_ticks*tick_value_bps)
    net = gross-total_cost
    return {"n": int(len(net)), "base_cost_bps": float(base_cost_bps),
            "extra_slippage_ticks": float(extra_slippage_ticks), "tick_value_bps": float(tick_value_bps),
            "total_cost_bps": total_cost, "mean_gross_bps": float(gross.mean()),
            "mean_net_bps": float(net.mean()), "positive_net_fraction": float((net>0).mean()),
            "net_returns_bps": net.tolist()}

def block_permutation_test(signal: Sequence[float], future_return_bps: Sequence[float],
                           cost_bps: float, n_permutations: int = 10000,
                           block_size: int = 5, seed: int = 20261012) -> dict:
    """One-sided null test by permuting contiguous return blocks relative to fixed signals."""
    s, r = np.asarray(signal,float), np.asarray(future_return_bps,float)
    if len(s) != len(r) or len(s) < max(20, block_size*2) or not np.isfinite(s).all() or not np.isfinite(r).all():
        raise ValueError("signal/returns must be finite, equal length and have >= max(20, 2*block_size) rows")
    if (np.abs(s)>1).any() or cost_bps < 0 or n_permutations < 100 or block_size < 1:
        raise ValueError("signals must be in [-1,1]; costs >= 0; permutations >= 100; block >= 1")
    active = s != 0
    if not active.any(): raise ValueError("signal has no active observations")
    observed = float(np.mean(s[active]*r[active]-cost_bps))
    rng = np.random.default_rng(seed); n=len(r); null=[]
    n_blocks=math.ceil(n/block_size)
    for _ in range(n_permutations):
        starts = rng.integers(0,n,size=n_blocks)
        perm = np.concatenate([np.take(r, np.arange(st,st+block_size)%n) for st in starts])[:n]
        null.append(float(np.mean(s[active]*perm[active]-cost_bps)))
    p = (1 + sum(v >= observed for v in null))/(n_permutations+1)
    return {"observed_mean_net_bps":observed,"null_95th_percentile_bps":float(np.quantile(null,.95)),
            "one_sided_p_value":float(p),"permutations":int(n_permutations),
            "block_size":int(block_size),"seed":int(seed),
            "beats_95_percentile":bool(observed>np.quantile(null,.95)),
            "method":"circular moving-block return permutation; diagnostic, not a fill simulator"}

def deflated_sharpe_diagnostic(returns: Sequence[float], trials: int = 1) -> dict:
    """Approximate probabilistic Sharpe diagnostic adjusted to an expected max-Sharpe benchmark."""
    x=np.asarray(returns,float)
    if len(x)<30 or not np.isfinite(x).all() or trials<1:
        return {"status":"INCONCLUSIVE","reason":"need >=30 finite returns and trials >=1"}
    sd=float(np.std(x,ddof=1))
    if sd<=1e-12: return {"status":"INCONCLUSIVE","reason":"zero return variance"}
    sr=float(np.mean(x)/sd); n=len(x)
    centered=(x-x.mean())/np.std(x,ddof=0)
    skew=float(np.mean(centered**3)); kurt=float(np.mean(centered**4))
    # Expected maximum of N approximately independent standard-normal trials.
    if trials == 1: benchmark=0.0
    else:
        from statistics import NormalDist
        nd=NormalDist()
        p1=max(1e-9,min(1-1e-9,1-1/trials))
        p2=max(1e-9,min(1-1e-9,1-1/(trials*math.e)))
        benchmark=((1-0.5772156649)*nd.inv_cdf(p1)+0.5772156649*nd.inv_cdf(p2))/math.sqrt(n)
    denom=math.sqrt(max(1e-12,1-skew*sr+((kurt-1)/4)*sr*sr))
    z=(sr-benchmark)*math.sqrt(n-1)/denom
    psr=0.5*(1+math.erf(z/math.sqrt(2)))
    return {"status":"DIAGNOSTIC_ONLY","n":n,"sharpe_per_observation":sr,
            "skewness":skew,"kurtosis_raw":kurt,"attempted_trials":int(trials),
            "expected_max_sharpe_benchmark_approx":benchmark,
            "probability_sharpe_exceeds_benchmark_approx":float(psr),
            "warning":"Approximation assumes trial-count independence; not a formal DSR without complete trial ledger and sampling-frequency assumptions."}

def spoof_orderbook(levels: Sequence[Sequence[float]], side: str = "bid",
                    multiplier: float = 10.0, wall_levels: int = 1) -> list:
    """Return a copied book with an artificial near-touch wall; input rows are [price, size]."""
    if side not in ("bid","ask") or multiplier <= 1 or wall_levels < 1 or not levels:
        raise ValueError("invalid side, multiplier, wall_levels or empty book")
    out=[[float(x[0]),float(x[1])] for x in levels]
    if any(not math.isfinite(p) or not math.isfinite(q) or p<=0 or q<0 for p,q in out):
        raise ValueError("book prices must be positive and sizes non-negative")
    for i in range(min(wall_levels,len(out))): out[i][1]*=multiplier
    return out

def shock_conformal_lower_band(lower: Sequence[float], upper: Sequence[float],
                               shock_mask: Sequence[bool], downside_widening: float) -> tuple[list,list]:
    """Stress-test interval response; expands intervals downward only when shock is active."""
    lo,hi,shock=map(np.asarray,(lower,upper,shock_mask))
    lo=lo.astype(float); hi=hi.astype(float); shock=shock.astype(bool)
    if not (len(lo) and len(lo)==len(hi)==len(shock)) or not np.isfinite(lo).all() or not np.isfinite(hi).all() or (lo>hi).any() or downside_widening<0:
        raise ValueError("invalid interval/shock inputs")
    lo[shock]-=downside_widening
    return lo.tolist(),hi.tolist()
