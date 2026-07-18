# PS8: AI for Industrial Knowledge Intelligence - Feature Checklist

This document contains a highly granular, testable, and parallelizable feature checklist for the PS8 hackathon project. 
Tasks are broken down into their smallest units, indicating the **Assigned Developer Role**, **Dependencies**, **Input/Output Contracts**, and **Independent Testing Methods** to allow simultaneous development.

---

## 🛠️ Developer Role Mappings & Parallel Development Strategy
To maximize velocity, the team is divided into 5 roles. Mock outputs should be used for dependent components to allow parallel coding:
- **`BE-1` (Data Engineer)**: Database models, document upload, OCR, text processing, metadata extraction, and vector ingestion.
- **`BE-2` (Search & LLM Engineer)**: Hybrid search index, RAG retrieval logic, AI chat engine, citation generation, and tone modes.
- **`BE-3` (Analytics & Intelligence Engineer)**: Root Cause Analysis (RCA), Temporal prediction, Knowledge Graphs, Cost ROI, and Compliance auditing.
- **`FE-1` (UI Developer - Chat & Shell)**: Main chat interface, citation viewer, sidebar, admin page, and basic API integrations.
- **`FE-2` (UI Developer - Dashboards)**: Interactive timeline, compliance views, dependency graph, and financial charts.

---

## 📂 Phase 1: Database Schema & Ingestion Pipeline (`BE-1` / `FE-1`)

### 1.1 SQL Database Schema Definition (`BE-1`)
*   [x] **Task 1.1.1: Define Core Database Models (SQLAlchemy)** ✅
    *   *Sub-feature*: Create models for `documents` (id, filename, filepath, doc_type, upload_date, status, metadata_json), `equipment` (id, name, serial_number, model, install_date, health_score, status), `maintenance_records` (id, equipment_id, record_date, description, cost, downtime_hours, category, failure_mode), and `inspections` (id, equipment_id, inspection_date, compliance_status, details).
    *   *Contract*: Tables defined in `backend/db/models.py`.
    *   *Testing Method*: Run a script to initialize the SQLite/PostgreSQL database and print the schemas: `python3 -c "from backend.db.models import Base; print(Base.metadata.tables.keys())"`
    *   *Dependencies*: None (Pure schema definition)
*   [x] **Task 1.1.2: Implement Database Session Helper** ✅
    *   *Sub-feature*: Setup sessionmaker and dependency injection engine for FastAPI (`get_db`).
    *   *Contract*: `backend/db/session.py` exporting `get_db` yielding a database session.
    *   *Testing Method*: Test session creation: `python3 -c "from backend.db.session import get_db; db = next(get_db()); print(db.is_active)"`
    *   *Dependencies*: Task 1.1.1

### 1.2 Document Upload & Local File Handler (`BE-1` / `FE-1`)
*   [x] **Task 1.2.1: Local Document Storage Setup**
    *   *Sub-feature*: Initialize folder structures for uploaded raw files under `/data/uploads/` and verify write/read permissions.
    *   *Contract*: Module saving raw stream to file. Returns file path on disk.
    *   *Testing Method*: Call saver function with mock stream and check if file exists: `test_file_exists("/data/uploads/test.pdf")`
    *   *Dependencies*: None
*   [x] **Task 1.2.2: FastAPI File Upload Endpoint (`/api/documents/upload`)**
    *   *Sub-feature*: Implement FastAPI route accepting `UploadFile`, saving via Task 1.2.1, and creating a db record in `documents` with status `PENDING`.
    *   *Contract*: `POST /api/documents/upload` returning JSON `{"document_id": "uuid", "filename": "x.pdf", "status": "PENDING"}`.
    *   *Testing Method*: Send cURL: `curl -X POST -F "file=@/path/to/test.pdf" http://localhost:8000/api/documents/upload`
    *   *Dependencies*: Task 1.1.2, Task 1.2.1
*   [x] **Task 1.2.3: Frontend Drag-and-Drop Dropzone UI (`FE-1`)**
    *   *Sub-feature*: Implement file selection UI box supporting drag-and-drop file uploads.
    *   *Contract*: React component sending files to `/api/documents/upload` and showing loading spinner.
    *   *Testing Method*: Mock api endpoint returning `{"document_id": "123", "filename": "test.pdf"}` and drag-drop a file. Verify success state.
    *   *Dependencies*: None (can mock endpoint)

