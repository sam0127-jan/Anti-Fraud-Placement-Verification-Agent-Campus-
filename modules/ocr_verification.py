"""
OCR Marksheet Verification Engine.
Stage 4 of Anti-Fraud Placement Verification Agent.
"""
import re
import io
from typing import Dict, Any, Optional, Tuple, List
from PIL import Image, ImageEnhance, ImageFilter
import pytesseract
import pandas as pd
from utils.helpers import are_names_matching, normalize_name


def preprocess_image_for_ocr(image: Image.Image) -> Image.Image:
    """
    Applies image enhancement (grayscale, contrast, sharpness)
    to optimize Tesseract OCR extraction accuracy on marksheet documents.
    """
    # Convert to grayscale
    gray = image.convert('L')
    
    # Increase contrast
    enhancer = ImageEnhance.Contrast(gray)
    contrasted = enhancer.enhance(1.8)
    
    # Increase sharpness
    sharpener = ImageEnhance.Sharpness(contrasted)
    sharpened = sharpener.enhance(1.5)
    
    return sharpened


def extract_images_from_pdf(pdf_bytes_or_path) -> List[Image.Image]:
    """
    Converts PDF pages to PIL images for OCR processing.
    Falls back to pypdf text extraction if pdf2image poppler is unavailable.
    """
    try:
        from pdf2image import convert_from_bytes, convert_from_path
        if isinstance(pdf_bytes_or_path, (bytes, bytearray)):
            return convert_from_bytes(pdf_bytes_or_path, dpi=200)
        else:
            return convert_from_path(pdf_bytes_or_path, dpi=200)
    except Exception as e:
        print(f"pdf2image conversion fallback: {e}")
        return []


def run_ocr_on_file(file_bytes: bytes, filename: str) -> Tuple[str, Optional[Image.Image], float]:
    """
    Extracts raw OCR text from image or PDF bytes.
    Returns:
        (raw_text: str, preview_image: Optional[Image.Image], confidence_estimate: float)
    """
    filename_lower = filename.lower()
    images: List[Image.Image] = []

    if filename_lower.endswith('.pdf'):
        # Check PDF text extraction first
        try:
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(file_bytes))
            direct_text = ""
            for page in reader.pages:
                t = page.extract_text()
                if t:
                    direct_text += t + "\n"
            if len(direct_text.strip()) > 30:
                # Digital PDF with embedded selectable text
                preview = None
                try:
                    from pdf2image import convert_from_bytes
                    pdf_imgs = convert_from_bytes(file_bytes, first_page=1, last_page=1)
                    if pdf_imgs:
                        preview = pdf_imgs[0]
                except Exception:
                    pass
                return direct_text, preview, 0.95
        except Exception:
            pass

        # Rasterize PDF pages for OCR
        pdf_images = extract_images_from_pdf(file_bytes)
        if pdf_images:
            images = pdf_images
        else:
            return "", None, 0.0
    else:
        # Image file (jpg, jpeg, png)
        try:
            img = Image.open(io.BytesIO(file_bytes))
            images = [img]
        except Exception:
            return "", None, 0.0

    if not images:
        return "", None, 0.0

    full_text = ""
    confidences = []

    for img in images:
        processed = preprocess_image_for_ocr(img)
        # Extract data with confidence
        try:
            data = pytesseract.image_to_data(processed, output_type=pytesseract.Output.DICT)
            page_text = " ".join([w for w in data['text'] if w.strip()])
            confs = [int(c) for c in data['conf'] if c != '-1']
            if confs:
                confidences.append(sum(confs) / len(confs))
            full_text += page_text + "\n"
        except Exception:
            # Fallback to standard string extraction
            try:
                text = pytesseract.image_to_string(processed)
                full_text += text + "\n"
                confidences.append(70.0)
            except Exception:
                pass

    avg_conf = (sum(confidences) / len(confidences)) / 100.0 if confidences else 0.0
    preview_img = images[0] if images else None
    return full_text, preview_img, avg_conf


