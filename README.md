# LKCS Exam Studio - Lord Krishna Convent School 🎓📄

A complete, modern school question paper authoring, blueprint specification, and generation system tailored for **Lord Krishna Convent School**. It provides an end-to-end workflow where **Admins** define exam blueprints, question breakdown quotas, and teacher assignments; **Teachers** enter questions with live LaTeX math formula preview and diagram uploads; and the final question papers can be downloaded as **print-ready PDFs** or **editable Microsoft Word (.docx)** documents with custom school branding.

---

## 🌟 Key Features

### 1. 👨‍💼 Admin Workflow & Blueprint Creator
- **Blueprint Specifications**: Specify Exam Title, Class, Optional Section, Subject, Exam Duration (minutes), and Total Marks.
- **Bulk Blueprint Generator**: Instantly generate blueprints for multiple classes in one click.
- **Section Breakdown**: Define sections (e.g. *Section A: MCQs*, *Section B: Short Answer*, *Section C: Long Answer*, *Section D: Case Study*) with optional section names.
- **Validation**: Strict validation ensuring Total Marks equals sum of question counts multiplied by marks per question.
- **Teacher Assignment**: Assign specific subject teachers to classes and sections.
- **Review & Status**: Track live question entry progress and approve papers.

### 2. 👩‍🏫 Teacher Portal & Question Entry
- **Focused Question Entry**: Teachers click "Enter Questions" directly on their assigned blueprint.
- **LaTeX Math Formula Support**: Real-time formula rendering preview using KaTeX (e.g. `$x^2 + y^2 = r^2$`, `$\frac{-b \pm \sqrt{b^2-4ac}}{2a}$`, `$$\int f(x) dx$$`).
- **MCQ Option Grid**: Structured 4-option inputs (A, B, C, D) with correct answer key selection.
- **Diagram & Figure Attachments**: Upload geometry figures, circuit diagrams, maps, or charts.
- **Internal Choice ("OR" Questions)**: Provide alternative questions with separate diagram attachments.
- **Locked on Submission**: Once submitted, question papers are locked for review.

### 3. 🎨 Custom School Formatting & Export
- **School Profile**: Lord Krishna Convent School name, affiliation, address, and crest logo.
- **Typography & Layout**: Font size options up to 25pt, customizable logo sizes up to 150px, font families (*Calibri*, *Arial*, *Times New Roman*, *Georgia*, *Old English Text MT*), and line spacing.
- **1-Column or 2-Column (Newspaper style)**: Switch between classic full-width layout and compact two-column layout.
- **One-Click PDF Print**: Pixel-perfect printable view optimized with CSS `@media print` rules.
- **Microsoft Word (.docx) Export**: Generates styled `.docx` files formatted with header tables, school logo, question numbers, and right-aligned marks.

### 4. 📶 School Wi-Fi & LAN Network Sharing
- Built-in network IP detection and **QR Code generator**.
- Teachers can scan the QR code from their mobile phones, tablets, or laptops on the school Wi-Fi to enter questions directly without installing anything.
- Admin can configure network scope (School Wi-Fi only or Any Network).

---

## 📁 Build Artifacts & Output (`dist/`)

The compiled standalone packages are located in [`dist/`](file:///Users/roopanshsethi/Downloads/LKCS/dist):

| Platform | File | Description |
| :--- | :--- | :--- |
| **macOS** | [`dist/LKCSExamStudio.dmg`](file:///Users/roopanshsethi/Downloads/LKCS/dist/LKCSExamStudio.dmg) | Disk image installer for macOS |
| **macOS** | [`dist/LKCSExamStudio.app`](file:///Users/roopanshsethi/Downloads/LKCS/dist/LKCSExamStudio.app) | Native macOS Application Bundle |
| **Windows** | [`dist/LKCSExamStudio.exe`](file:///Users/roopanshsethi/Downloads/LKCS/dist/LKCSExamStudio.exe) | Standalone Windows Executable |

---

## 🚀 Running & Building

### Running Locally (Development Mode)
```bash
python run_desktop.py
```
Or run the web server:
```bash
python run_server.py
```
Open `http://127.0.0.1:8000` in your browser.

### Rebuilding for macOS
On macOS, run:
```bash
chmod +x build_mac.sh
./build_mac.sh
```
This produces `dist/LKCSExamStudio.app` and `dist/LKCSExamStudio.dmg`.

### Rebuilding for Windows
On Windows, double-click:
```cmd
build_windows.bat
```
Or run:
```powershell
pyinstaller --clean --noconfirm LKCSExamStudio.spec
```
This produces `dist/LKCSExamStudio.exe`.

### Automated CI/CD (GitHub Actions)
The included workflow [`.github/workflows/build.yml`](.github/workflows/build.yml) automatically builds both the Windows `.exe` and macOS `.dmg` on every push or manual dispatch.

---

## 🔑 Default Credentials

- **Admin Login**:
  - Username: `admin`
  - Password: `admin123`
- **Sample Teacher Login**:
  - Email: `sharma@school.edu`
  - PIN: `1234`
