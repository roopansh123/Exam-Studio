// State management
let currentRole = 'admin'; // 'admin' or 'teacher'
let loggedInTeacher = null;
let currentPortalToken = null;
let blueprints = [];
let teachersList = [];
let activeBlueprint = null;
let currentQuestionIndex = 0;
let currentBlueprintQuestions = [];
let schoolSettings = {};
let currentShareTeacherId = null;
let schoolSubjects = [
    'English', 'Hindi', 'Mathematics', 'Science', 'Social Science',
    'Physics', 'Chemistry', 'Biology', 'Computer Science', 'Information Technology',
    'Economics', 'Accountancy', 'Business Studies', 'History', 'Geography',
    'Political Science', 'Sanskrit', 'Physical Education', 'Psychology', 'Sociology', 'Art & Craft'
];

// Admin authentication state
let isAdminLoggedIn = false;
let currentAdminUser = 'admin';

async function checkAdminAuth() {
    const token = localStorage.getItem('lkcs_admin_token');
    if (!token) {
        isAdminLoggedIn = false;
        updateAdminNavUI();
        return false;
    }
    try {
        const res = await fetch(`/api/admin/me?token=${encodeURIComponent(token)}`);
        const data = await res.json();
        if (data.authenticated) {
            isAdminLoggedIn = true;
            currentAdminUser = data.username || 'admin';
            updateAdminNavUI();
            return true;
        } else {
            isAdminLoggedIn = false;
            localStorage.removeItem('lkcs_admin_token');
            updateAdminNavUI();
            return false;
        }
    } catch (e) {
        console.error('Error verifying admin auth', e);
        isAdminLoggedIn = false;
        updateAdminNavUI();
        return false;
    }
}

function updateAdminNavUI() {
    updateNavUserSessionUI();
}

function updateNavUserSessionUI() {
    const adminBadge = document.getElementById('admin-logged-badge');
    const teacherBadge = document.getElementById('teacher-logged-badge');
    const adminUserDisp = document.getElementById('admin-username-display');
    const teacherNameDisp = document.getElementById('teacher-name-display');

    if (isAdminLoggedIn) {
        if (adminBadge) adminBadge.style.display = 'inline-flex';
        if (teacherBadge) teacherBadge.style.display = 'none';
        if (adminUserDisp) adminUserDisp.innerText = currentAdminUser;
    } else if (loggedInTeacher) {
        if (adminBadge) adminBadge.style.display = 'none';
        if (teacherBadge) teacherBadge.style.display = 'inline-flex';
        if (teacherNameDisp) teacherNameDisp.innerText = loggedInTeacher.name || 'Teacher';
    } else {
        if (adminBadge) adminBadge.style.display = 'none';
        if (teacherBadge) teacherBadge.style.display = 'none';
    }
}

async function handleAdminLogout() {
    await handleUserLogout();
}

async function handleUserLogout() {
    const token = localStorage.getItem('lkcs_admin_token');

    // 1. Immediately wipe all local credentials and reset state synchronously
    try {
        localStorage.removeItem('lkcs_admin_token');
        localStorage.removeItem('lkcs_admin_user');
        localStorage.removeItem('lkcs_teacher');
        localStorage.removeItem('lkcs_current_role');
        sessionStorage.clear();
    } catch (e) {
        console.error('Error clearing storage:', e);
    }

    isAdminLoggedIn = false;
    loggedInTeacher = null;

    // 2. Inform backend in background (do not block redirect if it lags)
    if (token) {
        try {
            fetch(`/api/admin/logout?token=${encodeURIComponent(token)}`, { 
                method: 'POST',
                keepalive: true 
            }).catch(() => {});
        } catch (e) {}
    }

    // 3. Immediately replace location so dashboard is not kept in back-history
    window.location.replace('/?logged_out=1');
}

async function handleAdminChangePassword(e) {
    e.preventDefault();
    const currentPass = document.getElementById('admin-current-pass')?.value;
    const newUser = document.getElementById('admin-new-user')?.value?.trim();
    const newPass = document.getElementById('admin-new-pass')?.value;
    const btn = document.getElementById('btn-update-admin-pass');

    if (!currentPass || !newPass) {
        alert('Please fill in current and new passwords.');
        return;
    }

    if (btn) btn.disabled = true;

    try {
        const res = await fetch('/api/admin/change-password', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                current_password: currentPass,
                new_username: newUser || null,
                new_password: newPass
            })
        });

        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.detail || 'Failed to update credentials.');
        }

        showToast('Admin credentials updated successfully!', 'success');
        const curEl = document.getElementById('admin-current-pass');
        const newEl = document.getElementById('admin-new-pass');
        if (curEl) curEl.value = '';
        if (newEl) newEl.value = '';
        if (newUser) {
            currentAdminUser = newUser;
            localStorage.setItem('lkcs_admin_user', newUser);
            updateAdminNavUI();
        }
    } catch (err) {
        alert('Error: ' + err.message);
    } finally {
        if (btn) btn.disabled = false;
    }
}

document.addEventListener('DOMContentLoaded', async () => {
    // 1. Initialize listeners immediately so tabs and controls are interactive
    initEventListeners();

    // 2. Check if accessed via Phone Portal Token
    const urlParams = new URLSearchParams(window.location.search);
    const hasToken = !!urlParams.get('token');
    if (hasToken) {
        try {
            await checkTokenSession();
        } catch (e) {
            console.error('Portal token check error', e);
        }
    }

    // 3. Check admin authentication
    try {
        await checkAdminAuth();
    } catch (e) {
        console.error('Admin auth check error', e);
    }

    // 4. Check saved teacher session
    const savedTeacher = localStorage.getItem('lkcs_teacher');
    if (savedTeacher && !loggedInTeacher) {
        try {
            loggedInTeacher = JSON.parse(savedTeacher);
        } catch (e) {
            console.error('Error parsing saved teacher session', e);
        }
    }

    // 5. If not authenticated as Admin, Teacher, or Portal Token, redirect to first login page
    if (!isAdminLoggedIn && !loggedInTeacher && !hasToken) {
        window.location.href = '/';
        return;
    }

    // 6. Set active role
    const preferredRole = localStorage.getItem('lkcs_current_role');
    if (isAdminLoggedIn && preferredRole !== 'teacher') {
        currentRole = 'admin';
        document.getElementById('role-admin-btn')?.classList.add('active');
        document.getElementById('role-teacher-btn')?.classList.remove('active');
    } else {
        currentRole = 'teacher';
        document.getElementById('role-admin-btn')?.classList.remove('active');
        document.getElementById('role-teacher-btn')?.classList.add('active');
    }

    updateNavUserSessionUI();

    // 7. Load global configs
    try { await loadNetworkInfo(); } catch (e) { console.error('Network info error', e); }
    try { await loadSchoolSettings(); } catch (e) { console.error('School settings error', e); }
    try { await loadTeachers(); } catch (e) { console.error('Teachers load error', e); }
    try { await loadBlueprints(); } catch (e) { console.error('Blueprints load error', e); }
    updateRoleUI();
});

// ----------------- Phone Portal Access Token Verification -----------------
async function checkTokenSession() {
    const urlParams = new URLSearchParams(window.location.search);
    const token = urlParams.get('token');
    if (!token) return false;
    
    try {
        const res = await fetch(`/api/portal/verify-token?token=${encodeURIComponent(token)}`);
        const data = await res.json();
        
        if (!res.ok || data.status === 'error') {
            document.body.innerHTML = `
                <div style="min-height: 100vh; display: flex; align-items: center; justify-content: center; background: #f8fafc; font-family: 'Plus Jakarta Sans', sans-serif; padding: 20px;">
                    <div style="background: white; border-radius: 16px; border: 1px solid #fee2e2; padding: 36px 28px; max-width: 460px; text-align: center; box-shadow: 0 10px 25px rgba(0,0,0,0.08);">
                        <div style="font-size: 52px; margin-bottom: 12px;">⚠️</div>
                        <h2 style="font-size: 20px; font-weight: 800; color: #991b1b; margin-bottom: 12px;">Portal Access Link Expired or Locked</h2>
                        <p style="font-size: 14px; color: #475569; line-height: 1.5; margin-bottom: 20px;">
                            ${data.message || 'This secure teacher portal access link has expired. Please contact your school administrator to receive a new link.'}
                        </p>
                        <div style="background: #fef2f2; border: 1px solid #fecaca; border-radius: 8px; padding: 10px 14px; font-size: 12px; color: #b91c1c; font-weight: 600;">
                            Validity Restriction: Admin controls the duration of this link for security.
                        </div>
                    </div>
                </div>
            `;
            return true;
        }
        
        // Logged in via secure token as teacher
        currentRole = 'teacher';
        loggedInTeacher = data.teacher;
        currentPortalToken = token;
        
        // Render mobile session banner
        const hoursRemaining = Math.max(0, Math.floor(data.remaining_seconds / 3600));
        const minsRemaining = Math.max(0, Math.floor((data.remaining_seconds % 3600) / 60));
        const timeStr = hoursRemaining > 0 ? `${hoursRemaining}h ${minsRemaining}m` : `${minsRemaining}m`;
        
        const container = document.querySelector('.app-container');
        if (container) {
            const banner = document.createElement('div');
            banner.className = 'mobile-token-banner';
            banner.innerHTML = `
                <div style="display: flex; align-items: center; gap: 8px;">
                    <span>📱</span>
                    <span>Phone Portal: <strong>${data.teacher.name}</strong></span>
                </div>
                <div style="font-size: 12px; background: rgba(0,0,0,0.2); padding: 4px 10px; border-radius: 20px;">
                    ⏱ Valid for: <strong>${timeStr}</strong>
                </div>
            `;
            container.insertBefore(banner, container.firstChild);
        }
        
        // Hide Admin tabs and role selector
        document.querySelectorAll('.admin-only').forEach(el => el.style.display = 'none');
        const roleBadge = document.querySelector('.role-badge-box');
        if (roleBadge) roleBadge.style.display = 'none';
        
        updateRoleUI();
        return true;
    } catch (e) {
        console.error('Failed to verify portal token', e);
        return false;
    }
}

