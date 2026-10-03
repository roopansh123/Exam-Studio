
import sqlite3
import os
import sys
import shutil
import json
from pathlib import Path

def get_app_data_dir():
    if getattr(sys, 'frozen', False):
        if sys.platform == "darwin":
            base = os.path.expanduser("~/Library/Application Support/LKCSExamStudio")
        elif sys.platform == "win32":
            exe_dir = os.path.dirname(sys.executable)
            try:
                test_file = os.path.join(exe_dir, ".test_write")
                with open(test_file, "w") as f:
                    f.write("ok")
                os.remove(test_file)
                base = os.path.join(exe_dir, "data")
            except Exception:
                base = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "LKCSExamStudio")
        else:
            base = os.path.expanduser("~/.lkcs_exam_studio")
    else:
        # Development mode: use workspace root
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.makedirs(base, exist_ok=True)
    return base

DATA_DIR = get_app_data_dir()
DB_PATH = os.path.join(DATA_DIR, "question_paper.db")
UPLOADS_DIR = os.path.join(DATA_DIR, "uploads")
os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(os.path.join(UPLOADS_DIR, "logos"), exist_ok=True)
os.makedirs(os.path.join(UPLOADS_DIR, "diagrams"), exist_ok=True)

# If running frozen and DB doesn't exist yet in persistent location, seed from bundle
if getattr(sys, 'frozen', False) and not os.path.exists(DB_PATH):
    seed_dir = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    seed_db = os.path.join(seed_dir, "question_paper.db")
    if os.path.exists(seed_db):
        try:
            shutil.copy2(seed_db, DB_PATH)
        except Exception as e:
            print("Notice: Could not seed question_paper.db:", e)

    seed_uploads = os.path.join(seed_dir, "uploads")
    if os.path.exists(seed_uploads):
        try:
            for root, dirs, files in os.walk(seed_uploads):
                rel_path = os.path.relpath(root, seed_uploads)
                target_dir = os.path.join(UPLOADS_DIR, rel_path)
                os.makedirs(target_dir, exist_ok=True)
                for file in files:
                    src_file = os.path.join(root, file)
                    dst_file = os.path.join(target_dir, file)
                    if not os.path.exists(dst_file):
                        shutil.copy2(src_file, dst_file)
        except Exception as e:
            print("Notice: Could not seed uploads:", e)

