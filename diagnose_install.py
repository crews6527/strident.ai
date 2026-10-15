"""Identify the local build and optional direct model check; no config writes."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from pcs_agent import __version__
from pcs_agent.brain import direct_plan
from pcs_agent.compliance import request_url
from pcs_agent.config import config_path, validate
from pcs_agent.provider import Ollama


def installation_report(root=None, command='Check compliance', config=None):
    root = Path(root or Path(__file__).resolve().parent).resolve()
    if config is None:
        settings = config_path()
        if settings.exists() and settings.stat().st_size > 128000:
            raise ValueError('Settings file exceeds the read limit.')
        config = validate(json.loads(settings.read_text(encoding='utf-8')) if settings.exists() else {})
    target = request_url(command, config['store_url'])
    direct = None if target else direct_plan(command)
    return {'version': __version__, 'source_folder': str(root), 'python': sys.executable,
            'source_origin': 'local extracted/installed files; no automatic GitHub sync',
            'runtime_sha256': hashlib.sha256((root / 'pcs_agent/runtime.py').read_bytes()).hexdigest(),
            'command_sha256': hashlib.sha256(command.encode()).hexdigest(), 'command_characters': len(command),
            'route': 'compliance checks' if target else 'direct' if direct else 'model',
            'will_call_ollama': not (target or direct),
            'selected_model': config['model'], 'ollama_url': config['ollama_url'],
            'model_timeout': config['model_timeout'], 'task_timeout': config['task_timeout'],
            'task_timeout_semantics':'worker inactivity, renewed by actual progress',
            'max_task_seconds':config.get('max_task_seconds',900)}


def collect_model_evidence(config):
    result = {}
    import psutil
    memory = psutil.virtual_memory()
    result['memory'] = {'total_bytes': memory.total, 'available_bytes': memory.available, 'percent': memory.percent}
    client = Ollama(config)
    try:
        info = client.inspect()
        result['ollama_version'] = info['version']
        result['installed_models'] = info['models']
        result['running_models'] = [{k: m.get(k) for k in ('name', 'size', 'size_vram', 'context_length')} for m in client.json('/api/ps').get('models', [])]
    except Exception as exc:
        result['connection_error'] = str(exc)
        return result
    if not config['model']:
        result['model_probe'] = {'ok': False, 'error': 'No model is selected. No model was substituted.'}
        return result
    from diagnose_ollama import run_check
    print('Testing the exact selected model with a short text-only request; settings remain unchanged.', flush=True)
    result['model_probe'] = run_check(config, emit=lambda text: print(text, flush=True))
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--offline', action='store_true')
    parser.add_argument('--command-file', type=Path)
    parser.add_argument('--output', type=Path, default=Path.home() / 'Downloads/Strident_Diagnostics.json')
    args = parser.parse_args()
    command = 'Check compliance'
    if args.command_file:
        if args.command_file.stat().st_size > 24000:
            raise ValueError('Use a UTF-8 command file smaller than 24 KB.')
        command = args.command_file.read_text(encoding='utf-8-sig')
    path = config_path()
    if path.exists() and path.stat().st_size > 128000:
        raise ValueError('Settings file exceeds the read limit.')
    config = validate(json.loads(path.read_text(encoding='utf-8')) if path.exists() else {})
    report = installation_report(command=command, config=config)
    report['check_compliance_bypasses_model'] = installation_report(config=config)['will_call_ollama'] is False
    fixture = Path(__file__).parent / 'tests/fixtures/compliance_request.txt'
    report['full_checklist_bypasses_model'] = installation_report(command=fixture.read_text(encoding='utf-8'), config=config)['will_call_ollama'] is False
    print(json.dumps(report, indent=2), flush=True)
    if not args.offline:
        report['model_evidence'] = collect_model_evidence(config)
        probe = report['model_evidence'].get('model_probe', {})
        print('MODEL PROBE: ' + ('PASS' if probe.get('ok') else 'FAILED: ' + probe.get('error', report['model_evidence'].get('connection_error', 'No result'))), flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print('Saved: ' + str(args.output), flush=True)
    print('The diagnostic contains build/route/model results, not your command text, history or settings keys.', flush=True)
    return 0 if report['check_compliance_bypasses_model'] and report['full_checklist_bypasses_model'] else 1


if __name__ == '__main__':
    import multiprocessing
    multiprocessing.freeze_support()
    raise SystemExit(main())
