"""
Automatic Email Alert and Penalty Notification Engine.
Stage 3 of Anti-Fraud Placement Verification Agent.
"""
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Dict, Any, Tuple, Optional, List
from dotenv import load_dotenv
from utils.helpers import generate_timestamp, ensure_directory
import json


load_dotenv()

DISPATCH_LOG_PATH = "data/email_dispatch_log.json"


def get_smtp_config() -> Dict[str, Any]:
    """Reads SMTP configuration strictly from environment variables."""
    # Reload in case .env was updated
    load_dotenv(override=True)
    return {
        'server': os.getenv('SMTP_SERVER', 'smtp.gmail.com'),
        'port': int(os.getenv('SMTP_PORT', '587')),
        'email': os.getenv('SMTP_EMAIL', ''),
        'password': os.getenv('SMTP_PASSWORD', ''),
        'tpo_email': os.getenv('TPO_EMAIL', 'mmohiteaniket248@gmail.com'),
        'simulation_mode': os.getenv('SMTP_SIMULATION_MODE', 'false').lower() in ['true', '1', 'yes']
    }


def is_smtp_configured() -> Tuple[bool, str]:
    """Validates if mandatory SMTP credentials are provided."""
    config = get_smtp_config()
    if config['simulation_mode']:
        return True, "Simulation mode enabled (Emails will be recorded in dispatch logs without network delivery)."
    
    missing = []
    if not config['server']:
        missing.append('SMTP_SERVER')
    if not config['email']:
        missing.append('SMTP_EMAIL')
    if not config['password']:
        missing.append('SMTP_PASSWORD')
    if not config['tpo_email']:
        missing.append('TPO_EMAIL')

    if missing:
        return False, f"Missing required environment variables: {', '.join(missing)}"
    return True, "SMTP is configured."


def generate_student_warning_content(record: Dict[str, Any]) -> Tuple[str, str]:
    """
    Constructs subject and body for Student Warning Email.
    Required contents:
    - Student name
    - Roll number
    - Detected mismatch
    - Submitted value
    - Official value
    - Verification status
    - Instruction to contact the placement cell
    """
    roll = record.get('Roll Number', 'N/A')
    name = record.get('Submitted Name') or record.get('Official Name', 'Student')
    status = record.get('Status', 'FLAGGED')
    reason = record.get('Reason', 'Data mismatch detected')
    
    sub_cgpa = record.get('Submitted CGPA')
    off_cgpa = record.get('Official CGPA')
    sub_val = f"{sub_cgpa:.2f}" if sub_cgpa is not None else "N/A"
    off_val = f"{off_cgpa:.2f}" if off_cgpa is not None else "Record Not Found"

    subject = f"[CRITICAL] Training & Placement Notice: Discrepancy Detected - Roll No {roll}"

    body = f"""Dear {name},

This is an automated formal notice from the Training and Placement Cell (TPO).

During our automated Anti-Fraud Placement Verification audit, a discrepancy was identified in your submitted placement credentials:

---------------------------------------------------------
VERIFICATION DETAILS:
---------------------------------------------------------
• Student Name:        {name}
• Roll Number:         {roll}
• Verification Status: {status}
• Detected Mismatch:   {reason}
• Submitted Value:     {sub_val}
• Official College:    {off_val}
---------------------------------------------------------

MANDATORY ACTION REQUIRED:
You are required to appear before the Placement Verification Committee within 48 business hours with original university marks cards and identity documentation.

Failure to report or provide clarification may result in referral to the Disciplinary Committee and placement suspension.

Sincerely,
Training & Placement Office (TPO)
College Placement Cell
"""
    return subject, body


def generate_tpo_alert_content(record: Dict[str, Any], tpo_email: str) -> Tuple[str, str]:
    """
    Constructs subject and body for TPO Fraud Alert Email.
    Required contents:
    - Student name
    - Roll number
    - Mismatch type
    - Official value
    - Submitted value
    - Difference
    - Timestamp
    """
    roll = record.get('Roll Number', 'N/A')
    name = record.get('Submitted Name') or record.get('Official Name', 'Unknown')
    reason = record.get('Reason', 'Mismatch detected')
    diff = record.get('Difference')
    diff_val = f"{diff:+.2f}" if diff is not None else "N/A"
    
    sub_cgpa = record.get('Submitted CGPA')
    off_cgpa = record.get('Official CGPA')
    sub_val = f"{sub_cgpa:.2f}" if sub_cgpa is not None else "N/A"
    off_val = f"{off_cgpa:.2f}" if off_cgpa is not None else "Record Not Found"
    timestamp = generate_timestamp()

    subject = f"[FRAUD ALERT] Discrepancy Detected in Placement Record - Roll {roll}"

    body = f"""ATTENTION: Training & Placement Officer / Placement Cell,

The Anti-Fraud Placement Verification Agent has flagged an anomalous submission during verification:

---------------------------------------------------------
FRAUD AUDIT REPORT:
---------------------------------------------------------
• Timestamp:           {timestamp}
• Student Name:        {name}
• Roll Number:         {roll}
• Mismatch Type:       {reason}
• Official Value:      {off_val}
• Submitted Value:     {sub_val}
• Difference:          {diff_val}
---------------------------------------------------------

This student record has been automatically logged into the FLAGGED STUDENTS registry for TPO administrative review.

Anti-Fraud Placement Verification Agent
"""
    return subject, body


