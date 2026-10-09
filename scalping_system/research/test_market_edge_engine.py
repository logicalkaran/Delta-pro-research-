from market_edge_features import enrich
from probabilistic_model import ProbabilisticModel

def row(): return {'imb5':.4,'imb10':.2,'delta5':.3,'delta30':.2,'delta60':.1,'ret5':.01,'ret30':.02,'ret60':.03,'cvd_slope30':.1,'spread_bps':2,'depth5_ratio':1.2,'depth10_ratio':1.1,'cvd':10,'mid':100}
def test_features():
 x=enrich(row()); assert 'toxicity_score' in x and 0<=x['toxicity_score']<=1
def test_model():
 rs=[enrich({**row(),'imb5':(-1 if i%2 else 1)}) for i in range(120)]; y=[i%2 for i in range(120)]; m=ProbabilisticModel(epochs=80).fit(rs,y); p=m.predict_proba(rs); assert len(p)==120 and ((p>=0)&(p<=1)).all()
