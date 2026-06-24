"""AION-6S Agent Loop — Claude-Code-style multi-step reasoning.

Provides:
  - Multi-step planning (AI proposes plan, then executes)
  - Loop detection (stop if same tool call repeats N times)
  - Token budget enforcement (stop if context grows too large)
  - Step-by-step confirmation in /build mode
  - Final synthesis step (summarize what was done)
  - Progress display ("Step N/M" instead of "round N/5")

Designed for 2GB RAM iPhone 6s — minimal allocations, no external deps.
"""

import os
import re
import sys
import time
import json
import hashlib
import logging

LOGGER = logging.getLogger(__name__)

# Defaults — overridden by config
DEFAULT_MAX_STEPS = 12          # hard cap on tool rounds
DEFAULT_LOOP_THRESHOLD = 3      # same tool call N times in a row = stop
DEFAULT_TOKEN_BUDGET = 180_000  # ~chars; ~45k tokens
DEFAULT_PLAN_TIMEOUT = 60       # seconds for plan generation


def _tool_signature(kind, inp):
    """Stable signature for a tool call (kind + normalized input)."""
    if inp is None:
        inp = ""
    norm = re.sub(r"\s+", " ", str(inp)).strip()[:200]
    raw = f"{kind}|{norm}".encode("utf-8", errors="replace")
    return hashlib.md5(raw).hexdigest()[:12]