// ----------------- Network & LAN Wi-Fi Info -----------------
async function loadNetworkInfo() {
    try {
        const res = await fetch('/api/network-info');
        const data = await res.json();
        wifiSettings = data;
        
        const modalLanUrl = document.getElementById('modal-lan-url');
        if (modalLanUrl) modalLanUrl.innerText = data.active_portal_url || data.lan_url;
        
        const modalQrImg = document.getElementById('modal-qr-img');
        if (modalQrImg && data.qr_code) {
            modalQrImg.src = data.qr_code;
        }
        
        // Update Wi-Fi modal admin controls
        const toggleBtn = document.getElementById('modal-wifi-toggle-btn');
        const modeSelect = document.getElementById('modal-wifi-mode-select');
        const scopeSelect = document.getElementById('modal-network-scope-select');
        const disabledWarning = document.getElementById('modal-wifi-disabled-warning');
        const activeContent = document.getElementById('modal-wifi-active-content');
        const modeBadge = document.getElementById('modal-wifi-mode-badge');
        const shareInstr = document.getElementById('modal-share-instructions');
        const tunnelBox = document.getElementById('modal-tunnel-control-box');
        const tunnelStatusText = document.getElementById('modal-tunnel-status-text');
        const modalTunnelBtn = document.getElementById('modal-tunnel-btn');
        
        if (toggleBtn) {
            if (data.wifi_enabled) {
                toggleBtn.innerText = '✓ Wi-Fi Access: ON';
                toggleBtn.className = 'btn btn-emerald btn-sm';
            } else {
                toggleBtn.innerText = '✕ Wi-Fi Access: OFF';
                toggleBtn.className = 'btn btn-danger btn-sm';
            }
        }
        
        if (modeSelect) {
            modeSelect.value = data.wifi_security_mode || 'secure';
        }
        
        if (scopeSelect) {
            scopeSelect.value = data.network_scope || 'school_wifi';
        }

        if (tunnelBox) {
            tunnelBox.style.display = data.network_scope === 'any_network' ? 'flex' : 'none';
            if (tunnelStatusText) {
                tunnelStatusText.innerText = data.is_tunnel_running 
                    ? `🟢 Tunnel Online: ${data.public_url}` 
                    : `🔴 Tunnel Offline`;
            }
            if (modalTunnelBtn) {
                modalTunnelBtn.innerText = data.is_tunnel_running ? 'Stop Tunnel' : 'Start Tunnel';
                modalTunnelBtn.className = data.is_tunnel_running ? 'btn btn-danger btn-sm' : 'btn btn-primary btn-sm';
            }
        }
        
        if (shareInstr) {
            if (data.network_scope === 'any_network') {
                shareInstr.innerHTML = '🌍 <strong>Any Network Mode Active:</strong> Teachers can access from anywhere on mobile cellular data (4G/5G) or home Wi-Fi:';
            } else {
                shareInstr.innerHTML = '🏫 <strong>School Wi-Fi Only:</strong> Teachers connected to the school Wi-Fi network can scan this QR code or open the link:';
            }
        }
        
        if (disabledWarning && activeContent) {
            if (data.wifi_enabled) {
                disabledWarning.style.display = 'none';
                activeContent.style.display = 'block';
            } else {
                disabledWarning.style.display = 'block';
                activeContent.style.display = 'none';
            }
        }
        
        if (modeBadge) {
            const scopeText = data.network_scope === 'any_network' ? '🌍 Any Network (Internet)' : '🏫 School Wi-Fi Only';
            if (data.wifi_security_mode === 'secure') {
                modeBadge.innerHTML = `🔒 <strong>Secure Mode (${scopeText}):</strong> Teacher PIN login or generated link required.`;
            } else {
                modeBadge.innerHTML = `🌐 <strong>Open Mode (${scopeText}):</strong> Quick portal access enabled without PIN.`;
            }
        }

        // Update School Settings Tab Tunnel Panel
        const tunnelBadge = document.getElementById('tunnel-status-badge');
        const btnToggleTunnel = document.getElementById('btn-toggle-tunnel');
        const publicUrlInput = document.getElementById('setting-public-url');
        
        if (tunnelBadge) {
            if (data.is_tunnel_running) {
                tunnelBadge.innerText = `🟢 Online: ${data.public_url}`;
                tunnelBadge.style.background = '#dcfce7';
                tunnelBadge.style.color = '#15803d';
            } else {
                tunnelBadge.innerText = `🔴 Tunnel Offline`;
                tunnelBadge.style.background = '#e2e8f0';
                tunnelBadge.style.color = '#475569';
            }
        }
        if (btnToggleTunnel) {
            btnToggleTunnel.innerText = data.is_tunnel_running ? 'Stop Tunnel' : '⚡ Start Internet Tunnel';
            btnToggleTunnel.className = data.is_tunnel_running ? 'btn btn-danger btn-sm' : 'btn btn-primary btn-sm';
        }
        if (publicUrlInput && data.public_url && !publicUrlInput.value) {
            publicUrlInput.value = data.public_url;
        }
    } catch (e) {
        console.error('Failed to load network info', e);
    }
}

function openLanModal() {
    document.getElementById('lan-modal').classList.add('active');
}

function closeLanModal() {
    document.getElementById('lan-modal').classList.remove('active');
}

async function toggleWifiAccess() {
    const newStatus = !wifiSettings.wifi_enabled;
    try {
        const res = await fetch('/api/wifi-settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                wifi_enabled: newStatus,
                wifi_security_mode: wifiSettings.wifi_security_mode || 'secure',
                network_scope: wifiSettings.network_scope || 'school_wifi',
                public_url: wifiSettings.public_url || ''
            })
        });
        if (res.ok) {
            await loadNetworkInfo();
            showToast(newStatus ? 'School Wi-Fi sharing turned ON' : 'School Wi-Fi sharing turned OFF by Admin', newStatus ? 'success' : 'info');
        }
    } catch (err) {
        alert('Failed to update Wi-Fi: ' + err.message);
    }
}

async function updateWifiModeFromModal() {
    const sel = document.getElementById('modal-wifi-mode-select');
    if (!sel) return;
    const newMode = sel.value;
    try {
        const res = await fetch('/api/wifi-settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                wifi_enabled: wifiSettings.wifi_enabled !== false,
                wifi_security_mode: newMode,
                network_scope: wifiSettings.network_scope || 'school_wifi',
                public_url: wifiSettings.public_url || ''
            })
        });
        if (res.ok) {
            await loadNetworkInfo();
            showToast(`Wi-Fi mode switched to: ${newMode === 'secure' ? 'Secure' : 'Open'}`, 'success');
        }
    } catch (err) {
        alert('Failed to update Wi-Fi mode');
    }
}

async function updateNetworkScopeFromModal() {
    const sel = document.getElementById('modal-network-scope-select');
    if (!sel) return;
    const newScope = sel.value;
    try {
        const res = await fetch('/api/wifi-settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                wifi_enabled: wifiSettings.wifi_enabled !== false,
                wifi_security_mode: wifiSettings.wifi_security_mode || 'secure',
                network_scope: newScope,
                public_url: wifiSettings.public_url || ''
            })
        });
        if (res.ok) {
            await loadNetworkInfo();
            showToast(`Network scope switched to: ${newScope === 'any_network' ? 'Any Network (Internet)' : 'School Wi-Fi Only'}`, 'success');
            // If switched to any_network and no tunnel running, auto-prompt to start
            if (newScope === 'any_network' && !wifiSettings.is_tunnel_running) {
                toggleInternetTunnel();
            }
        }
    } catch (err) {
        alert('Failed to update network scope');
    }
}

function toggleNetworkScopeUI() {
    const sel = document.getElementById('setting-network-scope');
    const panel = document.getElementById('internet-tunnel-panel');
    if (!sel || !panel) return;
    panel.style.display = sel.value === 'any_network' ? 'block' : 'none';
}

async function toggleInternetTunnel() {
    const isRunning = wifiSettings.is_tunnel_running;
    const btn = document.getElementById('btn-toggle-tunnel');
    const modalBtn = document.getElementById('modal-tunnel-btn');
    if (btn) btn.innerText = isRunning ? 'Stopping...' : 'Starting...';
    if (modalBtn) modalBtn.innerText = isRunning ? 'Stopping...' : 'Starting...';

    try {
        if (isRunning) {
            const res = await fetch('/api/tunnel/stop', { method: 'POST' });
            if (res.ok) {
                showToast('Internet tunnel stopped.', 'info');
            }
        } else {
            showToast('Starting secure internet tunnel... Please wait a few seconds.', 'info');
            const res = await fetch('/api/tunnel/start', { method: 'POST' });
            const data = await res.json();
            if (data.status === 'running' || data.url) {
                showToast(`Tunnel active! Public URL: ${data.url}`, 'success');
                const inp = document.getElementById('setting-public-url');
                if (inp) inp.value = data.url;
            } else if (data.message) {
                alert('Tunnel notice: ' + data.message);
            }
        }
        await loadNetworkInfo();
        await loadSchoolSettings();
    } catch (err) {
        alert('Tunnel error: ' + err.message);
    }
}

function copyLanUrl() {
    const url = document.getElementById('modal-lan-url')?.innerText;
    if (url) {
        navigator.clipboard.writeText(url).then(() => {
            showToast('Wi-Fi URL copied to clipboard!', 'success');
        });
    }
}

// ----------------- Navigation Tabs -----------------
function switchTab(tabId) {
    const adminTabs = ['tab-create', 'tab-teachers', 'tab-settings'];
    if (adminTabs.includes(tabId) && !isAdminLoggedIn) {
        window.location.href = '/?role=admin';
        return;
    }

    document.querySelectorAll('.nav-tab-btn').forEach(btn => btn.classList.remove('active'));
    document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));

    const activeBtn = document.querySelector(`.nav-tab-btn[data-tab="${tabId}"]`);
    if (activeBtn) activeBtn.classList.add('active');
    if (tabId === 'tab-entry') {
        const papersBtn = document.querySelector('.nav-tab-btn[data-tab="tab-papers"]');
        if (papersBtn) papersBtn.classList.add('active');
    }

    const activePane = document.getElementById(tabId);
    if (activePane) activePane.classList.add('active');

    if (tabId === 'tab-papers') loadBlueprints();
    if (tabId === 'tab-teachers') loadTeachers();
    if (tabId === 'tab-settings') loadSchoolSettings();
}

function setRole(role) {
    if (role === 'admin' && !isAdminLoggedIn) {
        if (confirm('Accessing Admin capabilities requires administrator login. Switch to Admin Login?')) {
            window.location.href = '/?role=admin';
        }
        return;
    }
    if (role === 'teacher' && !loggedInTeacher && !isAdminLoggedIn) {
        window.location.href = '/?role=teacher';
        return;
    }
    currentRole = role;
    localStorage.setItem('lkcs_current_role', role);
    document.getElementById('role-admin-btn')?.classList.toggle('active', role === 'admin');
    document.getElementById('role-teacher-btn')?.classList.toggle('active', role === 'teacher');

    if (role === 'teacher' && !loggedInTeacher) {
        openTeacherLoginModal();
    } else {
        updateRoleUI();
    }
}

function updateRoleUI() {
    const adminOnlyEls = document.querySelectorAll('.admin-only');
    if (currentRole === 'admin' && isAdminLoggedIn) {
        adminOnlyEls.forEach(el => el.style.display = '');
        const statusEl = document.getElementById('user-status-text');
        if (statusEl) statusEl.innerText = `Logged in as Admin (${currentAdminUser})`;
    } else {
        adminOnlyEls.forEach(el => el.style.display = 'none');
        const statusEl = document.getElementById('user-status-text');
        if (statusEl) {
            statusEl.innerText = loggedInTeacher 
                ? `Teacher: ${loggedInTeacher.name}` 
                : 'Teacher Mode';
        }
    }
    updateNavUserSessionUI();
    loadBlueprints();
}

