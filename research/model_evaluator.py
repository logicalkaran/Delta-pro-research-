"""Probability calibration and Murphy Brier decomposition."""
from __future__ import annotations
import math

def murphy_brier_decomposition(probabilities, outcomes, *, bins: int = 10) -> dict:
    """Return raw Brier plus binned Murphy REL-RES+UNC decomposition."""
    p=[float(x) for x in probabilities]; y=[float(x) for x in outcomes]
    if len(p) != len(y) or not p: raise ValueError("non-empty equal-length arrays required")
    if not isinstance(bins,int) or bins < 2: raise ValueError("bins must be >= 2")
    if any(not math.isfinite(x) or x < 0 or x > 1 for x in p): raise ValueError("probabilities must be in [0,1]")
    if any(x not in (0.0,1.0) for x in y): raise ValueError("outcomes must be binary 0/1")
    n=len(y); base=sum(y)/n; groups=[[] for _ in range(bins)]
    for pi, yi in zip(p,y): groups[min(bins-1,int(pi*bins))].append((pi,yi))
    reliability=resolution=0.0; binned_brier=0.0; detail=[]
    for i,g in enumerate(groups):
        if not g: continue
        avgp=sum(a for a,_ in g)/len(g); avgy=sum(b for _,b in g)/len(g); weight=len(g)/n
        reliability += weight*(avgp-avgy)**2
        resolution += weight*(avgy-base)**2
        binned_brier += sum((avgp-yi)**2 for _,yi in g)/n
        detail.append({"bin":i,"count":len(g),"mean_probability":avgp,"observed_frequency":avgy,"weight":weight})
    uncertainty=base*(1-base)
    raw_brier=sum((pi-yi)**2 for pi,yi in zip(p,y))/n
    reconstructed=reliability-resolution+uncertainty
    return {"n":n,"brier_score":raw_brier,"binned_brier_score":binned_brier,
            "reliability":reliability,"resolution":resolution,"uncertainty":uncertainty,
            "decomposed_brier":reconstructed,"decomposition_residual":binned_brier-reconstructed,
            "raw_vs_binned_gap":raw_brier-binned_brier,"base_rate":base,"bins":detail,
            "resolution_exceeds_uncertainty":resolution>uncertainty,
            "status":"OK" if abs(binned_brier-reconstructed)<1e-12 else "DECOMPOSITION_CHECK_FAILED"}
