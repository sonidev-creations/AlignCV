import React, { useEffect, useRef, useState } from 'react';
import { saveResume, listResumes, deleteResume, deleteResumesByName, resumeKey } from './resumeStorage';
import SystemStatus from './SystemStatus';
import SkillsVisual, { clearSkillsArtworkCache } from './SkillsVisual';
import logoUrl from './assets/aligncv-logo.png';
import { ContactRound, AlignLeft, ArrowLeft, ArrowRight, ChartPie, BriefcaseBusiness, Check, CheckCircle2, ChevronDown, Clock3, Download, FileCheck2, FileText, History, LoaderCircle, Menu, Paperclip, ScanSearch, Settings, ShieldCheck, Sparkles, Target, Upload, X } from 'lucide-react';

const API = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/+$/, '');
async function requestJSON(path, options) {
 let response;
 try {
  response = await fetch(`${API}${path}`, options);
 } catch (error) {
  if (error.name === 'AbortError') throw error;
  throw new Error(`Could not reach the backend at ${API}. Check that it is running and allows this page's address (${window.location.origin}).`);
 }
 let payload;
 try { payload = await response.json(); }
 catch { throw new Error(`The backend returned an unreadable response (HTTP ${response.status}). Please retry.`); }
 if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail : `Request failed (HTTP ${response.status}). Please retry.`);
 return payload;
}

function readPreference(key) {
 try { return localStorage.getItem(key) !== 'false'; } catch { return true; }
}
function savePreference(key, value) {
 try { localStorage.setItem(key, String(value)); } catch { /* Keep settings in memory when storage is blocked. */ }
}

const focusOptions = ['skills', 'education', 'experience', 'projects', 'contact'];

