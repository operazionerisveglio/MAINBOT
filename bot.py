"""
BOT PRINCIPALE - OPERAZIONE RISVEGLIO
======================================
Bot Telegram per la gestione della community, abbonamenti e navigazione.
Include sistema di consenso/liberatoria con firma elettronica OTP.

Per avviare il bot: python bot.py
"""

import logging
import asyncio
import threading
from datetime import datetime
from aiohttp import web
import stripe
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, 
    CommandHandler, 
    CallbackQueryHandler, 
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    ChatJoinRequestHandler,
    filters
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import (
    BOT_TOKEN, LINKS, CHANNEL_LINKS, GROUP_LINKS, MESSAGES, 
    RENEWAL_REMINDER_DAYS, STAFF_ADMIN_CHAT_ID,
    GROUP_IDS, CHANNEL_IDS, STRIPE_WEBHOOK_SECRET,
    ADMIN_LINKS, SUPER_ADMIN_IDS, CONSENT_DOCUMENT_VERSION,
    OTP_VALIDITY_MINUTES, DATA_CONTROLLER_NAME, DATA_CONTROLLER_EMAIL
)

SUPPORT_BOT_USERNAME = "@ORSupportoTecnicoBot"
SUPPORT_BOT_LINK = "https://t.me/ORSupportoTecnicoBot"
STAFF_ADMIN_GROUP_ID = -3379647913

from database import (
    init_db, add_user, get_user, is_subscribed, get_subscription_info,
    activate_subscription, get_expiring_subscriptions, get_expired_subscriptions,
    deactivate_subscription, create_ticket, get_open_tickets, close_ticket,
    get_stats, log_activity,
    is_approved, set_pending, approve_user, reject_user, get_pending_users,
    get_user_by_username, can_access_groups, can_subscribe,
    is_admin, is_super_admin, add_admin, remove_admin, get_all_admins, get_admin_ids,
    create_consent_record, verify_otp, get_user_consent, has_valid_consent,
    get_pending_consent, regenerate_otp, get_consent_stats
)
from payments import create_checkout_session, get_customer_portal_url

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Stati ConversationHandler
SUPPORT_CATEGORY, SUPPORT_DESCRIPTION = range(2)
(CONSENT_START, CONSENT_FULL_NAME, CONSENT_BIRTH_DATE, 
 CONSENT_BIRTH_PLACE, CONSENT_RESIDENCE, CONSENT_REVIEW, 
 CONSENT_OTP_VERIFY) = range(10, 17)


def get_user_status(user_id: int) -> str:
    """Restituisce lo stato dell'utente."""
    user = get_user(user_id)
    if not user:
        return 'new'
    
    status = user.get('subscription_status', 'inactive')
    approved = user.get('approved', False)
    consent_completed = user.get('consent_completed', False)
    
    if status == 'pending':
        return 'pending'
    if status == 'rejected':
        return 'rejected'
    
    if approved:
        if not consent_completed:
            pending_consent = get_pending_consent(user_id)
            if pending_consent:
                return 'consent_pending_otp'
            return 'awaiting_consent'
        if is_subscribed(user_id):
            return 'subscribed'
        return 'approved_not_subscribed'
    return 'new'