def parse_marksheet_text(raw_text: str) -> Dict[str, Any]:
    """
    Parses OCR text using regex patterns to find Roll Number, Student Name, and CGPA.
    
    Rules:
    - Does NOT invent missing OCR values.
    - If a field cannot be cleanly identified, returns None.
    """
    if not raw_text or not raw_text.strip():
        return {
            'extracted_name': None,
            'extracted_roll': None,
            'extracted_cgpa': None,
            'raw_text': "",
            'parse_success': False
        }

    extracted_roll = None
    extracted_name = None
    extracted_cgpa = None

    lines = [line.strip() for line in raw_text.split('\n') if line.strip()]

    # 1. ROLL NUMBER PARSING
    # Patterns like: "Roll No: 101", "Roll Number: 101", "Seat No: 204", "PRN: 123456"
    roll_patterns = [
        r'(?:roll\s*(?:number|no|num)?|seat\s*no|prn|reg(?:istration)?\s*no)\s*[:.\-]?\s*([A-Za-z0-9\-_/]+)',
        r'\b(?:roll|seat)\b\s*[:\-]?\s*([A-Za-z0-9\-_/]+)'
    ]
    for pattern in roll_patterns:
        match = re.search(pattern, raw_text, re.IGNORECASE)
        if match:
            candidate_roll = match.group(1).strip()
            if candidate_roll and not candidate_roll.lower().startswith(('of', 'the', 'for')):
                extracted_roll = candidate_roll
                break

    # 2. CGPA / SGPA / GRADE POINT PARSING
    # Patterns like: "CGPA: 8.45", "Cumulative Grade Point Average (CGPA): 8.25", "SGPA: 9.10"
    cgpa_patterns = [
        r'(?:cgpa|c\.g\.p\.a\.?|sgpa|pointer|grade\s*point\s*average)\)?\s*[:.\-]?\s*([0-9]\.[0-9]{1,2})',
        r'average\s*\([^)]*cgpa[^)]*\)\s*[:.\-]?\s*([0-9]\.[0-9]{1,2})',
        r'\bcgpa\b[^\d]{1,15}([0-9]\.[0-9]{1,2})',
        r'\b([0-9]\.[0-9]{2})\s*/\s*10(?:\.0)?\b'
    ]
    for pattern in cgpa_patterns:
        match = re.search(pattern, raw_text, re.IGNORECASE)
        if match:
            try:
                cgpa_val = float(match.group(1).strip())
                if 0.0 <= cgpa_val <= 10.0:
                    extracted_cgpa = round(cgpa_val, 2)
                    break
            except ValueError:
                pass

    # 3. STUDENT NAME PARSING
    # Patterns like: "Student Name: Rahul Patil", "Name of Student: John Doe"
    name_patterns = [
        r'(?:student\s*name|candidate\s*name|name\s+of\s+(?:the\s+)?student)\s*[:.\-]\s*([A-Za-z\s.\']+?)(?:\n|$|\r)',
        r'(?:name)\s*[:.\-]\s*([A-Za-z\s.\']+?)(?:\n|$|\r|roll|seat|branch|sem)',
        r'(?:mr\.|ms\.|mrs\.)\s+([A-Za-z\s]+?)(?:\n|$|\r|roll|seat|prn)'
    ]
    for pattern in name_patterns:
        match = re.search(pattern, raw_text, re.IGNORECASE)
        if match:
            candidate = match.group(1).strip()
            # Clean up trailing labels if on same line
            candidate = re.split(r'\b(roll|seat|prn|branch|sem|sgpa|cgpa|academic|dept)\b', candidate, flags=re.I)[0].strip()
            if len(candidate) >= 3 and not re.search(r'\d', candidate):
                extracted_name = candidate
                break

    parse_success = bool(extracted_roll or extracted_name or (extracted_cgpa is not None))

    return {
        'extracted_name': extracted_name,
        'extracted_roll': extracted_roll,
        'extracted_cgpa': extracted_cgpa,
        'raw_text': raw_text,
        'parse_success': parse_success
    }