### 1.3 Preprocessing & Extraction Pipeline (`BE-1`)
*   [ ] **Task 1.3.1: PDF Text Extraction Service**
    *   *Sub-feature*: Set up `pypdf`/`pdfplumber` to extract page-by-page text.
    *   *Contract*: Function `extract_pdf_text(file_path: str) -> List[Dict[str, Any]]` where each dict contains `{"page": int, "text": str}`.
    *   *Testing Method*: Run: `python3 -c "from backend.ingestion.pdf import extract_pdf_text; print(extract_pdf_text('data/sample.pdf')[0])"`
    *   *Dependencies*: None
*   [ ] **Task 1.3.2: OCR Text Extraction Engine (EasyOCR/Tesseract)**
    *   *Sub-feature*: Create an image-to-text pipeline that processes scanned PDF pages and images.
    *   *Contract*: Function `extract_ocr_text(file_path: str) -> List[Dict[str, Any]]`.
    *   *Testing Method*: Run: `python3 -c "from backend.ingestion.ocr import extract_ocr_text; print(extract_ocr_text('data/scanned.png'))"`
    *   *Dependencies*: None
*   [ ] **Task 1.3.3: Automatic Metadata and Entity Extractor**
    *   *Sub-feature*: Regex and LLM matching modules to extract Equipment ID, Serial Numbers, Document Type (SOP, Manual, Failure Log), and date ranges.
    *   *Contract*: Function `extract_metadata(text: str) -> Dict[str, Any]`.
    *   *Testing Method*: Run unit test with text containing "Pump Model P-101 Serial Number SN-883921" and assert returns: `{"equipment_id": "P-101", "serial_number": "SN-883921", "doc_type": "manual"}`
    *   *Dependencies*: None
*   [ ] **Task 1.3.4: Semantic Text Chunker**
    *   *Sub-feature*: Split extracted text into semantic paragraphs (e.g. splitting at double newlines or headers, keeping tables intact) rather than arbitrary characters.
    *   *Contract*: Function `chunk_text(pages_content: List[Dict], chunk_size: int, overlap: int) -> List[Dict]`. Chunks retain page number, header title, and metadata.
    *   *Testing Method*: Call function and verify that no chunk exceeds size limit and chunks share overlapping boundaries.
    *   *Dependencies*: Task 1.3.1, Task 1.3.2

### 1.4 Vector Storage Pipeline (`BE-1`)
*   [ ] **Task 1.4.1: Chroma Vector Database Connection**
    *   *Sub-feature*: Instantiate and configure local Chroma Client.
    *   *Contract*: Module initialization checking if database folder is ready.
    *   *Testing Method*: Run: `python3 -c "import chromadb; client = chromadb.PersistentClient(path='./db/chroma'); print(client.heartbeat())"`
    *   *Dependencies*: None
*   [ ] **Task 1.4.2: Embedding Generation Wrapper**
    *   *Sub-feature*: Call OpenAI `text-embedding-3-small` or Local HuggingFace embedding models.
    *   *Contract*: Function `get_embeddings(texts: List[str]) -> List[List[float]]`.
    *   *Testing Method*: Run: `python3 -c "from backend.ingestion.embed import get_embeddings; print(len(get_embeddings(['test'])[0]))"` (Should output 1536 for OpenAI)
    *   *Dependencies*: None (Ensure environment keys are loaded)
*   [ ] **Task 1.4.3: Ingestion Pipeline Orchestrator**
    *   *Sub-feature*: Combine text extraction, chunking, metadata extraction, embedding generation, and Chroma insertion in one workflow.
    *   *Contract*: Function `ingest_document(document_id: str) -> bool`. Updates database status to `INGESTED` or `FAILED`.
    *   *Testing Method*: Manually run function on a sample manual and confirm Chroma holds records: `client.get_collection("chunks").count()` returns positive number.
    *   *Dependencies*: Tasks 1.1.2, 1.2.1, 1.3.1, 1.3.4, 1.4.1, 1.4.2