// ----------------- Teacher Login Modal -----------------
function openTeacherLoginModal() {
    const modal = document.getElementById('teacher-login-modal');
    if (modal) modal.classList.add('active');
}

function closeTeacherLoginModal() {
    const modal = document.getElementById('teacher-login-modal');
    if (modal) modal.classList.remove('active');
    // If not logged in, reset role selector button to admin if admin is logged in
    if (!loggedInTeacher && currentRole === 'teacher') {
        if (isAdminLoggedIn) {
            currentRole = 'admin';
            document.getElementById('role-admin-btn')?.classList.add('active');
            document.getElementById('role-teacher-btn')?.classList.remove('active');
            updateRoleUI();
        } else {
            window.location.href = '/';
        }
    }
}

async function handleTeacherLogin(e) {
    e.preventDefault();
    const email = document.getElementById('login-teacher-email')?.value?.trim();
    const pin = document.getElementById('login-teacher-pin')?.value?.trim();
    if (!email || !pin) return;

    const formData = new FormData();
    formData.append('email', email);
    formData.append('pin', pin);

    try {
        const res = await fetch('/api/teacher/verify-pin', {
            method: 'POST',
            body: formData
        });
        const data = await res.json();
        if (res.ok && data.status === 'success') {
            loggedInTeacher = data.teacher;
            localStorage.setItem('lkcs_teacher', JSON.stringify(data.teacher));
            localStorage.setItem('lkcs_current_role', 'teacher');
            currentRole = 'teacher';
            closeTeacherLoginModal();
            updateRoleUI();
            updateNavUserSessionUI();
            showToast(`Welcome back, ${loggedInTeacher.name}!`, 'success');
        } else {
            alert(data.detail || 'Invalid email or PIN code.');
        }
    } catch (err) {
        alert('Login failed: ' + err.message);
    }
}

// ----------------- School Settings & Formatting -----------------
async function loadSchoolSettings() {
    try {
        const res = await fetch('/api/school-settings');
        if (!res.ok) return;
        const data = await res.json();
        schoolSettings = data;

        const setVal = (id, val) => {
            const el = document.getElementById(id);
            if (el && val !== undefined && val !== null) el.value = val;
        };
        const setChecked = (id, val) => {
            const el = document.getElementById(id);
            if (el) el.checked = Boolean(val);
        };

        setVal('setting-school-name', data.school_name || 'LORD KRISHNA CONVENT SCHOOL');
        setVal('setting-school-name-font', data.school_name_font || 'Canterbury');
        setVal('setting-subtitle', data.sub_title || '');
        setVal('setting-address', data.address || '');
        setVal('setting-watermark', data.watermark_text || '');
        setChecked('setting-show-watermark', data.show_watermark);
        setVal('setting-font-family', data.font_family || 'Calibri');
        setVal('setting-font-size', data.font_size || '11pt');
        setVal('setting-line-spacing', data.line_spacing || '1.15');
        setVal('setting-layout', data.page_layout || '1-column');
        setChecked('setting-show-instructions', data.show_instructions !== 0);
        setVal('setting-wifi-enabled', data.wifi_enabled !== 0 ? '1' : '0');
        setVal('setting-wifi-mode', data.wifi_security_mode || 'secure');
        setVal('setting-network-scope', data.network_scope || 'school_wifi');
        setVal('setting-public-url', data.public_url || '');

        const logoSize = data.logo_size || 80;
        setVal('setting-logo-size', logoSize);
        updateLogoSizePreview(logoSize);

        toggleNetworkScopeUI();

        const logoImg = document.getElementById('logo-preview-img');
        if (logoImg && data.logo_path) {
            logoImg.src = '/' + data.logo_path;
            logoImg.style.display = 'block';
        }

        if (data.subjects && Array.isArray(data.subjects) && data.subjects.length > 0) {
            schoolSubjects = data.subjects;
        }
        renderSchoolSubjects();

        updateSchoolNamePreview();
    } catch (e) {
        console.error('Failed to load school settings', e);
    }
}

// ----------------- School Subjects & Curriculum Management -----------------
function renderSchoolSubjects() {
    const container = document.getElementById('school-subjects-container');
    const badge = document.getElementById('subjects-count-badge');
    const datalist = document.getElementById('school-subjects-datalist');
    if (!container) return;

    if (!schoolSubjects || schoolSubjects.length === 0) {
        container.innerHTML = `<span style="color: var(--text-muted); font-size: 13px; font-style: italic;">No subjects added. Add your first subject below.</span>`;
        if (badge) badge.innerText = `0 Subjects`;
        if (datalist) datalist.innerHTML = '';
        return;
    }

    if (badge) badge.innerText = `${schoolSubjects.length} Subject${schoolSubjects.length === 1 ? '' : 's'}`;

    container.innerHTML = schoolSubjects.map(s => `
        <div class="subject-chip" style="display: inline-flex; align-items: center; gap: 7px; background: #ffffff; border: 1px solid #cbd5e1; padding: 5px 12px; border-radius: 20px; font-size: 12.5px; font-weight: 600; color: #1e293b; box-shadow: 0 1px 2px rgba(0,0,0,0.03); transition: all 0.15s ease;">
            <span>${escapeHtml(s)}</span>
            <button type="button" onclick="handleRemoveSubject('${escapeHtml(s)}')" style="background: none; border: none; cursor: pointer; color: #94a3b8; font-size: 14px; font-weight: 700; line-height: 1; padding: 0 2px; border-radius: 50%;" title="Remove ${escapeHtml(s)}" onmouseover="this.style.color='#ef4444'" onmouseout="this.style.color='#94a3b8'">✕</button>
        </div>
    `).join('');

    if (datalist) {
        datalist.innerHTML = schoolSubjects.map(s => `<option value="${escapeHtml(s)}"></option>`).join('');
    }
}

async function handleAddSubject() {
    const input = document.getElementById('new-subject-input');
    if (!input) return;
    const name = input.value.trim();
    if (!name) {
        showToast('Please enter a subject name', 'warning');
        return;
    }
    if (schoolSubjects.some(s => s.toLowerCase() === name.toLowerCase())) {
        showToast(`Subject "${name}" already exists`, 'warning');
        input.value = '';
        return;
    }

    try {
        const res = await fetch('/api/subjects', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name })
        });
        if (!res.ok) throw new Error(await res.text());
        const data = await res.json();
        schoolSubjects = data.subjects || [];
        renderSchoolSubjects();
        input.value = '';
        showToast(`Subject "${name}" added successfully!`, 'success');
    } catch (e) {
        schoolSubjects.push(name);
        renderSchoolSubjects();
        input.value = '';
        showToast(`Subject "${name}" added`, 'success');
    }
}

async function handleRemoveSubject(name) {
    if (!confirm(`Are you sure you want to remove subject "${name}" from school settings?`)) {
        return;
    }

    try {
        const res = await fetch(`/api/subjects/${encodeURIComponent(name)}`, {
            method: 'DELETE'
        });
        if (!res.ok) throw new Error(await res.text());
        const data = await res.json();
        schoolSubjects = data.subjects || [];
        renderSchoolSubjects();
        showToast(`Subject "${name}" removed.`, 'info');
    } catch (e) {
        schoolSubjects = schoolSubjects.filter(s => s.toLowerCase() !== name.toLowerCase());
        renderSchoolSubjects();
        showToast(`Subject "${name}" removed.`, 'info');
    }
}

async function addSubjectPreset(presetList) {
    let addedCount = 0;
    presetList.forEach(s => {
        if (!schoolSubjects.some(curr => curr.toLowerCase() === s.toLowerCase())) {
            schoolSubjects.push(s);
            addedCount++;
        }
    });

    if (addedCount === 0) {
        showToast('All subjects in this stream are already added.', 'info');
        return;
    }

    try {
        await fetch('/api/school-settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ...schoolSettings, subjects: schoolSubjects })
        });
        renderSchoolSubjects();
        showToast(`Added ${addedCount} subjects from preset stream!`, 'success');
    } catch (e) {
        renderSchoolSubjects();
        showToast(`Added ${addedCount} subjects from preset stream!`, 'success');
    }
}

async function resetSubjectsToDefault() {
    if (!confirm('Reset all subjects to the standard CBSE curriculum list?')) return;
    const defaults = [
        "English", "Hindi", "Mathematics", "Science", "Social Science",
        "Physics", "Chemistry", "Biology", "Computer Science", "Information Technology",
        "Economics", "Accountancy", "Business Studies", "History", "Geography",
        "Political Science", "Sanskrit", "Physical Education", "Psychology", "Sociology", "Art & Craft"
    ];
    schoolSubjects = defaults;
    try {
        await fetch('/api/school-settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ...schoolSettings, subjects: defaults })
        });
        renderSchoolSubjects();
        showToast('Subjects reset to CBSE standard curriculum list.', 'success');
    } catch (e) {
        renderSchoolSubjects();
        showToast('Subjects reset to defaults.', 'success');
    }
}

function updateLogoSizePreview(val) {
    const valSpan = document.getElementById('logo-size-val');
    if (valSpan) valSpan.textContent = val + 'px';
    const logoImg = document.getElementById('logo-preview-img');
    if (logoImg) {
        logoImg.style.maxHeight = val + 'px';
    }
}

function setLogoSizePreset(val) {
    const range = document.getElementById('setting-logo-size');
    if (range) {
        range.value = val;
        updateLogoSizePreview(val);
    }
}

function updateSchoolNamePreview() {
    const nameInput = document.getElementById('setting-school-name');
    const fontSelect = document.getElementById('setting-school-name-font');
    const previewEl = document.getElementById('school-name-preview');
    if (!previewEl) return;

    const name = nameInput?.value?.trim() || 'LORD KRISHNA CONVENT SCHOOL';
    const font = fontSelect?.value || 'Canterbury';

    previewEl.innerText = name;
    if (font === 'Canterbury') {
        previewEl.style.fontFamily = "'Canterbury', 'Old English Text MT', serif";
    } else if (font === 'Old English Text MT') {
        previewEl.style.fontFamily = "'Old English Text MT', 'Canterbury', 'Engravers Old English BT', serif";
    } else if (font === 'UnifrakturMaguntia') {
        previewEl.style.fontFamily = "'UnifrakturMaguntia', cursive, serif";
    } else if (font === 'Cinzel') {
        previewEl.style.fontFamily = "'Cinzel', serif";
    } else {
        previewEl.style.fontFamily = font;
    }
}

