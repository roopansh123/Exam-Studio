import os
import json
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn

def set_cell_margins(cell, top=100, bottom=100, left=150, right=150):
    """Set inner padding for table cell."""
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    tcMar = OxmlElement('w:tcMar')
    for m, val in [('top', top), ('bottom', bottom), ('left', left), ('right', right)]:
        node = OxmlElement(f'w:{m}')
        node.set(qn('w:w'), str(val))
        node.set(qn('w:type'), 'dxa')
        tcMar.append(node)
    tcPr.append(tcMar)

def set_cell_background(cell, hex_color):
    """Set background color for a table cell."""
    shading_elm = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{hex_color}"/>')
    cell._tc.get_or_add_tcPr().append(shading_elm)

def generate_docx(blueprint_data: dict, questions: list, school_settings: dict, output_path: str, is_answer_key: bool = False):
    """
    Generates a beautifully formatted Question Paper or Answer Key DOCX file.
    """
    doc = Document()
    
    # 1. Page Margins
    for section in doc.sections:
        section.top_margin = Inches(0.65)
        section.bottom_margin = Inches(0.65)
        section.left_margin = Inches(0.75)
        section.right_margin = Inches(0.75)

    font_name = school_settings.get('font_family', 'Calibri')
    font_size_raw = str(school_settings.get('font_size', '11pt')).replace('pt', '').strip()
    try:
        base_font_size = float(font_size_raw)
    except Exception:
        base_font_size = 11.0

    # Style defaults
    style = doc.styles['Normal']
    font = style.font
    font.name = font_name
    font.size = Pt(base_font_size)
    font.color.rgb = RGBColor(30, 41, 59) # Slate 800

    # 2. School Header (Logo + Title)
    logo_path = school_settings.get('logo_path', '')
    school_name = school_settings.get('school_name', 'LORD KRISHNA CONVENT SCHOOL').upper()
    sub_title = school_settings.get('sub_title', 'Affiliated to Central Board of Secondary Education (CBSE)')
    address = school_settings.get('address', '')
    watermark_text = school_settings.get('watermark_text', '')
    show_watermark = school_settings.get('show_watermark', 0)

    school_name_font = school_settings.get('school_name_font') or "Canterbury"

    # Header Table
    if logo_path and os.path.exists(logo_path):
        header_table = doc.add_table(rows=1, cols=2)
        header_table.alignment = WD_TABLE_ALIGNMENT.CENTER
        header_table.autofit = False
        
        # Logo cell with adjustable logo size
        logo_size_px = school_settings.get('logo_size', 80) or 80
        logo_width_in = max(0.5, min(3.0, float(logo_size_px) / 72.0))
        cell_logo = header_table.cell(0, 0)
        cell_logo.width = Inches(logo_width_in + 0.2)
        p_logo = cell_logo.paragraphs[0]
        p_logo.alignment = WD_ALIGN_PARAGRAPH.CENTER
        try:
            p_logo.add_run().add_picture(logo_path, width=Inches(logo_width_in))
        except Exception as e:
            print(f"Error adding logo: {e}")

        # Text cell
        cell_text = header_table.cell(0, 1)
        cell_text.width = Inches(max(4.0, 7.0 - logo_width_in))
        p_name = cell_text.paragraphs[0]
        p_name.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r_name = p_name.add_run(school_name + "\n")
        r_name.font.name = school_name_font
        r_name.font.size = Pt(20)
        r_name.font.bold = True
        r_name.font.color.rgb = RGBColor(15, 23, 42)

        if sub_title:
            r_sub = p_name.add_run(sub_title + "\n")
            r_sub.font.size = Pt(9.5)
            r_sub.font.italic = True
            r_sub.font.color.rgb = RGBColor(71, 85, 105)

        if address:
            r_addr = p_name.add_run(address)
            r_addr.font.size = Pt(8.5)
            r_addr.font.color.rgb = RGBColor(100, 116, 139)
    else:
        # Centered text header
        p_name = doc.add_paragraph()
        p_name.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_name.paragraph_format.space_after = Pt(2)
        r_name = p_name.add_run(school_name)
        r_name.font.name = school_name_font
        r_name.font.size = Pt(22)
        r_name.font.bold = True
        r_name.font.color.rgb = RGBColor(15, 23, 42)

        if sub_title:
            p_sub = doc.add_paragraph()
            p_sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p_sub.paragraph_format.space_after = Pt(1)
            r_sub = p_sub.add_run(sub_title)
            r_sub.font.size = Pt(10)
            r_sub.font.italic = True
            r_sub.font.color.rgb = RGBColor(71, 85, 105)

        if address:
            p_addr = doc.add_paragraph()
            p_addr.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p_addr.paragraph_format.space_after = Pt(4)
            r_addr = p_addr.add_run(address)
            r_addr.font.size = Pt(8.5)
            r_addr.font.color.rgb = RGBColor(100, 116, 139)

    # Exam Title
    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_title.paragraph_format.space_before = Pt(4)
    p_title.paragraph_format.space_after = Pt(6)
    
    exam_heading = blueprint_data.get('title', 'Examination').upper()
    if is_answer_key:
        exam_heading += " - [ANSWER KEY & MARKING SCHEME]"
    
    r_title = p_title.add_run(exam_heading)
    r_title.font.size = Pt(13)
    r_title.font.bold = True
    r_title.font.underline = True

    # 3. Exam Details Box (Class, Section, Subject, Time, Max Marks)
    details_table = doc.add_table(rows=2, cols=3)
    details_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    details_table.autofit = False

    cls_val = blueprint_data.get('class_name', '')
    sec_val = (blueprint_data.get('section') or '').strip()
    class_info = f"Class: {cls_val} ({sec_val})" if sec_val else f"Class: {cls_val}"
    subj_info = f"Subject: {blueprint_data.get('subject', '')}"
    time_info = f"Time Allowed: {blueprint_data.get('duration_minutes', 180)} Mins"
    marks_info = f"Maximum Marks: {blueprint_data.get('total_marks', 80)}"
    roll_info = "Roll No: ________________"
    date_info = "Date: ____________"

    # Fill details
    row0 = details_table.rows[0]
    row0.cells[0].paragraphs[0].add_run(class_info).font.bold = True
    row0.cells[1].paragraphs[0].add_run(subj_info).font.bold = True
    p_roll = row0.cells[2].paragraphs[0]
    p_roll.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    p_roll.add_run(roll_info).font.bold = True

    row1 = details_table.rows[1]
    row1.cells[0].paragraphs[0].add_run(time_info).font.bold = True
    row1.cells[1].paragraphs[0].add_run(marks_info).font.bold = True
    p_date = row1.cells[2].paragraphs[0]
    p_date.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    p_date.add_run(date_info).font.bold = True

    for r in details_table.rows:
        for c in r.cells:
            set_cell_margins(c, top=60, bottom=60, left=60, right=60)
            c.paragraphs[0].runs[0].font.size = Pt(10)

    # 4. General Instructions
    instructions = blueprint_data.get('general_instructions', '')
    if instructions and not is_answer_key and school_settings.get('show_instructions', 1):
        p_inst_head = doc.add_paragraph()
        p_inst_head.paragraph_format.space_before = Pt(8)
        p_inst_head.paragraph_format.space_after = Pt(2)
        r_inst_head = p_inst_head.add_run("General Instructions:")
        r_inst_head.font.size = Pt(10)
        r_inst_head.font.bold = True

        for line in instructions.split('\n'):
            line = line.strip()
            if line:
                p_line = doc.add_paragraph()
                p_line.paragraph_format.left_indent = Inches(0.2)
                p_line.paragraph_format.space_after = Pt(1)
                p_line.paragraph_format.line_spacing = 1.05
                r_line = p_line.add_run(line)
                r_line.font.size = Pt(9.5)
                r_line.font.italic = True
                r_line.font.color.rgb = RGBColor(51, 65, 85)

    # Divider line
    p_div = doc.add_paragraph()
    p_div.paragraph_format.space_before = Pt(4)
    p_div.paragraph_format.space_after = Pt(8)
    p_div_run = p_div.add_run("―" * 58)
    p_div_run.font.color.rgb = RGBColor(148, 163, 184)
    p_div.alignment = WD_ALIGN_PARAGRAPH.CENTER

    # Group questions by section
    sections_order = []
    sections_map = {}
    for q in questions:
        sec_name = q.get('section_name') or 'Section'
        if sec_name not in sections_map:
            sections_map[sec_name] = []
            sections_order.append(sec_name)
        sections_map[sec_name].append(q)

    # 5. Render Sections & Questions
    for sec_name in sections_order:
        sec_qs = sections_map[sec_name]
        
        # Section Heading
        p_sec = doc.add_paragraph()
        p_sec.paragraph_format.space_before = Pt(10)
        p_sec.paragraph_format.space_after = Pt(4)
        p_sec.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        r_sec = p_sec.add_run(f"― {sec_name.upper()} ―")
        r_sec.font.size = Pt(11)
        r_sec.font.bold = True
        r_sec.font.color.rgb = RGBColor(15, 23, 42)

        for q in sec_qs:
            q_num = q.get('question_number', 1)
            q_text = q.get('question_text', '')
            marks = q.get('marks', 1.0)
            q_type = q.get('question_type', 'Short_Answer')
            options_raw = q.get('options', '[]')
            img_path = q.get('image_path', '')
            or_text = q.get('or_question_text', '')
            or_img = q.get('or_image_path', '')
            correct_ans = q.get('correct_answer', '')
            explanation = q.get('solution_explanation', '')

            try:
                options = json.loads(options_raw) if isinstance(options_raw, str) else (options_raw or [])
            except Exception:
                options = []

            # Question Paragraph with Right-Aligned Marks
            q_table = doc.add_table(rows=1, cols=2)
            q_table.alignment = WD_TABLE_ALIGNMENT.CENTER
            q_table.autofit = False
            
            cell_q = q_table.cell(0, 0)
            cell_q.width = Inches(6.3)
            cell_m = q_table.cell(0, 1)
            cell_m.width = Inches(0.7)

            # Question text
            pq = cell_q.paragraphs[0]
            pq.paragraph_format.space_before = Pt(3)
            pq.paragraph_format.space_after = Pt(2)
            
            rq_num = pq.add_run(f"Q{q_num}. ")
            rq_num.font.bold = True
            
            # Clean up LaTeX signs for clean docx display if needed
            clean_text = q_text.replace('$$', '').replace('$', '')
            pq.add_run(clean_text)

            # Marks
            pm = cell_m.paragraphs[0]
            pm.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            pm.paragraph_format.space_before = Pt(3)
            pm.paragraph_format.space_after = Pt(2)
            rm = pm.add_run(f"[{int(marks) if marks.is_integer() else marks}]")
            rm.font.bold = True
            rm.font.color.rgb = RGBColor(71, 85, 105)

            # Diagram Image if attached
            if img_path and os.path.exists(img_path):
                p_img = doc.add_paragraph()
                p_img.paragraph_format.left_indent = Inches(0.4)
                p_img.paragraph_format.space_after = Pt(4)
                try:
                    p_img.add_run().add_picture(img_path, width=Inches(3.2))
                except Exception as e:
                    print(f"Error adding question image: {e}")

            # Options for MCQ
            if q_type == 'MCQ' and options:
                opt_labels = ['(a)', '(b)', '(c)', '(d)', '(e)', '(f)']
                
                # Check if options are short enough for 2-column or 4-column layout
                max_opt_len = max(len(str(o)) for o in options)
                
                if max_opt_len <= 18 and len(options) == 4:
                    # 4 options in 1 line or 2x2
                    t_opt = doc.add_table(rows=1, cols=4)
                    t_opt.alignment = WD_TABLE_ALIGNMENT.CENTER
                    for idx, opt_text in enumerate(options[:4]):
                        c = t_opt.cell(0, idx)
                        p_o = c.paragraphs[0]
                        p_o.paragraph_format.space_after = Pt(2)
                        r_opt = p_o.add_run(f"{opt_labels[idx]} {str(opt_text).replace('$', '')}")
                        r_opt.font.name = font_name
                        r_opt.font.size = Pt(base_font_size)
                elif max_opt_len <= 35 and len(options) == 4:
                    # 2x2 table
                    t_opt = doc.add_table(rows=2, cols=2)
                    t_opt.alignment = WD_TABLE_ALIGNMENT.CENTER
                    for idx, opt_text in enumerate(options[:4]):
                        r_idx = idx // 2
                        c_idx = idx % 2
                        c = t_opt.cell(r_idx, c_idx)
                        p_o = c.paragraphs[0]
                        p_o.paragraph_format.space_after = Pt(2)
                        r_opt = p_o.add_run(f"{opt_labels[idx]} {str(opt_text).replace('$', '')}")
                        r_opt.font.name = font_name
                        r_opt.font.size = Pt(base_font_size)
                else:
                    # 1 option per line
                    for idx, opt_text in enumerate(options):
                        p_opt = doc.add_paragraph()
                        p_opt.paragraph_format.left_indent = Inches(0.4)
                        p_opt.paragraph_format.space_after = Pt(1)
                        lbl = opt_labels[idx] if idx < len(opt_labels) else f"({idx+1})"
                        r_opt = p_opt.add_run(f"{lbl} {str(opt_text).replace('$', '')}")
                        r_opt.font.name = font_name
                        r_opt.font.size = Pt(base_font_size)

            # Internal Choice "OR" Question
            if or_text:
                p_or = doc.add_paragraph()
                p_or.alignment = WD_ALIGN_PARAGRAPH.CENTER
                p_or.paragraph_format.space_before = Pt(2)
                p_or.paragraph_format.space_after = Pt(2)
                r_or = p_or.add_run("― OR ―")
                r_or.font.bold = True
                r_or.font.italic = True
                r_or.font.size = Pt(10)

                p_or_q = doc.add_paragraph()
                p_or_q.paragraph_format.left_indent = Inches(0.35)
                p_or_q.paragraph_format.space_after = Pt(2)
                p_or_q.add_run(or_text.replace('$$', '').replace('$', ''))

                if or_img and os.path.exists(or_img):
                    p_or_img = doc.add_paragraph()
                    p_or_img.paragraph_format.left_indent = Inches(0.5)
                    try:
                        p_or_img.add_run().add_picture(or_img, width=Inches(3.2))
                    except Exception as e:
                        print(f"Error adding OR image: {e}")

            # Spacing between questions
            p_space = doc.add_paragraph()
            p_space.paragraph_format.space_after = Pt(3)

    # Footer note
    p_end = doc.add_paragraph()
    p_end.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_end.paragraph_format.space_before = Pt(12)
    r_end = p_end.add_run("*** END OF QUESTION PAPER ***")
    r_end.font.bold = True
    r_end.font.size = Pt(9.5)
    r_end.font.color.rgb = RGBColor(100, 116, 139)

    doc.save(output_path)
    return output_path
