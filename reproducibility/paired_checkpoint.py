"""Preserve each completed observation once without rewriting previous cases."""
from pathlib import Path
import json,uuid

class PairedCheckpoint:
    """An owned attempt's append-only evidence; never a completion certificate.

    The validator still writes its original complete paired report at the end.
    A new attempt gets a new journal, preserving interrupted observations.
    """
    def __init__(self,output,name):
        output=Path(output);output.mkdir(parents=True,exist_ok=True)
        if Path(name).name!=name:raise ValueError('Checkpoint name must be local.')
        self.path=output/(name+'-checkpoint-'+uuid.uuid4().hex+'.jsonl')
        self.path.open('xb').close()

    def append(self,row):
        # Keep the original JSON numeric tokens, fields and nesting. This is
        # transport, not encoding, comparison, filtering or scientific scoring.
        payload=(json.dumps(row,ensure_ascii=False,separators=(',',':'))+'\n').encode('utf-8')
        with self.path.open('ab') as stream:stream.write(payload)
