# Anti-Fraud Placement Verification Agent

An automated, role-focused document and academic credential verification system engineered for College Training & Placement Offices (TPO), Placement Officers, and Faculty Verification Committees.

---

## 📌 Project Architecture & Verification Workflow

The system enforces strict compliance against official college ground truth records through a sequential 6-stage pipeline:

```
Official College Data (Source of Truth)
           ↓
Student Submitted Data
           ↓
Roll Number Matching
           ↓
Name + CGPA Verification
           ↓
Fraud / Mismatch Detection
           ↓
OCR Marksheet Verification (Tesseract.js)
           ↓
Fraud Flagging & TPO Governance
           ↓
Warning Notice & Fraud Incident Drafting
           ↓
Controlled Blacklist / Flag Record (TPO Discretionary)
           ↓
Verifiable Report Generation (CSV & Excel)
```

---

## 🛠️ Technologies Used

- **UI & Dashboard:** React 19, Tailwind CSS v4, Lucide React
- **Full-Stack Server & Dev Mode:** Node.js Express server mounting Vite middlewares (`server.ts` on port 3000)
- **Email Backend Service:** NodeMailer SMTP transport connected via `/api/send-warning-email` and `/api/send-tpo-alert` with real RFC 5321 `250 OK` acknowledgment
- **Persistent Database:** JSON-backed disk database (`data/flagged_database.json`) & audit logs (`data/email_dispatch_logs.json`) surviving application restarts and reloads
- **Document & Spreadsheet Auditing:** SheetJS (`xlsx`) for multi-sheet Excel & CSV parsing
- **Optical Character Recognition (OCR):** Tesseract.js (Worker-based in-browser document scanner)
- **TypeScript:** Strict type checking across data models, validators, and audit pipelines
- **Testing:** Automated 10-point unit test suite + 10-step full end-to-end integration test runner (`npm test`)

---

## 📁 Project Structure

```text
anti-fraud-placement-agent/
├── src/
│   ├── App.tsx                # Main 8-section TPO Verification Portal & Dashboard
│   ├── main.tsx               # React application entry point
│   └── index.css              # Global styles & Tailwind CSS imports
├── tests/
│   ├── test_agent.ts          # Automated CLI test suite (10 scenarios)
│   └── test_agent.py          # Legacy Python test suite
├── data/
│   └── test/                  # Test datasets & sample marksheets (10 test cases)
│       ├── official_college_records_sample.xlsx
│       ├── student_submitted_records_sample.xlsx
│       ├── marksheet_case6_correct.png
│       ├── marksheet_case7_mismatch.png
│       └── marksheet_case8_unreadable.png
├── index.html                 # HTML shell with synchronized meta & title
├── package.json               # NPM scripts & dependencies
├── vite.config.ts             # Vite configuration with Tailwind CSS plugin
├── tsconfig.json              # TypeScript compiler configuration
├── .env.example               # Documentation of public vs private variables
├── .env                       # Local environment variables
└── README.md                  # Comprehensive architectural documentation
```

---

## ⚙️ Environment Variables (`.env.example`)

### 1. Public Variables (Client-Safe)
| Variable Name | Purpose | Where to Get It | Scope |
| :--- | :--- | :--- | :--- |
| `VITE_COLLEGE_NAME` | Institutional name displayed in reports | College Registry | Public (Client) |
| `VITE_APP_TITLE` | Application portal header | Placement Cell | Public (Client) |
| `VITE_TPO_DESK_EMAIL` | Desk contact for student notices | Placement Desk | Public (Client) |

### 2. Private Server-Side Secrets (Never Expose to Browser)
| Variable Name | Purpose | Where to Get It | Scope |
| :--- | :--- | :--- | :--- |
| `SMTP_SERVER` | SMTP host (e.g., `smtp.gmail.com`) | Email Provider | Private (Backend) |
| `SMTP_PORT` | Port (e.g., `587`) | Email Provider | Private (Backend) |
| `SMTP_EMAIL` | Sender mailbox address | College IT Admin | Private (Backend) |
| `SMTP_PASSWORD` | App-specific password / auth token | Mail Account Security | Private (Backend) |
| `TPO_EMAIL` | Alert recipient address | Placement Officer | Private (Backend) |

