"""
CONFIGURAZIONE BOT PRINCIPALE - OPERAZIONE RISVEGLIO
=====================================================
Questo file contiene tutte le configurazioni necessarie per il bot.
IMPORTANTE: Non condividere mai questo file con le chiavi reali!
"""

import os
from dotenv import load_dotenv

# Carica le variabili d'ambiente dal file .env
load_dotenv()

# =============================================================================
# TOKEN E CHIAVI API (da variabili d'ambiente per sicurezza)
# =============================================================================
BOT_TOKEN = os.getenv('BOT_TOKEN')  # Token del bot da @BotFather
STRIPE_SECRET_KEY = os.getenv('STRIPE_SECRET_KEY')  # Chiave segreta Stripe
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')  # Per verificare webhook
DATABASE_URL = os.getenv('DATABASE_URL')  # URL database PostgreSQL

# =============================================================================
# CONFIGURAZIONE STRIPE
# =============================================================================
# ID del prodotto abbonamento creato su Stripe (sostituisci con il tuo)
STRIPE_PRICE_ID = os.getenv('STRIPE_PRICE_ID', 'price_XXXXXXXXXXXXXXXXXX')

# Prezzo abbonamento (solo per riferimento, il prezzo reale è su Stripe)
SUBSCRIPTION_PRICE_EUR = 20

# =============================================================================
# LINK DEI GRUPPI E CANALI
# =============================================================================
# IMPORTANTE: Sostituisci questi link con quelli reali dei tuoi gruppi/canali
# Per ottenere i link: apri il gruppo/canale > Impostazioni > Link di invito

LINKS = {
    # Canale pubblico (link pubblico tipo t.me/NomeCanale)
    'hub': 'https://t.me/OperazioneRisveglioHub',
    
    # Canali/Gruppi privati (link tipo t.me/+CODICE)
    'comunicazioni': 'https://t.me/+INSERISCI_CODICE_QUI',
    'biblioteca': 'https://t.me/+INSERISCI_CODICE_QUI',
    'salotto': 'https://t.me/+INSERISCI_CODICE_QUI',
    'brainstorming': 'https://t.me/+INSERISCI_CODICE_QUI',
    
    # Gruppi staff (solo per admin)
    'staff_tecnico': 'https://t.me/+INSERISCI_CODICE_QUI',
    'staff_admin': 'https://t.me/+INSERISCI_CODICE_QUI',
}

# =============================================================================
# ID DEI GRUPPI (necessari per alcune operazioni del bot)
# =============================================================================
# Per ottenere l'ID: aggiungi il bot @userinfobot al gruppo e scrivi /start
# Oppure usa il bot @getidsbot

GROUP_IDS = {
    'comunicazioni': -1001234567890,  # Sostituisci con ID reale
    'biblioteca': -1001234567891,
    'salotto': -1001234567892,
    'brainstorming': -1001234567893,
    'staff_tecnico': -1001234567894,
    'staff_admin': -1001234567895,
}

# =============================================================================
# ID AMMINISTRATORI
# =============================================================================
# Lista degli user_id degli amministratori (per comandi speciali)
# Per ottenere il tuo ID: scrivi a @userinfobot

ADMIN_IDS = [
    123456789,  # Sostituisci con il tuo user_id
    # Aggiungi altri admin qui
]

# =============================================================================
# CHAT ID PER NOTIFICHE STAFF (NUOVO)
# =============================================================================
# ID del gruppo staff admin dove inviare notifiche di nuove richieste
# Imposta a None se non vuoi usare un gruppo (notifiche solo agli admin singoli)
# Per ottenere l'ID: aggiungi @userinfobot al gruppo e scrivi /start

STAFF_ADMIN_CHAT_ID = os.getenv('STAFF_ADMIN_CHAT_ID', None)
if STAFF_ADMIN_CHAT_ID:
    STAFF_ADMIN_CHAT_ID = int(STAFF_ADMIN_CHAT_ID)

# =============================================================================
# MESSAGGI DEL BOT
# =============================================================================
MESSAGES = {
    'welcome_new': """
👋 *Benvenuto in Operazione Risveglio!*

Sono il bot ufficiale della community. 

🔒 *ACCESSO RISERVATO*
Per accedere ai contenuti esclusivi è necessario:
1️⃣ Richiedere l'accesso (verrà valutato dal team)
2️⃣ Sottoscrivere un abbonamento mensile

💰 *ABBONAMENTO*
Solo 20€/mese per accesso illimitato a:
• 📚 Biblioteca Digitale completa
• 💬 Salotto Quantico (condivisione esperienze)
• 💡 Brainstorming & Feedback
• 📢 Comunicazioni ufficiali
• 🎯 Supporto prioritario

👇 Clicca "Richiedi Accesso" per iniziare!
""",

    'welcome_subscriber': """
🎉 *Bentornato, {name}!*

Il tuo abbonamento è *attivo* fino al {end_date}.

Usa i pulsanti qui sotto per accedere ai contenuti premium:
""",

    'subscription_expired': """
⚠️ *Abbonamento Scaduto*

Ciao {name}, il tuo abbonamento è scaduto il {end_date}.

Per continuare ad accedere ai contenuti premium, rinnova ora!

💡 Essendo già membro approvato, puoi rinnovare subito senza nuova richiesta.
""",

    'payment_success': """
✅ *Pagamento Completato!*

Grazie {name}! Il tuo abbonamento è ora attivo.

📅 Scadenza: {end_date}

Ora hai accesso a tutti i contenuti premium. Usa /start per vedere il menu completo!
""",

    'payment_cancelled': """
❌ *Pagamento Annullato*

Il pagamento è stato annullato. Se hai avuto problemi, contatta il supporto con /supporto.
""",

    'help': """
📖 *GUIDA AI COMANDI*

/start - Menu principale
/abbonati - Abbonati alla community
/stato - Verifica il tuo abbonamento
/supporto - Richiedi assistenza
/help - Mostra questa guida

*COMANDI ADMIN:*
/admin - Dashboard amministratore
/pending - Vedi richieste in attesa
/approva @username - Approva un utente
/rifiuta @username - Rifiuta un utente

🏠 *Hub Principale:* @OperazioneRisveglioHub
""",
}

# =============================================================================
# CONFIGURAZIONI VARIE
# =============================================================================
# Giorni di preavviso prima della scadenza abbonamento
RENEWAL_REMINDER_DAYS = 3

# Fuso orario per i report
TIMEZONE = 'Europe/Rome'
