"""
GESTIONE DATABASE - OPERAZIONE RISVEGLIO
=========================================
Questo modulo gestisce tutte le operazioni sul database PostgreSQL.
Include il sistema di consenso/liberatoria con firma elettronica OTP.
"""

import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta
from config import DATABASE_URL, SUPER_ADMIN_IDS
import logging
import random
import string

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
    
    # Tabella utenti
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
            approved_by BIGINT,
            consent_completed BOOLEAN DEFAULT FALSE,
            consent_completed_at TIMESTAMP
        )
    ''')
    
    # Aggiungi colonne se non esistono (per database esistenti)
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
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name='users' AND column_name='consent_completed') THEN
                ALTER TABLE users ADD COLUMN consent_completed BOOLEAN DEFAULT FALSE;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name='users' AND column_name='consent_completed_at') THEN
                ALTER TABLE users ADD COLUMN consent_completed_at TIMESTAMP;
            END IF;
        END $$;
    ''')
    
    # ==========================================================================
    # NUOVA TABELLA: Consenso/Liberatoria con firma elettronica
    # ==========================================================================
    cur.execute('''
        CREATE TABLE IF NOT EXISTS user_consents (
            consent_id SERIAL PRIMARY KEY,
            user_id BIGINT REFERENCES users(user_id),
            
            -- Dati anagrafici compilati dall'utente
            full_name TEXT NOT NULL,
            birth_date DATE NOT NULL,
            birth_place TEXT NOT NULL,
            residence TEXT NOT NULL,
            
            -- Dati di verifica firma elettronica
            otp_code TEXT NOT NULL,
            otp_generated_at TIMESTAMP NOT NULL,
            otp_verified_at TIMESTAMP,
            otp_attempts INTEGER DEFAULT 0,
            
            -- Dati probatori
            telegram_user_id BIGINT NOT NULL,
            telegram_username TEXT,
            ip_address TEXT,
            user_agent TEXT,
            
            -- Timestamp e stato
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            confirmed_at TIMESTAMP,
            is_confirmed BOOLEAN DEFAULT FALSE,
            
            -- Versione del documento accettato
            document_version TEXT DEFAULT '1.0',
            document_hash TEXT,
            
            -- Metadati aggiuntivi
            consent_metadata JSONB DEFAULT '{}'::jsonb,
            
            UNIQUE(user_id)
        )
    ''')
    
    # Indice per ricerche veloci
    cur.execute('''
        CREATE INDEX IF NOT EXISTS idx_user_consents_user_id ON user_consents(user_id);
        CREATE INDEX IF NOT EXISTS idx_user_consents_confirmed ON user_consents(is_confirmed);
    ''')
    
    # ==========================================================================
    # TABELLA: Log OTP (per tracciare tutti i tentativi)
    # ==========================================================================
    cur.execute('''
        CREATE TABLE IF NOT EXISTS otp_log (
            log_id SERIAL PRIMARY KEY,
            user_id BIGINT,
            otp_code TEXT,
            action TEXT,
            success BOOLEAN,
            ip_address TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # ==========================================================================
    # TABELLA: Amministratori dinamici
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
    
    # Assicurati che i Super Admin siano sempre presenti
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
    
    # Tabella esperienze
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
    
    # Tabella log attività
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
# FUNZIONI GESTIONE CONSENSO/LIBERATORIA
# =============================================================================

def generate_otp(length: int = 6) -> str:
    """Genera un codice OTP numerico."""
    return ''.join(random.choices(string.digits, k=length))


def create_consent_record(
    user_id: int,
    full_name: str,
    birth_date: str,
    birth_place: str,
    residence: str,
    telegram_username: str = None,
    ip_address: str = None
) -> dict:
    """
    Crea un record di consenso e genera un OTP.
    Restituisce il codice OTP generato.
    """
    conn = get_connection()
    cur = conn.cursor()
    
    otp_code = generate_otp(6)
    otp_generated_at = datetime.now()
    
    # Hash del documento per tracciabilità
    import hashlib
    document_content = f"CONSENSO_V1.0_{user_id}_{otp_generated_at.isoformat()}"
    document_hash = hashlib.sha256(document_content.encode()).hexdigest()
    
    try:
        # Elimina eventuali record precedenti non confermati
        cur.execute('''
            DELETE FROM user_consents 
            WHERE user_id = %s AND is_confirmed = FALSE
        ''', (user_id,))
        
        # Inserisci nuovo record
        cur.execute('''
            INSERT INTO user_consents (
                user_id, full_name, birth_date, birth_place, residence,
                otp_code, otp_generated_at, telegram_user_id, telegram_username,
                ip_address, document_hash
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING consent_id
        ''', (
            user_id, full_name, birth_date, birth_place, residence,
            otp_code, otp_generated_at, user_id, telegram_username,
            ip_address, document_hash
        ))
        
        consent_id = cur.fetchone()['consent_id']
        
        # Log dell'operazione
        cur.execute('''
            INSERT INTO otp_log (user_id, otp_code, action, success, ip_address)
            VALUES (%s, %s, 'generated', TRUE, %s)
        ''', (user_id, otp_code, ip_address))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Consenso creato per utente {user_id}, consent_id: {consent_id}")
        
        return {
            'success': True,
            'consent_id': consent_id,
            'otp_code': otp_code,
            'expires_at': otp_generated_at + timedelta(minutes=10)
        }
        
    except Exception as e:
        conn.rollback()
        conn.close()
        logger.error(f"Errore creazione consenso: {e}")
        return {'success': False, 'error': str(e)}


def verify_otp(user_id: int, otp_input: str, ip_address: str = None) -> dict:
    """
    Verifica il codice OTP inserito dall'utente.
    """
    conn = get_connection()
    cur = conn.cursor()
    
    try:
        # Recupera il record di consenso
        cur.execute('''
            SELECT * FROM user_consents 
            WHERE user_id = %s AND is_confirmed = FALSE
            ORDER BY created_at DESC LIMIT 1
        ''', (user_id,))
        
        consent = cur.fetchone()
        
        if not consent:
            conn.close()
            return {'success': False, 'error': 'Nessun consenso in attesa trovato'}
        
        # Verifica scadenza OTP (10 minuti)
        otp_generated = consent['otp_generated_at']
        if datetime.now() - otp_generated > timedelta(minutes=10):
            # Log tentativo fallito
            cur.execute('''
                INSERT INTO otp_log (user_id, otp_code, action, success, ip_address)
                VALUES (%s, %s, 'verify_expired', FALSE, %s)
            ''', (user_id, otp_input, ip_address))
            conn.commit()
            conn.close()
            return {'success': False, 'error': 'Codice OTP scaduto. Richiedi un nuovo codice.'}
        
        # Verifica numero tentativi (max 5)
        if consent['otp_attempts'] >= 5:
            cur.execute('''
                INSERT INTO otp_log (user_id, otp_code, action, success, ip_address)
                VALUES (%s, %s, 'verify_max_attempts', FALSE, %s)
            ''', (user_id, otp_input, ip_address))
            conn.commit()
            conn.close()
            return {'success': False, 'error': 'Troppi tentativi. Richiedi un nuovo codice.'}
        
        # Incrementa tentativi
        cur.execute('''
            UPDATE user_consents SET otp_attempts = otp_attempts + 1
            WHERE consent_id = %s
        ''', (consent['consent_id'],))
        
        # Verifica OTP
        if otp_input.strip() != consent['otp_code']:
            cur.execute('''
                INSERT INTO otp_log (user_id, otp_code, action, success, ip_address)
                VALUES (%s, %s, 'verify_wrong', FALSE, %s)
            ''', (user_id, otp_input, ip_address))
            conn.commit()
            conn.close()
            remaining = 5 - (consent['otp_attempts'] + 1)
            return {'success': False, 'error': f'Codice OTP errato. Tentativi rimanenti: {remaining}'}
        
        # OTP corretto - conferma il consenso
        confirmed_at = datetime.now()
        
        cur.execute('''
            UPDATE user_consents SET 
                is_confirmed = TRUE,
                confirmed_at = %s,
                otp_verified_at = %s,
                ip_address = COALESCE(ip_address, %s)
            WHERE consent_id = %s
        ''', (confirmed_at, confirmed_at, ip_address, consent['consent_id']))
        
        # Aggiorna lo stato dell'utente
        cur.execute('''
            UPDATE users SET 
                consent_completed = TRUE,
                consent_completed_at = %s
            WHERE user_id = %s
        ''', (confirmed_at, user_id))
        
        # Log successo
        cur.execute('''
            INSERT INTO otp_log (user_id, otp_code, action, success, ip_address)
            VALUES (%s, %s, 'verify_success', TRUE, %s)
        ''', (user_id, otp_input, ip_address))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Consenso confermato per utente {user_id}")
        
        return {
            'success': True,
            'consent_id': consent['consent_id'],
            'confirmed_at': confirmed_at,
            'full_name': consent['full_name']
        }
        
    except Exception as e:
        conn.rollback()
        conn.close()
        logger.error(f"Errore verifica OTP: {e}")
        return {'success': False, 'error': str(e)}


def get_user_consent(user_id: int) -> dict:
    """Recupera il consenso confermato di un utente."""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute('''
        SELECT * FROM user_consents 
        WHERE user_id = %s AND is_confirmed = TRUE
        ORDER BY confirmed_at DESC LIMIT 1
    ''', (user_id,))
    
    result = cur.fetchone()
    conn.close()
    
    return dict(result) if result else None


def has_valid_consent(user_id: int) -> bool:
    """Verifica se l'utente ha un consenso valido confermato."""
    consent = get_user_consent(user_id)
    return consent is not None and consent.get('is_confirmed', False)


def get_pending_consent(user_id: int) -> dict:
    """Recupera un consenso in attesa di conferma."""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute('''
        SELECT * FROM user_consents 
        WHERE user_id = %s AND is_confirmed = FALSE
        ORDER BY created_at DESC LIMIT 1
    ''', (user_id,))
    
    result = cur.fetchone()
    conn.close()
    
    return dict(result) if result else None


def regenerate_otp(user_id: int, ip_address: str = None) -> dict:
    """
    Rigenera un nuovo OTP per un consenso esistente.
    """
    conn = get_connection()
    cur = conn.cursor()
    
    try:
        # Verifica che esista un consenso in attesa
        cur.execute('''
            SELECT * FROM user_consents 
            WHERE user_id = %s AND is_confirmed = FALSE
            ORDER BY created_at DESC LIMIT 1
        ''', (user_id,))
        
        consent = cur.fetchone()
        
        if not consent:
            conn.close()
            return {'success': False, 'error': 'Nessun consenso in attesa trovato'}
        
        # Genera nuovo OTP
        new_otp = generate_otp(6)
        otp_generated_at = datetime.now()
        
        cur.execute('''
            UPDATE user_consents SET 
                otp_code = %s,
                otp_generated_at = %s,
                otp_attempts = 0
            WHERE consent_id = %s
        ''', (new_otp, otp_generated_at, consent['consent_id']))
        
        # Log
        cur.execute('''
            INSERT INTO otp_log (user_id, otp_code, action, success, ip_address)
            VALUES (%s, %s, 'regenerated', TRUE, %s)
        ''', (user_id, new_otp, ip_address))
        
        conn.commit()
        conn.close()
        
        logger.info(f"OTP rigenerato per utente {user_id}")
        
        return {
            'success': True,
            'otp_code': new_otp,
            'expires_at': otp_generated_at + timedelta(minutes=10)
        }
        
    except Exception as e:
        conn.rollback()
        conn.close()
        logger.error(f"Errore rigenerazione OTP: {e}")
        return {'success': False, 'error': str(e)}


def get_consent_stats() -> dict:
    """Statistiche sui consensi per il pannello admin."""
    conn = get_connection()
    cur = conn.cursor()
    
    # Totale consensi confermati
    cur.execute("SELECT COUNT(*) as total FROM user_consents WHERE is_confirmed = TRUE")
    total_confirmed = cur.fetchone()['total']
    
    # Consensi in attesa
    cur.execute("SELECT COUNT(*) as total FROM user_consents WHERE is_confirmed = FALSE")
    total_pending = cur.fetchone()['total']
    
    # Consensi oggi
    cur.execute('''
        SELECT COUNT(*) as total FROM user_consents 
        WHERE is_confirmed = TRUE AND DATE(confirmed_at) = CURRENT_DATE
    ''')
    today_confirmed = cur.fetchone()['total']
    
    conn.close()
    
    return {
        'total_confirmed': total_confirmed,
        'total_pending': total_pending,
        'today_confirmed': today_confirmed
    }


# =============================================================================
# FUNZIONI GESTIONE ADMIN DINAMICI
# =============================================================================

def is_admin(user_id: int) -> bool:
    """Verifica se l'utente è un amministratore (dal database)."""
    if user_id in SUPER_ADMIN_IDS:
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
    """Verifica se un utente è stato approvato (può compilare il consenso)."""
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
    """
    Approva un utente.
    L'utente dovrà poi compilare il form di consenso prima di poter abbonarsi.
    """
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute('''
        UPDATE users SET 
            approved = TRUE,
            approved_at = CURRENT_TIMESTAMP,
            approved_by = %s,
            subscription_status = 'awaiting_consent'
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


def can_subscribe(user_id: int) -> bool:
    """
    Verifica se un utente può procedere all'abbonamento.
    Deve essere: approvato E con consenso completato.
    """
    user = get_user(user_id)
    if not user:
        return False
    
    is_user_approved = user.get('approved', False)
    has_consent = user.get('consent_completed', False)
    
    return is_user_approved and has_consent


def can_access_groups(user_id: int) -> bool:
    """
    Verifica se un utente può accedere ai gruppi premium.
    Deve essere: approvato E con consenso completato E con abbonamento attivo.
    """
    user = get_user(user_id)
    if not user:
        return False
    
    is_user_approved = user.get('approved', False)
    has_consent = user.get('consent_completed', False)
    is_user_subscribed = is_subscribed(user_id)
    
    return is_user_approved and has_consent and is_user_subscribed


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
        'approved': user.get('approved', False),
        'consent_completed': user.get('consent_completed', False)
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
    """Disattiva l'abbonamento di un utente (ma resta approvato e con consenso!)."""
    conn = get_connection()
    cur = conn.cursor()
    
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
    
    # Utenti in attesa di consenso
    cur.execute("SELECT COUNT(*) as awaiting FROM users WHERE subscription_status = 'awaiting_consent' AND consent_completed = FALSE")
    awaiting_consent = cur.fetchone()['awaiting']
    
    # Numero admin
    cur.execute("SELECT COUNT(*) as admins FROM admins")
    total_admins = cur.fetchone()['admins']
    
    # Consensi confermati
    cur.execute("SELECT COUNT(*) as consents FROM user_consents WHERE is_confirmed = TRUE")
    total_consents = cur.fetchone()['consents']
    
    conn.close()
    
    return {
        'total_users': total_users,
        'active_subscribers': active_subscribers,
        'new_users_week': new_users_week,
        'open_tickets': open_tickets,
        'monthly_revenue': monthly_revenue / 100 if monthly_revenue else 0,
        'pending_users': pending_users,
        'awaiting_consent': awaiting_consent,
        'total_admins': total_admins,
        'total_consents': total_consents
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
