"""Validate external operator-profile loading against a temporary application contract."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from config import settings
from schemas.contracts import FileEdit, Patch
from verification.profiles import TRUSTED_PROFILES, load_operator_profiles
from verification.runner import VerificationRunner


def main():
    root=Path(__file__).resolve().parents[1]
    image=json.loads(subprocess.check_output(['docker','image','inspect','proofline-verification:python']))[0]['RepoDigests'][0]
    os.environ['PROOFLINE_ORDERS_VERIFICATION_IMAGE']=image
    settings.execution_enabled=True
    with tempfile.TemporaryDirectory(prefix='proofline-operator-') as temporary:
        directory=Path(temporary)
        for name in ('base','head','oracle'):
            (directory/name).mkdir()
        good='def quote(cents, discount):\n    return cents - discount\n'
        bad='def quote(cents, discount):\n    return cents\n'
        (directory/'base/orders.py').write_text(good)
        (directory/'head/orders.py').write_text(bad)
        (directory/'oracle/test_orders.py').write_text('from orders import quote\n\ndef test_regression():\n    assert quote(100, 20) == 80\n\ndef test_happy():\n    assert quote(100, 0) == 100\n')
        profile={'profile_id':'orders_discount_smoke','name':'Operator orders contract','description':'Independent operator-owned discount assertions',
            'test_command':[],'runtime':'python','image_env':'PROOFLINE_ORDERS_VERIFICATION_IMAGE','require_base':True,
            'oracle_dir':str(directory/'oracle'),'oracle_file':'test_orders.py','regression_test_id':'test_regression','happy_path_test_id':'test_happy',
            'container_command':['python','-m','pytest','-p','no:cacheprovider','--junitxml=/results/report.xml','/oracle/test_orders.py']}
        config=directory/'profiles.json';config.write_text(json.dumps([profile]))
        os.environ['PROOFLINE_VERIFICATION_PROFILES']=str(config)
        load_operator_profiles()
        assert 'orders_discount_smoke' in TRUSTED_PROFILES
        patch=Patch(run_id='operator-smoke',finding_id='discount',edits=[FileEdit(path='orders.py',old_content=bad,replacement=good,rationale='Restore discount contract')])
        success,message=VerificationRunner(directory/'head').verify_patch(patch,'orders_discount_smoke')
        result={'success':success,'message':message,'profile':profile,'patch':patch.model_dump()}
        (root/'evals/results/operator-profile-execution.json').write_text(json.dumps(result,indent=2))
        print(json.dumps({'success':success,'message':message,'phases':[c.check_name for c in patch.checks]}))
        return 0 if success else 1


if __name__=='__main__':
    raise SystemExit(main())
