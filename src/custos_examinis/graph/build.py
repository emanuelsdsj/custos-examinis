from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from custos_examinis.agents.aggregate import make_aggregate_node
from custos_examinis.agents.code_quality import make_code_quality_node
from custos_examinis.agents.guardrail import make_guardrail_node
from custos_examinis.agents.secrets import make_secrets_node
from custos_examinis.agents.vulnerability import make_vulnerability_node
from custos_examinis.domain.state import AuditState
from custos_examinis.llm.router import ModelRouter


def build_audit_graph(
    router: ModelRouter,
) -> CompiledStateGraph[AuditState, None, AuditState, AuditState]:
    graph = StateGraph[AuditState, None, AuditState, AuditState](AuditState)

    # mypy cannot solve NodeInputT from a factory-returned Callable value against
    # add_node's Protocol-union overloads (it works fine for inline `async def`
    # literals); each node function is otherwise fully typed against AuditState.
    graph.add_node("vulnerability_agent", make_vulnerability_node(router))  # type: ignore[call-overload]
    graph.add_node("code_quality_agent", make_code_quality_node(router))  # type: ignore[call-overload]
    graph.add_node("secrets_agent", make_secrets_node(router))  # type: ignore[call-overload]
    graph.add_node("aggregate", make_aggregate_node(router))  # type: ignore[call-overload]
    graph.add_node("guardrail", make_guardrail_node())  # type: ignore[call-overload]

    graph.add_edge(START, "vulnerability_agent")
    graph.add_edge(START, "code_quality_agent")
    graph.add_edge(START, "secrets_agent")

    graph.add_edge("vulnerability_agent", "aggregate")
    graph.add_edge("code_quality_agent", "aggregate")
    graph.add_edge("secrets_agent", "aggregate")

    graph.add_edge("aggregate", "guardrail")
    graph.add_edge("guardrail", END)

    return graph.compile()