def _record_dispatch(
    roll: str,
    recipient_type: str,
    recipient_email: str,
    subject: str,
    status: str,
    details: str
):
    """Logs email delivery attempts to audit file."""
    try:
        ensure_directory("data")
        logs = []
        if os.path.exists(DISPATCH_LOG_PATH):
            with open(DISPATCH_LOG_PATH, 'r', encoding='utf-8') as f:
                logs = json.load(f)

        logs.append({
            'timestamp': generate_timestamp(),
            'roll_number': roll,
            'recipient_type': recipient_type,
            'recipient_email': recipient_email,
            'subject': subject,
            'status': status,
            'details': details
        })

        with open(DISPATCH_LOG_PATH, 'w', encoding='utf-8') as f:
            json.dump(logs, f, indent=2)
    except Exception as e:
        print(f"Failed to log email dispatch: {e}")


def get_dispatch_logs() -> List[Dict[str, Any]]:
    """Retrieves all email dispatch logs."""
    if not os.path.exists(DISPATCH_LOG_PATH):
        return []
    try:
        with open(DISPATCH_LOG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []


def send_email_via_smtp(
    recipient: str, 
    subject: str, 
    body: str, 
    roll_number: str,
    recipient_type: str
) -> Tuple[bool, str]:
    """
    Sends email using Python smtplib with STARTTLS.
    Enforces truthfulness: Does NOT claim success unless SMTP actually succeeds.
    """
    config = get_smtp_config()

    # Simulation mode check
    if config['simulation_mode']:
        msg = f"[SIMULATED SUCCESS] Email prepared for {recipient} ({subject}). Simulation mode is active."
        _record_dispatch(roll_number, recipient_type, recipient, subject, "SIMULATED", msg)
        return True, msg

    # Strict check for credentials
    configured, msg = is_smtp_configured()
    if not configured:
        _record_dispatch(roll_number, recipient_type, recipient, subject, "FAILED", msg)
        return False, f"SMTP failure: {msg}"

    try:
        msg = MIMEMultipart()
        msg['From'] = config['email']
        msg['To'] = recipient
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        with smtplib.SMTP(config['server'], config['port'], timeout=10) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(config['email'], config['password'])
            server.send_message(msg)

        success_msg = f"Email successfully delivered to {recipient} via SMTP {config['server']}."
        _record_dispatch(roll_number, recipient_type, recipient, subject, "DELIVERED", success_msg)
        return True, success_msg

    except Exception as e:
        err_msg = f"SMTP transmission failed for {recipient}: {str(e)}"
        _record_dispatch(roll_number, recipient_type, recipient, subject, "FAILED", err_msg)
        return False, err_msg


def dispatch_alerts_for_flagged_record(
    record: Dict[str, Any],
    student_email: Optional[str] = None
) -> Dict[str, Any]:
    """
    Orchestrates sending both:
    1. Warning email to student (if email available or placeholder)
    2. Fraud alert email to TPO
    
    Rules:
    - Never send emails for VERIFIED records.
    """
    status = record.get('Status', '')
    if status == 'VERIFIED':
        return {
            'success': False,
            'message': 'Cannot send alert: Student is VERIFIED. Alerts only sent for FLAGGED or NOT FOUND records.'
        }

    config = get_smtp_config()
    roll = str(record.get('Roll Number', 'Unknown'))
    tpo_dest = config['tpo_email']
    stud_dest = student_email or f"student_{roll}@college.edu"

    # 1. Student Warning
    stud_subj, stud_body = generate_student_warning_content(record)
    stud_success, stud_msg = send_email_via_smtp(stud_dest, stud_subj, stud_body, roll, "Student")

    # 2. TPO Alert
    tpo_subj, tpo_body = generate_tpo_alert_content(record, tpo_dest)
    tpo_success, tpo_msg = send_email_via_smtp(tpo_dest, tpo_subj, tpo_body, roll, "TPO")

    overall_success = stud_success and tpo_success

    return {
        'success': overall_success,
        'student_dispatch': {'success': stud_success, 'message': stud_msg, 'recipient': stud_dest},
        'tpo_dispatch': {'success': tpo_success, 'message': tpo_msg, 'recipient': tpo_dest}
    }
