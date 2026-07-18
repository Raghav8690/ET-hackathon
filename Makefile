# ============================================================================
# PS8 – Project Makefile
# Works on macOS / Linux (make) and Windows (make via choco/scoop or nmake)
# ============================================================================

# ── Python / venv paths (auto-detect OS) ────────────────────────────────────
ifeq ($(OS),Windows_NT)
    VENV_DIR   = .venv
    PYTHON     = $(VENV_DIR)\Scripts\python.exe
    PIP        = $(VENV_DIR)\Scripts\pip.exe
    ACTIVATE   = $(VENV_DIR)\Scripts\activate
    SEP        = \\
    RM_RF      = rmdir /s /q
    MKDIR      = mkdir
    NPM        = npm.cmd
else
    VENV_DIR   = .venv
    PYTHON     = $(VENV_DIR)/bin/python
    PIP        = $(VENV_DIR)/bin/pip
    ACTIVATE   = source $(VENV_DIR)/bin/activate
    SEP        = /
    RM_RF      = rm -rf
    MKDIR      = mkdir -p
    NPM        = npm
endif

# ── Directories ─────────────────────────────────────────────────────────────
BACKEND_DIR  = backend
FRONTEND_DIR = frontend

# ── Default target ──────────────────────────────────────────────────────────
.PHONY: help
help: ## Show this help
	@echo ""
	@echo "  PS8 - AI for Industrial Knowledge Intelligence"
	@echo "  =============================================="
	@echo ""
	@echo "  Setup:"
	@echo "    make setup       – Create venv + install all deps (backend & frontend)"
	@echo "    make venv        – Create Python venv only"
	@echo "    make install     – Install Python backend dependencies"
	@echo "    make install-fe  – Install Node frontend dependencies"
	@echo ""
	@echo "  Run:"
	@echo "    make dev         – Run backend AND frontend concurrently"
	@echo "    make back        – Run FastAPI backend only"
	@echo "    make front       – Run React frontend only"
	@echo ""
	@echo "  Database:"
	@echo "    make db-init     – Create / migrate database tables"
	@echo "    make db-reset    – Drop and re-create all tables (WARNING: data loss)"
	@echo ""
	@echo "  Quality:"
	@echo "    make lint        – Lint frontend code"
	@echo "    make test        – Run backend tests"
	@echo ""
	@echo "  Build:"
	@echo "    make build       – Build frontend for production"
	@echo ""
	@echo "  Cleanup:"
	@echo "    make clean       – Remove venv, caches, and build artifacts"
	@echo ""

# ════════════════════════════════════════════════════════════════════════════
# SETUP
# ════════════════════════════════════════════════════════════════════════════

.PHONY: venv
venv: ## Create virtual environment with uv (fallback: python -m venv)
	@if command -v uv > /dev/null 2>&1; then \
		echo "→ Creating venv with uv (Python 3.12)..."; \
		uv venv $(VENV_DIR) --python 3.12 --seed; \
	else \
		echo "→ uv not found, falling back to python3 -m venv..."; \
		python3 -m venv $(VENV_DIR); \
	fi
	@echo "✅  Virtual environment ready at $(VENV_DIR)/"

.PHONY: install
install: ## Install backend Python dependencies
	@if command -v uv > /dev/null 2>&1; then \
		echo "→ Installing backend deps with uv..."; \
		uv pip install -r $(BACKEND_DIR)/requirements.txt; \
	else \
		echo "→ Installing backend deps with pip..."; \
		$(PIP) install -r $(BACKEND_DIR)/requirements.txt; \
	fi
	@echo "✅  Backend dependencies installed."

.PHONY: install-fe
install-fe: ## Install frontend Node dependencies
	@echo "→ Installing frontend deps..."
	@cd $(FRONTEND_DIR) && $(NPM) install
	@echo "✅  Frontend dependencies installed."

.PHONY: setup
setup: venv install install-fe ## Full project setup (venv + backend + frontend)
	@echo ""
	@echo "🎉  Setup complete! Run 'make dev' to start developing."

# ════════════════════════════════════════════════════════════════════════════
# RUN
# ════════════════════════════════════════════════════════════════════════════

.PHONY: back
back: ## Start FastAPI backend (with hot-reload)
	@echo "→ Starting backend at http://localhost:8000 ..."
	$(PYTHON) -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

.PHONY: front
front: ## Start React Vite dev server
	@echo "→ Starting frontend..."
	@cd $(FRONTEND_DIR) && $(NPM) run dev

.PHONY: dev
dev: ## Run backend AND frontend concurrently
ifeq ($(OS),Windows_NT)
	@echo "→ Starting backend and frontend (Windows)..."
	start /B $(PYTHON) -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
	cd $(FRONTEND_DIR) && $(NPM) run dev
else
	@echo "→ Starting backend and frontend..."
	@$(PYTHON) -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000 & \
		cd $(FRONTEND_DIR) && $(NPM) run dev; \
		wait
endif

# ════════════════════════════════════════════════════════════════════════════
# DATABASE
# ════════════════════════════════════════════════════════════════════════════

.PHONY: db-init
db-init: ## Create all database tables
	@echo "→ Initialising database tables..."
	$(PYTHON) -c "from backend.db.session import init_db; init_db(); print('✅  Tables created.')"

.PHONY: db-reset
db-reset: ## Drop and re-create all tables (DELETES ALL DATA)
	@echo "⚠️  Dropping all tables..."
	$(PYTHON) -c "from backend.db.session import drop_db, init_db; drop_db(); init_db(); print('✅  Database reset.')"

# ════════════════════════════════════════════════════════════════════════════
# QUALITY
# ════════════════════════════════════════════════════════════════════════════

.PHONY: lint
lint: ## Lint frontend code
	@cd $(FRONTEND_DIR) && $(NPM) run lint

.PHONY: test
test: ## Run backend tests with pytest
	$(PYTHON) -m pytest tests/ -v

# ════════════════════════════════════════════════════════════════════════════
# BUILD
# ════════════════════════════════════════════════════════════════════════════

.PHONY: build
build: ## Build frontend for production
	@echo "→ Building frontend..."
	@cd $(FRONTEND_DIR) && $(NPM) run build
	@echo "✅  Frontend built to $(FRONTEND_DIR)/dist/"

# ════════════════════════════════════════════════════════════════════════════
# CLEANUP
# ════════════════════════════════════════════════════════════════════════════

.PHONY: clean
clean: ## Remove venv, caches, and build artifacts
	@echo "→ Cleaning up..."
	$(RM_RF) $(VENV_DIR)
	$(RM_RF) $(FRONTEND_DIR)$(SEP)node_modules
	$(RM_RF) $(FRONTEND_DIR)$(SEP)dist
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@echo "✅  Clean."
