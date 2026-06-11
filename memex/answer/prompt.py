"""
Prompt template for MEMEX chat.

The prompt enforces citation-only answers. This template is non-negotiable.
"""

# Canonical system prompt template
SYSTEM_PROMPT = """You are MEMEX, a personal memory assistant. You have access to the user's
indexed personal documents, notes, and digital history. Your job is to answer
questions using ONLY the provided context below.

Rules (non-negotiable):
1. Only use information from the CONTEXT section. Do not use prior knowledge.
2. Every factual claim MUST be followed by [Source N] citing the source.
3. If the answer is not in the context, say exactly:
   "I don't have information about that in your indexed memory."
4. Do not fabricate, infer beyond the context, or fill gaps with general knowledge.
5. If multiple sources support a claim, cite all relevant ones: [Source 1][Source 3]."""


def build_context(retrieval_results: list) -> str:
    """Build the context section from retrieval results.

    Args:
        retrieval_results: List of RetrievalResult objects.

    Returns:
        Formatted context string with [Source N] markers.
    """
    if not retrieval_results:
        return "No relevant context found."

    parts = []
    for result in retrieval_results:
        captured = result.captured_at.strftime("%Y-%m-%d") if hasattr(result.captured_at, "strftime") else str(result.captured_at)
        source_header = (
            f"[Source {result.citation_index}] "
            f"(captured: {captured}, from: {result.source_type} — {result.source_path})"
        )
        parts.append(f"{source_header}\n{result.content}")

    return "\n\n".join(parts)


def build_history(turns: list[dict], max_turns: int = 6) -> str:
    """Build conversation history section.

    Args:
        turns: List of turn dicts with 'role' and 'content'.
        max_turns: Maximum number of turns to include.

    Returns:
        Formatted conversation history string.
    """
    if not turns:
        return ""

    recent = turns[-max_turns:]
    parts = []
    for turn in recent:
        role = turn.get("role", "user").upper()
        content = turn.get("content", "")
        parts.append(f"{role}: {content}")

    return "\n".join(parts)


def build_prompt(
    query: str,
    retrieval_results: list,
    history_turns: list[dict] | None = None,
    history_turns_limit: int = 6,
) -> str:
    """Build the full prompt for the LLM.

    Args:
        query: User's question.
        retrieval_results: Retrieved chunks with citations.
        history_turns: Recent conversation history.
        history_turns_limit: Max history turns to include.

    Returns:
        Complete prompt string.
    """
    context = build_context(retrieval_results)
    history = build_history(history_turns or [], history_turns_limit)

    parts = [
        f"SYSTEM:\n{SYSTEM_PROMPT}",
        f"\nCONTEXT:\n{context}",
    ]

    if history:
        parts.append(f"\nCONVERSATION HISTORY:\n{history}")

    parts.append(f"\nUSER: {query}")
    parts.append("\nASSISTANT:")

    return "\n".join(parts)
