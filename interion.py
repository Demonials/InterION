# interion.py
import os
import json
import socket
import qrcode
import hashlib
from datetime import datetime
from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, StreamingResponse
import uvicorn
from typing import Optional
import aiofiles

# Configuration
UPLOAD_FOLDER = "shared_files"
METADATA_FILE = "file_metadata.json"
PORT = 8000

# Create folder
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Load metadata
if os.path.exists(METADATA_FILE):
    with open(METADATA_FILE, 'r') as f:
        file_metadata = json.load(f)
else:
    file_metadata = {}

app = FastAPI(title="INTERion File Share", version="1.0")

from access_control import install_access_control, log_transfer
install_access_control(app)

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 1))
        ip = s.getsockname()[0]
    except:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

def format_size(size):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"

@app.get("/", response_class=HTMLResponse)
async def home():
    ip = get_local_ip()
    url = f"http://{ip}:{PORT}"
    
    # Calculate stats
    total_size = sum(meta['size'] for meta in file_metadata.values())
    total_gb = total_size / (1024**3)
    
    # Build file list
    file_list_html = ""
    if file_metadata:
        for filename, meta in sorted(file_metadata.items(), key=lambda x: x[1]['upload_date'], reverse=True):
            file_list_html += f'''
                <div class="file-item">
                    <div class="file-info">
                        <span class="file-name">{meta['custom_name']}</span>
                        <span class="file-details">{meta['size_readable']} • {meta['upload_date']}</span>
                    </div>
                    <div class="file-actions">
                        <a href="/download/{filename}" class="btn btn-download">⬇️ Download</a>
                        <a href="/delete/{filename}" class="btn btn-delete" onclick="return confirm('Delete this file?')">🗑️ Delete</a>
                    </div>
                </div>
            '''
    else:
        file_list_html = '''
            <div class="empty-state">
                <p>📭 No files uploaded yet</p>
                <p style="font-size: 14px; color: #999;">Upload your first file</p>
            </div>
        '''
    
    html = f'''
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=yes">
        <title>INTERion · File Share</title>
        <style>
            /* ===== RESET & BASE ===== */
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: #ffffff;
                color: #1a1a1a;
                min-height: 100vh;
                padding: 20px;
            }}
            
            .container {{
                max-width: 1000px;
                margin: 0 auto;
            }}
            
            /* ===== HEADER ===== */
            .header {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 16px 0;
                border-bottom: 2px solid #f0f0f0;
                margin-bottom: 24px;
                flex-wrap: wrap;
                gap: 12px;
            }}
            
            .logo {{
                font-size: 24px;
                font-weight: 700;
                letter-spacing: -0.5px;
                display: flex;
                align-items: center;
                gap: 10px;
            }}
            
            .logo span {{
                background: #000;
                color: #fff;
                font-size: 11px;
                font-weight: 600;
                padding: 2px 12px;
                border-radius: 20px;
                letter-spacing: 0.5px;
            }}
            
            .header-right {{
                display: flex;
                align-items: center;
                gap: 16px;
                flex-wrap: wrap;
            }}
            
            .url-display {{
                background: #f5f5f5;
                padding: 6px 14px;
                border-radius: 6px;
                font-size: 13px;
                font-weight: 500;
                color: #555;
                font-family: 'Courier New', monospace;
            }}
            
            .qr-btn {{
                color: #000;
                text-decoration: none;
                font-weight: 600;
                font-size: 14px;
                padding: 6px 16px;
                border: 2px solid #000;
                border-radius: 6px;
                transition: all 0.2s;
            }}
            
            .qr-btn:hover {{
                background: #000;
                color: #fff;
            }}
            
            /* ===== STATS BAR ===== */
            .stats {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
                gap: 12px;
                margin-bottom: 24px;
            }}
            
            .stat {{
                background: #f8f8f8;
                padding: 14px 18px;
                border-radius: 10px;
                border: 1px solid #eee;
                text-align: center;
            }}
            
            .stat .num {{
                font-size: 22px;
                font-weight: 700;
                color: #000;
                display: block;
            }}
            
            .stat .label {{
                font-size: 11px;
                color: #888;
                text-transform: uppercase;
                letter-spacing: 0.5px;
                margin-top: 2px;
            }}
            
            /* ===== UPLOAD SECTION ===== */
            .upload-section {{
                background: #fafafa;
                border: 2px dashed #ddd;
                border-radius: 12px;
                padding: 24px;
                margin-bottom: 24px;
                transition: border-color 0.3s;
            }}
            
            .upload-section:hover {{
                border-color: #000;
            }}
            
            .upload-section h3 {{
                font-size: 16px;
                margin-bottom: 16px;
                color: #000;
            }}
            
            .upload-form {{
                display: flex;
                gap: 12px;
                flex-wrap: wrap;
                align-items: flex-end;
            }}
            
            .form-group {{
                flex: 1;
                min-width: 140px;
            }}
            
            .form-group label {{
                display: block;
                font-size: 12px;
                font-weight: 600;
                color: #666;
                margin-bottom: 4px;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }}
            
            .form-group input[type="file"],
            .form-group input[type="text"] {{
                width: 100%;
                padding: 10px 12px;
                border: 2px solid #e0e0e0;
                border-radius: 8px;
                font-size: 14px;
                transition: border-color 0.2s;
                background: #fff;
                color: #1a1a1a;
            }}
            
            .form-group input:focus {{
                outline: none;
                border-color: #000;
            }}
            
            .btn {{
                padding: 10px 28px;
                background: #000;
                color: #fff;
                border: none;
                border-radius: 8px;
                font-size: 14px;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.2s;
                text-decoration: none;
                display: inline-block;
                text-align: center;
            }}
            
            .btn:hover {{
                background: #222;
                transform: translateY(-1px);
                box-shadow: 0 4px 16px rgba(0,0,0,0.15);
            }}
            
            .btn:disabled {{
                opacity: 0.6;
                cursor: not-allowed;
                transform: none !important;
            }}
            
            .btn-download {{
                background: #22a65e;
                padding: 6px 16px;
                font-size: 13px;
            }}
            
            .btn-download:hover {{
                background: #1a8a4e;
            }}
            
            .btn-delete {{
                background: #dc3545;
                padding: 6px 16px;
                font-size: 13px;
            }}
            
            .btn-delete:hover {{
                background: #c82333;
            }}
            
            /* ===== PROGRESS ===== */
            .progress-container {{
                margin-top: 16px;
                display: none;
            }}
            
            .progress-bar {{
                width: 100%;
                height: 6px;
                background: #e0e0e0;
                border-radius: 3px;
                overflow: hidden;
            }}
            
            .progress-fill {{
                height: 100%;
                background: #000;
                width: 0%;
                transition: width 0.3s ease;
                border-radius: 3px;
            }}
            
            .progress-text {{
                display: block;
                text-align: center;
                margin-top: 6px;
                font-size: 13px;
                color: #666;
                font-weight: 600;
            }}
            
            /* ===== FILE LIST ===== */
            .file-list {{
                background: #fff;
                border: 1px solid #eee;
                border-radius: 12px;
                padding: 20px;
                margin-bottom: 24px;
            }}
            
            .file-list-header {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 16px;
                padding-bottom: 12px;
                border-bottom: 1px solid #f0f0f0;
                flex-wrap: wrap;
                gap: 8px;
            }}
            
            .file-list-header h3 {{
                font-size: 16px;
                color: #000;
            }}
            
            .file-count {{
                background: #f0f0f0;
                padding: 2px 12px;
                border-radius: 12px;
                font-size: 12px;
                color: #666;
            }}
            
            .file-item {{
                padding: 12px 0;
                border-bottom: 1px solid #f0f0f0;
                display: flex;
                justify-content: space-between;
                align-items: center;
                gap: 12px;
                flex-wrap: wrap;
            }}
            
            .file-item:last-child {{
                border-bottom: none;
            }}
            
            .file-info {{
                flex: 1;
                min-width: 120px;
            }}
            
            .file-name {{
                font-weight: 600;
                color: #1a1a1a;
                display: block;
                font-size: 14px;
                word-break: break-word;
            }}
            
            .file-details {{
                font-size: 12px;
                color: #888;
                display: block;
                margin-top: 2px;
            }}
            
            .file-actions {{
                display: flex;
                gap: 8px;
                flex-shrink: 0;
            }}
            
            .empty-state {{
                text-align: center;
                padding: 40px 20px;
                color: #999;
            }}
            
            .empty-state p {{
                margin: 4px 0;
            }}
            
            /* ===== FOOTER ===== */
            .footer {{
                padding: 20px 0;
                text-align: center;
                font-size: 12px;
                color: #aaa;
                border-top: 1px solid #f0f0f0;
                margin-top: 8px;
            }}
            
            /* ===== RESPONSIVE ===== */
            @media (max-width: 768px) {{
                body {{ padding: 12px; }}
                
                .header {{
                    flex-direction: column;
                    align-items: stretch;
                    gap: 10px;
                }}
                
                .header-right {{
                    justify-content: space-between;
                }}
                
                .url-display {{
                    font-size: 12px;
                    padding: 4px 10px;
                    flex: 1;
                    text-align: center;
                }}
                
                .upload-form {{
                    flex-direction: column;
                    align-items: stretch;
                }}
                
                .form-group {{
                    min-width: unset;
                }}
                
                .btn {{
                    width: 100%;
                    justify-content: center;
                }}
                
                .file-item {{
                    flex-direction: column;
                    align-items: stretch;
                    gap: 8px;
                    padding: 12px 0;
                }}
                
                .file-actions {{
                    justify-content: flex-end;
                }}
                
                .file-actions .btn {{
                    flex: 1;
                    text-align: center;
                    padding: 8px 12px;
                }}
                
                .stats {{
                    grid-template-columns: 1fr 1fr;
                }}
            }}
            
            @media (max-width: 400px) {{
                .logo {{
                    font-size: 20px;
                }}
                
                .file-actions {{
                    flex-direction: column;
                }}
                
                .file-actions .btn {{
                    width: 100%;
                }}
                
                .stats {{
                    grid-template-columns: 1fr;
                }}
            }}
            
            /* ===== DARK MODE ===== */
            @media (prefers-color-scheme: dark) {{
                body {{
                    background: #1a1a1a;
                    color: #e8e8e8;
                }}
                
                .stat {{
                    background: #242424;
                    border-color: #333;
                }}
                
                .stat .num {{
                    color: #e8e8e8;
                }}
                
                .stat .label {{
                    color: #888;
                }}
                
                .upload-section {{
                    background: #242424;
                    border-color: #333;
                }}
                
                .upload-section:hover {{
                    border-color: #888;
                }}
                
                .upload-section h3 {{
                    color: #e8e8e8;
                }}
                
                .form-group input[type="file"],
                .form-group input[type="text"] {{
                    background: #1a1a1a;
                    border-color: #333;
                    color: #e8e8e8;
                }}
                
                .form-group input:focus {{
                    border-color: #888;
                }}
                
                .file-list {{
                    background: #242424;
                    border-color: #333;
                }}
                
                .file-list-header {{
                    border-bottom-color: #333;
                }}
                
                .file-list-header h3 {{
                    color: #e8e8e8;
                }}
                
                .file-count {{
                    background: #333;
                    color: #aaa;
                }}
                
                .file-item {{
                    border-bottom-color: #333;
                }}
                
                .file-name {{
                    color: #e8e8e8;
                }}
                
                .file-details {{
                    color: #888;
                }}
                
                .progress-bar {{
                    background: #333;
                }}
                
                .progress-text {{
                    color: #888;
                }}
                
                .footer {{
                    border-top-color: #333;
                    color: #666;
                }}
                
                .url-display {{
                    background: #242424;
                    color: #aaa;
                }}
                
                .qr-btn {{
                    border-color: #888;
                    color: #e8e8e8;
                }}
                
                .qr-btn:hover {{
                    background: #e8e8e8;
                    color: #1a1a1a;
                }}
                
                .btn {{
                    background: #e8e8e8;
                    color: #1a1a1a;
                }}
                
                .btn:hover {{
                    background: #fff;
                }}
                
                .btn-download {{
                    background: #22a65e;
                    color: #fff;
                }}
                
                .btn-download:hover {{
                    background: #28b86a;
                }}
                
                .btn-delete {{
                    background: #dc3545;
                    color: #fff;
                }}
                
                .btn-delete:hover {{
                    background: #e74c5c;
                }}
                
                .empty-state {{
                    color: #666;
                }}
                
                .empty-state p:last-child {{
                    color: #555;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <!-- Header -->
            <div class="header">
                <div class="logo">
                    ⚡ INTERion
                    <span>v1.0</span>
                </div>
                <div class="header-right">
                    <span class="url-display">{url}</span>
                    <a href="/qr" class="qr-btn">📱 QR</a>
                </div>
            </div>
            
            <!-- Stats -->
            <div class="stats">
                <div class="stat">
                    <span class="num">{len(file_metadata)}</span>
                    <span class="label">Files</span>
                </div>
                <div class="stat">
                    <span class="num">{total_gb:.2f}GB</span>
                    <span class="label">Storage Used</span>
                </div>
                <div class="stat">
                    <span class="num">⚡</span>
                    <span class="label">100+ Mbps</span>
                </div>
                <div class="stat">
                    <span class="num">●</span>
                    <span class="label">Online</span>
                </div>
            </div>
            
            <!-- Upload -->
            <div class="upload-section">
                <h3>⬆ Upload File</h3>
                <form action="/upload" method="post" enctype="multipart/form-data" class="upload-form" id="uploadForm">
                    <div class="form-group">
                        <label for="file">Choose File</label>
                        <input type="file" name="file" id="file" required>
                    </div>
                    <div class="form-group">
                        <label for="filename">Custom Name (optional)</label>
                        <input type="text" name="filename" id="filename" placeholder="Enter custom name">
                    </div>
                    <button type="submit" class="btn" id="uploadBtn">Upload</button>
                </form>
                <div class="progress-container" id="progressContainer">
                    <div class="progress-bar">
                        <div class="progress-fill" id="progressFill"></div>
                    </div>
                    <span class="progress-text" id="progressText">0%</span>
                </div>
            </div>
            
            <!-- File List -->
            <div class="file-list">
                <div class="file-list-header">
                    <h3>📂 Files</h3>
                    <span class="file-count">{len(file_metadata)} files</span>
                </div>
                {file_list_html}
            </div>
            
            <!-- Footer -->
            <div class="footer">
                INTERion • Fast file sharing for all devices
            </div>
        </div>
        
        <script>
            document.getElementById('uploadForm').addEventListener('submit', function(e) {{
                const fileInput = document.getElementById('file');
                if (fileInput.files.length === 0) return;
                
                const formData = new FormData(this);
                const progressContainer = document.getElementById('progressContainer');
                const progressFill = document.getElementById('progressFill');
                const progressText = document.getElementById('progressText');
                const uploadBtn = document.getElementById('uploadBtn');
                
                progressContainer.style.display = 'block';
                uploadBtn.disabled = true;
                uploadBtn.textContent = 'Uploading...';
                
                const xhr = new XMLHttpRequest();
                xhr.open('POST', '/upload', true);
                
                xhr.upload.addEventListener('progress', function(e) {{
                    if (e.lengthComputable) {{
                        const percent = Math.round((e.loaded / e.total) * 100);
                        progressFill.style.width = percent + '%';
                        progressText.textContent = percent + '%';
                    }}
                }});
                
                xhr.onload = function() {{
                    if (xhr.status === 200) {{
                        progressFill.style.width = '100%';
                        progressText.textContent = '✓ Complete!';
                        setTimeout(() => window.location.reload(), 800);
                    }} else {{
                        alert('Upload failed: ' + xhr.statusText);
                        progressContainer.style.display = 'none';
                        uploadBtn.disabled = false;
                        uploadBtn.textContent = 'Upload';
                    }}
                }};
                
                xhr.onerror = function() {{
                    alert('Upload failed!');
                    progressContainer.style.display = 'none';
                    uploadBtn.disabled = false;
                    uploadBtn.textContent = 'Upload';
                }};
                
                xhr.send(formData);
                e.preventDefault();
            }});
        </script>
    </body>
    </html>
    '''
    
    return HTMLResponse(html)

