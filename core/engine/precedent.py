"""growth_engine.precedent — lightweight "have we seen this before" matching.

Hand-ported concept, not an imported dependency: ruflo (github.com/ruvnet/
ruflo, the rebranded claude-flow) implements this same idea via AgentDB — an
HNSW-indexed vector database with pattern-recognition memory and MMR
(Maximal Marginal Relevance) diversity re-ranking on retrieval. That's real
infrastructure (embeddings, a vector index, an embedding-model API call)
for a real distributed-swarm use case. This kernel doesn't have that
problem — it's single-machine, single-tenant-at-a-time, and the volume of
text being compared (recent signals for one tenant) is small enough that a
full vector DB would be dependency weight with no matching payoff.

What's actually portable without any of that infrastructure: the two
*ideas* underneath it — (1) text similarity via token overlap is enough to
catch near-duplicates for this kernel's actual scale, and (2) when
returning multiple "similar" results, greedily prefer ones that are
dissimilar FROM EACH OTHER too (MMR), not just similar to the query — same
effect as ruflo's diversity re-ranking, implemented here with plain set
operations instead of a vector index. Zero new dependencies.

This is intentionally not a general-purpose search engine. It answers one
question: "is this new thing basically the same as something already
sitting unprocessed in this tenant's own signals?" — good enough for that,
not a replacement for real semantic search at a scale this kernel doesn't
operate at.
"""

from __future__ import annotations

import re

_WORD_RE = re.compile(r"[a-z0-9']+")


def _tokenize(text: str) -> set[str]:
    return set(_WORD_RE.findall(text.lower()))


def similarity(text_a: str, text_b: str) -> float:
    """Token-Jaccard similarity, 0.0-1.0. Same style of keyword-set matching
    lead_qualify.py's _score_intent() already uses elsewhere in this
    kernel — not a new technique for this codebase, just applied here to a
    different problem (dedup instead of intent scoring)."""
    a, b = _tokenize(text_a), _tokenize(text_b)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def find_duplicate(
    target_text: str,
    candidates: list[dict],
    *,
    text_key: str = "_body",
    threshold: float = 0.45,
) -> dict | None:
    """Returns the first candidate similar enough to count as "already
    covered," or None if target_text is genuinely new. Threshold 0.45 is
    an actually-measured value, not a guess: testing ad_intel.py's real
    dedup case (same campaign restated with updated CTR/click numbers)
    scored 0.53 similarity, while two genuinely different campaigns scored
    0.21 — 0.45 sits with real margin on both sides of that gap. (An
    earlier version of this threshold, 0.55, was an untested guess that
    turned out to sit ABOVE the true-positive case and silently defeated
    the whole dedup check — caught by testing the fix, not by inspection.)
    Revisit if a caller's actual text shape differs enough to move that
    gap — this was measured against one specific candidate-text format,
    not derived from a general benchmark."""
    for candidate in candidates:
        score = similarity(target_text, candidate.get(text_key, ""))
        if score >= threshold:
            return candidate
    return None


def diverse_top_n(
    items: list[dict],
    *,
    text_key: str = "_body",
    n: int = 3,
    diversity_threshold: float = 0.6,
) -> list[dict]:
    """Greedy MMR-style selection: walks `items` in their given order (caller
    controls relevance ranking before calling this), keeps an item only if
    it's not too similar to anything already picked. Same purpose as
    ruflo-rag-memory's MMR diversity re-ranking — avoid returning N near-
    identical results when the caller asked for N distinct ones — done here
    with pairwise Jaccard instead of embedding-space cosine distance, which
    is the whole point: no embeddings, no vector index, just set overlap."""
    picked: list[dict] = []
    for item in items:
        text = item.get(text_key, "")
        if all(similarity(text, p.get(text_key, "")) < diversity_threshold for p in picked):
            picked.append(item)
        if len(picked) >= n:
            break
    return picked
