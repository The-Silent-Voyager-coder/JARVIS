"""J.A.R.V.I.S. memory subsystem (Phase 3).

Persistent memory: working / long-term / episodic / semantic types, SQLite
persistence with provenance, confidence, expiration, deterministic
retrieval and ranking, and session-scoped working memory. No embeddings, no
LLM extraction, no vector search in this phase.

Submodules are imported lazily by the runtime to avoid import cycles; this
package intentionally exposes no eager imports.
"""
