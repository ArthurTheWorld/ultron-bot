const { default: makeWASocket, useMultiFileAuthState, DisconnectReason } = require('@whiskeysockets/baileys');
const qrcode = require('qrcode-terminal');
const axios = require('axios');

async function startWhatsApp() {
    // Carrega o estado de autenticação
    const { state, saveCreds } = await useMultiFileAuthState('auth_info_baileys');

    const sock = makeWASocket({
    auth: state,
    printQRInTerminal: true,
    syncFullHistory: true, // Sincroniza o histórico completo
    markOnlineOnConnect: false, // Não marca como online automaticamente
});

    // Salva as credenciais sempre que mudarem
    sock.ev.on('creds.update', saveCreds);

    // Gerencia a conexão
    sock.ev.on('connection.update', (update) => {
        const { connection, lastDisconnect, qr } = update;

        if (qr) {
            console.log('Escaneie o QR Code abaixo com o WhatsApp:');
            qrcode.generate(qr, { small: true });
        }

        if (connection === 'close') {
            const shouldReconnect = lastDisconnect?.error?.output?.statusCode !== DisconnectReason.loggedOut;
            console.log('Conexão fechada. Tentando reconectar...', shouldReconnect);
            if (shouldReconnect) {
                startWhatsApp();
            }
        } else if (connection === 'open') {
            console.log(' Ultron conectado ao WhatsApp');
        }
    });

    // Escuta novas mensagens
    sock.ev.on('messages.upsert', async ({ messages }) => {
        const msg = messages[0];
        
        // Ignora mensagens de grupos e mensagens enviadas pelo próprio bot
        if (!msg.message || msg.key.remoteJid.includes('@g.us') || msg.key.fromMe) return;

        const texto = msg.message.conversation || msg.message.extendedTextMessage?.text;
        if (!texto) return;

        console.log(` De: ${msg.key.remoteJid}`);
        console.log(` Corpo: "${texto}"`);

        try {
            // Chama o seu servidor Python
            const resposta = await axios.post('http://localhost:8000/mensagem', {
                texto: texto
            }, { timeout: 300000 });

            const respostas = resposta.data.respostas || [];
            const textoFinal = respostas.map(r => r.texto).join('\n\n');
            
            console.log(` Resposta: ${textoFinal}`);
            await sock.sendMessage(msg.key.remoteJid, { text: textoFinal });

        } catch (erro) {
            console.error(' Erro ao processar mensagem:', erro.message);
        }
    });
}

startWhatsApp();