from strategy.institutional_absorption_v1 import evaluate

def candle(o,h,l,c,v=100):
    return {"open":o,"high":h,"low":l,"close":c,"volume":v}

def micro(delta=-0.20, cvd=-200):
    return {"order_book":{"mid_price":100.0,"spread":0.01},
            "quality":{"fresh_seconds":0.1},
            "windows":{"30":{"delta_pct":delta}},
            "cvd_slope_30s":cvd}

def test_long_absorption_accepts_two_to_one_poc():
    rows=[candle(100,101,99,100) for _ in range(15)]
    rows += [candle(100,100.5,97,99.8)]
    sig=evaluate(micro(),rows,rows,oi_change_pct=-0.01,poc=120)
    assert sig.action=="LONG"
    assert sig.valid
    assert sig.rr>=2.0
    assert abs(sig.stop-(97-1.5*sig.atr))<1e-9

def test_long_rejects_poc_with_bad_rr():
    rows=[candle(100,101,99,100) for _ in range(15)]
    rows += [candle(100,100.5,97,99.8)]
    sig=evaluate(micro(),rows,rows,oi_change_pct=-0.01,poc=101)
    assert sig.action=="NO_TRADE"
    assert "POC_RR_BELOW_2" in sig.reason

def test_short_absorption_accepts():
    rows=[candle(100,101,99,100) for _ in range(15)]
    rows += [candle(100,104,99.5,100.2)]
    m=micro(delta=0.20,cvd=200)
    sig=evaluate(m,rows,rows,oi_change_pct=0.0,poc=80)
    assert sig.action=="SHORT"
    assert sig.valid
    assert sig.rr>=2.0

def test_oi_rising_blocks_absorption():
    rows=[candle(100,101,99,100) for _ in range(15)]
    rows += [candle(100,100.5,97,99.8)]
    sig=evaluate(micro(),rows,rows,oi_change_pct=0.20,poc=111)
    assert sig.action=="NO_TRADE"
