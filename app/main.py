import os
import json
import shutil
import secrets
import ipaddress
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List

from fastapi import FastAPI, Request, Form, UploadFile, File, HTTPException, Depends
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .database import get_db, init_db, UPLOADS_DIR, DB_PATH
from .utils import get_local_ip, generate_qr_code
from .docx_generator import generate_docx
from .tunnel_manager import TunnelManager

# Initialize DB
init_db()

app = FastAPI(title="School Question Paper Management System")

# Enable CORS for LAN access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

STATIC_DIR.mkdir(exist_ok=True)
TEMPLATES_DIR.mkdir(exist_ok=True)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# ----------------- Models -----------------
class SchoolSettingsUpdate(BaseModel):
    school_name: str
    school_name_font: Optional[str] = "Old English Text MT"
    sub_title: Optional[str] = ""
    address: Optional[str] = ""
    logo_size: Optional[int] = 80
    watermark_text: Optional[str] = ""
    show_watermark: Optional[bool] = False
    font_family: Optional[str] = "Calibri"
    font_size: Optional[str] = "11pt"
    line_spacing: Optional[str] = "1.15"
    page_layout: Optional[str] = "1-column"
    show_instructions: Optional[bool] = True
    enable_answer_key: Optional[bool] = False
    wifi_enabled: Optional[bool] = True
    wifi_security_mode: Optional[str] = "secure"
    wifi_passcode: Optional[str] = ""
    network_scope: Optional[str] = "school_wifi"  # 'school_wifi' or 'any_network'
    public_url: Optional[str] = ""

class WifiSettingsUpdate(BaseModel):
    wifi_enabled: bool
    wifi_security_mode: str = "secure"  # 'secure' or 'open'
    wifi_passcode: Optional[str] = ""
    network_scope: Optional[str] = "school_wifi"  # 'school_wifi' or 'any_network'
    public_url: Optional[str] = ""

class TunnelStartRequest(BaseModel):
    subdomain: Optional[str] = None

class GenerateLinkRequest(BaseModel):
    validity_hours: float = 24.0

class TeacherCreate(BaseModel):
    name: str
    email: str
    pin: str
    phone: Optional[str] = ""
    assigned_classes: Optional[list] = []

class TeacherLoginRequest(BaseModel):
    email: str
    pin: str

class AdminLoginRequest(BaseModel):
    username: str
    password: str

class AdminChangePasswordRequest(BaseModel):
    current_password: str
    new_username: Optional[str] = None
    new_password: str

class BlueprintCreate(BaseModel):
    title: str
    class_name: str
    section: Optional[str] = ""
    subject: str
    teacher_id: Optional[int] = None
    duration_minutes: int = 180
    total_marks: float = 80.0
    general_instructions: Optional[str] = ""
    sections_config: list

class BulkBlueprintCreate(BaseModel):
    title: str
    classes: list[str]
    sections: Optional[list[str]] = []
    subjects: list[str]
    teacher_id: Optional[int] = None
    duration_minutes: int = 180
    total_marks: float = 80.0
    general_instructions: Optional[str] = ""
    sections_config: list

def validate_blueprint_marks(sections_config: list, total_marks: float):
    """
    Validates that the sum of (count * marks_per_q) across all sections
    equals the blueprint's total_marks.
    """
    if not sections_config:
        raise HTTPException(status_code=400, detail="Blueprint must contain at least one section.")
    
    calculated_total = 0.0
    for idx, sec in enumerate(sections_config):
        count = float(sec.get('count', 0))
        marks_per_q = float(sec.get('marks_per_q', 0))
        if count <= 0:
            raise HTTPException(status_code=400, detail=f"Section {idx+1} ({sec.get('name', 'Unnamed')}) must have at least 1 question.")
        if marks_per_q <= 0:
            raise HTTPException(status_code=400, detail=f"Section {idx+1} ({sec.get('name', 'Unnamed')}) marks per question must be greater than 0.")
        calculated_total += (count * marks_per_q)
    
    if abs(calculated_total - float(total_marks)) > 0.01:
        raise HTTPException(
            status_code=400,
            detail=f"Marks mismatch: Total calculated marks from sections ({calculated_total:g}) does not match blueprint Total Marks ({total_marks:g}). Please adjust question counts or marks per question."
        )

class QuestionItem(BaseModel):
    blueprint_id: int
    section_id: str
    section_name: str
    question_number: int
    question_type: str
    question_text: str
    options: Optional[list] = []
    correct_answer: Optional[str] = ""
    solution_explanation: Optional[str] = ""
    marks: float = 1.0
    image_path: Optional[str] = ""
    or_question_text: Optional[str] = ""
    or_image_path: Optional[str] = ""

# In-memory set of active admin session tokens
ACTIVE_ADMIN_TOKENS = set()

