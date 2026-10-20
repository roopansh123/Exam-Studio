const express = require('express');
const { default: makeWASocket, useMultiFileAuthState, DisconnectReason, Browsers } = require('@whiskeysockets/baileys');
const { Boom } = require('@hapi/boom');
const qrcode = require('qrcode');
const pino = require('pino');
const path = require('path');
const fs = require('fs');
const http = require('http');

const app = express();
app.use(express.json());

const PORT = process.env.WA_BRIDGE_PORT || 3001;
let pythonPort = process.env.PYTHON_PORT ? parseInt(process.env.PYTHON_PORT, 10) : 8000;
const AUTH_DIR = process.env.WA_AUTH_DIR || path.join(__dirname, 'auth_info');

if (!fs.existsSync(AUTH_DIR)) {
    fs.mkdirSync(AUTH_DIR, { recursive: true });
}

let sock = null;
let isConnecting = false;
let connectionStatus = 'initializing';
let currentQrBase64 = null;
let connectedPhone = null;

// In-memory message store for Baileys retry and decryption requests
const messageStore = new Map();
function storeMessage(keyId, message) {
    if (!keyId) return;
    messageStore.set(keyId, message);
    if (messageStore.size > 1000) {
        const firstKey = messageStore.keys().next().value;
        messageStore.delete(firstKey);
    }
}

// Format phone number into E.164 digits
function formatWaNumber(phone) {
    let digits = String(phone || '').replace(/\D/g, '');
    if (digits.length === 10 && /^[6-9]/.test(digits)) {
        digits = '91' + digits;
    } else if (digits.length === 11 && digits.startsWith('0')) {
        digits = '91' + digits.slice(1);
    }
    return digits;
}

// Allow dynamic reconfiguration of Python backend port
app.post('/configure', (req, res) => {
    if (req.body && req.body.python_port) {
        pythonPort = parseInt(req.body.python_port, 10);
        console.log(`[WhatsApp Bridge] Python backend port updated to ${pythonPort}`);
    }
    res.json({ success: true, python_port: pythonPort });
});

async function notifyPythonBackend(endpoint, data) {
    try {
        const payload = JSON.stringify(data);
        const req = http.request({
            hostname: '127.0.0.1',
            port: pythonPort,
            path: endpoint,
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Content-Length': Buffer.byteLength(payload)
            },
            timeout: 8000
        }, (res) => {
            let resBody = '';
            res.on('data', chunk => resBody += chunk);
            res.on('end', () => {});
        });
        req.on('error', () => {});
        req.write(payload);
        req.end();
    } catch (e) {
        // Silently ignore if Python backend is busy
    }
}

async function forwardMessageToPython(fromPhone, text) {
    return new Promise((resolve) => {
        try {
            const payload = JSON.stringify({ from: fromPhone, text: text });
            const req = http.request({
                hostname: '127.0.0.1',
                port: pythonPort,
                path: '/api/whatsapp/internal/incoming',
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Content-Length': Buffer.byteLength(payload)
                },
                timeout: 10000
            }, (res) => {
                let resBody = '';
                res.on('data', chunk => resBody += chunk);
                res.on('end', () => {
                    try {
                        const parsed = JSON.parse(resBody);
                        resolve(parsed.reply || null);
                    } catch (err) {
                        resolve(null);
                    }
                });
            });
            req.on('error', (err) => {
                console.error('[WhatsApp Bridge] Failed to forward message to Python backend:', err.message);
                resolve(null);
            });
            req.write(payload);
            req.end();
        } catch (e) {
            resolve(null);
        }
    });
}

