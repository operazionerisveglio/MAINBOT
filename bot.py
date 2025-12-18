"""
BOT PRINCIPALE - OPERAZIONE RISVEGLIO
======================================
Bot Telegram per la gestione della community, abbonamenti e navigazione.

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
    ADMIN_LINKS, SUPER_ADMIN_ID
)
from database import (
    init_db, add_user, get_user, is_subscribed, get_subscription_info,
    activate_subscription, get_expiring_subscriptions, get_expired_subscriptions,
    deactivate_subscription, create_ticket, get_open_tickets, close_ticket,
    get_stats, log_activity,
    # Funzioni approvazione
    is_approved, set_pending, approve_user, reject_user, get_pending_users,
    get_user_by_username, can_access_groups,
    # Funzioni admin dinamici
    is_admin, is_super_admin, add_admin, remove_admin, get_all_admins, get_admin_ids
)
from payments import create_checkout_session, get_customer_portal_url

# Configurazione logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Stati per ConversationHandler (supporto)
SUPPORT_CATEGORY, SUPPORT_DESCRIPTION = range(2)


# =============================================================================
# FUNZIONI HELPER
# =============================================================================

# NOTA: is_admin ora viene importata dal database (gestione dinamica)


def get_user_status(user_id: int) -> str:
    """
    Restituisce lo stato dell'utente:
    - 'new': mai visto, deve fare richiesta
    - 'pending': richiesta inviata, in attesa approvazione
    - 'rejected': richiesta rifiutata
    - 'approved_not_subscribed': approvato ma non abbonato (o scaduto)
    - 'subscribed': approvato e abbonato attivo
    """
    user = get_user(user_id)
    
    if not user:
        return 'new'
    
    status = user.get('subscription_status', 'inactive')
    approved = user.get('approved', False)
    
    if status == 'pending':
        return 'pending'
    
    if status == 'rejected':
        return 'rejected'
    
    if approved:
        if is_subscribed(user_id):
            return 'subscribed'
        else:
            return 'approved_not_subscribed'
    
    return 'new'


def get_main_keyboard(user_status: str, user_id: int = None) -> InlineKeyboardMarkup:
    """Genera la tastiera principale in base allo stato utente."""
    
    if user_status == 'subscribed':
        # Utente approvato E abbonato - mostra tutti gli accessi
        keyboard = [
            # GRUPPI (con protezione "Approva nuovi membri")
            [InlineKeyboardButton("💬 Salotto Quantico", url=GROUP_LINKS['salotto'])],
            [InlineKeyboardButton("📚 Biblioteca Digitale", url=GROUP_LINKS['biblioteca'])],
            [InlineKeyboardButton("💡 Brainstorming", url=GROUP_LINKS['brainstorming'])],
            # CANALI (accesso diretto con link)
            [InlineKeyboardButton("📢 Comunicazioni", url=CHANNEL_LINKS['comunicazioni'])],
            [
                InlineKeyboardButton("📊 Il Mio Stato", callback_data='my_status'),
                InlineKeyboardButton("🎫 Supporto", callback_data='support')
            ],
            [InlineKeyboardButton("⚙️ Gestisci Abbonamento", callback_data='manage_subscription')],
        ]
        
        # Se l'utente è admin, aggiungi sezione admin
        if user_id and is_admin(user_id):
            keyboard.append([InlineKeyboardButton("━━━ 🔐 AREA ADMIN ━━━", callback_data='admin_separator')])
            keyboard.append([
                InlineKeyboardButton("🏛️ Amministrazione", url=ADMIN_LINKS['staff_admin']),
                InlineKeyboardButton("⚙️ Reparto Tecnico", url=ADMIN_LINKS['staff_tecnico'])
            ])
            keyboard.append([InlineKeyboardButton("📋 Pannello Admin", callback_data='admin_panel')])
    
    elif user_status == 'approved_not_subscribed':
        # Utente approvato ma non abbonato (può pagare direttamente)
        keyboard = [
            [InlineKeyboardButton("🔓 ABBONATI ORA (20€/mese)", callback_data='subscribe')],
            [InlineKeyboardButton("🏠 Vai all'Hub", url=LINKS['hub'])],
            [InlineKeyboardButton("📊 Il Mio Stato", callback_data='my_status')],
        ]
    
    elif user_status == 'pending':
        # Utente in attesa di approvazione
        keyboard = [
            [InlineKeyboardButton("⏳ Richiesta in Attesa", callback_data='pending_info')],
            [InlineKeyboardButton("🏠 Vai all'Hub", url=LINKS['hub'])],
        ]
    
    elif user_status == 'rejected':
        # Utente rifiutato
        keyboard = [
            [InlineKeyboardButton("🏠 Vai all'Hub", url=LINKS['hub'])],
            [InlineKeyboardButton("📧 Contatta Supporto", callback_data='support')],
        ]
    
    else:  # 'new'
        # Nuovo utente - deve fare richiesta
        keyboard = [
            [InlineKeyboardButton("📝 RICHIEDI ACCESSO", callback_data='request_access')],
            [InlineKeyboardButton("🏠 Vai all'Hub", url=LINKS['hub'])],
            [InlineKeyboardButton("❓ Cos'è Operazione Risveglio?", callback_data='info')],
        ]
    
    return InlineKeyboardMarkup(keyboard)


# =============================================================================
# COMANDI PRINCIPALI
# =============================================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Comando /start - Punto di ingresso principale del bot.
    Gestisce anche i deep link per i ritorni da Stripe.
    """
    user = update.effective_user
    
    # Registra/aggiorna l'utente nel database
    add_user(user.id, user.username, user.first_name, user.last_name)
    log_activity(user.id, 'start', 'Avvio bot')
    
    # Controlla se c'è un parametro (deep link)
    args = context.args
    if args:
        param = args[0]
        
        # Ritorno da pagamento riuscito
        if param.startswith('payment_success_'):
            await update.message.reply_text(
                "✅ *Grazie per l'acquisto!*\n\n"
                "Il tuo abbonamento verrà attivato a breve. "
                "Usa /start per vedere il menu completo.",
                parse_mode='Markdown'
            )
            return
        
        # Ritorno da pagamento annullato
        elif param == 'payment_cancelled':
            await update.message.reply_text(
                MESSAGES['payment_cancelled'],
                parse_mode='Markdown'
            )
            return
    
    # Determina lo stato dell'utente
    user_status = get_user_status(user.id)
    
    # Genera messaggio appropriato
    if user_status == 'subscribed':
        sub_info = get_subscription_info(user.id)
        end_date = sub_info['end_date'].strftime('%d/%m/%Y') if sub_info['end_date'] else 'N/A'
        text = MESSAGES['welcome_subscriber'].format(
            name=user.first_name,
            end_date=end_date
        )
    
    elif user_status == 'approved_not_subscribed':
        text = (
            f"👋 *Bentornato {user.first_name}!*\n\n"
            "✅ Sei già stato approvato per accedere alla community.\n\n"
            "Per accedere ai contenuti premium, completa l'abbonamento:"
        )
    
    elif user_status == 'pending':
        text = (
            f"👋 *Ciao {user.first_name}!*\n\n"
            "⏳ La tua richiesta di accesso è *in attesa di approvazione*.\n\n"
            "Un amministratore la valuterà a breve. Riceverai una notifica!"
        )
    
    elif user_status == 'rejected':
        text = (
            f"👋 *Ciao {user.first_name}!*\n\n"
            "❌ La tua richiesta di accesso non è stata approvata.\n\n"
            "Se ritieni sia un errore, contatta il supporto."
        )
    
    else:  # 'new'
        text = MESSAGES['welcome_new']
    
    keyboard = get_main_keyboard(user_status, user.id)
    
    await update.message.reply_text(
        text,
        parse_mode='Markdown',
        reply_markup=keyboard
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /help - Mostra la guida ai comandi."""
    await update.message.reply_text(
        MESSAGES['help'],
        parse_mode='Markdown'
    )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /stato - Mostra lo stato dell'abbonamento."""
    user = update.effective_user
    sub_info = get_subscription_info(user.id)
    
    if sub_info['status'] == 'not_found':
        text = "❌ Non sei ancora registrato. Usa /start per iniziare."
    elif sub_info['status'] == 'active':
        end_date = sub_info['end_date'].strftime('%d/%m/%Y')
        text = (
            f"✅ *Abbonamento Attivo*\n\n"
            f"📅 Scadenza: {end_date}\n"
            f"💳 Pagamenti totali: {sub_info['total_payments']}"
        )
    else:
        approved_text = "✅ Approvato" if sub_info.get('approved') else "⏳ Non approvato"
        text = (
            f"❌ *Abbonamento Non Attivo*\n\n"
            f"📋 Stato approvazione: {approved_text}\n\n"
            "Usa /start per vedere le opzioni disponibili."
        )
    
    await update.message.reply_text(text, parse_mode='Markdown')


async def subscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /abbonati - Avvia il processo di abbonamento."""
    user = update.effective_user
    
    # Verifica se l'utente è approvato
    if not is_approved(user.id):
        user_status = get_user_status(user.id)
        
        if user_status == 'pending':
            await update.message.reply_text(
                "⏳ La tua richiesta è in attesa di approvazione.\n"
                "Riceverai una notifica quando sarà elaborata."
            )
        elif user_status == 'rejected':
            await update.message.reply_text(
                "❌ La tua richiesta non è stata approvata.\n"
                "Contatta il supporto per maggiori informazioni."
            )
        else:
            await update.message.reply_text(
                "📝 Prima di abbonarti, devi richiedere l'accesso.\n"
                "Usa /start e clicca su 'Richiedi Accesso'."
            )
        return
    
    if is_subscribed(user.id):
        await update.message.reply_text(
            "✅ Hai già un abbonamento attivo!\n"
            "Usa /stato per vedere i dettagli."
        )
        return
    
    try:
        checkout_url = create_checkout_session(user.id)
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("💳 Vai al Pagamento", url=checkout_url)],
            [InlineKeyboardButton("❌ Annulla", callback_data='cancel')]
        ])
        
        await update.message.reply_text(
            "💰 *Abbonamento Operazione Risveglio*\n\n"
            "Prezzo: *20€/mese*\n\n"
            "Cosa include:\n"
            "• 📚 Accesso completo alla Biblioteca Digitale\n"
            "• 💬 Partecipazione al Salotto Quantico\n"
            "• 💡 Accesso al Brainstorming & Feedback\n"
            "• 📢 Comunicazioni ufficiali\n"
            "• 🎯 Supporto prioritario\n\n"
            "Clicca il pulsante per procedere al pagamento sicuro con Stripe:",
            parse_mode='Markdown',
            reply_markup=keyboard
        )
        
    except Exception as e:
        logger.error(f"Errore creazione checkout: {e}")
        await update.message.reply_text(
            "❌ Si è verificato un errore. Riprova più tardi o contatta il supporto."
        )


# =============================================================================
# GESTIONE RICHIESTE ACCESSO AI GRUPPI (ChatJoinRequest)
# =============================================================================

async def handle_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Gestisce le richieste di accesso ai gruppi privati.
    Chiamato quando qualcuno clicca un link di invito con "Approve new members" attivo.
    """
    join_request = update.chat_join_request
    user = join_request.from_user
    chat = join_request.chat
    
    logger.info(f"Richiesta accesso gruppo {chat.title} da user {user.id} (@{user.username})")
    
    # Verifica se l'utente può accedere (approvato E abbonato)
    if can_access_groups(user.id):
        # APPROVA
        await join_request.approve()
        logger.info(f"Utente {user.id} approvato per {chat.title}")
        
        try:
            await context.bot.send_message(
                chat_id=user.id,
                text=f"✅ *Accesso Approvato!*\n\nBenvenuto in *{chat.title}*!",
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Errore invio conferma a {user.id}: {e}")
    else:
        # RIFIUTA
        await join_request.decline()
        logger.info(f"Utente {user.id} rifiutato per {chat.title}")
        
        # Determina il motivo
        user_status = get_user_status(user.id)
        
        if user_status == 'new':
            reason = "Non hai ancora richiesto l'accesso. Scrivi /start al bot per iniziare."
        elif user_status == 'pending':
            reason = "La tua richiesta è ancora in attesa di approvazione."
        elif user_status == 'rejected':
            reason = "La tua richiesta di accesso non è stata approvata."
        elif user_status == 'approved_not_subscribed':
            reason = "Devi completare l'abbonamento per accedere. Scrivi /start al bot."
        else:
            reason = "Non hai i requisiti per accedere. Scrivi /start al bot per maggiori info."
        
        try:
            await context.bot.send_message(
                chat_id=user.id,
                text=f"❌ *Accesso Negato*\n\n{reason}",
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Errore invio rifiuto a {user.id}: {e}")


# =============================================================================
# GESTIONE CALLBACK (PULSANTI)
# =============================================================================

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce i click sui pulsanti inline."""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    data = query.data
    
    # NUOVO: Richiesta accesso
    if data == 'request_access':
        # Imposta l'utente come pending
        set_pending(user.id)
        log_activity(user.id, 'access_request', 'Richiesta accesso inviata')
        
        await query.edit_message_text(
            "✅ *Richiesta Inviata!*\n\n"
            "La tua richiesta di accesso è stata inviata agli amministratori.\n\n"
            "⏳ Riceverai una notifica quando sarà elaborata.\n\n"
            "Grazie per la pazienza!",
            parse_mode='Markdown'
        )
        
        # Notifica agli admin
        admin_keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Approva", callback_data=f'admin_approve_{user.id}'),
                InlineKeyboardButton("❌ Rifiuta", callback_data=f'admin_reject_{user.id}')
            ]
        ])
        
        admin_text = (
            "🆕 *NUOVA RICHIESTA DI ACCESSO*\n\n"
            f"👤 Nome: {user.first_name} {user.last_name or ''}\n"
            f"🔗 Username: @{user.username or 'N/A'}\n"
            f"🆔 ID: `{user.id}`\n\n"
            "Azione:"
        )
        
        # Invia notifica a tutti gli admin
        for admin_id in get_admin_ids():
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=admin_text,
                    parse_mode='Markdown',
                    reply_markup=admin_keyboard
                )
            except Exception as e:
                logger.error(f"Errore notifica admin {admin_id}: {e}")
        
        # Invia anche nel gruppo staff admin (se configurato)
        if STAFF_ADMIN_CHAT_ID:
            try:
                await context.bot.send_message(
                    chat_id=STAFF_ADMIN_CHAT_ID,
                    text=admin_text,
                    parse_mode='Markdown',
                    reply_markup=admin_keyboard
                )
            except Exception as e:
                logger.error(f"Errore notifica gruppo staff: {e}")
    
    # NUOVO: Info su richiesta pending
    elif data == 'pending_info':
        await query.answer("La tua richiesta è in lavorazione!", show_alert=True)
    
    # NUOVO: Approvazione/Rifiuto da admin (inline button)
    elif data.startswith('admin_approve_'):
        if not is_admin(user.id):
            await query.answer("Non sei autorizzato!", show_alert=True)
            return
        
        target_user_id = int(data.replace('admin_approve_', ''))
        approve_user(target_user_id, user.id)
        log_activity(target_user_id, 'approved', f'Approvato da {user.id}')
        
        await query.edit_message_text(
            f"✅ Utente `{target_user_id}` *APPROVATO*\n\n"
            f"Approvato da: @{user.username or user.first_name}",
            parse_mode='Markdown'
        )
        
        # Notifica l'utente approvato
        try:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔓 ABBONATI ORA", callback_data='subscribe')]
            ])
            
            await context.bot.send_message(
                chat_id=target_user_id,
                text=(
                    "🎉 *RICHIESTA APPROVATA!*\n\n"
                    "Benvenuto nella community Operazione Risveglio!\n\n"
                    "Ora puoi procedere con l'abbonamento per accedere "
                    "a tutti i contenuti premium."
                ),
                parse_mode='Markdown',
                reply_markup=keyboard
            )
        except Exception as e:
            logger.error(f"Errore notifica utente approvato {target_user_id}: {e}")
    
    elif data.startswith('admin_reject_'):
        if not is_admin(user.id):
            await query.answer("Non sei autorizzato!", show_alert=True)
            return
        
        target_user_id = int(data.replace('admin_reject_', ''))
        reject_user(target_user_id, user.id)
        log_activity(target_user_id, 'rejected', f'Rifiutato da {user.id}')
        
        await query.edit_message_text(
            f"❌ Utente `{target_user_id}` *RIFIUTATO*\n\n"
            f"Rifiutato da: @{user.username or user.first_name}",
            parse_mode='Markdown'
        )
        
        # Notifica l'utente rifiutato
        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text=(
                    "❌ *RICHIESTA NON APPROVATA*\n\n"
                    "Ci dispiace, la tua richiesta di accesso non è stata approvata.\n\n"
                    "Se ritieni sia un errore, contatta il supporto."
                ),
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Errore notifica utente rifiutato {target_user_id}: {e}")
    
    # Abbonamento
    elif data == 'subscribe':
        # Verifica se approvato
        if not is_approved(user.id):
            await query.answer("Devi prima essere approvato!", show_alert=True)
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
                "💰 *Abbonamento Operazione Risveglio*\n\n"
                "Prezzo: *20€/mese*\n\n"
                "Clicca per procedere al pagamento sicuro:",
                parse_mode='Markdown',
                reply_markup=keyboard
            )
        except Exception as e:
            logger.error(f"Errore checkout: {e}")
            await query.edit_message_text("❌ Errore. Riprova più tardi.")
    
    # Info sul progetto
    elif data == 'info':
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📝 RICHIEDI ACCESSO", callback_data='request_access')],
            [InlineKeyboardButton("🔙 Indietro", callback_data='back_to_menu')]
        ])
        
        await query.edit_message_text(
            "🌟 *COS'È OPERAZIONE RISVEGLIO?*\n\n"
            "Operazione Risveglio è una community dedicata allo sviluppo, "
            "uso e condivisione di esperienze nell'utilizzo di device quantistici "
            "per l'equilibrio personale.\n\n"
            "*Cosa troverai:*\n"
            "• 📚 Software, manuali e risorse esclusive\n"
            "• 💬 Community di supporto e condivisione\n"
            "• 💡 Possibilità di influenzare lo sviluppo\n"
            "• 🎧 Audio guidati e frequenze\n"
            "• 🧬 QRCode e schemi energetici\n\n"
            "Unisciti a noi!",
            parse_mode='Markdown',
            reply_markup=keyboard
        )
    
    # Stato abbonamento
    elif data == 'my_status':
        sub_info = get_subscription_info(user.id)
        
        if sub_info['status'] == 'active':
            end_date = sub_info['end_date'].strftime('%d/%m/%Y')
            text = (
                f"✅ *Il Tuo Abbonamento*\n\n"
                f"📅 Stato: Attivo\n"
                f"📆 Scadenza: {end_date}\n"
                f"💳 Pagamenti: {sub_info['total_payments']}"
            )
        else:
            approved_text = "✅ Sì" if sub_info.get('approved') else "❌ No"
            text = f"❌ Nessun abbonamento attivo.\n\n📋 Approvato: {approved_text}"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Indietro", callback_data='back_to_menu')]
        ])
        
        await query.edit_message_text(text, parse_mode='Markdown', reply_markup=keyboard)
    
    # Gestione abbonamento (portale Stripe)
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
                    "⚙️ *Gestione Abbonamento*\n\n"
                    "Dal portale Stripe puoi:\n"
                    "• Aggiornare il metodo di pagamento\n"
                    "• Vedere le fatture\n"
                    "• Cancellare l'abbonamento\n",
                    parse_mode='Markdown',
                    reply_markup=keyboard
                )
            except Exception as e:
                logger.error(f"Errore portale: {e}")
                await query.edit_message_text("❌ Errore. Riprova più tardi.")
        else:
            await query.edit_message_text("❌ Nessun abbonamento da gestire.")
    
    # Supporto
    elif data == 'support':
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("💳 Problemi Pagamento", callback_data='support_payment')],
            [InlineKeyboardButton("🔧 Supporto Tecnico", callback_data='support_tech')],
            [InlineKeyboardButton("🚪 Problemi Accesso", callback_data='support_access')],
            [InlineKeyboardButton("📚 Contenuti", callback_data='support_content')],
            [InlineKeyboardButton("❓ Altro", callback_data='support_other')],
            [InlineKeyboardButton("🔙 Indietro", callback_data='back_to_menu')]
        ])
        
        await query.edit_message_text(
            "🎫 *SUPPORTO*\n\n"
            "Seleziona la categoria del tuo problema:",
            parse_mode='Markdown',
            reply_markup=keyboard
        )
    
    # Categorie supporto
    elif data.startswith('support_'):
        category = data.replace('support_', '')
        context.user_data['support_category'] = category
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Annulla", callback_data='back_to_menu')]
        ])
        
        await query.edit_message_text(
            "📝 *Descrivi il tuo problema*\n\n"
            "Scrivi un messaggio dettagliato con:\n"
            "• Cosa stavi facendo\n"
            "• Quale errore vedi\n"
            "• Eventuali screenshot (puoi allegarli dopo)\n\n"
            "Invia il messaggio qui sotto:",
            parse_mode='Markdown',
            reply_markup=keyboard
        )
        
        return SUPPORT_DESCRIPTION
    
    # Torna al menu principale
    elif data == 'back_to_menu':
        user_status = get_user_status(user.id)
        
        if user_status == 'subscribed':
            sub_info = get_subscription_info(user.id)
            end_date = sub_info['end_date'].strftime('%d/%m/%Y') if sub_info['end_date'] else 'N/A'
            text = MESSAGES['welcome_subscriber'].format(name=user.first_name, end_date=end_date)
        elif user_status == 'approved_not_subscribed':
            text = f"👋 *Bentornato {user.first_name}!*\n\n✅ Sei approvato. Abbonati per accedere ai contenuti!"
        elif user_status == 'pending':
            text = f"⏳ La tua richiesta è in attesa di approvazione..."
        else:
            text = MESSAGES['welcome_new']
        
        keyboard = get_main_keyboard(user_status, user.id)
        await query.edit_message_text(text, parse_mode='Markdown', reply_markup=keyboard)
    
    # Separatore admin (non fa nulla)
    elif data == 'admin_separator':
        await query.answer("🔐 Sezione Admin", show_alert=False)
    
    # Pannello admin
    elif data == 'admin_panel':
        if not is_admin(user.id):
            await query.answer("Non autorizzato!", show_alert=True)
            return
        
        stats = get_stats()
        text = (
            "📊 *PANNELLO ADMIN*\n\n"
            f"👥 Utenti totali: {stats['total_users']}\n"
            f"✅ Abbonati attivi: {stats['active_subscribers']}\n"
            f"🆕 Nuovi (7gg): {stats['new_users_week']}\n"
            f"⏳ In attesa approvazione: {stats['pending_users']}\n"
            f"🎫 Ticket aperti: {stats['open_tickets']}\n"
            f"👑 Admin: {stats['total_admins']}\n"
            f"💰 Entrate mese: €{stats['monthly_revenue']:.2f}\n\n"
            "*Comandi disponibili:*\n"
            "/pending - Utenti in attesa\n"
            "/approva @user - Approva utente\n"
            "/rifiuta @user - Rifiuta utente\n"
            "/admin - Statistiche\n"
        )
        
        if is_super_admin(user.id):
            text += (
                "\n*Comandi Super Admin:*\n"
                "/addadmin <id> - Aggiungi admin\n"
                "/removeadmin <id> - Rimuovi admin\n"
                "/listadmin - Lista admin\n"
            )
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Torna al Menu", callback_data='back_to_menu')]
        ])
        
        await query.edit_message_text(text, parse_mode='Markdown', reply_markup=keyboard)
    
    # Annulla operazione
    elif data == 'cancel':
        await query.edit_message_text("❌ Operazione annullata.")


# =============================================================================
# GESTIONE SUPPORTO (CONVERSATION)
# =============================================================================

async def support_description_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Riceve la descrizione del problema di supporto."""
    user = update.effective_user
    description = update.message.text
    category = context.user_data.get('support_category', 'other')
    
    # Crea il ticket nel database
    ticket_id = create_ticket(user.id, category, description)
    
    # Mappa categorie
    category_names = {
        'payment': '💳 Pagamenti',
        'tech': '🔧 Tecnico',
        'access': '🚪 Accesso',
        'content': '📚 Contenuti',
        'other': '❓ Altro'
    }
    
    await update.message.reply_text(
        f"✅ *Ticket #{ticket_id} Creato!*\n\n"
        f"📌 Categoria: {category_names.get(category, category)}\n"
        f"⏰ Tempo stimato: 2-4 ore\n\n"
        "Ti risponderemo il prima possibile.\n"
        "Usa /start per tornare al menu.",
        parse_mode='Markdown'
    )
    
    log_activity(user.id, 'support_ticket', f'Ticket #{ticket_id} creato')
    
    # Pulisci i dati temporanei
    context.user_data.clear()
    
    return ConversationHandler.END


async def cancel_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Annulla la creazione del ticket."""
    context.user_data.clear()
    await update.message.reply_text("❌ Richiesta supporto annullata. Usa /start per tornare al menu.")
    return ConversationHandler.END


# =============================================================================
# COMANDI ADMIN
# =============================================================================

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /admin - Mostra statistiche (solo admin)."""
    user = update.effective_user
    
    if not is_admin(user.id):
        await update.message.reply_text("❌ Non hai i permessi per questo comando.")
        return
    
    stats = get_stats()
    
    text = (
        "📊 *STATISTICHE ADMIN*\n\n"
        f"👥 Utenti totali: {stats['total_users']}\n"
        f"✅ Abbonati attivi: {stats['active_subscribers']}\n"
        f"🆕 Nuovi (7 giorni): {stats['new_users_week']}\n"
        f"⏳ In attesa approvazione: {stats['pending_users']}\n"
        f"🎫 Ticket aperti: {stats['open_tickets']}\n"
        f"💰 Entrate mese: €{stats['monthly_revenue']:.2f}"
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⏳ Vedi Richieste Pending", callback_data='admin_pending')],
        [InlineKeyboardButton("🎫 Vedi Ticket Aperti", callback_data='admin_tickets')],
        [InlineKeyboardButton("📢 Invia Annuncio", callback_data='admin_announce')]
    ])
    
    await update.message.reply_text(text, parse_mode='Markdown', reply_markup=keyboard)


async def pending_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /pending - Mostra utenti in attesa di approvazione."""
    user = update.effective_user
    
    if not is_admin(user.id):
        await update.message.reply_text("❌ Non hai i permessi per questo comando.")
        return
    
    pending = get_pending_users()
    
    if not pending:
        await update.message.reply_text("✅ Nessuna richiesta in attesa!")
        return
    
    for p in pending[:10]:  # Max 10
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Approva", callback_data=f"admin_approve_{p['user_id']}"),
                InlineKeyboardButton("❌ Rifiuta", callback_data=f"admin_reject_{p['user_id']}")
            ]
        ])
        
        await update.message.reply_text(
            f"👤 *{p['first_name']} {p.get('last_name', '')}*\n"
            f"🔗 @{p['username'] or 'N/A'}\n"
            f"🆔 `{p['user_id']}`\n"
            f"📅 Richiesta: {p['joined_date'].strftime('%d/%m/%Y %H:%M') if p.get('joined_date') else 'N/A'}",
            parse_mode='Markdown',
            reply_markup=keyboard
        )
    
    if len(pending) > 10:
        await update.message.reply_text(f"... e altri {len(pending) - 10} in attesa.")


async def approve_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /approva @username - Approva un utente."""
    user = update.effective_user
    
    if not is_admin(user.id):
        await update.message.reply_text("❌ Non hai i permessi per questo comando.")
        return
    
    if not context.args:
        await update.message.reply_text("❌ Uso: /approva @username")
        return
    
    username = context.args[0]
    target_user = get_user_by_username(username)
    
    if not target_user:
        await update.message.reply_text(f"❌ Utente {username} non trovato.")
        return
    
    approve_user(target_user['user_id'], user.id)
    log_activity(target_user['user_id'], 'approved', f'Approvato da {user.id}')
    
    await update.message.reply_text(f"✅ Utente {username} approvato!")
    
    # Notifica l'utente
    try:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔓 ABBONATI ORA", callback_data='subscribe')]
        ])
        
        await context.bot.send_message(
            chat_id=target_user['user_id'],
            text=(
                "🎉 *RICHIESTA APPROVATA!*\n\n"
                "Benvenuto nella community Operazione Risveglio!\n\n"
                "Ora puoi procedere con l'abbonamento."
            ),
            parse_mode='Markdown',
            reply_markup=keyboard
        )
    except Exception as e:
        logger.error(f"Errore notifica: {e}")


