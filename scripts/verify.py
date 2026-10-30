"""统一运行现有验证脚本；真实引擎使用临时数据库和随机本地端口。"""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from flowable_bridge import engine_request
from python_sessions import stop_process

SHARED_ENGINE = {'verify-flowable.py', 'verify-diagnostic-review.py',
                 'verify-human-decisions.py', 'verify-component-decisions.py'}
OWN_ENGINE = {'verify-diagnosis-flowable.py', 'verify-diagnosis-execution.py',
              'verify-native-flowable.py', 'verify-cooling-example.py',
              'verify-action-confirmation.py', 'verify-review-concurrency.py'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--group', choices=['unit', 'engine', 'all'], default='all')
    local_python = ROOT / 'backend/.local/venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    parser.add_argument('--python', default=os.environ.get('PYTHON') or (
        str(local_python) if local_python.is_file() else sys.executable))
    args = parser.parse_args()
    checks = sorted([*ROOT.glob('scripts/verify-*.py'), *ROOT.glob('scripts/verify-*.mjs')])
    engine_checks = SHARED_ENGINE | OWN_ENGINE
    assert engine_checks <= {path.name for path in checks}, 'Unknown engine verification script'
    checks = [path for path in checks if args.group == 'all'
              or (path.name in engine_checks) == (args.group == 'engine')]
    logs = ROOT / 'backend/.local/verification'
    logs.mkdir(parents=True, exist_ok=True)
    environment = {**os.environ, 'PYTHONUTF8': '1', 'PYTHONUNBUFFERED': '1', 'PYTHON': args.python}
    results = []

    def run(command, name, timeout=600):
        path = logs / (name + '.log')
        started = time.monotonic()
        with path.open('w', encoding='utf-8') as log:
            process = subprocess.Popen(command, cwd=ROOT, env=environment, stdout=log, stderr=log,
                **({'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}))
            try:
                code = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                stop_process(process)
                code = -1
                log.write('\nVerification timed out\n')
        results.append({'name': name, 'exitCode': code, 'seconds': round(time.monotonic() - started, 2)})
        print(('PASS ' if code == 0 else 'FAIL ') + name, flush=True)
        if code:
            print(path.read_text(encoding='utf-8', errors='replace')[-16000:], flush=True)

    with tempfile.TemporaryDirectory(prefix='verification-engine-') as directory:
        engine = None
        with (logs / 'engine.log').open('w', encoding='utf-8') as log:
            try:
                if any(path.name in SHARED_ENGINE for path in checks):
                    with socket.socket() as available:
                        available.bind(('127.0.0.1', 0))
                        port = available.getsockname()[1]
                    host = f'http://127.0.0.1:{port}'
                    environment['FLOWABLE_URL'] = host
                    os.environ['FLOWABLE_URL'] = host
                    engine = subprocess.Popen(['java', '-jar',
                        str(ROOT / 'flowable-runtime/target/diagnostic-flowable-1.0.0.jar'),
                        f'--server.port={port}', '--spring.datasource.url=jdbc:h2:mem:verification;DB_CLOSE_DELAY=-1'],
                        cwd=directory, env=environment, stdout=log, stderr=log,
                        **({'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}))
                    deadline = time.monotonic() + 60
                    while True:
                        try:
                            engine_request('/process-api/management/engine')
                            break
                        except RuntimeError:
                            if engine.poll() is not None or time.monotonic() >= deadline:
                                raise RuntimeError('Verification engine failed to start; see ' + str(logs / 'engine.log'))
                            time.sleep(0.2)
                for path in checks:
                    command = [args.python, '-B', '-u', str(path)] if path.suffix == '.py' else ['node', str(path)]
                    run(command, path.name)
            finally:
                stop_process(engine)
                (logs / 'results.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
    failed = [result['name'] for result in results if result['exitCode']]
    print(f'{len(results) - len(failed)}/{len(results)} checks passed; logs: {logs}', flush=True)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