# ----------------- View Routes -----------------
@app.get("/", response_class=HTMLResponse)
async def home_page(request: Request):
    token = request.query_params.get("token")
    if token:
        return RedirectResponse(url=f"/dashboard?token={token}")
    return templates.TemplateResponse(request=request, name="login.html")

@app.get("/login", response_class=HTMLResponse)
@app.get("/admin/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request=request, name="login.html")

@app.get("/logout", response_class=HTMLResponse)
async def logout_view():
    return HTMLResponse("""
    <!DOCTYPE html>
    <html>
    <head><title>Logging out...</title></head>
    <body style="background:#0f172a;color:#94a3b8;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;">
        <script>
            try {
                localStorage.clear();
                sessionStorage.clear();
            } catch(e) {}
            window.location.replace('/?logged_out=1');
        </script>
        <p>Logging out, please wait...</p>
    </body>
    </html>
    """)

@app.get("/dashboard", response_class=HTMLResponse)
@app.get("/app", response_class=HTMLResponse)
@app.get("/portal", response_class=HTMLResponse)
async def dashboard_page(request: Request, token: Optional[str] = None):
    return templates.TemplateResponse(request=request, name="index.html")

@app.get("/paper/{blueprint_id}/print", response_class=HTMLResponse)
async def print_paper(request: Request, blueprint_id: int, answer_key: bool = False, role: Optional[str] = "admin"):
    if role == "teacher":
        raise HTTPException(status_code=403, detail="Teachers are not permitted to print or download question papers. Only school administrators have printing privileges.")

    conn = get_db()
    cursor = conn.cursor()
    
    # Fetch school settings
    cursor.execute("SELECT * FROM school_settings WHERE id = 1")
    school_row = cursor.fetchone()
    school = dict(school_row) if school_row else {}

    if answer_key and not school.get('enable_answer_key', 1):
        conn.close()
        raise HTTPException(status_code=403, detail="Answer key feature is disabled by the administrator.")

    # Fetch blueprint
    cursor.execute("SELECT * FROM paper_blueprints WHERE id = ?", (blueprint_id,))
    bp_row = cursor.fetchone()
    if not bp_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Blueprint not found")
    blueprint = dict(bp_row)

    # Fetch questions
    cursor.execute("SELECT * FROM questions WHERE blueprint_id = ? ORDER BY question_number ASC", (blueprint_id,))
    q_rows = cursor.fetchall()
    conn.close()

    questions = []
    sections_map = {}
    for r in q_rows:
        q = dict(r)
        try:
            q['parsed_options'] = json.loads(q['options']) if q.get('options') else []
        except Exception:
            q['parsed_options'] = []
        
        sec_name = q.get('section_name') or 'Section'
        if sec_name not in sections_map:
            sections_map[sec_name] = []
        sections_map[sec_name].append(q)
        questions.append(q)

    instructions_list = [line.strip() for line in (blueprint.get('general_instructions') or '').split('\n') if line.strip()]

    return templates.TemplateResponse(request=request, name="paper_print.html", context={
        "blueprint": blueprint,
        "school": school,
        "sections_map": sections_map,
        "questions": questions,
        "instructions_list": instructions_list,
        "is_answer_key": answer_key
    })

# ----------------- API Endpoints -----------------

@app.get("/api/network-info")
async def get_network_info():
    ip = get_local_ip()
    port = 8000
    lan_url = f"http://{ip}:{port}"
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT wifi_enabled, wifi_security_mode, wifi_passcode, network_scope, public_url FROM school_settings WHERE id = 1")
    row = dict(cursor.fetchone() or {})
    conn.close()
    
    wifi_enabled = bool(row.get('wifi_enabled', 1))
    wifi_security_mode = row.get('wifi_security_mode') or 'secure'
    has_passcode = bool(row.get('wifi_passcode'))
    network_scope = row.get('network_scope') or 'school_wifi'
    stored_public_url = row.get('public_url') or ''
    
    tunnel_mgr = TunnelManager.get_instance()
    tunnel_status = tunnel_mgr.get_status()
    active_tunnel_url = tunnel_status.get('url')
    
    effective_public_url = active_tunnel_url or stored_public_url
    
    # Active portal URL depends on network_scope
    if network_scope == 'any_network' and effective_public_url:
        active_portal_url = effective_public_url.rstrip('/')
        network_label = "Any Network (Internet / Mobile Data)"
    else:
        active_portal_url = lan_url
        network_label = "School Wi-Fi Only"
        
    qr_code = generate_qr_code(active_portal_url)
    
    return {
        "local_ip": ip,
        "port": port,
        "lan_url": lan_url,
        "network_scope": network_scope,
        "network_label": network_label,
        "public_url": effective_public_url,
        "active_portal_url": active_portal_url,
        "is_tunnel_running": tunnel_status.get('status') == 'running',
        "tunnel_status": tunnel_status,
        "qr_code": qr_code,
        "wifi_enabled": wifi_enabled,
        "wifi_security_mode": wifi_security_mode,
        "has_passcode": has_passcode
    }

@app.get("/api/wifi-settings")
async def get_wifi_settings():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT wifi_enabled, wifi_security_mode, wifi_passcode, network_scope, public_url FROM school_settings WHERE id = 1")
    row = dict(cursor.fetchone() or {})
    conn.close()
    
    tunnel_mgr = TunnelManager.get_instance()
    tunnel_status = tunnel_mgr.get_status()
    effective_public = tunnel_status.get('url') or row.get('public_url') or ''
    
    return {
        "wifi_enabled": bool(row.get('wifi_enabled', 1)),
        "wifi_security_mode": row.get('wifi_security_mode') or 'secure',
        "wifi_passcode": row.get('wifi_passcode') or '',
        "network_scope": row.get('network_scope') or 'school_wifi',
        "public_url": effective_public,
        "is_tunnel_running": tunnel_status.get('status') == 'running'
    }

@app.post("/api/wifi-settings")
async def update_wifi_settings(settings: WifiSettingsUpdate):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
    UPDATE school_settings
    SET wifi_enabled = ?, wifi_security_mode = ?, wifi_passcode = ?, network_scope = ?, public_url = ?
    WHERE id = 1
    ''', (
        1 if settings.wifi_enabled else 0,
        settings.wifi_security_mode or 'secure',
        settings.wifi_passcode or '',
        settings.network_scope or 'school_wifi',
        settings.public_url or ''
    ))
    conn.commit()
    conn.close()
    return {"status": "success", "message": "Network & Wi-Fi settings updated successfully"}

# --- Internet Tunnel Endpoints ---
@app.post("/api/tunnel/start")
async def start_tunnel(req: Optional[TunnelStartRequest] = None):
    subdomain = req.subdomain if req else None
    mgr = TunnelManager.get_instance()
    res = mgr.start_tunnel(port=8000, subdomain=subdomain)
    if res.get("url"):
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("UPDATE school_settings SET public_url = ?, network_scope = 'any_network' WHERE id = 1", (res["url"],))
        conn.commit()
        conn.close()
    return res

@app.post("/api/tunnel/stop")
async def stop_tunnel():
    mgr = TunnelManager.get_instance()
    res = mgr.stop_tunnel()
    return res

@app.get("/api/tunnel/status")
async def get_tunnel_status():
    mgr = TunnelManager.get_instance()
    return mgr.get_status()

# --- Admin Authentication ---
@app.post("/api/admin/login")
async def api_admin_login(data: AdminLoginRequest):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT admin_username, admin_password FROM school_settings WHERE id = 1")
    row = cursor.fetchone()
    conn.close()
    
    admin_user = 'admin'
    admin_pass = 'admin123'
    if row:
        row_dict = dict(row)
        admin_user = row_dict.get('admin_username') or 'admin'
        admin_pass = row_dict.get('admin_password') or 'admin123'
    
    if data.username.strip() == admin_user and data.password == admin_pass:
        token = secrets.token_urlsafe(32)
        ACTIVE_ADMIN_TOKENS.add(token)
        return {
            "status": "success",
            "token": token,
            "username": admin_user,
            "message": "Login successful"
        }
    else:
        raise HTTPException(status_code=401, detail="Invalid admin username or password. Please try again.")

@app.post("/api/admin/logout")
async def api_admin_logout(token: Optional[str] = None):
    if token and token in ACTIVE_ADMIN_TOKENS:
        ACTIVE_ADMIN_TOKENS.discard(token)
    return {"status": "success", "message": "Logged out successfully"}

@app.get("/api/admin/me")
async def api_admin_me(token: Optional[str] = None):
    if token and token in ACTIVE_ADMIN_TOKENS:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT admin_username FROM school_settings WHERE id = 1")
        row = cursor.fetchone()
        conn.close()
        admin_user = (dict(row).get('admin_username') if row else 'admin') or 'admin'
        return {"authenticated": True, "username": admin_user}
    return {"authenticated": False}

@app.post("/api/admin/change-password")
async def api_admin_change_password(data: AdminChangePasswordRequest):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT admin_username, admin_password FROM school_settings WHERE id = 1")
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Settings not found")
    
    row_dict = dict(row)
    current_pass = row_dict.get('admin_password') or 'admin123'
    if data.current_password != current_pass:
        conn.close()
        raise HTTPException(status_code=400, detail="Current password is incorrect.")
    
    new_user = (data.new_username.strip() if data.new_username else None) or row_dict.get('admin_username') or 'admin'
    cursor.execute("UPDATE school_settings SET admin_username = ?, admin_password = ? WHERE id = 1", (new_user, data.new_password))
    conn.commit()
    conn.close()
    return {"status": "success", "message": "Admin credentials updated successfully"}

# --- School Settings ---
@app.get("/api/school-settings")
async def get_school_settings():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM school_settings WHERE id = 1")
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else {}

@app.post("/api/school-settings")
async def update_school_settings(settings: SchoolSettingsUpdate):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
    UPDATE school_settings
    SET school_name = ?, school_name_font = ?, sub_title = ?, address = ?, logo_size = ?, watermark_text = ?,
        show_watermark = ?, font_family = ?, font_size = ?, line_spacing = ?,
        page_layout = ?, show_instructions = ?, enable_answer_key = ?,
        wifi_enabled = ?, wifi_security_mode = ?, wifi_passcode = ?,
        network_scope = ?, public_url = ?
    WHERE id = 1
    ''', (
        settings.school_name, settings.school_name_font or 'Old English Text MT',
        settings.sub_title, settings.address,
        settings.logo_size or 80,
        settings.watermark_text, 1 if settings.show_watermark else 0,
        settings.font_family, settings.font_size, settings.line_spacing,
        settings.page_layout, 1 if settings.show_instructions else 0,
        0,
        1 if settings.wifi_enabled else 0, settings.wifi_security_mode or 'secure',
        settings.wifi_passcode or '',
        settings.network_scope or 'school_wifi',
        settings.public_url or ''
    ))
    conn.commit()
    conn.close()
    return {"status": "success", "message": "Settings updated"}

