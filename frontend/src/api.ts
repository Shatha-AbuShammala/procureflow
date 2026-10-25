export const API_BASE = (import.meta.env.VITE_API_BASE || '/api').replace(/\/$/, '');
export type Session = {access:string;refresh:string};
export class ApiError extends Error { constructor(public status:number, message:string){super(message)} }
let accessToken:string|null=null;
let refreshToken:string|null=null;
export function setSession(s:Session|null){accessToken=s?.access ?? null;refreshToken=s?.refresh ?? null}
export function isSignedIn(){return Boolean(accessToken)}
async function parseResponse(res:Response){const text=await res.text();if(!text)return null;try{return JSON.parse(text)}catch{return text}}
async function send(path:string, init:RequestInit={}, retry=true):Promise<any>{
 const headers:Record<string,string>={...(init.headers as Record<string,string>||{})};
 if(init.body && !(init.body instanceof FormData))headers['Content-Type']='application/json';
 if(accessToken)headers.Authorization=`Bearer ${accessToken}`;
 const res=await fetch(`${API_BASE}${path}`,{...init,headers});
 if(res.status===401 && retry && refreshToken && path!=='/auth/refresh/'){
  const refreshed=await fetch(`${API_BASE}/auth/refresh/`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({refresh:refreshToken})});
  if(refreshed.ok){const data=await refreshed.json();accessToken=data.access;return send(path,init,false)}
  setSession(null);
 }
 const data=await parseResponse(res);
 if(!res.ok){const detail=typeof data==='string'?data:(data?.detail || data?.message || JSON.stringify(data) || 'Request failed');throw new ApiError(res.status,String(detail))}
 return data;
}
export async function login(username:string,password:string):Promise<Session>{const data=await send('/auth/login/',{method:'POST',body:JSON.stringify({username,password})});const s={access:data.access,refresh:data.refresh};setSession(s);return s}
export const api={get:(path:string)=>send(path),post:(path:string,data:unknown)=>send(path,{method:'POST',body:JSON.stringify(data)}),patch:(path:string,data:unknown)=>send(path,{method:'PATCH',body:JSON.stringify(data)}),del:(path:string)=>send(path,{method:'DELETE'})};
export function unpack<T>(data:unknown):T[]{if(Array.isArray(data))return data as T[];if(data && typeof data==='object' && 'results' in data && Array.isArray((data as {results:unknown}).results))return (data as {results:T[]}).results;return []}