async def reject_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /rifiuta @username - Rifiuta un utente."""
    user = update.effective_user
    
    if not is_admin(user.id):
        await update.message.reply_text("❌ Non hai i permessi per questo comando.")
        return
    
    if not context.args:
        await update.message.reply_text("❌ Uso: /rifiuta @username")
        return
    
    username = context.args[0]
    target_user = get_user_by_username(username)
    
    if not target_user:
        await update.message.reply_text(f"❌ Utente {username} non trovato.")
        return
    
    reject_user(target_user['user_id'], user.id)
    log_activity(target_user['user_id'], 'rejected', f'Rifiutato da {user.id}')
    
    await update.message.reply_text(f"❌ Utente {username} rifiutato.")
    
    # Notifica l'utente
    try:
        await context.bot.send_message(
            chat_id=target_user['user_id'],
            text="❌ *RICHIESTA NON APPROVATA*\n\nCi dispiace, la tua richiesta non è stata approvata.",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Errore notifica: {e}")


# =============================================================================
# COMANDI GESTIONE ADMIN DINAMICI (Solo Super Admin)
# =============================================================================

async def addadmin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /addadmin <user_id> - Aggiunge un admin (solo Super Admin)."""
    user = update.effective_user
    
    if not is_super_admin(user.id):
        await update.message.reply_text("❌ Solo il Super Admin può aggiungere admin.")
        return
    
    if not context.args:
        await update.message.reply_text(
            "❌ *Uso:* /addadmin <user_id>\n\n"
            "Esempio: `/addadmin 123456789`\n\n"
            "Per ottenere l'user_id, l'utente può scrivere a @userinfobot",
            parse_mode='Markdown'
        )
        return
    
    try:
        target_user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ L'user_id deve essere un numero.")
        return
    
    # Cerca info utente nel database
    target_user = get_user(target_user_id)
    username = target_user['username'] if target_user else None
    first_name = target_user['first_name'] if target_user else None
    
    if add_admin(target_user_id, user.id, username, first_name):
        name_display = f"@{username}" if username else f"ID: {target_user_id}"
        await update.message.reply_text(
            f"✅ *Admin Aggiunto!*\n\n"
            f"👤 {name_display}\n"
            f"🆔 `{target_user_id}`",
            parse_mode='Markdown'
        )
        log_activity(user.id, 'add_admin', f'Aggiunto admin {target_user_id}')
    else:
        await update.message.reply_text("ℹ️ L'utente è già admin.")