def get_main_keyboard(user_status: str, user_id: int = None) -> InlineKeyboardMarkup:
    """Genera la tastiera principale in base allo stato utente."""
    
    if user_status == 'subscribed':
        keyboard = [
            [InlineKeyboardButton("💬 Salotto Quantico", url=GROUP_LINKS['salotto'])],
            [InlineKeyboardButton("📚 Biblioteca Digitale", url=GROUP_LINKS['biblioteca'])],
            [InlineKeyboardButton("💡 Brainstorming", url=GROUP_LINKS['brainstorming'])],
            [InlineKeyboardButton("📢 Comunicazioni", url=CHANNEL_LINKS['comunicazioni'])],
            [
                InlineKeyboardButton("📊 Il Mio Stato", callback_data='my_status'),
                InlineKeyboardButton("🎫 Supporto", callback_data='support')
            ],
            [InlineKeyboardButton("⚙️ Gestisci Abbonamento", callback_data='manage_subscription')],
        ]
        if user_id and is_admin(user_id):
            keyboard.append([InlineKeyboardButton("━━━ 🔐 AREA ADMIN ━━━", callback_data='admin_separator')])
            keyboard.append([
                InlineKeyboardButton("🏛️ Amministrazione", url=ADMIN_LINKS['staff_admin']),
                InlineKeyboardButton("⚙️ Reparto Tecnico", url=ADMIN_LINKS['staff_tecnico'])
            ])
            keyboard.append([InlineKeyboardButton("📋 Pannello Admin", callback_data='admin_panel')])
    
    elif user_status == 'approved_not_subscribed':
        keyboard = [
            [InlineKeyboardButton("🔓 ABBONATI ORA (20€/mese)", callback_data='subscribe')],
            [InlineKeyboardButton("📋 Vedi il Mio Consenso", callback_data='view_consent')],
            [InlineKeyboardButton("🏠 Vai all'Hub", url=LINKS['hub'])],
            [InlineKeyboardButton("📊 Il Mio Stato", callback_data='my_status')],
        ]
    
    elif user_status == 'awaiting_consent':
        keyboard = [
            [InlineKeyboardButton("📝 COMPILA CONSENSO", callback_data='start_consent')],
            [InlineKeyboardButton("❓ Cos'è il Consenso?", callback_data='consent_info')],
            [InlineKeyboardButton("🏠 Vai all'Hub", url=LINKS['hub'])],
        ]
    
    elif user_status == 'consent_pending_otp':
        keyboard = [
            [InlineKeyboardButton("🔐 INSERISCI CODICE OTP", callback_data='enter_otp')],
            [InlineKeyboardButton("🔄 Richiedi Nuovo Codice", callback_data='resend_otp')],
            [InlineKeyboardButton("🏠 Vai all'Hub", url=LINKS['hub'])],
        ]
    
    elif user_status == 'pending':
        keyboard = [
            [InlineKeyboardButton("⏳ Richiesta in Attesa", callback_data='pending_info')],
            [InlineKeyboardButton("🏠 Vai all'Hub", url=LINKS['hub'])],
        ]
    
    elif user_status == 'rejected':
        keyboard = [
            [InlineKeyboardButton("🏠 Vai all'Hub", url=LINKS['hub'])],
            [InlineKeyboardButton("📧 Contatta Supporto", callback_data='support')],
        ]
    
    else:
        keyboard = [
            [InlineKeyboardButton("🔑 RICHIEDI ACCESSO", callback_data='request_access')],
            [InlineKeyboardButton("🏠 Vai all'Hub", url=LINKS['hub'])],
            [InlineKeyboardButton("❓ Cos'è Operazione Risveglio?", callback_data='info')],
        ]
    
    return InlineKeyboardMarkup(keyboard)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /start - Punto di ingresso principale."""
    user = update.effective_user
    add_user(user.id, user.username, user.first_name, user.last_name)
    log_activity(user.id, 'start', 'Avvio bot')
    
    args = context.args
    if args:
        param = args[0]
        if param.startswith('payment_success_'):
            await update.message.reply_text(
                "✅ *Grazie per l'acquisto!*\n\nHai attivato il tuo abbonamento. "
                "Usa /start per vedere il menu completo.",
                parse_mode='Markdown'
            )
            return
        elif param == 'payment_cancelled':
            await update.message.reply_text(MESSAGES['payment_cancelled'], parse_mode='Markdown')
            return
    
    user_status = get_user_status(user.id)
    
    if user_status == 'subscribed':
        sub_info = get_subscription_info(user.id)
        end_date = sub_info['end_date'].strftime('%d/%m/%Y') if sub_info['end_date'] else 'N/A'
        text = MESSAGES['welcome_subscriber'].format(name=user.first_name, end_date=end_date)
    elif user_status == 'approved_not_subscribed':
        text = f"👋 *Bentornato {user.first_name}!*\n\n✅ Hai completato la dichiarazione di consenso.\n\nOra puoi procedere con l'abbonamento!"
    elif user_status == 'awaiting_consent':
        text = f"👋 *Ciao {user.first_name}!*\n\n🎉 *La tua richiesta è stata APPROVATA!*\n\nPrima di procedere, compila la *Dichiarazione di Responsabilità e Consenso*.\n\n📝 Clicca il pulsante qui sotto."
    elif user_status == 'consent_pending_otp':
        text = f"👋 *Ciao {user.first_name}!*\n\n🔐 *Verifica in sospeso*\n\nHai compilato il modulo ma devi confermare con il codice OTP."
    elif user_status == 'pending':
        text = f"👋 *Ciao {user.first_name}!*\n\n⏳ La tua richiesta è *in attesa di approvazione*.\n\nRiceverai una notifica!"
    elif user_status == 'rejected':
        text = f"👋 *Ciao {user.first_name}!*\n\n❌ La tua richiesta non è stata approvata.\n\nContatta il supporto se ritieni sia un errore."
    else:
        text = MESSAGES['welcome_new']
    
    keyboard = get_main_keyboard(user_status, user.id)
    await update.message.reply_text(text, parse_mode='Markdown', reply_markup=keyboard)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(MESSAGES['help'], parse_mode='Markdown')


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    sub_info = get_subscription_info(user.id)
    
    if sub_info['status'] == 'not_found':
        text = "❌ Non sei ancora registrato. Usa /start per iniziare."
    elif sub_info['status'] == 'active':
        end_date = sub_info['end_date'].strftime('%d/%m/%Y')
        consent_status = "✅ Completato" if sub_info.get('consent_completed') else "❌ Non completato"
        text = f"✅ *Abbonamento Attivo*\n\n📅 Scadenza: {end_date}\n💳 Pagamenti: {sub_info['total_payments']}\n📋 Consenso: {consent_status}"
    else:
        approved_text = "✅ Approvato" if sub_info.get('approved') else "⏳ Non approvato"
        consent_text = "✅ Completato" if sub_info.get('consent_completed') else "❌ Non completato"
        text = f"❌ *Abbonamento Non Attivo*\n\n📋 Approvazione: {approved_text}\n📝 Consenso: {consent_text}\n\nUsa /start per le opzioni."
    
    await update.message.reply_text(text, parse_mode='Markdown')


async def subscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    if not can_subscribe(user.id):
        user_status = get_user_status(user.id)
        messages = {
            'pending': "⏳ La tua richiesta è in attesa di approvazione.",
            'rejected': "❌ La tua richiesta non è stata approvata.",
            'awaiting_consent': "📝 Prima di abbonarti, compila il consenso. Usa /start.",
            'consent_pending_otp': "🔐 Devi confermare il consenso con il codice OTP."
        }
        await update.message.reply_text(messages.get(user_status, "🔑 Prima richiedi l'accesso. Usa /start."))
        return
    
    if is_subscribed(user.id):
        await update.message.reply_text("✅ Hai già un abbonamento attivo! Usa /stato per dettagli.")
        return
    
    try:
        checkout_url = create_checkout_session(user.id)
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("💳 Vai al Pagamento", url=checkout_url)],
            [InlineKeyboardButton("❌ Annulla", callback_data='cancel')]
        ])
        await update.message.reply_text(
            "💰 *Abbonamento Operazione Risveglio*\n\nPrezzo: *20€/mese*\n\n"
            "Cosa include:\n• 📚 Biblioteca Digitale\n• 💬 Salotto Quantico\n"
            "• 💡 Brainstorming\n• 📢 Comunicazioni\n• 🎯 Supporto prioritario\n\n"
            "Clicca per procedere:",
            parse_mode='Markdown', reply_markup=keyboard
        )
    except Exception as e:
        logger.error(f"Errore checkout: {e}")
        await update.message.reply_text("❌ Errore. Riprova più tardi.")


async def handle_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce le richieste di accesso ai gruppi privati."""
    join_request = update.chat_join_request
    user = join_request.from_user
    chat = join_request.chat
    
    logger.info(f"Richiesta accesso {chat.title} da {user.id}")
    
    if can_access_groups(user.id):
        await join_request.approve()
        logger.info(f"Utente {user.id} approvato per {chat.title}")
        try:
            await context.bot.send_message(user.id, f"✅ *Accesso Approvato!*\n\nBenvenuto in *{chat.title}*!", parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Errore notifica: {e}")
    else:
        await join_request.decline()
        user_status = get_user_status(user.id)
        reasons = {
            'new': "Non hai ancora richiesto l'accesso. Scrivi /start al bot.",
            'pending': "La tua richiesta è ancora in attesa di approvazione.",
            'rejected': "La tua richiesta non è stata approvata.",
            'awaiting_consent': "Devi completare il modulo di consenso. Scrivi /start.",
            'consent_pending_otp': "Devi confermare il consenso con OTP. Scrivi /start.",
            'approved_not_subscribed': "Devi completare l'abbonamento. Scrivi /start."
        }
        try:
            await context.bot.send_message(user.id, f"❌ *Accesso Negato*\n\n{reasons.get(user_status, 'Scrivi /start per info.')}", parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Errore notifica rifiuto: {e}")


# =============================================================================
# GESTIONE CONSENSO/LIBERATORIA - CONVERSATION HANDLER
# =============================================================================

async def consent_start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback per avviare il form di consenso."""
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    
    if not is_approved(user.id):
        await query.edit_message_text("❌ Devi prima essere approvato.")
        return ConversationHandler.END
    
    if has_valid_consent(user.id):
        await query.edit_message_text("✅ Hai già completato il consenso! Usa /start per procedere.")
        return ConversationHandler.END
    
    intro_text = MESSAGES['consent_intro']
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 INIZIA COMPILAZIONE", callback_data='consent_begin')],
        [InlineKeyboardButton("📖 Leggi Documento", callback_data='consent_full_doc')],
        [InlineKeyboardButton("❌ Annulla", callback_data='back_to_menu')]
    ])
    await query.edit_message_text(intro_text, parse_mode='Markdown', reply_markup=keyboard)
    return CONSENT_START


async def consent_begin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inizia raccolta dati - Nome completo."""
    query = update.callback_query
    await query.answer()
    context.user_data['consent'] = {}
    
    text = "📝 *COMPILAZIONE MODULO*\n\n*Passaggio 1/5 - Nome e Cognome*\n\nInserisci il tuo *nome e cognome completo*.\n\n_Esempio: Mario Rossi_"
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Annulla", callback_data='cancel_consent')]])
    await query.edit_message_text(text, parse_mode='Markdown', reply_markup=keyboard)
    return CONSENT_FULL_NAME


async def consent_receive_full_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Riceve nome e chiede data nascita."""
    full_name = update.message.text.strip()
    
    if len(full_name) < 3 or ' ' not in full_name:
        await update.message.reply_text("⚠️ Inserisci nome e cognome completi.\n_Esempio: Mario Rossi_", parse_mode='Markdown')
        return CONSENT_FULL_NAME
    
    context.user_data['consent']['full_name'] = full_name
    text = "📝 *COMPILAZIONE MODULO*\n\n*Passaggio 2/5 - Data di Nascita*\n\nInserisci nel formato GG/MM/AAAA.\n\n_Esempio: 15/03/1990_"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Indietro", callback_data='consent_back_name')],
        [InlineKeyboardButton("❌ Annulla", callback_data='cancel_consent')]
    ])
    await update.message.reply_text(text, parse_mode='Markdown', reply_markup=keyboard)
    return CONSENT_BIRTH_DATE


async def consent_receive_birth_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Riceve data nascita e chiede luogo."""
    birth_date_str = update.message.text.strip()
    
    try:
        for fmt in ['%d/%m/%Y', '%d-%m-%Y', '%d.%m.%Y']:
            try:
                birth_date = datetime.strptime(birth_date_str, fmt)
                break
            except ValueError:
                continue
        else:
            raise ValueError("Formato non valido")
        
        age = (datetime.now() - birth_date).days // 365
        if age < 18 or age > 120:
            await update.message.reply_text("⚠️ Data non valida. Devi avere almeno 18 anni.")
            return CONSENT_BIRTH_DATE
    except ValueError:
        await update.message.reply_text("⚠️ Formato non valido. Usa GG/MM/AAAA.\n_Esempio: 15/03/1990_", parse_mode='Markdown')
        return CONSENT_BIRTH_DATE
    
    context.user_data['consent']['birth_date'] = birth_date.strftime('%Y-%m-%d')
    context.user_data['consent']['birth_date_display'] = birth_date.strftime('%d/%m/%Y')
    
    text = "📝 *COMPILAZIONE MODULO*\n\n*Passaggio 3/5 - Luogo di Nascita*\n\nInserisci città e provincia.\n\n_Esempio: Roma (RM)_"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Indietro", callback_data='consent_back_date')],
        [InlineKeyboardButton("❌ Annulla", callback_data='cancel_consent')]
    ])
    await update.message.reply_text(text, parse_mode='Markdown', reply_markup=keyboard)
    return CONSENT_BIRTH_PLACE


