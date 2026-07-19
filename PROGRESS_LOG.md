## [2026-07-19] Redundant metadata_json Removal & Chroma Vector Dimension Mismatch Recovery
- What was done:
  - **Removed Redundant `metadata_json` Output**: Removed the escaped `metadata_json` string field from `GET /api/documents/{id}` and `GET /api/documents/list` responses in `backend/routes/documents.py`. API clients now receive clean, non-redundant parsed `metadata` objects without escaped slashes.
  - **Chroma Embedding Dimension Mismatch Recovery**: Added automatic error recovery in `backend/ingestion/pipeline.py` and `backend/ingestion/vector_store.py`. If an embedding model change occurs (e.g., from 384-dim to 768-dim), Chroma's `InvalidArgumentError` is caught, the collection is automatically reset/recreated for the new dimension, and vector upserts succeed seamlessly.
  - **Test Suite Updates & Validation**: Updated unit test helpers in `test_phase_1_2.py` and added `test_ingest_document_dimension_mismatch_recovery` in `test_phase_1_4.py`. All 56 backend unit tests passed.
- Files changed: `backend/routes/documents.py`, `backend/ingestion/pipeline.py`, `backend/ingestion/vector_store.py`, `backend/tests/test_phase_1_2.py`, `backend/tests/test_phase_1_4.py`, `PROGRESS_LOG.md`.
- Status: Done
---
## [2026-07-18 16:06] Project Scaffold Setup
- What was done: Created the foundational project structure for PS8, including frontend, backend, data, and docs directories. Setup the tracking files.
- Files changed/created: FEATURE_CHECKLIST.md, PROGRESS_LOG.md, .env.example, .gitignore, README.md, backend/, frontend/, data/, docs/
- Status: Done
- Notes: Used Vite with React for the frontend as per instructions. FastAPI setup with basic structure for the backend.
---
## [2026-07-19] Ingestion Metadata Grounding & Equipment-ID API Correction
- What was done: Hardened metadata extraction so explicit equipment tags and serial numbers found by regex in the source text override LLM output. LLM identifiers not present in the source text are discarded, preventing plausible-but-fabricated equipment/serial IDs from creating or linking incorrect registry entries. Updated the Ollama extraction prompt to keep informal names in `equipment_name` and reserve `equipment_id` for explicit asset tags.
- API contract correction: `GET /api/documents/{id}` and `GET /api/documents/list` now return `equipment_id` as the extracted asset tag (for example `P-101`) and expose the database foreign-key UUID separately as `equipment_registry_id`. The UUID is intentional internal registry linkage, not the extracted equipment identifier.
- Files changed: `backend/ingestion/metadata.py`, `backend/routes/documents.py`, `backend/tests/test_phase_1_2.py`, `backend/tests/test_phase_1_3.py`, `PROGRESS_LOG.md`.
- Verification: New focused tests passed (equipment-tag grounding and public API field mapping). The broad legacy Phase 1 suite still has five unrelated failures: invalid-PDF auto-ingest timing in one upload test, two outdated tests expecting `dates` instead of `dates_mentioned`, and two Windows-incompatible vector-store tests that set the path to `/fake/dir`.
- Status: Done
---
## [2026-07-18 16:57] Expanded Feature Checklist for Parallel Development
- What was done: Expanded the FEATURE_CHECKLIST.md file in extreme depth, breaking down every feature into testable sub-features down to the smallest units. Assigned developer roles, defined contracts, and established independent testing methods for parallel collaboration.
- Files changed/created: FEATURE_CHECKLIST.md, PROGRESS_LOG.md
- Status: Done
- Notes: Aligned the features with the PS8 Hackathon Proposal document.
---
## [2026-07-18 17:17] Phase 1.1 Complete – Database Schema & Session Helper
- What was done: Implemented all SQLAlchemy ORM models (8 tables: documents, document_chunks, equipment, maintenance_records, inspections, equipment_dependencies, chat_sessions, chat_messages) and the database session helper with FastAPI dependency injection. Updated main.py to auto-initialise tables at startup via lifespan events. Uses SQLite for dev by default, PostgreSQL via DATABASE_URL env var.
- Files changed/created: backend/db/models.py (new), backend/db/session.py (new), backend/db/__init__.py (updated), backend/main.py (updated), data/ps8_dev.db (auto-created)
- Status: Done
- Notes: All 8 tables verified in SQLite. Insert/query/delete smoke test passed. Schema includes UUID PKs, proper FKs, indexes, and enum-like string columns for portability.
---
## [2026-07-18 17:43] Phase 1.2 Complete – Document Upload & Local File Handler
- What was done: Implemented all 3 tasks of Phase 1.2:
  - **Task 1.2.1** – Local Document Storage Setup: Created `backend/services/file_storage.py` with `save_upload()`, `delete_upload()`, `file_exists()`, and `get_upload_dir()` functions. Files saved under `data/uploads/` with UUID-prefixed collision-safe filenames and optional date-based subdirectories (YYYY/MM/DD).
  - **Task 1.2.2** – FastAPI File Upload Endpoint: Created `backend/routes/documents.py` with 4 endpoints: `POST /api/documents/upload` (accepts UploadFile, saves to disk, creates DB record with status PENDING), `GET /api/documents/list` (paginated with status/type filters), `GET /api/documents/{id}`, `DELETE /api/documents/{id}`. Registered router in `backend/main.py`.
  - **Task 1.2.3** – Frontend Drag-and-Drop Dropzone UI: Created `frontend/src/components/FileDropzone.jsx` with drag-and-drop support, document type selector, upload queue with loading/success/error states, and `frontend/src/services/api.js` centralised API client. Premium dark-mode glassmorphic CSS styling.
