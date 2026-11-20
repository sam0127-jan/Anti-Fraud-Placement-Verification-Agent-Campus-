import fs from 'fs';
import path from 'path';

interface StudentRecord {
  rollNo: string;
  name: string;
  cgpa: number;
}

function areNamesMatching(name1: string, name2: string): boolean {
  const cleanTokens = (s: string) =>
    s
      .toLowerCase()
      .replace(/^(mr\.|ms\.|mrs\.|shri|smt)\s+/i, '')
      .replace(/[^a-z\s]/g, '')
      .trim()
      .split(/\s+/)
      .filter(Boolean)
      .sort();

  const t1 = cleanTokens(name1);
  const t2 = cleanTokens(name2);

  if (t1.join(' ') === t2.join(' ')) return true;
  const set2 = new Set(t2);
  const common = t1.filter((x) => set2.has(x));
  if (common.length >= 2 && (common.length === t1.length || common.length === t2.length)) {
    return true;
  }
  return false;
}

function verifyStudent(sub: StudentRecord, officialMap: Map<string, StudentRecord>) {
  const off = officialMap.get(sub.rollNo);
  if (!off) {
    return { status: 'NOT FOUND', reason: 'Roll Number does not exist in official college database' };
  }
  const nameOk = areNamesMatching(off.name, sub.name);
  const diff = Math.round((sub.cgpa - off.cgpa) * 100) / 100;
  const cgpaOk = Math.abs(diff) < 0.001;

  if (nameOk && cgpaOk) {
    return { status: 'VERIFIED', reason: 'Record matches official college database' };
  }
  const reasons: string[] = [];
  if (!nameOk) reasons.push(`Student Name mismatch (Official: '${off.name}', Submitted: '${sub.name}')`);
  if (!cgpaOk) reasons.push(`CGPA mismatch (Official: ${off.cgpa.toFixed(2)}, Submitted: ${sub.cgpa.toFixed(2)}, Diff: ${diff > 0 ? '+' : ''}${diff.toFixed(2)})`);
  return { status: 'FLAGGED', reason: reasons.join('; '), diff };
}

