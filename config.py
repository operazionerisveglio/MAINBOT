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
SUPER_ADMIN_IDS = [
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
    SUPER_ADMIN_IDS,
]

# Chat ID per notifiche admin (opzionale)
STAFF_ADMIN_CHAT_ID = os.getenv('STAFF_ADMIN_CHAT_ID', None)

# =============================================================================
# CONFIGURAZIONE CONSENSO/LIBERATORIA
# =============================================================================
# Versione corrente del documento di consenso
CONSENT_DOCUMENT_VERSION = "1.0"

# Durata validità OTP in minuti
OTP_VALIDITY_MINUTES = 10

# Numero massimo tentativi OTP
OTP_MAX_ATTEMPTS = 5

# Titolare del trattamento dati
DATA_CONTROLLER_NAME = "Francesco Cinquefiori"
DATA_CONTROLLER_EMAIL = "gruppo.operazione.risveglio@gmail.com"

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

    # NUOVO: Messaggio consenso
    'consent_intro': """
📋 *DICHIARAZIONE DI RESPONSABILITÀ E CONSENSO*

Prima di procedere con l'abbonamento, è necessario compilare la dichiarazione di adesione consapevole e il consenso al trattamento dei dati personali.

📝 *Questo documento include:*
• Dichiarazione di adesione volontaria
• Regole di riservatezza e comportamento
• Informativa privacy (GDPR)
• Consenso al trattamento dati

⚠️ *IMPORTANTE:*
La compilazione è obbligatoria per procedere. I tuoi dati saranno trattati secondo il GDPR.

Clicca il pulsante qui sotto per iniziare la compilazione:
""",

    'consent_form_intro': """
📝 *COMPILAZIONE MODULO*

Inserisci i tuoi dati anagrafici come richiesto.
Questi dati saranno utilizzati esclusivamente per la dichiarazione di consenso.

*Passaggio {step}/5*
""",

    'consent_otp_sent': """
🔐 *CODICE DI VERIFICA INVIATO*

Ti ho appena inviato un codice OTP di 6 cifre.

⏰ Il codice è valido per *10 minuti*.
📱 Inserisci il codice per confermare la tua identità e firmare il documento.

⚠️ Hai massimo 5 tentativi.
""",

    'consent_confirmed': """
✅ *CONSENSO CONFERMATO!*

La tua dichiarazione è stata registrata con successo.

📋 *Riepilogo:*
• Nome: {full_name}
• Data conferma: {confirmed_at}
• Codice documento: #{consent_id}

🔐 *Firma elettronica verificata*
Questo documento ha valore probatorio ai sensi della normativa vigente.

Ora puoi procedere con l'abbonamento!
""",

    'consent_document': """
📜 *DICHIARAZIONE PERSONALE DI RESPONSABILITÀ E ADESIONE CONSAPEVOLE*

Io sottoscritto/a *{full_name}*
nato/a a *{birth_place}* il *{birth_date}*
residente in *{residence}*

DICHIARO QUANTO SEGUE:

*1. Adesione volontaria*
Dichiaro di aderire in modo volontario, libero e consapevole al gruppo privato denominato "OPERAZIONE RISVEGLIO", gestito da Francesco Cinquefiori, comprendendo che si tratta di uno spazio riservato di condivisione, ricerca personale e sperimentazione individuale di pratiche di benessere interiore, meditazione, consapevolezza ed esplorazione vibrazionale.

*2. Regole di riservatezza e comportamento*
Mi impegno a rispettare la riservatezza di tutti i contenuti, materiali, tecniche, informazioni, testi, audio o altri strumenti condivisi all'interno del gruppo; a non copiare, registrare, diffondere o divulgare tali contenuti a terzi; a mantenere un comportamento rispettoso, responsabile e coerente con le finalità del gruppo.

*3. Natura delle pratiche*
Dichiaro di essere pienamente consapevole che le pratiche, le informazioni e i contenuti condivisi non hanno finalità mediche, psicologiche o terapeutiche e non sostituiscono in alcun modo diagnosi, cure o trattamenti sanitari o professionali.

*4. Responsabilità personale*
Dichiaro di assumermi la piena ed esclusiva responsabilità personale per l'utilizzo delle pratiche e dei contenuti condivisi.

*5. Manleva*
Sollevo espressamente il fondatore, gli amministratori del gruppo e gli altri partecipanti da qualsiasi responsabilità, diretta o indiretta, derivante dall'uso delle informazioni condivise.

*6. Accettazione*
Dichiaro di aver letto attentamente il presente documento, di averne compreso il contenuto e di accettarlo integralmente senza riserve.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

*INFORMATIVA PRIVACY (GDPR)*

Il Titolare del trattamento è: Francesco Cinquefiori
Email: gruppo.operazione.risveglio@gmail.com

I dati raccolti (nome, data/luogo nascita, residenza, username Telegram) sono trattati per gestione adesione, tutela legale e organizzazione attività.

L'interessato può accedere, modificare o richiedere cancellazione dei propri dati contattando il Titolare.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

*CONFERMA CONSENSO*

Inserendo il codice OTP, dichiaro di aver letto l'informativa privacy e presto il mio consenso esplicito al trattamento dei dati personali per le finalità indicate.

📅 Data: {date}
🔐 Verifica tramite: Codice OTP Telegram
""",
}

# =============================================================================
# CONFIGURAZIONI VARIE
# =============================================================================
# Giorni di preavviso prima della scadenza abbonamento
RENEWAL_REMINDER_DAYS = 3

# Fuso orario per i report
TIMEZONE = 'Europe/Rome'
