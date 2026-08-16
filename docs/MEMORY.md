# Memory Architecture (contract for Phase 3)

## 1. Categories

| Category | Content | Example | Persistence |
|---|---|---|---|
| **Working** | current conversation/task context | messages, active task steps | session-scoped; RAM + persisted session file |
| **Long-term** | stable, genuinely useful facts about user/preferences | "user's build machine is ASUS V16, 16 GB RAM" | SQLite, curated |
| **Episodic** | records of things J.A.R.V.I.S. did | task history: created project → edited X → maven failed → fixed dep → build ok | SQLite, append-only per task |
| **Semantic** | retrieved knowledge from documents/projects/notes | API facts extracted from a README | SQLite, source-linked |

## 2. Memory Entry Schema

```python
@dataclass
class MemoryEntry:
    id: str
    category: MemoryCategory        # working | long_term | episodic | semantic
    content: str
    relevance: float                # 0..1 (for retrieval ranking)
    confidence: float               # 0..1
    source: str                     # where it came from (session, file, tool, user)
    provenance: dict                # e.g. {session_id, file_path, task_id, message_id}
    created_at: datetime
    updated_at: datetime | None
    expires_at: datetime | None     # optional expiration
    deleted: bool = False           # soft delete → user-inspectable/restorable
```

## 3. Rules (hard)

- **No automatic saving of every conversation.** Memory writes require a
  deliberate save decision (planner/agent memory tool), gated by `relevance`
  and `confidence` thresholds.
- Every entry carries relevance, provenance, timestamps, confidence, source;
  expiration is optional but supported.
- Users can inspect and delete memories (a Phase 3+ CLI/interfaces
  requirement; DB design must support `deleted` soft-remove now).
- Retrieval returns entries ranked by relevance, filtered by category;
  confidence is shown to agents so low-confidence entries never masquerade as
  facts.
- Episodic memory is derived from the task store (single source of truth),
  never duplicated.

## 4. Storage

SQLite at `C:\JARVIS\data\memory.db` (config: `memory.sqlite_path`). Tables:
`entries` (schema above), `tags`, `deletions` (audit of user removals).
WAL mode; indexed on `(category, created_at)`, FTS for content lookup —
embeddings/vector search are an optional later enhancement, not a Phase 3
requirement.

## 5. Events

`MemoryCreated`, `MemoryRetrieved`, `MemoryDeleted` are emitted so
observability and the HUD can trace memory activity.