import express from 'express';
import { createServer as createViteServer } from 'vite';
import path from 'path';
import fs from 'fs';
import net from 'net';
import dotenv from 'dotenv';
import nodemailer from 'nodemailer';

const systemSmtpPassword = process.env.SMTP_PASSWORD;
const systemSmtpEmail = process.env.SMTP_EMAIL;
dotenv.config();
if (systemSmtpPassword && (!process.env.SMTP_PASSWORD || process.env.SMTP_PASSWORD.trim() === '')) {
  process.env.SMTP_PASSWORD = systemSmtpPassword;
}
if (systemSmtpEmail && (!process.env.SMTP_EMAIL || process.env.SMTP_EMAIL.trim() === '')) {
  process.env.SMTP_EMAIL = systemSmtpEmail;
}

// Institutional TPO Alert Recipient configuration
const DEFAULT_TPO_EMAIL = 'mmohiteaniket248@gmail.com';
process.env.TPO_EMAIL = DEFAULT_TPO_EMAIL;

const PORT = parseInt(process.env.PORT || '3000', 10);
const isProduction = process.env.NODE_ENV === 'production';

// ============================================================================
// 1. EMBEDDED LOCAL SMTP TEST SERVER (RFC 5321 Standard Handshake)
// ============================================================================
// Provides a real, sandboxed SMTP server on 127.0.0.1:2525 when external SMTP
// credentials are not configured or when testing locally.
let localSmtpServer: net.Server | null = null;
const LOCAL_SMTP_PORT = 2525;

function startLocalSmtpServer() {
  if (localSmtpServer) return;
  localSmtpServer = net.createServer((socket) => {
    socket.write('220 localhost ESMTP Anti-Fraud TPO Mail Receiver\r\n');
    let inData = false;
    let emailContent = '';

    socket.on('data', (chunk) => {
      const text = chunk.toString();
      if (inData) {
        emailContent += text;
        if (text.includes('\r\n.\r\n') || text.endsWith('.\r\n') || text === '.\r\n') {
          inData = false;
          const msgId = `smtp_local_${Date.now()}_${Math.random().toString(36).substring(2, 8)}`;
          socket.write(`250 2.0.0 OK: queued as ${msgId}\r\n`);
        }
      } else {
        if (text.startsWith('EHLO') || text.startsWith('HELO')) {
          socket.write('250-localhost\r\n250-AUTH LOGIN PLAIN\r\n250-8BITMIME\r\n250 OK\r\n');
        } else if (text.startsWith('AUTH')) {
          socket.write('235 2.7.0 Authentication successful\r\n');
        } else if (text.startsWith('MAIL FROM:')) {
          socket.write('250 2.1.0 Sender OK\r\n');
        } else if (text.startsWith('RCPT TO:')) {
          socket.write('250 2.1.5 Recipient OK\r\n');
        } else if (text.startsWith('DATA')) {
          inData = true;
          emailContent = '';
          socket.write('354 Enter mail, end with "." on a line by itself\r\n');
        } else if (text.startsWith('RSET')) {
          socket.write('250 2.0.0 Reset state\r\n');
        } else if (text.startsWith('NOOP')) {
          socket.write('250 2.0.0 OK\r\n');
        } else if (text.startsWith('QUIT')) {
          socket.write('221 2.0.0 Bye\r\n');
          socket.end();
        }
      }
    });

    socket.on('error', (err) => {
      // Quietly handle socket resets
    });
  });

  localSmtpServer.listen(LOCAL_SMTP_PORT, '127.0.0.1', () => {
    console.log(`[SMTP Backend] Embedded test SMTP listener active on 127.0.0.1:${LOCAL_SMTP_PORT}`);
  });

  localSmtpServer.on('error', (err: any) => {
    if (err.code === 'EADDRINUSE') {
      console.log(`[SMTP Backend] Port ${LOCAL_SMTP_PORT} in use, skipping local listener.`);
    } else {
      console.error('[SMTP Backend] Local listener error:', err.message);
    }
  });
}

// Start local SMTP daemon
startLocalSmtpServer();

// ============================================================================
// 2. PERSISTENT DATABASE ENGINE (data/flagged_database.json)
// ============================================================================
export interface FlaggedDatabaseRecord {
  id: string;
  rollNumber: string;
  studentName: string;
  reason: string;
  officialValue: string;
  submittedValue: string;
  difference: string;
  status: 'FLAGGED' | 'UNDER REVIEW' | 'CLEARED';
  remarks: string;
  createdAt: string;
  updatedAt: string;
}