async function handleSettingsSubmit(e) {
    e.preventDefault();
    const payload = {
        school_name: document.getElementById('setting-school-name')?.value?.trim() || 'LORD KRISHNA CONVENT SCHOOL',
        school_name_font: document.getElementById('setting-school-name-font')?.value || 'Canterbury',
        sub_title: document.getElementById('setting-subtitle')?.value?.trim() || '',
        address: document.getElementById('setting-address')?.value?.trim() || '',
        logo_size: parseInt(document.getElementById('setting-logo-size')?.value) || 80,
        watermark_text: document.getElementById('setting-watermark')?.value?.trim() || '',
        show_watermark: document.getElementById('setting-show-watermark')?.checked ? 1 : 0,
        font_family: document.getElementById('setting-font-family')?.value || 'Calibri',
        font_size: document.getElementById('setting-font-size')?.value || '11pt',
        line_spacing: document.getElementById('setting-line-spacing')?.value || '1.15',
        page_layout: document.getElementById('setting-layout')?.value || '1-column',
        show_instructions: document.getElementById('setting-show-instructions')?.checked ? 1 : 0,
        enable_answer_key: 0,
        wifi_enabled: parseInt(document.getElementById('setting-wifi-enabled')?.value || '1'),
        wifi_security_mode: document.getElementById('setting-wifi-mode')?.value || 'secure',
        network_scope: document.getElementById('setting-network-scope')?.value || 'school_wifi',
        public_url: document.getElementById('setting-public-url')?.value?.trim() || '',
        wifi_passcode: '',
        subjects: schoolSubjects
    };

    try {
        const res = await fetch('/api/school-settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (res.ok) {
            schoolSettings = { ...schoolSettings, ...payload };
            showToast('School & Formatting Settings saved successfully!', 'success');
            await loadNetworkInfo();
        } else {
            const err = await res.json();
            alert('Failed to save settings: ' + (err.detail || 'Unknown error'));
        }
    } catch (err) {
        alert('Network error saving settings: ' + err.message);
    }
}

async function handleLogoUpload(input) {
    if (!input.files || !input.files[0]) return;
    const formData = new FormData();
    formData.append('file', input.files[0]);

    try {
        const res = await fetch('/api/upload-logo', {
            method: 'POST',
            body: formData
        });
        const data = await res.json();
        if (data.logo_path) {
            document.getElementById('logo-preview-img').src = '/' + data.logo_path;
            document.getElementById('logo-preview-img').style.display = 'block';
            showToast('Logo updated successfully!', 'success');
        }
    } catch (e) {
        alert('Failed to upload logo: ' + e.message);
    }
}

// ----------------- Teachers Management -----------------
async function loadTeachers() {
    try {
        const res = await fetch('/api/teachers');
        teachersList = await res.json();
        renderTeachersTable();
        populateTeacherSelectDropdown();
    } catch (e) {
        console.error('Error loading teachers', e);
    }
}

function renderTeachersTable() {
    const tbody = document.getElementById('teachers-tbody');
    if (!tbody) return;

    if (teachersList.length === 0) {
        tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--text-muted); padding: 24px;">No teachers added yet.</td></tr>`;
        return;
    }

    tbody.innerHTML = teachersList.map(t => {
        const assignmentsHtml = (t.assigned_classes || []).map(a => 
            `<span class="badge badge-assigned" style="margin: 2px;">${a.class || ''} - ${a.subject || ''}</span>`
        ).join('');

        // Find papers assigned to this teacher
        const assignedBps = blueprints.filter(b => b.teacher_id === t.id);
        const paperCount = assignedBps.length;
        const papersHtml = assignedBps.length > 0
            ? assignedBps.map(b => `
                <div style="font-size: 11.5px; margin: 2px 0;">
                    📄 <strong>${b.class_name}</strong> ${b.subject}
                    <span class="badge ${b.status === 'Questions_Submitted' ? 'badge-submitted' : 'badge-assigned'}" style="font-size: 10px; padding: 1px 5px;">${b.status === 'Questions_Submitted' ? 'Submitted' : 'Assigned'}</span>
                </div>
              `).join('')
            : '<span style="color: #94a3b8; font-style: italic; font-size: 12px;">No papers assigned</span>';

        const multipleBadge = paperCount > 1 
            ? `<span style="background: #e0e7ff; color: #3730a3; padding: 1px 6px; border-radius: 10px; font-size: 10.5px; font-weight: 700; margin-left: 4px;">${paperCount} Papers</span>` 
            : '';

        return `
            <tr>
                <td><strong>${t.name}</strong></td>
                <td>${t.email}</td>
                <td><code style="background: #f1f5f9; padding: 2px 6px; border-radius: 4px;">${t.pin}</code></td>
                <td>${assignmentsHtml || '<span style="color: #94a3b8;">None</span>'}</td>
                <td>
                    <div style="margin-bottom: 3px;"><strong>${paperCount} Assigned</strong> ${multipleBadge}</div>
                    ${papersHtml}
                </td>
                <td>
                    <div style="display: flex; gap: 6px; flex-wrap: wrap; align-items: center;">
                        <button class="btn btn-primary btn-sm" onclick="openShareLinkModal(${t.id})" title="Share portal link for teacher's phone with custom validity">
                            📱 Share Link
                        </button>
                        <button class="btn btn-secondary btn-sm" onclick="editTeacher(${t.id})">Edit</button>
                        <button class="btn btn-danger btn-sm" onclick="deleteTeacher(${t.id})">Delete</button>
                    </div>
                </td>
            </tr>
        `;
    }).join('');
}

// ----------------- Share Phone Portal Link Modal -----------------
function openShareLinkModal(teacherId) {
    currentShareTeacherId = teacherId;
    const t = teachersList.find(x => x.id === teacherId);
    if (!t) return;

    document.getElementById('share-teacher-name').innerText = t.name;
    document.getElementById('share-teacher-email').innerText = t.email;

    const teacherBlueprints = blueprints.filter(b => b.teacher_id === teacherId);
    document.getElementById('share-assigned-count').innerText = teacherBlueprints.length;

    const listEl = document.getElementById('share-assigned-papers-list');
    if (teacherBlueprints.length === 0) {
        listEl.innerHTML = '<span style="color: var(--text-muted); font-style: italic;">No exam papers currently assigned to this teacher.</span>';
    } else {
        listEl.innerHTML = teacherBlueprints.map((b, i) => `
            <div style="display: flex; align-items: center; justify-content: space-between; padding: 6px 10px; background: white; border-radius: 6px; border: 1px solid var(--border-color);">
                <div>
                    <strong>${b.class_name}</strong> - ${b.subject}: <em>${b.title}</em>
                </div>
                <span class="badge ${b.status === 'Questions_Submitted' ? 'badge-submitted' : 'badge-assigned'}">${b.status || 'Assigned'}</span>
            </div>
        `).join('');
    }

    document.getElementById('share-result-container').style.display = 'none';
    document.getElementById('share-validity-select').value = "24";
    const scopeSelect = document.getElementById('share-network-scope-select');
    if (scopeSelect) {
        scopeSelect.value = wifiSettings.network_scope || 'school_wifi';
    }
    document.getElementById('share-link-modal').classList.add('active');
}

function closeShareLinkModal() {
    document.getElementById('share-link-modal').classList.remove('active');
}

async function handleGenerateTeacherLink() {
    if (!currentShareTeacherId) return;
    const validityHours = parseFloat(document.getElementById('share-validity-select').value) || 24;
    const chosenScope = document.getElementById('share-network-scope-select')?.value || 'school_wifi';

    // If admin changed scope in the modal, synchronize it
    if (chosenScope !== wifiSettings.network_scope) {
        try {
            await fetch('/api/wifi-settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    wifi_enabled: wifiSettings.wifi_enabled !== false,
                    wifi_security_mode: wifiSettings.wifi_security_mode || 'secure',
                    network_scope: chosenScope,
                    public_url: wifiSettings.public_url || ''
                })
            });
            await loadNetworkInfo();
        } catch (e) {
            console.error('Failed to update scope preference', e);
        }
    }

    try {
        const res = await fetch(`/api/teachers/${currentShareTeacherId}/generate-link`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ validity_hours: validityHours })
        });

        if (!res.ok) throw new Error(await res.text());
        const data = await res.json();

        document.getElementById('share-qr-img').src = data.qr_code;
        document.getElementById('share-url-input').value = data.portal_url;
        
        // Render network scope and expiry info
        const isInternet = data.is_internet_accessible;
        const scopeBadgeHtml = isInternet
            ? `<span style="background: #dbeafe; color: #1e40af; padding: 2px 8px; border-radius: 12px; font-weight: 700; font-size: 11px;">🌍 Any Network (Internet / Mobile Data)</span>`
            : `<span style="background: #f1f5f9; color: #475569; padding: 2px 8px; border-radius: 12px; font-weight: 700; font-size: 11px;">🏫 School Wi-Fi Only</span>`;

        const expiryEl = document.getElementById('share-expiry-text');
        if (expiryEl && expiryEl.parentElement) {
            expiryEl.parentElement.innerHTML = `
                <div style="margin-bottom: 4px;">⏱ <strong>Valid until:</strong> ${data.expires_at} (${data.validity_hours} hours)</div>
                <div style="margin-bottom: 4px;">📡 <strong>Network Scope:</strong> ${scopeBadgeHtml}</div>
                <div>🔒 <strong>Security:</strong> Teachers cannot download or print papers. Papers lock upon submission.</div>
            `;
        }

        document.getElementById('share-result-container').style.display = 'block';
        showToast('Secure Phone Portal link generated successfully!', 'success');
    } catch (err) {
        alert('Failed to generate link: ' + err.message);
    }
}

function copyShareUrl() {
    const input = document.getElementById('share-url-input');
    if (!input || !input.value) return;
    navigator.clipboard.writeText(input.value).then(() => {
        showToast('Portal link copied to clipboard! Share it with the teacher.', 'success');
    });
}

function populateTeacherSelectDropdown() {
    const sel = document.getElementById('blueprint-teacher-id');
    if (!sel) return;
    sel.innerHTML = '<option value="">-- Select Teacher to Assign --</option>' + 
        teachersList.map(t => `<option value="${t.id}">${t.name} (${t.email})</option>`).join('');
}

function openAddTeacherModal() {
    document.getElementById('teacher-form-id').value = '';
    document.getElementById('teacher-form-name').value = '';
    document.getElementById('teacher-form-email').value = '';
    document.getElementById('teacher-form-pin').value = '1234';
    document.getElementById('teacher-form-phone').value = '';
    document.getElementById('teacher-assignments-list').innerHTML = '';
    addAssignmentRow(); // add 1 blank row
    document.getElementById('teacher-modal-title').innerText = 'Add New Teacher';
    document.getElementById('teacher-modal').classList.add('active');
}

function closeTeacherModal() {
    document.getElementById('teacher-modal').classList.remove('active');
}

function addAssignmentRow(cls = 'Class 10', subj = 'Mathematics') {
    const container = document.getElementById('teacher-assignments-list');
    const div = document.createElement('div');
    div.className = 'form-row assignment-row';
    div.style.marginBottom = '8px';
    div.innerHTML = `
        <div style="flex: 1.2;">
            <input type="text" class="form-input assign-class" placeholder="Class (e.g. Class 10)" value="${escapeHtml(cls)}">
        </div>
        <div style="flex: 1.5;">
            <input type="text" class="form-input assign-subject" list="school-subjects-datalist" placeholder="Subject (e.g. Science)" value="${escapeHtml(subj)}">
        </div>
        <div>
            <button type="button" class="btn btn-danger btn-sm" onclick="this.parentElement.parentElement.remove()">✕</button>
        </div>
    `;
    container.appendChild(div);
}

