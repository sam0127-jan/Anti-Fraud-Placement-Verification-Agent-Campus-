"""
Core Database / Excel Verification Engine.
Stage 2 of Anti-Fraud Placement Verification Agent.
"""
from typing import Dict, Any, List, Optional
import pandas as pd
from utils.helpers import are_names_matching, format_cgpa


STATUS_VERIFIED = "VERIFIED"
STATUS_FLAGGED = "FLAGGED"
STATUS_NOT_FOUND = "NOT FOUND"


def run_excel_verification(
    official_df: pd.DataFrame,
    submitted_df: pd.DataFrame
) -> Dict[str, Any]:
    """
    Executes anti-fraud verification by matching submitted student data
    against official college database ground truth.
    
    Ground truth rule:
    - Official college data is NEVER modified.
    - Each submitted record is matched via Roll Number.
    - Comparisons: Official Name vs Submitted Name, Official CGPA vs Submitted CGPA.
    - Status determination:
      * VERIFIED: Roll number found, Name matches, CGPA matches.
      * FLAGGED: Roll number found, but CGPA or Name mismatched.
      * NOT FOUND: Roll number does not exist in official database.
    
    Returns a dictionary containing:
      - 'results_df': pd.DataFrame with columns:
          ['Roll Number', 'Official Name', 'Submitted Name', 'Official CGPA', 
           'Submitted CGPA', 'Difference', 'Status', 'Reason']
      - 'metrics': Dict with counts of total, verified, flagged, not_found.
      - 'flagged_records': List of dicts representing flagged/not_found records for alerts.
    """
    # Create lookup map from official data by normalized Roll Number
    # Note: official_df is treated strictly as read-only ground truth
    official_lookup: Dict[str, Dict[str, Any]] = {}
    for _, row in official_df.iterrows():
        roll_key = str(row['Roll Number']).strip()
        official_lookup[roll_key] = {
            'Roll Number': roll_key,
            'Official Name': str(row['Student Name']).strip(),
            'Official CGPA': float(row['CGPA']) if pd.notna(row['CGPA']) else None
        }

    results: List[Dict[str, Any]] = []

    for _, sub_row in submitted_df.iterrows():
        sub_roll = str(sub_row['Roll Number']).strip()
        sub_name = str(sub_row['Student Name']).strip()
        sub_cgpa_raw = sub_row['CGPA']
        sub_cgpa = float(sub_cgpa_raw) if (pd.notna(sub_cgpa_raw) and sub_cgpa_raw is not None) else None

        # Check if Roll Number exists in official ground truth
        if sub_roll not in official_lookup:
            results.append({
                'Roll Number': sub_roll,
                'Official Name': 'N/A (Not Found)',
                'Submitted Name': sub_name,
                'Official CGPA': None,
                'Submitted CGPA': sub_cgpa,
                'Difference': None,
                'Status': STATUS_NOT_FOUND,
                'Reason': 'Roll Number does not exist in official college database'
            })
            continue

        off_record = official_lookup[sub_roll]
        off_name = off_record['Official Name']
        off_cgpa = off_record['Official CGPA']

        # Check Name Match
        name_matched, sim_score, name_reason = are_names_matching(off_name, sub_name)

        # Check CGPA
        cgpa_matched = False
        cgpa_diff: Optional[float] = None
        cgpa_reason = ""

        if sub_cgpa is None:
            cgpa_matched = False
            cgpa_reason = "Submitted CGPA is missing or invalid"
        elif off_cgpa is None:
            cgpa_matched = False
            cgpa_reason = "Official record CGPA is missing"
        else:
            cgpa_diff = round(sub_cgpa - off_cgpa, 2)
            # Match if difference is practically zero (accounting for float precision)
            if abs(cgpa_diff) < 0.001:
                cgpa_matched = True
            else:
                cgpa_matched = False
                cgpa_reason = f"CGPA mismatch (Official: {off_cgpa:.2f}, Submitted: {sub_cgpa:.2f}, Diff: {cgpa_diff:+.2f})"

        # Determine Final Verification Status & Reason
        if name_matched and cgpa_matched:
            status = STATUS_VERIFIED
            reason = "Record matches official college database"
        elif not name_matched and not cgpa_matched:
            status = STATUS_FLAGGED
            reason = f"Both Name and CGPA mismatch ({name_reason}; {cgpa_reason})"
        elif not cgpa_matched:
            status = STATUS_FLAGGED
            reason = cgpa_reason
        else:
            status = STATUS_FLAGGED
            reason = f"Student Name mismatch (Official: '{off_name}', Submitted: '{sub_name}')"

        results.append({
            'Roll Number': sub_roll,
            'Official Name': off_name,
            'Submitted Name': sub_name,
            'Official CGPA': off_cgpa,
            'Submitted CGPA': sub_cgpa,
            'Difference': cgpa_diff,
            'Status': status,
            'Reason': reason
        })

    results_df = pd.DataFrame(results)

    # Compute Summary Metrics
    total_submitted = len(results_df)
    verified_count = int((results_df['Status'] == STATUS_VERIFIED).sum()) if total_submitted > 0 else 0
    flagged_count = int((results_df['Status'] == STATUS_FLAGGED).sum()) if total_submitted > 0 else 0
    not_found_count = int((results_df['Status'] == STATUS_NOT_FOUND).sum()) if total_submitted > 0 else 0

    flagged_records = results_df[results_df['Status'].isin([STATUS_FLAGGED, STATUS_NOT_FOUND])].to_dict(orient='records')

    return {
        'results_df': results_df,
        'metrics': {
            'total_students': total_submitted,
            'verified': verified_count,
            'flagged': flagged_count,
            'not_found': not_found_count,
            'verification_rate': round((verified_count / total_submitted * 100), 1) if total_submitted > 0 else 0.0
        },
        'flagged_records': flagged_records
    }
