import os
import sys
import shutil
import subprocess
import time
import socket
import re
import json
import urllib.parse
import urllib.request
import ssl
import io
import base64
import logging
from typing import Dict, Any, Optional, List, Tuple

import qrcode
from .database import get_db

logger = logging.getLogger("LKCS-WhatsApp")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] [WhatsApp] %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def sanitize_phone(phone: Optional[str]) -> str:
    """Standardizes phone numbers into E.164 digits format (e.g., 919876543210)."""
    if not phone:
        return ""
    digits = re.sub(r"\D", "", str(phone))
    # If 10 digits starting with 6-9, assume Indian mobile number (+91)
    if len(digits) == 10 and digits[0] in "6789":
        digits = "91" + digits
    # If 11 digits starting with 0, replace 0 with 91
    elif len(digits) == 11 and digits.startswith("0"):
        digits = "91" + digits[1:]
    return digits


def get_school_and_whatsapp_settings() -> Dict[str, Any]:
    """Fetches school info and WhatsApp configuration from school_settings table."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM school_settings WHERE id = 1")
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return {}


class WhatsAppBotManager:
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self._bridge_proc = None
        self._bridge_port = 3001
        self._bridge_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "whatsapp_bridge")

    def is_bridge_port_open(self) -> bool:
        """Checks if bridge HTTP port 3001 is listening."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.5)
                return s.connect_ex(("127.0.0.1", self._bridge_port)) == 0
        except Exception:
            return False

    def ensure_bridge_running(self, python_port: int = 8000) -> bool:
        """Starts the Baileys Node.js microservice if not already running."""
        # 1. If already listening, configure python port and return True
        if self.is_bridge_port_open():
            self._configure_bridge_python_port(python_port)
            return True

        # 2. Check if node is installed
        node_bin = shutil.which("node")
        if not node_bin:
            logger.warning("Node.js is not found in PATH. WhatsApp Barcode bridge cannot start automatically.")
            return False

        server_script = os.path.join(self._bridge_dir, "server.js")
        if not os.path.exists(server_script):
            logger.error(f"WhatsApp bridge server script missing: {server_script}")
            return False

        env = os.environ.copy()
        env["WA_BRIDGE_PORT"] = str(self._bridge_port)
        env["PYTHON_PORT"] = str(python_port)

        try:
            logger.info("Spawning WhatsApp Baileys Barcode Bridge microservice...")
            self._bridge_proc = subprocess.Popen(
                [node_bin, server_script],
                cwd=self._bridge_dir,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            # Wait up to 4 seconds for port 3001 to open
            for _ in range(20):
                time.sleep(0.2)
                if self.is_bridge_port_open():
                    logger.info("WhatsApp Barcode Bridge microservice started and listening on port 3001.")
                    self._configure_bridge_python_port(python_port)
                    return True
            return False
        except Exception as e:
            logger.error(f"Failed to start WhatsApp bridge process: {e}")
            return False

    def _configure_bridge_python_port(self, python_port: int):
        """Notifies the Node bridge of the active Python port for incoming messages."""
        try:
            payload = json.dumps({"python_port": python_port}).encode("utf-8")
            req = urllib.request.Request(
                f"http://127.0.0.1:{self._bridge_port}/configure",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=2) as resp:
                pass
        except Exception:
            pass

    def get_bridge_status(self) -> Dict[str, Any]:
        """Queries the live connection and barcode status from the Node bridge."""
        if not self.is_bridge_port_open():
            return {
                "available": False,
                "status": "offline",
                "connected": False,
                "qr_code": None,
                "phone": None
            }
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{self._bridge_port}/status", method="GET")
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return {
                    "available": True,
                    "status": data.get("status", "unknown"),
                    "connected": bool(data.get("connected", False)),
                    "qr_code": data.get("qr_code"),
                    "phone": data.get("phone")
                }
        except Exception as e:
            return {
                "available": False,
                "status": "error",
                "connected": False,
                "qr_code": None,
                "phone": None,
                "error": str(e)
            }

    def send_bridge_whatsapp_message(self, to_phone: str, message_text: str) -> Dict[str, Any]:
        """Sends an outgoing message via the linked WhatsApp Web session."""
        clean_phone = sanitize_phone(to_phone)
        if not clean_phone:
            return {"success": False, "error": "Invalid recipient phone number."}

        if not self.is_bridge_port_open():
            return {"success": False, "error": "WhatsApp Barcode bridge is offline. Please scan the barcode first."}

        try:
            payload = json.dumps({"phone": clean_phone, "message": message_text}).encode("utf-8")
            req = urllib.request.Request(
                f"http://127.0.0.1:{self._bridge_port}/send-message",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data
        except urllib.error.HTTPError as he:
            err_body = he.read().decode("utf-8")
            try:
                err_json = json.loads(err_body)
                return {"success": False, "error": err_json.get("error", err_body)}
            except Exception:
                return {"success": False, "error": err_body}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def bridge_logout(self) -> Dict[str, Any]:
        """Unlinks the device and resets the WhatsApp session."""
        if not self.is_bridge_port_open():
            return {"success": True, "message": "Bridge is offline."}
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{self._bridge_port}/logout",
                data=b"{}",
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            return {"success": False, "error": str(e)}

    def send_message_smart(self, to_phone: str, message_text: str) -> Dict[str, Any]:
        """Sends message via linked WhatsApp Barcode session if connected, or Meta Cloud API if configured."""
        bridge_status = self.get_bridge_status()
        if bridge_status.get("connected"):
            res = self.send_bridge_whatsapp_message(to_phone, message_text)
            if res.get("success"):
                res["channel"] = "linked_device"
                return res

        # Fallback to Meta Cloud API if configured
        settings = get_school_and_whatsapp_settings()
        if settings.get("whatsapp_access_token") and settings.get("whatsapp_phone_number_id"):
            res = self.send_meta_whatsapp_message(to_phone, message_text)
            if res.get("success"):
                res["channel"] = "cloud_api"
                return res
            return res

        if not bridge_status.get("connected"):
            return {
                "success": False,
                "error": "WhatsApp is not connected. Please scan the official WhatsApp Barcode in Settings to connect your phone."
            }
        return {"success": False, "error": "Unable to deliver WhatsApp message."}

    # -------------------------------------------------------------
    # 1. Blueprint Formatting & Sharing
    # -------------------------------------------------------------
    def format_blueprint_message(self, blueprint_id: int, base_url: str = "") -> Tuple[str, Optional[Dict[str, Any]]]:
        """Formats an assigned question paper blueprint into a structured WhatsApp message."""
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM school_settings WHERE id = 1")
        settings = dict(cursor.fetchone() or {})

        cursor.execute("SELECT * FROM paper_blueprints WHERE id = ?", (blueprint_id,))
        bp_row = cursor.fetchone()
        if not bp_row:
            conn.close()
            return "Blueprint not found.", None
        bp = dict(bp_row)

        teacher = None
        if bp.get("teacher_id"):
            cursor.execute("SELECT * FROM teachers WHERE id = ?", (bp["teacher_id"],))
            t_row = cursor.fetchone()
            if t_row:
                teacher = dict(t_row)
        conn.close()

        school_name = settings.get("school_name", "LORD KRISHNA CONVENT SCHOOL").strip()
        sections_config = []
        try:
            sections_config = json.loads(bp.get("sections_config") or "[]")
        except Exception:
            pass

        # Build sections summary
        sections_lines = []
        for sec in sections_config:
            name = sec.get("name", "Section")
            q_count = sec.get("question_count", 0)
            marks_per = sec.get("marks_per_question", 1)
            total_sec_marks = float(q_count) * float(marks_per)
            q_type = sec.get("question_type", "Standard").replace("_", " ").title()
            choice = f" (Choice: {sec.get('internal_choice_count', 0)})" if sec.get("internal_choice_count") else ""
            sections_lines.append(
                f"• *{name}* ({total_sec_marks:g} Marks): {q_count} Questions × {marks_per:g}m each [{q_type}]{choice}"
            )
        sections_str = "\n".join(sections_lines) if sections_lines else "• Standard format."

        teacher_name = teacher.get("name", "Respected Teacher") if teacher else "Faculty Member"
        duration = bp.get("duration_minutes", 180)
        total_marks = bp.get("total_marks", 80)
        instructions = bp.get("general_instructions") or "Follow standard CBSE guidelines."

        # Submission portal URL
        effective_base = base_url.rstrip("/") if base_url else (settings.get("public_url") or "http://localhost:8000").rstrip("/")
        portal_url = f"{effective_base}/?role=teacher"

        msg = (
            f"🏛️ *{school_name}*\n"
            f"📋 *EXAM PAPER BLUEPRINT ASSIGNMENT*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👨‍🏫 *Teacher:* {teacher_name}\n"
            f"📚 *Class & Subject:* *{bp.get('class_name')}* — *{bp.get('subject')}*\n"
            f"📝 *Exam Title:* {bp.get('title')}\n"
            f"⏱️ *Duration:* {duration} Minutes | 🎯 *Total Marks:* {total_marks:g} Marks\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📌 *SECTIONS BLUEPRINT & MARKS BREAKDOWN:*\n"
            f"{sections_str}\n\n"
            f"💡 *General Instructions:*\n"
            f"_{instructions.strip()}_\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📱 *OPTION 1: One-Tap Mobile Portal (No Login Required)*\n"
            f"👉 {portal_url}\n\n"
            f"💬 *OPTION 2: Submit Directly In This WhatsApp Chat!*\n"
            f"You can submit questions right here! Just reply with:\n"
            f"`Section A: What is the unit of force? (1 Mark)`\n"
            f"`A) Newton  B) Joule  C) Watt  D) Pascal`\n\n"
            f"Commands you can send:\n"
            f"• *STATUS* — Review submitted questions\n"
            f"• *BLUEPRINT* — View this blueprint again\n"
            f"• *SUBMIT* — Lock & submit paper to Exam Cell\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"_LKCS Exam Studio Automated Academic Portal_"
        )

        return msg, {"blueprint": bp, "teacher": teacher, "school": settings, "portal_url": portal_url}

    def generate_wa_me_link(self, phone: str, text: str) -> str:
        """Generates a standard click-to-chat WhatsApp deep link."""
        clean_phone = sanitize_phone(phone)
        encoded_text = urllib.parse.quote(text)
        if clean_phone:
            return f"https://wa.me/{clean_phone}?text={encoded_text}"
        return f"https://wa.me/?text={encoded_text}"

    def generate_qr_code_base64(self, text_or_url: str) -> str:
        """Generates a base64 encoded PNG QR code for barcode/QR scanning in the browser."""
        payload = str(text_or_url or "")
        # If payload is overly long for a QR code, keep compact URL
        if len(payload) > 600 and "wa.me" in payload:
            base_url = payload.split("?")[0]
            payload = f"{base_url}?text=BLUEPRINT"

        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=7,
            border=2
        )
        qr.add_data(payload)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#0f172a", back_color="#ffffff")
        
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        b64_data = base64.b64encode(buffer.getvalue()).decode("utf-8")
        return f"data:image/png;base64,{b64_data}"

    # -------------------------------------------------------------
    # 2. Meta WhatsApp Cloud API Sender
    # -------------------------------------------------------------
    def send_meta_whatsapp_message(self, to_phone: str, message_text: str) -> Dict[str, Any]:
        """Sends an outgoing message using Meta WhatsApp Cloud API."""
        settings = get_school_and_whatsapp_settings()
        phone_number_id = settings.get("whatsapp_phone_number_id", "").strip()
        access_token = settings.get("whatsapp_access_token", "").strip()

        if not phone_number_id or not access_token:
            logger.warning("WhatsApp Cloud API credentials not configured.")
            return {"success": False, "error": "WhatsApp Cloud API credentials not configured in School Settings."}

        clean_recipient = sanitize_phone(to_phone)
        if not clean_recipient:
            return {"success": False, "error": "Invalid recipient phone number."}

        url = f"https://graph.facebook.com/v19.0/{phone_number_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": clean_recipient,
            "type": "text",
            "text": {
                "preview_url": True,
                "body": message_text
            }
        }

        data_bytes = json.dumps(payload).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

        req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")
        try:
            # SSL fallback
            try:
                ctx = ssl.create_default_context()
            except Exception:
                ctx = ssl._create_unverified_context()

            with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
                resp_data = resp.read().decode("utf-8")
                parsed = json.loads(resp_data)
                logger.info(f"WhatsApp Cloud API message sent to {clean_recipient}: {parsed}")
                return {"success": True, "data": parsed}
        except urllib.error.HTTPError as he:
            err_body = he.read().decode("utf-8")
            logger.error(f"Meta WhatsApp API HTTPError ({he.code}): {err_body}")
            return {"success": False, "error": f"Meta API HTTP {he.code}: {err_body}"}
        except Exception as e:
            logger.error(f"Meta WhatsApp API connection failure: {e}")
            return {"success": False, "error": str(e)}

    # -------------------------------------------------------------
    # 3. Conversational Bot Logic & Question Parser
    # -------------------------------------------------------------
    def handle_incoming_message(self, from_phone: str, message_text: str) -> str:
        """Processes incoming WhatsApp messages from teachers and automatically saves questions."""
        raw_msg = (message_text or "").strip()
        if not raw_msg:
            return "Please send a valid message or question."

        clean_from = sanitize_phone(from_phone)
        phone_suffix = clean_from[-10:] if len(clean_from) >= 10 else clean_from

        conn = get_db()
        cursor = conn.cursor()

        # Find teacher by phone (matching last 10 digits)
        cursor.execute("SELECT * FROM teachers")
        teachers = [dict(r) for r in cursor.fetchall()]
        teacher = None
        for t in teachers:
            t_clean = sanitize_phone(t.get("phone", ""))
            if t_clean and (t_clean[-10:] == phone_suffix or t_clean == clean_from):
                teacher = t
                break

        cursor.execute("SELECT school_name, public_url FROM school_settings WHERE id = 1")
        school_info = dict(cursor.fetchone() or {})
        school_name = school_info.get("school_name", "Lord Krishna Convent School")

        if not teacher:
            conn.close()
            return (
                f"👋 *Welcome to {school_name} Exam Studio!*\n\n"
                f"Your phone number (+{clean_from}) is not yet registered in the Teacher Directory.\n"
                f"Please request the School Exam In-charge or Admin to add your phone number in *Teacher Management*."
            )

        # Teacher recognized! Find assigned blueprints
        cursor.execute(
            """
            SELECT * FROM paper_blueprints 
            WHERE teacher_id = ? 
            ORDER BY id DESC
            """, 
            (teacher["id"],)
        )
        assigned_bps = [dict(r) for r in cursor.fetchall()]

        if not assigned_bps:
            conn.close()
            return (
                f"Hello *{teacher['name']}*! 👋\n\n"
                f"You currently have no exam paper blueprints assigned to your profile in {school_name}.\n"
                f"Once the Examination Head assigns a paper to you, you will receive the blueprint structure here."
            )

        # Default to the most active/recent blueprint
        active_bp = assigned_bps[0]

        upper_cmd = raw_msg.upper().strip()

        # Command: HELP / HI / START
        if upper_cmd in ["HI", "HELLO", "START", "HELP", "MENU"]:
            conn.close()
            bp_list = "\n".join([f"• ID #{b['id']}: *{b['class_name']} {b['subject']}* ({b['title']}) [{b['status']}]" for b in assigned_bps])
            return (
                f"Hello *{teacher['name']}*! 👋\n"
                f"Welcome to the *{school_name} Exam Studio Bot*.\n\n"
                f"📋 *Your Assigned Exam Papers:*\n"
                f"{bp_list}\n\n"
                f"💬 *Commands Available:*\n"
                f"• *STATUS* — View your question submission progress\n"
                f"• *BLUEPRINT* — View section guidelines & marks\n"
                f"• *SUBMIT* — Lock & submit paper to Exam Cell\n\n"
                f"📝 *How to Submit Questions:*\n"
                f"Type questions directly in this chat! For example:\n"
                f"`Section A: What is photosynthesis? (1 Mark)`\n"
                f"`A) Process to make food  B) Process of breathing`"
            )

        # Command: BLUEPRINT
        if upper_cmd in ["BLUEPRINT", "BP", "PAPERS", "STRUCTURE"]:
            msg, _ = self.format_blueprint_message(active_bp["id"], base_url=school_info.get("public_url", ""))
            conn.close()
            return msg

        # Command: STATUS / REVIEW / PROGRESS
        if upper_cmd in ["STATUS", "REVIEW", "PROGRESS", "SUMMARY"]:
            cursor.execute("SELECT * FROM questions WHERE blueprint_id = ? ORDER BY id ASC", (active_bp["id"],))
            existing_questions = [dict(r) for r in cursor.fetchall()]
            conn.close()

            sections_config = []
            try:
                sections_config = json.loads(active_bp.get("sections_config") or "[]")
            except Exception:
                pass

            status_lines = []
            total_target = 0
            total_current = len(existing_questions)

            for sec in sections_config:
                sec_id = sec.get("id")
                sec_name = sec.get("name", "Section")
                target = sec.get("question_count", 0)
                total_target += target
                sec_qs = [q for q in existing_questions if q.get("section_id") == sec_id]
                status_lines.append(f"• *{sec_name}*: {len(sec_qs)} / {target} questions submitted")

            progress_str = "\n".join(status_lines) if status_lines else "No sections configured."

            return (
                f"📊 *Question Paper Progress: {active_bp['class_name']} {active_bp['subject']}*\n"
                f"Status: *{active_bp['status']}*\n"
                f"Overall: *{total_current} / {total_target}* questions entered\n\n"
                f"{progress_str}\n\n"
                f"Reply with your next question or type *SUBMIT* when you have completed all sections."
            )

        # Command: SUBMIT / FINISH
        if upper_cmd in ["SUBMIT", "FINISH", "LOCK"]:
            cursor.execute(
                "UPDATE paper_blueprints SET status = 'Questions_Submitted', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (active_bp["id"],)
            )
            conn.commit()
            conn.close()
            return (
                f"🎉 *Paper Submitted Successfully!*\n\n"
                f"Dear *{teacher['name']}*, your question paper for *{active_bp['class_name']} {active_bp['subject']}* "
                f"has been marked as *Submitted* and forwarded to the Examination Department for review.\n\n"
                f"Thank you for your academic contribution to {school_name}!"
            )

        # -------------------------------------------------------------
        # Parse Incoming Text as a Question!
        # -------------------------------------------------------------
        sections_config = []
        try:
            sections_config = json.loads(active_bp.get("sections_config") or "[]")
        except Exception:
            pass

        # Detect Section
        target_sec = None
        # Check if message mentions "Section A", "Sec B", "Section-C", etc.
        sec_match = re.search(r"\b(?:section|sec)\s*[-:]?\s*([a-zA-Z0-9]+)\b", raw_msg, re.IGNORECASE)
        if sec_match:
            sec_letter = sec_match.group(1).upper()
            for s in sections_config:
                s_name = s.get("name", "").upper()
                if sec_letter in s_name or f"SECTION {sec_letter}" in s_name or s.get("id", "").endswith(sec_letter.lower()):
                    target_sec = s
                    break

        # If not explicitly specified, find the first section that still needs questions
        if not target_sec:
            cursor.execute("SELECT section_id, COUNT(*) as cnt FROM questions WHERE blueprint_id = ? GROUP BY section_id", (active_bp["id"],))
            counts = {r["section_id"]: r["cnt"] for r in cursor.fetchall()}
            for s in sections_config:
                if counts.get(s["id"], 0) < s.get("question_count", 0):
                    target_sec = s
                    break

        if not target_sec and sections_config:
            target_sec = sections_config[0]

        target_sec_id = target_sec.get("id", "sec_a") if target_sec else "sec_a"
        target_sec_name = target_sec.get("name", "Section A") if target_sec else "Section A"
        default_marks = float(target_sec.get("marks_per_question", 1) if target_sec else 1)

        # Extract marks if specified in text (e.g. "(2 marks)", "[3m]", "4 marks")
        marks = default_marks
        mark_match = re.search(r"\(?\s*(\d+(?:\.\d+)?)\s*(?:marks?|m)\s*\)?", raw_msg, re.IGNORECASE)
        if mark_match:
            try:
                marks = float(mark_match.group(1))
            except Exception:
                marks = default_marks

        # Clean question text: strip leading section/mark prefixes
        cleaned_question = raw_msg
        cleaned_question = re.sub(r"^(?:section|sec)\s*[-:]?\s*[a-zA-Z0-9]+[:\s-]*", "", cleaned_question, flags=re.IGNORECASE)
        cleaned_question = re.sub(r"\(?\s*\d+(?:\.\d+)?\s*(?:marks?|m)\s*\)?$", "", cleaned_question, flags=re.IGNORECASE).strip()

        # Check for MCQ Options (A) ... B) ...)
        options = []
        q_type = "Short_Answer"
        opt_matches = list(re.finditer(r"\b([A-Da-d])[\.\)]\s*(.*?)(?=\b[A-Da-d][\.\)]|$)", cleaned_question))
        if len(opt_matches) >= 2:
            q_type = "MCQ"
            main_q = cleaned_question[:opt_matches[0].start()].strip()
            for m in opt_matches:
                opt_letter = m.group(1).upper()
                opt_val = m.group(2).strip()
                options.append(f"{opt_letter}) {opt_val}")
            if main_q:
                cleaned_question = main_q
        elif marks >= 5:
            q_type = "Long_Answer"
        elif marks == 1:
            q_type = "VSA"

        # Determine next question number
        cursor.execute("SELECT MAX(question_number) as max_num FROM questions WHERE blueprint_id = ?", (active_bp["id"],))
        max_row = cursor.fetchone()
        next_q_num = ((max_row["max_num"] if max_row else 0) or 0) + 1

        # Save question to SQLite DB matching exact database schema
        cursor.execute(
            """
            INSERT INTO questions (
                blueprint_id, section_id, section_name, question_number, question_type,
                question_text, options, correct_answer, solution_explanation, marks,
                image_path, or_question_text, or_image_path
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, '', '', ?, '', '', '')
            """,
            (
                active_bp["id"], target_sec_id, target_sec_name, next_q_num, q_type,
                cleaned_question, json.dumps(options), marks
            )
        )
        conn.commit()

        # Check updated section count
        cursor.execute("SELECT COUNT(*) as cnt FROM questions WHERE blueprint_id = ? AND section_id = ?", (active_bp["id"], target_sec_id))
        cur_count = cursor.fetchone()["cnt"]
        target_count = target_sec.get("question_count", 0) if target_sec else 0

        conn.close()

        q_preview = cleaned_question[:80] + ("..." if len(cleaned_question) > 80 else "")
        return (
            f"✅ *Question Saved Successfully!*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📁 *Section:* {target_sec_name} ({marks:g} Marks)\n"
            f"📝 *Question:* {q_preview}\n"
            f"📊 *Section Progress:* {cur_count} / {target_count} questions\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"Send your next question, or type *STATUS* to review all."
        )