function editTeacher(id) {
    const t = teachersList.find(x => x.id === id);
    if (!t) return;
    document.getElementById('teacher-form-id').value = t.id;
    document.getElementById('teacher-form-name').value = t.name;
    document.getElementById('teacher-form-email').value = t.email;
    document.getElementById('teacher-form-pin').value = t.pin;
    document.getElementById('teacher-form-phone').value = t.phone || '';

    const container = document.getElementById('teacher-assignments-list');
    container.innerHTML = '';
    if (t.assigned_classes && t.assigned_classes.length > 0) {
        t.assigned_classes.forEach(a => addAssignmentRow(a.class, a.subject));
    } else {
        addAssignmentRow();
    }

    document.getElementById('teacher-modal-title').innerText = 'Edit Teacher';
    document.getElementById('teacher-modal').classList.add('active');
}

async function handleSaveTeacher(e) {
    e.preventDefault();
    const id = document.getElementById('teacher-form-id').value;
    const name = document.getElementById('teacher-form-name').value;
    const email = document.getElementById('teacher-form-email').value;
    const pin = document.getElementById('teacher-form-pin').value;
    const phone = document.getElementById('teacher-form-phone').value;

    const assignmentRows = document.querySelectorAll('.assignment-row');
    const assignments = [];
    assignmentRows.forEach(row => {
        const c = row.querySelector('.assign-class')?.value?.trim();
        const sub = row.querySelector('.assign-subject')?.value?.trim();
        if (c && sub) {
            assignments.push({ class: c, subject: sub });
        }
    });

    const payload = {
        name,
        email,
        pin,
        phone,
        assigned_classes: assignments
    };

    try {
        const url = id ? `/api/teachers/${id}` : '/api/teachers';
        const method = id ? 'PUT' : 'POST';
        const res = await fetch(url, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (!res.ok) throw new Error(await res.text());
        closeTeacherModal();
        await loadTeachers();
        showToast(id ? 'Teacher updated!' : 'Teacher added successfully!', 'success');
    } catch (err) {
        alert('Error: ' + err.message);
    }
}

async function deleteTeacher(id) {
    if (!confirm('Are you sure you want to remove this teacher?')) return;
    try {
        await fetch(`/api/teachers/${id}`, { method: 'DELETE' });
        await loadTeachers();
        showToast('Teacher removed', 'success');
    } catch (e) {
        alert('Error deleting teacher');
    }
}

// ----------------- Blueprints (Admin Specification) -----------------
async function loadBlueprints() {
    try {
        let url = '/api/blueprints';
        if (currentRole === 'teacher' && loggedInTeacher) {
            url += `?teacher_id=${loggedInTeacher.id}`;
        }
        const res = await fetch(url);
        blueprints = await res.json();
        renderBlueprintsList();
    } catch (e) {
        console.error('Error loading blueprints', e);
    }
}

function renderBlueprintsList() {
    const container = document.getElementById('blueprints-grid');
    if (!container) return;

    if (blueprints.length === 0) {
        container.innerHTML = `
            <div style="grid-column: 1 / -1; text-align: center; padding: 48px; background: white; border-radius: var(--radius-lg); border: 1px dashed var(--border-color);">
                <div style="font-size: 40px; margin-bottom: 12px;">📝</div>
                <h3 style="font-size: 18px; font-weight: 700;">No Question Papers Found</h3>
                <p style="color: var(--text-muted); margin-bottom: 16px;">Create a new blueprint specification to start generating papers.</p>
                <button class="btn btn-primary" onclick="switchTab('tab-create')">+ Create New Blueprint</button>
            </div>
        `;
        return;
    }

    container.innerHTML = blueprints.map(bp => {
        const entered = bp.entered_questions_count || 0;
        const target = bp.target_questions_count || 0;
        const pct = target > 0 ? Math.min(100, Math.round((entered / target) * 100)) : 0;
        
        let statusBadge = `<span class="badge badge-assigned">${bp.status || 'Assigned'}</span>`;
        if (bp.status === 'Questions_Submitted') statusBadge = `<span class="badge badge-submitted">Submitted</span>`;
        if (bp.status === 'Approved') statusBadge = `<span class="badge badge-approved">Approved</span>`;

        const isSubmitted = bp.status === 'Questions_Submitted' || bp.status === 'Approved';
        const isTeacher = currentRole === 'teacher';

        let actionsHtml = '';
        let warningBoxHtml = '';

        if (isTeacher) {
            // TEACHER VIEW:
            // 1. Download paper option (Print/PDF and Word DOCX) is completely removed for teachers
            // 2. Answer key is completely hidden from teachers
            // 3. Once paper is submitted, teacher cannot see the paper and a warning is shown
            if (isSubmitted) {
                warningBoxHtml = `
                    <div class="submitted-warning-box">
                        <span>⚠️ Paper is submitted to Admin! Questions are locked and cannot be viewed.</span>
                    </div>
                `;
                actionsHtml = `
                    <button class="btn btn-warning-submitted btn-sm" onclick="showPaperSubmittedWarning('${escapeHtml(bp.title)}')" style="width: 100%; display: flex; justify-content: center; align-items: center; gap: 6px;">
                        <span>🔒 Paper Submitted (Locked)</span>
                    </button>
                `;
            } else {
                actionsHtml = `
                    <button class="btn btn-primary btn-sm" onclick="openTeacherWorkspace(${bp.id})" style="width: 100%; display: flex; justify-content: center; align-items: center; gap: 6px;">
                        <span>✏ Enter Questions</span>
                    </button>
                `;
            }
        } else {
            // ADMIN VIEW:
            actionsHtml = `
                <a href="/paper/${bp.id}/print" target="_blank" class="btn btn-primary btn-sm" title="Preview and Print PDF">
                    🖨 Print / PDF
                </a>
                <a href="/api/paper/${bp.id}/docx" class="btn btn-emerald btn-sm" title="Download Word Document">
                    📄 Word (.docx)
                </a>
                <button class="btn btn-secondary btn-sm" onclick="cloneBlueprint(${bp.id})" title="Duplicate this blueprint for another class or section">
                    📋 Copy
                </button>
                <button class="btn btn-secondary btn-sm" onclick="openTeacherWorkspace(${bp.id})">
                    ✏ ${isSubmitted ? 'View Questions' : 'Enter Questions'}
                </button>
                ${isSubmitted ? `
                <button class="btn btn-reopen btn-sm" onclick="reopenBlueprint(${bp.id})" title="Unlock this paper so the teacher can edit again">
                    🔓 Reopen for Teacher
                </button>
                ` : ''}
                <button class="btn btn-danger btn-sm" onclick="deleteBlueprint(${bp.id})" style="margin-left: auto;">
                    🗑
                </button>
            `;
        }

        return `
            <div class="card">
                <div class="card-header">
                    <div>
                        <div class="card-title">${bp.title}</div>
                        <div class="card-subtitle">${bp.class_name} • ${bp.subject}</div>
                    </div>
                    ${statusBadge}
                </div>

                <div style="font-size: 13px; color: var(--dark-muted); margin-top: 8px;">
                    <div>⏱ <strong>${bp.duration_minutes} Mins</strong> | 🎯 <strong>${bp.total_marks} Marks</strong></div>
                    <div>👤 Teacher: <strong>${bp.teacher_name || 'Unassigned'}</strong></div>
                </div>

                <div class="progress-bar-container">
                    <div class="progress-labels">
                        <span>Questions Progress</span>
                        <span>${entered} / ${target} Qs (${pct}%)</span>
                    </div>
                    <div class="progress-track">
                        <div class="progress-fill" style="width: ${pct}%;"></div>
                    </div>
                </div>

                ${warningBoxHtml}

                <div class="card-actions">
                    ${actionsHtml}
                </div>
            </div>
        `;
    }).join('');
}

function showPaperSubmittedWarning(title) {
    const nameEl = document.getElementById('warning-paper-name');
    if (nameEl) nameEl.innerText = title || 'Question Paper';
    const modal = document.getElementById('submitted-warning-modal');
    if (modal) modal.classList.add('active');
}

function closeSubmittedWarningModal() {
    const modal = document.getElementById('submitted-warning-modal');
    if (modal) modal.classList.remove('active');
}

async function reopenBlueprint(bpId) {
    if (!confirm('Reopen this question paper? The assigned teacher will be able to view and edit questions again.')) return;
    try {
        const res = await fetch(`/api/blueprints/${bpId}/reopen`, { method: 'POST' });
        if (res.ok) {
            showToast('Question paper unlocked and reopened for teacher editing!', 'success');
            await loadBlueprints();
        }
    } catch (e) {
        alert('Failed to reopen paper');
    }
}

function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/'/g, "\\'").replace(/"/g, '&quot;');
}

// Dynamic Blueprint Sections Config
// Dynamic Blueprint Sections Config & Validation
let sectionConfigCounter = 0;

function updateBlueprintMarksSummary() {
    const targetMarksEl = document.getElementById('blueprint-total-marks');
    const targetMarks = targetMarksEl ? (parseFloat(targetMarksEl.value) || 0) : 80;
    
    let sumMarks = 0;
    let totalQuestions = 0;
    const boxes = document.querySelectorAll('#blueprint-sections-container .section-config-box');
    boxes.forEach(box => {
        const count = parseInt(box.querySelector('.bp-sec-count')?.value) || 0;
        const marks = parseFloat(box.querySelector('.bp-sec-marks')?.value) || 0;
        const subtotal = count * marks;
        sumMarks += subtotal;
        totalQuestions += count;
        
        const subEl = box.querySelector('.bp-sec-subtotal');
        if (subEl) {
            subEl.textContent = `${count} Qs × ${marks} m = ${subtotal.toFixed(subtotal % 1 === 0 ? 0 : 1)} Marks`;
        }
    });

    const badge = document.getElementById('bp-calculated-marks-badge');
    const targetDisp = document.getElementById('bp-target-marks-display');
    const statusBadge = document.getElementById('bp-marks-status-badge');
    
    if (badge) badge.textContent = `${sumMarks.toFixed(sumMarks % 1 === 0 ? 0 : 1)} Marks (${totalQuestions} Qs)`;
    if (targetDisp) targetDisp.textContent = targetMarks;
    
    if (statusBadge) {
        const diff = Math.round((sumMarks - targetMarks) * 100) / 100;
        if (Math.abs(diff) < 0.01) {
            statusBadge.style.background = '#dcfce7';
            statusBadge.style.color = '#15803d';
            statusBadge.style.border = '1px solid #86efac';
            statusBadge.innerHTML = `✓ Total Marks Match (${sumMarks} / ${targetMarks})`;
        } else if (diff < 0) {
            statusBadge.style.background = '#fef2f2';
            statusBadge.style.color = '#b91c1c';
            statusBadge.style.border = '1px solid #fecaca';
            statusBadge.innerHTML = `⚠️ Short by ${Math.abs(diff)} Marks (${sumMarks} / ${targetMarks})`;
        } else {
            statusBadge.style.background = '#fffbeb';
            statusBadge.style.color = '#b45309';
            statusBadge.style.border = '1px solid #fde68a';
            statusBadge.innerHTML = `⚠️ Exceeds by ${diff} Marks (${sumMarks} / ${targetMarks})`;
        }
    }
}

