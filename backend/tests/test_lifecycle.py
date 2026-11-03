from review.lifecycle import reconcile, stable_identity
from schemas.contracts import Disposition, Finding, FindingCategory, InputMode, Location, ReviewRun, Severity


def make_finding(line=1):
    return Finding(run_id="old",stable_fingerprint="same",category=FindingCategory.BUG,rule_id="ruff:B006",title="Mutable default",explanation="Shared state",user_impact="State leak",severity=Severity.MEDIUM,primary_location=Location(path="a.py",start_line=line,end_line=line))


def test_identity_survives_line_shift():
    first=make_finding()
    second=make_finding(3)
    assert stable_identity(first,{"a.py":"def f(items=[]): pass"},[]) == stable_identity(second,{"a.py":"\n\ndef f(items=[]): pass"},[])


def test_missing_model_finding_is_not_declared_fixed():
    old=make_finding()
    old.rule_id="proofline:model-bug"
    previous=ReviewRun(id="old",canonical_repo="repo",input_mode=InputMode.REPO)
    current=ReviewRun(id="new",canonical_repo="repo",input_mode=InputMode.REPO)
    reconcile(current,[],previous,[old])
    assert current.coverage["finding_lifecycle"]["changes"][0]["state"] == "not_redetected"


def test_dismissal_carries_forward():
    old=make_finding()
    old.disposition=Disposition.DISMISSED
    new=make_finding()
    run=ReviewRun(canonical_repo="repo",input_mode=InputMode.REPO)
    reconcile(run,[new],run,[old])
    assert new.disposition == Disposition.DISMISSED
