import {useState} from 'react';
import {functionIcons, functionIconFor} from './functionIcons.mjs';
import {FunctionIcon} from './FunctionIcon';
import './roster-editor.css';

export type Fn={key:number;label:string;momentary:boolean;source:string;confidence:'manual'|'verified';icon?:string};
export type RosterEntry={id:string;name:string;class_name:string;running_number:string;photo?:string;address:number|null;decoder:string;functions:Fn[];sound_profile?:string;notes?:string};

type Props={entry?:RosterEntry;onSave:(state:any)=>void;onClose:()=>void};
export function RosterEditor({entry,onSave,onClose}:Props){
 const current=entry??{id:'',name:'',class_name:'',running_number:'',address:null,decoder:'',functions:[],sound_profile:'',notes:''} as RosterEntry;
 const [draft,setDraft]=useState({...current,functions:current.functions.map(f=>({...f}))});
 const [address,setAddress]=useState(current.address===null?'':String(current.address));
 const [error,setError]=useState('');
 const [image,setImage]=useState<File|null>(null);
 const [saving,setSaving]=useState(false);
 const [created,setCreated]=useState<{id:string;state:any}|null>(null);
 const update=(key:string,value:string)=>setDraft({...draft,[key]:value});
 async function save(){
  if(saving)return;
  if(address.trim()&&(!/^\d+$/.test(address.trim())||Number(address)<1||Number(address)>10239)){setError('Enter a verified DCC address from 1–10239.');return}
  const keys=draft.functions.map(fn=>fn.key);
  if(keys.some(key=>!Number.isInteger(key)||key<0||key>28)||new Set(keys).size!==keys.length||draft.functions.some(fn=>!fn.label.trim()||!fn.source?.trim()||!['manual','verified'].includes(fn.confidence))){setError('Unique F0–F28 slots require a label, source and confidence.');return}
  setSaving(true);setError('');
  try{
   let result=created?.state;
   let savedId=created?.id||entry?.id;
   if(!created){
    const response=await fetch(entry?'/api/roster/'+encodeURIComponent(entry.id):'/api/roster',{method:entry?'PUT':'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...draft,address:address.trim()?Number(address):null})});
    if(response.status===405)throw Error('The railway server has not been updated to add locomotives yet. Your details have not been saved.');
    const body=await response.json();if(!response.ok)throw Error(typeof body.detail==='string'?body.detail:'Could not save locomotive details.');
    result=body;
    savedId=entry?.id||result.roster?.find((item:RosterEntry)=>item.name===draft.name.trim())?.id;
    if(!savedId)throw Error('Details were saved, but the new locomotive could not be found. Refresh the registry before trying again.');
    setCreated({id:savedId,state:result});
   }
   if(image){
    if(!savedId)throw Error('Locomotive details could not be linked to an image. Refresh the registry.');
    if(image.size>8*1024*1024)throw Error('Details saved, but the image exceeds 8 MB. Choose a smaller image.');
    const photo=await fetch('/api/roster/'+encodeURIComponent(savedId)+'/photo',{method:'PUT',headers:{'Content-Type':image.type},body:image});
    if(photo.status===405)throw Error('Details saved, but the railway server has not been updated to add images yet.');
    const body=await photo.json();if(!photo.ok)throw Error('Details saved, but the image could not be added: '+(typeof body.detail==='string'?body.detail:'please try again.'));
    result=body;
   }
   onSave(result);
  }catch(e){setError((e as Error).message)}finally{setSaving(false)}
 }
 return <div className="camera-overlay" role="dialog" aria-modal="true" aria-label={entry?'Edit '+entry.name:'Add locomotive'}><div className="panel camera-dialog roster-dialog"><h2>{entry?'Edit train details':'Add locomotive'}</h2><form onSubmit={e=>{e.preventDefault();save()}}>
 {(['name','class_name','running_number','decoder','sound_profile','notes'] as const).map(key=><label key={key}>{key.replace(/_/g,' ')}{key==='decoder'?' (optional)':''}<input required={key==='name'} value={draft[key]||''} onChange={e=>update(key,e.target.value)}/></label>)}
 <label>Verified DCC address, not the running number<input type="number" min="1" max="10239" value={address} onChange={e=>setAddress(e.target.value)} placeholder="Leave blank until verified"/></label>
 <section className="roster-image-field"><h3>Locomotive image</h3><label>Add locomotive image<input type="file" accept="image/jpeg,image/png,image/webp" onChange={e=>setImage(e.target.files?.[0]||null)}/></label><small>{image?image.name:entry?.photo?'Current image will be kept unless you choose another.':'Optional. Choose a JPEG, PNG or WebP image, up to 8 MB.'}</small></section>
 <section className="function-mapping">
  <div className="function-mapping-heading"><div><span className="eyebrow">DECODER CONTROLS</span><h3>Function mapping</h3></div><span className="function-count">{draft.functions.length} mapped</span></div>
  <p>Only add functions confirmed by an operator or decoder documentation. Icons are visual labels, not decoder settings. Switch track power off before editing.</p>
  <div className="function-edit-list">{draft.functions.map((fn,index)=><div className="function-edit" key={index}>
   <div className="function-edit-head"><span className="function-badge">F{fn.key}</span><strong>{fn.label.trim()||'New function'}</strong><button type="button" className="secondary function-remove" aria-label={'Remove F'+fn.key} onClick={()=>setDraft({...draft,functions:draft.functions.filter((_,i)=>i!==index)})}>Remove</button></div>
   <div className="function-edit-fields">
    <label className="function-number">F number<input type="number" min="0" max="28" value={fn.key} onChange={e=>setDraft({...draft,functions:draft.functions.map((f,i)=>i===index?{...f,key:Number(e.target.value)}:f)})}/></label>
    <label className="function-label">Function label<input required value={fn.label} placeholder="e.g. Whistle" onChange={e=>setDraft({...draft,functions:draft.functions.map((f,i)=>i===index?{...f,label:e.target.value}:f)})}/></label>
    <label className="function-icon-label">Button icon<span className="function-icon-select"><span className="function-icon-preview"><FunctionIcon id={functionIconFor(fn.label,fn.icon)} size={32}/></span><select aria-label={'Icon for F'+fn.key} value={fn.icon||''} onChange={e=>setDraft({...draft,functions:draft.functions.map((f,i)=>i===index?{...f,icon:e.target.value||undefined}:f)})}><option value="">Auto from label</option>{functionIcons.map(([group,options])=><optgroup key={group} label={group}>{options.map(([id,label])=><option key={id} value={id}>{label}</option>)}</optgroup>)}</select></span></label>
    <label className="function-source">Evidence / source<input required maxLength={200} value={fn.source||''} placeholder="Manual page or operator observation" onChange={e=>setDraft({...draft,functions:draft.functions.map((f,i)=>i===index?{...f,source:e.target.value}:f)})}/></label>
    <label className="function-confidence">Confidence<select value={fn.confidence||'manual'} onChange={e=>setDraft({...draft,functions:draft.functions.map((f,i)=>i===index?{...f,confidence:e.target.value as Fn['confidence']}:f)})}><option value="manual">Manual entry</option><option value="verified">Verified</option></select></label>
    <label className="function-momentary"><input type="checkbox" checked={fn.momentary} onChange={e=>setDraft({...draft,functions:draft.functions.map((f,i)=>i===index?{...f,momentary:e.target.checked}:f)})}/><span>Momentary<small>Active only while held</small></span></label>
   </div>
  </div>)}</div>
  <button type="button" className="secondary function-add" onClick={()=>{const used=new Set(draft.functions.map(fn=>fn.key));const next=Array.from({length:29},(_,i)=>i).find(i=>!used.has(i));if(next===undefined){setError('All F0–F28 slots are mapped.');return}setDraft({...draft,functions:[...draft.functions,{key:next,label:'',momentary:false,source:'',confidence:'manual'}]})}}>+ Add function</button>
 </section>
 {error&&<p role="alert">{error}</p>}<div className="photo-actions"><button className="power-btn" disabled={saving}>{saving?'Saving…':created?'Retry image upload':entry?'Save train details':'Add to registry'}</button><button type="button" className="secondary" onClick={()=>{if(created)onSave(created.state);else onClose()}}>{created?'Close':'Cancel'}</button></div></form></div></div>
}
