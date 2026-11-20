"""
Validators for Excel files and data integrity checks.
"""
from typing import Tuple, Dict, Any, Optional
import os
import pandas as pd


# Column name aliases for flexibility while maintaining strict canonical names
ROLL_NO_ALIASES = [
    'roll number', 'roll no', 'roll_no', 'rollno', 'roll_number', 
    'prn', 'registration no', 'reg no', 'seat no', 'student id'
]

NAME_ALIASES = [
    'student name', 'name', 'student_name', 'full name', 'candidate name'
]

CGPA_ALIASES = [
    'cgpa', 'c.g.p.a', 'c.g.p.a.', 'pointer', 'sgpa', 'gpa'
]


def _find_matching_column(columns: list, aliases: list) -> Optional[str]:
    """Finds the actual column name that matches one of the aliases (case-insensitive)."""
    for col in columns:
        cleaned_col = str(col).strip().lower().replace('.', '').replace('_', ' ')
        for alias in aliases:
            cleaned_alias = alias.lower().replace('.', '').replace('_', ' ')
            if cleaned_col == cleaned_alias:
                return col
    return None


def validate_excel_file(
    file_path_or_buffer: Any,
    filename: str = "",
    is_official: bool = False
) -> Tuple[bool, str, Optional[pd.DataFrame], Dict[str, Any]]:
    """
    Validates an Excel file for Anti-Fraud placement verification.
    
    Checks:
    - Supported extension (.xlsx, .xls)
    - File readability
    - Empty file check
    - Required columns existence: Roll Number, Student Name, CGPA
    - CGPA value validation (range 0.0 - 10.0)
    - Duplicate Roll Number detection
    
    Returns:
        (is_valid: bool, error_message: str, standardized_df: Optional[pd.DataFrame], metadata: Dict)
    """
    metadata: Dict[str, Any] = {
        'total_rows': 0,
        'valid_rows': 0,
        'duplicates': [],
        'invalid_cgpa_rows': [],
        'missing_values_count': 0
    }

    # 1. Extension check
    if filename:
        ext = os.path.splitext(filename)[1].lower()
        if ext not in ['.xlsx', '.xls']:
            return False, f"Unsupported file type '{ext}'. Please upload an Excel file (.xlsx or .xls).", None, metadata

    # 2. Read with pandas
    try:
        df = pd.read_excel(file_path_or_buffer)
    except Exception as e:
        return False, f"Failed to read Excel file: {str(e)}", None, metadata

    # 3. Empty check
    if df.empty or len(df.columns) == 0:
        return False, "Uploaded Excel file is completely empty.", None, metadata

    # 4. Column validation and normalization
    columns = list(df.columns)
    roll_col = _find_matching_column(columns, ROLL_NO_ALIASES)
    name_col = _find_matching_column(columns, NAME_ALIASES)
    cgpa_col = _find_matching_column(columns, CGPA_ALIASES)

    missing_cols = []
    if not roll_col:
        missing_cols.append("Roll Number")
    if not name_col:
        missing_cols.append("Student Name")
    if not cgpa_col:
        missing_cols.append("CGPA")

    if missing_cols:
        dataset_type = "Official" if is_official else "Student"
        return (
            False,
            f"Missing required column(s) in {dataset_type} Excel: {', '.join(missing_cols)}. "
            f"Expected columns: 'Roll Number', 'Student Name', 'CGPA'. Found: {list(df.columns)}",
            None,
            metadata
        )

    # Standardize column names to canonical format
    standardized_df = pd.DataFrame()
    standardized_df['Roll Number'] = df[roll_col].astype(str).str.strip()
    standardized_df['Student Name'] = df[name_col].astype(str).str.strip()
    
    # Clean up string artifacts (like 'nan', empty strings)
    standardized_df = standardized_df[
        (standardized_df['Roll Number'].str.lower() != 'nan') &
        (standardized_df['Roll Number'] != '')
    ].copy()

    if standardized_df.empty:
        return False, "File contains no valid student rows with Roll Numbers.", None, metadata

    # Convert CGPA safely
    raw_cgpa = df[cgpa_col].iloc[standardized_df.index]
    parsed_cgpa = []
    invalid_cgpa_indices = []

    for idx, val in raw_cgpa.items():
        try:
            if pd.isna(val) or str(val).strip() == '':
                raise ValueError("Empty CGPA")
            num = float(str(val).strip())
            if num < 0.0 or num > 10.0:
                invalid_cgpa_indices.append(idx)
                parsed_cgpa.append(None)
            else:
                parsed_cgpa.append(round(num, 2))
        except (ValueError, TypeError):
            invalid_cgpa_indices.append(idx)
            parsed_cgpa.append(None)

    standardized_df['CGPA'] = parsed_cgpa

    # Record invalid CGPA rows
    if invalid_cgpa_indices:
        metadata['invalid_cgpa_rows'] = invalid_cgpa_indices

    # Check duplicates
    duplicate_rolls = standardized_df[standardized_df.duplicated(subset=['Roll Number'], keep=False)]['Roll Number'].unique().tolist()
    if duplicate_rolls:
        metadata['duplicates'] = duplicate_rolls
        if is_official:
            # In official data, duplicate roll numbers compromise ground truth integrity
            return (
                False,
                f"Data integrity error: Official database contains duplicate Roll Numbers: {', '.join(duplicate_rolls[:5])}. "
                "Official records must have unique Roll Numbers.",
                None,
                metadata
            )

    metadata['total_rows'] = len(standardized_df)
    metadata['valid_rows'] = len(standardized_df.dropna(subset=['CGPA']))
    metadata['missing_values_count'] = len(invalid_cgpa_indices)

    return True, "Valid Excel file.", standardized_df, metadata
