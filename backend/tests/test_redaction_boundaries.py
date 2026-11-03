from ingestion.redactor import redact_secrets


def test_secret_redaction_covers_json_url_and_authorization():
    text='{"client_secret":"not-a-real-secret-value"}\nhttps://demo:pretend-password@example.invalid/path\nAuthorization: Bearer fictional-token-1234567890'
    safe,count=redact_secrets(text)
    assert count>=3
    assert 'not-a-real-secret-value' not in safe
    assert 'pretend-password' not in safe
    assert 'fictional-token-1234567890' not in safe
    assert 'example.invalid/path' in safe


def test_github_app_and_project_key_patterns_are_redacted():
    token='ghu_'+'A'*36
    key='sk-proj-'+'B'*45
    safe,count=redact_secrets(token+' '+key)
    assert token not in safe and key not in safe and count==2


def test_nested_tool_source_is_redacted_before_json_escaping():
    import json

    from ingestion.redactor import redact_value
    output={'text':'1: api_key = "fictional-client-secret"','nested':[{'client_secret':'another-fictional-secret'}]}
    safe=json.dumps(redact_value(output))
    assert 'fictional-client-secret' not in safe
    assert 'another-fictional-secret' not in safe
    assert 'REDACTED_SECRET' in safe
