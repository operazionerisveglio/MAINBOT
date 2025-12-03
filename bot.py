"""
BOT PRINCIPALE - OPERAZIONE RISVEGLIO
======================================
Bot Telegram per la gestione della community, abbonamenti e navigazione.

Per avviare il bot: python bot.py
"""

import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, 
    CommandHandler, 
    CallbackQueryHandler, 
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import BOT_TOKEN, LINKS, MESSAGES, ADMIN_IDS, RENEWAL_REMINDER_DAYS
from database import (
    init_db, add_user, get_user, is_subscribed, get_subscription_info,
    activate_subscription, get_expiring_subscriptions, get_expired_subscriptions,
    deactivate_subscription, create_ticket, get_open_tickets, close_ticket,
    get_stats, log_activity
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

def is_admin(user_id: int) -> bool:
    """Verifica se l'utente è un amministratore."""
    return user_id in ADMIN_IDS


def get_main_keyboard(subscribed: bool) -> InlineKeyboardMarkup:
    """Genera la tastiera principale in base allo stato abbonamento."""
    if subscribed:
        keyboard = [
            [InlineKeyboardButton("💬 Salotto Quantico", url=LINKS['salotto'])],
            [InlineKeyboardButton("📚 Biblioteca Digitale", url=LINKS['biblioteca'])],
            [InlineKeyboardButton("💡 Brainstorming", url=LINKS['brainstorming'])],
            [InlineKeyboardButton("📢 Comunicazioni", url=LINKS['comunicazioni'])],
            [
                InlineKeyboardButton("📊 Il Mio Stato", callback_data='my_status'),
                InlineKeyboardButton("🎫 Supporto", callback_data='support')
            ],
            [InlineKeyboardButton("⚙️ Gestisci Abbonamento", callback_data='manage_subscription')],
        ]
    else:
        keyboard = [
            [InlineKeyboardButton("🔓 ABBONATI ORA (20€/mese)", callback_data='subscribe')],
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
            # Il webhook Stripe attiverà l'abbonamento
            # Qui mostriamo solo un messaggio di conferma
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
    
    # Verifica stato abbonamento
    subscribed = is_subscribed(user.id)
    
    if subscribed:
        # Utente abbonato
        sub_info = get_subscription_info(user.id)
        end_date = sub_info['end_date'].strftime('%d/%m/%Y') if sub_info['end_date'] else 'N/A'
        
        text = MESSAGES['welcome_subscriber'].format(
            name=user.first_name,
            end_date=end_date
        )
    else:
        # Utente non abbonato
        text = MESSAGES['welcome_new']
    
    keyboard = get_main_keyboard(subscribed)
    
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
        text = (
            "❌ *Abbonamento Non Attivo*\n\n"
            "Usa /abbonati per sottoscrivere un abbonamento."
        )
    
    await update.message.reply_text(text, parse_mode='Markdown')


async def subscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /abbonati - Avvia il processo di abbonamento."""
    user = update.effective_user
    
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
# GESTIONE CALLBACK (PULSANTI)
# =============================================================================

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce i click sui pulsanti inline."""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    data = query.data
    
    # Abbonamento
    if data == 'subscribe':
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
            [InlineKeyboardButton("🔓 ABBONATI ORA", callback_data='subscribe')],
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
            text = "❌ Nessun abbonamento attivo."
        
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
        subscribed = is_subscribed(user.id)
        
        if subscribed:
            sub_info = get_subscription_info(user.id)
            end_date = sub_info['end_date'].strftime('%d/%m/%Y') if sub_info['end_date'] else 'N/A'
            text = MESSAGES['welcome_subscriber'].format(name=user.first_name, end_date=end_date)
        else:
            text = MESSAGES['welcome_new']
        
        keyboard = get_main_keyboard(subscribed)
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
        f"🎫 Ticket aperti: {stats['open_tickets']}\n"
        f"💰 Entrate mese: €{stats['monthly_revenue']:.2f}"
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎫 Vedi Ticket Aperti", callback_data='admin_tickets')],
        [InlineKeyboardButton("📢 Invia Annuncio", callback_data='admin_announce')]
    ])
    
    await update.message.reply_text(text, parse_mode='Markdown', reply_markup=keyboard)


async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce i callback admin."""
    query = update.callback_query
    await query.answer()
    
    if not is_admin(update.effective_user.id):
        return
    
    if query.data == 'admin_tickets':
        tickets = get_open_tickets()
        
        if not tickets:
            await query.edit_message_text("✅ Nessun ticket aperto!")
            return
        
        text = "🎫 *TICKET APERTI*\n\n"
        for t in tickets[:10]:  # Mostra max 10
            text += (
                f"*#{t['ticket_id']}* - {t['category']}\n"
                f"👤 @{t['username'] or t['first_name']}\n"
                f"📝 {t['description'][:50]}...\n\n"
            )
        
        await query.edit_message_text(text, parse_mode='Markdown')


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
# MAIN
# =============================================================================

def main():
    """Avvia il bot."""
    # Inizializza il database
    init_db()
    logger.info("Database inizializzato")
    
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
    application.add_handler(support_handler)
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(CallbackQueryHandler(admin_callback, pattern='^admin_'))
    
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
