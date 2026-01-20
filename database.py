"""
GESTIONE DATABASE - OPERAZIONE RISVEGLIO
=========================================
Questo modulo gestisce tutte le operazioni sul database PostgreSQL.
"""

import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta
from config import DATABASE_URL, SUPER_ADMIN_IDS
import logging

logger = logging.getLogger(__name__)


def get_connection():
    """Crea e restituisce una connessione al database."""
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


def init_db():
    """
    Inizializza il database creando tutte le tabelle necessarie.
    Chiamare questa funzione all'avvio del bot.
    """
    conn = get_connection()
    cur = conn.cursor()
    
    # Tabella utenti (AGGIUNTO: approved, approved_at, approved_by)
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            subscription_status TEXT DEFAULT 'inactive',
            subscription_start DATE,
            subscription_end DATE,
            stripe_customer_id TEXT,
            stripe_subscription_id TEXT,
            joined_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            total_payments INTEGER DEFAULT 0,
            notes TEXT,
            approved BOOLEAN DEFAULT FALSE,
            approved_at TIMESTAMP,
            approved_by BIGINT
        )
    ''')
    
    # Aggiungi colonna approved se non esiste (per database esistenti)
    cur.execute('''
        DO $$ 
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name='users' AND column_name='approved') THEN
                ALTER TABLE users ADD COLUMN approved BOOLEAN DEFAULT FALSE;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name='users' AND column_name='approved_at') THEN
                ALTER TABLE users ADD COLUMN approved_at TIMESTAMP;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name='users' AND column_name='approved_by') THEN
                ALTER TABLE users ADD COLUMN approved_by BIGINT;
            END IF;
        END $$;
    ''')
    
    # ==========================================================================
    # NUOVA TABELLA: Amministratori dinamici
    # ==========================================================================
    cur.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            user_id BIGINT PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            added_by BIGINT,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            role TEXT DEFAULT 'admin'
        )
    ''')
    
    # Assicurati che il Super Admin sia sempre presente
    for super_admin_id in SUPER_ADMIN_IDS:
        cur.execute('''
            INSERT INTO admins (user_id, role, added_by)
            VALUES (%s, 'super_admin', %s)
            ON CONFLICT (user_id) DO UPDATE SET role = 'super_admin'
        ''', (super_admin_id, super_admin_id))
    
    # Tabella pagamenti
    cur.execute('''
        CREATE TABLE IF NOT EXISTS payments (
            payment_id SERIAL PRIMARY KEY,
            user_id BIGINT REFERENCES users(user_id),
            stripe_payment_id TEXT UNIQUE,
            amount INTEGER,
            currency TEXT DEFAULT 'eur',
            status TEXT,
            payment_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Tabella ticket supporto
    cur.execute('''
        CREATE TABLE IF NOT EXISTS support_tickets (
            ticket_id SERIAL PRIMARY KEY,
            user_id BIGINT REFERENCES users(user_id),
            category TEXT,
            description TEXT,
            status TEXT DEFAULT 'open',
            priority TEXT DEFAULT 'normal',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            resolved_at TIMESTAMP,
            assigned_to BIGINT
        )
    ''')
    
    # Tabella esperienze (per archiviare testimonianze significative)
    cur.execute('''
        CREATE TABLE IF NOT EXISTS experiences (
            experience_id SERIAL PRIMARY KEY,
            user_id BIGINT REFERENCES users(user_id),
            device_app_name TEXT,
            experience_text TEXT,
            rating INTEGER,
            approved BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            approved_by BIGINT,
            approved_at TIMESTAMP
        )
    ''')
    
    # Tabella log attività (per analytics)
    cur.execute('''
        CREATE TABLE IF NOT EXISTS activity_log (
            log_id SERIAL PRIMARY KEY,
            user_id BIGINT,
            action TEXT,
            details TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()
    logger.info("Database inizializzato con successo")


# =============================================================================
# FUNZIONI GESTIONE ADMIN DINAMICI
# =============================================================================

def is_admin(user_id: int) -> bool:
    """Verifica se l'utente è un amministratore (dal database)."""
    if user_id == SUPER_ADMIN_ID:
        return True
    
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute('SELECT user_id FROM admins WHERE user_id = %s', (user_id,))
    result = cur.fetchone()
    
    conn.close()
    return result is not None


def is_super_admin(user_id: int) -> bool:
    """Verifica se l'utente è un Super Admin."""
    return user_id in SUPER_ADMIN_IDS


def add_admin(user_id: int, added_by: int, username: str = None, first_name: str = None) -> bool:
    """
    Aggiunge un nuovo admin.
    Restituisce True se aggiunto, False se già esistente.
    """
    if not is_super_admin(added_by):
        logger.warning(f"Tentativo non autorizzato di aggiungere admin da {added_by}")
        return False
    
    conn = get_connection()
    cur = conn.cursor()
    
    try:
        cur.execute('''
            INSERT INTO admins (user_id, username, first_name, added_by)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (user_id) DO NOTHING
            RETURNING user_id
        ''', (user_id, username, first_name, added_by))
        
        result = cur.fetchone()
        conn.commit()
        conn.close()
        
        if result:
            logger.info(f"Admin {user_id} aggiunto da {added_by}")
            return True
        else:
            logger.info(f"Admin {user_id} già esistente")
            return False
    except Exception as e:
        conn.rollback()
        conn.close()
        logger.error(f"Errore aggiunta admin: {e}")
        return False


def remove_admin(user_id: int, removed_by: int) -> bool:
    """
    Rimuove un admin.
    Non si può rimuovere il Super Admin.
    """
    if not is_super_admin(removed_by):
        logger.warning(f"Tentativo non autorizzato di rimuovere admin da {removed_by}")
        return False
    
    if user_id in SUPER_ADMIN_IDS:
        logger.warning("Tentativo di rimuovere un Super Admin!")
        return False
    
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute('DELETE FROM admins WHERE user_id = %s AND role != %s', (user_id, 'super_admin'))
    deleted = cur.rowcount > 0
    
    conn.commit()
    conn.close()
    
    if deleted:
        logger.info(f"Admin {user_id} rimosso da {removed_by}")
    
    return deleted


def get_all_admins() -> list:
    """Recupera la lista di tutti gli admin."""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute('''
        SELECT a.*, u.username as current_username, u.first_name as current_first_name
        FROM admins a
        LEFT JOIN users u ON a.user_id = u.user_id
        ORDER BY a.added_at ASC
    ''')
    
    results = cur.fetchall()
    conn.close()
    
    return [dict(r) for r in results]


def get_admin_ids() -> list:
    """Recupera solo gli ID degli admin (per controlli veloci)."""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute('SELECT user_id FROM admins')
    results = cur.fetchall()
    
    conn.close()
    return [r['user_id'] for r in results]


# =============================================================================
# FUNZIONI UTENTI
# =============================================================================

def add_user(user_id: int, username: str = None, first_name: str = None, last_name: str = None):
    """Aggiunge un nuovo utente o aggiorna i dati se esiste già."""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute('''
        INSERT INTO users (user_id, username, first_name, last_name, last_activity)
        VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
        ON CONFLICT (user_id) DO UPDATE SET
            username = COALESCE(%s, users.username),
            first_name = COALESCE(%s, users.first_name),
            last_name = COALESCE(%s, users.last_name),
            last_activity = CURRENT_TIMESTAMP
    ''', (user_id, username, first_name, last_name, username, first_name, last_name))
    
    conn.commit()
    conn.close()
    logger.info(f"Utente {user_id} aggiunto/aggiornato")


def get_user(user_id: int) -> dict:
    """Recupera i dati di un utente."""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute('SELECT * FROM users WHERE user_id = %s', (user_id,))
    result = cur.fetchone()
    
    conn.close()
    return dict(result) if result else None


def is_subscribed(user_id: int) -> bool:
    """Verifica se un utente ha un abbonamento attivo."""
    user = get_user(user_id)
    
    if not user:
        return False
    
    if user['subscription_status'] != 'active':
        return False
    
    if user['subscription_end'] is None:
        return False
    
    # Confronta con la data odierna
    return user['subscription_end'] >= datetime.now().date()


# =============================================================================
# FUNZIONI PER SISTEMA APPROVAZIONE
# =============================================================================

def is_approved(user_id: int) -> bool:
    """Verifica se un utente è stato approvato (può abbonarsi)."""
    user = get_user(user_id)
    if not user:
        return False
    return user.get('approved', False)


def set_pending(user_id: int):
    """Imposta un utente come 'in attesa di approvazione'."""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute('''
        UPDATE users SET 
            subscription_status = 'pending',
            approved = FALSE
        WHERE user_id = %s
    ''', (user_id,))
    
    conn.commit()
    conn.close()
    logger.info(f"Utente {user_id} impostato come pending")


def approve_user(user_id: int, approved_by: int):
    """Approva un utente (può ora abbonarsi)."""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute('''
        UPDATE users SET 
            approved = TRUE,
            approved_at = CURRENT_TIMESTAMP,
            approved_by = %s,
            subscription_status = 'inactive'
        WHERE user_id = %s
    ''', (approved_by, user_id))
    
    conn.commit()
    conn.close()
    logger.info(f"Utente {user_id} approvato da {approved_by}")


def reject_user(user_id: int, rejected_by: int):
    """Rifiuta un utente."""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute('''
        UPDATE users SET 
            approved = FALSE,
            subscription_status = 'rejected',
            notes = CONCAT(COALESCE(notes, ''), ' | Rifiutato il ', CURRENT_DATE::TEXT, ' da ', %s::TEXT)
        WHERE user_id = %s
    ''', (rejected_by, user_id))
    
    conn.commit()
    conn.close()
    logger.info(f"Utente {user_id} rifiutato da {rejected_by}")


def get_pending_users() -> list:
    """Recupera tutti gli utenti in attesa di approvazione."""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute('''
        SELECT * FROM users 
        WHERE subscription_status = 'pending' 
        AND approved = FALSE
        ORDER BY joined_date ASC
    ''')
    
    results = cur.fetchall()
    conn.close()
    
    return [dict(r) for r in results]


def get_user_by_username(username: str) -> dict:
    """Recupera un utente dal suo username."""
    conn = get_connection()
    cur = conn.cursor()
    
    # Rimuovi @ se presente
    username = username.lstrip('@')
    
    cur.execute('SELECT * FROM users WHERE LOWER(username) = LOWER(%s)', (username,))
    result = cur.fetchone()
    
    conn.close()
    return dict(result) if result else None


def can_access_groups(user_id: int) -> bool:
    """
    Verifica se un utente può accedere ai gruppi premium.
    Deve essere: approvato E con abbonamento attivo.
    """
    user = get_user(user_id)
    if not user:
        return False
    
    is_user_approved = user.get('approved', False)
    is_user_subscribed = is_subscribed(user_id)
    
    return is_user_approved and is_user_subscribed


# =============================================================================
# FUNZIONI ABBONAMENTO
# =============================================================================

def get_subscription_info(user_id: int) -> dict:
    """Recupera le informazioni dettagliate sull'abbonamento."""
    user = get_user(user_id)
    
    if not user:
        return {'status': 'not_found'}
    
    is_active = is_subscribed(user_id)
    
    return {
        'status': 'active' if is_active else 'inactive',
        'start_date': user['subscription_start'],
        'end_date': user['subscription_end'],
        'stripe_customer_id': user['stripe_customer_id'],
        'total_payments': user['total_payments'],
        'approved': user.get('approved', False)
    }


def activate_subscription(user_id: int, stripe_customer_id: str, stripe_subscription_id: str = None, days: int = 30):
    """Attiva o rinnova l'abbonamento di un utente."""
    conn = get_connection()
    cur = conn.cursor()
    
    start_date = datetime.now().date()
    end_date = start_date + timedelta(days=days)
    
    cur.execute('''
        UPDATE users SET 
            subscription_status = 'active',
            subscription_start = %s,
            subscription_end = %s,
            stripe_customer_id = %s,
            stripe_subscription_id = %s,
            total_payments = total_payments + 1
        WHERE user_id = %s
    ''', (start_date, end_date, stripe_customer_id, stripe_subscription_id, user_id))
    
    conn.commit()
    conn.close()
    logger.info(f"Abbonamento attivato per utente {user_id} fino a {end_date}")


def deactivate_subscription(user_id: int):
    """Disattiva l'abbonamento di un utente (ma resta approvato!)."""
    conn = get_connection()
    cur = conn.cursor()
    
    # NOTA: Non tocchiamo 'approved', l'utente può ri-abbonarsi senza nuova richiesta
    cur.execute('''
        UPDATE users SET subscription_status = 'expired'
        WHERE user_id = %s
    ''', (user_id,))
    
    conn.commit()
    conn.close()
    logger.info(f"Abbonamento disattivato per utente {user_id}")


def get_expiring_subscriptions(days: int = 3) -> list:
    """Recupera gli utenti con abbonamento in scadenza nei prossimi X giorni."""
    conn = get_connection()
    cur = conn.cursor()
    
    target_date = datetime.now().date() + timedelta(days=days)
    
    cur.execute('''
        SELECT * FROM users 
        WHERE subscription_status = 'active' 
        AND subscription_end <= %s
        AND subscription_end >= CURRENT_DATE
    ''', (target_date,))
    
    results = cur.fetchall()
    conn.close()
    
    return [dict(r) for r in results]


def get_expired_subscriptions() -> list:
    """Recupera gli utenti con abbonamento scaduto."""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute('''
        SELECT * FROM users 
        WHERE subscription_status = 'active' 
        AND subscription_end < CURRENT_DATE
    ''')
    
    results = cur.fetchall()
    conn.close()
    
    return [dict(r) for r in results]


# =============================================================================
# FUNZIONI PAGAMENTI
# =============================================================================

def record_payment(user_id: int, stripe_payment_id: str, amount: int, status: str):
    """Registra un pagamento nel database."""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute('''
        INSERT INTO payments (user_id, stripe_payment_id, amount, status)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (stripe_payment_id) DO UPDATE SET status = %s
    ''', (user_id, stripe_payment_id, amount, status, status))
    
    conn.commit()
    conn.close()
    logger.info(f"Pagamento {stripe_payment_id} registrato per utente {user_id}")


# =============================================================================
# FUNZIONI TICKET SUPPORTO
# =============================================================================

def create_ticket(user_id: int, category: str, description: str, priority: str = 'normal') -> int:
    """Crea un nuovo ticket di supporto e restituisce l'ID."""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute('''
        INSERT INTO support_tickets (user_id, category, description, priority)
        VALUES (%s, %s, %s, %s)
        RETURNING ticket_id
    ''', (user_id, category, description, priority))
    
    ticket_id = cur.fetchone()['ticket_id']
    
    conn.commit()
    conn.close()
    logger.info(f"Ticket #{ticket_id} creato per utente {user_id}")
    
    return ticket_id


def get_open_tickets() -> list:
    """Recupera tutti i ticket aperti."""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute('''
        SELECT t.*, u.username, u.first_name 
        FROM support_tickets t
        JOIN users u ON t.user_id = u.user_id
        WHERE t.status = 'open'
        ORDER BY 
            CASE t.priority 
                WHEN 'critical' THEN 1 
                WHEN 'high' THEN 2 
                WHEN 'normal' THEN 3 
                WHEN 'low' THEN 4 
            END,
            t.created_at ASC
    ''')
    
    results = cur.fetchall()
    conn.close()
    
    return [dict(r) for r in results]


def close_ticket(ticket_id: int):
    """Chiude un ticket di supporto."""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute('''
        UPDATE support_tickets SET 
            status = 'closed',
            resolved_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE ticket_id = %s
    ''', (ticket_id,))
    
    conn.commit()
    conn.close()
    logger.info(f"Ticket #{ticket_id} chiuso")


# =============================================================================
# FUNZIONI STATISTICHE
# =============================================================================

def get_stats() -> dict:
    """Recupera statistiche generali per il dashboard admin."""
    conn = get_connection()
    cur = conn.cursor()
    
    # Utenti totali
    cur.execute('SELECT COUNT(*) as total FROM users')
    total_users = cur.fetchone()['total']
    
    # Abbonati attivi
    cur.execute('''
        SELECT COUNT(*) as active FROM users 
        WHERE subscription_status = 'active' AND subscription_end >= CURRENT_DATE
    ''')
    active_subscribers = cur.fetchone()['active']
    
    # Nuovi utenti ultimi 7 giorni
    cur.execute('''
        SELECT COUNT(*) as new FROM users 
        WHERE joined_date >= CURRENT_DATE - INTERVAL '7 days'
    ''')
    new_users_week = cur.fetchone()['new']
    
    # Ticket aperti
    cur.execute("SELECT COUNT(*) as open FROM support_tickets WHERE status = 'open'")
    open_tickets = cur.fetchone()['open']
    
    # Entrate del mese
    cur.execute('''
        SELECT COALESCE(SUM(amount), 0) as revenue FROM payments 
        WHERE status = 'succeeded' 
        AND payment_date >= DATE_TRUNC('month', CURRENT_DATE)
    ''')
    monthly_revenue = cur.fetchone()['revenue']
    
    # Utenti in attesa di approvazione
    cur.execute("SELECT COUNT(*) as pending FROM users WHERE subscription_status = 'pending' AND approved = FALSE")
    pending_users = cur.fetchone()['pending']
    
    # Numero admin
    cur.execute("SELECT COUNT(*) as admins FROM admins")
    total_admins = cur.fetchone()['admins']
    
    conn.close()
    
    return {
        'total_users': total_users,
        'active_subscribers': active_subscribers,
        'new_users_week': new_users_week,
        'open_tickets': open_tickets,
        'monthly_revenue': monthly_revenue / 100 if monthly_revenue else 0,
        'pending_users': pending_users,
        'total_admins': total_admins
    }


def log_activity(user_id: int, action: str, details: str = None):
    """Registra un'attività nel log."""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute('''
        INSERT INTO activity_log (user_id, action, details)
        VALUES (%s, %s, %s)
    ''', (user_id, action, details))
    
    conn.commit()
    conn.close()
