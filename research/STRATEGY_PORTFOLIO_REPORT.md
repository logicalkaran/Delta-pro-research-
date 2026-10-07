# Strategy Portfolio v1

Status: RESEARCH_ONLY

Raw trade events: 73078
Feature samples: 73043
Strategies tested: 12
Taker round-trip cost: 11.8 bps

No production execution code was modified. No live order was submitted.

## Top train-ranked candidates
- fisher_microstructure_proxy | 300s | 8/16 bps | train n=69 avg=-0.654 PF=0.9454376942331302 | validation n=15 avg=-14.488 PF=0.0 | test n=28 avg=-12.214 PF=0.025212866465646397
- fisher_microstructure_proxy | 300s | 10/20 bps | train n=69 avg=-3.466 PF=0.7631434827922595 | validation n=15 avg=-12.076 PF=0.05265989092442429 | test n=28 avg=-12.287 PF=0.006485225965435786
- liquidity_sweep_reversal | 300s | 5/10 bps | train n=81 avg=-3.932 PF=0.6333857828859579 | validation n=24 avg=-10.917 PF=0.0007635695265755452 | test n=40 avg=-11.612 PF=0.008852024636001429
- cvd_acceleration | 300s | 8/16 bps | train n=192 avg=-5.042 PF=0.5874593551430849 | validation n=32 avg=-12.730 PF=0.03843840677223515 | test n=70 avg=-13.082 PF=0.020823019332071674
- momentum_continuation | 300s | 8/16 bps | train n=77 avg=-5.465 PF=0.5765002161633207 | validation n=20 avg=-14.114 PF=0.04174094153171435 | test n=31 avg=-12.427 PF=0.01363258936050216
- fisher_microstructure_proxy | 120s | 10/20 bps | train n=69 avg=-5.708 PF=0.48827408040348463 | validation n=15 avg=-14.210 PF=0.0 | test n=28 avg=-11.901 PF=0.0
- fisher_microstructure_proxy | 120s | 8/16 bps | train n=69 avg=-5.723 PF=0.4875973298413649 | validation n=15 avg=-14.090 PF=0.0 | test n=28 avg=-12.076 PF=0.0
- liquidity_sweep_reversal | 300s | 8/16 bps | train n=81 avg=-5.954 PF=0.5329712304459898 | validation n=24 avg=-11.587 PF=0.04815265318308348 | test n=40 avg=-11.679 PF=0.019640119193050816
- cvd_acceleration | 300s | 10/20 bps | train n=192 avg=-6.034 PF=0.5423947237280057 | validation n=32 avg=-11.985 PF=0.07272424871382036 | test n=70 avg=-13.193 PF=0.030709909541961445
- liquidity_sweep_reversal | 300s | 10/20 bps | train n=81 avg=-6.165 PF=0.524301347098826 | validation n=24 avg=-11.551 PF=0.07223638383526604 | test n=40 avg=-12.063 PF=0.010495268015978202
- fisher_microstructure_proxy | 300s | 5/10 bps | train n=69 avg=-6.688 PF=0.44463908166639204 | validation n=15 avg=-13.942 PF=0.0 | test n=28 avg=-12.868 PF=0.0
- liquidity_sweep_reversal | 120s | 10/20 bps | train n=81 avg=-6.786 PF=0.40442784138323035 | validation n=24 avg=-9.658 PF=0.08455145721461745 | test n=42 avg=-12.121 PF=0.0

## Interpretation
The router is a research ranking layer, not a live trading authorization. Session/regime matrices are diagnostic and use the full historical sample; they must not be treated as out-of-sample evidence.

A candidate is not considered profitable unless it survives chronological validation/test, realistic execution, sample-size requirements, and walk-forward validation. Maker fills are not assumed.