function Logo(){ return <div className="brand brand-image"><img src={logoUrl} alt="AlignCV" width="2172" height="724" decoding="async"/></div>; }
function Sidebar({page,setPage,onToggleSettings}){
 const links=[['upload','Analyze',ScanSearch],['resumes','Uploaded resumes',FileText],['history','History',History],['metrics','Calculated metrics',ChartPie]];
 return <aside className="sidebar"><Logo/><nav>{links.map(([id,label,Icon])=><button key={id} className={`nav-item ${page===id?'active':''}`} onClick={()=>setPage(id)}><Icon size={18}/><span>{label}</span></button>)}</nav><button className="nav-item settings" onClick={onToggleSettings}><Settings size={18}/><span>Settings</span></button></aside>
}
function Score({value,label,color,caption}){return <div className="score-card"><div className={`ring ${color}`} style={{'--score':`${Math.max(0,Math.min(100,value||0))}%`}}><span>{value ?? '—'}{value!==null&&value!==undefined?'%':''}</span></div><div><b>{label}</b><small>{caption}</small></div></div>}
function ExperienceEntries({value}) {
 const entries=Array.isArray(value)?value:[value];
 return <div className="experience-list">{entries.map((entry,index)=>{
  const parts=String(entry).split(/\s*[\u2022\n]\s*/).filter(Boolean);
  const header=parts.shift()||'';
  const [role,...metadata]=header.split(/\s*\|\s*/);
  return <section className="experience-entry" key={index}><h3>{role}</h3>{metadata.length>0&&<p className="experience-meta">{metadata.join(' | ')}</p>}{parts.length>0&&<ul>{parts.slice(0,2).map((text,i)=><li key={i}>{text}</li>)}</ul>}{parts.length>2&&<details className="experience-more"><summary>Show {parts.length-2} more highlights</summary><ul>{parts.slice(2).map((text,i)=><li key={i}>{text}</li>)}</ul></details>}</section>;
 })}</div>;
}
function SummaryText({result}){
 const bullets=result.summary_style==='bullets'||/^\s*[-•]\s/m.test(result.summary);
 if(!bullets)return <p className="summary-text">{result.summary}</p>;
 const points=result.summary.split(/\n+/).map(text=>text.replace(/^\s*[-•]\s*/, '').trim()).filter(Boolean);
 return <ul className="summary-text summary-bullets">{points.map((point,index)=><li key={index}>{point}</li>)}</ul>;
}
function downloadReport(result){
 const lines=['AlignCV resume analysis report',`Resume: ${result.filename}`,`Generated: ${new Date().toLocaleString()}`,'',`Summary:\n${result.summary}`,'','Extracted details:'];
 for(const [label,field] of Object.entries(result.fields||{})){const value=Array.isArray(field?.value)?field.value.join(', '):(field?.value||'No verified data');lines.push(`${label}: ${value}`,`Evidence: ${field?.evidence?.length?field.evidence.join(' | '):'None'}`)}
 lines.push('','Key findings:',...(result.key_findings||[]).map(item=>`- ${item}`),'','Recommendations:',...(result.improvement_suggestions||[]).map(item=>`- ${item}`));
 if(result.job_match){lines.push('','Job match:',result.job_match.score==null?(result.job_match.note||'No job comparison available.'):`${result.job_match.score}% - ${result.job_match.verdict}`,...(result.job_match.requirements||[]).map(item=>`- ${item.requirement}: ${item.status} (${item.reason})`))}
 const blob=new Blob([lines.join('\n')],{type:'text/plain;charset=utf-8'});const url=URL.createObjectURL(blob);const anchor=document.createElement('a');anchor.href=url;anchor.download=`AlignCV-${(result.filename||'report').replace(/[^a-z0-9._-]+/gi,'_')}.txt`;document.body.appendChild(anchor);anchor.click();anchor.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
function FieldCard({title,field}){
 const [open,setOpen]=useState(false); const val=field?.value; const missing=val===null||val===undefined||val===''||(Array.isArray(val)&&!val.length);
 return <article className="field-card"><button className="field-head" onClick={()=>setOpen(!open)} aria-expanded={open}><span><i className={`status-dot ${field?.status==='uncertain'?'warn':missing?'muted':field.status==='supported'?'good':'warn'}`}></i><b>{title}</b></span><span className={`badge ${field?.status==='uncertain'?'badge-warn':missing?'badge-muted':field.status==='supported'?'badge-good':'badge-warn'}`}>{field?.status==='uncertain'?'Needs review':missing?'Missing':field.status==='supported'?'Evidence found':'Check this'}<ChevronDown size={14}/></span></button>{!missing&&<div className="field-value">{title==='Experience'?<ExperienceEntries value={val}/>:Array.isArray(val)?<div className="chips">{val.map((x,i)=><span className="chip" key={i}>{x}</span>)}</div>:<p>{val}</p>}</div>}{missing&&<p className={`field-empty ${field?.status==='uncertain'?'needs-review':''}`}>{field?.status==='uncertain'?`${title} could not be verified. Review the original resume.`:`No ${title.toLowerCase()} data was extracted from this resume.`}</p>}{open&&<div className="evidence-box"><strong><ShieldCheck size={14}/> Source evidence</strong>{field?.evidence?.length?field.evidence.map((q,i)=><blockquote key={i}>“{q}”</blockquote>):<p>No exact source excerpt could be verified. Review this detail in the original document.</p>}</div>}</article>
}
function CompletenessFeedback({result}){
 const labels={name:'Name',email:'Email address',skills:'Skills',education:'Education',experience:'Work experience'};
 const checks=result.completeness?.checks||Object.entries(labels).map(([key,label])=>{
  const field=result.fields[key];const values=Array.isArray(field?.value)?field.value:[field?.value];const present=values.some(value=>typeof value==='string'&&value.trim());
  const status=present&&field?.status==='supported'?'supported':field?.status==='uncertain'||present?'uncertain':'missing';
  return {field:key,label,status,message:status==='supported'?`${label} found with source evidence.`:status==='uncertain'?`${label} could not be verified. Review the original resume.`:`No ${label.toLowerCase()} data was extracted from this resume.`};
 });
 const found=checks.filter(check=>check.status==='supported').length;
 return <article className="result-card completeness-feedback"><div className="card-heading"><span className="icon-tile teal-tile"><FileCheck2 size={18}/></span><div><h2>Completeness check</h2><small>{found} of {checks.length} required fields verified</small></div></div><div className="completeness-checks">{checks.map(check=><div className={`completeness-check ${check.status}`} key={check.field}><div><b>{check.label}</b><span className={`badge ${check.status==='supported'?'badge-good':check.status==='uncertain'?'badge-warn':'badge-muted'}`}>{check.status==='supported'?'Found':check.status==='uncertain'?'Needs review':'Missing'}</span></div></div>)}</div></article>;
}
function AtsReadability({review}){
 return <article className="result-card tab-card"><div className="card-heading"><span className="icon-tile teal-tile"><FileCheck2 size={18}/></span><div><h2>ATS readability</h2></div></div>{review?<><div className="ats-status"><b>{review.status}</b><span>{review.passed} of {review.total} basic checks passed</span></div><div className="ats-checks">{review.checks.map((check,index)=><div className="ats-check" key={index}>{check.status==='pass'?<CheckCircle2 size={19}/>:<ScanSearch size={19}/>}<div><b>{check.label}</b></div><span className={`chip ${check.status==='pass'?'good-chip':'warn-chip'}`}>{check.status==='pass'?'Passed':'Review'}</span></div>)}</div></>:<p>Run a new analysis from the Analyze page to check this resume.</p>}</article>;
}
function NextSteps({items}) {
 if(!items?.length)return null;
 return <article className="result-card next-steps"><div className="card-heading"><span className="icon-tile blue-tile"><BriefcaseBusiness size={18}/></span><div><h2>Your next steps</h2><small>Practical ways to strengthen your resume</small></div></div><ol>{items.map((item,index)=><li key={index}>{item}</li>)}</ol></article>;
}
function CalculatedMetrics(){
 const metrics=[
  ['Completeness', ['20% per verified field; missing or uncertain = 0.']],
  ['Summary evidence', ['Summary words matching verified quotes; not factual accuracy.']],
  ['Job match', ['Weighted JD evidence: met 100%, partial 40%, missing 0%; essential gaps cap scores. Not an ATS score.']],
  ['Skills', ['Select a category to explore its skills; AI artwork illustrates category themes.']],
  ['ATS readability', ['Checks readable text, contact details and section headings.']]
 ];
 return <section className="page metrics-page"><div className="history-heading"><h1>Calculated metrics</h1></div><div className="metrics-grid">{metrics.map(([title,points])=><article className="result-card" key={title}><h2>{title}</h2><ul>{points.map(point=><li key={point}>{point}</li>)}</ul></article>)}</div></section>;
}
const HISTORY_KEY='aligncv.report-history.v1';
function readHistory(){
 try{const saved=JSON.parse(localStorage.getItem(HISTORY_KEY)||'[]');return Array.isArray(saved)?saved.filter(item=>typeof item?.id==='string'&&typeof item?.createdAt==='string'&&typeof item?.report?.filename==='string'&&item.report.fields&&typeof item.report.summary==='string').slice(0,20):[]}catch{return []}
}
function ResumePreview({resume,onClose}){
 const [url,setUrl]=useState('');
 const [text,setText]=useState('');
 useEffect(()=>{
  const objectUrl=URL.createObjectURL(resume.blob);setUrl(objectUrl);
  let active=true;
  if(!/\.pdf$/i.test(resume.name))resume.blob.text().then(value=>{if(active)setText(value)});
  return()=>{active=false;URL.revokeObjectURL(objectUrl)};
 },[resume]);
 return <div className="resume-preview"><div className="resume-preview-heading"><h2>{resume.name}</h2><div className="resume-preview-actions"><a className="button secondary" href={url} download={resume.name}>Download</a><button className="button secondary" onClick={onClose}>Close</button></div></div>{/\.pdf$/i.test(resume.name)?<object data={url} type="application/pdf" className="resume-pdf" aria-label={`Preview of ${resume.name}`}><p>Preview unavailable. <a href={url} target="_blank" rel="noreferrer">Open PDF</a></p></object>:<pre className="resume-text">{text}</pre>}</div>;
}
function UploadedResumes(){
 const [items,setItems]=useState([]),[selected,setSelected]=useState(null),[error,setError]=useState(''),[loading,setLoading]=useState(true);
 useEffect(()=>{let active=true;listResumes().then(files=>{if(active){setItems(files.sort((a,b)=>b.createdAt.localeCompare(a.createdAt)))}}).catch(()=>{if(active)setError('Could not load saved resumes. Allow browser storage and try again.')}).finally(()=>{if(active)setLoading(false)});return()=>{active=false}},[]);
 const remove=async item=>{try{await deleteResume(item.id);const remaining=items.filter(x=>x.id!==item.id);setItems(remaining);if(selected?.id===item.id)setSelected(null)}catch{setError('Could not delete this resume. Please try again.')}};
 return <section className="page history-page"><div className="history-heading"><div><h1>Uploaded resumes</h1></div></div>{error&&<p className="error-banner" role="alert">{error}</p>}{loading?<p role="status">Loading resumes...</p>:items.length?<><div className="history-list">{items.map(item=><article className="result-card history-item" key={item.id}><FileText size={22}/><div className="history-info"><h2>{item.name}</h2><p>{Math.round(item.size/1024)} KB</p></div><div className="history-actions"><button className="button secondary" aria-pressed={selected?.id===item.id} onClick={()=>setSelected(item)}>View resume</button><button className="button secondary" onClick={()=>remove(item)} aria-label={`Delete resume ${item.name}`}>Delete</button></div></article>)}</div>{selected&&<ResumePreview key={selected.id} resume={selected} onClose={()=>setSelected(null)}/>}</>:<div className="result-card history-empty"><FileText size={28}/><h2>No resumes saved yet</h2><p>Upload a resume to preview it here. Older analyses are available in History.</p></div>}</section>;
}
function ReportHistory({items,onOpen,onDelete,notice}){
 return <section className="page history-page"><div className="history-heading"><div><h1>Analysis history</h1></div></div>{notice&&<p role="status" className="error-banner">{notice}</p>}{items.length?<div className="history-list">{items.map(item=><article className="result-card history-item" key={item.id}><span className="icon-tile blue-tile"><FileText size={20}/></span><div className="history-info"><h2>{item.report.filename}</h2><p><time dateTime={item.createdAt}>{new Date(item.createdAt).toLocaleString()}</time></p><small>{Array.isArray(item.report.fields.skills?.value)?item.report.fields.skills.value.length:0} skills{item.report.completeness?.score!=null?` / ${item.report.completeness.score}% complete`:''}</small></div><div className="history-actions"><button className="button secondary" onClick={()=>onOpen(item)}>View report <ArrowRight size={15}/></button><button className="button secondary" onClick={()=>onDelete(item.id)} aria-label={`Delete saved report for ${item.report.filename}`}>Delete</button></div></article>)}</div>:<div className="result-card history-empty"><History size={28}/><h2>No saved analyses yet</h2><p>Analyze a resume to see its report here.</p></div>}</section>;
}
function App(){
 const [history,setHistory]=useState(readHistory);
 const [historyNotice,setHistoryNotice]=useState('');
 const updateHistory=items=>{setHistory(items);try{localStorage.setItem(HISTORY_KEY,JSON.stringify(items));setHistoryNotice('')}catch{setHistoryNotice('Browser storage is unavailable or full. Changes are kept only until this page closes.')}};
 useEffect(()=>{const sync=e=>{if(e.key===HISTORY_KEY||e.key===null)setHistory(readHistory())};window.addEventListener('storage',sync);return()=>window.removeEventListener('storage',sync)},[]);
 const openSaved=item=>{if(window.history.state?.aligncvPage!=='report')window.history.pushState({aligncvPage:'report'},'',window.location.href);setResult(item.report);setActiveTab('Overview');setPage('report')};

 const [page,setPage]=useState('upload'),[strictJSON,setStrictJSON]=useState(()=>readPreference('aligncv.strict-json')),[file,setFile]=useState(null),[summaryStyle,setSummaryStyle]=useState('brief'),[level,setLevel]=useState('standard'),[focus,setFocus]=useState([]),[optionsOpen,setOptionsOpen]=useState(false),[jobOpen,setJobOpen]=useState(false),[job,setJob]=useState(''),[useRag,setUseRag]=useState(true),[drag,setDrag]=useState(false),[error,setError]=useState(''),[result,setResult]=useState(null),[activeTab,setActiveTab]=useState('Overview'),[busy,setBusy]=useState(false),[mobileMenu,setMobileMenu]=useState(false),[sampleList,setSampleList]=useState([]),[samplesOpen,setSamplesOpen]=useState(false);
 const inputRef=useRef(null);
 useEffect(()=>{if(!window.history.state?.aligncvPage)window.history.replaceState({aligncvPage:'upload'},'',window.location.href);const onPop=()=>setPage(window.history.state?.aligncvPage||'upload');window.addEventListener('popstate',onPop);return()=>window.removeEventListener('popstate',onPop)},[]);
 useEffect(()=>{const controller=new AbortController();requestJSON('/api/samples',{signal:controller.signal}).then(setSampleList).catch(()=>{});return ()=>controller.abort()},[]);
 const pickFile=f=>{if(!f)return;setError('');if(!['application/pdf','text/plain'].includes(f.type)&&!/\.(pdf|txt)$/i.test(f.name)){setError('Please choose a PDF or TXT resume.');return}if(f.size>5*1024*1024){setError('Maximum file size is 5 MB.');return}if(!file||resumeKey(file)!==resumeKey(f)){setJob('');setJobOpen(false)}setFile(f);setResult(null);saveResume(f).catch(()=>setError('Resume selected, but browser storage is unavailable. Its preview will not be saved.'))};
 const loadSample=async name=>{if(!name){setSamplesOpen(!samplesOpen);if(!sampleList.length){try{const samples=await requestJSON('/api/samples');setSampleList(samples);setSamplesOpen(true)}catch{setError('Could not load samples. Make sure the backend is running.')}}return}try{const sample=await requestJSON(`/api/samples/${encodeURIComponent(name)}`);pickFile(new File([Uint8Array.from(atob(sample.content_base64),char=>char.charCodeAt(0))],sample.name,{type:sample.media_type}));setSamplesOpen(false)}catch(e){setError(e.message)}};
 const loadSampleJob=async()=>{try{const sample=await requestJSON('/api/sample-job-description');setJob(sample.text);setJobOpen(true);setError('')}catch(e){setError(e.message)}};
 const analyze=async()=>{if(busy)return;if(!file){setError('Upload a resume or choose a sample first.');return}const analysisFile=file;const analysisJob=job.trim();setError('');setBusy(true);setPage('loading');try{const data=new FormData();data.append('file',analysisFile);data.append('summary_style',summaryStyle);data.append('analysis_level',level);data.append('focus_areas',JSON.stringify(focus.length?focus:focusOptions));data.append('job_description',analysisJob);data.append('use_rag',String(useRag));data.append('strict_json',String(strictJSON));const payload=await requestJSON('/api/analyze',{method:'POST',body:data});setResult(payload);updateHistory([{id:crypto.randomUUID(),resumeId:resumeKey(analysisFile),createdAt:new Date().toISOString(),report:payload},...history].slice(0,20));setFile(null);setJob('');setJobOpen(false);setActiveTab('Overview');window.history.pushState({aligncvPage:'report'},'',window.location.href);setPage('report')}catch(e){setError(e.message||'Could not analyze this resume.');setPage('upload')}finally{setBusy(false)}};
 const deleteHistoryItem=async id=>{const item=history.find(entry=>entry.id===id);try{if(item?.resumeId)await deleteResume(item.resumeId);else if(item?.report?.filename)await deleteResumesByName(item.report.filename);clearSkillsArtworkCache();if(result?.filename===item?.report?.filename){setResult(null);setPage('history')}}catch{setHistoryNotice('Report deleted, but its saved resume could not be cleared. Open Uploaded resumes and remove it there.')}updateHistory(history.filter(entry=>entry.id!==id))};
 const skillList=result?.skills_visual||[];
 const navPage=id=>{if(window.history.state?.aligncvPage!==id)window.history.pushState({aligncvPage:id},'',window.location.href);setPage(id);setMobileMenu(false)};
 return <div className="app-shell"><Sidebar page={page} setPage={navPage} onToggleSettings={()=>navPage('settings')}/><div className="mobile-header"><button className="icon-btn" aria-label="Toggle navigation" aria-expanded={mobileMenu} onClick={()=>setMobileMenu(!mobileMenu)}><Menu size={20}/></button><Logo/><button className="icon-btn" aria-label="Uploaded resumes" onClick={()=>navPage('resumes')}><FileText size={19}/></button></div>{mobileMenu&&<div className="mobile-menu">{[['upload','Analyze'],['resumes','Uploaded resumes'],['history','History'],['metrics','Calculated metrics'],['settings','Settings']].map(([id,label])=><button key={id} onClick={()=>navPage(id)}>{label}</button>)}</div>}
 <main className="main">
 {page==='upload'&&<section className="page upload-page"><div className="page-intro"><div><h1>Make your resume stand out.</h1><p>Evidence-backed insights, made simple.</p></div></div>
 <div className="upload-grid"><div className="main-column"><div className={`dropzone ${drag?'dragging':''}`} onDragOver={e=>{e.preventDefault();setDrag(true)}} onDragLeave={()=>setDrag(false)} onDrop={e=>{e.preventDefault();setDrag(false);pickFile(e.dataTransfer.files?.[0])}}><div className="upload-icon"><Upload size={26}/></div><h2>{file?'Resume ready to analyze':'Drop a resume to begin'}</h2><p>PDF or TXT · Up to 5 MB</p><button className="button secondary" onClick={()=>inputRef.current?.click()}><Paperclip size={16}/> Choose file</button><input ref={inputRef} type="file" accept=".pdf,.txt,application/pdf,text/plain" hidden onChange={e=>pickFile(e.target.files?.[0])}/><button className="link-button" onClick={()=>loadSample(null)}>{samplesOpen?'Close sample resumes':'Use a sample resume'} <ArrowRight size={14}/></button>{samplesOpen&&<div className="sample-options">{sampleList.map(s=><button key={s.name} onClick={()=>loadSample(s.name)}>{s.label}</button>)}</div>}</div>
 {file&&<div className="uploaded-card"><div className="section-label"><FileText size={17}/> Uploaded resume</div><div className="file-row"><div className="pdf-icon"><FileText size={19}/></div><div className="file-info"><b>{file.name}</b><small>{(file.size/1024).toFixed(0)} KB · Ready for analysis</small></div><button className="icon-btn remove" aria-label="Remove file" onClick={()=>setFile(null)}><X size={17}/></button></div></div>}
 <div className="job-card"><button className="accordion-title" onClick={()=>setJobOpen(!jobOpen)}><span><BriefcaseBusiness size={17}/><span><b>Target job description</b></span></span><ChevronDown size={17} className={jobOpen?'rotate':''}/></button>{jobOpen&&<div className="accordion-content"><label htmlFor="job-description">Paste the job description</label><button className="link-button" onClick={loadSampleJob}>Use sample job description <ArrowRight size={14}/></button><textarea id="job-description" value={job} onChange={e=>setJob(e.target.value.slice(0,12000))} placeholder="Example: Paste a software developer job description here…" rows="5"/></div>}</div>
 <div className="options-card"><button className="accordion-title" onClick={()=>setOptionsOpen(!optionsOpen)}><span><AlignLeft size={17}/><span><b>Analysis options</b></span></span><ChevronDown size={17} className={optionsOpen?'rotate':''}/></button>{optionsOpen&&<div className="accordion-content options-content"><div className="control-row"><label>Summary style</label><div className="segmented">{[['brief','Brief'],['detailed','Detailed'],['bullets','Bullets']].map(([v,l])=><button key={v} onClick={()=>setSummaryStyle(v)} className={summaryStyle===v?'selected':''}>{l}</button>)}</div></div><div className="control-row"><label>Analysis depth</label><div className="segmented">{[['basic','Basic'],['standard','Standard'],['detailed','Detailed']].map(([v,l])=><button key={v} onClick={()=>setLevel(v)} className={level===v?'selected':''}>{l}</button>)}</div></div><div className="focus-control"><div><b>Focus areas</b></div><div className="chips">{focusOptions.map(x=><button className={`chip selectable ${focus.includes(x)?'on':''}`} key={x} onClick={()=>setFocus(focus.includes(x)?focus.filter(y=>y!==x):[...focus,x])}>{focus.includes(x)&&<Check size={12}/>} {x[0].toUpperCase()+x.slice(1)}</button>)}</div></div></div>}</div>
 <button className="button primary analyze-button" onClick={analyze} disabled={busy||!file}><Sparkles size={17}/> Analyze resume <ArrowRight size={17}/></button>{error&&<div className="error-banner" role="alert">{error}</div>}
 </div></div></section>}
 {page==='loading'&&<section className="page loading-page"><button className="back-link" onClick={()=>navPage('upload')}><ArrowLeft size={16}/> Back to upload</button><div className="loading-card"><div className="stepper"><div className="step done"><i><Check size={14}/></i><span>Upload</span></div><div className="step-line active"/><div className="step active"><i>2</i><span>Analyze</span></div><div className="step-line"/><div className="step"><i>3</i><span>Report</span></div></div><div className="progress-ring"><LoaderCircle size={64}/><Sparkles size={22}/></div><h1>Analyzing your resume…</h1><p>Finding evidence and checking details.</p><div className="progress-list"><div className="progress-item done"><CheckCircle2 size={17}/><span><b>Extracting document text</b><small>Reading {file?.name||'your resume'}</small></span></div><div className="progress-item active"><LoaderCircle size={17}/><span><b>Retrieving relevant evidence</b><small>{useRag?'Matching resume passages to analysis fields':'Preparing full-document analysis'}</small></span></div><div className="progress-item"><Clock3 size={17}/><span><b>Validating the report</b><small>Checking extracted details and missing fields</small></span></div></div><div className="loading-tip"><ShieldCheck size={15}/> Your report will be based on the uploaded document.</div></div></section>}
 {page==='report'&&result&&<section className="page report-page">{historyNotice&&<p role="status" className="error-banner">{historyNotice}</p>}<div className="report-top"><div className="report-heading"><div><div className="eyebrow">ANALYSIS REPORT</div><h1>Your resume report</h1><p><FileText size={15}/> {result.filename}</p></div><button className="button secondary" onClick={()=>downloadReport(result)}><Download size={16}/> Download report</button></div></div>
 <div className="score-grid"><Score value={result.grounding?.score} label="Summary evidence" color="blue" caption="Word overlap with verified resume excerpts"/><Score value={result.completeness?.score} label="Resume completeness" color="green" caption={`${result.completeness?.supported_fields||0} of ${result.completeness?.total_fields||5} key fields verified`}/>{result.job_match&&<Score value={result.job_match.score} label="Job match estimate" color="violet" caption="Evidence against job requirements"/>}</div>
 <div className="report-tabs" role="group" aria-label="Report sections">{['Overview','Extracted details','Job match','Skills','ATS readability','Recommendations'].map(t=><button key={t} onClick={()=>setActiveTab(t)} aria-pressed={activeTab===t} className={activeTab===t?'tab-active':''}>{t}</button>)}</div>
 {activeTab==='Overview'&&<div className="results-grid"><div className="result-main"><CompletenessFeedback result={result}/><article className="result-card summary-card"><div className="card-heading"><span className="icon-tile blue-tile"><Sparkles size={18}/></span><div><h2>Your profile at a glance</h2></div></div><SummaryText result={result}/></article></div></div>}
 {activeTab==='Extracted details'&&<article className="result-card tab-card"><div className="card-heading"><span className="icon-tile teal-tile"><ContactRound size={18}/></span><div><h2>Extracted resume details</h2><small>Your extracted information, with supporting resume excerpts.</small></div></div><div className="fields-list">{['name','email','skills','education','experience'].map(k=><FieldCard key={k} title={k[0].toUpperCase()+k.slice(1)} field={result.fields[k]}/>)}</div>{result.key_findings?.length>0&&<><h3 className="subheading">What stands out</h3><ul className="findings">{result.key_findings.map((x,i)=><li key={i}><CheckCircle2 size={15}/>{x}</li>)}</ul></>}</article>}
 {activeTab==='Recommendations'&&(result.improvement_suggestions?.length?<NextSteps items={result.improvement_suggestions}/>:<article className="result-card tab-card"><h2>Recommendations</h2><p>No recommendations were returned for this resume.</p></article>)}
 {activeTab==='Job match'&&<article className="result-card tab-card"><div className="card-heading"><span className="icon-tile violet-tile"><Target size={18}/></span><h2>Job description comparison</h2></div>{result.job_match?.requirements?.length?<><div className="match-score"><strong>{result.job_match.score}%</strong><span>{result.job_match.verdict}</span></div><p className="match-method">{result.job_match.note}</p><div className="job-category-grid">{result.job_match.categories.map(c=><div className="job-category" key={c.category}><span>{c.category}</span><b>{c.score}%</b></div>)}</div><div className="job-requirements">{result.job_match.requirements.map((r,i)=><div className="job-requirement" key={i}><div><b>{r.requirement}</b><span className={`chip ${r.status==='met'?'good-chip':'warn-chip'}`}>{r.status==='met'?'Met':r.status==='partial'?'Partial':'Missing'}{r.essential?' / Essential':''}</span></div><p>{r.reason}</p><details><summary>View evidence</summary><blockquote>JD: {r.jd_evidence}</blockquote>{r.evidence.map((q,j)=><blockquote key={j}>Resume: {q}</blockquote>)}</details></div>)}</div></>:<p>{result.job_match?.note||'Paste a job description to compare this resume against its requirements.'}</p>}</article>}
 {activeTab==='ATS readability'&&<AtsReadability review={result.ats_readability}/>}
 {activeTab==='Skills'&&<SkillsVisual key={result.filename+result.analysis_seconds} items={skillList} requestJSON={requestJSON}/>}
 </section>}

 {page==='metrics'&&<CalculatedMetrics/>}
 {page==='settings'&&<SystemStatus requestJSON={requestJSON} strictJSON={strictJSON} setStrictJSON={value=>{setStrictJSON(value);savePreference("aligncv.strict-json",value)}} useRag={useRag} setUseRag={setUseRag}/>}
 {page==='resumes'&&<UploadedResumes/>}
 {page==='history'&&<ReportHistory items={history} onOpen={openSaved} onDelete={deleteHistoryItem} notice={historyNotice}/>}

 </main><footer className="mobile-bottom"><button onClick={()=>navPage('upload')} className={page==='upload'?'active':''}><ScanSearch size={17}/>Analyze</button><button onClick={()=>navPage('resumes')} className={page==='resumes'?'active':''}><FileText size={17}/>Resumes</button><button onClick={()=>navPage('history')} className={page==='history'?'active':''}><History size={17}/>History</button><button onClick={()=>navPage('metrics')} className={page==='metrics'?'active':''}><ChartPie size={17}/>Metrics</button></footer></div>
}

export default App;