@app.post("/api/upload-logo")
async def upload_logo(file: UploadFile = File(...)):
    conn = get_db()
    cursor = conn.cursor()
    ext = Path(file.filename).suffix or ".png"
    save_path = os.path.join(UPLOADS_DIR, "logos", f"school_logo{ext}")
    
    with open(save_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    rel_path = f"uploads/logos/school_logo{ext}"
    cursor.execute("UPDATE school_settings SET logo_path = ? WHERE id = 1", (rel_path,))
    conn.commit()
    conn.close()
    return {"status": "success", "logo_path": rel_path}

# --- Teachers ---
@app.get("/api/teachers")
async def list_teachers():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM teachers ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    teachers = []
    for r in rows:
        t = dict(r)
        try:
            t['assigned_classes'] = json.loads(t['assigned_classes']) if t['assigned_classes'] else []
        except Exception:
            t['assigned_classes'] = []
        teachers.append(t)
    return teachers

@app.post("/api/teachers")
async def add_teacher(data: TeacherCreate):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('''
        INSERT INTO teachers (name, email, pin, phone, assigned_classes)
        VALUES (?, ?, ?, ?, ?)
        ''', (data.name, data.email, data.pin, data.phone, json.dumps(data.assigned_classes or [])))
        conn.commit()
        teacher_id = cursor.lastrowid
        conn.close()
        return {"status": "success", "id": teacher_id}
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=400, detail=str(e))

