"""
MEMEX TUI — Terminal chat interface using Textual.

Provides an interactive chat with the local MEMEX instance.
"""

from __future__ import annotations

import json
from typing import Optional

import httpx
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, VerticalScroll
from textual.reactive import reactive
from textual.widgets import Button, Footer, Header, Input, Label, Static


class ChatMessage(Static):
    """A single chat message widget."""

    def __init__(self, role: str, content: str, citations: list = None, **kwargs):
        self.role = role
        self.content = content
        self.citations = citations or []
        super().__init__(**kwargs)

    def compose(self) -> ComposeResult:
        role_label = "🧑 You" if self.role == "user" else "🧠 MEMEX"
        yield Label(f"[bold]{role_label}[/bold]", classes="chat-role")
        yield Static(self.content, classes="chat-content")

        if self.citations:
            yield Label("[dim]Sources:[/dim]", classes="sources-label")
            for citation in self.citations:
                yield Static(
                    f"[dim][Source {citation.get('index', '?')}] "
                    f"({citation.get('source_type', '?')}) "
                    f"{citation.get('source_path', '?')[:60]}[/dim]",
                    classes="source-card",
                )


class MEMEXChatApp(App):
    """MEMEX Terminal Chat Interface."""

    CSS = """
    Screen {
        layout: vertical;
    }

    #chat-container {
        height: 1fr;
        border: solid green;
        padding: 1;
        overflow-y: auto;
    }

    #input-container {
        height: auto;
        dock: bottom;
        padding: 1;
    }

    #message-input {
        height: 3;
    }

    .chat-role {
        text-style: bold;
        margin-bottom: 0;
    }

    .chat-content {
        margin-left: 2;
        margin-bottom: 1;
    }

    .sources-label {
        margin-left: 2;
        margin-top: 0;
    }

    .source-card {
        margin-left: 4;
        margin-bottom: 0;
    }

    #title {
        text-align: center;
        text-style: bold;
        color: green;
    }

    #status {
        color: gray;
    }
    """

    BINDINGS = [("q", "quit", "Quit"), ("c", "clear_chat", "Clear")]

    messages: reactive[list] = reactive([])

    def __init__(self, session_id: Optional[str] = None, **kwargs):
        import uuid
        self._session_id = session_id or str(uuid.uuid4())
        self._base_url = "http://127.0.0.1:7700"
        self._client = httpx.Client(timeout=120.0)
        super().__init__(**kwargs)

    def compose(self) -> ComposeResult:
        yield Header()
        yield Label("╔═══════════════════════════════════╗", id="title")
        yield Label("║     MEMEX — Second Brain Chat     ║", id="title")
        yield Label("╚═══════════════════════════════════╝", id="title")
        yield Label("Type your question below. Press Enter to send.", id="status")
        yield VerticalScroll(id="chat-container")
        yield Horizontal(
            Input(placeholder="Ask your memory...", id="message-input"),
            Button("Send", variant="primary", id="send-btn"),
            id="input-container",
        )
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle send button click."""
        if event.button.id == "send-btn":
            self._send_message()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key in input."""
        if event.input.id == "message-input":
            self._send_message()

    def _send_message(self) -> None:
        """Send a chat message."""
        input_widget = self.query_one("#message-input", Input)
        query = input_widget.value.strip()
        if not query:
            return

        input_widget.value = ""

        # Add user message
        self._add_message("user", query)

        # Send to API
        try:
            response = self._client.post(
                f"{self._base_url}/api/chat",
                json={"session_id": self._session_id, "query": query},
                timeout=120.0,
            )
            if response.status_code == 200:
                data = response.json().get("data", {})
                answer = data.get("answer", "No response received.")
                citations = data.get("citations", [])
                self._add_message("assistant", answer, citations)
            else:
                self._add_message("assistant", f"Error: {response.status_code}")
        except httpx.ConnectError:
            self._add_message(
                "assistant",
                "Cannot connect to MEMEX daemon. Is it running? Start with: memex start",
            )
        except Exception as e:
            self._add_message("assistant", f"Error: {str(e)}")

    def _add_message(self, role: str, content: str, citations: list = None) -> None:
        """Add a message to the chat display."""
        container = self.query_one("#chat-container", VerticalScroll)
        msg = ChatMessage(role, content, citations)
        container.mount(msg)
        # Scroll to bottom
        container.scroll_end(animate=False)

    def action_clear_chat(self) -> None:
        """Clear chat messages."""
        container = self.query_one("#chat-container", VerticalScroll)
        container.remove_children()


def run_tui() -> None:
    """Run the TUI application."""
    app = MEMEXChatApp()
    app.run()


if __name__ == "__main__":
    run_tui()
