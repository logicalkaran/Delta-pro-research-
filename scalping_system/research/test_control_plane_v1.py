import tempfile
from pathlib import Path
from experiment_manager_v1 import fingerprint,chronological_split
from champion_challenger_v1 import evaluate
from ai_research_council_v1 import build_packet

def test_fingerprint_stable(): assert fingerprint({'b':2,'a':1})==fingerprint({'a':1,'b':2})
def test_split_chronological():
    a,b=chronological_split([{'ts':3},{'ts':1},{'ts':2},{'ts':4}],0.5); assert [x['ts'] for x in a]==[1,2] and [x['ts'] for x in b]==[3,4]
def test_challenger_promotion():
    c={'n':100,'profit_factor':1.3,'avg_net_bps':1.0,'first_half_avg_net_bps':.2,'second_half_avg_net_bps':1.8}; h={'avg_net_bps':.5}; assert evaluate(h,c)['promote']
def test_challenger_rejected():
    c={'n':100,'profit_factor':2,'avg_net_bps':1,'first_half_avg_net_bps':-.1,'second_half_avg_net_bps':2}; assert not evaluate({'avg_net_bps':.5},c)['promote']
def test_council_no_order_authority(): assert build_packet([])['order_authority'] is False