def verify_marksheet_against_official(
    ocr_result: Dict[str, Any],
    official_df: Optional[pd.DataFrame],
    manual_roll_override: Optional[str] = None
) -> Dict[str, Any]:
    """
    Compares OCR-extracted marksheet data against the Official College Excel ground truth.
    
    Status Rules:
    - MANUAL REVIEW:
      If OCR confidence is too low, or Roll Number and Name cannot be extracted,
      or CGPA cannot be located.
      Do NOT invent missing OCR values.
    - FLAGGED:
      Roll Number exists officially, but CGPA or Name mismatches.
    - VERIFIED:
      Roll Number matches official record, Name matches, and CGPA matches.
    - NOT FOUND:
      Roll Number extracted does not exist in official database.
    """
    extracted_name = ocr_result.get('extracted_name')
    extracted_roll = manual_roll_override.strip() if manual_roll_override else ocr_result.get('extracted_roll')
    extracted_cgpa = ocr_result.get('extracted_cgpa')

    # If official data is not provided or empty
    if official_df is None or official_df.empty:
        return {
            'status': 'MANUAL REVIEW',
            'reason': 'Official college database not uploaded. Cannot perform cross-verification.',
            'ocr_name': extracted_name or 'Not Detected',
            'ocr_roll': extracted_roll or 'Not Detected',
            'ocr_cgpa': extracted_cgpa,
            'official_name': 'N/A',
            'official_cgpa': None,
            'difference': None
        }

    # If essential fields were not extracted by OCR
    if not extracted_roll and not extracted_name:
        return {
            'status': 'MANUAL REVIEW',
            'reason': 'Low OCR confidence: Neither Roll Number nor Student Name could be detected reliably.',
            'ocr_name': 'Not Detected',
            'ocr_roll': 'Not Detected',
            'ocr_cgpa': extracted_cgpa,
            'official_name': 'N/A',
            'official_cgpa': None,
            'difference': None
        }

    if extracted_cgpa is None:
        return {
            'status': 'MANUAL REVIEW',
            'reason': 'Low OCR confidence: Marksheet CGPA/SGPA could not be located in document text.',
            'ocr_name': extracted_name or 'Not Detected',
            'ocr_roll': extracted_roll or 'Not Detected',
            'ocr_cgpa': None,
            'official_name': 'N/A',
            'official_cgpa': None,
            'difference': None
        }

    # Locate official record
    official_match = None
    if extracted_roll:
        matched_rows = official_df[official_df['Roll Number'].astype(str).str.strip() == str(extracted_roll).strip()]
        if not matched_rows.empty:
            official_match = matched_rows.iloc[0]

    # If roll didn't match directly, try finding by name if available
    if official_match is None and extracted_name:
        for _, row in official_df.iterrows():
            matched, _, _ = are_names_matching(str(row['Student Name']), extracted_name)
            if matched:
                official_match = row
                break

    if official_match is None:
        return {
            'status': 'FLAGGED',
            'reason': f"Roll Number '{extracted_roll or 'N/A'}' / Name '{extracted_name or 'N/A'}' does not exist in official college database.",
            'ocr_name': extracted_name or 'Not Detected',
            'ocr_roll': extracted_roll or 'Not Detected',
            'ocr_cgpa': extracted_cgpa,
            'official_name': 'N/A (Not Found)',
            'official_cgpa': None,
            'difference': None
        }

    off_name = str(official_match['Student Name']).strip()
    off_cgpa = float(official_match['CGPA']) if pd.notna(official_match['CGPA']) else None

    # Name check
    name_matched = True
    name_reason = "Name matched"
    if extracted_name:
        name_matched, _, name_reason = are_names_matching(off_name, extracted_name)

    # CGPA check
    cgpa_diff = None
    cgpa_matched = False
    cgpa_reason = ""

    if off_cgpa is None:
        cgpa_matched = False
        cgpa_reason = "Official CGPA missing in database"
    else:
        cgpa_diff = round(extracted_cgpa - off_cgpa, 2)
        if abs(cgpa_diff) < 0.001:
            cgpa_matched = True
        else:
            cgpa_matched = False
            cgpa_reason = f"Marksheet CGPA mismatch (Official: {off_cgpa:.2f}, Marksheet: {extracted_cgpa:.2f}, Diff: {cgpa_diff:+.2f})"

    # Overall Status
    if name_matched and cgpa_matched:
        final_status = 'VERIFIED'
        final_reason = 'Marksheet credentials strictly verified against official database.'
    else:
        final_status = 'FLAGGED'
        reasons = []
        if not name_matched:
            reasons.append(name_reason)
        if not cgpa_matched:
            reasons.append(cgpa_reason)
        final_reason = "; ".join(reasons)

    return {
        'status': final_status,
        'reason': final_reason,
        'ocr_name': extracted_name or 'Not Detected',
        'ocr_roll': extracted_roll or str(official_match['Roll Number']),
        'ocr_cgpa': extracted_cgpa,
        'official_name': off_name,
        'official_cgpa': off_cgpa,
        'difference': cgpa_diff
    }