function addSectionConfigRow(name = '', type = 'Short_Answer', count = 5, marks = 2.0, instruction = '') {
    sectionConfigCounter++;
    const container = document.getElementById('blueprint-sections-container');
    const secId = `sec_${sectionConfigCounter}`;
    const subtotal = (count * marks).toFixed((count * marks) % 1 === 0 ? 0 : 1);
    
    const div = document.createElement('div');
    div.className = 'section-config-box';
    div.id = `box_${secId}`;
    div.innerHTML = `
        <div class="section-config-header" style="display: flex; align-items: center; justify-content: space-between;">
            <div style="display: flex; align-items: center; gap: 10px;">
                <span>Section Definition #${sectionConfigCounter}</span>
                <span class="bp-sec-subtotal" style="font-size: 11.5px; font-weight: 700; color: #1e40af; background: #dbeafe; padding: 2px 8px; border-radius: 4px;">
                    ${count} Qs × ${marks} m = ${subtotal} Marks
                </span>
            </div>
            <button type="button" class="btn btn-danger btn-sm" onclick="document.getElementById('box_${secId}').remove(); updateBlueprintMarksSummary();">Remove</button>
        </div>
        <div class="form-row">
            <div class="form-group" style="flex: 2;">
                <label class="form-label">Section Title</label>
                <input type="text" class="form-input bp-sec-name" value="${name || 'Section ' + String.fromCharCode(64 + sectionConfigCounter) + ' (Questions)'}" placeholder="e.g. Section A (Multiple Choice Questions)">
            </div>
            <div class="form-group" style="flex: 1.5;">
                <label class="form-label">Question Type</label>
                <select class="form-select bp-sec-type">
                    <option value="MCQ" ${type === 'MCQ' ? 'selected' : ''}>Multiple Choice (MCQ)</option>
                    <option value="VSA" ${type === 'VSA' ? 'selected' : ''}>Very Short Answer (VSA)</option>
                    <option value="Short_Answer" ${type === 'Short_Answer' ? 'selected' : ''}>Short Answer (SA)</option>
                    <option value="Long_Answer" ${type === 'Long_Answer' ? 'selected' : ''}>Long Answer (LA)</option>
                    <option value="Fill_Blanks" ${type === 'Fill_Blanks' ? 'selected' : ''}>Fill in the Blanks</option>
                    <option value="True_False" ${type === 'True_False' ? 'selected' : ''}>True / False</option>
                    <option value="Case_Study" ${type === 'Case_Study' ? 'selected' : ''}>Case Based / Diagram</option>
                </select>
            </div>
            <div class="form-group" style="flex: 1;">
                <label class="form-label">No. of Questions</label>
                <input type="number" min="1" class="form-input bp-sec-count" value="${count}" oninput="updateBlueprintMarksSummary()">
            </div>
            <div class="form-group" style="flex: 1;">
                <label class="form-label">Marks Each</label>
                <input type="number" step="0.5" min="0.5" class="form-input bp-sec-marks" value="${marks}" oninput="updateBlueprintMarksSummary()">
            </div>
        </div>
        <div class="form-group" style="margin-bottom: 0;">
            <label class="form-label">Section Instructions (Optional)</label>
            <input type="text" class="form-input bp-sec-inst" value="${instruction}" placeholder="e.g. All questions are compulsory. Internal choice provided in Q12.">
        </div>
    `;
    container.appendChild(div);
    updateBlueprintMarksSummary();
}

function resetBlueprintForm() {
    document.getElementById('blueprint-form').reset();
    document.getElementById('blueprint-sections-container').innerHTML = '';
    sectionConfigCounter = 0;
    // Add default CBSE-style sections (Total = 80 marks)
    addSectionConfigRow('Section A (Multiple Choice Questions)', 'MCQ', 20, 1.0, 'Select the correct option.');
    addSectionConfigRow('Section B (Very Short Answer Type)', 'VSA', 6, 2.0, 'Answer in 30-50 words.');
    addSectionConfigRow('Section C (Short Answer Type)', 'Short_Answer', 7, 3.0, 'Answer in 50-80 words.');
    addSectionConfigRow('Section D (Long Answer Type)', 'Long_Answer', 3, 5.0, 'Internal choice provided.');
    addSectionConfigRow('Section E (Case-Based Integrated)', 'Case_Study', 3, 4.0, 'Each case question carries 4 marks.');
    updateBlueprintMarksSummary();
}

async function handleCreateBlueprint(e) {
    e.preventDefault();
    if (!isAdminLoggedIn) {
        window.location.href = `/admin/login?next=${encodeURIComponent(window.location.pathname)}`;
        return;
    }
    const title = document.getElementById('blueprint-title').value.trim();
    const className = document.getElementById('blueprint-class').value.trim();
    const subject = document.getElementById('blueprint-subject').value.trim();
    const teacherId = document.getElementById('blueprint-teacher-id').value;
    const duration = parseInt(document.getElementById('blueprint-duration').value) || 180;
    const totalMarks = parseFloat(document.getElementById('blueprint-total-marks').value) || 80;
    const instructions = document.getElementById('blueprint-instructions').value;

    const secBoxes = document.querySelectorAll('.section-config-box');
    if (secBoxes.length === 0) {
        alert('Please add at least one section to the blueprint.');
        return;
    }

    let calculatedTotal = 0;
    const sectionsConfig = [];
    secBoxes.forEach((box, idx) => {
        const count = parseInt(box.querySelector('.bp-sec-count').value) || 1;
        const marks = parseFloat(box.querySelector('.bp-sec-marks').value) || 1.0;
        calculatedTotal += (count * marks);
        sectionsConfig.push({
            id: `sec_${idx + 1}`,
            name: box.querySelector('.bp-sec-name').value,
            type: box.querySelector('.bp-sec-type').value,
            count: count,
            marks_per_q: marks,
            instruction: box.querySelector('.bp-sec-inst').value || ''
        });
    });

    // STRICT VALIDATION: Questions * Marks must equal Total Marks
    if (Math.abs(calculatedTotal - totalMarks) > 0.01) {
        alert(`❌ Validation Error: Total Marks Mismatch!\n\nThe sum of (Questions × Marks) across all sections is ${calculatedTotal} marks, but the blueprint Total Marks is set to ${totalMarks} marks.\n\nPlease adjust the number of questions or marks per question in each section so the total equals exactly ${totalMarks} marks.`);
        return;
    }

    const payload = {
        title,
        class_name: className,
        section: '',
        subject,
        teacher_id: teacherId ? parseInt(teacherId) : null,
        duration_minutes: duration,
        total_marks: totalMarks,
        general_instructions: instructions,
        sections_config: sectionsConfig
    };

    try {
        const res = await fetch('/api/blueprints', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || 'Failed to create blueprint');
        }
        showToast('Question Paper Blueprint created successfully!', 'success');
        resetBlueprintForm();
        await loadBlueprints();
        switchTab('tab-papers');
    } catch (err) {
        alert('Failed to create blueprint: ' + err.message);
    }
}

async function cloneBlueprint(id) {
    try {
        const res = await fetch(`/api/blueprints/${id}/clone`, { method: 'POST' });
        if (!res.ok) throw new Error(await res.text());
        showToast('Blueprint duplicated successfully! You can now edit its class or section.', 'success');
        await loadBlueprints();
    } catch (e) {
        alert('Error duplicating blueprint: ' + e.message);
    }
}

async function deleteBlueprint(id) {
    if (!confirm('Are you sure you want to delete this question paper and all its questions?')) return;
    try {
        await fetch(`/api/blueprints/${id}`, { method: 'DELETE' });
        await loadBlueprints();
        showToast('Question Paper deleted', 'success');
    } catch (e) {
        alert('Error deleting paper');
    }
}

// ----------------- Teacher Entry Workspace -----------------
async function openTeacherWorkspace(bpId) {
    try {
        const res = await fetch(`/api/blueprints/${bpId}?role=${currentRole}`);
        activeBlueprint = await res.json();
        
        // If teacher attempts to open a submitted paper, block and show warning
        if (currentRole === 'teacher' && (activeBlueprint.is_locked || activeBlueprint.status === 'Questions_Submitted' || activeBlueprint.status === 'Approved')) {
            showPaperSubmittedWarning(activeBlueprint.title);
            return;
        }

        switchTab('tab-entry');
        setupTeacherWorkspace();
    } catch (e) {
        alert('Failed to load blueprint details');
    }
}

function setupTeacherWorkspace() {
    if (!activeBlueprint) return;
    document.getElementById('workspace-title').innerText = `${activeBlueprint.title} (${activeBlueprint.class_name} - ${activeBlueprint.subject})`;
    
    // Build list of slots based on sections_config
    const slots = [];
    let qCounter = 1;
    (activeBlueprint.sections_config || []).forEach(sec => {
        for (let i = 0; i < sec.count; i++) {
            // Find existing question if entered
            const existing = (activeBlueprint.questions || []).find(q => q.question_number === qCounter);
            slots.push({
                question_number: qCounter,
                section_id: sec.id,
                section_name: sec.name,
                question_type: sec.type,
                marks: sec.marks_per_q,
                data: existing || null
            });
            qCounter++;
        }
    });

    currentBlueprintQuestions = slots;
    renderQuestionNavigationList();
    loadQuestionIntoForm(0);
}

function renderQuestionNavigationList() {
    const listEl = document.getElementById('q-nav-list');
    listEl.innerHTML = currentBlueprintQuestions.map((slot, idx) => {
        const isFilled = slot.data && slot.data.question_text;
        const isActive = idx === currentQuestionIndex;
        return `
            <div class="q-nav-item ${isActive ? 'active' : ''} ${isFilled ? 'filled' : ''}" onclick="loadQuestionIntoForm(${idx})">
                <div>
                    <strong>Q${slot.question_number}</strong>
                    <span style="font-size: 11.5px; color: var(--text-muted); margin-left: 6px;">(${slot.question_type.replace('_', ' ')})</span>
                </div>
                <div>
                    <span style="font-size: 11.5px; font-weight: 700; color: var(--primary);">[${slot.marks}M]</span>
                    ${isFilled ? ' <span style="color: var(--success); font-weight: 700;">✓</span>' : ''}
                </div>
            </div>
        `;
    }).join('');
}

