"""Stateless Gemini Interactions transport, with no implicit continuation/tool execution."""

from types import SimpleNamespace


def request_interaction(client, model, request, schema, thinking, timeout, max_output):
    generation = {"max_output_tokens": min(request.max_output_tokens, max_output)}
    if thinking != "default":
        if model.startswith("gemini-2.5"):
            raise ValueError("Gemini 2.5 token thinking budgets require generate_content mode; use auto")
        generation["thinking_level"] = thinking
    response = client.interactions.create(
        model=model,
        input=request.context,
        system_instruction=request.system_instruction,
        response_format={"type": "text", "mime_type": "application/json", "schema": schema.model_json_schema()},
        generation_config=generation,
        store=False,
        background=False,
        stream=False,
        automatic_continuation=False,
        timeout=timeout,
    )
    usage = getattr(response, "usage", None)
    metadata = SimpleNamespace(
        prompt_token_count=getattr(usage, "total_input_tokens", 0) or 0,
        candidates_token_count=getattr(usage, "total_output_tokens", 0) or 0,
        total_token_count=getattr(usage, "total_tokens", 0) or 0,
        cached_content_token_count=getattr(usage, "total_cached_tokens", 0) or 0,
        thoughts_token_count=getattr(usage, "total_thought_tokens", 0) or 0,
    )
    text = getattr(response, "output_text", None)
    if text is None:
        outputs = [
            step for step in (getattr(response, "steps", None) or []) if getattr(step, "type", None) == "model_output"
        ]
        text = (
            "".join(
                getattr(block, "text", "")
                for block in (getattr(outputs[-1], "content", None) or [])
                if getattr(block, "type", None) == "text"
            )
            if outputs
            else ""
        )
    status = getattr(response, "status", None)
    reason = "STOP" if status == "completed" else "INTERACTION_" + str(status or "unknown").upper()
    return SimpleNamespace(
        text=text, usage_metadata=metadata, candidates=[SimpleNamespace(finish_reason=SimpleNamespace(name=reason))]
    )
