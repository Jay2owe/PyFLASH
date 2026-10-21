"""Interrupted observations survive and later attempts cannot replace them."""
import json,math
from reproducibility.paired_checkpoint import PairedCheckpoint

def test_checkpoint_preserves_complete_observations_before_interruption(tmp_path):
    checkpoint=PairedCheckpoint(tmp_path,'native-pairs')
    rows=[{'item':{'key':'one','values':[1,2.5,None,'κ']},'actual':[[1.,-0.]],'error':None},
          {'item':{'key':'two'},'actual':[float('inf'),float('nan')],'error':'retained failure'}]
    checkpoint.append(rows[0]);first=checkpoint.path.read_bytes()
    checkpoint.append(rows[1]);assert checkpoint.path.read_bytes().startswith(first)
    observed=[json.loads(line) for line in checkpoint.path.read_text(encoding='utf-8').splitlines()]
    assert observed[0]==rows[0]
    assert observed[1]['item']==rows[1]['item'] and observed[1]['error']==rows[1]['error']
    assert math.isinf(observed[1]['actual'][0]) and math.isnan(observed[1]['actual'][1])
    assert math.copysign(1.,observed[0]['actual'][0][1])==-1.

def test_new_attempt_retains_original_failed_attempt_bytes(tmp_path):
    original=PairedCheckpoint(tmp_path,'native-pairs');original.append({'error':'original failure'})
    frozen=original.path.read_bytes()
    later=PairedCheckpoint(tmp_path,'native-pairs');later.append({'error':None,'actual':[3.]})
    assert later.path!=original.path and original.path.read_bytes()==frozen
    assert json.loads(later.path.read_text())=={'error':None,'actual':[3.]}