async def consent_receive_birth_place(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Riceve luogo nascita e chiede residenza."""
    birth_place = update.message.text.strip()
    
    if len(birth_place) < 2:
        await update.message.reply_text("⚠️ Inserisci un luogo valido.\n_Esempio: Roma (RM)_", parse_mode='Markdown')
        return CONSENT_BIRTH_PLACE
    
    context.user_data['consent']['birth_place'] = birth_place
    text = "📝 *COMPILAZIONE MODULO*\n\n*Passaggio 4/5 - Residenza*\n\nInserisci indirizzo completo.\n\n_Esempio: Via Roma 123, 00100 Roma (RM)_"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Indietro", callback_data='consent_back_place')],
        [InlineKeyboardButton("❌ Annulla", callback_data='cancel_consent')]
    ])
    await update.message.reply_text(text, parse_mode='Markdown', reply_markup=keyboard)
    return CONSENT_RESIDENCE


async def consent_receive_residence(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Riceve residenza e mostra riepilogo."""
    residence = update.message.text.strip()
    
    if len(residence) < 5:
        await update.message.reply_text("⚠️ Inserisci indirizzo completo.\n_Esempio: Via Roma 123, 00100 Roma (RM)_", parse_mode='Markdown')
        return CONSENT_RESIDENCE
    
    context.user_data['consent']['residence'] = residence
    consent_data = context.user_data['consent']
    
    document_text = MESSAGES['consent_document'].format(
        full_name=consent_data['full_name'],
        birth_place=consent_data['birth_place'],
        birth_date=consent_data['birth_date_display'],
        residence=consent_data['residence'],
        date=datetime.now().strftime('%d/%m/%Y %H:%M')
    )
    await update.message.reply_text(document_text, parse_mode='Markdown')
    
    confirm_text = (
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "📋 *PASSAGGIO 5/5 - CONFERMA*\n\n"
        f"• Nome: {consent_data['full_name']}\n"
        f"• Nato/a a: {consent_data['birth_place']}\n"
        f"• Data nascita: {consent_data['birth_date_display']}\n"
        f"• Residenza: {consent_data['residence']}\n\n"
        "⚠️ *Confermando, dichiari di aver letto e accettato il documento.*\n\n"
        "Clicca *CONFERMA* per ricevere il codice OTP."
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ CONFERMA E RICEVI OTP", callback_data='consent_confirm')],
        [InlineKeyboardButton("✏️ Modifica Dati", callback_data='consent_edit')],
        [InlineKeyboardButton("❌ Annulla", callback_data='cancel_consent')]
    ])
    await update.message.reply_text(confirm_text, parse_mode='Markdown', reply_markup=keyboard)
    return CONSENT_REVIEW


async def consent_confirm_send_otp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Conferma dati e invia OTP."""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    consent_data = context.user_data.get('consent', {})
    
    if not consent_data:
        await query.edit_message_text("❌ Errore: dati non trovati. Ricomincia con /start")
        return ConversationHandler.END
    
    result = create_consent_record(
        user_id=user.id,
        full_name=consent_data['full_name'],
        birth_date=consent_data['birth_date'],
        birth_place=consent_data['birth_place'],
        residence=consent_data['residence'],
        telegram_username=user.username
    )
    
    if not result['success']:
        await query.edit_message_text(f"❌ Errore: {result.get('error', 'Sconosciuto')}. Riprova.")
        return ConversationHandler.END
    
    otp_code = result['otp_code']
    
    # Invia OTP in un messaggio separato
    await context.bot.send_message(
        chat_id=user.id,
        text=f"🔐 *IL TUO CODICE OTP*\n\n`{otp_code}`\n\n⏰ Valido per 10 minuti.\n\n_Inserisci questo codice per confermare._",
        parse_mode='Markdown'
    )
    
    await query.edit_message_text(
        "✅ *Codice OTP inviato!*\n\n"
        "Ti ho inviato un codice di 6 cifre.\n"
        "⏰ Hai 10 minuti e 5 tentativi.\n\n"
        "📝 Scrivi il codice qui sotto:",
        parse_mode='Markdown'
    )
    
    log_activity(user.id, 'consent_otp_sent', f'OTP inviato per consenso')
    return CONSENT_OTP_VERIFY


async def consent_verify_otp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Verifica il codice OTP inserito."""
    user = update.effective_user
    otp_input = update.message.text.strip()
    
    if not otp_input.isdigit() or len(otp_input) != 6:
        await update.message.reply_text("⚠️ Il codice deve essere di 6 cifre. Riprova:")
        return CONSENT_OTP_VERIFY
    
    result = verify_otp(user.id, otp_input)
    
    if not result['success']:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Richiedi Nuovo Codice", callback_data='resend_otp_conv')],
            [InlineKeyboardButton("❌ Annulla", callback_data='cancel_consent')]
        ])
        await update.message.reply_text(f"❌ {result['error']}", reply_markup=keyboard)
        return CONSENT_OTP_VERIFY
    
    # Consenso confermato!
    confirmed_text = MESSAGES['consent_confirmed'].format(
        full_name=result['full_name'],
        confirmed_at=result['confirmed_at'].strftime('%d/%m/%Y %H:%M'),
        consent_id=result['consent_id']
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔓 ABBONATI ORA", callback_data='subscribe')],
        [InlineKeyboardButton("🏠 Menu Principale", callback_data='back_to_menu')]
    ])
    
    await update.message.reply_text(confirmed_text, parse_mode='Markdown', reply_markup=keyboard)
    
    log_activity(user.id, 'consent_confirmed', f'Consenso #{result["consent_id"]} confermato')
    context.user_data.clear()
    return ConversationHandler.END


