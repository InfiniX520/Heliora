"""Rule-based in-memory memory retrieval for Day-1 scaffold."""

from __future__ import annotations

from dataclasses import dataclass
import re


TOKEN_PATTERN = re.compile(r"[a-z0-9_]+")


@dataclass(frozen=True)
class MemoryRecord:
    """Static memory record used by the scaffold retrieval flow."""

    memory_id: str
    scope: str
    content: str
    source: str
    tags: tuple[str, ...]


def _tokenize(text: str) -> set[str]:
    return set(TOKEN_PATTERN.findall(text.lower()))


class RuleBasedMemoryStore:
    """Simple deterministic retrieval store backed by static records."""

    def __init__(self) -> None:
        self._records: tuple[MemoryRecord, ...] = (
            MemoryRecord(
                memory_id="mem_proj_style_001",
                scope="project",
                content="Project coding style prefers relative paths and reproducible environment setup.",
                source="project.guidelines",
                tags=("style", "relative_path", "setup"),
            ),
            MemoryRecord(
                memory_id="mem_proj_api_002",
                scope="project",
                content="Task submit requires idempotency key and supports deterministic replay.",
                source="backend.tasks",
                tags=("task", "idempotency", "api"),
            ),
            MemoryRecord(
                memory_id="mem_course_math_001",
                scope="course",
                content="Linear algebra review focuses on vectors, matrices, and transformations.",
                source="course.notes",
                tags=("course", "math", "review"),
            ),
            MemoryRecord(
                memory_id="mem_thread_sync_001",
                scope="thread",
                content="Latest sync confirmed backend health endpoint, smoke tests, and docs availability.",
                source="thread.log",
                tags=("status", "health", "smoke"),
            ),
            MemoryRecord(
                memory_id="mem_global_arch_001",
                scope="global",
                content="Architecture baseline includes orchestrator, worker, and queue routing layers.",
                source="global.architecture",
                tags=("architecture", "queue", "orchestrator"),
            ),
        )

    def retrieve(
        self,
        query: str,
        scope: str,
        top_k: int,
        graph_retrieval_enabled: bool,
    ) -> list[dict]:
        """Retrieve top-k matched memory records with simple token scoring."""
        query_tokens = _tokenize(query)
        if not query_tokens:
            return []

        allowed_scopes = {scope}
        if scope != "global":
            allowed_scopes.add("global")

        scored: list[dict] = []
        lowered_query = query.lower()

        for record in self._records:
            if scope == "global":
                pass
            elif record.scope not in allowed_scopes:
                continue

            text_blob = " ".join((record.content, record.source, " ".join(record.tags))).lower()
            text_tokens = _tokenize(text_blob)
            matched_terms = sorted(query_tokens.intersection(text_tokens))
            if not matched_terms and lowered_query not in text_blob:
                continue

            score = float(len(matched_terms))
            if lowered_query in text_blob:
                score += 0.75
            if record.scope == scope and scope != "global":
                score += 0.25
            if graph_retrieval_enabled and "queue" in matched_terms:
                score += 0.2

            scored.append(
                {
                    "memory_id": record.memory_id,
                    "scope": record.scope,
                    "content": record.content,
                    "source": record.source,
                    "tags": list(record.tags),
                    "score": round(score, 3),
                    "matched_terms": matched_terms,
                }
            )

        scored.sort(key=lambda item: (-item["score"], item["memory_id"]))
        return scored[:top_k]


def build_injected_context(memories: list[dict], max_items: int = 3) -> str:
    """Build short text context to inject into downstream prompts."""
    if not memories:
        return ""

    lines = [f"[{item['scope']}] {item['content']}" for item in memories[:max_items]]
    return "\n".join(lines)


memory_store = RuleBasedMemoryStore()