> **Security Guarantee:** Private credentials (`SMTP_PASSWORD`) are never bundled into the client bundle or accessed in browser code. Notice delivery is performed exclusively on the server side via Express REST endpoints (`/api/send-warning-email` and `/api/send-tpo-alert`). All operations return verified delivery IDs and RFC 5321 `250 OK` acknowledgment codes.

---

## 🚀 How to Run Locally

### 1. Install Dependencies
```bash
npm install
```

### 2. Run the Development Server
```bash
npm run dev
```
The application will open at `http://localhost:3000`.

### 3. Build for Production
```bash
npm run build
```

### 4. Run the Automated Test Suite
```bash
npm test
```

---

## 🧪 Automated Testing Suite (Stage 6)

The automated test runner (`npm test`) validates both the 10-point unit test suite and the 10-step live end-to-end integration workflow:

### Mandatory 10-Step End-to-End Workflow Verification:
| Step | Action | Verification Check | Status |
| :--- | :--- | :--- | :--- |
| 1 | Rule Check & Flag | Roll 101, Name Rahul Patil, Official 8.25 vs Submitted 9.25 → FLAGGED with CGPA mismatch | **PASS** |
| 2 | Persist Record | Stored in persistent database via `POST /api/flagged` | **PASS** |
| 3 | Application Refresh | Queried `GET /api/flagged` and verified on disk in `data/flagged_database.json` | **PASS** |
| 4 | Student Warning Email | Dispatched via `POST /api/send-warning-email` | **PASS** |
| 5 | TPO Fraud Alert | Dispatched via `POST /api/send-tpo-alert` | **PASS** |
| 6 | SMTP Delivery Confirmation | Received actual RFC 5321 `250 2.0.0 OK` from mail server with message ID | **PASS** |
| 7 | TPO Governance Status | Status updated to `UNDER REVIEW` via `PATCH /api/flagged/:id` | **PASS** |
| 8 | TPO Remarks | Added remark "Candidate summoned with original marksheets" | **PASS** |
| 9 | Application Refresh | Re-queried persistent store across application restart/reload | **PASS** |
| 10 | Persistence Retention | Verified status (`UNDER REVIEW`) and remark remain intact in store | **PASS** |

### Unit Test Matrix:
The automated test runner validates all 10 standard test cases:

| # | Test Scenario | Conditions | Expected Status | Status |
| :--- | :--- | :--- | :--- | :--- |
| 1 | **Correct Student Data** | Roll 101, Rahul Patil, CGPA 8.25 matches registrar | `VERIFIED` | **PASS** |
| 2 | **Incorrect / Inflated CGPA** | Roll 102 submitted 9.80 vs official 9.10 (+0.70 variance) | `FLAGGED` | **PASS** |
| 3 | **Incorrect Name** | Roll 103 submitted name "Vikram Singh" vs official "Amit Verma" | `FLAGGED` | **PASS** |
| 4 | **Unknown Roll Number** | Roll 999 does not exist in registrar records | `NOT FOUND` | **PASS** |
| 5 | **Duplicate Roll in Official** | Duplicate Roll 101 in official records | `DATA INTEGRITY ERROR` | **PASS** |
| 6 | **Invalid CGPA Range** | CGPA values outside 0.00-10.00 or non-numeric | `VALIDATION REJECTION` | **PASS** |
| 7 | **OCR Clean Marksheet** | Extracted Roll 101, Rahul Patil, 8.25 matches records | `VERIFIED` | **PASS** |
| 8 | **OCR Forged CGPA** | Marksheet with altered CGPA 9.95 vs official 8.25 | `FLAGGED` | **PASS** |
| 9 | **OCR Unreadable Scan** | Illegible or obscured document image | `MANUAL REVIEW` | **PASS** |
| 10 | **Email Security Policy** | Client prevents false claims of email delivery | `EMAIL NOT CONFIGURED` | **PASS** |

---

## 🛡️ TPO Governance & Blacklist Policy
- **No Automatic Permanent Blacklisting:** System mismatches never trigger irreversible disciplinary penalties automatically.
- **Three Controlled Discretionary States:**
  - `FLAGGED`: Automated audit detected a variance or absence from registrar records.
  - `UNDER REVIEW`: Candidate is called for in-person document scrutiny with original university marksheets.
  - `CLEARED`: Exonerated by Placement Committee with recorded justification remarks.