async function connectToWhatsApp() {
    if (isConnecting) return;
    isConnecting = true;

    if (sock) {
        try {
            sock.ev.removeAllListeners();
            sock.end();
        } catch (e) {}
        sock = null;
    }

    try {
        const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);

        sock = makeWASocket({
            auth: state,
            logger: pino({ level: 'warn' }),
            printQRInTerminal: false,
            browser: Browsers.macOS('Desktop'),
            syncFullHistory: false,
            markOnlineOnConnect: true,
            getMessage: async (key) => {
                if (key && key.id && messageStore.has(key.id)) {
                    return messageStore.get(key.id);
                }
                return { conversation: '' };
            }
        });

        sock.ev.on('connection.update', async (update) => {
            const { connection, lastDisconnect, qr } = update;

            if (qr) {
                try {
                    currentQrBase64 = await qrcode.toDataURL(qr, {
                        margin: 2,
                        width: 280,
                        color: {
                            dark: '#0f172a',
                            light: '#ffffff'
                        }
                    });
                    connectionStatus = 'qr_ready';
                    console.log('[WhatsApp Bridge] New Official QR Code generated. Ready for scanning.');
                } catch (e) {
                    console.error('[WhatsApp Bridge] Error rendering QR code data URL:', e);
                }
            }

            if (connection === 'close') {
                const statusCode = lastDisconnect?.error?.output?.statusCode;
                const isLoggedOut = statusCode === DisconnectReason.loggedOut;
                console.log(`[WhatsApp Bridge] Connection closed (status: ${statusCode}). Reconnecting: ${!isLoggedOut}`);
                
                connectionStatus = isLoggedOut ? 'logged_out' : 'disconnected';
                currentQrBase64 = null;
                connectedPhone = null;

                notifyPythonBackend('/api/whatsapp/internal/status', {
                    status: connectionStatus,
                    connected: false
                });

                if (isLoggedOut) {
                    try {
                        fs.rmSync(AUTH_DIR, { recursive: true, force: true });
                        fs.mkdirSync(AUTH_DIR, { recursive: true });
                    } catch (e) {}
                }

                setTimeout(() => {
                    isConnecting = false;
                    connectToWhatsApp();
                }, isLoggedOut ? 1500 : 2500);

            } else if (connection === 'open') {
                connectionStatus = 'connected';
                currentQrBase64 = null;
                connectedPhone = sock.user?.id ? sock.user.id.split(':')[0] : 'connected';
                console.log(`[WhatsApp Bridge] Successfully connected to WhatsApp! Account: +${connectedPhone}`);

                notifyPythonBackend('/api/whatsapp/internal/status', {
                    status: 'connected',
                    connected: true,
                    phone: connectedPhone
                });
                isConnecting = false;
            }
        });

        sock.ev.on('creds.update', saveCreds);

        // Handle incoming messages from teachers
        sock.ev.on('messages.upsert', async ({ messages, type }) => {
            if (type !== 'notify') return;

            for (const msg of messages) {
                if (msg.key.fromMe) continue;
                const remoteJid = msg.key.remoteJid;
                if (!remoteJid || remoteJid.includes('@broadcast') || remoteJid.includes('@g.us')) continue;

                const fromPhone = remoteJid.split('@')[0];
                const text = msg.message?.conversation ||
                             msg.message?.extendedTextMessage?.text ||
                             msg.message?.imageMessage?.caption ||
                             '';

                if (!text || !text.trim()) continue;

                console.log(`[WhatsApp Bridge] Incoming message from ${fromPhone}: "${text.trim().substring(0, 50)}..."`);

                // Forward to Python backend for question ingestion
                const replyText = await forwardMessageToPython(fromPhone, text.trim());
                if (replyText) {
                    try {
                        const replySent = await sock.sendMessage(remoteJid, { text: replyText });
                        if (replySent?.key?.id) {
                            storeMessage(replySent.key.id, replySent.message);
                        }
                        console.log(`[WhatsApp Bridge] Sent auto-reply to ${fromPhone}`);
                    } catch (err) {
                        console.error(`[WhatsApp Bridge] Error sending reply to ${fromPhone}:`, err.message);
                    }
                }
            }
        });

    } catch (err) {
        console.error('[WhatsApp Bridge] Fatal error in connectToWhatsApp:', err);
        connectionStatus = 'error';
        isConnecting = false;
        setTimeout(connectToWhatsApp, 5000);
    }
}

// ----------------- EXPRESS API ENDPOINTS -----------------

