"""不依赖流程平台，直接运行同一套业务接口。"""
import argparse
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / 'src'))
from cooling_lab.api import CoolingSession


def main():
    parser = argparse.ArgumentParser(description='Standalone simulated cooling diagnosis')
    parser.add_argument('--scenario', choices=['filter', 'fan', 'healthy', 'unknown', 'fan_stuck'], default='fan')
    parser.add_argument('--device-id', default='COOL-01')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    session = CoolingSession(args.scenario, args.device_id)
    if not session.is_overheated():
        result = session.report_healthy()
    else:
        with ThreadPoolExecutor(max_workers=2) as pool:
            air = pool.submit(session.collect_air)
            fan = pool.submit(session.collect_fan)
            air_sample, fan_sample = air.result(), fan.result()
        if session.filter_is_blocked(air_sample):
            session.clean_filter()
            result = session.report_filter()
        elif session.fan_is_faulty(fan_sample):
            asyncio.run(session.restart_fan())
            result = session.report_fan()
        else:
            print(json.dumps({'status': 'failed', 'reason': 'Neither known cause matched',
                              **session.summary()}, ensure_ascii=False, indent=2))
            return 2
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(result['chartSvg'], encoding='utf-8')
    print(json.dumps({key: value for key, value in result.items() if key != 'chartSvg'},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
