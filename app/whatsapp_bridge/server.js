const express = require('express');
const { default: makeWASocket, useMultiFileAuthState, DisconnectReason } = require('@whiskeysockets/baileys');
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
let connectionStatus = 'initializing';
let currentQrBase64 = null;
let connectedPhone = null;

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
                console.error('Failed to forward message to Python backend:', err.message);
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
    try {
        const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);

        sock = makeWASocket({
            auth: state,
            logger: pino({ level: 'silent' }),
            printQRInTerminal: false,
            browser: ['LKCS Exam Studio', 'Desktop', '2.0.0'],
            syncFullHistory: false
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
                const statusCode = (lastDisconnect?.error instanceof Boom)?.output?.statusCode;
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

                // Reconnect after brief pause unless logged out
                setTimeout(() => {
                    connectToWhatsApp();
                }, isLoggedOut ? 1000 : 3000);

            } else if (connection === 'open') {
                connectionStatus = 'connected';
                currentQrBase64 = null;
                connectedPhone = sock.user?.id ? sock.user.id.split(':')[0] : 'connected';
                console.log(`[WhatsApp Bridge] Successfully connected to WhatsApp! Account: ${connectedPhone}`);

                notifyPythonBackend('/api/whatsapp/internal/status', {
                    status: 'connected',
                    connected: true,
                    phone: connectedPhone
                });
            }
        });

        sock.ev.on('creds.update', saveCreds);

        // Handle incoming messages from teachers
        sock.ev.on('messages.upsert', async ({ messages, type }) => {
            if (type !== 'notify') return;

            for (const msg of messages) {
                // Ignore messages sent by bot itself or status broadcasts
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
                        await sock.sendMessage(remoteJid, { text: replyText });
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
        return res.status(400).json({ success: false, error: 'WhatsApp is not connected yet. Please scan the barcode first.' });
    }

    if (!phone || !message) {
        return res.status(400).json({ success: false, error: 'Recipient phone and message are required.' });
    }

    try {
        const cleanPhone = phone.replace(/\D/g, '');
        const jid = `${cleanPhone}@s.whatsapp.net`;
        await sock.sendMessage(jid, { text: message });
        return res.json({ success: true, message: `Delivered message to ${cleanPhone}` });
    } catch (err) {
        console.error('[WhatsApp Bridge] Error sending message:', err);
        return res.status(500).json({ success: false, error: err.message });
    }
});

// Logout / Disconnect
app.post('/logout', async (req, res) => {
    try {
        if (sock) {
            await sock.logout();
        }
        try {
            fs.rmSync(AUTH_DIR, { recursive: true, force: true });
        } catch (e) {}
        connectionStatus = 'disconnected';
        currentQrBase64 = null;
        connectedPhone = null;
        setTimeout(connectToWhatsApp, 1000);
        return res.json({ success: true, message: 'Logged out successfully.' });
    } catch (err) {
        return res.status(500).json({ success: false, error: err.message });
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
