from pathlib import Path
import json, hashlib, subprocess, difflib
ROOT=Path.cwd(); V=ROOT.parents[1]/'vendor/DeepTutor'; REPO=ROOT.parents[2]
PIN=V/'UPSTREAM_SNAPSHOT.json'; pin=json.loads(PIN.read_text('utf-8'))
sha=lambda b:hashlib.sha256(b).hexdigest()
cache=ROOT/'.runtime/browser-check-12d290667b/task0-upstream'
changes={x['path']:x for x in pin['local_changes']}; deletes={x['path']:x for x in pin['local_deletions']}
for rel in ['web/app/(workspace)/learning/journal/page.tsx','web/features/heart/AssessmentEvidence.tsx','web/components/learning/LearningScrollRestoration.tsx','web/tests/assessment-evidence.spec.tsx','web/tests/learning-scroll-restoration.spec.tsx']:
    changes.setdefault(rel, {'path':rel,'local_sha256':'pending'})
affected=[]
for rel, expected in pin['files'].items():
    p=V/rel
    if p.exists():
        if sha(p.read_bytes())!=changes.get(rel,{}).get('local_sha256',expected): affected.append(rel)
    elif rel not in deletes: affected.append(rel)
for rel,row in changes.items():
    p=V/rel
    if rel not in pin['files'] and (not p.exists() or sha(p.read_bytes())!=row['local_sha256']):affected.append(rel)
affected.extend(row['path'] for row in [*changes.values(),*deletes.values()] if row.get('patch')=='LOCAL_PATCHES/student-learning-task5.patch')
print('AFFECTED',len(set(affected)),flush=True)
def original(rel):
    expected=pin['files'].get(rel)
    if expected is None:return b''
    p=cache/rel
    if p.exists() and sha(p.read_bytes())==expected:return p.read_bytes()
    path='project/vendor/DeepTutor/'+rel
    commits=['HEAD']+subprocess.check_output(['git','log','--all','--format=%H','--',path],cwd=REPO).decode().splitlines()
    for commit in dict.fromkeys(commits):
        r=subprocess.run(['git','show',commit+':'+path],cwd=REPO,capture_output=True)
        if r.returncode==0 and sha(r.stdout)==expected:
            p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(r.stdout);return r.stdout
    raise RuntimeError('original not found '+rel)
patch=[]; rows=[]
for rel in sorted(set(affected)):
    before=original(rel); p=V/rel; after=p.read_bytes() if p.exists() else b''
    a='a/project/vendor/DeepTutor/'+rel;b='b/project/vendor/DeepTutor/'+rel
    patch.append('diff --git '+a+' '+b+'\n')
    if not before:patch.append('new file mode 100644\n')
    if not p.exists():patch.append('deleted file mode 100644\n')
    diff=''.join(difflib.unified_diff(before.decode('utf-8-sig').splitlines(True),after.decode('utf-8-sig').splitlines(True),fromfile=a if before else '/dev/null',tofile=b if p.exists() else '/dev/null'))
    patch.append(diff)
    entry={'path':rel,'upstream_sha256':pin['files'].get(rel),'patch':'LOCAL_PATCHES/student-learning-task5.patch','reason':'任务 5：学习概览、路径与档案、按需证据和返回位置'}
    if p.exists():
        entry['local_sha256']=sha(after);changes[rel]=entry
    else:
        changes.pop(rel,None);deletes[rel]=entry
    rows.append({'path':rel,'action':'modify' if p.exists() else 'delete'})
(V/'LOCAL_PATCHES/student-learning-task5.patch').write_text(''.join(patch),encoding='utf-8',newline='\n')
pin['local_changes']=sorted(changes.values(),key=lambda x:x['path']);pin['local_deletions']=sorted(deletes.values(),key=lambda x:x['path'])
PIN.write_text(json.dumps(pin,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
errors=[]
for rel,expected in pin['files'].items():
    p=V/rel
    if rel in deletes:
        if p.exists():errors.append('deleted file present '+rel)
    elif not p.exists() or sha(p.read_bytes())!=changes.get(rel,{}).get('local_sha256',expected):errors.append('hash mismatch '+rel)
for row in changes.values():
    p=V/row['path']
    if not p.exists() or sha(p.read_bytes())!=row['local_sha256']:errors.append('local mismatch '+row['path'])
    if not (V/row['patch']).exists():errors.append('patch missing '+row['path'])
assert not errors,errors
result=subprocess.run(['git','apply','--check','--reverse','--ignore-space-change',str(V/'LOCAL_PATCHES/student-learning-task5.patch')],cwd=REPO,capture_output=True)
assert result.returncode==0,result.stderr.decode('utf-8',errors='replace')
report={'baseline_files':len(pin['files']),'local_changes':len(changes),'local_deletions':len(deletes),'task5':rows,'hash_errors':errors,'reverse_patch_check':True}
(ROOT/'.runtime/task5-provenance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k!='task5'}),flush=True)
