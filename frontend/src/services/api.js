/**
 * PS8 – API Client Service
 *
 * Centralises all backend HTTP calls.  Base URL defaults to the dev
 * server at http://localhost:8000 and can be overridden via the
 * VITE_API_BASE_URL environment variable.
 */
const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";
/**
 * Upload a file to the backend.
 *
 * @param {File} file  - Browser File object from an input or drag-and-drop.
 * @param {string} docType - Document type tag (e.g. "MANUAL", "SOP").
 * @returns {Promise<object>} Parsed JSON response with document_id, filename, status.
 */
export async function uploadDocument(file, docType = "OTHER") {
    const formData = new FormData();
    formData.append("file", file);
    const url = `${API_BASE}/api/documents/upload?doc_type=${encodeURIComponent(docType)}`;
    const response = await fetch(url, {
        method: "POST",
        body: formData,
    });
    if (!response.ok) {
        const err = await response.json().catch(() => ({ detail: response.statusText }));
        throw new Error(err.detail || "Upload failed");
    }
    return response.json();
}
/**
 * Fetch all documents from the backend.
 *
 * @param {object} params - Optional query params: status, doc_type, limit, offset.
 * @returns {Promise<object>} { total, documents: [...] }
 */
export async function listDocuments(params = {}) {
    const query = new URLSearchParams(params).toString();
    const url = `${API_BASE}/api/documents/list${query ? `?${query}` : ""}`;
    const response = await fetch(url);
    if (!response.ok) {
        throw new Error("Failed to fetch documents");
    }
    return response.json();
}
/**
 * Get a single document by ID.
 *
 * @param {string} documentId
 * @returns {Promise<object>}
 */
export async function getDocument(documentId) {
    const response = await fetch(`${API_BASE}/api/documents/${documentId}`);
    if (!response.ok) {
        throw new Error("Document not found");
    }
    return response.json();
}
/**
 * Delete a document.
 *
 * @param {string} documentId
 * @returns {Promise<object>}
 */
export async function deleteDocument(documentId) {
    const response = await fetch(`${API_BASE}/api/documents/${documentId}`, {
        method: "DELETE",
    });
    if (!response.ok) {
        throw new Error("Failed to delete document");
    }
    return response.json();
}
