"""
---------------
Central configuration for Part B — hardcoded, offline-friendly.
No environment variables used anywhere.

CHANGES FROM ORIGINAL:
  1. Added COLLECTION_PROPS and COLLECTION_SECTIONS (new dual-collection schema)
  2. Removed apply_parta_service_env() — no longer needed (no env vars)
  3. PARTA_DATA_DIR now points to data/checkpoints/ for _ready.json reads
  4. Removed reference to old COLLECTION_NAME (was single flat collection)
  5. ENTITY_LABELS aligned with ingest_neo4j.py labels (equipment, metric, etc.)
"""
from __future__ import annotations

from pathlib import Path

# ── Directory layout ──────────────────────────────────────────────────────────
# Repo structure:   .../project/parta/   and   .../project/partb/
PARTB_DIR    = Path(__file__).resolve().parent
REPO_ROOT    = PARTB_DIR.parent
PARTA_DIR    = REPO_ROOT / "parta"
PORTABLE_DIR = PARTA_DIR / "portable"
RERANKER_DIR = PORTABLE_DIR / "reranker"

# Part A data directories
PARTA_DATA_DIR       = PARTA_DIR / "data"
CHECKPOINTS_DIR      = PARTA_DATA_DIR / "checkpoints"   # _ready.json files
METADATA_DIR         = PARTA_DATA_DIR / "metadata"      # _metadata.json files
QDRANT_LOG_DIR       = PARTA_DATA_DIR / "qdrant"        # _chunks.json logs
PARTA_RAW_DIR        = PARTA_DATA_DIR / "raw"
# ── MongoDB ───────────────────────────────────────────────────────────────────
MONGO_URI = "mongodb://localhost:27017"
MONGO_DB  = "rag_system"

# ── JWT — must match Part A ───────────────────────────────────────────────────
JWT_SECRET       = "ISRO_RAG_SECRET_CHANGE_IN_PROD"  # MUST match parta/main_api.py
JWT_ALGORITHM    = "HS256"
JWT_EXPIRE_HOURS = 8

# ── LLM routing ───────────────────────────────────────────────────────────────
OLLAMA_URL         = "http://127.0.0.1:11434"
USE_OLLAMA_DIRECT  = True
LITELLM_BASE_URL   = "http://127.0.0.1:4000"
LITELLM_API_KEY    = ""

# ── Qdrant — two-collection schema (aligned with ingest_qdrant.py) ────────────
QDRANT_URL          = "http://localhost:6333"
COLLECTION_PROPS       = "propositions"   # atomic sentence vectors — precise facts
COLLECTION_SECTIONS    = "sections"       # full section chunk vectors — context
COLLECTION_SELECTIONS  = COLLECTION_SECTIONS  # alias used by health checks

# ── Neo4j ─────────────────────────────────────────────────────────────────────
NEO4J_URI      = "bolt://localhost:7687"
NEO4J_USER     = "neo4j"
NEO4J_PASSWORD = "sac@1234"

# ── GLiNER entity labels — must match ingest_neo4j.py ENTITY_LABELS ──────────
ENTITY_LABELS = [
    "equipment",
    "metric",
    "organization",
    "location",
    "identifier",
    "concept",
    "person",
]

# ── Retrieval constants ───────────────────────────────────────────────────────
GLINER_QUERY_THRESHOLD = 0.35
BOOST_BOTH             = 0.12   # score bonus for sections found by both Qdrant+Neo4j
LONG_CHUNK_WORDS       = 450    # sections longer than this are sub-segmented

# How many propositions to fetch in Step 1 of retrieval
PROP_RETRIEVE_LIMIT = 40
# How many sections to fetch in Step 4 (direct section search)
SECT_RETRIEVE_LIMIT = 20
# Max Neo4j section name hits per entity query
NEO4J_ENTITY_LIMIT     = 200
PAGE_EXPAND_MAX_CHARS  = 9000

# ── Mode configuration ────────────────────────────────────────────────────────
MODE_ORDER = ("fast", "balanced", "deep")

MODE_CONFIG: dict[str, dict] = {
    "fast": {
        "ollama_model":         "gemma3:1b",
        "litellm_model":        "ollama/gemma3:1b",
        "prop_retrieve_limit":  PROP_RETRIEVE_LIMIT,
        "sect_retrieve_limit":  SECT_RETRIEVE_LIMIT,
        "final_top_n":          8,
        "context_max_chars":    12000,
        "history_pairs":        3,
        "llm_timeout_s":        600.0,
    },
    "balanced": {
        "ollama_model":         "mistral:7b-instruct-q4_K_M",
        "litellm_model":        "ollama/mistral:7b-instruct-q4_K_M",
        "prop_retrieve_limit":  PROP_RETRIEVE_LIMIT,
        "sect_retrieve_limit":  SECT_RETRIEVE_LIMIT,
        "final_top_n":          8,
        "context_max_chars":    14000,
        "history_pairs":        5,
        "llm_timeout_s":        600.0,
    },
    "deep": {
        "ollama_model":         "llama3.1:8b-instruct-q4_K_M",
        "litellm_model":        "ollama/llama3.1:8b-instruct-q4_K_M",
        "prop_retrieve_limit":  48,
        "sect_retrieve_limit":  24,
        "final_top_n":          10,
        "context_max_chars":    16000,
        "history_pairs":        6,
        "llm_timeout_s":        600.0,
    },
}