---

## 🔍 Phase 2: RAG, Vector Search & Hybrid Retrieval (`BE-2`)

### 2.1 Lexical & Dense Vector Indexing (`BE-2`)
*   [ ] **Task 2.1.1: Vector Similarity Retriever**
    *   *Sub-feature*: Query Chroma index with query embedding, returning top-k matches with metadata filters.
    *   *Contract*: Function `retrieve_vector_matches(query_vector: List[float], k: int, filters: Dict) -> List[Dict]`.
    *   *Testing Method*: Execute retrieval and verify output matches format: `[{"text": "...", "metadata": {"page": 1, "doc_id": "..."}}]`
    *   *Dependencies*: Task 1.4.1
*   [ ] **Task 2.1.2: BM25 Lexical Retriever**
    *   *Sub-feature*: Instantiate a BM25 index over all document chunks stored in PostgreSQL/Chroma to fetch exact keyword matches.
    *   *Contract*: Class `BM25Index` supporting `.search(query_str: str, k: int, filters: Dict) -> List[Dict]`.
    *   *Testing Method*: Index 3 simple sentences. Search for "overheating". Verify the sentence with "overheating" ranks first.
    *   *Dependencies*: Task 1.3.4

### 2.2 Hybrid Search & Fusion Engine (`BE-2`)
*   [ ] **Task 2.2.1: Reciprocal Rank Fusion (RRF) Implementation**
    *   *Sub-feature*: Merge lists of results from Vector search and BM25 search using the RRF algorithm.
    *   *Contract*: Function `fuse_results(vector_results: List[Dict], bm25_results: List[Dict], k_constant: int = 60) -> List[Dict]`.
    *   *Testing Method*: Pass mock duplicate search result lists with differing ranks. Verify fused scores order the common elements correctly.
    *   *Dependencies*: None (can be developed with mock inputs)
*   [ ] **Task 2.2.2: Metadata Filtering Interface**
    *   *Sub-feature*: Enable filtering by equipment_id, document type, date range, or tag during hybrid search execution.
    *   *Contract*: Combine database filters and Chroma collections filters inside the main query handler.
    *   *Testing Method*: Run: `search_hybrid("bearing failure", filters={"equipment_id": "PUMP-101"})` and verify no records from other pumps return.
    *   *Dependencies*: Tasks 2.1.1, 2.1.2

### 2.3 Ranking & Decay Optimizations (`BE-2`)
*   [ ] **Task 2.3.1: Temporal Recency Decay Function**
    *   *Sub-feature*: Calculate score multipliers based on age of document. Recent logs are boosted; old logs decay exponentially.
    *   *Contract*: Function `apply_recency_decay(score: float, doc_date: datetime, halflife_days: float = 365) -> float`.
    *   *Testing Method*: Pass an age of 365 days. Confirm the decayed score is half of original score.
    *   *Dependencies*: None
*   [ ] **Task 2.3.2: Critical Alert Boosting**
    *   *Sub-feature*: Detect if document chunk contains key terms like "ALERT", "CRITICAL", "FAILURE", and apply score boost.
    *   *Contract*: Boost function integrated into final sorting step.
    *   *Testing Method*: Search for "bearing". Check that chunk containing "CRITICAL ALERT: bearing melted" ranks higher than normal specification manual.
    *   *Dependencies*: Task 2.2.1

---

## 💬 Phase 3: AI Chat Assistant & Conversation Management (`BE-2` / `FE-1`)

### 3.1 Session Manager & History (`BE-2`)
*   [ ] **Task 3.1.1: Conversation Session Storage Schema**
    *   *Sub-feature*: Save and retrieve chat sessions containing a list of messages.
    *   *Contract*: Database routes `get_session_history(session_id: str) -> List[Dict]`.
    *   *Testing Method*: Insert session messages and retrieve. Assert list matches exact inserts.
    *   *Dependencies*: Task 1.1.2
*   [ ] **Task 3.1.2: Context-Aware Buffer Generator**
    *   *Sub-feature*: Compile last K messages of conversation history to pass as LLM context window.
    *   *Contract*: Function `compile_chat_history(session_id: str, limit: int = 5) -> List[Dict]`.
    *   *Testing Method*: Insert 10 messages. Retrieve with limit 3, and confirm only last 3 items are returned.
    *   *Dependencies*: Task 3.1.1

