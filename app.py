"""
Anti-Fraud Placement Verification Agent
Streamlit Web Dashboard for Training & Placement Cell (TPO)
"""
import io
import os
import pandas as pd
import streamlit as st
from PIL import Image

# Import our modular engines
from utils.validators import validate_excel_file
from utils.helpers import format_cgpa, generate_timestamp
from modules.excel_verification import (
    run_excel_verification,
    STATUS_VERIFIED,
    STATUS_FLAGGED,
    STATUS_NOT_FOUND
)
from modules.fraud_logic import (
    get_all_flagged_records,
    get_flagged_dataframe,
    sync_flagged_records_from_verification,
    update_record_status,
    FLAG_STATUS_FLAGGED,
    FLAG_STATUS_UNDER_REVIEW,
    FLAG_STATUS_CLEARED
)
from modules.email_alert import (
    get_smtp_config,
    is_smtp_configured,
    dispatch_alerts_for_flagged_record,
    get_dispatch_logs
)
from modules.ocr_verification import (
    run_ocr_on_file,
    parse_marksheet_text,
    verify_marksheet_against_official
)

# Page configuration
st.set_page_config(
    page_title="Anti-Fraud Placement Verification Agent",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling for clean, professional TPO dashboard
st.markdown("""
<style>
    .main-header {
        font-size: 1.8rem;
        font-weight: 700;
        color: #1e293b;
        margin-bottom: 0.25rem;
    }
    .sub-header {
        font-size: 0.95rem;
        color: #64748b;
        margin-bottom: 1.5rem;
    }
    .badge-verified {
        background-color: #dcfce7;
        color: #15803d;
        padding: 4px 10px;
        border-radius: 4px;
        font-weight: 600;
        font-size: 0.85rem;
    }
    .badge-flagged {
        background-color: #fee2e2;
        color: #b91c1c;
        padding: 4px 10px;
        border-radius: 4px;
        font-weight: 600;
        font-size: 0.85rem;
    }
    .badge-notfound {
        background-color: #ffedd5;
        color: #c2410c;
        padding: 4px 10px;
        border-radius: 4px;
        font-weight: 600;
        font-size: 0.85rem;
    }
    .badge-review {
        background-color: #f3e8ff;
        color: #7e22ce;
        padding: 4px 10px;
        border-radius: 4px;
        font-weight: 600;
        font-size: 0.85rem;
    }
</style>
""", unsafe_allow_html=True)

# Initialize Session State
if 'official_df' not in st.session_state:
    st.session_state['official_df'] = None
if 'official_metadata' not in st.session_state:
    st.session_state['official_metadata'] = None
if 'official_filename' not in st.session_state:
    st.session_state['official_filename'] = None

if 'submitted_df' not in st.session_state:
    st.session_state['submitted_df'] = None
if 'submitted_metadata' not in st.session_state:
    st.session_state['submitted_metadata'] = None
if 'submitted_filename' not in st.session_state:
    st.session_state['submitted_filename'] = None

if 'verification_results' not in st.session_state:
    st.session_state['verification_results'] = None

if 'ocr_history' not in st.session_state:
    st.session_state['ocr_history'] = []

# Sidebar Navigation
with st.sidebar:
    st.markdown("### 🛡️ Placement Verification")
    st.markdown("**Role:** Training & Placement Officer (TPO)")
    st.markdown("---")
    
    menu = st.radio(
        "Navigation",
        [
            "1. 📊 Dashboard",
            "2. 📤 Upload Official Data",
            "3. 📥 Upload Student Data",
            "4. 🔍 Verify Data",
            "5. 📄 Marksheet OCR Verification",
            "6. 📋 Verification Results",
            "7. 🚩 Flagged Students",
            "8. ✉️ Email Status"
        ],
        index=0
    )
    
    st.markdown("---")
    # Quick Status Indicators
    st.markdown("##### 📁 Loaded Datasets")
    if st.session_state['official_df'] is not None:
        st.success(f"Official: {len(st.session_state['official_df'])} records loaded")
    else:
        st.caption("Official Data: Not Loaded")

    if st.session_state['submitted_df'] is not None:
        st.info(f"Student: {len(st.session_state['submitted_df'])} submissions")
    else:
        st.caption("Student Data: Not Loaded")

    if st.session_state['verification_results'] is not None:
        st.caption("Verification State: Processed")


# =========================================================================
# SECTION 1: DASHBOARD
# =========================================================================
if menu == "1. 📊 Dashboard":
    st.markdown('<div class="main-header">Anti-Fraud Placement Verification Agent</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">TPO Operations &amp; Integrity Oversight Center</div>', unsafe_allow_html=True)

    results_data = st.session_state['verification_results']
    flagged_records = get_all_flagged_records()

    if results_data is None:
        st.info("ℹ️ **No data available.** Please proceed to **Upload Official Data** and **Upload Student Data** to initiate verification.")
        
        # Guide cards
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown("### 1. Upload Data")
            st.write("Upload official college records as the single source of truth, then upload candidate-submitted placement sheets.")
        with c2:
            st.markdown("### 2. Automated Cross-Check")
            st.write("The agent matches roll numbers, audits names, and flags CGPA discrepancies or unrecorded entries.")
        with c3:
            st.markdown("### 3. OCR & Governance")
            st.write("Verify marksheets using OCR, review flagged candidates, and dispatch automated warning and TPO alert emails.")
    else:
        metrics = results_data['metrics']
        
        # Real statistics
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Total Submitted", metrics['total_students'])
        m2.metric("Verified (Clean)", metrics['verified'])
        m3.metric("Flagged (Mismatch)", metrics['flagged'], delta=f"-{metrics['flagged']}" if metrics['flagged'] > 0 else "0", delta_color="inverse")
        m4.metric("Not Found", metrics['not_found'], delta=f"-{metrics['not_found']}" if metrics['not_found'] > 0 else "0", delta_color="inverse")
        
        # Count manual reviews from OCR
        manual_ocr_count = sum(1 for item in st.session_state['ocr_history'] if item.get('status') == 'MANUAL REVIEW')
        m5.metric("Manual Review (OCR)", manual_ocr_count)

        st.markdown("---")

        col_chart, col_flagged = st.columns([1, 1])

        with col_chart:
            st.subheader("Verification Breakdown")
            chart_df = pd.DataFrame({
                "Status": ["VERIFIED", "FLAGGED", "NOT FOUND"],
                "Count": [metrics['verified'], metrics['flagged'], metrics['not_found']]
            })
            st.bar_chart(chart_df.set_index("Status"), color="#3b82f6")

        with col_flagged:
            st.subheader("TPO Flagged Registry Summary")
            st.write(f"Total Registry Entries: **{len(flagged_records)}**")
            
            under_review = sum(1 for r in flagged_records if r.get('Status') == FLAG_STATUS_UNDER_REVIEW)
            cleared = sum(1 for r in flagged_records if r.get('Status') == FLAG_STATUS_CLEARED)
            flagged = sum(1 for r in flagged_records if r.get('Status') == FLAG_STATUS_FLAGGED)
            
            summary_df = pd.DataFrame([
                {"Category": "Active FLAGGED", "Count": flagged},
                {"Category": "UNDER REVIEW (TPO)", "Count": under_review},
                {"Category": "CLEARED (Legitimate)", "Count": cleared}
            ])
            st.dataframe(summary_df, use_container_width=True, hide_index=True)


# =========================================================================
# SECTION 2: UPLOAD OFFICIAL DATA
# =========================================================================
elif menu == "2. 📤 Upload Official Data":
    st.markdown('<div class="main-header">Official College Student Data</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Upload ground truth registrar/examination records (Source of Truth)</div>', unsafe_allow_html=True)

    st.markdown("""
    **File Requirements:**
    - Format: `.xlsx` or `.xls`
    - Required Columns: **Roll Number**, **Student Name**, **CGPA**
    - Note: This dataset is strictly read-only and will never be modified.
    """)

    uploaded_file = st.file_uploader("Select Official College Records Excel File", type=["xlsx", "xls"], key="off_uploader")

    if uploaded_file is not None:
        is_valid, msg, standardized_df, meta = validate_excel_file(
            uploaded_file, 
            filename=uploaded_file.name, 
            is_official=True
        )

        if not is_valid:
            st.error(f"❌ Validation Failed: {msg}")
        else:
            st.session_state['official_df'] = standardized_df
            st.session_state['official_metadata'] = meta
            st.session_state['official_filename'] = uploaded_file.name
            st.success(f"✅ Official Data successfully verified and loaded: **{len(standardized_df)}** valid student records.")

    if st.session_state['official_df'] is not None:
        st.markdown(f"#### Active Official Records ({st.session_state['official_filename']})")
        st.dataframe(st.session_state['official_df'].head(50), use_container_width=True)
        if st.button("Clear Loaded Official Data"):
            st.session_state['official_df'] = None
            st.session_state['official_metadata'] = None
            st.session_state['official_filename'] = None
            st.session_state['verification_results'] = None
            st.rerun()


# =========================================================================
# SECTION 3: UPLOAD STUDENT DATA
# =========================================================================
elif menu == "3. 📥 Upload Student Data":
    st.markdown('<div class="main-header">Student Submitted Placement Data</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Upload student-submitted placement registration Excel sheet to audit</div>', unsafe_allow_html=True)

    st.markdown("""
    **File Requirements:**
    - Format: `.xlsx` or `.xls`
    - Required Columns: **Roll Number**, **Student Name**, **CGPA**
    """)

    uploaded_sub = st.file_uploader("Select Student Submitted Excel File", type=["xlsx", "xls"], key="sub_uploader")

    if uploaded_sub is not None:
        is_valid, msg, standardized_df, meta = validate_excel_file(
            uploaded_sub,
            filename=uploaded_sub.name,
            is_official=False
        )

        if not is_valid:
            st.error(f"❌ Validation Failed: {msg}")
        else:
            st.session_state['submitted_df'] = standardized_df
            st.session_state['submitted_metadata'] = meta
            st.session_state['submitted_filename'] = uploaded_sub.name
            st.success(f"✅ Student Submissions loaded: **{len(standardized_df)}** student rows ready for verification.")

    if st.session_state['submitted_df'] is not None:
        st.markdown(f"#### Active Student Submissions ({st.session_state['submitted_filename']})")
        st.dataframe(st.session_state['submitted_df'].head(50), use_container_width=True)
        if st.button("Clear Loaded Student Submissions"):
            st.session_state['submitted_df'] = None
            st.session_state['submitted_metadata'] = None
            st.session_state['submitted_filename'] = None
            st.session_state['verification_results'] = None
            st.rerun()


# =========================================================================
# SECTION 4: VERIFY DATA
# =========================================================================
elif menu == "4. 🔍 Verify Data":
    st.markdown('<div class="main-header">Execute Placement Verification</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Cross-examine student submissions against official ground truth</div>', unsafe_allow_html=True)

    off_df = st.session_state.get('official_df')
    sub_df = st.session_state.get('submitted_df')

    col1, col2 = st.columns(2)
    with col1:
        if off_df is not None:
            st.success(f"Official Data: {len(off_df)} student records")
        else:
            st.warning("⚠️ Official Data not loaded. Please upload in Section 2.")
    with col2:
        if sub_df is not None:
            st.success(f"Student Data: {len(sub_df)} submissions")
        else:
            st.warning("⚠️ Student Data not loaded. Please upload in Section 3.")

    if off_df is not None and sub_df is not None:
        if st.button("🚀 Run Anti-Fraud Verification Engine", type="primary"):
            with st.spinner("Analyzing candidate submissions and calculating variances..."):
                results = run_excel_verification(off_df, sub_df)
                st.session_state['verification_results'] = results
                
                # Automatically sync newly flagged records into TPO Flagged Students registry
                new_flagged = results['flagged_records']
                added = sync_flagged_records_from_verification(new_flagged)
                
                st.success(f"Verification complete! {results['metrics']['verified']} verified, {results['metrics']['flagged']} flagged, {results['metrics']['not_found']} not found.")
                if added > 0:
                    st.info(f"📋 {added} newly detected non-compliant record(s) logged to the TPO Flagged Registry.")

    if st.session_state['verification_results'] is not None:
        res = st.session_state['verification_results']
        df_res = res['results_df']
        
        st.markdown("---")
        st.subheader("Verification Run Summary")
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Audited Submissions", res['metrics']['total_students'])
        c2.metric("VERIFIED", res['metrics']['verified'])
        c3.metric("FLAGGED", res['metrics']['flagged'])
        c4.metric("NOT FOUND", res['metrics']['not_found'])

        st.markdown("#### Detailed Verification Output")
        
        # Status Filter
        filter_status = st.multiselect(
            "Filter by Verification Status",
            options=[STATUS_VERIFIED, STATUS_FLAGGED, STATUS_NOT_FOUND],
            default=[STATUS_FLAGGED, STATUS_NOT_FOUND, STATUS_VERIFIED]
        )
        
        filtered_df = df_res[df_res['Status'].isin(filter_status)]
        st.dataframe(filtered_df, use_container_width=True, hide_index=True)


# =========================================================================
# SECTION 5: MARKSHEET OCR VERIFICATION
# =========================================================================
elif menu == "5. 📄 Marksheet OCR Verification":
    st.markdown('<div class="main-header">OCR Marksheet Verification</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Optical Character Recognition extraction &amp; cross-validation against official records</div>', unsafe_allow_html=True)

    off_df = st.session_state.get('official_df')
    if off_df is None:
        st.warning("⚠️ Official College Data is not loaded. Cross-verification will mark results for manual check.")

    st.markdown("""
    **Accepted formats:** `.jpg`, `.jpeg`, `.png`, `.pdf`
    The agent extracts **Roll Number**, **Student Name**, and **CGPA/SGPA** and validates them directly against official records.
    """)

    uploaded_doc = st.file_uploader(
        "Upload Student Marksheet Document",
        type=["jpg", "jpeg", "png", "pdf"],
        key="marksheet_uploader"
    )

    manual_roll = st.text_input("Optional: Manual Roll Number Override (if document image is partially obscured)", "")

    if uploaded_doc is not None:
        col_img, col_ocr = st.columns([1, 1])

        with st.spinner("Extracting text and scanning marksheet with OCR..."):
            file_bytes = uploaded_doc.read()
            raw_text, preview_img, conf = run_ocr_on_file(file_bytes, uploaded_doc.name)
            parsed = parse_marksheet_text(raw_text)

        with col_img:
            st.markdown("#### Document Preview")
            if preview_img is not None:
                st.image(preview_img, caption=uploaded_doc.name, use_container_width=True)
            else:
                st.info("No visual preview available (Digital PDF or plain text).")

        with col_ocr:
            st.markdown("#### OCR Extraction &amp; Cross-Check")
            
            # Cross-verify against official records
            verification_outcome = verify_marksheet_against_official(
                parsed, 
                off_df, 
                manual_roll_override=manual_roll if manual_roll else None
            )

            status = verification_outcome['status']
            if status == 'VERIFIED':
                st.markdown(f'<span class="badge-verified">STATUS: {status}</span>', unsafe_allow_html=True)
            elif status == 'FLAGGED':
                st.markdown(f'<span class="badge-flagged">STATUS: {status}</span>', unsafe_allow_html=True)
            else:
                st.markdown(f'<span class="badge-review">STATUS: {status}</span>', unsafe_allow_html=True)

            st.write(f"**Reason / Details:** {verification_outcome['reason']}")
            
            # Metrics comparison card
            comp_df = pd.DataFrame([
                {"Attribute": "Roll Number", "OCR Extracted": str(verification_outcome['ocr_roll']), "Official Record": str(verification_outcome['ocr_roll']) if status != 'FLAGGED' else "N/A"},
                {"Attribute": "Student Name", "OCR Extracted": str(verification_outcome['ocr_name']), "Official Record": str(verification_outcome['official_name'])},
                {"Attribute": "CGPA", "OCR Extracted": format_cgpa(verification_outcome['ocr_cgpa']), "Official Record": format_cgpa(verification_outcome['official_cgpa'])},
                {"Attribute": "Difference", "OCR Extracted": "-", "Official Record": f"{verification_outcome['difference']:+.2f}" if verification_outcome['difference'] is not None else "N/A"}
            ])
            st.dataframe(comp_df, use_container_width=True, hide_index=True)

            # Store in OCR session history
            if st.button("Save Result to Verification Audit Log"):
                record_to_save = {
                    'filename': uploaded_doc.name,
                    'timestamp': generate_timestamp(),
                    'ocr_roll': verification_outcome['ocr_roll'],
                    'ocr_name': verification_outcome['ocr_name'],
                    'ocr_cgpa': verification_outcome['ocr_cgpa'],
                    'official_cgpa': verification_outcome['official_cgpa'],
                    'status': status,
                    'reason': verification_outcome['reason']
                }
                st.session_state['ocr_history'].append(record_to_save)
                
                # If flagged, sync to registry
                if status == 'FLAGGED':
                    sync_flagged_records_from_verification([{
                        'Roll Number': verification_outcome['ocr_roll'],
                        'Submitted Name': verification_outcome['ocr_name'],
                        'Official Name': verification_outcome['official_name'],
                        'Difference': verification_outcome['difference'],
                        'Reason': f"Marksheet OCR: {verification_outcome['reason']}"
                    }])
                st.success("Result saved to audit history.")

            with st.expander("View Raw OCR Text Extraction"):
                st.text(raw_text if raw_text else "No text detected.")

    if st.session_state['ocr_history']:
        st.markdown("---")
        st.subheader("Recent OCR Verification Audits")
        st.dataframe(pd.DataFrame(st.session_state['ocr_history']), use_container_width=True, hide_index=True)


# =========================================================================
# SECTION 6: VERIFICATION RESULTS
# =========================================================================
elif menu == "6. 📋 Verification Results":
    st.markdown('<div class="main-header">Official Placement Verification Results</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Complete audit register and verifiable report generator</div>', unsafe_allow_html=True)

    results_data = st.session_state.get('verification_results')

    if results_data is None:
        st.info("ℹ️ No verification results available yet. Run verification in Section 4.")
    else:
        results_df = results_data['results_df']
        
        c_search, c_filter = st.columns([2, 1])
        with c_search:
            search_query = st.text_input("Search student by Roll Number or Name", "")
        with c_filter:
            status_filter = st.selectbox("Filter Status", ["ALL", STATUS_VERIFIED, STATUS_FLAGGED, STATUS_NOT_FOUND])

        display_df = results_df.copy()
        if status_filter != "ALL":
            display_df = display_df[display_df['Status'] == status_filter]
        if search_query.strip():
            sq = search_query.strip().lower()
            display_df = display_df[
                display_df['Roll Number'].str.lower().str.contains(sq) |
                display_df['Submitted Name'].str.lower().str.contains(sq) |
                display_df['Official Name'].str.lower().str.contains(sq)
            ]

        st.dataframe(display_df, use_container_width=True, hide_index=True)

        st.markdown("---")
        st.subheader("Download Verification Report")
        
        col_csv, col_excel = st.columns(2)
        with col_csv:
            csv_bytes = results_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download Report as CSV",
                data=csv_bytes,
                file_name=f"Placement_Verification_Report_{generate_timestamp().replace(':', '-').replace(' ', '_')}.csv",
                mime="text/csv"
            )
        with col_excel:
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                results_df.to_excel(writer, index=False, sheet_name='Verification_Results')
            excel_bytes = output.getvalue()
            st.download_button(
                label="📥 Download Report as Excel (.xlsx)",
                data=excel_bytes,
                file_name=f"Placement_Verification_Report_{generate_timestamp().replace(':', '-').replace(' ', '_')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )


# =========================================================================
# SECTION 7: FLAGGED STUDENTS
# =========================================================================
elif menu == "7. 🚩 Flagged Students":
    st.markdown('<div class="main-header">Flagged Students &amp; Blacklist Record</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Controlled administrative register for disciplinary and eligibility review</div>', unsafe_allow_html=True)

    st.markdown("""
    **TPO Governance Policy:**
    - Students are **never** permanently blacklisted solely from automated data entry discrepancies.
    - Status can be updated between **FLAGGED**, **UNDER REVIEW**, and **CLEARED** with administrative justification remarks.
    """)

    flagged_df = get_flagged_dataframe()

    if flagged_df.empty:
        st.success("🎉 No students are currently flagged in the registry.")
    else:
        st.dataframe(flagged_df, use_container_width=True, hide_index=True)

        st.markdown("---")
        st.subheader("Manage Student Status / Blacklist Record")
        
        rolls = flagged_df['Roll Number'].tolist()
        c1, c2, c3 = st.columns(3)
        with c1:
            selected_roll = st.selectbox("Select Candidate Roll Number", rolls)
        with c2:
            new_status = st.selectbox("Update Governance Status", [FLAG_STATUS_UNDER_REVIEW, FLAG_STATUS_CLEARED, FLAG_STATUS_FLAGGED])
        with c3:
            remarks = st.text_input("TPO Remarks / Decision Notes", "Reviewed in placement office")

        if st.button("Update Candidate Record"):
            success = update_record_status(selected_roll, new_status, remarks)
            if success:
                st.success(f"Candidate Roll {selected_roll} status updated to '{new_status}'.")
                st.rerun()
            else:
                st.error("Failed to update status.")


# =========================================================================
# SECTION 8: EMAIL STATUS & DISPATCH
# =========================================================================
elif menu == "8. ✉️ Email Status":
    st.markdown('<div class="main-header">Automated Email Alerts &amp; Dispatch Status</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Student Warning Notices &amp; TPO Fraud Incident Transmissions</div>', unsafe_allow_html=True)

    smtp_cfg = get_smtp_config()
    is_cfg, cfg_msg = is_smtp_configured()

    col_env, col_summary = st.columns([1, 1])
    with col_env:
        st.markdown("#### SMTP Configuration Status")
        if smtp_cfg['simulation_mode']:
            st.info("ℹ️ **Simulation Mode Active:** Alerts will be generated, verified, and logged without connecting to an external SMTP network.")
        elif is_cfg:
            st.success(f"✅ SMTP Active: Connected to **{smtp_cfg['server']}:{smtp_cfg['port']}**")
        else:
            st.error(f"⚠️ SMTP Not Fully Configured: {cfg_msg}")

        st.write(f"- **Server:** `{smtp_cfg['server']}`")
        st.write(f"- **Port:** `{smtp_cfg['port']}`")
        st.write(f"- **Sender Email:** `{smtp_cfg['email'] or 'Not Set'}`")
        st.write(f"- **TPO Alert Destination:** `{smtp_cfg['tpo_email']}`")

    with col_summary:
        st.markdown("#### Automated Alert Rules")
        st.write("1. **Student Warning Email:** Dispatched only for FLAGGED or NOT FOUND records.")
        st.write("2. **TPO Incident Alert:** Dispatched with complete mismatch telemetry.")
        st.write("3. **Verified Records:** Strictly excluded from fraud warnings.")
        st.write("4. **Delivery Guarantee:** Real SMTP delivery is verified before marking DELIVERED.")

    st.markdown("---")
    st.subheader("Dispatch Alerts for Flagged Students")

    flagged_records = get_all_flagged_records()
    active_mismatches = [r for r in flagged_records if r.get('Status') in [FLAG_STATUS_FLAGGED, FLAG_STATUS_UNDER_REVIEW]]

    if not active_mismatches:
        st.info("No active flagged records requiring alerts.")
    else:
        st.write(f"There are **{len(active_mismatches)}** candidates eligible for fraud warning notification.")
        
        selected_cand = st.selectbox(
            "Select Candidate to Dispatch Warning & TPO Alert",
            options=active_mismatches,
            format_func=lambda x: f"Roll: {x['Roll Number']} | {x['Name']} | {x['Reason']}"
        )

        custom_email = st.text_input(
            "Candidate Email Address (Defaults to student roll domain)", 
            value=f"{str(selected_cand['Roll Number']).lower()}@college.edu"
        )

        if st.button("📨 Dispatch Warning Email to Student & Alert to TPO", type="primary"):
            with st.spinner("Processing email transmission..."):
                dispatch_res = dispatch_alerts_for_flagged_record(selected_cand, student_email=custom_email)
                
                if dispatch_res.get('success'):
                    st.success("✅ Email Operation Succeeded!")
                    st.write(f"Student: {dispatch_res['student_dispatch']['message']}")
                    st.write(f"TPO: {dispatch_res['tpo_dispatch']['message']}")
                else:
                    st.error("❌ Email Operation Encountered an Issue:")
                    st.write(f"Student dispatch: {dispatch_res.get('student_dispatch', {}).get('message')}")
                    st.write(f"TPO dispatch: {dispatch_res.get('tpo_dispatch', {}).get('message')}")

    st.markdown("---")
    st.subheader("Email Dispatch Audit Log")
    logs = get_dispatch_logs()
    if logs:
        st.dataframe(pd.DataFrame(logs), use_container_width=True, hide_index=True)
    else:
        st.caption("No emails dispatched yet.")
