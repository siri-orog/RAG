#!/usr/bin/env python3
"""
test.py — GraphRAG Knowledge Base Test Script
----------------------------------------------
Tests the knowledge base built by the new processing pipeline:
  chunk.py → triple_rep.py → propositions.py → ingest_qdrant.py → ingest_neo4j.py

RETRIEVAL PIPELINE (small-to-big):
  Step 1 : Embed query → search Qdrant "propositions" collection (precise facts)
  Step 2 : Extract query entities with GLiNER → Neo4j traversal → section names
  Step 3 : Fetch full parent sections from Qdrant "sections" collection
  Step 4 : Also search "sections" collection directly (broad context)
  Step 5 : Merge all candidates, deduplicate
  Step 6 : Rerank with CrossEncoder (offline, portable/reranker)
  Step 7 : Build context → call Ollama → return answer

USAGE:
  python test.py                          → interactive Q&A loop
  python test.py "your question"          → single question, print answer
  python test.py --no-llm "question"      → retrieval only, skip Ollama
  python test.py --diagnose               → full KB health check
  python test.py --test-qdrant            → Qdrant collection diagnostics
  python test.py --test-neo4j             → Neo4j all-5-layers diagnostics
  python test.py --test-retrieval "q"     → trace every retrieval step visibly
  python test.py --json "question"        → machine-readable JSON output

Edit the CONFIG block below. No internet required.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Optional

logging.getLogger("transformers").setLevel(logging.ERROR)

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  CONFIG — edit these values to match your setup                          ║
# ╚══════════════════════════════════════════════════════════════════════════╝

QDRANT_URL           = "http://localhost:6333"
COLLECTION_PROPS     = "propositions"     # atomic sentence vectors
COLLECTION_SECTIONS  = "sections"         # full section chunk vectors

NEO4J_URI            = "bolt://localhost:7687"
NEO4J_USER           = "neo4j"
NEO4J_PASSWORD       = "sac@1234"

# Book IDs to restrict search — must match the book_id used during ingestion
BOOK_IDS             = ["PSLV-C50"]       # ← change to your ingested book_id(s)

OLLAMA_URL           = "http://localhost:11434"
OLLAMA_MODEL         = "llama3.1:8b-instruct-q4_K_M"

# Offline reranker — place CrossEncoder model in portable/reranker/
RERANKER_DIR         = BASE_DIR / "portable" / "reranker"

# Retrieval tuning
PROP_RETRIEVE_LIMIT  = 40    # propositions fetched from Qdrant in Step 1
SECT_RETRIEVE_LIMIT  = 20    # sections fetched from Qdrant in Step 4
NEO4J_ENTITY_LIMIT   = 200   # max Neo4j entity→section hits
FINAL_TOP_N          = 8     # sections sent to LLM after reranking
BOOST_BOTH           = 0.12  # score bonus for sections found by both Qdrant+Neo4j
CONTEXT_MAX_CHARS    = 14000
GLINER_THRESHOLD     = 0.35
PROMPT_MODE          = "balanced"  # "fast" | "balanced" | "deep"

# ╚══════════════════════════════════════════════════════════════════════════╝


# ─────────────────────────────────────────────────────────────────────────────
# SYSTEM PROMPT
# ─────────────────────────────────────────────────────────────────────────────

BASE_SYSTEM_PROMPT = (
    "You are an expert technical assistant for ISRO documents and space "
    "technology manuals.\n\n"
    "Your task is to provide accurate, complete, and well-structured answers "
    "based STRICTLY on the provided context from the knowledge base.\n\n"
    "Follow these guidelines:\n"
    "1. Explain concepts thoroughly — do not leave out important details.\n"
    "2. Structure your answer clearly using bullet points, bold text, and "
    "paragraphs for readability.\n"
    "3. Synthesize information if it appears across multiple sections.\n"
    "4. If the context does not contain enough information, state exactly "
    "what is missing. Never guess or hallucinate.\n"
    "5. ALWAYS cite the source after every fact: [Book: X | Page: Y]\n"
    "6. Give a complete answer regardless of question complexity."
)

MODE_STYLE = {
    "fast":     "",
    "balanced": "\n7. Use section headings for multi-part answers.",
    "deep": (
        "\n7. Use headings and subheadings for complex answers."
        "\n8. Cross-reference information between sections when relevant."
        "\n9. If the question involves a process or sequence, "
        "explain each step in order."
    ),
}


def get_system_prompt(mode: str = PROMPT_MODE) -> str:
    return BASE_SYSTEM_PROMPT + MODE_STYLE.get(mode, MODE_STYLE["balanced"])


# ─────────────────────────────────────────────────────────────────────────────
# LAZY-LOADED GLOBALS — each model loaded once, then reused
# ─────────────────────────────────────────────────────────────────────────────

_gliner_model  = None
_reranker      = None
_neo_driver    = None
_qdrant_client = None
_nomic_model   = None


def get_qdrant_client():
    global _qdrant_client
    if _qdrant_client is None:
        from qdrant_client import QdrantClient
        _qdrant_client = QdrantClient(url=QDRANT_URL)
        print(f"[LOAD] Qdrant connected at {QDRANT_URL}")
    return _qdrant_client


def _qdrant_vector_search(
    client,
    *,
    collection_name: str,
    query_vector,
    query_filter,
    limit: int,
    with_payload: bool,
):
    if hasattr(client, "query_points"):
        resp = client.query_points(
            collection_name=collection_name,
            query=query_vector,
            query_filter=query_filter,
            limit=limit,
            with_payload=with_payload,
        )
        return list(resp.points)
    return client.search(
        collection_name=collection_name,
        query_vector=query_vector,
        query_filter=query_filter,
        limit=limit,
        with_payload=with_payload,
    )


def get_neo4j():
    global _neo_driver
    if _neo_driver is None:
        from neo4j import GraphDatabase
        print(f"[LOAD] Connecting Neo4j at {NEO4J_URI}...")
        _neo_driver = GraphDatabase.driver(
            NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)
        )
        _neo_driver.verify_connectivity()
        print("[OK]   Neo4j connected.")
    return _neo_driver


def get_gliner():
    global _gliner_model
    if _gliner_model is None:
        from gliner import GLiNER
        model_dir = BASE_DIR / "portable" / "gliner"
        print(f"[LOAD] GLiNER from {model_dir}...")
        _gliner_model = GLiNER.from_pretrained(
            str(model_dir), local_files_only=True
        ).to("cpu")
        print("[OK]   GLiNER ready.")
    return _gliner_model


def get_reranker():
    global _reranker
    if _reranker is None:
        cfg = RERANKER_DIR / "config.json"
        if not cfg.is_file():
            raise FileNotFoundError(
                f"Reranker not found at {RERANKER_DIR}\n"
                "Place offline CrossEncoder model in portable/reranker/"
            )
        from sentence_transformers import CrossEncoder
        print(f"[LOAD] CrossEncoder from {RERANKER_DIR}...")
        _reranker = CrossEncoder(str(RERANKER_DIR))
        print("[OK]   Reranker ready.")
    return _reranker


def get_nomic():
    global _nomic_model
    if _nomic_model is None:
        from sentence_transformers import SentenceTransformer
        model_dir = BASE_DIR / "portable" / "nomic"
        print(f"[LOAD] Nomic from {model_dir}...")
        _nomic_model = SentenceTransformer(
            str(model_dir), trust_remote_code=True, device="cpu"
        )
        print("[OK]   Nomic ready.")
    return _nomic_model


# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 — SEARCH PROPOSITIONS (precise fact retrieval)
# ─────────────────────────────────────────────────────────────────────────────

def search_propositions(query: str, book_ids: list, limit: int = PROP_RETRIEVE_LIMIT) -> list:
    """
    Searches the 'propositions' collection for atomic sentence matches.
    Each hit is one precise fact — a single sentence or table row.
    Returns list of dicts with parent_chunk_id for small-to-big lookup.
    """
    from qdrant_client import models as qm

    client    = get_qdrant_client()
    model     = get_nomic()
    query_vec = model.encode("search_query: " + query, show_progress_bar=False).tolist()

    filters = None
    if book_ids:
        filters = qm.Filter(must=[
            qm.FieldCondition(key="book_id", match=qm.MatchAny(any=book_ids))
        ])

    try:
        hits = _qdrant_vector_search(
            client,
            collection_name=COLLECTION_PROPS,
            query_vector=query_vec,
            query_filter=filters,
            limit=limit,
            with_payload=True,
        )
    except Exception as e:
        print(f"[WARN] Propositions search failed: {e}")
        return []

    results = []
    for h in hits:
        pl = h.payload or {}
        results.append({
            "proposition_id":  str(h.id),
            "text":            pl.get("text", ""),
            "parent_chunk_id": pl.get("parent_chunk_id"),
            "section_path":    pl.get("section_path", []),
            "page":            pl.get("page", 0),
            "source_type":     pl.get("source_type", "text"),
            "book_id":         pl.get("book_id"),
            "score":           h.score,
        })
    return results


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — GLINER ON QUERY → NEO4J TRAVERSAL
# ─────────────────────────────────────────────────────────────────────────────

GLINER_ENTITY_LABELS = [
    "equipment", "metric", "organization",
    "location", "identifier", "concept", "person",
]


def extract_query_entities(query: str) -> list:
    """Runs GLiNER on the query text to extract entity terms."""
    model = get_gliner()
    text  = query.replace("\n", " ").strip()
    try:
        preds = model.predict_entities(text, GLINER_ENTITY_LABELS, threshold=GLINER_THRESHOLD)
    except Exception as e:
        print(f"[WARN] GLiNER on query failed: {e}")
        return []

    seen  = set()
    terms = []
    for p in preds:
        name = p.get("text", "").strip().lower()
        if name and name not in seen and len(name) >= 3:
            seen.add(name)
            terms.append(name)
    return terms


def neo4j_sections_for_entities(book_ids: list, entity_terms: list) -> list:
    """
    Traverses Neo4j:
      Entity (name matches query terms) -[MENTIONED_IN]-> Section/Subsection
    Returns list of section names.
    Layer 3 of the graph: Entity-Section links.
    """
    if not entity_terms or not book_ids:
        return []

    driver = get_neo4j()
    cypher = """
    MATCH (e:Entity)-[:MENTIONED_IN]->(s)
    WHERE s.book_id IN $book_ids
      AND (s:Section OR s:Subsection)
      AND ANY(t IN $terms WHERE
          toLower(e.name) = toLower(t)
          OR (size(t) >= 4 AND toLower(e.name) CONTAINS toLower(t))
          OR (size(t) >= 4 AND toLower(t) CONTAINS toLower(e.name))
      )
    RETURN DISTINCT s.name AS section_name
    LIMIT $lim
    """
    try:
        with driver.session() as session:
            rows = session.run(cypher, book_ids=book_ids, terms=entity_terms, lim=NEO4J_ENTITY_LIMIT)
            return [r["section_name"] for r in rows if r.get("section_name")]
    except Exception as e:
        print(f"[WARN] Neo4j entity traversal failed: {e}")
        return []


def neo4j_specs_for_terms(book_ids: list, entity_terms: list) -> list:
    """
    Fetches Spec nodes linked to matching entities.
    Layer 2 of the graph: HAS_SPECIFICATION edges.
    Returns list of {entity, value, unit, raw, section} dicts.
    Injected into context as precise numeric facts before prose.
    """
    if not entity_terms or not book_ids:
        return []

    driver = get_neo4j()
    cypher = """
    MATCH (e:Entity)-[:HAS_SPECIFICATION]->(sp:Spec)
    WHERE e.book_id IN $book_ids
      AND ANY(t IN $terms WHERE
          toLower(e.name) CONTAINS toLower(t)
          OR toLower(t) CONTAINS toLower(e.name)
      )
    RETURN e.name AS entity, sp.value AS value,
           sp.unit AS unit, sp.raw AS raw, sp.section AS section
    LIMIT 50
    """
    try:
        with driver.session() as session:
            rows  = session.run(cypher, book_ids=book_ids, terms=entity_terms)
            specs = []
            for r in rows:
                if r.get("raw"):
                    specs.append({
                        "entity":  r["entity"],
                        "value":   r["value"],
                        "unit":    r["unit"],
                        "raw":     r["raw"],
                        "section": r["section"],
                    })
            return specs
    except Exception as e:
        print(f"[WARN] Neo4j spec lookup failed: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3 — FETCH PARENT SECTIONS (small-to-big retrieval)
# ─────────────────────────────────────────────────────────────────────────────

def fetch_sections_by_chunk_ids(chunk_ids: list, book_ids: list) -> list:
    """
    Fetches full section payloads from 'sections' collection
    using the parent_chunk_id from each proposition hit.
    This is the small-to-big retrieval step.
    """
    if not chunk_ids:
        return []

    client  = get_qdrant_client()
    results = []

    for i in range(0, len(chunk_ids), 64):
        batch = chunk_ids[i: i + 64]
        try:
            pts = client.retrieve(
                collection_name = COLLECTION_SECTIONS,
                ids             = batch,
                with_payload    = True,
            )
            for p in pts:
                pl         = p.payload or {}
                page_range = pl.get("page_range", {"start": 0, "end": 0})
                if isinstance(page_range, dict):
                    page_list = [page_range.get("start", 0), page_range.get("end", 0)]
                elif isinstance(page_range, list):
                    page_list = page_range
                else:
                    page_list = [0, 0]

                results.append({
                    "chunk_id":     str(p.id),
                    "text":         pl.get("text", ""),
                    "book_id":      pl.get("book_id"),
                    "section_path": pl.get("section_path", []),
                    "page_range":   page_list,
                    "chunk_type":   pl.get("chunk_type", "text"),
                    "from_qdrant":  True,
                    "from_neo4j":   False,
                    "qdrant_score": None,
                })
        except Exception as e:
            print(f"[WARN] Section fetch failed for batch: {e}")

    return results


# ─────────────────────────────────────────────────────────────────────────────
# STEP 4 — SEARCH SECTIONS DIRECTLY (broad context)
# ─────────────────────────────────────────────────────────────────────────────

def search_sections_direct(
    query: str, book_ids: list, section_names: list,
    limit: int = SECT_RETRIEVE_LIMIT,
) -> list:
    """
    Searches the 'sections' collection with the query vector.
    Also marks sections whose path appears in section_names (from Neo4j).
    """
    from qdrant_client import models as qm

    client    = get_qdrant_client()
    model     = get_nomic()
    query_vec = model.encode("search_query: " + query, show_progress_bar=False).tolist()

    book_filter = None
    if book_ids:
        book_filter = qm.Filter(must=[
            qm.FieldCondition(key="book_id", match=qm.MatchAny(any=book_ids))
        ])

    all_hits = []
    try:
        hits = _qdrant_vector_search(
            client,
            collection_name=COLLECTION_SECTIONS,
            query_vector=query_vec,
            query_filter=book_filter,
            limit=limit,
            with_payload=True,
        )
        all_hits.extend(hits)
    except Exception as e:
        print(f"[WARN] Sections search failed: {e}")

    results = []
    seen    = set()
    for h in all_hits:
        cid = str(h.id)
        if cid in seen:
            continue
        seen.add(cid)

        pl         = h.payload or {}
        page_range = pl.get("page_range", {"start": 0, "end": 0})
        if isinstance(page_range, dict):
            page_list = [page_range.get("start", 0), page_range.get("end", 0)]
        elif isinstance(page_range, list):
            page_list = page_range
        else:
            page_list = [0, 0]

        s_path     = pl.get("section_path", [])
        from_neo4j = any(sn in s_path for sn in section_names) if section_names else False

        results.append({
            "chunk_id":     cid,
            "text":         pl.get("text", ""),
            "book_id":      pl.get("book_id"),
            "section_path": s_path,
            "page_range":   page_list,
            "chunk_type":   pl.get("chunk_type", "text"),
            "qdrant_score": h.score,
            "from_qdrant":  True,
            "from_neo4j":   from_neo4j,
        })
    return results


# ─────────────────────────────────────────────────────────────────────────────
# STEP 5 — MERGE ALL CANDIDATES
# ─────────────────────────────────────────────────────────────────────────────

def merge_candidates(
    parent_sections: list,
    direct_sections: list,
    neo4j_names:     list,
) -> list:
    """
    Merges parent sections (from proposition hits) and direct sections.
    Deduplicates by chunk_id. Marks from_neo4j based on section_path intersection.
    """
    by_id: dict = {}

    for s in parent_sections + direct_sections:
        cid = s.get("chunk_id", "")
        if not cid:
            continue
        if cid not in by_id:
            by_id[cid] = s.copy()
        else:
            by_id[cid]["from_qdrant"] = by_id[cid].get("from_qdrant") or s.get("from_qdrant")
            by_id[cid]["from_neo4j"]  = by_id[cid].get("from_neo4j")  or s.get("from_neo4j")
            if (s.get("qdrant_score") or 0) > (by_id[cid].get("qdrant_score") or 0):
                by_id[cid]["qdrant_score"] = s["qdrant_score"]

    for cid, s in by_id.items():
        if neo4j_names and any(n in s.get("section_path", []) for n in neo4j_names):
            s["from_neo4j"] = True

    return [s for s in by_id.values() if (s.get("text") or "").strip()]


# ─────────────────────────────────────────────────────────────────────────────
# STEP 6 — RERANK
# ─────────────────────────────────────────────────────────────────────────────

def rerank_candidates(query: str, candidates: list, top_n: int = FINAL_TOP_N) -> list:
    """
    Reranks with CrossEncoder. Applies BOOST_BOTH bonus to sections found
    by both Qdrant and Neo4j. Falls back to qdrant_score if reranker fails.
    """
    if not candidates:
        return []

    try:
        ce     = get_reranker()
        pairs  = [(query, c.get("text") or "") for c in candidates]
        scores = ce.predict(pairs)
        for i, c in enumerate(candidates):
            c["rerank_score"] = float(scores[i])
            if c.get("from_qdrant") and c.get("from_neo4j"):
                c["rerank_score"] += BOOST_BOTH
    except Exception as e:
        print(f"[WARN] Reranker failed ({e}). Using Qdrant scores.")
        for c in candidates:
            base = c.get("qdrant_score")
            c["rerank_score"] = float(base) if isinstance(base, (int, float)) else 0.0
            if c.get("from_qdrant") and c.get("from_neo4j"):
                c["rerank_score"] += BOOST_BOTH

    candidates.sort(key=lambda x: x.get("rerank_score", 0.0), reverse=True)
    return candidates[:top_n]


# ─────────────────────────────────────────────────────────────────────────────
# CONTEXT BUILDER
# ─────────────────────────────────────────────────────────────────────────────

def _split_sentences(text: str) -> list:
    try:
        import nltk
        p = BASE_DIR / "portable" / "nltk_data"
        if p.exists() and str(p) not in nltk.data.path:
            nltk.data.path.insert(0, str(p))
        from nltk.tokenize import sent_tokenize
        return sent_tokenize(text)
    except Exception:
        return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def build_context(
    chunks:    list,
    query:     str,
    specs:     list = None,
    max_chars: int  = CONTEXT_MAX_CHARS,
) -> str:
    """
    Builds the LLM context string from top-ranked sections.
    Spec nodes from Neo4j are prepended as a precise-facts block.
    Long sections are sub-segmented and re-ranked by CrossEncoder.
    """
    parts = []
    total = 0

    # Inject Neo4j spec nodes at top — precise numeric facts before prose
    if specs:
        lines = ["[PRECISE TECHNICAL SPECIFICATIONS FROM KNOWLEDGE GRAPH]"]
        for sp in specs[:20]:
            lines.append(
                f"  • {sp['entity']} — {sp['raw']}"
                + (f" (section: {sp['section']})" if sp.get("section") else "")
            )
        block = "\n".join(lines)
        parts.append(block)
        total += len(block)

    ce = None
    for c in chunks:
        text = (c.get("text") or "").strip()
        if not text:
            continue

        bid        = c.get("book_id") or "?"
        page_range = c.get("page_range") or [0, 0]
        s_path     = c.get("section_path") or []
        path_str   = " → ".join(s_path) if s_path else ""
        label      = f"[Book: {bid} | Page: {page_range[0]}–{page_range[1]}]"
        if path_str:
            label += f" | Section: {path_str}"
        label += "\n"

        if len(text.split()) <= 450:
            block = label + text
        else:
            sents    = _split_sentences(text)
            segments = []
            cur      = ""
            for s in sents:
                if len(cur.split()) + len(s.split()) <= 220:
                    cur = (cur + " " + s).strip()
                else:
                    if cur:
                        segments.append(cur)
                    cur = s
            if cur:
                segments.append(cur)

            if not segments:
                block = label + text[:4000]
            else:
                try:
                    if ce is None:
                        ce = get_reranker()
                    seg_scores = ce.predict([(query, seg) for seg in segments])
                    best_i     = max(range(len(segments)), key=lambda i: seg_scores[i])
                    block      = label + segments[best_i]
                except Exception:
                    block = label + segments[0][:4000]

        if total + len(block) > max_chars:
            block = block[: max(0, max_chars - total)]

        parts.append(block)
        total += len(block)
        if total >= max_chars:
            break

    return "\n\n---\n\n".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# STEP 7 — CALL OLLAMA
# ─────────────────────────────────────────────────────────────────────────────

def call_ollama(prompt: str) -> str:
    import requests
    url     = f"{OLLAMA_URL.rstrip('/')}/api/generate"
    payload = {"model": OLLAMA_MODEL, "prompt": prompt, "stream": False}
    try:
        r = requests.post(url, json=payload, timeout=600)
        r.raise_for_status()
        return (r.json().get("response") or "").strip()
    except Exception as e:
        return f"[Ollama error: {e}]"


# ─────────────────────────────────────────────────────────────────────────────
# FULL END-TO-END PIPELINE
# ─────────────────────────────────────────────────────────────────────────────

def run_e2e(query: str, book_ids: list, verbose: bool = True) -> tuple:
    """Runs the full 7-step retrieval pipeline. Returns (answer, sources)."""
    t0 = time.perf_counter()

    if verbose: print("[1/7] Searching propositions...")
    prop_hits = search_propositions(query, book_ids, PROP_RETRIEVE_LIMIT)
    if verbose: print(f"      → {len(prop_hits)} proposition hits")

    if verbose: print("[2/7] Extracting query entities (GLiNER)...")
    entity_terms = extract_query_entities(query)
    if verbose: print(f"      → entities: {entity_terms or '(none)'}")

    if verbose: print("[3/7] Neo4j entity → section traversal...")
    neo4j_section_names = neo4j_sections_for_entities(book_ids, entity_terms)
    if verbose: print(f"      → {len(neo4j_section_names)} sections from graph")

    specs = neo4j_specs_for_terms(book_ids, entity_terms)
    if verbose and specs: print(f"      → {len(specs)} spec values from graph")

    if verbose: print("[4/7] Fetching parent sections (small-to-big)...")
    parent_chunk_ids = list({
        p["parent_chunk_id"] for p in prop_hits if p.get("parent_chunk_id")
    })
    parent_sections = fetch_sections_by_chunk_ids(parent_chunk_ids, book_ids)
    if verbose: print(f"      → {len(parent_sections)} parent sections fetched")

    if verbose: print("[5/7] Direct section search...")
    direct_sections = search_sections_direct(
        query, book_ids, neo4j_section_names, SECT_RETRIEVE_LIMIT
    )
    if verbose: print(f"      → {len(direct_sections)} sections found")

    if verbose: print("[6/7] Merging candidates...")
    candidates = merge_candidates(parent_sections, direct_sections, neo4j_section_names)
    if verbose: print(f"      → {len(candidates)} unique candidates")

    if verbose: print("[7/7] Reranking...")
    top = rerank_candidates(query, candidates, FINAL_TOP_N)
    if verbose: print(f"      → top {len(top)} selected")

    elapsed = time.perf_counter() - t0
    if verbose: print(f"\n  ⏱  Retrieval: {elapsed:.2f}s")

    context = build_context(top, query, specs)
    prompt  = (
        f"{get_system_prompt(PROMPT_MODE)}\n\n"
        f"Context from knowledge base:\n{context}\n\n"
        f"Question: {query}\n"
        f"Answer:"
    )
    answer = call_ollama(prompt)

    sources = [
        {
            "chunk_id":     c.get("chunk_id"),
            "book_id":      c.get("book_id"),
            "page_range":   c.get("page_range"),
            "section_path": c.get("section_path"),
            "chunk_type":   c.get("chunk_type"),
            "from_qdrant":  c.get("from_qdrant"),
            "from_neo4j":   c.get("from_neo4j"),
            "rerank_score": round(c.get("rerank_score", 0.0), 4),
        }
        for c in top
    ]
    return answer, sources


def run_retrieval_only(query: str, book_ids: list) -> None:
    """Retrieval without LLM — prints retrieved context as JSON."""
    prop_hits  = search_propositions(query, book_ids, PROP_RETRIEVE_LIMIT)
    terms      = extract_query_entities(query)
    neo_names  = neo4j_sections_for_entities(book_ids, terms)
    specs      = neo4j_specs_for_terms(book_ids, terms)
    parent_ids = list({p["parent_chunk_id"] for p in prop_hits if p.get("parent_chunk_id")})
    parents    = fetch_sections_by_chunk_ids(parent_ids, book_ids)
    directs    = search_sections_direct(query, book_ids, neo_names, SECT_RETRIEVE_LIMIT)
    candidates = merge_candidates(parents, directs, neo_names)
    top        = rerank_candidates(query, candidates, FINAL_TOP_N)
    ctx        = build_context(top, query, specs)
    print(json.dumps(
        {"context": ctx, "specs": specs, "sources": top},
        ensure_ascii=False, indent=2, default=str,
    ))


# ─────────────────────────────────────────────────────────────────────────────
# DIAGNOSTIC TESTS
# ─────────────────────────────────────────────────────────────────────────────

def _sep(title: str = ""):
    print("\n" + "═" * 68)
    if title:
        print(f"  {title}")
        print("═" * 68)


def diagnose_qdrant() -> bool:
    """Tests both Qdrant collections and reports health."""
    _sep("QDRANT DIAGNOSTICS")
    ok = True
    client = get_qdrant_client()

    for col in [COLLECTION_PROPS, COLLECTION_SECTIONS]:
        print(f"\n  Collection: '{col}'")
        try:
            info  = client.get_collection(col)
            count = info.points_count
            print(f"    Status : {info.status}")
            print(f"    Points : {count:,}")
            if count == 0:
                print(f"    ❌ EMPTY — has ingest_qdrant.py run?")
                ok = False
            else:
                print(f"    ✅ Has data")

            sample = client.scroll(collection_name=col, limit=3, with_payload=True)[0]
            print(f"    Sample payloads:")
            for p in sample:
                pl = p.payload or {}
                print(
                    f"      • book_id={pl.get('book_id')} | "
                    f"type={pl.get('source_type') or pl.get('chunk_type')} | "
                    f"page={pl.get('page') or pl.get('page_range')} | "
                    f"text={str(pl.get('text',''))[:60]}..."
                )
        except Exception as e:
            print(f"    ❌ ERROR: {e}")
            ok = False

    print(f"\n  Quick search test on '{COLLECTION_PROPS}'...")
    hits = search_propositions("thrust engine", BOOK_IDS, limit=3)
    if hits:
        print(f"  ✅ Search works — {len(hits)} hits")
        for h in hits:
            print(f"      score={h['score']:.4f} | {h['text'][:80]}...")
    else:
        print(f"  ⚠  No hits — check BOOK_IDS in CONFIG matches your ingested book_id")

    return ok


def diagnose_neo4j() -> bool:
    """Tests all 5 Neo4j graph layers."""
    _sep("NEO4J DIAGNOSTICS — ALL 5 LAYERS")
    ok     = True
    driver = get_neo4j()

    with driver.session() as s:

        print("\n  ── Layer 1: Document Hierarchy ──")
        for label in ["Book", "Chapter", "Section", "Subsection"]:
            ct = s.run(
                f"MATCH (n:{label}) WHERE n.book_id IN $bids RETURN count(n) AS c",
                bids=BOOK_IDS,
            ).single()["c"]
            icon = "✅" if ct > 0 else ("❌" if label != "Subsection" else "⚠")
            print(f"    {icon} {label} nodes: {ct:,}")
            if ct == 0 and label in ("Book", "Chapter", "Section"):
                ok = False

        ct = s.run("MATCH ()-[r:NEXT_SECTION]->() RETURN count(r) AS c").single()["c"]
        print(f"    {'✅' if ct > 0 else '⚠'} NEXT_SECTION edges: {ct:,}")

        print("\n  ── Layer 2: Specification Nodes ──")
        ct = s.run(
            "MATCH (e:Entity)-[:HAS_SPECIFICATION]->(sp:Spec) "
            "WHERE e.book_id IN $bids RETURN count(sp) AS c",
            bids=BOOK_IDS,
        ).single()["c"]
        print(f"    {'✅' if ct > 0 else '⚠'} Spec nodes: {ct:,}")
        rows = s.run(
            "MATCH (e:Entity)-[:HAS_SPECIFICATION]->(sp:Spec) "
            "WHERE e.book_id IN $bids RETURN e.name AS entity, sp.raw AS raw LIMIT 3",
            bids=BOOK_IDS,
        )
        for r in rows:
            print(f"         • {r['entity']} → {r['raw']}")

        print("\n  ── Layer 3: Entity-Section Links ──")
        ct = s.run(
            "MATCH (e:Entity)-[:MENTIONED_IN]->(s) WHERE s.book_id IN $bids RETURN count(e) AS c",
            bids=BOOK_IDS,
        ).single()["c"]
        icon = "✅" if ct > 0 else "❌"
        print(f"    {icon} Entity→MENTIONED_IN edges: {ct:,}")
        if ct == 0:
            ok = False
        rows = s.run(
            "MATCH (e:Entity)-[:MENTIONED_IN]->(s) WHERE s.book_id IN $bids "
            "RETURN e.name AS name, e.type AS type, s.name AS section LIMIT 3",
            bids=BOOK_IDS,
        )
        for r in rows:
            print(f"         • [{r['type']}] {r['name']} → {r['section']}")

        print("\n  ── Layer 4: Sentence Co-occurrence ──")
        ct = s.run("MATCH ()-[r:SENTENCE_CO_OCCURS]->() RETURN count(r) AS c").single()["c"]
        print(f"    {'✅' if ct > 0 else '⚠'} SENTENCE_CO_OCCURS edges: {ct:,}")
        rows = s.run(
            "MATCH (a:Entity)-[r:SENTENCE_CO_OCCURS]->(b:Entity) "
            "RETURN a.name AS a, b.name AS b, r.count AS cnt "
            "ORDER BY r.count DESC LIMIT 3"
        )
        for r in rows:
            print(f"         • '{r['a']}' ↔ '{r['b']}' (count: {r['cnt']})")

        print("\n  ── Layer 5: Table Nodes ──")
        ct = s.run(
            "MATCH (t:Table) WHERE t.book_id IN $bids RETURN count(t) AS c",
            bids=BOOK_IDS,
        ).single()["c"]
        print(f"    {'✅' if ct > 0 else '⚠'} Table nodes: {ct:,}")
        ct = s.run(
            "MATCH (t:Table)-[:HAS_ROW]->(r:TableRow) WHERE t.book_id IN $bids RETURN count(r) AS c",
            bids=BOOK_IDS,
        ).single()["c"]
        print(f"    {'✅' if ct > 0 else '⚠'} TableRow nodes: {ct:,}")
        rows = s.run(
            "MATCH (t:Table) WHERE t.book_id IN $bids "
            "RETURN t.title AS title, t.row_count AS rows LIMIT 3",
            bids=BOOK_IDS,
        )
        for r in rows:
            print(f"         • {r['title']} ({r['rows']} rows)")

    return ok


def diagnose_full() -> None:
    """Full KB health check — Qdrant + Neo4j."""
    _sep("FULL KNOWLEDGE BASE HEALTH CHECK")
    print(f"  Books  : {BOOK_IDS}")
    print(f"  Qdrant : {QDRANT_URL}")
    print(f"  Neo4j  : {NEO4J_URI}")
    q_ok = diagnose_qdrant()
    n_ok = diagnose_neo4j()
    _sep("SUMMARY")
    print(f"  Qdrant : {'✅ HEALTHY' if q_ok else '❌ ISSUES FOUND'}")
    print(f"  Neo4j  : {'✅ HEALTHY' if n_ok else '❌ ISSUES FOUND'}")
    if q_ok and n_ok:
        print("\n  ✅ Knowledge base looks healthy. Run a query to test retrieval.")
    else:
        print("\n  ⚠  Fix the issues above before running queries.")


def diagnose_retrieval(query: str) -> None:
    """Traces every retrieval step for one query."""
    _sep(f"RETRIEVAL TRACE: '{query[:60]}'")
    print(f"  Books: {BOOK_IDS}\n")

    print("── Step 1: Proposition search ──")
    props = search_propositions(query, BOOK_IDS, PROP_RETRIEVE_LIMIT)
    print(f"  {len(props)} propositions found")
    for p in props[:5]:
        print(f"  score={p['score']:.4f} [{p['source_type']}] {p['text'][:80]}...")

    print("\n── Step 2: GLiNER entity extraction ──")
    terms = extract_query_entities(query)
    print(f"  Entities: {terms}")

    print("\n── Step 3: Neo4j entity → section traversal ──")
    neo_names = neo4j_sections_for_entities(BOOK_IDS, terms)
    print(f"  Sections from graph: {neo_names[:10]}")

    print("\n── Step 3b: Neo4j spec lookup ──")
    specs = neo4j_specs_for_terms(BOOK_IDS, terms)
    for sp in specs[:5]:
        print(f"  {sp['entity']} → {sp['raw']}")

    print("\n── Step 4: Parent section fetch (small-to-big) ──")
    parent_ids = list({p["parent_chunk_id"] for p in props if p.get("parent_chunk_id")})
    parents    = fetch_sections_by_chunk_ids(parent_ids, BOOK_IDS)
    print(f"  {len(parents)} parent sections fetched")

    print("\n── Step 5: Direct section search ──")
    directs = search_sections_direct(query, BOOK_IDS, neo_names, SECT_RETRIEVE_LIMIT)
    print(f"  {len(directs)} direct sections found")

    print("\n── Step 6: Merge ──")
    candidates = merge_candidates(parents, directs, neo_names)
    both_hits  = sum(1 for c in candidates if c.get("from_qdrant") and c.get("from_neo4j"))
    print(f"  {len(candidates)} unique candidates | both Qdrant+Neo4j: {both_hits}")

    print("\n── Step 7: Rerank ──")
    top = rerank_candidates(query, candidates, FINAL_TOP_N)
    print(f"  Top {len(top)} after reranking:")
    for i, c in enumerate(top):
        path = " → ".join(c.get("section_path") or [])
        print(
            f"  {i+1}. score={c.get('rerank_score',0):.4f} | "
            f"pages={c.get('page_range')} | "
            f"qdrant={c.get('from_qdrant')} neo4j={c.get('from_neo4j')}\n"
            f"     {path}\n"
            f"     {str(c.get('text',''))[:100]}..."
        )


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(
        description="GraphRAG Knowledge Base Test Script. Edit CONFIG block at top."
    )
    ap.add_argument("query_once", nargs="?",
                    help="Single question. Omit for interactive mode.")
    ap.add_argument("--no-llm",          action="store_true",
                    help="Retrieval only — skip Ollama.")
    ap.add_argument("--json",            action="store_true",
                    help="Print machine-readable JSON output.")
    ap.add_argument("--diagnose",        action="store_true",
                    help="Full KB health check.")
    ap.add_argument("--test-qdrant",     action="store_true",
                    help="Qdrant diagnostics only.")
    ap.add_argument("--test-neo4j",      action="store_true",
                    help="Neo4j 5-layer diagnostics only.")
    ap.add_argument("--test-retrieval",  action="store_true",
                    help="Trace all retrieval steps for query_once.")
    args = ap.parse_args()

    _sep("GraphRAG Knowledge Base Test")
    print(f"  Qdrant  : {QDRANT_URL}")
    print(f"    props : '{COLLECTION_PROPS}'")
    print(f"    sects : '{COLLECTION_SECTIONS}'")
    print(f"  Neo4j   : {NEO4J_URI}")
    print(f"  Books   : {BOOK_IDS}")
    print(f"  Ollama  : {OLLAMA_URL}  model={OLLAMA_MODEL}")
    print(f"  Reranker: {RERANKER_DIR}")
    print(f"  Mode    : {PROMPT_MODE}")

    # Model path checks
    errors = []
    for name, path in [
        ("Nomic",    BASE_DIR / "portable" / "nomic"),
        ("GLiNER",   BASE_DIR / "portable" / "gliner"),
        ("Reranker", RERANKER_DIR),
    ]:
        if not path.exists():
            errors.append(f"  ❌ {name} not found: {path}")
    if errors:
        print("\nMISSING MODELS:")
        for e in errors:
            print(e)
        return 1

    if args.diagnose:
        get_qdrant_client(); get_neo4j(); get_gliner(); get_reranker(); get_nomic()
        diagnose_full()
        return 0

    if args.test_qdrant:
        get_qdrant_client(); get_nomic()
        diagnose_qdrant()
        return 0

    if args.test_neo4j:
        get_neo4j()
        diagnose_neo4j()
        return 0

    if args.test_retrieval:
        if not args.query_once:
            print("ERROR: --test-retrieval requires a query.")
            print("  python test.py --test-retrieval 'your question'")
            return 1
        get_qdrant_client(); get_neo4j(); get_gliner(); get_reranker(); get_nomic()
        diagnose_retrieval(args.query_once.strip())
        return 0

    # Load all models
    print("\nLoading models...")
    try:
        get_qdrant_client(); get_neo4j(); get_gliner(); get_reranker(); get_nomic()
    except Exception as e:
        print(f"\n❌ Startup failed: {e}")
        return 1

    print("─" * 68)

    def one(q: str) -> int:
        try:
            if args.no_llm:
                run_retrieval_only(q, BOOK_IDS)
                return 0
            answer, sources = run_e2e(q, BOOK_IDS, verbose=True)
        except Exception as exc:
            import traceback
            print(f"[ERROR] {exc}", file=sys.stderr)
            traceback.print_exc()
            return 1

        if args.json:
            print(json.dumps({"answer": answer, "sources": sources},
                             ensure_ascii=False, indent=2))
        else:
            print("\n─── Answer ───────────────────────────────────────────────\n")
            print(answer)
            print("\n─── Sources ──────────────────────────────────────────────")
            for s in sources:
                pr   = s.get("page_range") or [0, 0]
                path = " → ".join(s.get("section_path") or [])
                print(
                    f"  pages {pr[0]}–{pr[1]} | "
                    f"qdrant={s.get('from_qdrant')} "
                    f"neo4j={s.get('from_neo4j')} | "
                    f"rerank={s.get('rerank_score')} | "
                    f"{path[:60]}"
                )
        print("─" * 68)
        return 0

    if args.query_once:
        return one(args.query_once.strip())

    # Interactive loop
    print("Type your question (or 'quit' to exit):")
    while True:
        try:
            q = input("\nQuestion: ").strip()
        except EOFError:
            break
        if not q:
            continue
        if q.lower() in ("quit", "exit", "q"):
            break
        rc = one(q)
        if rc != 0:
            return rc

    return 0


if __name__ == "__main__":
    sys.exit(main())
