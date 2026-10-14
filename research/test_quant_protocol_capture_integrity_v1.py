import gzip, json
from delta_collector.orderbook_engine_v1 import OrderBookEngine, process_message
from research.quant_protocol_capture_integrity_v1 import audit

def test_replay_checks_snapshot_and_incremental_checksum(tmp_path):
    p=tmp_path/"session_part_0001.jsonl.gz"
    engine=OrderBookEngine()
    snap={"type":"ob_updates","action":"snapshot","seq":10,"ts":100,"cs":0,
          "a":[["101","3"],["102","4"]],"b":[["100","5"],["99","6"]]}
    process_message(engine,snap); snap["cs"]=engine.checksum()
    update={"type":"ob_updates","action":"update","seq":11,"ts":200,"cs":0,
            "a":[["101","7"]],"b":[["100","8"]]}
    process_message(engine,update); update["cs"]=engine.checksum()
    with gzip.open(p,"wt") as f:
        f.write(json.dumps({"message":snap})+"\n")
        f.write(json.dumps({"message":update})+"\n")
    result=audit([str(p)])
    assert result["status"]=="PASS"
    assert result["orderbook"]["seen"]==2
    assert result["orderbook"]["checksum_ok"]==2
    assert result["orderbook"]["sequence_or_reconstruction_errors"]==0
