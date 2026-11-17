"""Google authentication and owner-controlled approval for INTERion."""
import html, json, os, secrets, tempfile
from dotenv import load_dotenv

load_dotenv()
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

AUTH_DB=Path(os.getenv("INTERION_AUTH_DB","auth_users.json"))
GOOGLE_CLIENT_ID=os.getenv("GOOGLE_CLIENT_ID","").strip()
ADMIN_EMAIL=os.getenv("INTERION_ADMIN_EMAIL","").strip().casefold()
SESSION_SECRET=os.getenv("INTERION_SESSION_SECRET","").strip()
COOKIE_SECURE=os.getenv("INTERION_COOKIE_SECURE","false").casefold()=="true"
SESSION_MAX_AGE=604800
COOKIE_NAME="interion_session"
NONCE_COOKIE="interion_login_nonce"

def _serializer():
    if len(SESSION_SECRET)<32:
        raise RuntimeError("Set INTERION_SESSION_SECRET to a random secret of at least 32 characters.")
    return URLSafeTimedSerializer(SESSION_SECRET,salt="interion-auth-v1")

def _read_users()->dict[str,dict[str,Any]]:
    if not AUTH_DB.exists(): return {}
    try:
        with AUTH_DB.open("r",encoding="utf-8") as f: data=json.load(f)
        return data if isinstance(data,dict) else {}
    except (OSError,json.JSONDecodeError):
        raise HTTPException(status_code=500,detail="Could not read the access database.")

def _write_users(users):
    AUTH_DB.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix="interion-auth-",suffix=".json",dir=str(AUTH_DB.parent))
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as f: json.dump(users,f,indent=2,ensure_ascii=False)
        os.replace(tmp,AUTH_DB)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)

def _session(request):
    token=request.cookies.get(COOKIE_NAME)
    if not token: return None
    try:
        value=_serializer().loads(token,max_age=SESSION_MAX_AGE)
        return value if isinstance(value,dict) and value.get("sub") else None
    except (BadSignature,SignatureExpired,RuntimeError): return None

def _is_admin(session):
    return bool(ADMIN_EMAIL and session and str(session.get("email","")).casefold()==ADMIN_EMAIL)

def _page(title,body):
    return HTMLResponse(f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)} · INTERion</title><style>
