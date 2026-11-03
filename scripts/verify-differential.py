"""Exercise real isolated base/head/patched checks for the three trusted fixture profiles."""
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from config import settings
from schemas.contracts import Patch, FileEdit
from verification.runner import VerificationRunner


def main():
    root=Path(__file__).resolve().parents[1]
    images=json.loads(subprocess.check_output(['docker','image','inspect','proofline-verification:python','proofline-verification:node']))
    os.environ['PROOFLINE_VERIFICATION_IMAGE']=images[0]['RepoDigests'][0]
    os.environ['PROOFLINE_NODE_VERIFICATION_IMAGE']=images[1]['RepoDigests'][0]
    settings.execution_enabled=True
    results=[]
    for language,suffix in [('python','py'),('javascript','cjs'),('typescript','ts')]:
        directory=root/'fixtures/differential'/language
        name='contract.'+suffix
        patch=Patch(run_id='differential-smoke',finding_id=language,edits=[FileEdit(path=name,
            old_content=(directory/'head'/name).read_text(),replacement=(directory/'base'/name).read_text(),rationale='Restore empty-input contract')])
        success,message=VerificationRunner(directory/'head').verify_patch(patch,language+'_contract')
        results.append({'language':language,'success':success,'message':message,'patch':patch.model_dump()})
        print(language,success,message,flush=True)
    output=root/'evals/results/differential-execution.json'
    output.write_text(json.dumps(results,indent=2))
    return 0 if all(row['success'] for row in results) else 1


if __name__=='__main__':
    raise SystemExit(main())