### 3.2 Chat Assistant LLM Routing (`BE-2`)
*   [ ] **Task 3.2.1: RAG Response Prompt Builder**
    *   *Sub-feature*: Craft the system prompt injecting retrieved chunks, user metadata context, and formatting rules.
    *   *Contract*: Function `build_rag_prompt(query: str, context_chunks: List[str], history: List[Dict], mode: str) -> str`.
    *   *Testing Method*: Print prompt output. Confirm placeholder values (chunks, history, query) are injected without layout break.
    *   *Dependencies*: Task 3.1.2
*   [ ] **Task 3.2.2: LLM Completion Client (OpenAI API with Fallbacks)**
    *   *Sub-feature*: Invoke GPT-4 completion with system instructions. If API fails, fall back to Google Gemini or Anthropic API.
    *   *Contract*: Function `generate_completion(prompt: str) -> str`.
    *   *Testing Method*: Mock API failure to trigger fallback block. Check that fallback API response is successfully returned.
    *   *Dependencies*: None
*   [ ] **Task 3.2.3: FastAPI Chat Endpoint `/api/chat`**
    *   *Sub-feature*: Main query handler, accepting question, filters, session ID, and mode.
    *   *Contract*: `POST /api/chat` with body `{"query": str, "session_id": str, "mode": "technical"|"manager", "filters": Dict}` returning JSON answer with metadata list.
    *   *Testing Method*: `curl -X POST -H "Content-Type: application/json" -d '{"query": "Why did pump A fail?", "session_id": "test-session"}' http://localhost:8000/api/chat`
    *   *Dependencies*: Tasks 2.2.1, 3.2.1, 3.2.2

### 3.3 Tone & Presentation Mode Switching (`BE-2` / `FE-1`)
*   [ ] **Task 3.3.1: System Prompt Tone Variations**
    *   *Sub-feature*: Alter system prompts based on toggle. Technical mode (forces focus on specifications, clearances, limits) vs. Manager mode (forces focus on costs, schedules, downstream impacts).
    *   *Contract*: Prompt generation templates matching selected mode.
    *   *Testing Method*: Send a query in "manager" mode. Assert response contains financial keywords (e.g. "Cost", "Loss", "Savings").
    *   *Dependencies*: Task 3.2.1
*   [ ] **Task 3.3.2: Citation & Reference Extractor**
    *   *Sub-feature*: Post-process LLM response or require structured output (JSON schema) to extract citations pointing to specific document, page, and chunk.
    *   *Contract*: Returns structured response: `{"answer": "...", "citations": [{"document_id": "...", "page": 2, "snippet": "..."}]}`.
    *   *Testing Method*: Test parser with mock LLM text containing `[Source: ManualA, Page 4]`. Verify citations parse cleanly into list.
    *   *Dependencies*: Task 3.2.3

### 3.4 Chat UI Development (`FE-1`)
*   [ ] **Task 3.4.1: Message Stream & Bubble Layout**
    *   *Sub-feature*: Create a responsive chat area with User and AI speech bubbles supporting markdown formatting.
    *   *Contract*: React component `ChatWindow` drawing messages.
    *   *Testing Method*: Feed static list of messages to component state. Verify markdown tables and bullet lists display correctly.
    *   *Dependencies*: None
*   [ ] **Task 3.4.2: Citation Overlay Modal & Cards**
    *   *Sub-feature*: Citation cards appearing under AI answers. Clicking them reveals full citation snippet or pdf preview.
    *   *Contract*: Component rendering citation snippets interactively.
    *   *Testing Method*: Click on citation card and confirm popup reveals target page snippet.
    *   *Dependencies*: Task 3.4.1
*   [ ] **Task 3.4.3: Session Sidebar & Metadata Selector**
    *   *Sub-feature*: Left-hand sidebar containing list of previous conversation sessions and checkboxes to filter retrieval.
    *   *Contract*: Active state management linking filters to the API call payload.
    *   *Testing Method*: Select filters. Click "Send" in Chat window and confirm outgoing payload includes the selected filters.
    *   *Dependencies*: None

