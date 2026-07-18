"""
PS8 – Core Database Models (SQLAlchemy ORM)

Defines every persistent entity required by the Industrial Knowledge Intelligence
platform.  All tables use UUID primary keys so records created across services
never collide.

Tables
------
documents          – Uploaded files & their processing status.
document_chunks    – Semantic text chunks extracted from documents (indexed in
                     the vector DB as well, but metadata lives here).
equipment          – Physical equipment / asset registry.
maintenance_records – Per-equipment maintenance & failure history.
inspections        – Regulatory / compliance inspection log.
equipment_dependencies – Directed graph edges for cascade-failure analysis.
chat_sessions      – Conversation sessions for the AI assistant.
chat_messages      – Individual messages within a chat session.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, relationship


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------
class Base(DeclarativeBase):
    """Declarative base shared across all models."""
    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _uuid() -> str:
    """Generate a new UUID4 as a string (portable across SQLite & PG)."""
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    """Timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
DOCUMENT_TYPE_VALUES = (
    "SOP",        # Standard Operating Procedure
    "MANUAL",     # OEM / vendor manual
    "REPORT",     # Maintenance / incident report
    "INSPECTION", # Inspection record
    "COMPLIANCE", # Regulatory / compliance document
    "SCHEMATIC",  # Technical drawing / P&ID
    "OTHER",
)

DOCUMENT_STATUS_VALUES = (
    "PENDING",    # Uploaded, not yet processed
    "PROCESSING", # Extraction / embedding in progress
    "INGESTED",   # Successfully vectorised
    "FAILED",     # Processing failed
)

EQUIPMENT_STATUS_VALUES = (
    "OPERATIONAL",
    "DEGRADED",
    "DOWN",
    "DECOMMISSIONED",
)

COMPLIANCE_STATUS_VALUES = (
    "COMPLIANT",
    "NON_COMPLIANT",
    "PENDING_REVIEW",
)

FAILURE_CATEGORY_VALUES = (
    "MECHANICAL",
    "ELECTRICAL",
    "HYDRAULIC",
    "THERMAL",
    "CORROSION",
    "INSTRUMENTATION",
    "SOFTWARE",
    "HUMAN_ERROR",
    "UNKNOWN",
)

CHAT_MESSAGE_ROLE_VALUES = (
    "USER",
    "ASSISTANT",
    "SYSTEM",
)


# ---------------------------------------------------------------------------
# 1. Documents
# ---------------------------------------------------------------------------
class Document(Base):
    """An uploaded file – PDF, Word, Excel, or scanned image."""

    __tablename__ = "documents"

    id = Column(String(36), primary_key=True, default=_uuid)
    filename = Column(String(512), nullable=False, comment="Original upload filename")
    filepath = Column(String(1024), nullable=False, comment="On-disk storage path")
    file_size_bytes = Column(Integer, nullable=True, comment="Size of the raw file")
    doc_type = Column(
        String(20),
        nullable=False,
        default="OTHER",
        comment="One of: " + ", ".join(DOCUMENT_TYPE_VALUES),
    )
    status = Column(
        String(20),
        nullable=False,
        default="PENDING",
        comment="One of: " + ", ".join(DOCUMENT_STATUS_VALUES),
    )
    upload_date = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    processed_date = Column(DateTime(timezone=True), nullable=True)

    # Extracted metadata (JSON-like free text stored as TEXT for SQLite compat)
    metadata_json = Column(Text, nullable=True, comment="Auto-extracted metadata as JSON string")

    # Relationships
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")

    # Linked equipment (optional manual or auto-detected association)
    equipment_id = Column(String(36), ForeignKey("equipment.id"), nullable=True)
    equipment = relationship("Equipment", back_populates="documents")

    # Date range covered by the document
    date_range_start = Column(DateTime(timezone=True), nullable=True)
    date_range_end = Column(DateTime(timezone=True), nullable=True)

    # Compliance relevance flag
    compliance_relevant = Column(Boolean, default=False, nullable=False)

    # Error details when status == FAILED
    error_message = Column(Text, nullable=True)

    __table_args__ = (
        Index("ix_documents_status", "status"),
        Index("ix_documents_doc_type", "doc_type"),
        Index("ix_documents_equipment_id", "equipment_id"),
    )

    def __repr__(self) -> str:
        return f"<Document(id={self.id!r}, filename={self.filename!r}, status={self.status!r})>"