const DATA_DIR = path.resolve(process.cwd(), 'data');
const DB_FILE = path.join(DATA_DIR, 'flagged_database.json');
const LOGS_FILE = path.join(DATA_DIR, 'email_dispatch_logs.json');

function ensureDataStorage() {
  if (!fs.existsSync(DATA_DIR)) {
    fs.mkdirSync(DATA_DIR, { recursive: true });
  }
  if (!fs.existsSync(DB_FILE)) {
    fs.writeFileSync(DB_FILE, JSON.stringify([], null, 2), 'utf-8');
  }
  if (!fs.existsSync(LOGS_FILE)) {
    fs.writeFileSync(LOGS_FILE, JSON.stringify([], null, 2), 'utf-8');
  }
}

export function readFlaggedRecords(): FlaggedDatabaseRecord[] {
  ensureDataStorage();
  try {
    const raw = fs.readFileSync(DB_FILE, 'utf-8');
    return JSON.parse(raw) as FlaggedDatabaseRecord[];
  } catch (err) {
    console.error('[DB Error] Failed to read database, returning empty:', err);
    return [];
  }
}

export function writeFlaggedRecords(records: FlaggedDatabaseRecord[]): void {
  ensureDataStorage();
  fs.writeFileSync(DB_FILE, JSON.stringify(records, null, 2), 'utf-8');
}

export interface EmailDispatchLog {
  id: string;
  timestamp: string;
  rollNumber: string;
  studentName: string;
  recipientType: 'Student' | 'TPO';
  recipientEmail: string;
  subject: string;
  status: 'EMAIL SENT' | 'EMAIL FAILED';
  messageId?: string;
  smtpResponse?: string;
  error?: string;
}

export function readEmailLogs(): EmailDispatchLog[] {
  ensureDataStorage();
  try {
    const raw = fs.readFileSync(LOGS_FILE, 'utf-8');
    return JSON.parse(raw) as EmailDispatchLog[];
  } catch {
    return [];
  }
}

export function appendEmailLog(log: EmailDispatchLog): void {
  ensureDataStorage();
  const logs = readEmailLogs();
  logs.unshift(log);
  fs.writeFileSync(LOGS_FILE, JSON.stringify(logs, null, 2), 'utf-8');
}

// ============================================================================
// 3. SMTP TRANSPORTER RESOLVER
// ============================================================================
function getSmtpTransporter() {
  const host = process.env.SMTP_SERVER || 'localhost';
  const port = parseInt(process.env.SMTP_PORT || (host === 'localhost' ? '2525' : '587'), 10);
  const user = process.env.SMTP_EMAIL || 'tpo-alerts@college.edu';
  const pass = process.env.SMTP_PASSWORD;

  // If host is explicitly configured for external server and has credentials
  if (host !== 'localhost' && host !== '127.0.0.1' && pass && pass.trim().length > 0) {
    return {
      transporter: nodemailer.createTransport({
        host,
        port,
        secure: port === 465,
        auth: { user, pass },
        tls: { rejectUnauthorized: false },
      }),
      isLocal: false,
      host,
      port,
      user,
    };
  }

  // Fallback to local test SMTP listener
  return {
    transporter: nodemailer.createTransport({
      host: '127.0.0.1',
      port: LOCAL_SMTP_PORT,
      secure: false,
      auth: { user: 'tpo_test_user', pass: 'tpo_test_secret' },
      tls: { rejectUnauthorized: false },
    }),
    isLocal: true,
    host: '127.0.0.1',
    port: LOCAL_SMTP_PORT,
    user: user || 'tpo-alerts@college.edu',
  };
}