async def consent_resend_otp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Rigenera OTP per consenso in corso."""
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    
    result = regenerate_otp(user.id)
    
    if not result['success']:
        await query.edit_message_text(f"❌ {result.get('error', 'Errore sconosciuto')}")
        return CONSENT_OTP_VERIFY if query.data == 'resend_otp_conv' else ConversationHandler.END
    
    await context.bot.send_message(
        chat_id=user.id,
        text=f"🔐 *NUOVO CODICE OTP*\n\n`{result['otp_code']}`\n\n⏰ Valido per 10 minuti.",
        parse_mode='Markdown'
    )
    
    await query.edit_message_text("✅ Nuovo codice inviato! Inseriscilo qui sotto:", parse_mode='Markdown')
    return CONSENT_OTP_VERIFY


async def cancel_consent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Annulla il processo di consenso."""
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text("❌ Compilazione annullata. Usa /start quando vuoi riprendere.")
    else:
        await update.message.reply_text("❌ Compilazione annullata. Usa /start quando vuoi riprendere.")
    context.user_data.clear()
    return ConversationHandler.END


async def consent_back_handlers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce i pulsanti indietro nel form."""
    query = update.callback_query
    await query.answer()
    
    if query.data == 'consent_back_name':
        context.user_data['consent'] = {}
        text = "📝 *Passaggio 1/5 - Nome e Cognome*\n\nInserisci il tuo *nome e cognome completo*.\n\n_Esempio: Mario Rossi_"
        await query.edit_message_text(text, parse_mode='Markdown')
        return CONSENT_FULL_NAME
    
    elif query.data == 'consent_back_date':
        text = "📝 *Passaggio 2/5 - Data di Nascita*\n\nInserisci nel formato GG/MM/AAAA.\n\n_Esempio: 15/03/1990_"
        await query.edit_message_text(text, parse_mode='Markdown')
        return CONSENT_BIRTH_DATE
    
    elif query.data == 'consent_back_place':
        text = "📝 *Passaggio 3/5 - Luogo di Nascita*\n\nInserisci città e provincia.\n\n_Esempio: Roma (RM)_"
        await query.edit_message_text(text, parse_mode='Markdown')
        return CONSENT_BIRTH_PLACE
    
    elif query.data == 'consent_edit':
        text = "📝 *Passaggio 1/5 - Nome e Cognome*\n\nInserisci il tuo *nome e cognome completo*.\n\n_Esempio: Mario Rossi_"
        context.user_data['consent'] = {}
        await query.edit_message_text(text, parse_mode='Markdown')
        return CONSENT_FULL_NAME


async def consent_full_doc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra il documento completo senza dati."""
    query = update.callback_query
    await query.answer()
    
    doc_text = """📜 *DICHIARAZIONE PERSONALE DI RESPONSABILITÀ E ADESIONE CONSAPEVOLE*

*1. Adesione volontaria*
Dichiaro di aderire in modo volontario, libero e consapevole al gruppo privato "OPERAZIONE RISVEGLIO", gestito da Francesco Cinquefiori, comprendendo che si tratta di uno spazio riservato di condivisione e ricerca personale.

*2. Regole di riservatezza*
Mi impegno a rispettare la riservatezza di tutti i contenuti condivisi e a non divulgarli a terzi.

*3. Natura delle pratiche*
Le pratiche condivise non hanno finalità mediche o terapeutiche e non sostituiscono cure professionali.

*4. Responsabilità personale*
Mi assumo la piena responsabilità per l'utilizzo delle pratiche e dei contenuti.

*5. Manleva*
Sollevo il fondatore e gli amministratori da qualsiasi responsabilità derivante dall'uso delle informazioni condivise.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

*INFORMATIVA PRIVACY (GDPR)*
Titolare: Francesco Cinquefiori
Email: gruppo.operazione.risveglio@gmail.com

I dati raccolti sono trattati per gestione adesione e tutela legale. L'interessato può richiedere accesso, modifica o cancellazione dei propri dati."""
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 INIZIA COMPILAZIONE", callback_data='consent_begin')],
        [InlineKeyboardButton("⬅️ Indietro", callback_data='start_consent')]
    ])
    
    await query.edit_message_text(doc_text, parse_mode='Markdown', reply_markup=keyboard)
    return CONSENT_START