*{{box-sizing:border-box}}body{{margin:0;min-height:100vh;display:grid;place-items:center;padding:24px;font-family:Inter,system-ui,sans-serif;background:#f4f5f7;color:#15171a}}
.panel{{width:min(100%,520px);background:#fff;border:1px solid #e7e8eb;border-radius:22px;padding:34px;box-shadow:0 18px 60px #10182812}}
.brand{{font-weight:800;letter-spacing:-.7px;font-size:19px}}.brand span{{background:#15171a;color:#fff;border-radius:20px;padding:4px 9px;font-size:10px;margin-left:5px}}
h1{{font-size:27px;letter-spacing:-1px;margin:28px 0 9px}}p{{color:#626873;line-height:1.65}}.note{{background:#f5f6f8;border-radius:12px;padding:13px 15px;font-size:13px;color:#525966;margin-top:20px}}
button{{border:0;border-radius:11px;padding:12px 15px;font-size:13px;font-weight:700;cursor:pointer;background:#15171a;color:#fff}}
.status{{display:inline-flex;gap:8px;background:#fff5df;color:#805500;padding:8px 12px;border-radius:30px;font-size:12px;font-weight:700}}
.dot{{width:7px;height:7px;background:#d99a20;border-radius:50%}}small{{color:#8a9099}}table{{width:100%;border-collapse:collapse;margin-top:18px;font-size:13px}}
td,th{{padding:12px 8px;border-bottom:1px solid #eee;text-align:left}}.actions{{display:flex;gap:7px}}.actions button{{padding:9px 10px}}.approve{{background:#16794b}}.reject{{background:#b42318}}#error{{color:#b42318;font-size:13px;min-height:20px}}
</style></head><body><main class="panel"><div class="brand">⚡ INTERion <span>ACCESS</span></div>\${body}</main></body></html>""")

def install_access_control(app:FastAPI):
    @app.middleware("http")
    async def approval_gate(request:Request,call_next):
        path=request.url.path
        if path in {"/login","/auth/google","/pending","/rejected","/logout","/health","/favicon.ico"}:
            return await call_next(request)
        session=_session(request)
        if not session: return RedirectResponse("/login",status_code=303)
        if _is_admin(session): return await call_next(request)
        user=_read_users().get(str(session["sub"]))
        if not user or user.get("status")=="pending": return RedirectResponse("/pending",status_code=303)
        if user.get("status")!="approved": return RedirectResponse("/rejected",status_code=303)
        return await call_next(request)

    @app.get("/login",response_class=HTMLResponse)
    async def login_page():
        nonce=secrets.token_urlsafe(32)
        missing=not GOOGLE_CLIENT_ID or not ADMIN_EMAIL or len(SESSION_SECRET)<32
        note=("Google sign-in setup is incomplete. Configure GOOGLE_CLIENT_ID, INTERION_ADMIN_EMAIL and INTERION_SESSION_SECRET."
              if missing else "New accounts remain locked until the owner approves them.")
        body=f"""<h1>Sign in to INTERion</h1><p>Private file sharing, with access controlled by the owner.</p>
<div id="googleButton"></div><p id="error"></p><div class="note">{html.escape(note)}</div>
<script src="https://accounts.google.com/gsi/client" async defer></script><script>
const nonce={json.dumps(nonce)};
window.handleGoogleCredential=async(response)=>{{const e=document.getElementById('error');e.textContent='Verifying Google account…';
try{{const r=await fetch('/auth/google',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{credential:response.credential,nonce}})}});
const d=await r.json();if(!r.ok)throw new Error(d.detail||'Sign-in failed');location.assign(d.redirect||'/pending');}}
catch(err){{e.textContent=err.message;}}}};
window.addEventListener('load',()=>{{if(!{json.dumps(bool(GOOGLE_CLIENT_ID))})return;
google.accounts.id.initialize({{client_id:{json.dumps(GOOGLE_CLIENT_ID)},callback:window.handleGoogleCredential}});
google.accounts.id.renderButton(document.getElementById('googleButton'),{{theme:'outline',size:'large',shape:'rectangular',width:350,text:'signin_with'}});}});
</script>"""
        response=_page("Sign in",body)
        response.set_cookie(NONCE_COOKIE,nonce,max_age=600,httponly=True,secure=COOKIE_SECURE,samesite="lax")
        return response

    @app.post("/auth/google")
    async def google_login(request:Request):
        if not GOOGLE_CLIENT_ID or not ADMIN_EMAIL: raise HTTPException(503,"Owner has not configured Google sign-in.")
        body=await request.json()
        nonce=str(body.get("nonce","")); cookie_nonce=request.cookies.get(NONCE_COOKIE,"")
        credential=body.get("credential","")
        if not credential or not nonce or not cookie_nonce or not secrets.compare_digest(nonce,cookie_nonce):
            raise HTTPException(400,"Sign-in verification failed. Please try again.")
        try: claims=id_token.verify_oauth2_token(credential,google_requests.Request(),GOOGLE_CLIENT_ID)
        except Exception: raise HTTPException(401,"Google could not verify this sign-in. Please try again.")
        email=str(claims.get("email","")).strip().casefold(); sub=str(claims.get("sub","")).strip()
        if not sub or not email or claims.get("email_verified") is not True:
            raise HTTPException(401,"A verified Google account is required.")
        users=_read_users(); owner=email==ADMIN_EMAIL; previous=users.get(sub,{})
        status="admin" if owner else previous.get("status","pending")
        users[sub]={"sub":sub,"email":email,"name":str(claims.get("name","")),"picture":str(claims.get("picture","")),
                    "status":status,"created_at":previous.get("created_at",datetime.now(timezone.utc).isoformat()),
                    "last_sign_in":datetime.now(timezone.utc).isoformat()}
        _write_users(users)
        response=JSONResponse({"ok":True,"redirect":"/admin" if owner else ("/" if status=="approved" else ("/rejected" if status=="rejected" else "/pending"))})
        response.set_cookie(COOKIE_NAME,_serializer().dumps({"sub":sub,"email":email}),max_age=SESSION_MAX_AGE,
                            httponly=True,secure=COOKIE_SECURE,samesite="lax")
        response.delete_cookie(NONCE_COOKIE)
        return response

    @app.get("/pending",response_class=HTMLResponse)
    async def pending_page(request:Request):
        session=_session(request)
        if not session: return RedirectResponse("/login",status_code=303)
        if _is_admin(session): return RedirectResponse("/admin",status_code=303)
        user=_read_users().get(str(session["sub"]),{})
        if user.get("status")=="approved": return RedirectResponse("/",status_code=303)
        if user.get("status")=="rejected": return RedirectResponse("/rejected",status_code=303)
        name=html.escape(str(user.get("name") or user.get("email") or "there"))
        return _page("Approval pending",f"""<div class="status"><span class="dot"></span>PENDING FOR APPROVAL</div>
<h1>You're on the list, {name}.</h1><p>Your Google account is verified, but this INTERion instance is private.</p>
<p>The owner must approve your account before you can upload, browse or download files.</p>
<div class="note">You can close this page and sign in again later to check your access status.</div>
<form action="/logout" method="post"><button type="submit" style="margin-top:18px">Sign out</button></form>""")

    @app.get("/rejected",response_class=HTMLResponse)
    async def rejected_page():
        return _page("Access not granted",'<h1>Access not granted</h1><p>The owner has not granted access to this account.</p><form action="/logout" method="post"><button>Sign out</button></form>')

    @app.post("/logout")
    async def logout():
        response=RedirectResponse("/login",status_code=303); response.delete_cookie(COOKIE_NAME); response.delete_cookie(NONCE_COOKIE); return response

    @app.get("/admin",response_class=HTMLResponse)
    async def admin_page(request:Request):
        session=_session(request)
        if not _is_admin(session): raise HTTPException(403,"Only the configured owner can manage access.")
        rows=[]
        for sub,user in sorted(_read_users().items(),key=lambda item:item[1].get("created_at","")):
            if user.get("status")=="admin": continue
            email=html.escape(str(user.get("email",""))); name=html.escape(str(user.get("name","")))
            status=html.escape(str(user.get("status","pending"))); safe_sub=html.escape(sub,quote=True)
            actions=""
            if status!="approved": actions+=f'<button class="approve" data-sub="{safe_sub}" data-status="approved" onclick="setAccess(this.dataset.sub,this.dataset.status)">Approve</button>'
            if status!="rejected": actions+=f'<button class="reject" data-sub="{safe_sub}" data-status="rejected" onclick="setAccess(this.dataset.sub,this.dataset.status)">Reject</button>'
            rows.append(f"<tr><td>{name}<br><small>{email}</small></td><td>{status}</td><td><div class='actions'>{actions}</div></td></tr>")
        body=f"""<h1>Access requests</h1><p>Only your configured Google account can approve or reject users.</p>
<table><thead><tr><th>Account</th><th>Status</th><th>Action</th></tr></thead><tbody>{''.join(rows) or '<tr><td colspan="3">No requests yet.</td></tr>'}</tbody></table>
<p id="result"></p><script>async function setAccess(sub,status){{const r=await fetch('/admin/users/'+encodeURIComponent(sub),{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{status}})}});const d=await r.json();if(!r.ok){{document.getElementById('result').textContent=d.detail||'Update failed';return;}}location.reload();}}</script>
<form action="/logout" method="post"><button style="margin-top:18px">Sign out</button></form>"""
        return _page("Owner access panel",body)

    @app.post("/admin/users/{user_sub}")
    async def update_user_access(user_sub:str,request:Request):
        session=_session(request)
        if not _is_admin(session): raise HTTPException(403,"Only the configured owner can manage access.")
        status=(await request.json()).get("status")
        if status not in {"approved","rejected"}: raise HTTPException(400,"Status must be approved or rejected.")
        if user_sub==str(session["sub"]): raise HTTPException(400,"Owner access cannot be changed here.")
        users=_read_users()
        if user_sub not in users: raise HTTPException(404,"User not found.")
        users[user_sub]["status"]=status; users[user_sub]["reviewed_at"]=datetime.now(timezone.utc).isoformat()
        _write_users(users)
        return JSONResponse({"ok":True,"status":status})

    @app.get("/health")
    async def health(): return JSONResponse({"status":"ok"})
