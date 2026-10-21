"""Retire only bounded terminal snapshot aliases covered by verified packets."""
import argparse
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import shutil
import stat
import sys
import time

from reproducibility import compact_evidence as c
from reproducibility import source_retention as retention


def retire(packet, store, *, receipt_name='retirement.json', resume_from=None):
    packet, store = Path(packet).resolve(), Path(store).resolve()
    c.guard(store)
    plan_path = packet / 'plan.json'
    plan = json.loads(plan_path.read_text())
    proof = json.loads((packet / 'verification.json').read_text())
    consumer = json.loads((packet / 'link-limit-consumer-check.json').read_text())
    run = json.loads((packet / 'run.json').read_text())
    identity = c.digest(plan_path)
    if (not proof['passed'] or not run['passed'] or run['status'] != 'finished' or
            proof['plan_sha256'] != identity or consumer['plan_sha256'] != identity or
            consumer['running_command_reference_matches'] != 0 or
            proof['run_receipt_sha256'] != c.digest(packet / 'run.json') or
            proof['cleanup_chain_file_sha256'] != c.digest(packet / 'cleanup-chain.jsonl.gz')):
        raise ValueError('Retirement requires the unchanged verified packet and consumer decision')
    versions = plan['versions']
    if not 0 < len(versions) <= 20 or any(not 0 < v['files'] <= 20000 for v in versions):
        raise ValueError('Snapshot selection exceeds the explicit bounds')
    retired_keys = set()
    last, _, count, _, _ = c.journal_state(packet / 'cleanup-chain.jsonl.gz', identity, retired_keys)
    if count != proof['files'] or last != proof['last_record_sha256']:
        raise ValueError('Recovery chain does not match the completed verification')
    # Refresh command/cwd evidence just before deletion. Never stop another job.
    import psutil
    roots = [str(Path(v['snapshot']).resolve()).casefold() for v in versions]
    matches = []
    for process in psutil.process_iter(['pid', 'name', 'cmdline']):
        if not (process.info['name'] or '').lower().startswith(('python', 'rscript', 'r.exe', 'java')):
            continue
        try:
            command = ' '.join(process.info['cmdline'] or []).casefold()
            cwd = process.cwd().casefold()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        if any(root in command or cwd == root or cwd.startswith(root + '\\') for root in roots):
            matches.append(process.pid)
    if matches:
        raise ValueError('Running source consumers remain: ' + str(matches))
    # Freeze exact standalone driver and its helpers; independent canonical
    # copies keep subsequent worktree edits from changing recoverable code.
    producers = []
    for source in (Path(__file__), Path(retention.__file__), Path(c.__file__)):
        row = {'path': 'reproducibility/' + source.name, 'size': source.stat().st_size,
               'sha256': c.digest(source, True)}
        blob = c.object_path(store, row['sha256'])
        blob.parent.mkdir(parents=True, exist_ok=True)
        if not blob.exists():
            with source.open('rb') as reader, blob.open('xb') as writer:
                shutil.copyfileobj(reader, writer, c.BLOCK)
        c.validate(blob, row)
        blob.chmod(stat.S_IREAD)
        producers.append(row)
    if receipt_name != 'retirement.json' and not (receipt_name.startswith('retirement-') and receipt_name.endswith('.json')):
        raise ValueError('Use a distinct retirement receipt name')
    receipt_path = c.owned(packet, receipt_name)
    previous = json.loads(receipt_path.read_text()) if receipt_path.exists() else None
    if previous and previous['producers'] != producers:
        raise ValueError('Retirement producer changed; preserve its previous receipt')
    producer_manifest = packet / ('retirement-producers-' + c.chain_hash({'producers':producers})[:12] + '.jsonl.gz')
    if producer_manifest.exists():
        if list(c.entries(producer_manifest)) != producers:
            raise ValueError('Retained producer manifest changed')
    else:
        with gzip.open(producer_manifest, 'wt', encoding='utf-8') as stream:
            for row in producers:
                stream.write(json.dumps(row, sort_keys=True, separators=(',', ':')) + '\n')
    resumed = None
    if not previous and resume_from is not None:
        resume_path = c.owned(packet, resume_from)
        resumed = json.loads(resume_path.read_text())
        if resumed['status'] != 'finished' or resumed['plan_sha256'] != identity:
            raise ValueError('Resume only a completed retirement attempt for this plan')
    rows = list(previous['versions']) if previous else list(resumed['versions']) if resumed else []
    receipt = {'schema_version': 1, 'command': sys.argv, 'python': sys.version,
               'plan_sha256': identity, 'verification_sha256': c.digest(packet / 'verification.json'),
               'object_store': str(store), 'producers': producers, 'versions': rows,
               'producer_manifest': producer_manifest.name,
               'producer_manifest_sha256': c.digest(producer_manifest),
               'psutil_version': psutil.__version__,
               'resumed_receipt': previous.get('resumed_receipt') if previous else resume_from,
               'resumed_receipt_sha256': (previous.get('resumed_receipt_sha256') if previous else
                                          c.digest(c.owned(packet,resume_from)) if resumed else None),
               'minimum_free_ram_bytes': c.RAM_FLOOR, 'active_consumer_matches': matches,
               'status': 'running', 'passed': False, 'scientific_cases': 0,
               'scientific_approval_changed': False, 'failures': []}
    c.atomic_json(receipt_path, receipt)
    verified_objects = set()
    for version in versions:
        manifest = packet / version['manifest']
        if c.digest(manifest) != version['manifest_sha256']:
            raise ValueError('Version manifest changed')
        prior = next((r for r in reversed(rows) if r['version'] == version['id']), None)
        if prior and prior.get('directory_absent'):
            if (prior['manifest_sha256'] != version['manifest_sha256'] or
                    prior['source_paths_retired'] != version['files'] or Path(version['snapshot']).exists()):
                raise ValueError('Previously retired snapshot unexpectedly exists')
            continue
        already = {r['path'] for i, r in enumerate(c.entries(manifest))
                   if (version['id'], i) in retired_keys}
        directory_manifest = None
        directory_record_path = packet / ('directory-state-' + version['id'] + '.json')
        if directory_record_path.exists():
            directory_record = json.loads(directory_record_path.read_text())
            directory_manifest = c.owned(packet,directory_record['directory_manifest'])
            if c.digest(directory_manifest) != directory_record['directory_manifest_sha256']:
                raise ValueError('Captured directory state changed')
        while True:
            try:
                removed = retention.retire_snapshot(version['snapshot'], manifest, store,
                            already_retired=already,
                            directory_manifest=directory_manifest,
                            verified_objects=verified_objects,
                            journal_path=packet / ('retirement-' + version['id'] + '.jsonl.gz'))
                row = {'version': version['id'], 'snapshot': version['snapshot'],
                       'source_paths_retired': removed, 'directory_absent': True,
                       'manifest': version['manifest'], 'manifest_sha256': version['manifest_sha256'],
                       'retirement_chain': 'retirement-' + version['id'] + '.jsonl.gz'}
                if directory_manifest is not None:
                    row.update(directory_manifest=directory_manifest.name,
                               directory_manifest_sha256=c.digest(directory_manifest))
                break
            except c.ResourcePause as error:
                receipt.update(status='resource-paused', pause_reason=str(error))
                c.atomic_json(receipt_path, receipt)
                time.sleep(5)
            except ValueError as error:
                row = {'version': version['id'], 'snapshot': version['snapshot'],
                       'directory_absent': False, 'preserved_reason': str(error)}
                receipt['failures'].append(row)
                break
        rows.append(row)
        receipt.update(status='running')
        c.atomic_json(receipt_path, receipt)
    receipt.update(status='finished', passed=not receipt['failures'],
                   finished_at=datetime.now(timezone.utc).isoformat())
    c.atomic_json(receipt_path, receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packet', type=Path, required=True)
    parser.add_argument('--store', type=Path, required=True)
    parser.add_argument('--receipt-name', default='retirement.json')
    parser.add_argument('--resume-from')
    args = parser.parse_args()
    result = retire(args.packet, args.store, receipt_name=args.receipt_name, resume_from=args.resume_from)
    print(json.dumps(result), flush=True)
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