async def removeadmin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /removeadmin <user_id> - Rimuove un admin (solo Super Admin)."""
    user = update.effective_user
    
    if not is_super_admin(user.id):
        await update.message.reply_text("❌ Solo il Super Admin può rimuovere admin.")
        return
    
    if not context.args:
        await update.message.reply_text(
            "❌ *Uso:* /removeadmin <user_id>\n\n"
            "Esempio: `/removeadmin 123456789`",
            parse_mode='Markdown'
        )
        return
    
    try:
        target_user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ L'user_id deve essere un numero.")
        return
    
    if target_user_id == SUPER_ADMIN_ID:
        await update.message.reply_text("❌ Non puoi rimuovere il Super Admin!")
        return
    
    if remove_admin(target_user_id, user.id):
        await update.message.reply_text(
            f"✅ *Admin Rimosso!*\n\n"
            f"🆔 `{target_user_id}`",
            parse_mode='Markdown'
        )
        log_activity(user.id, 'remove_admin', f'Rimosso admin {target_user_id}')
    else:
        await update.message.reply_text("❌ Utente non trovato tra gli admin.")


async def listadmin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /listadmin - Mostra lista admin (solo Super Admin)."""
    user = update.effective_user
    
    if not is_super_admin(user.id):
        await update.message.reply_text("❌ Solo il Super Admin può vedere la lista admin.")
        return
    
    admins = get_all_admins()
    
    if not admins:
        await update.message.reply_text("ℹ️ Nessun admin configurato.")
        return
    
    text = "👥 *LISTA AMMINISTRATORI*\n\n"
    
    for admin in admins:
        role_emoji = "👑" if admin['role'] == 'super_admin' else "👤"
        username = admin.get('current_username') or admin.get('username') or '-'
        name = admin.get('current_first_name') or admin.get('first_name') or '-'
        
        text += f"{role_emoji} *{name}*\n"
        text += f"   └ @{username}\n"
        text += f"   └ ID: `{admin['user_id']}`\n\n"
    
    await update.message.reply_text(text, parse_mode='Markdown')


