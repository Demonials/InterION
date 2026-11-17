try:
 from dotenv import load_dotenv
 load_dotenv()
except ImportError:
 pass
import json, os, socket, ipaddress, urllib.error, urllib.request
from pathlib import Path
from typing import Any
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
CLOUD_URL='https://interion-zeta.vercel.app'
_PUBLIC_CONFIG=None
COOKIE='interion_firebase'
COOKIE_SECURE=os.getenv('INTERION_COOKIE_SECURE','false').lower()=='true'
HOST_FILE=Path(os.getenv('INTERION_HOST_FILE','interion_host.json'))
LAN_CIDR=os.getenv('INTERION_LAN_CIDR','').strip()
def public_config():
 global _PUBLIC_CONFIG
 if _PUBLIC_CONFIG is not None:return _PUBLIC_CONFIG
 try:
  req=urllib.request.Request(CLOUD_URL+'/api/config.js',headers={'Accept':'application/json'})
  with urllib.request.urlopen(req,timeout=10) as r:data=json.loads(r.read().decode())
  required=('apiKey','authDomain','projectId','appId')
  if not all(data.get(k) for k in required):raise ValueError('Incomplete Firebase web configuration')
  _PUBLIC_CONFIG={k:data[k] for k in required}
  return _PUBLIC_CONFIG
 except Exception as e:
  raise HTTPException(503,'Could not load InterION configuration from the cloud. Check your internet connection or try again later.') from e

def cloud(path,payload,token=None):
 h={'Content-Type':'application/json'}
 if token: h['Authorization']='Bearer '+token
 req=urllib.request.Request(CLOUD_URL+'/api/'+path,data=json.dumps(payload).encode(),headers=h,method='POST')
 try:
  with urllib.request.urlopen(req,timeout=8) as r:return json.loads(r.read().decode())
 except urllib.error.HTTPError as e:
  try: detail=json.loads(e.read().decode()).get('error','Cloud authorization failed')
  except Exception: detail='Cloud authorization failed'
  raise HTTPException(e.code,detail)
 except Exception: raise HTTPException(503,'InterION Cloud unavailable; online verification is required')
def host_uid():
 try:return json.loads(HOST_FILE.read_text()).get('uid')
 except Exception:return None
def claim_host(uid):
 if not HOST_FILE.exists():HOST_FILE.write_text(json.dumps({'uid':uid},indent=2))
 if host_uid()!=uid:raise HTTPException(403,'This host is registered to another account. Same-account devices only.')
def login_html():
 cfg=json.dumps(public_config())
 body='''<h1>Sign in to InterION</h1><p>Use the same Google account on every device connected to this host.</p><button id="signin">Continue with Google</button><p id="msg"></p><script type="module">
import {initializeApp} from 'https://www.gstatic.com/firebasejs/10.12.2/firebase-app.js';
import {getAuth,GoogleAuthProvider,signInWithPopup} from 'https://www.gstatic.com/firebasejs/10.12.2/firebase-auth.js';
const app=initializeApp(CONFIG);const auth=getAuth(app);document.getElementById('signin').onclick=async()=>{try{const u=await signInWithPopup(auth,new GoogleAuthProvider());const idToken=await u.user.getIdToken(true);const r=await fetch('/auth/firebase',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({idToken})});const d=await r.json();if(!r.ok)throw Error(d.detail||'Sign in failed');location.href=d.redirect||'/';}catch(e){document.getElementById('msg').textContent=e.message;}};
</script>'''.replace('CONFIG',cfg)
 return HTMLResponse('<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>InterION Login</title><style>body{font-family:system-ui;background:#f3f5f7;display:grid;place-items:center;min-height:100vh;margin:0;padding:20px}main{background:white;padding:32px;border-radius:20px;max-width:460px;width:100%}button{background:#15171a;color:white;border:0;border-radius:10px;padding:13px 20px;font-weight:700}</style></head><body><main><b>⚡ INTERION</b>'+body+'</main></body></html>')
def client_is_local(request:Request):
 try:
  remote=ipaddress.ip_address(request.client.host)
  if remote.is_loopback:return True
  if LAN_CIDR:return remote in ipaddress.ip_network(LAN_CIDR,strict=False)
  sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
  try:sock.connect(('8.8.8.8',1));local=ipaddress.ip_address(sock.getsockname()[0])
  finally:sock.close()
  if local.is_private and remote.version==4:return remote in ipaddress.ip_network(str(local)+'/24',strict=False)
  return remote.is_private
 except Exception:return False

def install_access_control(app:FastAPI):
 @app.middleware('http')
 async def gate(request:Request,call_next):
  path=request.url.path
  if path!='/health' and not client_is_local(request):return HTMLResponse('<h2>Local network required</h2><p>Connect to the same local network as the InterION host.</p>',status_code=403)
  if path in {'/login','/auth/firebase','/logout','/health','/favicon.ico'}:return await call_next(request)
  token=request.cookies.get(COOKIE)
  if not token:return RedirectResponse('/login',status_code=303)
  try:
   v=cloud('verify',{},token)
   if v.get('status')!='approved':
    dest='/pending' if v.get('status')=='pending' else '/rejected'
    if path!=dest:return RedirectResponse(dest,status_code=303)
   else:
    claim_host(str(v['uid']));request.state.interion_user=v
  except HTTPException as e:
   if e.status_code in (401,403):
    r=RedirectResponse('/login',status_code=303);r.delete_cookie(COOKIE);return r
   return HTMLResponse('<h2>InterION Cloud unavailable</h2><p>'+e.detail+'</p>',status_code=503)
  return await call_next(request)
 @app.get('/login',response_class=HTMLResponse)
 async def login():return login_html()
 @app.post('/auth/firebase')
 async def firebase_login(request:Request):
  token=str((await request.json()).get('idToken',''))
  if not token:raise HTTPException(400,'Firebase ID token required')
  v=cloud('verify',{},token)
  if v.get('status')=='approved':claim_host(str(v['uid']))
  status=v.get('status','pending');dest='/' if status=='approved' else ('/pending' if status=='pending' else '/rejected')
  r=JSONResponse({'ok':True,'redirect':dest});r.set_cookie(COOKIE,token,max_age=3600,httponly=True,secure=COOKIE_SECURE,samesite='lax');return r
 @app.get('/pending',response_class=HTMLResponse)
 async def pending():return HTMLResponse('<main style="font-family:system-ui;margin:12vh auto;max-width:520px;padding:24px"><h1>Pending for approval</h1><p>The InterION owner must approve your Google account.</p><a href="/logout">Sign out</a></main>')
 @app.get('/rejected',response_class=HTMLResponse)
 async def rejected():return HTMLResponse('<main style="font-family:system-ui;margin:12vh auto;max-width:520px;padding:24px"><h1>Access not approved</h1><p>This account cannot access this host.</p><a href="/logout">Sign out</a></main>')
 @app.get('/logout')
 @app.post('/logout')
 async def logout():
  r=RedirectResponse('/login',status_code=303);r.delete_cookie(COOKIE);return r
 @app.get('/health')
 async def health():return JSONResponse({'status':'ok','auth':'firebase-cloud'})
def log_transfer(request:Request,event:dict[str,Any]):
 token=request.cookies.get(COOKIE,'')
 if token:
  try:cloud('logs',event,token)
  except Exception:pass
