import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.jsx';
import './styles.css';
import { listResumes } from './resumeStorage';

// Finish the one-time old-resume cleanup before uploads can be saved.
async function start(){
 try { await listResumes(); } catch { /* The app also works without browser storage. */ }
 createRoot(document.getElementById('root')).render(<React.StrictMode><App /></React.StrictMode>);
}
start();
