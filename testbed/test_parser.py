"""Synthetic-only regression tests. Never interprets real Redis logs."""
import csv
import subprocess
import sys
import tempfile
from pathlib import Path

PARSER=Path(__file__).with_name('parse_wflog.py')

def run_with(logtext,nodes='node0\nnode1\n',sub='version,submit_epoch_ms\n1,1000\n'):
    with tempfile.TemporaryDirectory() as td:
        d=Path(td)
        (d/'submit.csv').write_text(sub)
        (d/'nodes.csv').write_text('node_id\n'+nodes)
        (d/'log.txt').write_text(logtext)
        return subprocess.run([sys.executable,str(PARSER),str(d/'submit.csv'),str(d/'log.txt'),'--expected-nodes',str(d/'nodes.csv')],capture_output=True,text=True)

missing=run_with('[REDIS] [Patch Applied] [1100] [node0] [1] [eager]\n')
assert missing.returncode == 0,missing.stderr
r=list(csv.DictReader(missing.stdout.splitlines()))[0]
assert (r['nodes_applied'],r['nodes_total'],r['update_lag_ms'],r['mixed_version_window_ms']) == ('1','2','inf','inf'),r
print('PASS parser 1/4: fully silent expected node prevents false completion')

full=run_with('[REDIS] [Patch Applied] [1100] [node0] [1] [eager]\n[REDIS] [Patch Applied] [1120] [node1] [1] [eager]\n')
assert full.returncode == 0,full.stderr
r=list(csv.DictReader(full.stdout.splitlines()))[0]
assert (r['nodes_applied'],r['nodes_total'],r['update_lag_ms'],r['mixed_version_window_ms']) == ('2','2','120.000','20.000'),r
print('PASS parser 2/4: complete cluster reports correct lag and skew')

unknown=run_with('[REDIS] [Patch Applied] [1100] [node4] [1] [eager]\n')
assert unknown.returncode != 0 and 'unknown node IDs' in unknown.stderr,unknown.stderr
print('PASS parser 3/4: unknown node ID rejected')

absent=run_with('[REDIS] [Patch Applied] [1120] [node0] [2] [eager]\n')
assert absent.returncode == 0,absent.stderr
r=list(csv.DictReader(absent.stdout.splitlines()))[0]
assert r['nodes_applied']=='0' and r['update_lag_ms']=='inf',r
print('PASS parser 4/4: requested version with no applications is incomplete')