# =============================================================================
# GESTIONE CALLBACK PRINCIPALI
# =============================================================================

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce i click sui pulsanti inline."""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    data = query.data
    
    if data == 'request_access':
        set_pending(user.id)
        log_activity(user.id, 'access_request', 'Richiesta accesso inviata')
        
        await query.edit_message_text(
            "✅ *Richiesta Inviata!*\n\n"
            "La tua richiesta è stata inviata agli amministratori.\n"
            "⏳ Riceverai una notifica quando sarà elaborata.",
            parse_mode='Markdown'
        )
        
        admin_keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Approva", callback_data=f'admin_approve_{user.id}'),
                InlineKeyboardButton("❌ Rifiuta", callback_data=f'admin_reject_{user.id}')
            ]
        ])
        admin_text = f"🆕 *NUOVA RICHIESTA*\n\n👤 {user.first_name} {user.last_name or ''}\n🔗 @{user.username or 'N/A'}\n🆔 `{user.id}`"
        
        for admin_id in get_admin_ids():
            try:
                await context.bot.send_message(admin_id, admin_text, parse_mode='Markdown', reply_markup=admin_keyboard)
            except Exception as e:
                logger.error(f"Errore notifica admin {admin_id}: {e}")
        
        if STAFF_ADMIN_CHAT_ID:
            try:
                await context.bot.send_message(STAFF_ADMIN_CHAT_ID, admin_text, parse_mode='Markdown', reply_markup=admin_keyboard)
            except Exception as e:
                logger.error(f"Errore notifica gruppo staff: {e}")
    
    elif data == 'pending_info':
        await query.answer("La tua richiesta è in lavorazione!", show_alert=True)
    
    elif data == 'subscribe':
        if not can_subscribe(user.id):
            await query.answer("Devi prima completare il consenso!", show_alert=True)
            return
        
        if is_subscribed(user.id):
            await query.edit_message_text("✅ Hai già un abbonamento attivo!")
            return
        
        try:
            checkout_url = create_checkout_session(user.id)
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("💳 Vai al Pagamento", url=checkout_url)],
                [InlineKeyboardButton("🔙 Indietro", callback_data='back_to_menu')]
            ])
            await query.edit_message_text(
                "💰 *Abbonamento Operazione Risveglio*\n\nPrezzo: *20€/mese*\n\nClicca per procedere:",
                parse_mode='Markdown', reply_markup=keyboard
            )
        except Exception as e:
            logger.error(f"Errore checkout: {e}")
            await query.edit_message_text("❌ Errore. Riprova più tardi.")
    
    elif data == 'info':
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔑 RICHIEDI ACCESSO", callback_data='request_access')],
            [InlineKeyboardButton("🔙 Indietro", callback_data='back_to_menu')]
        ])
        await query.edit_message_text(
            "🌟 *COS'È OPERAZIONE RISVEGLIO?*\n\n"
            "Community dedicata allo sviluppo e condivisione di esperienze "
            "nell'utilizzo di device quantistici per l'equilibrio personale.\n\n"
            "*Cosa troverai:*\n• 📚 Software e risorse esclusive\n• 💬 Community di supporto\n"
            "• 💡 Possibilità di influenzare lo sviluppo\n• 🎧 Audio e frequenze\n• 🧬 QRCode e schemi energetici",
            parse_mode='Markdown', reply_markup=keyboard
        )
    
    elif data == 'consent_info':
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📝 COMPILA ORA", callback_data='start_consent')],
            [InlineKeyboardButton("🔙 Indietro", callback_data='back_to_menu')]
        ])
        await query.edit_message_text(
            "📋 *COS'È IL CONSENSO?*\n\n"
            "È una dichiarazione obbligatoria che include:\n\n"
            "• *Adesione volontaria* alla community\n"
            "• *Regole di riservatezza* sui contenuti\n"
            "• *Informativa privacy* (GDPR)\n"
            "• *Consenso al trattamento dati*\n\n"
            "La compilazione richiede circa 2 minuti.\n"
            "I tuoi dati sono protetti secondo la normativa vigente.",
            parse_mode='Markdown', reply_markup=keyboard
        )
    
    elif data == 'view_consent':
        consent = get_user_consent(user.id)
        if consent:
            text = (
                f"📋 *IL TUO CONSENSO*\n\n"
                f"• Nome: {consent['full_name']}\n"
                f"• Nato/a a: {consent['birth_place']}\n"
                f"• Data nascita: {consent['birth_date'].strftime('%d/%m/%Y')}\n"
                f"• Residenza: {consent['residence']}\n\n"
                f"📅 Confermato il: {consent['confirmed_at'].strftime('%d/%m/%Y %H:%M')}\n"
                f"🆔 Codice: #{consent['consent_id']}\n"
                f"📝 Versione documento: {consent['document_version']}"
            )
        else:
            text = "❌ Nessun consenso trovato."
        
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Indietro", callback_data='back_to_menu')]])
        await query.edit_message_text(text, parse_mode='Markdown', reply_markup=keyboard)
    
    elif data == 'enter_otp':
        await query.edit_message_text(
            "🔐 *INSERISCI CODICE OTP*\n\n"
            "Scrivi il codice di 6 cifre che hai ricevuto:",
            parse_mode='Markdown'
        )
        return CONSENT_OTP_VERIFY
    
    elif data == 'resend_otp':
        result = regenerate_otp(user.id)
        if result['success']:
            await context.bot.send_message(
                user.id,
                f"🔐 *NUOVO CODICE OTP*\n\n`{result['otp_code']}`\n\n⏰ Valido per 10 minuti.",
                parse_mode='Markdown'
            )
            await query.edit_message_text(
                "✅ Nuovo codice inviato!\n\nInseriscilo qui sotto:",
                parse_mode='Markdown'
            )
            return CONSENT_OTP_VERIFY
        else:
            await query.edit_message_text(f"❌ {result.get('error', 'Errore')}. Usa /start per riprovare.")
    
    elif data == 'my_status':
        sub_info = get_subscription_info(user.id)
        if sub_info['status'] == 'active':
            end_date = sub_info['end_date'].strftime('%d/%m/%Y')
            text = f"✅ *Il Tuo Abbonamento*\n\n📅 Stato: Attivo\n📆 Scadenza: {end_date}\n💳 Pagamenti: {sub_info['total_payments']}"
        else:
            approved_text = "✅ Sì" if sub_info.get('approved') else "❌ No"
            consent_text = "✅ Sì" if sub_info.get('consent_completed') else "❌ No"
            text = f"❌ Nessun abbonamento attivo.\n\n📋 Approvato: {approved_text}\n📝 Consenso: {consent_text}"
        
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Indietro", callback_data='back_to_menu')]])
        await query.edit_message_text(text, parse_mode='Markdown', reply_markup=keyboard)
    
    elif data == 'manage_subscription':
        user_data = get_user(user.id)
        if user_data and user_data.get('stripe_customer_id'):
            try:
                portal_url = get_customer_portal_url(user_data['stripe_customer_id'])
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("⚙️ Gestisci su Stripe", url=portal_url)],
                    [InlineKeyboardButton("🔙 Indietro", callback_data='back_to_menu')]
                ])
                await query.edit_message_text(
                    "⚙️ *Gestione Abbonamento*\n\nDal portale Stripe puoi:\n• Aggiornare il metodo di pagamento\n• Vedere le fatture\n• Cancellare l'abbonamento",
                    parse_mode='Markdown', reply_markup=keyboard
                )
            except Exception as e:
                logger.error(f"Errore portale: {e}")
                await query.edit_message_text("❌ Errore. Riprova più tardi.")
        else:
            await query.edit_message_text("❌ Nessun abbonamento da gestire.")
    
    elif data == 'support':
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("━━━ 💳 PAGAMENTI ━━━", callback_data='support_separator')],
            [InlineKeyboardButton("💳 Problemi Pagamento", callback_data='support_payment')],
            [InlineKeyboardButton("⚙️ Problemi Abbonamento", callback_data='support_subscription')],
            [InlineKeyboardButton("━━━ 🔧 TECNICO ━━━", callback_data='support_separator')],
            [InlineKeyboardButton("🔧 Supporto Tecnico", url=SUPPORT_BOT_LINK)],
            [InlineKeyboardButton("🚪 Problemi Accesso", url=SUPPORT_BOT_LINK)],
            [InlineKeyboardButton("🔙 Indietro", callback_data='back_to_menu')]
        ])
        await query.edit_message_text(
            "🎫 *SUPPORTO*\n\n*💳 Pagamenti/Abbonamento:*\nSeleziona un'opzione sotto.\n\n*🔧 Tecnico:*\nUsa il bot dedicato.",
            parse_mode='Markdown', reply_markup=keyboard
        )
    
    elif data == 'support_separator':
        pass
    
    elif data == 'support_payment':
        context.user_data['support_category'] = 'payment'
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Annulla", callback_data='support')]])
        await query.edit_message_text(
            "💳 *PROBLEMI DI PAGAMENTO*\n\nDescrivi il problema:\n• Quale errore vedi?\n• Quale carta usi?\n• Quando è successo?",
            parse_mode='Markdown', reply_markup=keyboard
        )
        return SUPPORT_DESCRIPTION
    
    elif data == 'support_subscription':
        context.user_data['support_category'] = 'subscription'
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Annulla", callback_data='support')]])
        await query.edit_message_text(
            "⚙️ *PROBLEMI DI ABBONAMENTO*\n\nDescrivi il problema:\n• Rinnovo non funziona?\n• Abbonamento non riconosciuto?\n• Vuoi cancellare?",
            parse_mode='Markdown', reply_markup=keyboard
        )
        return SUPPORT_DESCRIPTION
    
    elif data == 'back_to_menu':
        user_status = get_user_status(user.id)
        if user_status == 'subscribed':
            sub_info = get_subscription_info(user.id)
            end_date = sub_info['end_date'].strftime('%d/%m/%Y') if sub_info['end_date'] else 'N/A'
            text = MESSAGES['welcome_subscriber'].format(name=user.first_name, end_date=end_date)
        elif user_status == 'approved_not_subscribed':
            text = f"👋 *Bentornato {user.first_name}!*\n\n✅ Consenso completato. Abbonati per accedere!"
        elif user_status == 'awaiting_consent':
            text = f"👋 *Ciao {user.first_name}!*\n\n🎉 Richiesta APPROVATA! Compila il consenso."
        elif user_status == 'consent_pending_otp':
            text = f"🔐 Verifica in sospeso. Inserisci il codice OTP."
        elif user_status == 'pending':
            text = "⏳ Richiesta in attesa di approvazione..."
        else:
            text = MESSAGES['welcome_new']
        
        keyboard = get_main_keyboard(user_status, user.id)
        await query.edit_message_text(text, parse_mode='Markdown', reply_markup=keyboard)
    
    elif data == 'admin_separator':
        await query.answer("🔐 Sezione Admin", show_alert=False)
    
    elif data == 'admin_panel':
        if not is_admin(user.id):
            await query.answer("Non autorizzato!", show_alert=True)
            return
        
        stats = get_stats()
        consent_stats = get_consent_stats()
        text = (
            "📊 *PANNELLO ADMIN*\n\n"
            f"👥 Utenti: {stats['total_users']}\n"
            f"✅ Abbonati: {stats['active_subscribers']}\n"
            f"🆕 Nuovi (7gg): {stats['new_users_week']}\n"
            f"⏳ In attesa: {stats['pending_users']}\n"
            f"📝 Attesa consenso: {stats['awaiting_consent']}\n"
            f"🎫 Ticket: {stats['open_tickets']}\n"
            f"📋 Consensi: {consent_stats['total_confirmed']}\n"
            f"💰 Entrate mese: €{stats['monthly_revenue']:.2f}\n\n"
            "*Comandi:*\n/pending - Richieste\n/approva @user\n/rifiuta @user"
        )
        
        if is_super_admin(user.id):
            text += "\n\n*Super Admin:*\n/addadmin <id>\n/removeadmin <id>\n/listadmin"
        
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data='back_to_menu')]])
        await query.edit_message_text(text, parse_mode='Markdown', reply_markup=keyboard)
    
    elif data == 'cancel':
        await query.edit_message_text("❌ Operazione annullata.")


# =============================================================================
# GESTIONE SUPPORTO
# =============================================================================

async def support_description_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Riceve descrizione problema supporto."""
    user = update.effective_user
    description = update.message.text
    category = context.user_data.get('support_category', 'payment')
    
    ticket_id = create_ticket(user.id, category, description)
    category_names = {'payment': '💳 Pagamenti', 'subscription': '⚙️ Abbonamento'}
    
    await update.message.reply_text(
        f"✅ *Ticket #{ticket_id} Creato!*\n\n📌 Categoria: {category_names.get(category, category)}\n⏰ Risposta stimata: 2-4 ore",
        parse_mode='Markdown'
    )
    
    log_activity(user.id, 'support_ticket', f'Ticket #{ticket_id}')
    
    try:
        staff_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("👀 Prendi in carico", callback_data=f'ticket_take_{ticket_id}'),
             InlineKeyboardButton("✅ Risolto", callback_data=f'ticket_close_{ticket_id}')],
            [InlineKeyboardButton("📞 Contatta", url=f'tg://user?id={user.id}')]
        ])
        await context.bot.send_message(
            STAFF_ADMIN_GROUP_ID,
            f"🎫 *TICKET #{ticket_id}*\n\n👤 @{user.username or 'N/A'}\n🆔 `{user.id}`\n📂 {category_names.get(category)}\n\n📝 {description[:500]}",
            parse_mode='Markdown', reply_markup=staff_keyboard
        )
    except Exception as e:
        logger.error(f"Errore notifica staff: {e}")
    
    context.user_data.clear()
    return ConversationHandler.END


