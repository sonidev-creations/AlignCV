import React, { useRef, useState } from 'react';
import { ArrowUpRight, Download, LoaderCircle, Sparkles, Layers3 } from 'lucide-react';

const colors=['#38d5b4','#728cff','#bd9bff','#69c4ed','#f1bc73','#a5b4c9'];
const artworkCache=new Map();
export function clearSkillsArtworkCache(){artworkCache.clear();}
const label=category=>category==='Other'?'Additional skills':category;
export default function SkillsVisual({items,requestJSON,visualGeneration=true}){
 const [selected,setSelected]=useState(null),[artwork,setArtwork]=useState(null),[mode,setMode]=useState('map'),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const inFlight=useRef(false);
 const categories=items.filter(item=>item.count>0);
 const active=categories.find(item=>item.category===selected)||categories[0];
 const total=categories.reduce((sum,item)=>sum+item.count,0);
 if(!total)return <p className="muted-text">No verified skills found.</p>;
 const key=categories.map(item=>item.category).sort().join('|');
 const generate=async()=>{
  if(inFlight.current)return;
  const cached=artworkCache.get(key);
  if(cached){setArtwork(cached);setMode('art');setError('');return;}
  inFlight.current=true;setBusy(true);setError('');
  try{
   const result=await requestJSON('/api/skills-image',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({categories:categories.map(({category,count})=>({category,count}))})});
   if(!/^data:image\/jpeg;base64,/.test(result.image_url))throw new Error('Could not load the visual. Try again.');
   if(artworkCache.size>=8)artworkCache.delete(artworkCache.keys().next().value);
   artworkCache.set(key,result);setArtwork(result);setMode('art');
  }catch(e){setError(e.message)}finally{inFlight.current=false;setBusy(false)}
 };
 let offset=0;
 return <section className="skill-explorer">
  <div className="skill-explorer-header"><div><span className="skill-kicker">CAPABILITIES</span><h2>Skills explorer <span>{total} skills</span></h2></div></div>
  <div className="skill-explorer-body"><div className="skill-visual-panel">
   <div className="skill-visual-toolbar"><span><Layers3 size={13}/> {mode==='art'?'AI illustration':'Category map'}</span>{artwork&&<button onClick={()=>setMode(mode==='map'?'art':'map')}>{mode==='map'?'AI visual':'Show map'}<ArrowUpRight size={13}/></button>}</div>
   {mode==='art'&&artwork?<div className="skill-art"><img src={artwork.image_url} alt={artwork.alt}/><span>AI illustration - category themes</span><a href={artwork.image_url} download="aligncv-skills-visual.jpg" aria-label="Download AI visual"><Download size={15}/></a></div>:<svg className="skill-orbit" viewBox="0 0 280 270" role="group" aria-label="Select a skill category"><circle cx="140" cy="132" r="88" fill="none" stroke="#22334e" strokeWidth="22"/>{categories.map((item,index)=>{
    const length=item.count/total*100;
    const start=offset;offset+=length;
    return <circle key={item.category} cx="140" cy="132" r="88" pathLength="100" fill="none" stroke={colors[index%colors.length]} strokeWidth={active.category===item.category?27:20} strokeDasharray={`${Math.max(0.1,length-1.3)} ${100-Math.max(0.1,length-1.3)}`} strokeDashoffset={-start} transform="rotate(-90 140 132)" className="skill-orbit-segment" role="button" tabIndex={0} aria-label={`${label(item.category)}, ${item.count} skills`} aria-pressed={active.category===item.category} onClick={()=>setSelected(item.category)} onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();setSelected(item.category)}}}><title>{label(item.category)}: {item.count} skills</title></circle>;
   })}<text x="140" y="128" textAnchor="middle" fill="white" fontSize="40" fontWeight="700">{active.count}</text><text x="140" y="151" textAnchor="middle" fill="#a7b9d4" fontSize="12">{label(active.category)}</text><text x="140" y="252" textAnchor="middle" fill="#a7b9d4" fontSize="10">{categories.length} categories - select to explore</text></svg>}
  </div><div className="skill-details-panel"><div className="skill-category-switches" role="group" aria-label="Skill categories">{categories.map((item,index)=><button key={item.category} className={active.category===item.category?'selected':''} aria-pressed={active.category===item.category} onClick={()=>setSelected(item.category)}><i style={{background:colors[index%colors.length]}}/><span>{label(item.category)}</span><b>{item.count}</b></button>)}</div><div className="skill-selection" aria-live="polite"><div><h3>{label(active.category)}</h3><span>{active.count} skills</span></div>{active.skills?.length?<div className="skill-tags">{active.skills.map(skill=><span key={skill}>{skill}</span>)}</div>:<p className="helper">Analyze again to load skill names for this report.</p>}</div></div></div>
  {error&&<p className="skill-visual-error" role="alert">{error}</p>}
 </section>;
}