---

## 📈 Phase 4: Advanced Domain Analytics (`BE-3` / `FE-2`)

### 4.1 Root Cause Analysis (RCA) Engine (`BE-3`)
*   [ ] **Task 4.1.1: Failure Mode Classifier**
    *   *Sub-feature*: Analyze text from historical logs to classify failures into structured fields (e.g. electrical, bearing, seal failure, overheating).
    *   *Contract*: Function `classify_failure_mode(log_text: str) -> Dict[str, Any]`.
    *   *Testing Method*: Pass "motor winding melted due to overload". Assert returns `{"failure_category": "Electrical", "sub_category": "Winding Burnout"}`.
    *   *Dependencies*: None (LLM-based)
*   [ ] **Task 4.1.2: Pattern Correlator**
    *   *Sub-feature*: Analyze failure categories across timestamps and equipment relationships to detect commonalities (e.g. "70% of bearing failures occur when ambient temperature > 35°C").
    *   *Contract*: Function `correlate_failures(equipment_id: str) -> List[Dict[str, Any]]`.
    *   *Testing Method*: Inject 4 mock failure logs with overheating events. Run correlation. Verify output states thermal correlations are high.
    *   *Dependencies*: Task 4.1.1, Task 1.1.2

### 4.2 Temporal Intelligence & Prediction (`BE-3` / `FE-2`)
*   [ ] **Task 4.2.1: Log Date Extractor**
    *   *Sub-feature*: Parse unstructured maintenance reports for dates, ordering events chronologically.
    *   *Contract*: Function `extract_log_dates(text: str) -> Optional[datetime]`.
    *   *Testing Method*: Pass "Serviced on 14th Aug 2025". Confirm parsed date is `2025-08-14`.
    *   *Dependencies*: None
*   [ ] **Task 4.2.2: MTBF & Health Calculator**
    *   *Sub-feature*: Calculate Mean Time Between Failures (MTBF) and current Health Score (weighted on number of failures and severity of recent events).
    *   *Contract*: Endpoint `/api/analytics/health/{equipment_id}` returning health metrics.
    *   *Testing Method*: Request health of equipment with 0 failures (returns ~100) vs 5 failures in 1 month (returns <30).
    *   *Dependencies*: Task 1.1.2
*   [ ] **Task 4.2.3: Predictive Alert Engine**
    *   *Sub-feature*: Check if frequency/patterns of failures indicate an imminent failure event (e.g. Compressor showing 3 vibrations in 6 months predicts failure in 30 days).
    *   *Contract*: Endpoint `/api/analytics/predictive-alerts` listing flagged assets.
    *   *Testing Method*: Mock database state with repeated incidents. Call endpoint and confirm "Compressor-7" appears in list.
    *   *Dependencies*: Task 4.2.2
*   [ ] **Task 4.2.4: Interactive Failure Timeline Chart (`FE-2`)**
    *   *Sub-feature*: Visual timeline plotting historical service records, failures, and predictive alarm thresholds.
    *   *Contract*: Chart rendering events chronologically using Recharts.
    *   *Testing Method*: Pass static timeline dataset to component. Confirm hover tooltip shows exact date and issue description.
    *   *Dependencies*: None (can mock endpoint output)

### 4.3 Equipment Relationship Mapping / Knowledge Graph (`BE-3` / `FE-2`)
*   [ ] **Task 4.3.1: Dependency Topology Extractor**
    *   *Sub-feature*: Build database representation of directed connections: `source_equipment_id` -> `target_equipment_id` (e.g. Pump A feeds Pipeline B).
    *   *Contract*: Service fetching graph nodes and edges: `/api/topology/graph` returning JSON list of nodes and links.
    *   *Testing Method*: Seed 2 mock connections. Fetch endpoint and verify nodes and connections lists match seeded database records.
    *   *Dependencies*: Task 1.1.2
*   [ ] **Task 4.3.2: Cascading Failure Analyzer**
    *   *Sub-feature*: Traversal algorithm to find all downstream processes/equipment affected if a specific node fails.
    *   *Contract*: Function `get_cascade_impact(failed_equipment_id: str) -> List[str]`.
    *   *Testing Method*: Build path `A -> B -> C`. Call function with `A`. Confirm output contains `["B", "C"]`.
    *   *Dependencies*: Task 4.3.1
