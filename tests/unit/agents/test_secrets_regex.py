from custos_examinis.agents.secrets import (
    AGENT_NAME,
    ROLE,
    SecretTriageBatch,
    SecretTriageDecision,
    _scan_file,
    make_secrets_node,
)
from custos_examinis.domain.state import initial_state
from custos_examinis.ingest.models import FileSet, IngestedFile
from custos_examinis.llm.router import ModelRouter
from tests.fakes.fake_chat_model import ScriptedChatModel


def test_scan_file_detects_aws_key_without_any_llm_call() -> None:
    content = 'AWS_KEY = "AKIAABCDEFGHIJKLMNOP"\n'
    findings, candidates = _scan_file("config.py", content)

    assert len(findings) == 1
    assert findings[0].rule_id == "secret-aws-access-key"
    assert candidates == []


def test_scan_file_skips_obvious_placeholder_values() -> None:
    content = 'password = "changeme"\n'
    _, candidates = _scan_file("config.py", content)

    assert candidates == []


def test_scan_file_flags_ambiguous_generic_assignment_as_candidate() -> None:
    content = 'api_key = "sk_totally_not_a_placeholder_value"\n'
    findings, candidates = _scan_file("config.py", content)

    assert findings == []
    assert len(candidates) == 1


async def test_secrets_node_skips_triage_call_when_no_candidates() -> None:
    file_set = FileSet(files={"a.py": IngestedFile(path="a.py", content="x = 1", size_bytes=5)})
    fake = ScriptedChatModel(should_raise=True)
    router = ModelRouter.from_models({ROLE: [fake]})
    node = make_secrets_node(router)

    result = await node(initial_state("audit-1", file_set))

    assert result["secret_findings"] == []
    assert result["token_usage"] == []


async def test_secrets_node_adds_finding_for_triaged_secret() -> None:
    content = 'api_key = "sk_totally_not_a_placeholder_value"\n'
    ingested = IngestedFile(path="config.py", content=content, size_bytes=len(content))
    file_set = FileSet(files={"config.py": ingested})
    decision = SecretTriageDecision(index=0, is_secret=True, confidence=0.9)
    batch = SecretTriageBatch(decisions=[decision])
    fake = ScriptedChatModel(structured_response=batch)
    router = ModelRouter.from_models({ROLE: [fake]})
    node = make_secrets_node(router)

    result = await node(initial_state("audit-1", file_set))

    assert len(result["secret_findings"]) == 1
    assert result["secret_findings"][0].agent == AGENT_NAME