- Files changed/created: backend/services/file_storage.py (new), backend/routes/documents.py (new), backend/main.py (updated), frontend/src/components/FileDropzone.jsx (new), frontend/src/components/FileDropzone.css (new), frontend/src/services/api.js (new), backend/tests/test_phase_1_2.py (new), FEATURE_CHECKLIST.md (updated)
- Status: Done
- Notes: Virtual environment created (`venv/`). All 16 pytest tests passed (7 file storage + 9 endpoint tests). Backend tested via FastAPI TestClient. Created `backend/tests/` package with comprehensive test coverage.
---
## [2026-07-18 18:46] Phase 1.3 & 1.4 Completion – Preprocessing Pipeline & Vector Storage
- What is being done:
  - **Task 1.3.1** – Verify & harden PDF Text Extraction Service (`backend/ingestion/pdf.py`). Code exists but is unchecked – validate contract, add error handling, mark complete.
  - **Task 1.3.2** – Verify & harden OCR Text Extraction Engine (`backend/ingestion/ocr.py`). Code exists – validate contract, add fallback to pytesseract, mark complete.
  - **Task 1.3.3** – Verify & harden Automatic Metadata and Entity Extractor (`backend/ingestion/metadata.py`). Code exists – validate regex patterns, add date range extraction, mark complete.
  - **Task 1.3.4** – Verify & harden Semantic Text Chunker (`backend/ingestion/chunker.py`). Code exists – validate chunk size limits, overlap logic, header detection, mark complete.
  - **Task 1.4.1** – Build Chroma Vector Database Connection (`backend/ingestion/vector_store.py`). New file – instantiate PersistentClient, create/get collection, health check.
  - **Task 1.4.2** – Build Embedding Generation Wrapper (`backend/ingestion/embed.py`). New file – support both OpenAI `text-embedding-3-small` and local HuggingFace `sentence-transformers` fallback.
  - **Task 1.4.3** – Build Ingestion Pipeline Orchestrator (`backend/ingestion/pipeline.py`). New file – full pipeline combining extract → chunk → metadata → embed → Chroma insert. Updates document status to INGESTED/FAILED. Wire to FastAPI route for triggering post-upload.
  - Add comprehensive unit tests for all Phase 1.3 and 1.4 modules.
  - Update `requirements.txt` with any new dependencies.
- Files changed/created: backend/ingestion/pdf.py (updated), backend/ingestion/ocr.py (updated), backend/ingestion/metadata.py (updated), backend/ingestion/chunker.py (updated), backend/ingestion/vector_store.py (new), backend/ingestion/embed.py (new), backend/ingestion/pipeline.py (new), backend/routes/documents.py (updated), backend/requirements.txt (updated), FEATURE_CHECKLIST.md (updated)
- Status: Done
- Notes: 1.3.x code files existed as stubs from initial scaffolding but were never tested or marked complete. 1.4.x is entirely new.
---
## [2026-07-19] Ollama Embedding Model Separation
- What was done: Corrected the embedding wrapper to use only Ollama's current batch endpoint, `/api/embed`; the removed legacy `/api/embeddings` fallback was the source of the 404 log. Added `OLLAMA_EMBEDDING_MODEL`, separate from `OLLAMA_MODEL`, so a chat/metadata model cannot be incorrectly used for vector generation.
- Environment behavior: `gpt-oss:120b-cloud` is retained for metadata extraction. Its local Ollama model record advertises completion/tools/thinking only, so embeddings now use the local HuggingFace fallback until a dedicated model (for example `embeddinggemma`) is installed and configured.
- Files changed: `backend/ingestion/embed.py`, `.env`, `.env.example`, `backend/tests/test_phase_1_4.py`, `PROGRESS_LOG.md`.
- Verification: Six embedding-focused tests passed, including a regression test confirming `/api/embed` receives `OLLAMA_EMBEDDING_MODEL`; changed module compiles cleanly.
- Status: Done
---
## [2026-07-19] Analytics-Ready Ingestion Metadata Schema
- What was done: Added schema version 2.0 enrichment for multi-equipment documents, structured monetary costs, typed event dates, inspection status/date, severity normalisation, and deterministic date compatibility fields. Root causes are now retained only when the source sentence contains explicit causal evidence, avoiding symptoms being reported as causes.
- API contract: Document detail/list responses retain `metadata_json` for backward compatibility and now also expose parsed `metadata`, removing the need for clients to decode an escaped JSON string.
- Files changed: `backend/ingestion/metadata.py`, `backend/ingestion/pipeline.py`, `backend/routes/documents.py`, `backend/tests/test_phase_1_2.py`, `backend/tests/test_phase_1_3.py`, `PROGRESS_LOG.md`.
- Verification: 26 metadata/chunking tests and the API metadata mapping test passed; changed ingestion and route modules compile cleanly.
- Status: Done
---
