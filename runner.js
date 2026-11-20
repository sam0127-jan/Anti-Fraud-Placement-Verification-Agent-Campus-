import { spawn } from 'child_process';

console.log('[DevRunner] Starting Streamlit Anti-Fraud Placement Verification Agent...');

const streamlit = spawn('streamlit', [
  'run',
  'app.py',
  '--server.port', '3000',
  '--server.address', '0.0.0.0',
  '--server.enableCORS', 'false',
  '--server.enableXsrfProtection', 'false',
  '--server.headless', 'true'
], {
  stdio: 'inherit',
  env: process.env
});

streamlit.on('exit', (code) => {
  console.log(`[DevRunner] Streamlit exited with code ${code}`);
  process.exit(code || 0);
});

process.on('SIGINT', () => streamlit.kill('SIGINT'));
process.on('SIGTERM', () => streamlit.kill('SIGTERM'));
