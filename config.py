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
STRIPE_PRICE_ID = os.getenv('STRIPE_PRICE_ID', 'price_1SbnGPAjq2QmGIcgPhSM2xy1')

# Prezzo abbonamento (solo per riferimento, il prezzo reale è su Stripe)
SUBSCRIPTION_PRICE_EUR = 20

# =============================================================================
# SUPER ADMIN (proprietario - non può essere rimosso)
# =============================================================================
SUPER_ADMIN_ID = [
    1164635816,
    5310018118, 
]

# =============================================================================
# LINK DEI GRUPPI E CANALI
# =============================================================================
LINKS = {
    # Hub pubblico
    'hub': 'https://t.me/OperazioneRisveglioHub',
    
    # Canali/Gruppi privati per abbonati
    'comunicazioni': 'https://t.me/+eDycLemLgJViYzY0',
    'biblioteca': 'https://t.me/+kkYRJIFhTfFjZmM8',
    'salotto': 'https://t.me/+GmeCma6o4-JhMGM0',
    'brainstorming': 'https://t.me/+89hE5BvuiRw2Yzg8',
    
    # Gruppi staff (solo per admin)
    'staff_tecnico': 'https://t.me/+vFLBhBLx4T81ZGM0',
    'staff_admin': 'https://t.me/+GQzZscckn19kNjU0',
}

# Separati per comodità nel codice
CHANNEL_LINKS = {
    'hub': LINKS['hub'],
    'comunicazioni': LINKS['comunicazioni'],
}

GROUP_LINKS = {
    'biblioteca': LINKS['biblioteca'],
    'salotto': LINKS['salotto'],
    'brainstorming': LINKS['brainstorming'],
}

ADMIN_LINKS = {
    'staff_tecnico': LINKS['staff_tecnico'],
    'staff_admin': LINKS['staff_admin'],
}

# =============================================================================
# ID DEI GRUPPI (necessari per gestire richieste di accesso)
# =============================================================================
GROUP_IDS = {
    'comunicazioni': -3397059711,
    'biblioteca': -3435704855,
    'salotto': -3449899109,
    'brainstorming': -3377524539,
    'staff_tecnico': -3348195812,
    'staff_admin': -3379647913,
}

CHANNEL_IDS = {
    'comunicazioni': -3397059711,
}

# =============================================================================
# ID AMMINISTRATORI (legacy - ora gestito da database)
# =============================================================================
# Questa lista viene usata come fallback se il database non è disponibile
ADMIN_IDS = [
    SUPER_ADMIN_ID,
]

# Chat ID per notifiche admin (opzionale)
STAFF_ADMIN_CHAT_ID = os.getenv('STAFF_ADMIN_CHAT_ID', None)

# =============================================================================
# MESSAGGI DEL BOT
# =============================================================================
MESSAGES = {
    'welcome_new': """
👋 *Benvenuto in Operazione Risveglio!*

Sono il bot ufficiale della community. Ecco cosa puoi fare:

🔒 *CONTENUTI PREMIUM*
Per accedere a tutti i contenuti esclusivi (Biblioteca, Salotto Quantico, Brainstorming) è necessario un abbonamento.

💰 *ABBONAMENTO*
Solo 20€/mese per accesso illimitato a:
• 📚 Biblioteca Digitale completa
• 💬 Salotto Quantico (condivisione esperienze)
• 💡 Brainstorming & Feedback
• 📢 Comunicazioni ufficiali
• 🎯 Supporto prioritario

Usa i pulsanti qui sotto per navigare!
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