*   [ ] **Task 4.3.3: Interactive Graph Visualization Component (`FE-2`)**
    *   *Sub-feature*: Render network graph of equipment connections allowing click-to-highlight cascade paths.
    *   *Contract*: React component using React Flow or Vis.js.
    *   *Testing Method*: Verify component draws nodes and arrows correctly. Click node A and confirm nodes B and C are highlighted visually.
    *   *Dependencies*: None (can mock JSON network map)

### 4.4 Financial Cost Impact Analysis (`BE-3` / `FE-2`)
*   [ ] **Task 4.4.1: Cost Calculator Service**
    *   *Sub-feature*: Aggregate part costs, labor costs, and lost-production downtime cost (downtime hours * rate). Compare proactive repair cost with reactive/emergency costs.
    *   *Contract*: Endpoint `/api/economics/roi/{equipment_id}` returning preventive cost vs emergency cost + ROI ratio.
    *   *Testing Method*: Send payload. Verify equation outputs correct ROI value: `ROI = (EmergencyCost - PreventiveCost) / PreventiveCost`.
    *   *Dependencies*: Task 1.1.2
*   [ ] **Task 4.4.2: Financial Dashboard Panel (`FE-2`)**
    *   *Sub-feature*: UI widgets showing cost charts, total estimated savings, and maintenance ROI comparison bars.
    *   *Contract*: React component displaying economic metrics.
    *   *Testing Method*: Render component with mock financial dataset. Confirm currency symbols and decimals are formatted.
    *   *Dependencies*: None

### 4.5 Compliance & Regulatory Auditing (`BE-3` / `FE-2`)
*   [ ] **Task 4.5.1: Compliance Rule Engine**
    *   *Sub-feature*: Parse user manuals or safety guides for inspection frequencies (e.g. "inspected every 365 days") and flag overdue assets.
    *   *Contract*: Function `check_compliance(equipment_id: str) -> Dict[str, Any]`.
    *   *Testing Method*: Seed manual inspection frequency of 12 months, and last inspection as 15 months ago. Confirm returned status is `NON_COMPLIANT`.
    *   *Dependencies*: Tasks 1.1.2, 1.3.3
*   [ ] **Task 4.5.2: Compliance Status Interface (`FE-2`)**
    *   *Sub-feature*: Tab/page displaying a table of regulatory rules, matching inspection dates, and color-coded statuses (Compliant: Green, Overdue: Red).
    *   *Contract*: Table UI rendering data from compliance endpoint.
    *   *Testing Method*: Confirm table highlights overdue columns.
    *   *Dependencies*: None

---

## 🖥️ Phase 5: Dashboard & User Interface (`FE-1` / `FE-2`)

### 5.1 Main App Shell & Navigation (`FE-1`)
*   [ ] **Task 5.1.1: Routing & Page Layout**
    *   *Sub-feature*: Set up React router (or custom hooks) separating Chat Interface, Equipment Registry Dashboard, and Administration Upload view.
    *   *Contract*: URL routes `/chat`, `/dashboard`, `/admin`.
    *   *Testing Method*: Click menu items and confirm corresponding component renders in main viewport.
    *   *Dependencies*: None
*   [ ] **Task 5.1.2: Premium CSS Design System & Theme**
    *   *Sub-feature*: Setup dark-mode palette, glassmorphism card panels, smooth transitions, and standard typography in `index.css`.
    *   *Contract*: Predefined root CSS variables for background, text, accent, alert, and success colors.
    *   *Testing Method*: Open app page and confirm dark mode theme renders beautifully with modern fonts.
    *   *Dependencies*: None

### 5.2 Equipment Registry Dashboard (`FE-2`)
*   [ ] **Task 5.2.1: Registry Table Grid**
    *   *Sub-feature*: Grid displaying all assets, serial numbers, status, health score, and MTBF.
    *   *Contract*: Responsive table component with search sorting.
    *   *Testing Method*: Search for "Compressor" and verify table filters out non-compressor assets.
    *   *Dependencies*: None