function loadQuestionIntoForm(index) {
    currentQuestionIndex = index;
    renderQuestionNavigationList();
    const slot = currentBlueprintQuestions[index];
    if (!slot) return;

    document.getElementById('q-form-num-display').innerText = `Question ${slot.question_number} of ${currentBlueprintQuestions.length}`;
    document.getElementById('q-form-section-display').innerText = slot.section_name;
    document.getElementById('q-form-type').value = slot.question_type;
    document.getElementById('q-form-marks').value = slot.marks;

    const data = slot.data || {};
    document.getElementById('q-form-text').value = data.question_text || '';
    document.getElementById('q-form-or-text').value = data.or_question_text || '';

    // MCQ Options
    const isMcq = slot.question_type === 'MCQ';
    document.getElementById('mcq-options-container').style.display = isMcq ? 'block' : 'none';
    if (isMcq) {
        const opts = data.options || ['', '', '', ''];
        document.getElementById('mcq-opt-a').value = opts[0] || '';
        document.getElementById('mcq-opt-b').value = opts[1] || '';
        document.getElementById('mcq-opt-c').value = opts[2] || '';
        document.getElementById('mcq-opt-d').value = opts[3] || '';
    }

    // Images
    document.getElementById('q-img-preview-box').innerHTML = data.image_path ? 
        `<img src="/${data.image_path}" style="max-height: 120px; border-radius: 6px; border: 1px solid #cbd5e1;">` : '';
    document.getElementById('q-current-img-path').value = data.image_path || '';

    document.getElementById('or-img-preview-box').innerHTML = data.or_image_path ? 
        `<img src="/${data.or_image_path}" style="max-height: 120px; border-radius: 6px; border: 1px solid #cbd5e1;">` : '';
    document.getElementById('or-current-img-path').value = data.or_image_path || '';

    updateMathPreview();
}

function updateMathPreview() {
    const text = document.getElementById('q-form-text').value;
    const previewEl = document.getElementById('q-math-preview');
    if (!text.trim()) {
        previewEl.innerHTML = '<span style="color: var(--text-muted); font-style: italic;">LaTeX math preview will appear here (e.g. $x^2 + y^2 = r^2$ or $\\frac{a}{b}$)...</span>';
        return;
    }

    previewEl.innerHTML = text;
    if (window.renderMathInElement) {
        window.renderMathInElement(previewEl, {
            delimiters: [
                {left: '$$', right: '$$', display: true},
                {left: '$', right: '$', display: false}
            ],
            throwOnError: false
        });
    }
}

