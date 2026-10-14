import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from order_block_experiment import Candle, aggregate_1m_to_15m, atr, validate_candles, metrics, simulate

def test_validation_deduplicates_and_rejects_bad_ohlc():
    good=Candle(900,10,12,9,11,3)
    assert validate_candles([good,good])==[good]
    try: validate_candles([Candle(900,10,8,9,11,1)])
    except ValueError: pass
    else: raise AssertionError("invalid OHLC must be rejected")

def test_15m_aggregation_requires_complete_bars():
    rows=[{"timestamp":900+i*60,"open":10+i,"high":12+i,"low":9+i,"close":11+i,"volume":1} for i in range(15)]
    result=aggregate_1m_to_15m(rows)
    assert len(result)==1 and result[0].timestamp==900
    assert (result[0].open,result[0].close,result[0].high,result[0].low,result[0].volume)==(10,25,26,9,15)
    assert aggregate_1m_to_15m(rows[:-1])==[]

def test_atr_and_empty_metrics():
    candles=[Candle(i*900,10,12,9,11) for i in range(20)]
    values=atr(candles,14)
    assert values[12] is None and values[13]==3
    assert metrics([])["trades"]==0

def test_short_history_has_no_trades():
    candles=[Candle(i*900,100+i,102+i,99+i,101+i) for i in range(30)]
    assert simulate(candles)==[]


def test_minimum_risk_width_filter_skips_narrow_stop(monkeypatch):
    import order_block_experiment as ob
    from order_block_experiment import Zone
    candles=[Candle(i*900,100,100.2,99.8,100) for i in range(60)]
    # Create one deterministic bullish retest. Entry is next candle open.
    candles[41]=Candle(41*900,100.0,100.1,99.95,100.05)
    created=[[] for _ in candles]
    created[40]=[Zone("long",99.9,100.0,40,candles[40].timestamp,39)]
    monkeypatch.setattr(ob,"atr",lambda cs:[1.0]*len(cs))
    monkeypatch.setattr(ob,"detect_zones",lambda cs,as_,**kwargs:created)
    baseline=ob.simulate(candles,min_risk_bps=0)
    filtered=ob.simulate(candles,min_risk_bps=60)
    assert len(baseline)==1
    assert abs((baseline[0].entry-baseline[0].stop)/baseline[0].entry*10000)<60
    assert filtered==[]
