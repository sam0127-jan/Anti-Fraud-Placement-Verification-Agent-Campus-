"""
Fraud Detection, Flagging and TPO Penalty/Blacklist Governance Logic.
Anti-Fraud Placement Verification Agent.
"""
import os
import json
from datetime import datetime
from typing import List, Dict, Any, Optional
import pandas as pd
from utils.helpers import generate_timestamp, ensure_directory


FLAG_STATUS_FLAGGED = "FLAGGED"
FLAG_STATUS_UNDER_REVIEW = "UNDER REVIEW"
FLAG_STATUS_CLEARED = "CLEARED"

STORAGE_PATH = "data/flagged_students.json"


def _load_storage() -> List[Dict[str, Any]]:
    """Loads existing flagged students registry."""
    if not os.path.exists(STORAGE_PATH):
        return []
    try:
        with open(STORAGE_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []


def _save_storage(records: List[Dict[str, Any]]) -> bool:
    """Saves flagged students registry securely."""
    try:
        ensure_directory("data")
        with open(STORAGE_PATH, 'w', encoding='utf-8') as f:
            json.dump(records, f, indent=2, default=str)
        return True
    except Exception as e:
        print(f"Error saving flagged students registry: {e}")
        return False


def get_all_flagged_records() -> List[Dict[str, Any]]:
    """Returns the list of all flagged student records."""
    return _load_storage()


def get_flagged_dataframe() -> pd.DataFrame:
    """Returns the flagged student records as a Pandas DataFrame for UI display."""
    records = get_all_flagged_records()
    if not records:
        return pd.DataFrame(columns=[
            'Roll Number', 'Name', 'Reason', 'Difference', 'Date', 'Status', 'TPO Remarks'
        ])
    return pd.DataFrame(records)


def sync_flagged_records_from_verification(new_mismatches: List[Dict[str, Any]]) -> int:
    """
    Ingests flagged or not-found records from a verification run.
    Important:
    - Never overwrites an existing TPO review decision (e.g. 'CLEARED' or 'UNDER REVIEW').
    - If a record already exists, updates the reason/timestamp if still in FLAGGED state,
      or preserves TPO manual governance state.
    - Prevents duplicates.
    
    Returns count of newly added records.
    """
    existing_records = _load_storage()
    existing_map = {r['Roll Number']: r for r in existing_records}
    added_count = 0

    for item in new_mismatches:
        roll = str(item.get('Roll Number', '')).strip()
        if not roll:
            continue

        name = item.get('Submitted Name') or item.get('Official Name') or 'Unknown'
        reason = item.get('Reason', 'Mismatch detected')
        diff = item.get('Difference')
        diff_str = f"{diff:+.2f}" if (diff is not None and isinstance(diff, (int, float))) else "N/A"

        if roll in existing_map:
            # Preserve existing TPO manual status; only update reason if still FLAGGED
            curr_record = existing_map[roll]
            if curr_record.get('Status') == FLAG_STATUS_FLAGGED:
                curr_record['Reason'] = reason
                curr_record['Difference'] = diff_str
                curr_record['Date'] = generate_timestamp()
        else:
            new_record = {
                'Roll Number': roll,
                'Name': name,
                'Reason': reason,
                'Difference': diff_str,
                'Date': generate_timestamp(),
                'Status': FLAG_STATUS_FLAGGED,
                'TPO Remarks': 'System Flagged upon verification'
            }
            existing_records.append(new_record)
            existing_map[roll] = new_record
            added_count += 1

    _save_storage(existing_records)
    return added_count


def update_record_status(
    roll_number: str, 
    new_status: str, 
    remarks: Optional[str] = None
) -> bool:
    """
    Allows TPO / Placement Officers to update student governance status.
    Available statuses:
    - FLAGGED
    - UNDER REVIEW
    - CLEARED
    
    No automatic irreversible decisions are made.
    """
    allowed_statuses = [FLAG_STATUS_FLAGGED, FLAG_STATUS_UNDER_REVIEW, FLAG_STATUS_CLEARED]
    if new_status not in allowed_statuses:
        raise ValueError(f"Status must be one of {allowed_statuses}")

    records = _load_storage()
    updated = False
    for rec in records:
        if rec['Roll Number'] == str(roll_number).strip():
            rec['Status'] = new_status
            if remarks:
                rec['TPO Remarks'] = remarks.strip()
            rec['Last Updated'] = generate_timestamp()
            updated = True
            break

    if updated:
        _save_storage(records)
    return updated


def clear_flagged_registry() -> bool:
    """Clears the flagged registry (used for tests or fresh reset)."""
    return _save_storage([])