// Status and QR Code
app.get('/status', (req, res) => {
    res.json({
        status: connectionStatus,
        connected: connectionStatus === 'connected',
        qr_code: currentQrBase64,
        phone: connectedPhone
    });
});

// Outgoing message sender
app.post('/send-message', async (req, res) => {
    const { phone, message } = req.body;

    if (connectionStatus !== 'connected' || !sock) {
        return res.status(400).json({ 
            success: false, 
            error: 'WhatsApp is not connected yet. Please scan the barcode with your phone first.' 
        });
    }

    if (!phone || !message) {
        return res.status(400).json({ 
            success: false, 
            error: 'Recipient phone and message are required.' 
        });
    }

    const cleanPhone = formatWaNumber(phone);
    if (!cleanPhone || cleanPhone.length < 8) {
        return res.status(400).json({ 
            success: false, 
            error: `Invalid recipient phone number: ${phone}` 
        });
    }

    try {
        console.log(`[WhatsApp Bridge] Verifying WhatsApp account for +${cleanPhone}...`);
        let targetJid = `${cleanPhone}@s.whatsapp.net`;

        try {
            const onWaList = await sock.onWhatsApp(cleanPhone);
            console.log(`[WhatsApp Bridge] onWhatsApp result for ${cleanPhone}:`, JSON.stringify(onWaList));

            if (!onWaList || onWaList.length === 0 || !onWaList[0]?.exists) {
                return res.status(400).json({
                    success: false,
                    error: `Phone number +${cleanPhone} is not registered on WhatsApp. Please check the recipient's phone number.`
                });
            }
            targetJid = onWaList[0].jid;
        } catch (checkErr) {
            console.warn(`[WhatsApp Bridge] onWhatsApp lookup warning:`, checkErr.message);
        }

        console.log(`[WhatsApp Bridge] Delivering message to ${targetJid}...`);
        const sent = await sock.sendMessage(targetJid, { text: message });

        if (sent?.key?.id) {
            storeMessage(sent.key.id, sent.message);
            console.log(`[WhatsApp Bridge] Successfully transmitted message to ${targetJid} (Msg ID: ${sent.key.id})`);
        }

        return res.json({ 
            success: true, 
            message: `Delivered message to +${cleanPhone}`,
            jid: targetJid,
            message_id: sent?.key?.id || null
        });
    } catch (err) {
        console.error(`[WhatsApp Bridge] Error sending message to ${cleanPhone}:`, err);
        return res.status(500).json({ 
            success: false, 
            error: `Failed to deliver WhatsApp message: ${err.message}` 
        });
    }
});

// Logout / Disconnect
app.post('/logout', async (req, res) => {
    try {
        if (sock) {
            try {
                await sock.logout();
            } catch (logoutErr) {
                console.warn('[WhatsApp Bridge] sock.logout error (ignoring):', logoutErr.message);
                try {
                    sock.ev.removeAllListeners();
                    sock.end();
                } catch (e) {}
            }
            sock = null;
        }
        try {
            fs.rmSync(AUTH_DIR, { recursive: true, force: true });
            fs.mkdirSync(AUTH_DIR, { recursive: true });
        } catch (e) {}

        connectionStatus = 'disconnected';
        currentQrBase64 = null;
        connectedPhone = null;

        notifyPythonBackend('/api/whatsapp/internal/status', {
            status: 'disconnected',
            connected: false,
            phone: null
        });

        setTimeout(() => {
            connectToWhatsApp();
        }, 1000);

        return res.json({ success: true, message: 'Logged out successfully.' });
    } catch (err) {
        console.error('[WhatsApp Bridge] Logout error:', err);
        return res.json({ success: true, message: 'Auth session reset.' });
    }
});

// Health check
app.get('/health', (req, res) => {
    res.json({ status: 'ok', time: new Date().toISOString() });
});

// Start Express and initiate Baileys
app.listen(PORT, '127.0.0.1', () => {
    console.log(`[WhatsApp Bridge] Microservice running on http://127.0.0.1:${PORT}`);
    connectToWhatsApp();
});
