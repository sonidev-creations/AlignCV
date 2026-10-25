import React, { useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
export default function SystemStatus({requestJSON, compact=false, onClose, strictJSON, setStrictJSON, useRag, setUseRag}){
 const [status,setStatus]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(true),[refresh,setRefresh]=useState(0),[checked,setChecked]=useState(null);
 useEffect(()=>{const controller=new AbortController();let active=true;setBusy(true);setError('');
  const timeout=setTimeout(()=>controller.abort(),12000);
  requestJSON('/api/system-status',{signal:controller.signal}).then(data=>{if(active){setStatus(data);setChecked(new Date())}}).catch(()=>{if(active){setStatus(null);setError('Backend unreachable. Check that the server is running.')}}).finally(()=>{clearTimeout(timeout);if(active)setBusy(false)});
  return()=>{active=false;clearTimeout(timeout);controller.abort()};
 },[refresh,requestJSON]);
 const rows=status?[['Backend API',status.backend],['Groq API',status.groq],['AI model',status.model],['RAG mode',status.retrieval],['Cloudflare artwork',status.cloudflare]]:[];
 const content=<><div className="system-status-heading"><h2>System status</h2><div><button className="icon-btn" aria-label="Refresh status" disabled={busy} onClick={()=>setRefresh(value=>value+1)}><RefreshCw size={15}/></button>{onClose&&<button className="icon-btn" aria-label="Close settings" onClick={onClose}>×</button>}</div></div>{busy?<p role="status">Checking connections...</p>:error?<p className="error-banner" role="alert">{error}</p>:<><dl>{rows.map(([label,value])=><div key={label}><dt>{label}</dt><dd className={value==='Connected'?'system-connected':''}>{value}</dd></div>)}</dl><div className="ai-settings"><label><span><b>Strict JSON validation</b><small>Reject malformed model output and retry safely.</small></span><button className={`switch ${strictJSON?'on':''}`} role="switch" aria-label="Strict JSON validation" aria-checked={strictJSON} onClick={()=>setStrictJSON(!strictJSON)}><i/></button></label><label><span><b>Use retrieval</b><small>Highlight relevant resume passages during analysis.</small></span><button className={`switch ${useRag?"on":""}`} role="switch" aria-label="Use retrieval" aria-checked={useRag} onClick={()=>setUseRag(!useRag)}><i/></button></label></div>{Object.keys(status.limits).length>0&&<><h3>Token limits</h3><dl>{Object.entries(status.limits).map(([label,value])=><div key={label}><dt>{label}</dt><dd>{value.toLocaleString()}</dd></div>)}</dl></>}</>}</>;
 if(compact)return <aside className="system-popover" aria-label="System status">{content}</aside>;
 return <section className="page"><article className="result-card system-status">{content}</article></section>;
}