async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce i callback admin."""
    query = update.callback_query
    await query.answer()
    
    if not is_admin(update.effective_user.id):
        return
    
    if query.data == 'admin_pending':
        pending = get_pending_users()
        
        if not pending:
            await query.edit_message_text("✅ Nessuna richiesta in attesa!")
            return
        
        text = "⏳ *RICHIESTE IN ATTESA*\n\n"
        for p in pending[:10]:
            text += (
                f"👤 {p['first_name']} (@{p['username'] or 'N/A'})\n"
                f"   ID: `{p['user_id']}`\n\n"
            )
        
        text += "\nUsa /pending per gestirle singolarmente."
        
        await query.edit_message_text(text, parse_mode='Markdown')
    
    elif query.data == 'admin_tickets':
        tickets = get_open_tickets()
        
        if not tickets:
            await query.edit_message_text("✅ Nessun ticket aperto!")
            return
        
        text = "🎫 *TICKET APERTI*\n\n"
        for t in tickets[:10]:
            text += (
                f"*#{t['ticket_id']}* - {t['category']}\n"
                f"👤 @{t['username'] or t['first_name']}\n"
                f"📝 {t['description'][:50]}...\n\n"
            )
        
        await query.edit_message_text(text, parse_mode='Markdown')
    
    # GESTIONE APPROVAZIONE UTENTI (FIX - spostato qui da button_handler)
    elif query.data.startswith('admin_approve_'):
        user = update.effective_user
        target_user_id = int(query.data.replace('admin_approve_', ''))
        approve_user(target_user_id, user.id)
        log_activity(target_user_id, 'approved', f'Approvato da {user.id}')
        
        await query.edit_message_text(
            f"✅ Utente `{target_user_id}` *APPROVATO*\n\n"
            f"Approvato da: @{user.username or user.first_name}",
            parse_mode='Markdown'
        )
        
        # Notifica l'utente approvato
        try:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔓 ABBONATI ORA", callback_data='subscribe')]
            ])
            
            await context.bot.send_message(
                chat_id=target_user_id,
                text=(
                    "🎉 *RICHIESTA APPROVATA!*\n\n"
                    "Benvenuto nella community Operazione Risveglio!\n\n"
                    "Ora puoi procedere con l'abbonamento per accedere "
                    "a tutti i contenuti premium."
                ),
                parse_mode='Markdown',
                reply_markup=keyboard
            )
        except Exception as e:
            logger.error(f"Errore notifica utente approvato {target_user_id}: {e}")
    
    elif query.data.startswith('admin_reject_'):
        user = update.effective_user
        target_user_id = int(query.data.replace('admin_reject_', ''))
        reject_user(target_user_id, user.id)
        log_activity(target_user_id, 'rejected', f'Rifiutato da {user.id}')
        
        await query.edit_message_text(
            f"❌ Utente `{target_user_id}` *RIFIUTATO*\n\n"
            f"Rifiutato da: @{user.username or user.first_name}",
            parse_mode='Markdown'
        )
        
        # Notifica l'utente rifiutato
        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text=(
                    "❌ *RICHIESTA NON APPROVATA*\n\n"
                    "Ci dispiace, la tua richiesta di accesso non è stata approvata.\n\n"
                    "Se ritieni sia un errore, contatta il supporto."
                ),
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Errore notifica utente rifiutato {target_user_id}: {e}")


# =============================================================================
# TASK SCHEDULATI
# =============================================================================

async def check_expiring_subscriptions(context: ContextTypes.DEFAULT_TYPE):
    """
    Task schedulato: controlla abbonamenti in scadenza e invia promemoria.
    Eseguito ogni giorno.
    """
    expiring = get_expiring_subscriptions(days=RENEWAL_REMINDER_DAYS)
    
    for user in expiring:
        try:
            end_date = user['subscription_end'].strftime('%d/%m/%Y')
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Rinnova Ora", callback_data='subscribe')]
            ])
            
            await context.bot.send_message(
                chat_id=user['user_id'],
                text=(
                    f"⚠️ *Promemoria Abbonamento*\n\n"
                    f"Il tuo abbonamento scade il {end_date}.\n"
                    "Rinnova per continuare ad accedere ai contenuti premium!"
                ),
                parse_mode='Markdown',
                reply_markup=keyboard
            )
            
            logger.info(f"Promemoria inviato a {user['user_id']}")
            
        except Exception as e:
            logger.error(f"Errore invio promemoria a {user['user_id']}: {e}")


async def check_expired_subscriptions(context: ContextTypes.DEFAULT_TYPE):
    """
    Task schedulato: disattiva abbonamenti scaduti.
    Eseguito ogni giorno.
    """
    expired = get_expired_subscriptions()
    
    for user in expired:
        try:
            deactivate_subscription(user['user_id'])
            
            await context.bot.send_message(
                chat_id=user['user_id'],
                text=MESSAGES['subscription_expired'].format(
                    name=user['first_name'],
                    end_date=user['subscription_end'].strftime('%d/%m/%Y')
                ),
                parse_mode='Markdown'
            )
            
            logger.info(f"Abbonamento scaduto disattivato per {user['user_id']}")
            
        except Exception as e:
            logger.error(f"Errore disattivazione {user['user_id']}: {e}")


# =============================================================================
# WEBHOOK SERVER PER STRIPE (in thread separato)
# =============================================================================

def run_webhook_server_sync():
    """Avvia il server webhook in modo sincrono (per thread separato)."""
    
    async def handle_stripe_webhook(request):
        """Gestisce i webhook da Stripe."""
        payload = await request.read()
        sig_header = request.headers.get('Stripe-Signature')
        
        logger.info("=== WEBHOOK STRIPE RICEVUTO ===")
        
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, STRIPE_WEBHOOK_SECRET
            )
            logger.info(f"Evento Stripe: {event['type']}")
        except ValueError as e:
            logger.error(f"Payload non valido: {e}")
            return web.Response(status=400)
        except stripe.error.SignatureVerificationError as e:
            logger.error(f"Firma non valida: {e}")
            return web.Response(status=400)
        
        # Gestisci checkout completato
        if event['type'] == 'checkout.session.completed':
            session = event['data']['object']
            user_id = session.get('metadata', {}).get('telegram_user_id')
            customer_id = session.get('customer')
            subscription_id = session.get('subscription')
            
            if user_id:
                user_id = int(user_id)
                activate_subscription(user_id, customer_id, subscription_id)
                logger.info(f"✅ Abbonamento ATTIVATO per user {user_id}")
            else:
                logger.error("telegram_user_id non trovato nei metadata!")
        
        elif event['type'] == 'invoice.payment_succeeded':
            logger.info("Pagamento rinnovo ricevuto")
        
        elif event['type'] == 'customer.subscription.deleted':
            logger.info("Abbonamento cancellato")
        
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
        logger.info("🌐 Webhook server avviato su porta 8080")
        
        # Mantieni il server in esecuzione
        while True:
            await asyncio.sleep(3600)
    
    # Crea un nuovo event loop per questo thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(start_server())


# =============================================================================
# MAIN
# =============================================================================

def main():
    """Avvia il bot."""
    # Inizializza il database
    init_db()
    logger.info("Database inizializzato")
    
    # Avvia il webhook server in un thread separato
    webhook_thread = threading.Thread(target=run_webhook_server_sync, daemon=True)
    webhook_thread.start()
    logger.info("Webhook thread avviato")
    
    # Crea l'applicazione
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Handler conversazione supporto
    support_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_handler, pattern='^support_')],
        states={
            SUPPORT_DESCRIPTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, support_description_handler)
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel_support)],
    )
    
    # Registra gli handler
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('help', help_command))
    application.add_handler(CommandHandler('stato', status_command))
    application.add_handler(CommandHandler('abbonati', subscribe_command))
    application.add_handler(CommandHandler('admin', admin_stats))
    application.add_handler(CommandHandler('pending', pending_command))
    application.add_handler(CommandHandler('approva', approve_command))
    application.add_handler(CommandHandler('rifiuta', reject_command))
    # Comandi gestione admin (solo Super Admin)
    application.add_handler(CommandHandler('addadmin', addadmin_command))
    application.add_handler(CommandHandler('removeadmin', removeadmin_command))
    application.add_handler(CommandHandler('listadmin', listadmin_command))
    application.add_handler(support_handler)
    application.add_handler(CallbackQueryHandler(admin_callback, pattern='^admin_'))
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Handler per richieste di accesso ai gruppi
    application.add_handler(ChatJoinRequestHandler(handle_join_request))
    
    # Configura lo scheduler per i task periodici
    scheduler = AsyncIOScheduler(timezone='Europe/Rome')
    
    # Controlla abbonamenti ogni giorno alle 9:00
    scheduler.add_job(
        check_expiring_subscriptions,
        'cron',
        hour=9,
        minute=0,
        args=[application]
    )
    
    scheduler.add_job(
        check_expired_subscriptions,
        'cron',
        hour=0,
        minute=5,
        args=[application]
    )
    
    scheduler.start()
    logger.info("Scheduler avviato")
    
    # Avvia il bot
    logger.info("Bot avviato!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
