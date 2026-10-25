"""Thin client for Lyzr Agent Studio agents.

Every agent role can point at its own Lyzr agent (LYZR_AGENT_INTAKE, ...), or all roles can share
one general agent (LYZR_AGENT_ID); the role brief is always sent inside the message, so a single
blank agent works. When no key is configured, or a call fails, callers fall back to rules, so the
app keeps working offline. Numbers in the ledger never come from these calls.
"""
import json
import logging
import os
import re
import time

import httpx

log = logging.getLogger("khata.llm")

ROLES = ("intake", "messenger", "mediator", "analyst", "deadline")


class Lyzr:
    def __init__(self):
        self.api_key = os.getenv("LYZR_API_KEY", "").strip()
        self.url = os.getenv("LYZR_CHAT_URL", "https://agent-prod.studio.lyzr.ai/v3/inference/chat/")
        self.user_id = os.getenv("LYZR_USER_ID", "karigar-khata@demo")
        self.default_agent = os.getenv("LYZR_AGENT_ID", "").strip()
        self.timeout = float(os.getenv("LYZR_TIMEOUT", "30"))
        self.last_error: str | None = None
        self.calls = 0

    def agent_for(self, role: str) -> str:
        return os.getenv(f"LYZR_AGENT_{role.upper()}", "").strip() or self.default_agent

    def enabled(self, role: str = "") -> bool:
        if not self.api_key:
            return False
        if role:
            return bool(self.agent_for(role))
        return any(self.agent_for(r) for r in ROLES)

    def chat(self, role: str, message: str, session_id: str) -> str | None:
        agent_id = self.agent_for(role)
        if not (self.api_key and agent_id):
            return None
        t0 = time.time()
        try:
            r = httpx.post(
                self.url,
                headers={"x-api-key": self.api_key, "Content-Type": "application/json"},
                json={"user_id": self.user_id, "agent_id": agent_id,
                      "session_id": f"{agent_id}-{session_id}", "message": message},
                timeout=self.timeout,
            )
            r.raise_for_status()
            data = r.json()
            self.calls += 1
            self.last_error = None
            text = data.get("response") if isinstance(data, dict) else None
            if text is None and isinstance(data, dict):
                text = data.get("message") or data.get("output")
            log.info("lyzr %s ok in %.1fs", role, time.time() - t0)
            return text if isinstance(text, str) else json.dumps(data)
        except Exception as e:  # network, auth, quota: degrade to rules
            self.last_error = f"{type(e).__name__}: {e}"[:300]
            log.warning("lyzr %s failed: %s", role, self.last_error)
            return None

    def status(self) -> dict:
        return {
            "configured": bool(self.api_key),
            "agents": {r: bool(self.agent_for(r)) for r in ROLES},
            "calls": self.calls,
            "last_error": self.last_error,
        }


lyzr = Lyzr()


def extract_json(text: str | None):
    """Pull the first JSON object/array out of an LLM reply (handles ```json fences)."""
    if not text:
        return None
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1)
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        end = text.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                continue
    return None


NUM_RE = re.compile(r"\d+(?:[.,]\d+)*")


def numbers_preserved(source: str, candidate: str) -> bool:
    """True if every number in `source` appears verbatim in `candidate`. Used to reject any LLM
    rewrite that drops or alters a weight, rate, date or amount."""
    want = {n.replace(",", "") for n in NUM_RE.findall(source)}
    have = {n.replace(",", "") for n in NUM_RE.findall(candidate)}
    return want <= have
