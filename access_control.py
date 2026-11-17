try:
 from dotenv import load_dotenv
 load_dotenv()
except ImportError:
 pass
import json, os, socket, ipaddress, urllib.error, urllib.request, secrets, time
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
_AUTH_CHALLENGES={}
AUTH_ORIGIN='https://interion-zeta.vercel.app'
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
 endpoint=path if path.endswith('.js') else path+'.js'
 req=urllib.request.Request(CLOUD_URL+'/api/'+endpoint,data=json.dumps(payload).encode(),headers=h,method='POST')
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
 body='''<h1>Sign in to InterION</h1><p>Google sign-in securely opens on InterION Cloud. No local IP needs to be registered with Firebase.</p><button id="signin">Continue with Google</button><p id="msg"></p><script>
const CLOUD_ORIGIN='https://interion-zeta.vercel.app';
const msg=document.getElementById('msg'),button=document.getElementById('signin');
button.onclick=async()=>{let popup;try{
 const cr=await fetch('/auth/challenge',{method:'POST'});if(!cr.ok)throw Error('Could not start secure sign-in ('+cr.status+')');const {state}=await cr.json();
 const target=location.origin;const url=CLOUD_ORIGIN+'/auth.html?origin='+encodeURIComponent(target)+'&state='+encodeURIComponent(state);
 popup=window.open(url,'interion_google_login','width=520,height=680');
 if(!popup)throw Error('Popup blocked. Allow popups for this local InterION page and try again.');
 msg.textContent='Complete Google sign-in in the popup…';
 const timer=setInterval(()=>{if(popup.closed){clearInterval(timer);if(msg.textContent.startsWith('Complete'))msg.textContent='Sign-in window closed. Please try again.';}},500);
 const handler=async(event)=>{if(event.origin!==CLOUD_ORIGIN||!event.data||event.data.type!=='INTERION_AUTH'||event.data.state!==state)return;window.removeEventListener('message',handler);clearInterval(timer);try{const r=await fetch('/auth/firebase',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({idToken:event.data.idToken,state})});const d=await r.json();if(!r.ok)throw Error(d.detail||'Sign-in failed');location.href=d.redirect||'/';}catch(e){msg.textContent=e.message;}};
 window.addEventListener('message',handler);
 }catch(e){if(popup&&!popup.closed)popup.close();msg.textContent=e.message;}};
</script>'''
 return HTMLResponse('<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>InterION Login</title><style>body{font-family:system-ui;background:#f3f5f7;display:grid;place-items:center;min-height:100vh;margin:0;padding:20px}main{background:white;padding:32px;border-radius:20px;max-width:460px;width:100%}button{background:#15171a;color:white;border:0;border-radius:10px;padding:13px 20px;font-weight:700}#msg{overflow-wrap:anywhere;color:#b42318}</style></head><body><main><b>⚡ INTERION</b>'+body+'</main></body></html>')

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
  if path in {'/login','/auth/challenge','/auth/firebase','/logout','/health','/favicon.ico'}:return await call_next(request)
  token=request.cookies.get(COOKIE)
  if not token:return RedirectResponse('/login',status_code=303)
  try:
   v=cloud('verify',{},token)
   if v.get('status')!='approved':
    dest='/pending' if v.get('status')=='pending' else '/rejected'
    if path!=dest:return RedirectResponse(dest,status_code=303)
   else:
    request.state.interion_user=v
  except HTTPException as e:
   if e.status_code in (401,403):
    r=RedirectResponse('/login',status_code=303);r.delete_cookie(COOKIE);return r
   return HTMLResponse('<h2>InterION Cloud unavailable</h2><p>'+e.detail+'</p>',status_code=503)
  return await call_next(request)
 @app.get('/login',response_class=HTMLResponse)
 async def login():return login_html()
 @app.post('/auth/challenge')
 async def auth_challenge():
  now=time.time()
  for key,expires in list(_AUTH_CHALLENGES.items()):
   if expires<now:_AUTH_CHALLENGES.pop(key,None)
  state=secrets.token_urlsafe(32)
  _AUTH_CHALLENGES[state]=now+300
  return JSONResponse({'state':state,'expiresIn':300})
 @app.post('/auth/firebase')
 async def firebase_login(request:Request):
  body=await request.json()
  token=str(body.get('idToken',''));state=str(body.get('state',''))
  expires=_AUTH_CHALLENGES.pop(state,None) if state else None
  if not expires or expires<time.time():raise HTTPException(400,'Sign-in challenge expired or invalid. Please try again.')
  if not token:raise HTTPException(400,'Firebase ID token required')
  v=cloud('verify',{},token)
  # Approved accounts are isolated by UID in local storage; no single-account host lock.
  status=v.get('status','pending');dest='/' if status=='approved' else ('/pending' if status=='pending' else '/rejected')
  r=JSONResponse({'ok':True,'redirect':dest});r.set_cookie(COOKIE,token,max_age=3600,httponly=True,secure=COOKIE_SECURE,samesite='lax');return r
 @app.get('/pending',response_class=HTMLResponse)
 async def pending():return HTMLResponse('<main style="font-family:system-ui;margin:12vh auto;max-width:520px;padding:24px"><h1>Pending for approval</h1><p>The InterION owner must approve your Google account.</p><a href="/logout">Sign out</a></main>')
 @app.get('/rejected',response_class=HTMLResponse)
 async def rejected():return HTMLResponse('<main style="font-family:system-ui;margin:12vh auto;max-width:520px;padding:24px"><h1>Access not approved</h1><p>This account cannot access this host.</p><a href="/logout">Sign out</a></main>')
 @app.get('/logout')
 @app.post('/logout')
 async def logout():
  r=RedirectResponse('/login',status_code=303)
  r.delete_cookie(COOKIE)
  return r
 @app.get('/health')
 async def health():return JSONResponse({'status':'ok','auth':'firebase-cloud'})
def log_transfer(request:Request,event:dict[str,Any]):
 token=request.cookies.get(COOKIE,'')
 if token:
  try:cloud('logs',event,token)
  except Exception:pass
