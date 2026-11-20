"""
Helper utilities for Anti-Fraud Placement Verification.
"""
import re
import os
from datetime import datetime
from typing import Tuple
import pandas as pd


def normalize_name(name: str) -> str:
    """
    Cleans and normalizes student name for robust matching.
    Removes titles like Mr./Ms., special characters, multiple spaces,
    and converts to lowercase.
    """
    if not isinstance(name, str) or not name.strip():
        return ""
    
    cleaned = name.strip().lower()
    # Remove honorifics
    cleaned = re.sub(r'^(mr\.|ms\.|mrs\.|shri|smt)\s*', '', cleaned)
    # Remove non-alphabet characters (except spaces)
    cleaned = re.sub(r'[^a-z\s]', '', cleaned)
    # Collapse multiple whitespaces
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned


def are_names_matching(name1: str, name2: str) -> Tuple[bool, float, str]:
    """
    Compares two names for identity matching.
    Supports:
    - Exact match
    - Inverted First/Last name (e.g. "Patil Rahul" vs "Rahul Patil")
    - Token set containment
    
    Returns:
        (is_matching: bool, similarity_score: float, reason_detail: str)
    """
    n1 = normalize_name(name1)
    n2 = normalize_name(name2)

    if not n1 or not n2:
        return False, 0.0, "One or both names are empty"

    if n1 == n2:
        return True, 1.0, "Exact match"

    tokens1 = sorted(n1.split())
    tokens2 = sorted(n2.split())

    # Check if sets of tokens match regardless of order (e.g., First Last vs Last First)
    if tokens1 == tokens2:
        return True, 0.98, "Matched with transposed first/last name"

    # Token overlap check (e.g. middle initial missing or expanded)
    set1, set2 = set(tokens1), set(tokens2)
    intersection = set1.intersection(set2)
    union = set1.union(set2)

    jaccard_sim = len(intersection) / len(union) if union else 0.0

    # If all tokens of one name are in the other name (e.g., "Rahul Patil" vs "Rahul Suresh Patil")
    if set1.issubset(set2) or set2.issubset(set1):
        if len(intersection) >= 2:
            return True, 0.90, "Matched with partial middle name variation"

    if jaccard_sim >= 0.70:
        return True, jaccard_sim, f"High token similarity ({int(jaccard_sim * 100)}%)"

    return False, jaccard_sim, f"Name mismatch (Official: '{name1}', Submitted: '{name2}')"


def format_cgpa(val) -> str:
    """Formats CGPA nicely to 2 decimal places."""
    try:
        if val is None or pd.isna(val):
            return "N/A"
        return f"{float(val):.2f}"
    except (ValueError, TypeError):
        return "N/A"


def generate_timestamp() -> str:
    """Returns readable current timestamp."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def ensure_directory(dir_path: str):
    """Ensures directory exists."""
    os.makedirs(dir_path, exist_ok=True)
