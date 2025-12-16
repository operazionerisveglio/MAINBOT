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
STRIPE_PRICE_ID = os.getenv('STRIPE_PRICE_ID', 'price_1SbnGPAjq2QmGIcgPhSM2xy1')

# Prezzo abbonamento (solo per riferimento, il prezzo reale è su Stripe)
SUBSCRIPTION_PRICE_EUR = 20

# =============================================================================
# LINK DEI CANALI (solo 2: Hub e Comunicazioni)
# =============================================================================
# I CANALI sono per comunicazioni one-to-many (solo admin postano)

CHANNEL_LINKS = {
    'hub': 'https://t.me/OperazioneRisveglioHub',            # Pubblico
    'comunicazioni': 'https://t.me/+eDycLemLgJViYzY0',   # Privato - Annunci
}

# =============================================================================
# LINK DEI GRUPPI (tutti gli altri)
# =============================================================================
# I GRUPPI permettono interazione (con Topics)
# IMPORTANTE: Attiva "Approva nuovi membri" in questi gruppi!

GROUP_LINKS = {
    'biblioteca': 'https://t.me/+kkYRJIFhTfFjZmM8',      # Download risorse
    'salotto': 'https://t.me/+GmeCma6o4-JhMGM0',         # Condivisione esperienze
    'brainstorming': 'https://t.me/+89hE5BvuiRw2Yzg8',   # Feedback e idee
}

# =============================================================================
# LINK GRUPPI STAFF (solo invito manuale, NON gestiti dal bot)
# =============================================================================
STAFF_LINKS = {
    'staff_tecnico': 'https://t.me/+vFLBhBLx4T81ZGM0',
    'staff_admin': 'https://t.me/+GQzZscckn19kNjU0',
}

# Tutti i link insieme (per comodità nel bot)
LINKS = {**CHANNEL_LINKS, **GROUP_LINKS}

# =============================================================================
# ID DEI CANALI E GRUPPI
# =============================================================================
# Per ottenere l'ID: aggiungi @userinfobot al canale/gruppo e scrivi /start

CHANNEL_IDS = {
    'comunicazioni':  -3397059711,  # Sostituisci con ID reale
}

GROUP_IDS = {
    'biblioteca': -3435704855,     # Sostituisci con ID reale
    'salotto': -3449899109,
    'brainstorming': -3377524539,
    'staff_tecnico': -3348195812,
    'staff_admin': -3379647913,
}

# =============================================================================
# ID AMMINISTRATORI
# =============================================================================
# Lista degli user_id degli amministratori (per comandi speciali)
# Per ottenere il tuo ID: scrivi a @userinfobot

ADMIN_IDS = [
     1164635816,  # Sostituisci con il tuo user_id
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
