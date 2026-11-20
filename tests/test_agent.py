"""
Automated Test Suite for Anti-Fraud Placement Verification Agent.
Validates all 10 required test cases across Stages 1 to 6.
"""
import os
import sys
import unittest
import pandas as pd

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from utils.validators import validate_excel_file
from modules.excel_verification import (
    run_excel_verification,
    STATUS_VERIFIED,
    STATUS_FLAGGED,
    STATUS_NOT_FOUND
)
from modules.ocr_verification import (
    run_ocr_on_file,
    parse_marksheet_text,
    verify_marksheet_against_official
)
from modules.email_alert import (
    send_email_via_smtp,
    dispatch_alerts_for_flagged_record,
    get_smtp_config
)
from modules.fraud_logic import (
    sync_flagged_records_from_verification,
    update_record_status,
    get_all_flagged_records,
    clear_flagged_registry,
    FLAG_STATUS_UNDER_REVIEW,
    FLAG_STATUS_CLEARED
)


class TestAntiFraudPlacementAgent(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.official_path = "data/test/official_college_records_sample.xlsx"
        cls.submitted_path = "data/test/student_submitted_records_sample.xlsx"
        
        # Load official data
        valid_off, msg_off, cls.official_df, _ = validate_excel_file(
            cls.official_path, filename=cls.official_path, is_official=True
        )
        assert valid_off, f"Failed loading official test data: {msg_off}"

        # Load submitted data
        valid_sub, msg_sub, cls.submitted_df, _ = validate_excel_file(
            cls.submitted_path, filename=cls.submitted_path, is_official=False
        )
        assert valid_sub, f"Failed loading submitted test data: {msg_sub}"

        # Run verification engine
        cls.results = run_excel_verification(cls.official_df, cls.submitted_df)
        cls.results_df = cls.results['results_df']

    # TEST CASE 1: Correct student data -> VERIFIED
    def test_case_01_correct_student_data(self):
        row = self.results_df[self.results_df['Roll Number'] == '101'].iloc[0]
        self.assertEqual(row['Status'], STATUS_VERIFIED, "Case 1 failed: Expected VERIFIED for student 101")
        self.assertEqual(row['Submitted Name'], "Rahul Patil")
        self.assertEqual(row['Official CGPA'], 8.25)
        self.assertEqual(row['Submitted CGPA'], 8.25)
        self.assertEqual(row['Difference'], 0.0)

    # TEST CASE 2: Incorrect CGPA -> FLAGGED
    def test_case_02_incorrect_cgpa(self):
        row = self.results_df[self.results_df['Roll Number'] == '102'].iloc[0]
        self.assertEqual(row['Status'], STATUS_FLAGGED, "Case 2 failed: Expected FLAGGED for student 102")
        self.assertIn("CGPA mismatch", row['Reason'])
        self.assertAlmostEqual(row['Difference'], 0.70, places=2)

    # TEST CASE 3: Incorrect name -> FLAGGED
    def test_case_03_incorrect_name(self):
        row = self.results_df[self.results_df['Roll Number'] == '103'].iloc[0]
        self.assertEqual(row['Status'], STATUS_FLAGGED, "Case 3 failed: Expected FLAGGED for student 103")
        self.assertIn("Student Name mismatch", row['Reason'])

    # TEST CASE 4: Incorrect Roll Number / Discrepancy -> FLAGGED
    def test_case_04_incorrect_roll_or_cgpa(self):
        row = self.results_df[self.results_df['Roll Number'] == '104'].iloc[0]
        self.assertEqual(row['Status'], STATUS_FLAGGED, "Case 4 failed: Expected FLAGGED for student 104")

    # TEST CASE 5: Roll Number not found in official college data -> NOT FOUND
    def test_case_05_roll_not_found(self):
        row = self.results_df[self.results_df['Roll Number'] == '999'].iloc[0]
        self.assertEqual(row['Status'], STATUS_NOT_FOUND, "Case 5 failed: Expected NOT FOUND for student 999")
        self.assertIn("does not exist in official", row['Reason'])

    # TEST CASE 6: OCR Correct Marksheet -> VERIFIED
    def test_case_06_ocr_correct_marksheet(self):
        img_path = "data/test/marksheet_case6_correct.png"
        with open(img_path, 'rb') as f:
            file_bytes = f.read()
        raw_text, _, _ = run_ocr_on_file(file_bytes, "marksheet_case6_correct.png")
        parsed = parse_marksheet_text(raw_text)
        outcome = verify_marksheet_against_official(parsed, self.official_df)
        self.assertEqual(outcome['status'], 'VERIFIED', f"Case 6 failed: {outcome['reason']}")
        self.assertEqual(outcome['ocr_roll'], '101')
        self.assertEqual(outcome['ocr_cgpa'], 8.25)

    # TEST CASE 7: OCR Incorrect/Mismatched Marksheet -> FLAGGED
    def test_case_07_ocr_mismatched_marksheet(self):
        img_path = "data/test/marksheet_case7_mismatch.png"
        with open(img_path, 'rb') as f:
            file_bytes = f.read()
        raw_text, _, _ = run_ocr_on_file(file_bytes, "marksheet_case7_mismatch.png")
        parsed = parse_marksheet_text(raw_text)
        outcome = verify_marksheet_against_official(parsed, self.official_df)
        self.assertEqual(outcome['status'], 'FLAGGED', "Case 7 failed: Expected FLAGGED for forged marksheet")
        self.assertIn("CGPA mismatch", outcome['reason'])

    # TEST CASE 8: OCR Unreadable/Damaged Marksheet -> MANUAL REVIEW
    def test_case_08_ocr_unreadable_marksheet(self):
        img_path = "data/test/marksheet_case8_unreadable.png"
        with open(img_path, 'rb') as f:
            file_bytes = f.read()
        raw_text, _, _ = run_ocr_on_file(file_bytes, "marksheet_case8_unreadable.png")
        parsed = parse_marksheet_text(raw_text)
        outcome = verify_marksheet_against_official(parsed, self.official_df)
        self.assertEqual(outcome['status'], 'MANUAL REVIEW', "Case 8 failed: Expected MANUAL REVIEW for unreadable marksheet")

    # TEST CASE 9: Email Success (Simulation / SMTP Delivery)
    def test_case_09_email_success(self):
        flagged_record = {
            'Roll Number': '102',
            'Submitted Name': 'Priya Sharma',
            'Official Name': 'Priya Sharma',
            'Submitted CGPA': 9.80,
            'Official CGPA': 9.10,
            'Difference': 0.70,
            'Status': 'FLAGGED',
            'Reason': 'CGPA mismatch'
        }
        res = dispatch_alerts_for_flagged_record(flagged_record, student_email="priya.sharma@college.edu")
        self.assertTrue(res['success'], "Case 9 failed: Email dispatch should succeed")
        self.assertTrue(res['student_dispatch']['success'])
        self.assertTrue(res['tpo_dispatch']['success'])

    # TEST CASE 10: Email Failure Handling (Verified student must NOT receive fraud alert)
    def test_case_10_email_verified_rejection_and_failure(self):
        verified_record = {
            'Roll Number': '101',
            'Submitted Name': 'Rahul Patil',
            'Official Name': 'Rahul Patil',
            'Submitted CGPA': 8.25,
            'Official CGPA': 8.25,
            'Difference': 0.0,
            'Status': 'VERIFIED',
            'Reason': 'Clean'
        }
        # Rule: Do NOT send emails for VERIFIED records!
        res = dispatch_alerts_for_flagged_record(verified_record)
        self.assertFalse(res['success'], "Case 10 failed: Verified record must NOT have alerts dispatched")
        self.assertIn("VERIFIED", res['message'])


if __name__ == "__main__":
    unittest.main(verbosity=2)
