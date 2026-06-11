"""Unit tests for answer prompt building and citations."""

import pytest
from datetime import datetime

from memex.answer.prompt import build_prompt, build_context, SYSTEM_PROMPT
from memex.config.settings import RetrievalResult


class TestPromptBuilding:
    def test_system_prompt_is_nonempty(self):
        assert len(SYSTEM_PROMPT) > 100
        assert "non-negotiable" in SYSTEM_PROMPT.lower()
        assert "[Source N]" in SYSTEM_PROMPT

    def test_context_building(self):
        results = [
            RetrievalResult(
                chunk_id="c1",
                document_id="d1",
                content="Python is a language",
                combined_score=0.9,
                vector_score=0.8,
                keyword_score=0.7,
                graph_score=0.0,
                temporal_score=1.0,
                source_type="filesystem",
                source_path="/notes/python.md",
                captured_at=datetime(2026, 1, 1),
                citation_index=1,
            ),
            RetrievalResult(
                chunk_id="c2",
                document_id="d2",
                content="FastAPI is a web framework",
                combined_score=0.8,
                vector_score=0.7,
                keyword_score=0.6,
                graph_score=0.0,
                temporal_score=0.9,
                source_type="browser",
                source_path="https://fastapi.tiangolo.com",
                captured_at=datetime(2026, 3, 1),
                citation_index=2,
            ),
        ]

        context = build_context(results)
        assert "[Source 1]" in context
        assert "[Source 2]" in context
        assert "Python is a language" in context
        assert "FastAPI" in context

    def test_empty_results_context(self):
        context = build_context([])
        assert "No relevant context" in context

    def test_full_prompt_structure(self):
        results = [
            RetrievalResult(
                chunk_id="c1", document_id="d1", content="test",
                combined_score=1.0, vector_score=1.0, keyword_score=0.0,
                graph_score=0.0, temporal_score=1.0,
                source_type="test", source_path="/t",
                captured_at=datetime(2026, 1, 1),
                citation_index=1,
            ),
        ]

        prompt = build_prompt("What is test?", results)
        assert "SYSTEM:" in prompt
        assert "CONTEXT:" in prompt
        assert "[Source 1]" in prompt
        assert "What is test?" in prompt
        assert "ASSISTANT:" in prompt

    def test_prompt_with_history(self):
        history = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ]
        prompt = build_prompt("Next question", [], history)
        assert "CONVERSATION HISTORY" in prompt
        assert "USER: Hello" in prompt
        assert "ASSISTANT: Hi there" in prompt


class TestCitationExtraction:
    def test_extract_citations(self):
        from memex.answer.chat import ChatEngine
        answer = "Python is great [Source 1]. It's also popular [Source 2]."
        citations = ChatEngine._extract_citations(answer)
        assert citations == {1, 2}

    def test_no_citations(self):
        from memex.answer.chat import ChatEngine
        answer = "No sources here."
        citations = ChatEngine._extract_citations(answer)
        assert citations == set()

    def test_repeated_citation(self):
        from memex.answer.chat import ChatEngine
        answer = "Fact [Source 1] and again [Source 1]."
        citations = ChatEngine._extract_citations(answer)
        assert citations == {1}