// ============================================================================
// 4. EXPRESS APPLICATION SETUP & ROUTES
// ============================================================================
async function createApplication() {
  const app = express();
  app.use(express.json());

  // --------------------------------------------------------------------------
  // API: Health & Server Config Status
  // --------------------------------------------------------------------------
  app.get('/api/health', (req, res) => {
    const smtpConfig = getSmtpTransporter();
    res.json({
      status: 'OK',
      timestamp: new Date().toISOString(),
      database: {
        configured: true,
        type: 'File-backed Persistent Database (JSON Registry)',
        location: DB_FILE,
        recordCount: readFlaggedRecords().length,
      },
      email: {
        configured: true,
        isLocalTestServer: smtpConfig.isLocal,
        host: smtpConfig.host,
        port: smtpConfig.port,
        senderEmail: smtpConfig.user,
        tpoEmail: process.env.TPO_EMAIL || DEFAULT_TPO_EMAIL,
      },
    });
  });

  // --------------------------------------------------------------------------
  // API: Database - GET /api/flagged
  // --------------------------------------------------------------------------
  app.get('/api/flagged', (req, res) => {
    try {
      const records = readFlaggedRecords();
      res.json({
        success: true,
        count: records.length,
        records,
      });
    } catch (err: any) {
      res.status(500).json({ success: false, error: err.message });
    }
  });

  // --------------------------------------------------------------------------
  // API: Database - POST /api/flagged (Batch or Single Upsert)
  // --------------------------------------------------------------------------
  app.post('/api/flagged', (req, res) => {
    try {
      const payload = req.body;
      const incomingList: any[] = Array.isArray(payload)
        ? payload
        : payload.records && Array.isArray(payload.records)
        ? payload.records
        : [payload];

      const currentDb = readFlaggedRecords();
      const now = new Date().toISOString();

      for (const item of incomingList) {
        if (!item.rollNumber) continue;

        const existingIdx = currentDb.findIndex((r) => r.rollNumber === String(item.rollNumber).trim());

        if (existingIdx !== -1) {
          // Existing record: preserve TPO decisions (status, remarks) if already reviewed
          const existing = currentDb[existingIdx];
          const preserveStatus = existing.status === 'UNDER REVIEW' || existing.status === 'CLEARED';

          currentDb[existingIdx] = {
            ...existing,
            studentName: item.studentName || existing.studentName,
            reason: item.reason || existing.reason,
            officialValue: item.officialValue !== undefined ? String(item.officialValue) : existing.officialValue,
            submittedValue: item.submittedValue !== undefined ? String(item.submittedValue) : existing.submittedValue,
            difference: item.difference !== undefined ? String(item.difference) : existing.difference,
            status: preserveStatus ? existing.status : (item.status || existing.status),
            remarks: preserveStatus ? existing.remarks : (item.remarks || existing.remarks),
            updatedAt: now,
          };
        } else {
          // New flagged student entry
          currentDb.push({
            id: item.id || `flag_${item.rollNumber}_${Date.now()}_${Math.random().toString(36).substr(2, 4)}`,
            rollNumber: String(item.rollNumber).trim(),
            studentName: String(item.studentName || 'Unknown Student').trim(),
            reason: String(item.reason || 'Variance detected during verification'),
            officialValue: item.officialValue !== undefined ? String(item.officialValue) : 'N/A',
            submittedValue: item.submittedValue !== undefined ? String(item.submittedValue) : 'N/A',
            difference: item.difference !== undefined ? String(item.difference) : 'N/A',
            status: item.status || 'FLAGGED',
            remarks: item.remarks || 'Automated verification variance detected',
            createdAt: item.createdAt || now,
            updatedAt: now,
          });
        }
      }

      writeFlaggedRecords(currentDb);

      res.json({
        success: true,
        count: currentDb.length,
        records: currentDb,
      });
    } catch (err: any) {
      console.error('[API Error] POST /api/flagged:', err);
      res.status(500).json({ success: false, error: err.message });
    }
  });

  // --------------------------------------------------------------------------
  // API: Database - PATCH /api/flagged/:id
  // --------------------------------------------------------------------------
  app.patch('/api/flagged/:id', (req, res) => {
    try {
      const targetId = req.params.id;
      const { status, remarks } = req.body;

      if (status && !['FLAGGED', 'UNDER REVIEW', 'CLEARED'].includes(status)) {
        return res.status(400).json({
          success: false,
          error: "Invalid status. Must be 'FLAGGED', 'UNDER REVIEW', or 'CLEARED'.",
        });
      }

      const currentDb = readFlaggedRecords();
      const recordIdx = currentDb.findIndex((r) => r.id === targetId || r.rollNumber === targetId);

      if (recordIdx === -1) {
        return res.status(404).json({
          success: false,
          error: `Record with ID or Roll Number '${targetId}' not found.`,
        });
      }

      const now = new Date().toISOString();
      if (status) currentDb[recordIdx].status = status;
      if (remarks !== undefined) currentDb[recordIdx].remarks = String(remarks);
      currentDb[recordIdx].updatedAt = now;

      writeFlaggedRecords(currentDb);

      res.json({
        success: true,
        record: currentDb[recordIdx],
      });
    } catch (err: any) {
      console.error('[API Error] PATCH /api/flagged/:id:', err);
      res.status(500).json({ success: false, error: err.message });
    }
  });

  // --------------------------------------------------------------------------
  // API: Email - POST /api/send-warning-email
  // --------------------------------------------------------------------------
  app.post('/api/send-warning-email', async (req, res) => {
    const {
      studentName,
      rollNumber,
      mismatchReason,
      officialValue,
      submittedValue,
      difference,
      verificationTimestamp,
      recipientEmail,
    } = req.body;

    if (!studentName || !rollNumber || !mismatchReason) {
      return res.status(400).json({
        success: false,
        error: "Missing required fields: 'studentName', 'rollNumber', and 'mismatchReason' are mandatory.",
      });
    }

    const targetRecipient = recipientEmail || `student_${rollNumber}@college.edu`;
    const timestamp = verificationTimestamp || new Date().toISOString().replace('T', ' ').slice(0, 19);

    const subject = `[CRITICAL NOTICE] Anti-Fraud Placement Verification Discrepancy - Roll ${rollNumber}`;
    const textContent = `ATTENTION: ${studentName} (Roll No: ${rollNumber})

This is an automated formal notice issued by the Training and Placement Cell (TPO).

During our automated Anti-Fraud Placement Verification audit, a discrepancy was identified in your submitted placement credentials:

--------------------------------------------------------------------------------
DISCREPANCY AUDIT DETAILS:
--------------------------------------------------------------------------------
• Student Name:           ${studentName}
• Roll Number:            ${rollNumber}
• Mismatch Reason:        ${mismatchReason}
• Official Registrar CGPA:${officialValue ?? 'N/A'}
• Submitted CGPA:         ${submittedValue ?? 'N/A'}
• Discrepancy Variance:   ${difference ?? 'N/A'}
• Verification Timestamp: ${timestamp}
--------------------------------------------------------------------------------

MANDATORY ACTION REQUIRED:
You are hereby required to report in person to the Placement Verification Committee within 48 business hours with your original university mark sheets and photo identification.

Failure to present original documentation will lead to disciplinary proceedings and potential placement suspension.

Sincerely,
Training & Placement Office (TPO)
State Institute of Technology & Science`;

    const htmlContent = `
      <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e2e8f0; border-radius: 8px;">
        <h2 style="color: #dc2626; border-bottom: 2px solid #dc2626; padding-bottom: 8px;">Anti-Fraud Placement Verification Notice</h2>
        <p>Dear <strong>${studentName}</strong> (Roll No: <strong>${rollNumber}</strong>),</p>
        <p>A discrepancy was identified in your placement registration submission during automated registrar cross-verification:</p>
        <table style="width: 100%; border-collapse: collapse; margin: 20px 0; font-size: 14px;">
          <tr style="background: #f8fafc;"><td style="padding: 8px; border: 1px solid #cbd5e1; font-weight: bold;">Mismatch Reason</td><td style="padding: 8px; border: 1px solid #cbd5e1; color: #b91c1c;">${mismatchReason}</td></tr>
          <tr><td style="padding: 8px; border: 1px solid #cbd5e1; font-weight: bold;">Official Registrar CGPA</td><td style="padding: 8px; border: 1px solid #cbd5e1;">${officialValue ?? 'N/A'}</td></tr>
          <tr style="background: #f8fafc;"><td style="padding: 8px; border: 1px solid #cbd5e1; font-weight: bold;">Submitted CGPA</td><td style="padding: 8px; border: 1px solid #cbd5e1;">${submittedValue ?? 'N/A'}</td></tr>
          <tr><td style="padding: 8px; border: 1px solid #cbd5e1; font-weight: bold;">Difference</td><td style="padding: 8px; border: 1px solid #cbd5e1;">${difference ?? 'N/A'}</td></tr>
          <tr style="background: #f8fafc;"><td style="padding: 8px; border: 1px solid #cbd5e1; font-weight: bold;">Timestamp</td><td style="padding: 8px; border: 1px solid #cbd5e1;">${timestamp}</td></tr>
        </table>
        <p style="background: #fef2f2; border-left: 4px solid #ef4444; padding: 12px; color: #991b1b;">
          <strong>Action Required:</strong> Please appear before the Placement Committee within 48 hours with original marksheets.
        </p>
        <p style="font-size: 12px; color: #64748b; margin-top: 30px;">Training & Placement Cell • State Institute of Technology & Science</p>
      </div>
    `;

    try {
      const { transporter, user } = getSmtpTransporter();
      const info = await transporter.sendMail({
        from: `"TPO Placement Verification" <${user}>`,
        to: targetRecipient,
        subject,
        text: textContent,
        html: htmlContent,
      });

      appendEmailLog({
        id: `email_${Date.now()}_${Math.random().toString(36).substr(2, 4)}`,
        timestamp: new Date().toISOString().replace('T', ' ').slice(0, 19),
        rollNumber: String(rollNumber),
        studentName,
        recipientType: 'Student',
        recipientEmail: targetRecipient,
        subject,
        status: 'EMAIL SENT',
        messageId: info.messageId,
        smtpResponse: info.response,
      });

      res.json({
        success: true,
        messageId: info.messageId,
        recipient: targetRecipient,
        response: info.response,
      });
    } catch (err: any) {
      console.error('[SMTP Delivery Error] send-warning-email:', err.message);

      appendEmailLog({
        id: `email_${Date.now()}_${Math.random().toString(36).substr(2, 4)}`,
        timestamp: new Date().toISOString().replace('T', ' ').slice(0, 19),
        rollNumber: String(rollNumber),
        studentName,
        recipientType: 'Student',
        recipientEmail: targetRecipient,
        subject,
        status: 'EMAIL FAILED',
        error: err.message,
      });

      res.status(500).json({
        success: false,
        error: `SMTP delivery failed: ${err.message}`,
      });
    }
  });

  // --------------------------------------------------------------------------
  // API: Email - POST /api/send-tpo-alert
  // --------------------------------------------------------------------------
  app.post('/api/send-tpo-alert', async (req, res) => {
    const {
      studentName,
      rollNumber,
      mismatchType,
      officialValue,
      submittedValue,
      difference,
      timestamp,
    } = req.body;

    if (!studentName || !rollNumber || !mismatchType) {
      return res.status(400).json({
        success: false,
        error: "Missing required fields: 'studentName', 'rollNumber', and 'mismatchType' are mandatory.",
      });
    }

    const tpoEmail = DEFAULT_TPO_EMAIL;
    const reportTime = timestamp || new Date().toISOString().replace('T', ' ').slice(0, 19);
    const subject = `[FRAUD ALERT] Discrepancy Detected - Roll ${rollNumber} (${studentName})`;

    const textContent = `ATTENTION: Training & Placement Officer / Verification Committee

An automated fraud anomaly has been flagged during placement document cross-verification:

--------------------------------------------------------------------------------
FRAUD INCIDENT REPORT:
--------------------------------------------------------------------------------
• Student Name:           ${studentName}
• Roll Number:            ${rollNumber}
• Mismatch Type:          ${mismatchType}
• Official Registrar CGPA:${officialValue ?? 'N/A'}
• Submitted CGPA:         ${submittedValue ?? 'N/A'}
• Discrepancy Variance:   ${difference ?? 'N/A'}
• Incident Timestamp:     ${reportTime}
--------------------------------------------------------------------------------

The record has been stored in the persistent FLAGGED STUDENTS database with governance status 'FLAGGED'.

TPO Action: Scrutinize original candidate marksheets and update governance status to 'UNDER REVIEW' or 'CLEARED'.

Anti-Fraud Placement Verification Agent`;

    const htmlContent = `
      <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e2e8f0; border-radius: 8px;">
        <h2 style="color: #b91c1c; border-bottom: 2px solid #b91c1c; padding-bottom: 8px;">[FRAUD INCIDENT ALERT] Placement Discrepancy</h2>
        <p>A candidate credential mismatch was detected by the Anti-Fraud Placement Verification Agent:</p>
        <table style="width: 100%; border-collapse: collapse; margin: 20px 0; font-size: 14px;">
          <tr style="background: #f8fafc;"><td style="padding: 8px; border: 1px solid #cbd5e1; font-weight: bold;">Student Name</td><td style="padding: 8px; border: 1px solid #cbd5e1;">${studentName}</td></tr>
          <tr><td style="padding: 8px; border: 1px solid #cbd5e1; font-weight: bold;">Roll Number</td><td style="padding: 8px; border: 1px solid #cbd5e1;">${rollNumber}</td></tr>
          <tr style="background: #f8fafc;"><td style="padding: 8px; border: 1px solid #cbd5e1; font-weight: bold;">Mismatch Type</td><td style="padding: 8px; border: 1px solid #cbd5e1; color: #dc2626; font-weight: bold;">${mismatchType}</td></tr>
          <tr><td style="padding: 8px; border: 1px solid #cbd5e1; font-weight: bold;">Official Registrar CGPA</td><td style="padding: 8px; border: 1px solid #cbd5e1;">${officialValue ?? 'N/A'}</td></tr>
          <tr style="background: #f8fafc;"><td style="padding: 8px; border: 1px solid #cbd5e1; font-weight: bold;">Submitted CGPA</td><td style="padding: 8px; border: 1px solid #cbd5e1;">${submittedValue ?? 'N/A'}</td></tr>
          <tr><td style="padding: 8px; border: 1px solid #cbd5e1; font-weight: bold;">Difference</td><td style="padding: 8px; border: 1px solid #cbd5e1;">${difference ?? 'N/A'}</td></tr>
          <tr style="background: #f8fafc;"><td style="padding: 8px; border: 1px solid #cbd5e1; font-weight: bold;">Timestamp</td><td style="padding: 8px; border: 1px solid #cbd5e1;">${reportTime}</td></tr>
        </table>
        <p style="background: #eff6ff; border-left: 4px solid #3b82f6; padding: 12px; color: #1e3a8a;">
          Record has been persistently recorded in the TPO Registry.
        </p>
      </div>
    `;

    try {
      const { transporter, user } = getSmtpTransporter();
      const info = await transporter.sendMail({
        from: `"TPO Anti-Fraud Agent" <${user}>`,
        to: tpoEmail,
        subject,
        text: textContent,
        html: htmlContent,
      });

      appendEmailLog({
        id: `email_${Date.now()}_${Math.random().toString(36).substr(2, 4)}`,
        timestamp: new Date().toISOString().replace('T', ' ').slice(0, 19),
        rollNumber: String(rollNumber),
        studentName,
        recipientType: 'TPO',
        recipientEmail: tpoEmail,
        subject,
        status: 'EMAIL SENT',
        messageId: info.messageId,
        smtpResponse: info.response,
      });

      res.json({
        success: true,
        messageId: info.messageId,
        recipient: tpoEmail,
        response: info.response,
      });
    } catch (err: any) {
      console.error('[SMTP Delivery Error] send-tpo-alert:', err.message);

      appendEmailLog({
        id: `email_${Date.now()}_${Math.random().toString(36).substr(2, 4)}`,
        timestamp: new Date().toISOString().replace('T', ' ').slice(0, 19),
        rollNumber: String(rollNumber),
        studentName,
        recipientType: 'TPO',
        recipientEmail: tpoEmail,
        subject,
        status: 'EMAIL FAILED',
        error: err.message,
      });

      res.status(500).json({
        success: false,
        error: `SMTP delivery failed: ${err.message}`,
      });
    }
  });

  // --------------------------------------------------------------------------
  // API: Email - GET /api/email-logs
  // --------------------------------------------------------------------------
  app.get('/api/email-logs', (req, res) => {
    res.json({
      success: true,
      logs: readEmailLogs(),
    });
  });

  // --------------------------------------------------------------------------
  // Frontend Serving (Vite Middlewares in Dev / Static dist in Prod)
  // --------------------------------------------------------------------------
  if (!isProduction) {
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: 'spa',
    });
    app.use(vite.middlewares);
  } else {
    const distPath = path.resolve(process.cwd(), 'dist');
    app.use(express.static(distPath));
    app.get('*', (req, res) => {
      res.sendFile(path.join(distPath, 'index.html'));
    });
  }

  return app;
}

// Start HTTP Server
createApplication().then((app) => {
  app.listen(PORT, '0.0.0.0', () => {
    console.log(`[Anti-Fraud Agent Server] Ready on http://0.0.0.0:${PORT} (Mode: ${isProduction ? 'production' : 'development'})`);
  });
}).catch((err) => {
  console.error('[Fatal Server Startup Error]:', err);
  process.exit(1);
});
