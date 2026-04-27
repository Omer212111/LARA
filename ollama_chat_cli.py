#!/usr/bin/env python3
"""
Simple terminal chat with Ollama using the official `ollama` package.

Keeps full multi-turn history and sends it on every request so context is preserved.
Optionally persists messages to a JSON session file (load on start, save after each turn).

Usage:
  python ollama_chat_cli.py
  python ollama_chat_cli.py --model tinyllama:latest
  python ollama_chat_cli.py --session my_chat.json
  python ollama_chat_cli.py --no-session-file

Environment (optional overrides):
  OLLAMA_HOST, OLLAMA_USER, OLLAMA_PASSWORD, OLLAMA_MODEL
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from ollama import Client

DEFAULT_MODEL = "tinyllama:latest"
DEFAULT_SYSTEM = "You are a helpful assistant."
DEFAULT_SESSION = Path(".ollama_chat_session.json")


def make_client() -> Client:
    return Client(
        host=os.environ.get("OLLAMA_HOST", "https://192.116.98.6"),
        auth=(
            os.environ.get("OLLAMA_USER", "group1"),
            os.environ.get("OLLAMA_PASSWORD", "MTAgroup1"),
        ),
        verify=False,  # same behavior as curl -k
        timeout=float(os.environ.get("OLLAMA_TIMEOUT", "120")),
    )


def _model_names_from_list_result(result: Any) -> set[str]:
    models = getattr(result, "models", None)
    if models is None and isinstance(result, dict):
        models = result.get("models", [])
    if models is None:
        return set()

    names: set[str] = set()
    for m in models:
        if isinstance(m, dict):
            name = m.get("model") or m.get("name")
        else:
            name = getattr(m, "model", None) or getattr(m, "name", None)
        if isinstance(name, str) and name:
            names.add(name)
    return names


def ensure_model_exists(client: Client, model: str) -> None:
    try:
        available = _model_names_from_list_result(client.list())
    except Exception as e:
        raise RuntimeError(f"Could not verify model list from server: {e}") from e

    if model in available:
        return

    available_display = ", ".join(sorted(available)) if available else "(none reported)"
    raise ValueError(
        f"Model '{model}' not found on server. Available models: {available_display}"
    )


def _validate_messages(messages: list[dict[str, Any]]) -> None:
    for i, m in enumerate(messages):
        if not isinstance(m, dict):
            raise ValueError(f"Message {i} must be an object, got {type(m).__name__}")
        if m.get("role") not in ("system", "user", "assistant", "tool"):
            raise ValueError(f"Message {i} has invalid role: {m.get('role')!r}")
        if "content" not in m:
            raise ValueError(f"Message {i} missing 'content'")


def load_session(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("Session file must be a JSON array of message objects.")
    _validate_messages(data)
    return data


def save_session(path: Path, messages: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(messages, f, indent=2, ensure_ascii=False)


def ensure_system_message(
    messages: list[dict[str, Any]], system: str
) -> list[dict[str, Any]]:
    if not messages:
        return [{"role": "system", "content": system}]
    if messages[0].get("role") != "system":
        return [{"role": "system", "content": system}, *messages]
    return messages


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Ollama chat CLI with persistent history.")
    p.add_argument(
        "--model",
        default=os.environ.get("OLLAMA_MODEL", DEFAULT_MODEL),
        help=f"Model name (default: {DEFAULT_MODEL} or OLLAMA_MODEL).",
    )
    p.add_argument(
        "--system",
        default=DEFAULT_SYSTEM,
        help="System prompt when starting a new session.",
    )
    p.add_argument(
        "--session",
        type=Path,
        default=DEFAULT_SESSION,
        help=f"JSON file for load/save (default: {DEFAULT_SESSION}).",
    )
    p.add_argument(
        "--no-session-file",
        action="store_true",
        help="Do not read or write a session file (in-memory only this run).",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    client = make_client()
    try:
        ensure_model_exists(client, args.model)
    except Exception as e:
        print(f"Error: {e}")
        raise SystemExit(1)

    session_path: Path | None = None if args.no_session_file else args.session

    if session_path and session_path.exists():
        try:
            messages = ensure_system_message(load_session(session_path), args.system)
        except (json.JSONDecodeError, ValueError) as e:
            print(f"Could not load session ({session_path}): {e}")
            print("Starting a new conversation.")
            messages = [{"role": "system", "content": args.system}]
    else:
        messages = [{"role": "system", "content": args.system}]

    print(f"Model: {args.model}")
    print("Commands: /quit /exit | /clear (reset chat, keep system) | /save (write session now)")
    print(f"Session file: {session_path or 'disabled (this run only)'}")
    print()

    while True:
        try:
            user_text = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            if session_path:
                try:
                    save_session(session_path, messages)
                except OSError as e:
                    print(f"(Could not save session: {e})")
            return

        if not user_text:
            continue

        low = user_text.lower()
        if low in ("/quit", "/exit", "quit", "exit"):
            if session_path:
                try:
                    save_session(session_path, messages)
                except OSError as e:
                    print(f"Could not save session: {e}")
            print("Bye.")
            return

        if low == "/clear":
            messages = [{"role": "system", "content": args.system}]
            if session_path:
                try:
                    save_session(session_path, messages)
                except OSError as e:
                    print(f"Could not save session: {e}")
            print("(History cleared.)\n")
            continue

        if low == "/save":
            if not session_path:
                print("(No session file configured.)\n")
                continue
            try:
                save_session(session_path, messages)
                print(f"(Saved to {session_path}.)\n")
            except OSError as e:
                print(f"Save failed: {e}\n")
            continue

        messages.append({"role": "user", "content": user_text})

        try:
            response = client.chat(
                model=args.model,
                messages=messages,
                stream=False,
            )
        except Exception as e:
            messages.pop()  # drop failed user message so history stays consistent
            print(f"Error: {e}\n")
            continue

        assistant_content = (response.message.content or "").strip()
        print(f"Assistant: {assistant_content}\n")
        messages.append({"role": "assistant", "content": assistant_content})

        if session_path:
            try:
                save_session(session_path, messages)
            except OSError as e:
                print(f"(Warning: could not save session: {e})\n")


if __name__ == "__main__":
    main()
