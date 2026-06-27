# 0001-record-tech-decisions-with-adrs

**Date**: 2026-06-21
**Status**: Accepted

## Context

As we build JSON AI Studio, we are making ongoing technical decisions — which libraries to use, what architecture for sessions, streaming protocol, error handling strategy, etc. We need a lightweight but disciplined way to record these so that:

- Anyone reading the code later can understand **why** things were chosen
- Decisions are diff-friendly and versioned alongside code
- We can track when decisions change or get superseded
- Requirement docs stay focused on "what" not "how"

Currently we risk losing this knowledge as conversations evolve, requirements shift, and new contributors join.

## Decision

Adopt the **Architecture Decision Record (ADR)** pattern for all technical decisions:

- One file per decision in `docs/adr/`, numbered sequentially (`0001-title.md`).
- Each ADR uses the template: **Context → Decision → Status → Consequences → References**.
- Requirements live in separate `requirements.md` files per app (frontend/backend). Only feature-level requirements go there — technical choices migrate to ADRs.
- When a decision is revisited, create a new ADR that supersedes the old one rather than editing it in place.

See the README for the full template and instructions.

## Status

**Accepted** — implemented in this project structure on 2026-06-21.

## Consequences

### The good
- Every technical choice is explicitly documented with rationale, alternatives, and consequences.
- Decisions are diff-friendly: `git log -- docs/adr/0007.md` shows the evolution of one decision.
- Requirement files stay focused on "what" without technical noise.
- New contributors can trace the "why" behind architectural choices quickly.

### The bad
- Slightly more overhead to write decisions (but this is a net positive for maintainability).
- Requires discipline: decisions written today must be referenced properly, not just updated in place.

### Neutrals
- ADRs are text files — no special tooling required. Standard markdown.

## References

- Original paper: [Record Architectural Decisions](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions) by Michael Nygard
