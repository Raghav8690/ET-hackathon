import re
from typing import Dict, Any

def extract_metadata(text: str) -> Dict[str, Any]:
    """
    Regex and simple logic based matching to extract Equipment ID, Serial Numbers, Document Type, etc.
    
    Example expected text: "Pump Model P-101 Serial Number SN-883921"
    Expected output: {"equipment_id": "P-101", "serial_number": "SN-883921", "doc_type": "manual"}
    """
    metadata = {}
    
    # Regexes to extract equipment ID and serial number
    equip_match = re.search(r'(?:Equipment ID|Model)\s*[:\-]?\s*([A-Z0-9\-]+)', text, re.IGNORECASE)
    if equip_match:
        metadata['equipment_id'] = equip_match.group(1)
        
    sn_match = re.search(r'Serial Number\s*[:\-]?\s*([A-Z0-9\-]+)', text, re.IGNORECASE)
    if sn_match:
        metadata['serial_number'] = sn_match.group(1)
        
    # Naive document type extraction based on keywords
    text_lower = text.lower()
    if 'manual' in text_lower or 'specification' in text_lower:
        metadata['doc_type'] = 'manual'
    elif 'report' in text_lower or 'failure' in text_lower or 'log' in text_lower:
        metadata['doc_type'] = 'report'
    elif 'sop' in text_lower or 'procedure' in text_lower:
        metadata['doc_type'] = 'sop'
    else:
        metadata['doc_type'] = 'other'
        
    return metadata