@app.post("/upload")
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    filename: Optional[str] = Form(None)
):
    try:
        original_filename = file.filename
        
        if filename and filename.strip():
            name_without_ext = filename.strip()
            _, ext = os.path.splitext(original_filename)
            final_filename = name_without_ext + ext
        else:
            final_filename = original_filename
        
        file_path = os.path.join(UPLOAD_FOLDER, final_filename)
        counter = 1
        while os.path.exists(file_path):
            name, ext = os.path.splitext(final_filename)
            final_filename = f"{name}_{counter}{ext}"
            file_path = os.path.join(UPLOAD_FOLDER, final_filename)
        
        size = 0
        chunk_size = 1024 * 1024
        
        async with aiofiles.open(file_path, 'wb') as f:
            while chunk := await file.read(chunk_size):
                await f.write(chunk)
                size += len(chunk)
        
        file_metadata[final_filename] = {
            'original_name': original_filename,
            'custom_name': filename if filename and filename.strip() else original_filename,
            'size': size,
            'upload_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'size_readable': format_size(size)
        }
        
        with open(METADATA_FILE, 'w') as f:
            json.dump(file_metadata, f, indent=2)
        
        return JSONResponse({
            "status": "success",
            "filename": final_filename,
            "size": format_size(size)
        })
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/download/{filename}")
async def download_file(filename: str, request: Request):
    file_path = os.path.join(UPLOAD_FOLDER, filename)
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    
    log_transfer(request, {"event":"download","fileName":filename,"size":file_metadata.get(filename,{}).get("size",0),"direction":"download","result":"success"})
    return FileResponse(file_path, filename=filename)

