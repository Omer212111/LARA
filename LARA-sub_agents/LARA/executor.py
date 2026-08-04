"""
LARA MAS — Executor entry point

Wires up the AppOrchestrator with all four app specialists and exposes
executor_node as the LangGraph node, keeping the same interface as before.

Per-step dispatch: for each ReAct step the orchestrator picks the specialist
whose app name appears in the corresponding Explorer plan step, then uses
that specialist's system prompt for the LLM call.  Falls back to the generic
REACT_EXECUTOR_SYSTEM when no specialist matches (e.g. multi-app glue steps).
"""

from app_agents import (
    AmazonExecutor,
    ApiDocsExecutor,
    AppOrchestrator,
    FileSystemExecutor,
    GmailExecutor,
    PhoneExecutor,
    SimpleNoteExecutor,
    SplitwiseExecutor,
    SpotifyExecutor,
    TodoistExecutor,
    VenmoExecutor,
)

_orchestrator = AppOrchestrator(
    specialists={
        "spotify":     SpotifyExecutor(),
        "gmail":       GmailExecutor(),
        "amazon":      AmazonExecutor(),
        "file_system": FileSystemExecutor(),
        "venmo":       VenmoExecutor(),
        "phone":       PhoneExecutor(),
        "simple_note": SimpleNoteExecutor(),
        "splitwise":   SplitwiseExecutor(),
        "todoist":     TodoistExecutor(),
        "api_docs":    ApiDocsExecutor(),
    }
)

# LangGraph node — same signature as before
executor_node = _orchestrator.node
