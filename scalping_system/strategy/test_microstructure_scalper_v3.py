"""Unit tests for Microstructure Scalper V3."""
from strategy.microstructure_scalper_v3 import evaluate
def base():
    return {"windows":{"5":{"delta_pct":.20,"trades":8},"30":{"delta_pct":.12}},
            "price":{"5":{"return_pct":.12}},
            "order_book":{"imbalance_5":.20,"spread":1.0,"mid_price":84000},
            "quality":{"fresh_seconds":.1},"persistence":.9}
def main():
    assert evaluate(base()).action=="LONG"
    x=base(); x["price"]["5"]["return_pct"]=-.12; x["windows"]["5"]["delta_pct"]=-.20; x["windows"]["30"]["delta_pct"]=-.12; x["order_book"]["imbalance_5"]=-.20
    assert evaluate(x).action=="SHORT"
    x=base(); x["persistence"]=.2; assert evaluate(x).action=="NO_TRADE"
    x=base(); x["order_book"]["spread"]=100; assert evaluate(x).action=="NO_TRADE"
    x=base(); x["volatility_pct"]=.5; assert evaluate(x).action=="NO_TRADE"
    print("V3 TESTS: 5/5 PASSED")
if __name__=="__main__": main()
