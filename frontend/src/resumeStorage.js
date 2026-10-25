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
 const id=JSON.stringify([file.name,file.size,file.lastModified]);
 return transaction('readwrite',store=>store.put({id,name:file.name,size:file.size,createdAt:new Date().toISOString(),blob:file}));
}
export function listResumes(){return transaction('readonly',store=>store.getAll());}
export function deleteResume(id){return transaction('readwrite',store=>store.delete(id));}