class AgentLoop:
    """Drives the multi-step agent loop on top of an AION instance.

    Usage:
        agent = AgentLoop(aion, config)
        agent.run(user_message)
    """

    __slots__ = [
        "aion", "config", "max_steps", "loop_threshold",
        "token_budget", "plan_timeout", "stop_reason",
        "step_count", "plan_text", "results_log",
    ]

    def __init__(self, aion, config=None):
        self.aion = aion
        self.config = config or {}
        self.max_steps = int(self.config.get("max_steps", DEFAULT_MAX_STEPS))
        self.loop_threshold = int(self.config.get("loop_threshold", DEFAULT_LOOP_THRESHOLD))
        self.token_budget = int(self.config.get("token_budget", DEFAULT_TOKEN_BUDGET))
        self.plan_timeout = int(self.config.get("plan_timeout", DEFAULT_PLAN_TIMEOUT))
        self.stop_reason = ""
        self.step_count = 0
        self.plan_text = ""
        self.results_log = []

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(self, user_message):
        """Run the full agent loop for one user message.

        Returns the final assistant text (str) or None on hard failure.
        """
        aion = self.aion
        self.step_count = 0
        self.results_log = []
        self.stop_reason = ""

        # 1. Initial response — AI may already include tool calls
        response = aion._stream(gray=False)
        if response is None:
            return None
        final = response

        # 2. Plan-mode short-circuit: just parse & display, don't loop
        if aion.mode == "plan":
            aion._process_ai_response(final, heal=False)
            return final

        # 3. Multi-step loop
        sig_history = []   # recent tool signatures for loop detection
        consecutive_failures = 0
        last_results = []

        for step in range(self.max_steps):
            self.step_count = step + 1

            # Token budget check
            ctx_chars = sum(len(m.get("content", "")) for m in aion.memory.get_context())
            if ctx_chars > self.token_budget:
                self._emit_warn(f"token budget exceeded ({ctx_chars} > {self.token_budget}) — stopping")
                self.stop_reason = "token_budget"
                break

            # Execute any tool calls in the current response
            results = aion._process_ai_response(final, heal=False)

            if not results:
                # No tool calls → AI gave a final answer
                break

            self.results_log.extend(results)
            last_results = results

            # Loop detection: same signature repeated N times in a row
            sigs = [_tool_signature(r["kind"], r.get("input")) for r in results]
            sig_history.extend(sigs)
            if self._is_looping(sig_history):
                self._emit_warn(f"loop detected ({self.loop_threshold} identical tool calls) — stopping")
                self.stop_reason = "loop"
                # Feed the loop signal back so AI can adapt
                aion.memory.add(
                    "tool",
                    "[system] You are repeating the same tool call. "
                    "Stop and either change your approach or give a final answer."
                )
                final = aion._stream(gray=False) or ""
                break

            # Consecutive failure circuit breaker
            for r in results:
                if not r.get("success", True):
                    consecutive_failures += 1
                else:
                    consecutive_failures = 0
            if consecutive_failures >= 3:
                self._emit_warn(f"circuit breaker: {consecutive_failures} consecutive tool failures")
                self.stop_reason = "failures"
                aion.memory.add(
                    "tool",
                    "[system] Multiple tool calls have failed. "
                    "Summarize what went wrong and suggest next steps."
                )
                final = aion._stream(gray=False) or ""
                break

            # /build mode: pause for confirmation between steps
            if aion.mode == "build" and not self._confirm_step(results):
                self._emit_warn("user stopped execution")
                self.stop_reason = "user_abort"
                break

            # Progress display
            self._emit_progress(step + 1, self.max_steps, results)

            # Feed results back to AI
            aion.memory.add("tool", aion._format_tool_results(results))

            # Next round
            nxt = aion._stream(gray=False)
            if nxt is None:
                self._emit_warn("API error during agent loop")
                self.stop_reason = "api_error"
                break
            final = nxt

        else:
            # for/else: loop completed without break → hit max_steps
            self._emit_warn(f"hit max_steps={self.max_steps}")
            self.stop_reason = "max_steps"

        # 4. Final synthesis if we actually did work
        if self.results_log and self.stop_reason not in ("user_abort",):
            final = self._synthesize(final, last_results) or final

        return final

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _is_looping(self, sig_history):
        """True if the last `loop_threshold` signatures are identical."""
        if len(sig_history) < self.loop_threshold:
            return False
        recent = sig_history[-self.loop_threshold:]
        return len(set(recent)) == 1

    def _confirm_step(self, results):
        """In /build mode, ask user before continuing. Returns True to proceed."""
        aion = self.aion
        print()
        for r in results:
            kind = r.get("kind", "?")
            inp = r.get("input", "")
            ok = r.get("success", True)
            mark = "✓" if ok else "✗"
            print(f"  {mark} [{kind}] {inp[:80]}")
        print()
        try:
            ans = input(f"{aion.__class__.__name__}> continue? [Y/n/skip] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return False
        if ans in ("n", "no", "stop", "abort", "q", "quit"):
            return False
        if ans in ("s", "skip"):
            # Skip means: don't run more steps, but synthesize what we have
            self.stop_reason = "user_skip"
            return False
        return True

    def _synthesize(self, final, last_results):
        """Ask AI for a final summary of what was accomplished."""
        aion = self.aion
        steps_done = len(self.results_log)
        kinds = {}
        for r in self.results_log:
            kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
        summary = ", ".join(f"{v} {k}" for k, v in sorted(kinds.items()))

        prompt = (
            f"[system] You completed {steps_done} tool step(s) ({summary}). "
            "Give a concise final answer to the user. "
            "Do NOT call any more tools. Just summarize the result."
        )
        aion.memory.add("tool", prompt)
        synth = aion._stream(gray=False)
        return synth

    def _emit_progress(self, step, total, results):
        kinds = ",".join(sorted({r["kind"] for r in results}))
        msg = f"step {step}/{total} — {len(results)} tool(s) [{kinds}]"
        try:
            c = sys.modules[__name__].__dict__.get("_emit")
            if c:
                c(msg)
                return
        except Exception:
            pass
        # Fallback: print directly
        try:
            from aion import cl, ANSI
            cl("DIM", f"\n  ━ {msg} ━\n")
        except Exception:
            print(f"\n  ━ {msg} ━\n")

    def _emit_warn(self, msg):
        try:
            from aion import cl
            cl("WARN", f"\n  ⚠ {msg}\n")
        except Exception:
            print(f"\n  WARN: {msg}\n")


def _emit(msg):
    """Optional progress hook — set by aion.py to route through its UI."""
    pass
