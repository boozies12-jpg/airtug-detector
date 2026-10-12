"""Run each known-truth IQ case and retain per-case logs/results."""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
for folder in sorted((ROOT / 'data/decoder-comparison').glob('synthetic-*')):
    with (folder / 'run.log').open('w') as log:
        subprocess.run([sys.executable, str(Path(__file__).with_name('compare_decoders.py')), str(folder)],
                       stdout=log, stderr=subprocess.STDOUT, check=True)
    print(folder.name, 'complete', flush=True)