async def cancel_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Annullato. Usa /start per tornare al menu.")
    return ConversationHandler.END


# =============================================================================
# COMANDI ADMIN
# =============================================================================

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("❌ Non autorizzato.")
        return
    
    stats = get_stats()
    consent_stats = get_consent_stats()
    
    text = (
        "📊 *STATISTICHE ADMIN*\n\n"
        f"👥 Utenti: {stats['total_users']}\n"
        f"✅ Abbonati: {stats['active_subscribers']}\n"
        f"🆕 Nuovi (7gg): {stats['new_users_week']}\n"
        f"⏳ In attesa: {stats['pending_users']}\n"
        f"📝 Attesa consenso: {stats['awaiting_consent']}\n"
        f"📋 Consensi totali: {consent_stats['total_confirmed']}\n"
        f"🎫 Ticket: {stats['open_tickets']}\n"
        f"💰 Entrate mese: €{stats['monthly_revenue']:.2f}"
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⏳ Richieste Pending", callback_data='admin_pending')],
        [InlineKeyboardButton("🎫 Ticket Aperti", callback_data='admin_tickets')]
    ])
    
    await update.message.reply_text(text, parse_mode='Markdown', reply_markup=keyboard)


async def pending_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("❌ Non autorizzato.")
        return
    
    pending = get_pending_users()
    if not pending:
        await update.message.reply_text("✅ Nessuna richiesta in attesa!")
        return
    
    for p in pending[:10]:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Approva", callback_data=f"admin_approve_{p['user_id']}"),
             InlineKeyboardButton("❌ Rifiuta", callback_data=f"admin_reject_{p['user_id']}")]
        ])
        await update.message.reply_text(
            f"👤 *{p['first_name']} {p.get('last_name', '')}*\n🔗 @{p['username'] or 'N/A'}\n🆔 `{p['user_id']}`",
            parse_mode='Markdown', reply_markup=keyboard
        )
    
    if len(pending) > 10:
        await update.message.reply_text(f"... e altri {len(pending) - 10}")