# ---------------------------------------------------------------------------
# 2. Document Chunks
# ---------------------------------------------------------------------------
class DocumentChunk(Base):
    """A semantic text chunk extracted from a document.

    The vector embedding itself is stored in Chroma; this table holds the
    metadata and original text so we can reconstruct citations.
    """

    __tablename__ = "document_chunks"

    id = Column(String(36), primary_key=True, default=_uuid)
    document_id = Column(String(36), ForeignKey("documents.id"), nullable=False)

    chunk_index = Column(Integer, nullable=False, comment="Order within the parent document")
    text = Column(Text, nullable=False, comment="Raw extracted text for this chunk")
    page_number = Column(Integer, nullable=True, comment="Source page (1-indexed)")
    section_title = Column(String(512), nullable=True, comment="Header / section if detected")

    # Token count so we can enforce context-window limits downstream
    token_count = Column(Integer, nullable=True)

    # Chroma vector ID (may differ from row id if re-embedded)
    vector_id = Column(String(128), nullable=True, comment="Corresponding ID in the vector store")

    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    # Relationships
    document = relationship("Document", back_populates="chunks")

    __table_args__ = (
        Index("ix_chunks_document_id", "document_id"),
        Index("ix_chunks_vector_id", "vector_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<DocumentChunk(id={self.id!r}, doc={self.document_id!r}, "
            f"idx={self.chunk_index})>"
        )


# ---------------------------------------------------------------------------
# 3. Equipment
# ---------------------------------------------------------------------------
class Equipment(Base):
    """Physical asset / equipment registry entry."""

    __tablename__ = "equipment"

    id = Column(String(36), primary_key=True, default=_uuid)
    name = Column(String(256), nullable=False, comment="Human-readable name, e.g. 'Pump A'")
    serial_number = Column(String(128), nullable=True, unique=True)
    model = Column(String(256), nullable=True, comment="Manufacturer model identifier")
    manufacturer = Column(String(256), nullable=True)
    location = Column(String(512), nullable=True, comment="Plant / area / bay")
    install_date = Column(DateTime(timezone=True), nullable=True)

    # Computed fields (refreshed by analytics services)
    health_score = Column(Float, nullable=True, default=100.0, comment="0-100 health metric")
    status = Column(
        String(20),
        nullable=False,
        default="OPERATIONAL",
        comment="One of: " + ", ".join(EQUIPMENT_STATUS_VALUES),
    )

    # OEM-recommended maintenance interval in days
    oem_maintenance_interval_days = Column(Integer, nullable=True)
    # OEM-recommended inspection interval in days
    oem_inspection_interval_days = Column(Integer, nullable=True)

    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    # Relationships
    documents = relationship("Document", back_populates="equipment")
    maintenance_records = relationship(
        "MaintenanceRecord", back_populates="equipment", cascade="all, delete-orphan"
    )
    inspections = relationship(
        "Inspection", back_populates="equipment", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_equipment_name", "name"),
        Index("ix_equipment_status", "status"),
    )

    def __repr__(self) -> str:
        return f"<Equipment(id={self.id!r}, name={self.name!r}, status={self.status!r})>"


# ---------------------------------------------------------------------------
# 4. Maintenance Records
# ---------------------------------------------------------------------------
class MaintenanceRecord(Base):
    """A single maintenance event or failure incident for an equipment asset."""

    __tablename__ = "maintenance_records"

    id = Column(String(36), primary_key=True, default=_uuid)
    equipment_id = Column(String(36), ForeignKey("equipment.id"), nullable=False)

    record_date = Column(DateTime(timezone=True), nullable=False, comment="When the event occurred")
    description = Column(Text, nullable=False, comment="Free-text description of the event")

    # Cost tracking
    parts_cost = Column(Float, nullable=True, default=0.0)
    labor_cost = Column(Float, nullable=True, default=0.0)
    total_cost = Column(Float, nullable=True, default=0.0)
    downtime_hours = Column(Float, nullable=True, default=0.0)

    # Classification
    failure_mode = Column(
        String(64),
        nullable=True,
        comment="Specific failure mode, e.g. 'Bearing Overheating'",
    )
    failure_category = Column(
        String(20),
        nullable=True,
        default="UNKNOWN",
        comment="One of: " + ", ".join(FAILURE_CATEGORY_VALUES),
    )
    is_failure = Column(Boolean, default=False, comment="True if this was an unplanned failure")
    is_preventive = Column(Boolean, default=False, comment="True if this was scheduled maintenance")
    severity = Column(
        String(10),
        nullable=True,
        default="MEDIUM",
        comment="LOW / MEDIUM / HIGH / CRITICAL",
    )

    # Environmental conditions at time of event (for correlation analysis)
    ambient_temperature_c = Column(Float, nullable=True)
    humidity_pct = Column(Float, nullable=True)

    # Link back to source document if extracted from a report
    source_document_id = Column(String(36), ForeignKey("documents.id"), nullable=True)

    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    # Relationships
    equipment = relationship("Equipment", back_populates="maintenance_records")
    source_document = relationship("Document")

    __table_args__ = (
        Index("ix_maint_equipment_id", "equipment_id"),
        Index("ix_maint_record_date", "record_date"),
        Index("ix_maint_failure_category", "failure_category"),
        Index("ix_maint_is_failure", "is_failure"),
    )

    def __repr__(self) -> str:
        return (
            f"<MaintenanceRecord(id={self.id!r}, equip={self.equipment_id!r}, "
            f"date={self.record_date}, failure={self.is_failure})>"
        )


# ---------------------------------------------------------------------------
# 5. Inspections
# ---------------------------------------------------------------------------
class Inspection(Base):
    """Regulatory / compliance inspection record for an equipment asset."""

    __tablename__ = "inspections"

    id = Column(String(36), primary_key=True, default=_uuid)
    equipment_id = Column(String(36), ForeignKey("equipment.id"), nullable=False)

    inspection_date = Column(DateTime(timezone=True), nullable=False)
    next_due_date = Column(DateTime(timezone=True), nullable=True)
    inspector_name = Column(String(256), nullable=True)

    compliance_status = Column(
        String(20),
        nullable=False,
        default="PENDING_REVIEW",
        comment="One of: " + ", ".join(COMPLIANCE_STATUS_VALUES),
    )

    regulation_reference = Column(String(512), nullable=True, comment="E.g. OSHA 1910.xxx")
    details = Column(Text, nullable=True, comment="Inspection notes / findings")
    corrective_action = Column(Text, nullable=True, comment="Required follow-up if non-compliant")

    source_document_id = Column(String(36), ForeignKey("documents.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    # Relationships
    equipment = relationship("Equipment", back_populates="inspections")
    source_document = relationship("Document")

    __table_args__ = (
        Index("ix_insp_equipment_id", "equipment_id"),
        Index("ix_insp_compliance_status", "compliance_status"),
        Index("ix_insp_inspection_date", "inspection_date"),
    )

    def __repr__(self) -> str:
        return (
            f"<Inspection(id={self.id!r}, equip={self.equipment_id!r}, "
            f"status={self.compliance_status!r})>"
        )


# ---------------------------------------------------------------------------
# 6. Equipment Dependencies (Knowledge Graph edges)
# ---------------------------------------------------------------------------
class EquipmentDependency(Base):
    """Directed edge in the equipment relationship graph.

    Example: Pump-A  --supplies-->  Pipeline-B  --fills-->  Tank-C
    Used for cascade-failure impact analysis.
    """

    __tablename__ = "equipment_dependencies"

    id = Column(String(36), primary_key=True, default=_uuid)
    source_equipment_id = Column(String(36), ForeignKey("equipment.id"), nullable=False)
    target_equipment_id = Column(String(36), ForeignKey("equipment.id"), nullable=False)
    relationship_type = Column(
        String(64),
        nullable=False,
        default="supplies",
        comment="Edge label, e.g. 'supplies', 'feeds', 'drains', 'powers'",
    )
    criticality = Column(
        String(10),
        nullable=True,
        default="MEDIUM",
        comment="LOW / MEDIUM / HIGH / CRITICAL",
    )
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    # Relationships (no back_populates – accessed via explicit queries)
    source_equipment = relationship("Equipment", foreign_keys=[source_equipment_id])
    target_equipment = relationship("Equipment", foreign_keys=[target_equipment_id])

    __table_args__ = (
        Index("ix_dep_source", "source_equipment_id"),
        Index("ix_dep_target", "target_equipment_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<EquipmentDependency({self.source_equipment_id!r} "
            f"--{self.relationship_type}--> {self.target_equipment_id!r})>"
        )


# ---------------------------------------------------------------------------
# 7. Chat Sessions
# ---------------------------------------------------------------------------
class ChatSession(Base):
    """A conversation session between a user and the AI assistant."""

    __tablename__ = "chat_sessions"

    id = Column(String(36), primary_key=True, default=_uuid)
    title = Column(String(512), nullable=True, comment="Auto-generated or user-set session title")
    mode = Column(
        String(20),
        nullable=False,
        default="technical",
        comment="Tone mode: 'technical' or 'manager'",
    )
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    # Relationships
    messages = relationship(
        "ChatMessage", back_populates="session", cascade="all, delete-orphan",
        order_by="ChatMessage.created_at",
    )

    def __repr__(self) -> str:
        return f"<ChatSession(id={self.id!r}, title={self.title!r})>"


# ---------------------------------------------------------------------------
# 8. Chat Messages
# ---------------------------------------------------------------------------
class ChatMessage(Base):
    """A single message within a chat session."""

    __tablename__ = "chat_messages"

    id = Column(String(36), primary_key=True, default=_uuid)
    session_id = Column(String(36), ForeignKey("chat_sessions.id"), nullable=False)

    role = Column(
        String(10),
        nullable=False,
        comment="One of: " + ", ".join(CHAT_MESSAGE_ROLE_VALUES),
    )
    content = Column(Text, nullable=False, comment="Message body (markdown supported)")

    # Structured citations attached to ASSISTANT messages (JSON string)
    citations_json = Column(Text, nullable=True, comment="JSON array of citation objects")

    # Optional link to equipment discussed in this message
    equipment_id = Column(String(36), ForeignKey("equipment.id"), nullable=True)

    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    # Relationships
    session = relationship("ChatSession", back_populates="messages")

    __table_args__ = (
        Index("ix_msg_session_id", "session_id"),
        Index("ix_msg_role", "role"),
    )

    def __repr__(self) -> str:
        return (
            f"<ChatMessage(id={self.id!r}, session={self.session_id!r}, "
            f"role={self.role!r})>"
        )