async function handleQuestionSave(e) {
    if (e) e.preventDefault();
    const slot = currentBlueprintQuestions[currentQuestionIndex];
    if (!slot) return;

    const qText = document.getElementById('q-form-text').value.trim();
    if (!qText) {
        alert('Please enter question text before saving.');
        return;
    }

    let options = [];
    if (slot.question_type === 'MCQ') {
        options = [
            document.getElementById('mcq-opt-a').value.trim(),
            document.getElementById('mcq-opt-b').value.trim(),
            document.getElementById('mcq-opt-c').value.trim(),
            document.getElementById('mcq-opt-d').value.trim()
        ];
    }

    const payload = {
        blueprint_id: activeBlueprint.id,
        section_id: slot.section_id,
        section_name: slot.section_name,
        question_number: slot.question_number,
        question_type: slot.question_type,
        question_text: qText,
        options: options,
        correct_answer: '',
        solution_explanation: '',
        marks: parseFloat(document.getElementById('q-form-marks').value) || slot.marks,
        image_path: document.getElementById('q-current-img-path').value || '',
        or_question_text: document.getElementById('q-form-or-text').value.trim(),
        or_image_path: document.getElementById('or-current-img-path').value || ''
    };

    try {
        const res = await fetch(`/api/blueprints/${activeBlueprint.id}/questions`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (!res.ok) throw new Error(await res.text());
        
        slot.data = payload;
        showToast(`Q${slot.question_number} saved!`, 'success');
        
        // Move to next question automatically if available
        if (currentQuestionIndex < currentBlueprintQuestions.length - 1) {
            loadQuestionIntoForm(currentQuestionIndex + 1);
        } else {
            renderQuestionNavigationList();
        }
    } catch (err) {
        alert('Error saving question: ' + err.message);
    }
}

async function uploadQuestionDiagram(input, target) {
    if (!input.files || !input.files[0]) return;
    const formData = new FormData();
    formData.append('file', input.files[0]);

    try {
        const res = await fetch('/api/upload-diagram', {
            method: 'POST',
            body: formData
        });
        const data = await res.json();
        if (data.image_path) {
            if (target === 'main') {
                document.getElementById('q-current-img-path').value = data.image_path;
                document.getElementById('q-img-preview-box').innerHTML = 
                    `<img src="/${data.image_path}" style="max-height: 120px; border-radius: 6px; border: 1px solid #cbd5e1;">`;
            } else {
                document.getElementById('or-current-img-path').value = data.image_path;
                document.getElementById('or-img-preview-box').innerHTML = 
                    `<img src="/${data.image_path}" style="max-height: 120px; border-radius: 6px; border: 1px solid #cbd5e1;">`;
            }
            showToast('Diagram image uploaded!', 'success');
        }
    } catch (e) {
        alert('Failed to upload diagram: ' + e.message);
    }
}

async function submitPaperToAdmin() {
    if (!activeBlueprint) return;
    const unfilled = currentBlueprintQuestions.filter(s => !s.data || !s.data.question_text);
    if (unfilled.length > 0) {
        if (!confirm(`Warning: ${unfilled.length} questions are still empty.\n\nDo you still want to submit to the Admin?\n\nIMPORTANT: Once submitted, the paper will be LOCKED immediately. You will NOT be able to view or edit the questions.`)) {
            return;
        }
    } else {
        if (!confirm('Are you ready to submit this question paper to the Admin?\n\nIMPORTANT: Once submitted, the paper will be LOCKED immediately and you will no longer be able to view or edit the questions.')) {
            return;
        }
    }

    const formData = new FormData();
    formData.append('status', 'Questions_Submitted');

    try {
        await fetch(`/api/blueprints/${activeBlueprint.id}/status`, {
            method: 'PUT',
            body: formData
        });
        showToast('Question paper successfully submitted to Admin! Locked for review.', 'success');
        const submittedTitle = activeBlueprint.title;
        activeBlueprint.status = 'Questions_Submitted';
        switchTab('tab-papers');
        showPaperSubmittedWarning(submittedTitle);
    } catch (e) {
        alert('Error submitting paper');
    }
}

// ----------------- Bulk Blueprint Generator -----------------
const ALL_BULK_CLASSES = [
    'Class 1', 'Class 2', 'Class 3', 'Class 4', 'Class 5',
    'Class 6', 'Class 7', 'Class 8', 'Class 9', 'Class 10',
    'Class 11', 'Class 12'
];

const ALL_BULK_SUBJECTS = [
    'English', 'Hindi', 'Mathematics', 'Science', 'Social Science',
    'Physics', 'Chemistry', 'Biology', 'Computer Science', 'Sanskrit'
];

let bulkSectionCounter = 0;

function openBulkBlueprintModal() {
    if (!isAdminLoggedIn) {
        window.location.href = `/admin/login?next=${encodeURIComponent(window.location.pathname)}`;
        return;
    }

    // Populate classes
    const classContainer = document.getElementById('bulk-class-chips');
    if (classContainer) {
        classContainer.innerHTML = ALL_BULK_CLASSES.map((cls, i) => `
            <label style="display: flex; align-items: center; gap: 5px; font-size: 12.5px; background: white; padding: 4px 10px; border-radius: 20px; border: 1px solid #cbd5e1; cursor: pointer;">
                <input type="checkbox" class="bulk-class-chk" value="${cls}" ${i >= 8 && i <= 9 ? 'checked' : ''} onchange="updateBulkCountPreview()">
                <span>${cls}</span>
            </label>
        `).join('');
    }

    // Populate subjects
    const subjectContainer = document.getElementById('bulk-subject-chips');
    const availableSubjects = (schoolSubjects && schoolSubjects.length > 0) ? schoolSubjects : ALL_BULK_SUBJECTS;
    if (subjectContainer) {
        subjectContainer.innerHTML = availableSubjects.map((subj, i) => `
            <label style="display: flex; align-items: center; gap: 5px; font-size: 12.5px; background: white; padding: 4px 10px; border-radius: 20px; border: 1px solid #cbd5e1; cursor: pointer;">
                <input type="checkbox" class="bulk-subject-chk" value="${escapeHtml(subj)}" ${i === 2 ? 'checked' : ''} onchange="updateBulkCountPreview()">
                <span>${escapeHtml(subj)}</span>
            </label>
        `).join('');
    }

    // Populate teachers dropdown in bulk modal
    const teacherSelect = document.getElementById('bulk-bp-teacher-id');
    if (teacherSelect && teachersList) {
        teacherSelect.innerHTML = `<option value="">⚡ Auto-Match by Teacher's Assigned Classes</option>` +
            teachersList.map(t => `<option value="${t.id}">${escapeHtml(t.name)} (${t.email})</option>`).join('');
    }

    // Setup default sections if empty
    const secContainer = document.getElementById('bulk-sections-container');
    if (secContainer && secContainer.children.length === 0) {
        resetBulkSections();
    }

    updateBulkCountPreview();
    updateBulkMarksSummary();
    document.getElementById('bulk-blueprint-modal').classList.add('active');
}

function closeBulkBlueprintModal() {
    document.getElementById('bulk-blueprint-modal').classList.remove('active');
}

function selectBulkClasses(list) {
    document.querySelectorAll('.bulk-class-chk').forEach(chk => {
        chk.checked = list.includes(chk.value);
    });
    updateBulkCountPreview();
}

function selectBulkSubjects(list) {
    document.querySelectorAll('.bulk-subject-chk').forEach(chk => {
        chk.checked = list.includes(chk.value);
    });
    updateBulkCountPreview();
}

function updateBulkCountPreview() {
    const checkedClasses = Array.from(document.querySelectorAll('.bulk-class-chk:checked')).map(c => c.value);
    const checkedSubjects = Array.from(document.querySelectorAll('.bulk-subject-chk:checked')).map(s => s.value);

    const total = checkedClasses.length * checkedSubjects.length;
    const badge = document.getElementById('bulk-papers-count-badge');
    const submitBtn = document.getElementById('btn-submit-bulk-bp');
    
    if (badge) {
        badge.textContent = `${total} Question Paper${total === 1 ? '' : 's'} (${checkedClasses.length} Classes × ${checkedSubjects.length} Subjs)`;
    }
    if (submitBtn) {
        submitBtn.innerHTML = `⚡ Generate ${total} Blueprints`;
        submitBtn.disabled = total === 0;
    }
}

function resetBulkSections() {
    const container = document.getElementById('bulk-sections-container');
    if (!container) return;
    container.innerHTML = '';
    bulkSectionCounter = 0;
    addBulkSectionConfigRow('Section A (Multiple Choice Questions)', 'MCQ', 20, 1.0, 'Select the correct option.');
    addBulkSectionConfigRow('Section B (Very Short Answer Type)', 'VSA', 6, 2.0, 'Answer in 30-50 words.');
    addBulkSectionConfigRow('Section C (Short Answer Type)', 'Short_Answer', 7, 3.0, 'Answer in 50-80 words.');
    addBulkSectionConfigRow('Section D (Long Answer Type)', 'Long_Answer', 3, 5.0, 'Internal choice provided.');
    addBulkSectionConfigRow('Section E (Case-Based Integrated)', 'Case_Study', 3, 4.0, 'Each case question carries 4 marks.');
    updateBulkMarksSummary();
}

function addBulkSectionConfigRow(name = '', type = 'Short_Answer', count = 5, marks = 2.0, instruction = '') {
    bulkSectionCounter++;
    const container = document.getElementById('bulk-sections-container');
    const secId = `bulk_sec_${bulkSectionCounter}`;
    const subtotal = (count * marks).toFixed((count * marks) % 1 === 0 ? 0 : 1);
    
    const div = document.createElement('div');
    div.className = 'section-config-box bulk-sec-box';
    div.id = `box_${secId}`;
    div.innerHTML = `
        <div class="section-config-header" style="display: flex; align-items: center; justify-content: space-between;">
            <div style="display: flex; align-items: center; gap: 10px;">
                <span>Section #${bulkSectionCounter}</span>
                <span class="bulk-sec-subtotal" style="font-size: 11.5px; font-weight: 700; color: #1e40af; background: #dbeafe; padding: 2px 8px; border-radius: 4px;">
                    ${count} Qs × ${marks} m = ${subtotal} Marks
                </span>
            </div>
            <button type="button" class="btn btn-danger btn-sm" onclick="document.getElementById('box_${secId}').remove(); updateBulkMarksSummary();">Remove</button>
        </div>
        <div class="form-row">
            <div class="form-group" style="flex: 2;">
                <label class="form-label">Section Title</label>
                <input type="text" class="form-input bulk-bp-sec-name" value="${name || 'Section ' + String.fromCharCode(64 + bulkSectionCounter)}" placeholder="e.g. Section A">
            </div>
            <div class="form-group" style="flex: 1.5;">
                <label class="form-label">Question Type</label>
                <select class="form-select bulk-bp-sec-type">
                    <option value="MCQ" ${type === 'MCQ' ? 'selected' : ''}>Multiple Choice (MCQ)</option>
                    <option value="VSA" ${type === 'VSA' ? 'selected' : ''}>Very Short Answer (VSA)</option>
                    <option value="Short_Answer" ${type === 'Short_Answer' ? 'selected' : ''}>Short Answer (SA)</option>
                    <option value="Long_Answer" ${type === 'Long_Answer' ? 'selected' : ''}>Long Answer (LA)</option>
                    <option value="Fill_Blanks" ${type === 'Fill_Blanks' ? 'selected' : ''}>Fill in the Blanks</option>
                    <option value="True_False" ${type === 'True_False' ? 'selected' : ''}>True / False</option>
                    <option value="Case_Study" ${type === 'Case_Study' ? 'selected' : ''}>Case Based / Diagram</option>
                </select>
            </div>
            <div class="form-group" style="flex: 1;">
                <label class="form-label">No. of Qs</label>
                <input type="number" min="1" class="form-input bulk-bp-sec-count" value="${count}" oninput="updateBulkMarksSummary()">
            </div>
            <div class="form-group" style="flex: 1;">
                <label class="form-label">Marks</label>
                <input type="number" step="0.5" min="0.5" class="form-input bulk-bp-sec-marks" value="${marks}" oninput="updateBulkMarksSummary()">
            </div>
        </div>
        <div class="form-group" style="margin-bottom: 0;">
            <label class="form-label">Instructions (Optional)</label>
            <input type="text" class="form-input bulk-bp-sec-inst" value="${instruction}" placeholder="e.g. All questions are compulsory.">
        </div>
    `;
    container.appendChild(div);
    updateBulkMarksSummary();
}

function updateBulkMarksSummary() {
    const targetMarksEl = document.getElementById('bulk-bp-total-marks');
    const targetMarks = targetMarksEl ? (parseFloat(targetMarksEl.value) || 0) : 80;
    
    let sumMarks = 0;
    let totalQuestions = 0;
    const boxes = document.querySelectorAll('#bulk-sections-container .bulk-sec-box');
    boxes.forEach(box => {
        const count = parseInt(box.querySelector('.bulk-bp-sec-count')?.value) || 0;
        const marks = parseFloat(box.querySelector('.bulk-bp-sec-marks')?.value) || 0;
        const subtotal = count * marks;
        sumMarks += subtotal;
        totalQuestions += count;
        
        const subEl = box.querySelector('.bulk-sec-subtotal');
        if (subEl) {
            subEl.textContent = `${count} Qs × ${marks} m = ${subtotal.toFixed(subtotal % 1 === 0 ? 0 : 1)} Marks`;
        }
    });

    const badge = document.getElementById('bulk-calculated-marks-badge');
    const targetDisp = document.getElementById('bulk-target-marks-display');
    const statusBadge = document.getElementById('bulk-marks-status-badge');
    
    if (badge) badge.textContent = `${sumMarks.toFixed(sumMarks % 1 === 0 ? 0 : 1)} Marks (${totalQuestions} Qs)`;
    if (targetDisp) targetDisp.textContent = targetMarks;
    
    if (statusBadge) {
        const diff = Math.round((sumMarks - targetMarks) * 100) / 100;
        if (Math.abs(diff) < 0.01) {
            statusBadge.style.background = '#dcfce7';
            statusBadge.style.color = '#15803d';
            statusBadge.style.border = '1px solid #86efac';
            statusBadge.innerHTML = `✓ Total Marks Match (${sumMarks} / ${targetMarks})`;
        } else if (diff < 0) {
            statusBadge.style.background = '#fef2f2';
            statusBadge.style.color = '#b91c1c';
            statusBadge.style.border = '1px solid #fecaca';
            statusBadge.innerHTML = `⚠️ Short by ${Math.abs(diff)} Marks (${sumMarks} / ${targetMarks})`;
        } else {
            statusBadge.style.background = '#fffbeb';
            statusBadge.style.color = '#b45309';
            statusBadge.style.border = '1px solid #fde68a';
            statusBadge.innerHTML = `⚠️ Exceeds by ${diff} Marks (${sumMarks} / ${targetMarks})`;
        }
    }
}

async function handleBulkCreateBlueprint(e) {
    e.preventDefault();
    if (!isAdminLoggedIn) {
        window.location.href = `/admin/login?next=${encodeURIComponent(window.location.pathname)}`;
        return;
    }
    const title = document.getElementById('bulk-bp-title').value.trim();
    const checkedClasses = Array.from(document.querySelectorAll('.bulk-class-chk:checked')).map(c => c.value);
    const checkedSubjects = Array.from(document.querySelectorAll('.bulk-subject-chk:checked')).map(s => s.value);
    const teacherId = document.getElementById('bulk-bp-teacher-id').value;
    const duration = parseInt(document.getElementById('bulk-bp-duration').value) || 180;
    const totalMarks = parseFloat(document.getElementById('bulk-bp-total-marks').value) || 80;
    const instructions = document.getElementById('bulk-bp-instructions').value;

    if (checkedClasses.length === 0) {
        alert('Please select at least one class.');
        return;
    }
    if (checkedSubjects.length === 0) {
        alert('Please select at least one subject.');
        return;
    }

    const secBoxes = document.querySelectorAll('#bulk-sections-container .bulk-sec-box');
    if (secBoxes.length === 0) {
        alert('Please add at least one section to the blueprint structure.');
        return;
    }

    let calculatedTotal = 0;
    const sectionsConfig = [];
    secBoxes.forEach((box, idx) => {
        const count = parseInt(box.querySelector('.bulk-bp-sec-count').value) || 1;
        const marks = parseFloat(box.querySelector('.bulk-bp-sec-marks').value) || 1.0;
        calculatedTotal += (count * marks);
        sectionsConfig.push({
            id: `sec_${idx + 1}`,
            name: box.querySelector('.bulk-bp-sec-name').value,
            type: box.querySelector('.bulk-bp-sec-type').value,
            count: count,
            marks_per_q: marks,
            instruction: box.querySelector('.bulk-bp-sec-inst').value || ''
        });
    });

    // STRICT VALIDATION: Questions * Marks must equal Total Marks
    if (Math.abs(calculatedTotal - totalMarks) > 0.01) {
        alert(`❌ Validation Error: Total Marks Mismatch!\n\nThe sum of (Questions × Marks) across all sections is ${calculatedTotal} marks, but the blueprint Total Marks is set to ${totalMarks} marks.\n\nPlease adjust the number of questions or marks per question in each section so the total equals exactly ${totalMarks} marks.`);
        return;
    }

    const payload = {
        title,
        classes: checkedClasses,
        sections: [""],
        subjects: checkedSubjects,
        teacher_id: teacherId ? parseInt(teacherId) : null,
        duration_minutes: duration,
        total_marks: totalMarks,
        general_instructions: instructions,
        sections_config: sectionsConfig
    };

    const submitBtn = document.getElementById('btn-submit-bulk-bp');
    submitBtn.disabled = true;
    submitBtn.innerText = 'Creating Blueprints...';

    try {
        const res = await fetch('/api/blueprints/bulk', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || 'Failed to create bulk blueprints');
        }
        const data = await res.json();
        showToast(data.message || `Successfully created ${data.created_count} blueprints!`, 'success');
        closeBulkBlueprintModal();
        await loadBlueprints();
        switchTab('tab-papers');
    } catch (err) {
        alert('Failed to generate bulk blueprints: ' + err.message);
    } finally {
        submitBtn.disabled = false;
        updateBulkCountPreview();
    }
}

// ----------------- UI Helpers & Toasts -----------------
function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.style.position = 'fixed';
    toast.style.bottom = '24px';
    toast.style.right = '24px';
    toast.style.padding = '12px 20px';
    toast.style.background = type === 'success' ? '#10b981' : '#3b82f6';
    toast.style.color = '#ffffff';
    toast.style.borderRadius = '8px';
    toast.style.boxShadow = '0 10px 15px -3px rgba(0,0,0,0.2)';
    toast.style.fontWeight = '600';
    toast.style.fontSize = '13.5px';
    toast.style.zIndex = '9999';
    toast.style.transition = 'all 0.3s ease';
    toast.innerText = message;

    document.body.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 300);
    }, 2800);
}

function initEventListeners() {
    document.querySelectorAll('.nav-tab-btn').forEach(btn => {
        btn.addEventListener('click', () => switchTab(btn.dataset.tab));
    });

    // Explicit logout button listener
    const logoutBtn = document.getElementById('user-logout-btn');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', (e) => {
            e.preventDefault();
            handleUserLogout();
        });
    }

    // LaTeX live input listener
    const qTextInput = document.getElementById('q-form-text');
    if (qTextInput) {
        qTextInput.addEventListener('input', updateMathPreview);
    }

    // Default sections for new blueprint form
    resetBlueprintForm();
}
