/**
 * PS8 – FileDropzone Component
 *
 * A drag-and-drop file upload zone with visual feedback, progress indication,
 * and success/error states.  Supports multiple file types (PDF, images, etc.)
 * and sends files to the backend upload endpoint.
 */
import { useState, useRef, useCallback } from "react";
import { uploadDocument } from "../services/api";
import "./FileDropzone.css";
const ACCEPTED_TYPES = [
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/tiff",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
    "text/plain",
];
const ACCEPTED_EXTENSIONS = ".pdf,.png,.jpg,.jpeg,.tiff,.docx,.doc,.txt";
const DOC_TYPE_OPTIONS = [
    { value: "OTHER", label: "Auto-detect" },
    { value: "MANUAL", label: "OEM Manual" },
    { value: "SOP", label: "SOP" },
    { value: "REPORT", label: "Report" },
    { value: "INSPECTION", label: "Inspection Record" },
    { value: "COMPLIANCE", label: "Compliance Doc" },
    { value: "SCHEMATIC", label: "Schematic / P&ID" },
];
export default function FileDropzone() {
    const [isDragOver, setIsDragOver] = useState(false);
    const [uploads, setUploads] = useState([]); // { file, status, result, error }
    const [docType, setDocType] = useState("OTHER");
    const fileInputRef = useRef(null);
    // ---- Drag handlers ----
    const handleDragEnter = useCallback((e) => {
        e.preventDefault();
        e.stopPropagation();
        setIsDragOver(true);
    }, []);
    const handleDragLeave = useCallback((e) => {
        e.preventDefault();
        e.stopPropagation();
        setIsDragOver(false);
    }, []);
    const handleDragOver = useCallback((e) => {
        e.preventDefault();
        e.stopPropagation();
    }, []);
    // ---- Upload a single file ----
    const processFile = useCallback(
        async (file) => {
            const id = `${file.name}-${Date.now()}`;
            const entry = { id, file, status: "uploading", result: null, error: null };
            setUploads((prev) => [...prev, entry]);
            try {
                const result = await uploadDocument(file, docType);
                setUploads((prev) =>
                    prev.map((u) =>
                        u.id === id ? { ...u, status: "success", result } : u
                    )
                );
            } catch (err) {
                setUploads((prev) =>
                    prev.map((u) =>
                        u.id === id
                            ? { ...u, status: "error", error: err.message }
                            : u
                    )
                );
            }
        },
        [docType]
    );
    // ---- Handle file drop ----
    const handleDrop = useCallback(
        (e) => {
            e.preventDefault();
            e.stopPropagation();
            setIsDragOver(false);
            const files = Array.from(e.dataTransfer.files);
            files.forEach(processFile);
        },
        [processFile]
    );
    // ---- Handle file input ----
    const handleFileSelect = useCallback(
        (e) => {
            const files = Array.from(e.target.files);
            files.forEach(processFile);
            // Reset input so the same file can be re-selected
            e.target.value = "";
        },
        [processFile]
    );
    // ---- Clear completed uploads ----
    const clearCompleted = () => {
        setUploads((prev) => prev.filter((u) => u.status === "uploading"));
    };
    const hasCompleted = uploads.some(
        (u) => u.status === "success" || u.status === "error"
    );
    return (
        <div className="dropzone-wrapper">
            {/* Document Type Selector */}
            <div className="dropzone-type-selector">
                <label htmlFor="doc-type-select">Document Type:</label>
                <select
                    id="doc-type-select"
                    value={docType}
                    onChange={(e) => setDocType(e.target.value)}
                >
                    {DOC_TYPE_OPTIONS.map((opt) => (
                        <option key={opt.value} value={opt.value}>
                            {opt.label}
                        </option>
                    ))}
                </select>
            </div>
            {/* Drop Zone */}
            <div
                className={`dropzone ${isDragOver ? "dropzone--active" : ""}`}
                onDragEnter={handleDragEnter}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") fileInputRef.current?.click();
                }}
            >
                <input
                    ref={fileInputRef}
                    type="file"
                    multiple
                    accept={ACCEPTED_EXTENSIONS}
                    onChange={handleFileSelect}
                    className="dropzone-input"
                    id="file-upload-input"
                />
                <div className="dropzone-icon">
                    <svg
                        xmlns="http://www.w3.org/2000/svg"
                        width="48"
                        height="48"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="1.5"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                    >
                        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                        <polyline points="17 8 12 3 7 8" />
                        <line x1="12" y1="3" x2="12" y2="15" />
                    </svg>
                </div>
                <p className="dropzone-title">
                    {isDragOver ? "Drop files here…" : "Drag & drop files or click to browse"}
                </p>
                <p className="dropzone-subtitle">
                    Supports PDF, Word, Images, and Text files
                </p>
            </div>
            {/* Upload Queue */}
            {uploads.length > 0 && (
                <div className="upload-queue">
                    <div className="upload-queue-header">
                        <h3>Uploads</h3>
                        {hasCompleted && (
                            <button className="btn-clear" onClick={clearCompleted}>
                                Clear completed
                            </button>
                        )}
                    </div>
                    <ul className="upload-list">
                        {uploads.map((u) => (
                            <li key={u.id} className={`upload-item upload-item--${u.status}`}>
                                <div className="upload-item-info">
                                    <span className="upload-item-icon">
                                        {u.status === "uploading" && (
                                            <span className="spinner" />
                                        )}
                                        {u.status === "success" && "✓"}
                                        {u.status === "error" && "✗"}
                                    </span>
                                    <span className="upload-item-name">{u.file.name}</span>
                                    <span className="upload-item-size">
                                        {(u.file.size / 1024).toFixed(1)} KB
                                    </span>
                                </div>
                                {u.status === "success" && u.result && (
                                    <div className="upload-item-result">
                                        ID: <code>{u.result.document_id}</code> — Status:{" "}
                                        <span className="badge badge--pending">
                                            {u.result.status}
                                        </span>
                                    </div>
                                )}
                                {u.status === "error" && (
                                    <div className="upload-item-error">{u.error}</div>
                                )}
                            </li>
                        ))}
                    </ul>
                </div>
            )}
        </div>
    );
}
