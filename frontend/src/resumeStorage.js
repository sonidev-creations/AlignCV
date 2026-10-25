const DB_NAME = 'aligncv-resumes';
function database() {
 return new Promise((resolve,reject)=>{
  const request=indexedDB.open(DB_NAME,1);
  request.onupgradeneeded=()=>request.result.createObjectStore('files',{keyPath:'id'});
  request.onsuccess=()=>resolve(request.result);
  request.onerror=()=>reject(request.error);
 });
}
async function transaction(mode,operation){
 const db=await database();
 try{return await new Promise((resolve,reject)=>{
  const tx=db.transaction('files',mode);
  const request=operation(tx.objectStore('files'));
  tx.oncomplete=()=>resolve(request.result);
  tx.onerror=()=>reject(tx.error);
  tx.onabort=()=>reject(tx.error||new Error('Resume storage failed.'));
 });}finally{db.close();}
}
export function saveResume(file){
 const id=resumeKey(file);
 return transaction('readwrite',store=>store.put({id,name:file.name,size:file.size,createdAt:new Date().toISOString(),blob:file}));
}
export function resumeKey(file){return JSON.stringify([file.name,file.size,file.lastModified]);}
export function listResumes(){return transaction('readonly',store=>store.getAll());}
export function deleteResume(id){return transaction('readwrite',store=>store.delete(id));}
export function deleteResumesByName(name){
 return transaction('readwrite',store=>{
  const request=store.getAll();
  request.onsuccess=()=>{for(const item of request.result||[])if(item.name===name)store.delete(item.id);};
  return request;
 });
}
