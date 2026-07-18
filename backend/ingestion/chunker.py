from typing import List, Dict, Any

def chunk_text(pages_content: List[Dict[str, Any]], chunk_size: int = 1000, overlap: int = 200) -> List[Dict[str, Any]]:
    """
    Split extracted text into semantic paragraphs/chunks.
    Chunks retain page number, header title (mocked), and metadata.
    """
    chunks = []
    
    for page in pages_content:
        page_num = page.get("page", 1)
        text = page.get("text", "")
        
        # Split by double newline to approximate paragraphs
        paragraphs = text.split("\n\n")
        
        current_chunk_text = ""
        
        for p in paragraphs:
            if not p.strip():
                continue
                
            if len(current_chunk_text) + len(p) > chunk_size and current_chunk_text:
                chunks.append({
                    "page": page_num,
                    "text": current_chunk_text.strip(),
                    "section_title": "General" 
                })
                # Simple overlap logic - taking last `overlap` characters roughly
                current_chunk_text = current_chunk_text[-overlap:] + "\n\n" + p
            else:
                if current_chunk_text:
                    current_chunk_text += "\n\n" + p
                else:
                    current_chunk_text = p
                    
        if current_chunk_text.strip():
            chunks.append({
                "page": page_num,
                "text": current_chunk_text.strip(),
                "section_title": "General"
            })
            
    return chunks