def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()

    # School & formatting settings
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS school_settings (
        id INTEGER PRIMARY KEY,
        school_name TEXT NOT NULL DEFAULT 'DELHI PUBLIC SCHOOL',
        school_name_font TEXT DEFAULT 'Old English Text MT',
        sub_title TEXT DEFAULT 'Affiliated to CBSE, New Delhi | Affiliation No. 123456',
        address TEXT DEFAULT 'Knowledge Park, Institutional Area, New Delhi - 110001',
        logo_path TEXT DEFAULT '',
        logo_size INTEGER DEFAULT 80,
        watermark_text TEXT DEFAULT 'CONFIDENTIAL',
        show_watermark INTEGER DEFAULT 0,
        font_family TEXT DEFAULT 'Calibri',
        font_size TEXT DEFAULT '11pt',
        line_spacing TEXT DEFAULT '1.15',
        page_layout TEXT DEFAULT '1-column',
        show_marks_box INTEGER DEFAULT 1,
        show_instructions INTEGER DEFAULT 1,
        header_border_style TEXT DEFAULT 'double',
        enable_answer_key INTEGER DEFAULT 1,
        wifi_enabled INTEGER DEFAULT 1,
        wifi_security_mode TEXT DEFAULT 'secure',
        wifi_passcode TEXT DEFAULT '',
        network_scope TEXT DEFAULT 'school_wifi', -- 'school_wifi' (School Wi-Fi Only) or 'any_network' (Internet/Anywhere)
        public_url TEXT DEFAULT '',               -- Custom domain or active tunnel public URL
        admin_username TEXT DEFAULT 'admin',
        admin_password TEXT DEFAULT 'admin123'
    )
    ''')

    # Ensure at least 1 default school setting row exists
    cursor.execute('SELECT COUNT(*) as cnt FROM school_settings')
    if cursor.fetchone()['cnt'] == 0:
        cursor.execute('''
        INSERT INTO school_settings (id, school_name, school_name_font, sub_title, address, logo_size, watermark_text, show_watermark, font_family, font_size, line_spacing, page_layout, enable_answer_key, wifi_enabled, wifi_security_mode, network_scope, public_url, admin_username, admin_password)
        VALUES (1, 'LORD KRISHNA CONVENT SCHOOL', 'Old English Text MT', 'Affiliated to Central Board of Secondary Education (CBSE)', 'Knowledge Campus, New Delhi', 80, 'CONFIDENTIAL - EXAM 2026', 0, 'Calibri', '11pt', '1.15', '1-column', 0, 1, 'secure', 'school_wifi', '', 'admin', 'admin123')
        ''')

    # Migration for existing databases that lack new columns
    cursor.execute("PRAGMA table_info(school_settings)")
    existing_cols = [r['name'] for r in cursor.fetchall()]
    if 'school_name_font' not in existing_cols:
        cursor.execute("ALTER TABLE school_settings ADD COLUMN school_name_font TEXT DEFAULT 'Old English Text MT'")
    if 'logo_size' not in existing_cols:
        cursor.execute("ALTER TABLE school_settings ADD COLUMN logo_size INTEGER DEFAULT 80")
    if 'enable_answer_key' not in existing_cols:
        cursor.execute("ALTER TABLE school_settings ADD COLUMN enable_answer_key INTEGER DEFAULT 1")
    if 'wifi_enabled' not in existing_cols:
        cursor.execute("ALTER TABLE school_settings ADD COLUMN wifi_enabled INTEGER DEFAULT 1")
    if 'wifi_security_mode' not in existing_cols:
        cursor.execute("ALTER TABLE school_settings ADD COLUMN wifi_security_mode TEXT DEFAULT 'secure'")
    if 'wifi_passcode' not in existing_cols:
        cursor.execute("ALTER TABLE school_settings ADD COLUMN wifi_passcode TEXT DEFAULT ''")
    if 'network_scope' not in existing_cols:
        cursor.execute("ALTER TABLE school_settings ADD COLUMN network_scope TEXT DEFAULT 'school_wifi'")
    if 'public_url' not in existing_cols:
        cursor.execute("ALTER TABLE school_settings ADD COLUMN public_url TEXT DEFAULT ''")
    if 'admin_username' not in existing_cols:
        cursor.execute("ALTER TABLE school_settings ADD COLUMN admin_username TEXT DEFAULT 'admin'")
    if 'admin_password' not in existing_cols:
        cursor.execute("ALTER TABLE school_settings ADD COLUMN admin_password TEXT DEFAULT 'admin123'")

    # If school name is still default placeholder, update to Lord Krishna Convent School
    cursor.execute("UPDATE school_settings SET school_name = 'LORD KRISHNA CONVENT SCHOOL' WHERE id = 1 AND (school_name LIKE '%SPRINGDALE%' OR school_name LIKE '%DELHI PUBLIC SCHOOL%')")

    # Teachers table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS teachers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        pin TEXT NOT NULL DEFAULT '1234',
        phone TEXT DEFAULT '',
        assigned_classes TEXT DEFAULT '[]', -- JSON list of class-section-subject e.g. [{"class": "Class 10", "section": "A", "subject": "Mathematics"}]
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # Seed an initial teacher if none exists
    cursor.execute('SELECT COUNT(*) as cnt FROM teachers')
    if cursor.fetchone()['cnt'] == 0:
        sample_assignments = json.dumps([
            {"class": "Class 10", "section": "A", "subject": "Mathematics"},
            {"class": "Class 10", "section": "B", "subject": "Science"},
            {"class": "Class 12", "section": "A", "subject": "Physics"}
        ])
        cursor.execute('''
        INSERT INTO teachers (name, email, pin, phone, assigned_classes)
        VALUES ('Dr. Sharma (Senior PGT)', 'sharma@school.edu', '1234', '9876543210', ?)
        ''', (sample_assignments,))

    # Question Paper Blueprint / Specifications
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS paper_blueprints (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,                         -- e.g. "Half Yearly Examination 2026-27"
        class_name TEXT NOT NULL,                    -- e.g. "Class 10"
        section TEXT NOT NULL,                       -- e.g. "A"
        subject TEXT NOT NULL,                       -- e.g. "Mathematics"
        teacher_id INTEGER,                          -- Assigned teacher ID
        duration_minutes INTEGER DEFAULT 180,        -- Duration in minutes
        total_marks REAL DEFAULT 80,                 -- Maximum marks
        general_instructions TEXT DEFAULT '',        -- General instructions text
        sections_config TEXT NOT NULL DEFAULT '[]',  -- JSON array of section blueprints
        status TEXT DEFAULT 'Assigned',              -- 'Draft', 'Assigned', 'Submitted', 'Approved'
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (teacher_id) REFERENCES teachers (id)
    )
    ''')

    # Questions table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        blueprint_id INTEGER NOT NULL,
        section_id TEXT NOT NULL,                    -- e.g. "sec_a", "sec_b"
        section_name TEXT NOT NULL,                  -- e.g. "Section A: Multiple Choice Questions"
        question_number INTEGER NOT NULL,            -- e.g. 1, 2, 3...
        question_type TEXT NOT NULL,                 -- 'MCQ', 'VSA', 'Short_Answer', 'Long_Answer', 'Fill_Blanks', 'True_False', 'Case_Study'
        question_text TEXT NOT NULL,
        options TEXT DEFAULT '[]',                   -- JSON array of options e.g. ["Option A", "Option B", "Option C", "Option D"]
        correct_answer TEXT DEFAULT '',              -- Correct answer or answer key
        solution_explanation TEXT DEFAULT '',        -- Marking scheme / explanation
        marks REAL NOT NULL DEFAULT 1.0,
        image_path TEXT DEFAULT '',                  -- Diagram / Image if any
        or_question_text TEXT DEFAULT '',            -- Optional OR choice question
        or_image_path TEXT DEFAULT '',               -- Optional OR image
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (blueprint_id) REFERENCES paper_blueprints (id) ON DELETE CASCADE
    )
    ''')

    # Teacher Access Tokens (for phone portal access with validity duration)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS teacher_access_tokens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        teacher_id INTEGER NOT NULL,
        token TEXT UNIQUE NOT NULL,
        validity_hours REAL NOT NULL DEFAULT 24,
        expires_at TIMESTAMP NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        is_active INTEGER DEFAULT 1,
        FOREIGN KEY (teacher_id) REFERENCES teachers (id) ON DELETE CASCADE
    )
    ''')

    # Seed a sample blueprint and questions if empty
    cursor.execute('SELECT COUNT(*) as cnt FROM paper_blueprints')
    if cursor.fetchone()['cnt'] == 0:
        sample_sections = json.dumps([
            {
                "id": "sec_a",
                "name": "Section A (Multiple Choice Questions)",
                "type": "MCQ",
                "count": 5,
                "marks_per_q": 1.0,
                "instruction": "Each question carries 1 mark. Select the correct alternative."
            },
            {
                "id": "sec_b",
                "name": "Section B (Short Answer Questions - I)",
                "type": "Short_Answer",
                "count": 3,
                "marks_per_q": 2.0,
                "instruction": "Each question carries 2 marks. Write concise answers."
            },
            {
                "id": "sec_c",
                "name": "Section C (Short Answer Questions - II)",
                "type": "Short_Answer",
                "count": 2,
                "marks_per_q": 3.0,
                "instruction": "Each question carries 3 marks. Show necessary steps."
            },
            {
                "id": "sec_d",
                "name": "Section D (Long Answer Questions)",
                "type": "Long_Answer",
                "count": 1,
                "marks_per_q": 5.0,
                "instruction": "Each question carries 5 marks. Internal choice is provided."
            }
        ])
        
        default_instructions = (
            "1. This question paper contains 11 questions divided into 4 Sections: A, B, C, and D.\n"
            "2. Section A comprises 5 questions of 1 mark each (Multiple Choice Questions).\n"
            "3. Section B comprises 3 questions of 2 marks each (Short Answer Type-I).\n"
            "4. Section C comprises 2 questions of 3 marks each (Short Answer Type-II).\n"
            "5. Section D comprises 1 question of 5 marks (Long Answer Type).\n"
            "6. All questions are compulsory. However, an internal choice in some questions has been provided.\n"
            "7. Use of calculators is strictly prohibited."
        )

        cursor.execute('''
        INSERT INTO paper_blueprints (title, class_name, section, subject, teacher_id, duration_minutes, total_marks, general_instructions, sections_config, status)
        VALUES ('Mid-Term Summative Assessment (2026-27)', 'Class 10', 'A', 'Mathematics', 1, 180, 22, ?, ?, 'Questions_Submitted')
        ''', (default_instructions, sample_sections))
        
        bp_id = cursor.lastrowid

        # Insert some sample questions with LaTeX and options
        sample_qs = [
            (bp_id, "sec_a", "Section A (Multiple Choice Questions)", 1, "MCQ",
             "If the HCF of 65 and 117 is expressible in the form $65m - 117$, then the value of $m$ is:",
             json.dumps(["4", "2", "1", "3"]), "2", "65 = 13 x 5, 117 = 13 x 9. HCF = 13. 65m - 117 = 13 => 65m = 130 => m = 2.", 1.0, "", "", ""),
            (bp_id, "sec_a", "Section A (Multiple Choice Questions)", 2, "MCQ",
             "The discriminant of the quadratic equation $2x^2 - 4x + 3 = 0$ is:",
             json.dumps(["-8", "10", "-16", "8"]), "-8", "D = b^2 - 4ac = (-4)^2 - 4(2)(3) = 16 - 24 = -8.", 1.0, "", "", ""),
            (bp_id, "sec_a", "Section A (Multiple Choice Questions)", 3, "MCQ",
             "The distance of the point $P(3, 4)$ from the x-axis is:",
             json.dumps(["3 units", "4 units", "5 units", "1 unit"]), "4 units", "Distance from x-axis is |y-coordinate| = 4 units.", 1.0, "", "", ""),
            (bp_id, "sec_a", "Section A (Multiple Choice Questions)", 4, "MCQ",
             "If $\\sin \\theta + \\cos \\theta = \\sqrt{2} \\cos \\theta$, then the value of $\\cos \\theta - \\sin \\theta$ is:",
             json.dumps(["$\\sqrt{2} \\sin \\theta$", "$\\sqrt{2}$", "$2 \\sin \\theta$", "$-\\sqrt{2} \\sin \\theta$"]), "$\\sqrt{2} \\sin \\theta$", "Squaring both sides and simplifying yields sqrt(2) sin theta.", 1.0, "", "", ""),
            (bp_id, "sec_a", "Section A (Multiple Choice Questions)", 5, "MCQ",
             "A card is drawn from a well-shuffled deck of 52 cards. The probability of getting a red face card is:",
             json.dumps(["3/26", "3/13", "1/26", "1/13"]), "3/26", "Number of red face cards = 6 (3 hearts + 3 diamonds). P = 6/52 = 3/26.", 1.0, "", "", ""),
            
            (bp_id, "sec_b", "Section B (Short Answer Questions - I)", 6, "Short_Answer",
             "Prove that $\\sqrt{5}$ is an irrational number.",
             "[]", "Assume sqrt(5) is rational = p/q (co-prime). 5 = p^2/q^2 => p^2 = 5q^2, contradicting co-prime assumption.", "Full mathematical proof step-by-step.", 2.0, "", "", ""),
            (bp_id, "sec_b", "Section B (Short Answer Questions - I)", 7, "Short_Answer",
             "Find the roots of the quadratic equation $x^2 - 3x - 10 = 0$ by factorization method.",
             "[]", "x = 5 or x = -2", "x^2 - 5x + 2x - 10 = 0 => (x - 5)(x + 2) = 0 => x = 5, -2.", 2.0, "", "", ""),
            (bp_id, "sec_b", "Section B (Short Answer Questions - I)", 8, "Short_Answer",
             "Find the 10th term of the Arithmetic Progression: $2, 7, 12, \\dots$",
             "[]", "47", "a = 2, d = 5. a_10 = a + 9d = 2 + 9(5) = 47.", 2.0, "", "", ""),
            
            (bp_id, "sec_c", "Section C (Short Answer Questions - II)", 9, "Short_Answer",
             "Prove that the tangents drawn from an external point to a circle are equal in length.",
             "[]", "Geometry proof using RHS congruence theorem in right triangles.", "Draw circle with center O, tangents PA and PB from P. Prove triangle OPA congruent to triangle OPB.", 3.0, "", "", ""),
            (bp_id, "sec_c", "Section C (Short Answer Questions - II)", 10, "Short_Answer",
             "From a point on the ground, the angle of elevation of the top of a tower is observed to be $30^\\circ$. On walking $20\\text{ m}$ towards the tower, the angle of elevation becomes $60^\\circ$. Find the height of the tower.",
             "[]", "Height = 10 * sqrt(3) meters (approx 17.32 m)", "Use tan(30) = h/(x+20) and tan(60) = h/x. Solve for h.", 3.0, "", "", ""),
            
            (bp_id, "sec_d", "Section D (Long Answer Questions)", 11, "Long_Answer",
             "State and prove Basic Proportionality Theorem (Thales's Theorem).",
             "[]", "Statement: If a line is drawn parallel to one side of a triangle intersecting other two sides, then it divides the two sides in same ratio. Proof with construction.", "Marks breakdown: Statement 1m, Given & Construction 1m, Proof 3m.", 5.0, "",
             "OR\nA straight highway leads to the foot of a tower. A man standing at the top of the tower observes a car at an angle of depression of $30^\\circ$, which is approaching the foot of the tower with a uniform speed. Six seconds later, the angle of depression of the car is found to be $60^\\circ$. Find the time taken by the car to reach the foot of the tower from this point.", "")
        ]

        cursor.executemany('''
        INSERT INTO questions (blueprint_id, section_id, section_name, question_number, question_type, question_text, options, correct_answer, solution_explanation, marks, image_path, or_question_text, or_image_path)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', sample_qs)

    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")
