"""Build/check a complete tool inventory for the deferred consolidated campaign."""
from __future__ import annotations
import argparse
import ast
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/'catalog/verification_campaign.json'


def build():
    registry=json.loads((ROOT/'catalog/mcp_tool_registry.json').read_text(encoding='utf-8'))
    source=ROOT/'tests/integration/test_corel_live.py'
    tree=ast.parse(source.read_text(encoding='utf-8'))
    gates={}
    for cls in tree.body:
        if not isinstance(cls,ast.ClassDef): continue
        for method in cls.body:
            if not isinstance(method,ast.FunctionDef) or not method.name.startswith('test_'): continue
            calls={node.func.attr for node in ast.walk(method) if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute)}
            calls.update(node.attr for node in ast.walk(method) if isinstance(node,ast.Attribute)
                         and isinstance(node.value,ast.Attribute) and node.value.attr=='bridge')
            gates[cls.name+'.'+method.name]=calls
    entries=[]
    for tool in registry['tools']:
        if tool['implementation']['state']!='registered': continue
        name=tool['name']; method=tool['implementation'].get('bridge_method','').split('.')[-1]
        native=bool(tool.get('api_requirements'))
        prepared=[gate for gate,calls in gates.items() if method in calls or name in calls] if native else []
        sources=[s for s in tool.get('test_evidence',{}).get('sources',[]) if s.startswith('tests/') and (ROOT/s).is_file()]
        entries.append({'tool':name,'implementation_status':tool['status'],'local_test_sources':sources,
            'native_coverage':'prepared_pending_run' if prepared else ('missing_explicit_gate' if native else 'local_only'),
            'native_gate_candidates':prepared,'native_result':'not_run' if native else 'not_applicable',
            'mcp_envelope_result':'pending_consolidated_client_run',
            'manual_artifact_review':'pending' if native and tool['permission']=='mutating' else 'not_applicable'})
    return {'schema':'verification-campaign-v1','live_policy':'deferred_by_user',
        'scope':'Every registered MCP tool; native candidates are call-site evidence, not proof of assertions or live success.',
        'tools':entries}


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--check',action='store_true'); args=parser.parse_args()
    result=build()
    if args.check:
        if not OUTPUT.is_file() or json.loads(OUTPUT.read_text(encoding='utf-8'))!=result:
            raise SystemExit('Verification inventory is stale; rebuild it before the consolidated campaign.')
    else: OUTPUT.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    missing=[e['tool'] for e in result['tools'] if e['native_coverage']=='missing_explicit_gate']
    print(f"Coverage inventory {'checked' if args.check else 'built'}: {len(result['tools'])} tools; {len(missing)} need explicit native gates.")
    if missing: print('Missing native gates: '+', '.join(missing))


if __name__=='__main__': main()