@app.get("/delete/{filename}")
async def delete_file(filename: str, request: Request):
    file_path = os.path.join(UPLOAD_FOLDER, filename)
    
    if os.path.exists(file_path):
        os.remove(file_path)
        if filename in file_metadata:
            del file_metadata[filename]
            with open(METADATA_FILE, 'w') as f:
                json.dump(file_metadata, f, indent=2)
        log_transfer(request, {"event":"delete","fileName":filename,"direction":"delete","result":"success"})
        return JSONResponse({"status": "success"})
    else:
        raise HTTPException(status_code=404, detail="File not found")

@app.get("/qr", response_class=HTMLResponse)
async def show_qr():
    ip = get_local_ip()
    url = f"http://{ip}:{PORT}"
    
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    img_path = "temp_qr.png"
    img.save(img_path)
    
    import base64
    with open(img_path, 'rb') as f:
        img_data = base64.b64encode(f.read()).decode()
    os.remove(img_path)
    
    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
        <title>INTERion · QR</title>
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: #ffffff;
                min-height: 100vh;
                display: flex;
                justify-content: center;
                align-items: center;
                padding: 20px;
            }}
            
            .qr-container {{
                background: #fafafa;
                border: 2px solid #eee;
                border-radius: 16px;
                padding: 32px;
                text-align: center;
                max-width: 400px;
                width: 100%;
            }}
            
            .logo {{
                font-size: 20px;
                font-weight: 700;
                color: #000;
            }}
            
            h2 {{
                color: #1a1a1a;
                margin-top: 12px;
                font-size: 18px;
                font-weight: 600;
            }}
            
            .qr-code {{
                margin: 20px 0;
                background: white;
                padding: 16px;
                border-radius: 12px;
                display: inline-block;
                border: 1px solid #eee;
            }}
            
            .qr-code img {{
                max-width: 100%;
                height: auto;
                display: block;
            }}
            
            .url {{
                background: #f5f5f5;
                padding: 12px;
                border-radius: 8px;
                word-break: break-all;
                font-family: 'Courier New', monospace;
                font-size: 13px;
                color: #333;
                margin: 12px 0;
            }}
            
            .btn-back {{
                display: inline-block;
                padding: 10px 24px;
                background: #000;
                color: #fff;
                border: none;
                border-radius: 8px;
                text-decoration: none;
                font-weight: 600;
                font-size: 14px;
                transition: all 0.2s;
            }}
            
            .btn-back:hover {{
                background: #222;
                transform: translateY(-1px);
            }}
            
            .instruction {{
                color: #888;
                font-size: 14px;
                margin: 8px 0;
            }}
            
            @media (prefers-color-scheme: dark) {{
                body {{
                    background: #1a1a1a;
                }}
                
                .qr-container {{
                    background: #242424;
                    border-color: #333;
                }}
                
                .logo {{
                    color: #e8e8e8;
                }}
                
                h2 {{
                    color: #e8e8e8;
                }}
                
                .url {{
                    background: #1a1a1a;
                    color: #aaa;
                }}
                
                .instruction {{
                    color: #888;
                }}
                
                .qr-code {{
                    border-color: #333;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="qr-container">
            <div class="logo">⚡ INTERion</div>
            <h2>Scan to Access</h2>
            <p class="instruction">Open camera and scan QR code</p>
            <div class="qr-code">
                <img src="data:image/png;base64,{img_data}" alt="QR Code">
            </div>
            <div class="url">{url}</div>
            <a href="/" class="btn-back">← Back</a>
        </div>
    </body>
    </html>
    '''

@app.get("/files")
async def list_files():
    return JSONResponse(file_metadata)

@app.get("/speed-test")
async def speed_test():
    size = 10 * 1024 * 1024
    data = os.urandom(size)
    return StreamingResponse(
        iter([data]),
        media_type='application/octet-stream',
        headers={
            'Content-Disposition': 'attachment; filename="speed_test_10mb.bin"',
            'Content-Length': str(size)
        }
    )

if __name__ == "__main__":
    ip = get_local_ip()
    url = f"http://{ip}:{PORT}"
    
    print("=" * 50)
    print("⚡ INTERion File Share")
    print("=" * 50)
    print(f"✅ Server: {url}")
    print(f"📱 Access from phone: {url}")
    print(f"📂 Files: {UPLOAD_FOLDER}")
    print("=" * 50)
    print("Features:")
    print("  • Upload with custom names")
    print("  • Download files")
    print("  • Delete files")
    print("  • QR code access")
    print("  • 100+ Mbps speed")
    print("=" * 50)
    print("Press Ctrl+C to stop")
    print("=" * 50)
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=PORT,
        log_level="info",
        access_log=True
    )