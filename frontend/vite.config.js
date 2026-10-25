import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig(({ command, mode }) => {
 const env = loadEnv(mode, process.cwd(), 'VITE_');
 if (command === 'build') {
  let api;
  try { api = new URL(env.VITE_API_URL); } catch { throw new Error('Set VITE_API_URL to the backend HTTPS URL before building.'); }
  const local = ['localhost', '127.0.0.1', '[::1]'].includes(api.hostname);
  if ((api.protocol !== 'https:' && !(local && api.protocol === 'http:')) || api.pathname !== '/' || api.search || api.hash || api.username || api.password) {
   throw new Error('VITE_API_URL must be an HTTPS origin without a path (for example https://aligncv-api.onrender.com).');
  }
 }
 return { plugins: [react()], server: { host: '0.0.0.0' } };
});