*   [ ] **Task 5.2.2: Alerts List Panel**
    *   *Sub-feature*: Actionable panel listing current critical alerts and predicted failure warnings.
    *   *Contract*: Scrollable side widget drawing priority status alerts.
    *   *Testing Method*: Push warning state into alerts list. Confirm card changes layout and border color to red.
    *   *Dependencies*: None

### 5.3 Admin Panel UI (`FE-1`)
*   [ ] **Task 5.3.1: Document Catalog Grid**
    *   *Sub-feature*: List uploaded files, files sizes, extraction statuses (Uploading, Processing, Success, Failed), and document types.
    *   *Contract*: React table calling `/api/documents/list`.
    *   *Testing Method*: Fetch mock catalog array. Verify status values map to correct icon indicators (e.g. checkmark, error sign).
    *   *Dependencies*: None
*   [ ] **Task 5.3.2: Vector Storage Monitor Panel**
    *   *Sub-feature*: Metric cards displaying total chunks, collection count, average length, and vector DB heartbeat status.
    *   *Contract*: API endpoint fetch and display widget.
    *   *Testing Method*: Render panel with mock DB stats. Check for fallback display if backend database is offline.
    *   *Dependencies*: None

---

## 🚀 Phase 6: Polish, Integration & Seeding (`BE-1` / `BE-2` / `FE-1`)

### 6.1 Database Seeding & Mock Data (`BE-1`)
*   [ ] **Task 6.1.1: Maintenance Logs Seeder Script**
    *   *Sub-feature*: Create a python script generating 10-15 mock maintenance records containing failure modes, dates, and repair costs for P-101, C-302, and V-401.
    *   *Contract*: CLI script `python3 -m backend.db.seed`.
    *   *Testing Method*: Run script and query DB: `select count(*) from maintenance_records` must be >10.
    *   *Dependencies*: Tasks 1.1.1, 1.1.2
*   [ ] **Task 6.1.2: Sample Reference Documents**
    *   *Sub-feature*: Add 3-5 real or synthetic OEM specifications PDF manuals into raw storage to serve as vector query source material.
    *   *Contract*: Files stored under `data/samples/`.
    *   *Testing Method*: Verify files are valid PDFs. Run chunker script and verify text returns.
    *   *Dependencies*: None

### 6.2 Error Resilience & Fallbacks (`BE-1` / `BE-2`)
*   [ ] **Task 6.2.1: Ingestion Failure Recovery**
    *   *Sub-feature*: Wrap OCR and extraction jobs in try-catch blocks. If ingestion fails, flag status as `FAILED` in the database with log details rather than crashing server.
    *   *Contract*: Safe transaction commit during failures.
    *   *Testing Method*: Upload corrupted text file/broken image. Verify database changes status to `FAILED`.
    *   *Dependencies*: Task 1.4.3
*   [ ] **Task 6.2.2: RAG Hallucination Guardrails**
    *   *Sub-feature*: Inject strict parameters ensuring LLM only replies when facts are verified in the context, returning "Information not found in database" otherwise.
    *   *Contract*: System prompt testing validation checks.
    *   *Testing Method*: Ask chat: "What is the capital of France?". Verify it returns the default "not found" response or restricts output to the industrial equipment domain.
    *   *Dependencies*: Task 3.2.1

### 6.3 Final End-to-End Testing (`BE-1` / `BE-2` / `FE-1`)
*   [ ] **Task 6.3.1: End-to-End CLI Pipeline Test**
    *   *Sub-feature*: Integration test script that uploads a document, runs ingestion, performs vector query, and queries LLM chat.
    *   *Contract*: Integrates FastAPI test client routes.
    *   *Testing Method*: Run script: `pytest backend/tests/test_e2e.py`
    *   *Dependencies*: All Backend Tasks
*   [ ] **Task 6.3.2: Production Build Pipeline Verification**
    *   *Sub-feature*: Verify React build output compiles cleanly and FastAPI runs with Gunicorn/Uvicorn configuration.
    *   *Contract*: Production build scripts running without warning.
    *   *Testing Method*: Run: `cd frontend && npm run build` and check for errors. Run backend server in production configurations.
    *   *Dependencies*: All Frontend Tasks
