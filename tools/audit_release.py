"""Read-only source/bundle hygiene check; never print matched credential values."""
import json
import os
import re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SKIP={'.git','.venv','venv','node_modules','dist','__pycache__','.pytest_cache','.aws','.ssh','.codex','datasets','downloads','test-results','playwright-report'}
PATTERN=re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|sk-[A-Za-z0-9]{24,}')


def audit():
    issues=[];count=0
    for name in ('.gitignore','.dockerignore'):
        text=(ROOT/name).read_text()
        for expected in ('.env','node_modules','.venv','dist','__pycache__'):
            if expected not in text:issues.append(name+': missing exclusion '+expected)
    for folder in ('backend','frontend','public','tools','docs','examples'):
        for current,dirs,files in os.walk(ROOT/folder):
            dirs[:]=[d for d in dirs if d not in SKIP]
            for name in files:
                path=Path(current)/name
                if name.startswith('.env') and name!='.env.example':continue
                if name=='.DS_Store' or path.suffix in ('.pyc','.tsbuildinfo','.log'):continue
                count+=1
                if path.stat().st_size>2*1024*1024:issues.append(str(path.relative_to(ROOT))+': exceeds source review size cap');continue
                if path.suffix in ('.py','.ts','.tsx','.json','.md','.yaml','.lock','.cjs') and PATTERN.search(path.read_bytes()):
                    issues.append(str(path.relative_to(ROOT))+': potential secret pattern')
    files=list((ROOT/'frontend/dist').rglob('*'))
    bundles=[p for p in files if p.is_file()]
    present=[os.environ[n].encode() for n in ('BASETEN_API_KEY','RECOMMENDATION_AUTH_TOKEN','SEGMENTATION_AUTH_TOKEN') if os.environ.get(n)]
    for path in bundles:
        body=path.read_bytes()
        if any(secret in body for secret in present):issues.append(str(path.relative_to(ROOT))+': contains a current credential value')
        if path.suffix in ('.js','.html') and (b'BASETEN_API_KEY' in body or b'SEGMENTATION_AUTH_TOKEN' in body):
            issues.append(str(path.relative_to(ROOT))+': backend credential variable referenced in browser artifact')
    if not bundles:issues.append('Frontend build missing')
    report={'status':'failed' if issues else 'passed','source_files_checked':count,'built_files_checked':len(bundles),
            'current_credential_values_checked':len(present),'issues':issues,
            'limits':'Heuristic file/bundle review, not a verified Git index or exhaustive secret scanner.'}
    print(json.dumps(report,indent=2));return report

if __name__=='__main__':raise SystemExit(0 if audit()['status']=='passed' else 1)