async def approve_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("❌ Non autorizzato.")
        return
    
    if not context.args:
        await update.message.reply_text("❌ Uso: /approva @username")
        return
    
    target_user = get_user_by_username(context.args[0])
    if not target_user:
        await update.message.reply_text(f"❌ Utente {context.args[0]} non trovato.")
        return
    
    approve_user(target_user['user_id'], user.id)
    log_activity(target_user['user_id'], 'approved', f'Approvato da {user.id}')
    
    await update.message.reply_text(f"✅ {context.args[0]} approvato!")
    
    try:
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("📝 COMPILA CONSENSO", callback_data='start_consent')]])
        await context.bot.send_message(
            target_user['user_id'],
            "🎉 *RICHIESTA APPROVATA!*\n\nBenvenuto! Ora compila la dichiarazione di consenso per procedere con l'abbonamento.",
            parse_mode='Markdown', reply_markup=keyboard
        )
    except Exception as e:
        logger.error(f"Errore notifica: {e}")


async def reject_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("❌ Non autorizzato.")
        return
    
    if not context.args:
        await update.message.reply_text("❌ Uso: /rifiuta @username")
        return
    
    target_user = get_user_by_username(context.args[0])
    if not target_user:
        await update.message.reply_text(f"❌ Utente {context.args[0]} non trovato.")
        return
    
    reject_user(target_user['user_id'], user.id)
    log_activity(target_user['user_id'], 'rejected', f'Rifiutato da {user.id}')
    
    await update.message.reply_text(f"❌ {context.args[0]} rifiutato.")
    
    try:
        await context.bot.send_message(target_user['user_id'], "❌ *RICHIESTA NON APPROVATA*\n\nContatta il supporto se ritieni sia un errore.", parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Errore notifica: {e}")


async def addadmin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_super_admin(user.id):
        await update.message.reply_text("❌ Solo Super Admin.")
        return
    
    if not context.args:
        await update.message.reply_text("❌ Uso: /addadmin <user_id>", parse_mode='Markdown')
        return
    
    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ L'user_id deve essere un numero.")
        return
    
    target_user = get_user(target_id)
    if add_admin(target_id, user.id, target_user.get('username') if target_user else None, target_user.get('first_name') if target_user else None):
        await update.message.reply_text(f"✅ Admin aggiunto: `{target_id}`", parse_mode='Markdown')
        log_activity(user.id, 'add_admin', f'Aggiunto {target_id}')
    else:
        await update.message.reply_text("ℹ️ Utente già admin.")


async def removeadmin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_super_admin(user.id):
        await update.message.reply_text("❌ Solo Super Admin.")
        return
    
    if not context.args:
        await update.message.reply_text("❌ Uso: /removeadmin <user_id>")
        return
    
    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ L'user_id deve essere un numero.")
        return
    
    if target_id in SUPER_ADMIN_IDS:
        await update.message.reply_text("❌ Non puoi rimuovere un Super Admin!")
        return
    
    if remove_admin(target_id, user.id):
        await update.message.reply_text(f"✅ Admin rimosso: `{target_id}`", parse_mode='Markdown')
        log_activity(user.id, 'remove_admin', f'Rimosso {target_id}')
    else:
        await update.message.reply_text("❌ Non trovato tra gli admin.")


async def listadmin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_super_admin(user.id):
        await update.message.reply_text("❌ Solo Super Admin.")
        return
    
    admins = get_all_admins()
    if not admins:
        await update.message.reply_text("ℹ️ Nessun admin configurato.")
        return
    
    text = "👥 *LISTA ADMIN*\n\n"
    for admin in admins:
        role_emoji = "👑" if admin['role'] == 'super_admin' else "👤"
        username = admin.get('current_username') or admin.get('username') or '-'
        name = admin.get('current_first_name') or admin.get('first_name') or '-'
        text += f"{role_emoji} *{name}* (@{username})\n   ID: `{admin['user_id']}`\n\n"
    
    await update.message.reply_text(text, parse_mode='Markdown')


async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce callback admin."""
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    
    if not is_admin(user.id):
        return
    
    if query.data == 'admin_pending':
        pending = get_pending_users()
        if not pending:
            await query.edit_message_text("✅ Nessuna richiesta in attesa!")
            return
        
        text = "⏳ *RICHIESTE IN ATTESA*\n\n"
        for p in pending[:10]:
            text += f"👤 {p['first_name']} (@{p['username'] or 'N/A'})\n   ID: `{p['user_id']}`\n\n"
        text += "\nUsa /pending per gestirle."
        await query.edit_message_text(text, parse_mode='Markdown')
    
    elif query.data == 'admin_tickets':
        tickets = get_open_tickets()
        if not tickets:
            await query.edit_message_text("✅ Nessun ticket aperto!")
            return
        
        text = "🎫 *TICKET APERTI*\n\n"
        for t in tickets[:10]:
            text += f"*#{t['ticket_id']}* - {t['category']}\n👤 @{t['username'] or t['first_name']}\n📝 {t['description'][:50]}...\n\n"
        await query.edit_message_text(text, parse_mode='Markdown')
    
    elif query.data.startswith('admin_approve_'):
        target_id = int(query.data.replace('admin_approve_', ''))
        approve_user(target_id, user.id)
        log_activity(target_id, 'approved', f'Approvato da {user.id}')
        
        await query.edit_message_text(f"✅ Utente `{target_id}` *APPROVATO*\n\nDa: @{user.username or user.first_name}", parse_mode='Markdown')
        
        try:
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("📝 COMPILA CONSENSO", callback_data='start_consent')]])
            await context.bot.send_message(
                target_id,
                "🎉 *RICHIESTA APPROVATA!*\n\nBenvenuto! Compila la dichiarazione di consenso per procedere.",
                parse_mode='Markdown', reply_markup=keyboard
            )
        except Exception as e:
            logger.error(f"Errore notifica: {e}")
    
    elif query.data.startswith('admin_reject_'):
        target_id = int(query.data.replace('admin_reject_', ''))
        reject_user(target_id, user.id)
        log_activity(target_id, 'rejected', f'Rifiutato da {user.id}')
        
        await query.edit_message_text(f"❌ Utente `{target_id}` *RIFIUTATO*\n\nDa: @{user.username or user.first_name}", parse_mode='Markdown')
        
        try:
            await context.bot.send_message(target_id, "❌ *RICHIESTA NON APPROVATA*\n\nContatta il supporto se ritieni sia un errore.", parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Errore notifica: {e}")
    
    elif query.data.startswith('ticket_take_'):
        ticket_id = int(query.data.replace('ticket_take_', ''))
        await query.edit_message_text(query.message.text + f"\n\n✅ *Preso in carico da @{user.username or user.first_name}*", parse_mode='Markdown')
        log_activity(user.id, 'ticket_take', f'Ticket #{ticket_id}')
    
    elif query.data.startswith('ticket_close_'):
        ticket_id = int(query.data.replace('ticket_close_', ''))
        try:
            close_ticket(ticket_id)
        except:
            pass
        await query.edit_message_text(query.message.text + f"\n\n✅ *RISOLTO da @{user.username or user.first_name}*", parse_mode='Markdown')
        log_activity(user.id, 'ticket_close', f'Ticket #{ticket_id}')


# =============================================================================
# TASK SCHEDULATI
# =============================================================================

async def check_expiring_subscriptions(context: ContextTypes.DEFAULT_TYPE):
    expiring = get_expiring_subscriptions(days=RENEWAL_REMINDER_DAYS)
    for user in expiring:
        try:
            end_date = user['subscription_end'].strftime('%d/%m/%Y')
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Rinnova", callback_data='subscribe')]])
            await context.bot.send_message(
                user['user_id'],
                f"⚠️ *Promemoria*\n\nIl tuo abbonamento scade il {end_date}. Rinnova!",
                parse_mode='Markdown', reply_markup=keyboard
            )
        except Exception as e:
            logger.error(f"Errore promemoria {user['user_id']}: {e}")


async def check_expired_subscriptions(context: ContextTypes.DEFAULT_TYPE):
    expired = get_expired_subscriptions()
    for user in expired:
        try:
            deactivate_subscription(user['user_id'])
            await context.bot.send_message(
                user['user_id'],
                MESSAGES['subscription_expired'].format(name=user['first_name'], end_date=user['subscription_end'].strftime('%d/%m/%Y')),
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Errore disattivazione {user['user_id']}: {e}")


# =============================================================================
# WEBHOOK SERVER
# =============================================================================

def run_webhook_server_sync():
    async def handle_stripe_webhook(request):
        payload = await request.read()
        sig_header = request.headers.get('Stripe-Signature')
        
        logger.info("=== WEBHOOK STRIPE ===")
        
        try:
            event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
            logger.info(f"Evento: {event['type']}")
        except ValueError as e:
            logger.error(f"Payload non valido: {e}")
            return web.Response(status=400)
        except stripe.error.SignatureVerificationError as e:
            logger.error(f"Firma non valida: {e}")
            return web.Response(status=400)
        
        if event['type'] == 'checkout.session.completed':
            session = event['data']['object']
            user_id = session.get('metadata', {}).get('telegram_user_id')
            if user_id:
                user_id = int(user_id)
                activate_subscription(user_id, session.get('customer'), session.get('subscription'))
                logger.info(f"✅ Abbonamento ATTIVATO per {user_id}")
            else:
                logger.error("telegram_user_id non trovato!")
        
        return web.Response(text='OK', status=200)

    async def health_check(request):
        return web.Response(text='OK', status=200)

    async def start_server():
        app = web.Application()
        app.router.add_post('/webhook/stripe', handle_stripe_webhook)
        app.router.add_get('/health', health_check)
        app.router.add_get('/', health_check)
        
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', 8080)
        await site.start()
        logger.info("🌐 Webhook server su porta 8080")
        
        while True:
            await asyncio.sleep(3600)
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(start_server())


# =============================================================================
# MAIN
# =============================================================================

def main():
    init_db()
    logger.info("Database inizializzato")
    
    webhook_thread = threading.Thread(target=run_webhook_server_sync, daemon=True)
    webhook_thread.start()
    logger.info("Webhook thread avviato")
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Conversation Handler per il Consenso
    consent_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(consent_start_callback, pattern='^start_consent$'),
        ],
        states={
            CONSENT_START: [
                CallbackQueryHandler(consent_begin, pattern='^consent_begin$'),
                CallbackQueryHandler(consent_full_doc, pattern='^consent_full_doc$'),
                CallbackQueryHandler(button_handler, pattern='^back_to_menu$'),
            ],
            CONSENT_FULL_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, consent_receive_full_name),
                CallbackQueryHandler(cancel_consent, pattern='^cancel_consent$'),
            ],
            CONSENT_BIRTH_DATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, consent_receive_birth_date),
                CallbackQueryHandler(consent_back_handlers, pattern='^consent_back_name$'),
                CallbackQueryHandler(cancel_consent, pattern='^cancel_consent$'),
            ],
            CONSENT_BIRTH_PLACE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, consent_receive_birth_place),
                CallbackQueryHandler(consent_back_handlers, pattern='^consent_back_date$'),
                CallbackQueryHandler(cancel_consent, pattern='^cancel_consent$'),
            ],
            CONSENT_RESIDENCE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, consent_receive_residence),
                CallbackQueryHandler(consent_back_handlers, pattern='^consent_back_place$'),
                CallbackQueryHandler(cancel_consent, pattern='^cancel_consent$'),
            ],
            CONSENT_REVIEW: [
                CallbackQueryHandler(consent_confirm_send_otp, pattern='^consent_confirm$'),
                CallbackQueryHandler(consent_back_handlers, pattern='^consent_edit$'),
                CallbackQueryHandler(cancel_consent, pattern='^cancel_consent$'),
            ],
            CONSENT_OTP_VERIFY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, consent_verify_otp),
                CallbackQueryHandler(consent_resend_otp, pattern='^resend_otp_conv$'),
                CallbackQueryHandler(cancel_consent, pattern='^cancel_consent$'),
            ],
        },
        fallbacks=[
            CommandHandler('cancel', cancel_consent),
            CallbackQueryHandler(cancel_consent, pattern='^cancel_consent$'),
        ],
        allow_reentry=True,
    )
    
    # Conversation Handler per Supporto
    support_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_handler, pattern='^support_')],
        states={
            SUPPORT_DESCRIPTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, support_description_handler)
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel_support)],
    )
    
    # Registra handlers
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('help', help_command))
    application.add_handler(CommandHandler('stato', status_command))
    application.add_handler(CommandHandler('abbonati', subscribe_command))
    application.add_handler(CommandHandler('admin', admin_stats))
    application.add_handler(CommandHandler('pending', pending_command))
    application.add_handler(CommandHandler('approva', approve_command))
    application.add_handler(CommandHandler('rifiuta', reject_command))
    application.add_handler(CommandHandler('addadmin', addadmin_command))
    application.add_handler(CommandHandler('removeadmin', removeadmin_command))
    application.add_handler(CommandHandler('listadmin', listadmin_command))
    
    application.add_handler(consent_handler)
    application.add_handler(support_handler)
    
    application.add_handler(CallbackQueryHandler(admin_callback, pattern='^admin_'))
    application.add_handler(CallbackQueryHandler(admin_callback, pattern='^ticket_'))
    application.add_handler(CallbackQueryHandler(button_handler))
    
    application.add_handler(ChatJoinRequestHandler(handle_join_request))
    
    # Scheduler
    scheduler = AsyncIOScheduler(timezone='Europe/Rome')
    scheduler.add_job(check_expiring_subscriptions, 'cron', hour=9, minute=0, args=[application])
    scheduler.add_job(check_expired_subscriptions, 'cron', hour=0, minute=5, args=[application])
    scheduler.start()
    logger.info("Scheduler avviato")
    
    logger.info("Bot avviato!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