async function runEndToEndVerification() {
  console.log('================================================================');
  console.log('EXECUTION OF MANDATORY 10-STEP END-TO-END VERIFICATION TEST');
  console.log('================================================================\n');

  // Input Data as specified in brief
  const official = { rollNo: '101', name: 'Rahul Patil', cgpa: 8.25 };
  const submitted = { rollNo: '101', name: 'Rahul Patil', cgpa: 9.25 };

  console.log('Input Parameters:');
  console.log('  Official:  Roll: 101, Name: Rahul Patil, CGPA: 8.25');
  console.log('  Submitted: Roll: 101, Name: Rahul Patil, CGPA: 9.25\n');

  // Step 0: Verification Logic
  const officialMap = new Map<string, StudentRecord>();
  officialMap.set(official.rollNo, official);

  const verificationResult = verifyStudent(submitted, officialMap);
  console.log(`[Verification Outcome] Status: ${verificationResult.status}`);
  console.log(`[Discrepancy Reason]  Reason: ${verificationResult.reason}`);

  if (verificationResult.status !== 'FLAGGED' || !verificationResult.reason.includes('CGPA mismatch')) {
    throw new Error(`Step 0 Failed: Expected FLAGGED with CGPA mismatch, got ${verificationResult.status}`);
  }
  console.log('✔ Verification Rule Check: PASS (Expected FLAGGED due to CGPA mismatch)\n');

  const BASE_URL = 'http://127.0.0.1:3000';

  // Step 1: Save the flagged record to the persistent database
  console.log('Step 1: Saving flagged record to persistent database via POST /api/flagged...');
  const saveRes = await fetch(`${BASE_URL}/api/flagged`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      records: [
        {
          rollNumber: submitted.rollNo,
          studentName: submitted.name,
          reason: verificationResult.reason,
          officialValue: String(official.cgpa),
          submittedValue: String(submitted.cgpa),
          difference: '+1.00',
          status: 'FLAGGED',
          remarks: 'Automated verification variance detected',
        },
      ],
    }),
  });
  const saveData = await saveRes.json();
  if (!saveRes.ok || !saveData.success) {
    throw new Error(`Step 1 Failed: ${JSON.stringify(saveData)}`);
  }
  console.log('✔ Step 1 PASS: Record successfully persisted to database.');

  // Step 2 & 3: Refresh the application & verify record still exists
  console.log('\nStep 2 & 3: Simulating application refresh and querying persistent database GET /api/flagged...');
  const getRes = await fetch(`${BASE_URL}/api/flagged`);
  const getData = await getRes.json();
  const foundRecord = getData.records?.find((r: any) => r.rollNumber === '101');
  if (!foundRecord) {
    throw new Error('Step 3 Failed: Record for Roll 101 not found after refresh query.');
  }

  // Also verify on physical disk
  const dbDiskPath = path.resolve(process.cwd(), 'data', 'flagged_database.json');
  const diskRaw = fs.readFileSync(dbDiskPath, 'utf-8');
  const diskRecords = JSON.parse(diskRaw);
  const diskMatch = diskRecords.find((r: any) => r.rollNumber === '101');
  if (!diskMatch) {
    throw new Error('Step 3 Failed: Record not found in data/flagged_database.json on disk.');
  }
  console.log(`✔ Step 2 & 3 PASS: Record verified surviving refresh on disk and API. Roll: ${foundRecord.rollNumber}, Name: ${foundRecord.studentName}, Status: ${foundRecord.status}`);

  // Step 4: Send the student warning email
  console.log('\nStep 4: Sending Student Warning Email via POST /api/send-warning-email...');
  const studentEmailRes = await fetch(`${BASE_URL}/api/send-warning-email`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      studentName: submitted.name,
      rollNumber: submitted.rollNo,
      mismatchReason: verificationResult.reason,
      officialValue: String(official.cgpa),
      submittedValue: String(submitted.cgpa),
      difference: '+1.00',
      verificationTimestamp: new Date().toISOString(),
      recipientEmail: 'mohiteaniket248@gmail.com',
    }),
  });
  const studentEmailData = await studentEmailRes.json();
  if (!studentEmailRes.ok || !studentEmailData.success) {
    throw new Error(`Step 4 Failed: ${JSON.stringify(studentEmailData)}`);
  }
  console.log(`✔ Step 4 PASS: Student warning email delivered. Message ID: ${studentEmailData.messageId}`);

  // Step 5: Send the TPO fraud alert
  console.log('\nStep 5: Sending TPO Fraud Alert via POST /api/send-tpo-alert...');
  const tpoEmailRes = await fetch(`${BASE_URL}/api/send-tpo-alert`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      studentName: submitted.name,
      rollNumber: submitted.rollNo,
      mismatchType: verificationResult.reason,
      officialValue: String(official.cgpa),
      submittedValue: String(submitted.cgpa),
      difference: '+1.00',
      timestamp: new Date().toISOString(),
    }),
  });
  const tpoEmailData = await tpoEmailRes.json();
  if (!tpoEmailRes.ok || !tpoEmailData.success) {
    throw new Error(`Step 5 Failed: ${JSON.stringify(tpoEmailData)}`);
  }
  if (tpoEmailData.recipient !== 'mmohiteaniket248@gmail.com') {
    throw new Error(`Step 5 Failed: Expected recipient to be mmohiteaniket248@gmail.com, got ${tpoEmailData.recipient}`);
  }
  console.log(`✔ Step 5 PASS: TPO fraud alert delivered to ${tpoEmailData.recipient}. Message ID: ${tpoEmailData.messageId}`);

  // Step 6: Verify actual email delivery response
  console.log('\nStep 6: Verifying SMTP server transmission responses...');
  console.log(`  Student Email SMTP Response: ${studentEmailData.response}`);
  console.log(`  TPO Alert SMTP Response:     ${tpoEmailData.response}`);
  if (!studentEmailData.response.includes('250') || !tpoEmailData.response.includes('250')) {
    throw new Error('Step 6 Failed: SMTP server response did not include standard RFC 5321 250 OK acknowledgment.');
  }
  console.log('✔ Step 6 PASS: Verified RFC 5321 250 OK acknowledgment for all dispatched emails.');

  // Step 7 & 8: Change status to UNDER REVIEW and add a remark
  console.log('\nStep 7 & 8: TPO updating status to UNDER REVIEW and adding audit remarks via PATCH /api/flagged/101...');
  const targetId = foundRecord.id || '101';
  const newRemark = 'Candidate summoned with original marksheets for physical registrar scrutiny.';
  const patchRes = await fetch(`${BASE_URL}/api/flagged/${targetId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      status: 'UNDER REVIEW',
      remarks: newRemark,
    }),
  });
  const patchData = await patchRes.json();
  if (!patchRes.ok || !patchData.success) {
    throw new Error(`Step 7/8 Failed: ${JSON.stringify(patchData)}`);
  }
  console.log(`✔ Step 7 & 8 PASS: Updated status to '${patchData.record.status}' with remark '${patchData.record.remarks}'.`);

  // Step 9 & 10: Refresh and verify status and remark remain saved
  console.log('\nStep 9 & 10: Refreshing application state and verifying persistence...');
  const refreshRes = await fetch(`${BASE_URL}/api/flagged`);
  const refreshData = await refreshRes.json();
  const refreshedRecord = refreshData.records?.find((r: any) => r.rollNumber === '101');

  if (!refreshedRecord) {
    throw new Error('Step 10 Failed: Record 101 missing after refresh.');
  }
  if (refreshedRecord.status !== 'UNDER REVIEW') {
    throw new Error(`Step 10 Failed: Expected status UNDER REVIEW, found ${refreshedRecord.status}`);
  }
  if (refreshedRecord.remarks !== newRemark) {
    throw new Error(`Step 10 Failed: Expected remark '${newRemark}', found '${refreshedRecord.remarks}'`);
  }
  console.log(`✔ Step 9 & 10 PASS: Persisted record verified after refresh!`);
  console.log(`  Roll:    ${refreshedRecord.rollNumber}`);
  console.log(`  Name:    ${refreshedRecord.studentName}`);
  console.log(`  Status:  ${refreshedRecord.status}`);
  console.log(`  Remarks: ${refreshedRecord.remarks}`);
  console.log(`  Updated: ${refreshedRecord.updatedAt}`);

  console.log('\n================================================================');
  console.log('ALL 10 END-TO-END VERIFICATION STEPS COMPLETED & VERIFIED: PASS');
  console.log('================================================================\n');
}

runEndToEndVerification().catch((err) => {
  console.error('\n✖ END-TO-END TEST FAILED:', err.message);
  process.exit(1);
});