@app.put("/api/teachers/{teacher_id}")
async def update_teacher(teacher_id: int, data: TeacherCreate):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
    UPDATE teachers
    SET name = ?, email = ?, pin = ?, phone = ?, assigned_classes = ?
    WHERE id = ?
    ''', (data.name, data.email, data.pin, data.phone, json.dumps(data.assigned_classes or []), teacher_id))
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.delete("/api/teachers/{teacher_id}")
async def delete_teacher(teacher_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM teachers WHERE id = ?", (teacher_id,))
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.post("/api/teacher/login")
async def api_teacher_login(data: TeacherLoginRequest):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM teachers WHERE LOWER(email) = LOWER(?) AND pin = ?", (data.email.strip(), data.pin.strip()))
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=401, detail="Invalid teacher email address or PIN code.")
    teacher = dict(row)
    try:
        teacher['assigned_classes'] = json.loads(teacher['assigned_classes']) if teacher['assigned_classes'] else []
    except Exception:
        teacher['assigned_classes'] = []
    return {"status": "success", "teacher": teacher}

@app.post("/api/teacher/verify-pin")
async def verify_teacher_pin(request: Request):
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        body = await request.json()
        email = body.get("email", "")
        pin = body.get("pin", "")
    else:
        form = await request.form()
        email = form.get("email", "")
        pin = form.get("pin", "")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM teachers WHERE LOWER(email) = LOWER(?) AND pin = ?", (str(email).strip(), str(pin).strip()))
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=401, detail="Invalid teacher email or PIN")
    teacher = dict(row)
    try:
        teacher['assigned_classes'] = json.loads(teacher['assigned_classes']) if teacher['assigned_classes'] else []
    except Exception:
        teacher['assigned_classes'] = []
    return {"status": "success", "teacher": teacher}

# --- Blueprints (Admin specifications) ---
@app.get("/api/blueprints")
async def list_blueprints(teacher_id: Optional[int] = None):
    conn = get_db()
    cursor = conn.cursor()
    if teacher_id:
        cursor.execute('''
        SELECT b.*, t.name as teacher_name
        FROM paper_blueprints b
        LEFT JOIN teachers t ON b.teacher_id = t.id
        WHERE b.teacher_id = ?
        ORDER BY b.id DESC
        ''', (teacher_id,))
    else:
        cursor.execute('''
        SELECT b.*, t.name as teacher_name
        FROM paper_blueprints b
        LEFT JOIN teachers t ON b.teacher_id = t.id
        ORDER BY b.id DESC
        ''')
    rows = cursor.fetchall()
    
    result = []
    for r in rows:
        bp = dict(r)
        try:
            bp['sections_config'] = json.loads(bp['sections_config']) if bp['sections_config'] else []
        except Exception:
            bp['sections_config'] = []
            
        # Count questions entered
        cursor.execute("SELECT COUNT(*) as q_count FROM questions WHERE blueprint_id = ?", (bp['id'],))
        bp['entered_questions_count'] = cursor.fetchone()['q_count']
        
        # Calculate target questions count
        target_count = sum(s.get('count', 0) for s in bp['sections_config'])
        bp['target_questions_count'] = target_count
        result.append(bp)

    conn.close()
    return result

@app.get("/api/blueprints/{bp_id}")
async def get_blueprint(bp_id: int, role: Optional[str] = "admin"):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
    SELECT b.*, t.name as teacher_name, t.email as teacher_email
    FROM paper_blueprints b
    LEFT JOIN teachers t ON b.teacher_id = t.id
    WHERE b.id = ?
    ''', (bp_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Blueprint not found")
    
    bp = dict(row)
    try:
        bp['sections_config'] = json.loads(bp['sections_config']) if bp['sections_config'] else []
    except Exception:
        bp['sections_config'] = []

    # If role is teacher and paper is already submitted, lock access to questions
    is_submitted = bp.get('status') in ('Questions_Submitted', 'Approved')
    if role == 'teacher' and is_submitted:
        conn.close()
        bp['is_locked'] = True
        bp['lock_message'] = "Paper is submitted! Questions are locked and cannot be viewed or edited."
        bp['warning_message'] = "Paper is submitted! Questions are locked and cannot be viewed or edited."
        bp['questions'] = []
        return bp

    # Get questions
    cursor.execute("SELECT * FROM questions WHERE blueprint_id = ? ORDER BY question_number ASC", (bp_id,))
    q_rows = cursor.fetchall()
    conn.close()

    bp['is_locked'] = False
    bp['questions'] = []
    for q in q_rows:
        qd = dict(q)
        try:
            qd['options'] = json.loads(qd['options']) if qd.get('options') else []
        except Exception:
            qd['options'] = []
        bp['questions'].append(qd)

    return bp

@app.post("/api/blueprints/{bp_id}/reopen")
async def reopen_blueprint(bp_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE paper_blueprints SET status = 'Assigned', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (bp_id,))
    conn.commit()
    conn.close()
    return {"status": "success", "message": "Blueprint unlocked and reopened for teacher editing"}

@app.post("/api/blueprints")
async def create_blueprint(data: BlueprintCreate):
    validate_blueprint_marks(data.sections_config, data.total_marks)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
    INSERT INTO paper_blueprints (
        title, class_name, section, subject, teacher_id, duration_minutes, total_marks,
        general_instructions, sections_config, status
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Assigned')
    ''', (
        data.title, data.class_name, data.section, data.subject, data.teacher_id,
        data.duration_minutes, data.total_marks, data.general_instructions or '',
        json.dumps(data.sections_config)
    ))
    conn.commit()
    bp_id = cursor.lastrowid
    conn.close()
    return {"status": "success", "id": bp_id}

@app.post("/api/blueprints/bulk")
async def create_bulk_blueprints(data: BulkBlueprintCreate):
    validate_blueprint_marks(data.sections_config, data.total_marks)

    classes = [c.strip() for c in data.classes if c.strip()]
    sections = [s.strip() for s in data.sections if s.strip()] or [""]
    subjects = [sub.strip() for sub in data.subjects if sub.strip()]

    if not classes:
        raise HTTPException(status_code=400, detail="Please select or provide at least one class.")
    if not subjects:
        raise HTTPException(status_code=400, detail="Please select or provide at least one subject.")

    conn = get_db()
    cursor = conn.cursor()
    created_ids = []

    # Fetch teachers to auto-match if teacher_id is not explicitly chosen
    cursor.execute("SELECT id, name, assigned_classes FROM teachers")
    teachers = [dict(t) for t in cursor.fetchall()]

    for cls in classes:
        for sec in sections:
            for subj in subjects:
                assigned_tid = data.teacher_id
                if not assigned_tid:
                    for t in teachers:
                        try:
                            assigned_list = json.loads(t.get('assigned_classes') or '[]')
                            for a in assigned_list:
                                if a.get('class') == cls and (not a.get('section') or a.get('section') == sec) and a.get('subject') == subj:
                                    assigned_tid = t['id']
                                    break
                            if assigned_tid:
                                break
                        except Exception:
                            pass

                cursor.execute('''
                INSERT INTO paper_blueprints (
                    title, class_name, section, subject, teacher_id, duration_minutes, total_marks,
                    general_instructions, sections_config, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Assigned')
                ''', (
                    data.title, cls, sec, subj, assigned_tid,
                    data.duration_minutes, data.total_marks, data.general_instructions or '',
                    json.dumps(data.sections_config)
                ))
                created_ids.append(cursor.lastrowid)

    conn.commit()
    conn.close()
    return {
        "status": "success",
        "created_count": len(created_ids),
        "created_ids": created_ids,
        "message": f"Successfully created {len(created_ids)} question paper blueprints!"
    }

@app.post("/api/blueprints/{bp_id}/clone")
async def clone_blueprint(bp_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM paper_blueprints WHERE id = ?", (bp_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Blueprint not found")
    bp = dict(row)
    cursor.execute('''
    INSERT INTO paper_blueprints (
        title, class_name, section, subject, teacher_id, duration_minutes, total_marks,
        general_instructions, sections_config, status
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Assigned')
    ''', (
        f"{bp['title']} (Copy)", bp['class_name'], bp['section'], bp['subject'],
        bp['teacher_id'], bp['duration_minutes'], bp['total_marks'],
        bp['general_instructions'], bp['sections_config']
    ))
    new_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return {"status": "success", "id": new_id, "message": "Blueprint cloned successfully"}

@app.put("/api/blueprints/{bp_id}")
async def update_blueprint(bp_id: int, data: BlueprintCreate):
    validate_blueprint_marks(data.sections_config, data.total_marks)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
    UPDATE paper_blueprints
    SET title = ?, class_name = ?, section = ?, subject = ?, teacher_id = ?,
        duration_minutes = ?, total_marks = ?, general_instructions = ?,
        sections_config = ?, updated_at = CURRENT_TIMESTAMP
    WHERE id = ?
    ''', (
        data.title, data.class_name, data.section, data.subject, data.teacher_id,
        data.duration_minutes, data.total_marks, data.general_instructions or '',
        json.dumps(data.sections_config), bp_id
    ))
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.delete("/api/blueprints/{bp_id}")
async def delete_blueprint(bp_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM questions WHERE blueprint_id = ?", (bp_id,))
    cursor.execute("DELETE FROM paper_blueprints WHERE id = ?", (bp_id,))
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.put("/api/blueprints/{bp_id}/status")
async def update_blueprint_status(bp_id: int, status: str = Form(...)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE paper_blueprints SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (status, bp_id))
    conn.commit()
    conn.close()
    return {"status": "success", "new_status": status}

# --- Questions Management ---
@app.post("/api/upload-diagram")
async def upload_diagram(file: UploadFile = File(...)):
    ext = Path(file.filename).suffix or ".png"
    import uuid
    filename = f"diag_{uuid.uuid4().hex[:10]}{ext}"
    save_path = os.path.join(UPLOADS_DIR, "diagrams", filename)
    with open(save_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    rel_path = f"uploads/diagrams/{filename}"
    return {"status": "success", "image_path": rel_path}

@app.post("/api/blueprints/{bp_id}/questions")
async def add_or_update_question(bp_id: int, q: QuestionItem):
    conn = get_db()
    cursor = conn.cursor()
    
    # Check if blueprint is already submitted
    cursor.execute("SELECT status FROM paper_blueprints WHERE id = ?", (bp_id,))
    bp_row = cursor.fetchone()
    if bp_row and bp_row['status'] in ('Questions_Submitted', 'Approved'):
        conn.close()
        raise HTTPException(status_code=403, detail="Paper is already submitted to the Admin and questions cannot be modified.")

    # Check if question number already exists in this blueprint
    cursor.execute("SELECT id FROM questions WHERE blueprint_id = ? AND question_number = ?", (bp_id, q.question_number))
    existing = cursor.fetchone()

    if existing:
        cursor.execute('''
        UPDATE questions
        SET section_id = ?, section_name = ?, question_type = ?, question_text = ?,
            options = ?, correct_answer = ?, solution_explanation = ?, marks = ?,
            image_path = ?, or_question_text = ?, or_image_path = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        ''', (
            q.section_id, q.section_name, q.question_type, q.question_text,
            json.dumps(q.options or []), q.correct_answer or '', q.solution_explanation or '',
            q.marks, q.image_path or '', q.or_question_text or '', q.or_image_path or '',
            existing['id']
        ))
        q_id = existing['id']
    else:
        cursor.execute('''
        INSERT INTO questions (
            blueprint_id, section_id, section_name, question_number, question_type,
            question_text, options, correct_answer, solution_explanation, marks,
            image_path, or_question_text, or_image_path
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            bp_id, q.section_id, q.section_name, q.question_number, q.question_type,
            q.question_text, json.dumps(q.options or []), q.correct_answer or '',
            q.solution_explanation or '', q.marks, q.image_path or '',
            q.or_question_text or '', q.or_image_path or ''
        ))
        q_id = cursor.lastrowid

    conn.commit()
    conn.close()
    return {"status": "success", "id": q_id}

@app.delete("/api/questions/{q_id}")
async def delete_question(q_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM questions WHERE id = ?", (q_id,))
    conn.commit()
    conn.close()
    return {"status": "success"}

# --- Teacher Phone Access Link Generation & Verification ---
@app.post("/api/teachers/{teacher_id}/generate-link")
async def generate_teacher_link(teacher_id: int, req: GenerateLinkRequest):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM teachers WHERE id = ?", (teacher_id,))
    teacher = cursor.fetchone()
    if not teacher:
        conn.close()
        raise HTTPException(status_code=404, detail="Teacher not found")
        
    # Get assigned blueprints
    cursor.execute("SELECT id, title, class_name, section, subject, status FROM paper_blueprints WHERE teacher_id = ?", (teacher_id,))
    blueprints = [dict(b) for b in cursor.fetchall()]

    # Check network scope and active tunnel / public url
    cursor.execute("SELECT network_scope, public_url FROM school_settings WHERE id = 1")
    net_row = dict(cursor.fetchone() or {})
    network_scope = net_row.get('network_scope', 'school_wifi')
    stored_public = net_row.get('public_url', '')

    tunnel_mgr = TunnelManager.get_instance()
    tunnel_status = tunnel_mgr.get_status()
    effective_public = tunnel_status.get('url') or stored_public
    
    token = secrets.token_urlsafe(24)
    expires_at = datetime.now() + timedelta(hours=req.validity_hours)
    
    cursor.execute('''
    INSERT INTO teacher_access_tokens (teacher_id, token, validity_hours, expires_at)
    VALUES (?, ?, ?, ?)
    ''', (teacher_id, token, req.validity_hours, expires_at.isoformat()))
    conn.commit()
    conn.close()
    
    ip = get_local_ip()
    port = 8000
    lan_portal_url = f"http://{ip}:{port}/portal?token={token}"

    if network_scope == 'any_network' and effective_public:
        portal_url = f"{effective_public.rstrip('/')}/portal?token={token}"
        network_label = "Any Network (Internet / Mobile Data)"
        is_internet = True
    else:
        portal_url = lan_portal_url
        network_label = "School Wi-Fi Only"
        is_internet = False

    qr_code = generate_qr_code(portal_url)
    
    return {
        "status": "success",
        "token": token,
        "portal_url": portal_url,
        "share_url": portal_url,
        "lan_url": lan_portal_url,
        "network_scope": network_scope,
        "network_label": network_label,
        "is_internet_accessible": is_internet,
        "qr_code": qr_code,
        "expires_at": expires_at.strftime("%Y-%m-%d %H:%M:%S"),
        "validity_hours": req.validity_hours,
        "teacher": {
            "id": teacher['id'],
            "name": teacher['name'],
            "email": teacher['email']
        },
        "assigned_blueprints": blueprints
    }

@app.get("/api/portal/verify-token")
async def verify_portal_token(request: Request, token: str):
    conn = get_db()
    cursor = conn.cursor()
    
    # Check wifi enabled and network scope
    cursor.execute("SELECT wifi_enabled, wifi_security_mode, enable_answer_key, network_scope, public_url FROM school_settings WHERE id = 1")
    settings = dict(cursor.fetchone() or {})
    
    if not settings.get('wifi_enabled', 1):
        conn.close()
        return JSONResponse(status_code=403, content={
            "status": "error",
            "error_type": "wifi_disabled",
            "message": "School Wi-Fi / LAN portal access has been turned OFF by the administrator."
        })

    # Network access scope check: if school_wifi, restrict to private/local network
    network_scope = settings.get('network_scope', 'school_wifi')
    if network_scope == 'school_wifi':
        forwarded = request.headers.get("x-forwarded-for", "")
        client_ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "")
        if client_ip:
            try:
                ip_obj = ipaddress.ip_address(client_ip)
                if not (ip_obj.is_private or ip_obj.is_loopback):
                    conn.close()
                    return JSONResponse(status_code=403, content={
                        "status": "error",
                        "error_type": "wifi_only_restriction",
                        "message": "Portal access is restricted to the School Wi-Fi network only. Please connect your device to the School Wi-Fi network to proceed."
                    })
            except ValueError:
                pass
        
    cursor.execute('''
    SELECT tat.*, t.name as teacher_name, t.email as teacher_email, t.pin as teacher_pin, t.phone as teacher_phone, t.assigned_classes
    FROM teacher_access_tokens tat
    JOIN teachers t ON tat.teacher_id = t.id
    WHERE tat.token = ? AND tat.is_active = 1
    ''', (token,))
    token_row = cursor.fetchone()
    if not token_row:
        conn.close()
        return JSONResponse(status_code=401, content={
            "status": "error",
            "error_type": "invalid_token",
            "message": "Invalid or inactive portal access link."
        })
        
    token_data = dict(token_row)
    try:
        expires_at = datetime.fromisoformat(token_data['expires_at'])
    except Exception:
        expires_at = datetime.strptime(token_data['expires_at'], "%Y-%m-%d %H:%M:%S")
        
    now = datetime.now()
    if now > expires_at:
        conn.close()
        return JSONResponse(status_code=401, content={
            "status": "error",
            "error_type": "token_expired",
            "message": f"This access link expired on {expires_at.strftime('%b %d, %Y at %I:%M %p')}. Please request a new link from the school administrator.",
            "expired_at": token_data['expires_at']
        })
        
    # Get assigned blueprints
    cursor.execute('''
    SELECT b.*, t.name as teacher_name
    FROM paper_blueprints b
    LEFT JOIN teachers t ON b.teacher_id = t.id
    WHERE b.teacher_id = ?
    ORDER BY b.id DESC
    ''', (token_data['teacher_id'],))
    bps = [dict(b) for b in cursor.fetchall()]
    
    for bp in bps:
        try:
            bp['sections_config'] = json.loads(bp['sections_config']) if bp['sections_config'] else []
        except Exception:
            bp['sections_config'] = []
        cursor.execute("SELECT COUNT(*) as cnt FROM questions WHERE blueprint_id = ?", (bp['id'],))
        bp['entered_questions_count'] = cursor.fetchone()['cnt']
        bp['target_questions_count'] = sum(s.get('count', 0) for s in bp['sections_config'])
        
    conn.close()
    
    remaining_secs = max(0, int((expires_at - now).total_seconds()))
    
    return {
        "status": "success",
        "teacher": {
            "id": token_data['teacher_id'],
            "name": token_data['teacher_name'],
            "email": token_data['teacher_email']
        },
        "assigned_blueprints": bps,
        "expires_at": token_data['expires_at'],
        "remaining_seconds": remaining_secs,
        "enable_answer_key": bool(settings.get('enable_answer_key', 1)),
        "wifi_security_mode": settings.get('wifi_security_mode', 'secure')
    }

# --- DOCX Generation Download ---
@app.get("/api/paper/{blueprint_id}/docx")
async def download_paper_docx(blueprint_id: int, answer_key: bool = False, include_answers: bool = False, role: Optional[str] = "admin"):
    if role == "teacher":
        raise HTTPException(status_code=403, detail="Teachers are not permitted to download question papers. Only school administrators have download privileges.")

    is_ak = bool(answer_key or include_answers)

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM school_settings WHERE id = 1")
    school = dict(cursor.fetchone() or {})

    if is_ak and not school.get('enable_answer_key', 1):
        conn.close()
        raise HTTPException(status_code=403, detail="Answer key feature is disabled by the administrator.")

    cursor.execute("SELECT * FROM paper_blueprints WHERE id = ?", (blueprint_id,))
    bp_row = cursor.fetchone()
    if not bp_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Blueprint not found")
    blueprint = dict(bp_row)

    cursor.execute("SELECT * FROM questions WHERE blueprint_id = ? ORDER BY question_number ASC", (blueprint_id,))
    questions = [dict(r) for r in cursor.fetchall()]
    conn.close()

    temp_dir = BASE_DIR / "temp"
    temp_dir.mkdir(exist_ok=True)

    suffix = "_Answer_Key" if is_ak else ""
    filename = f"{blueprint['class_name']}_{blueprint['subject']}{suffix}.docx".replace(" ", "_")
    output_path = temp_dir / filename

    generate_docx(blueprint, questions, school, str(output_path), is_answer_key=is_ak)

    return FileResponse(
        path=str(output_path),
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
