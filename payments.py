"""
INTEGRAZIONE PAGAMENTI STRIPE - OPERAZIONE RISVEGLIO
=====================================================
Questo modulo gestisce tutti i pagamenti tramite Stripe.
"""

import stripe
from config import STRIPE_SECRET_KEY, STRIPE_PRICE_ID, STRIPE_WEBHOOK_SECRET
import logging

logger = logging.getLogger(__name__)

# Configura la chiave API di Stripe
stripe.api_key = STRIPE_SECRET_KEY


def create_checkout_session(user_id: int, user_email: str = None) -> str:
    """
    Crea una sessione di checkout Stripe e restituisce l'URL per il pagamento.
    
    Args:
        user_id: ID Telegram dell'utente
        user_email: Email dell'utente (opzionale)
    
    Returns:
        URL della pagina di checkout Stripe
    """
    try:
        # Crea la sessione di checkout
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price': STRIPE_PRICE_ID,
                'quantity': 1,
            }],
            mode='subscription',  # Per abbonamenti ricorrenti
            # mode='payment',  # Usa questo per pagamenti singoli
            
            # URL di ritorno dopo il pagamento
            success_url=f'https://t.me/OperazioneRisveglioBot?start=payment_success_{user_id}',
            cancel_url=f'https://t.me/OperazioneRisveglioBot?start=payment_cancelled',
            
            # Metadati per identificare l'utente
            metadata={
                'telegram_user_id': str(user_id),
            },
            
            # Pre-compila l'email se disponibile
            customer_email=user_email,
            
            # Permetti codici promozionali
            allow_promotion_codes=True,
            
            # Raccogli indirizzo di fatturazione
            billing_address_collection='auto',
        )
        
        logger.info(f"Checkout session creata per utente {user_id}: {session.id}")
        return session.url
        
    except stripe.error.StripeError as e:
        logger.error(f"Errore Stripe nella creazione checkout: {e}")
        raise


def create_customer(user_id: int, email: str, name: str = None) -> str:
    """
    Crea un cliente Stripe e restituisce il customer_id.
    """
    try:
        customer = stripe.Customer.create(
            email=email,
            name=name,
            metadata={
                'telegram_user_id': str(user_id),
            }
        )
        logger.info(f"Cliente Stripe creato: {customer.id}")
        return customer.id
        
    except stripe.error.StripeError as e:
        logger.error(f"Errore nella creazione cliente: {e}")
        raise


def get_customer_portal_url(customer_id: str) -> str:
    """
    Crea un link al portale clienti Stripe dove l'utente può gestire
    il proprio abbonamento (cancellare, aggiornare carta, ecc.)
    """
    try:
        session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url='https://t.me/OperazioneRisveglioBot',
        )
        return session.url
        
    except stripe.error.StripeError as e:
        logger.error(f"Errore nella creazione portale: {e}")
        raise


def cancel_subscription(subscription_id: str) -> bool:
    """
    Cancella un abbonamento Stripe.
    """
    try:
        stripe.Subscription.delete(subscription_id)
        logger.info(f"Abbonamento {subscription_id} cancellato")
        return True
        
    except stripe.error.StripeError as e:
        logger.error(f"Errore nella cancellazione: {e}")
        return False


def get_subscription_status(subscription_id: str) -> dict:
    """
    Recupera lo stato di un abbonamento.
    """
    try:
        subscription = stripe.Subscription.retrieve(subscription_id)
        return {
            'status': subscription.status,
            'current_period_end': subscription.current_period_end,
            'cancel_at_period_end': subscription.cancel_at_period_end,
        }
        
    except stripe.error.StripeError as e:
        logger.error(f"Errore nel recupero abbonamento: {e}")
        return None


def verify_webhook_signature(payload: bytes, sig_header: str) -> dict:
    """
    Verifica la firma del webhook Stripe per sicurezza.
    
    Args:
        payload: Body della richiesta
        sig_header: Header Stripe-Signature
    
    Returns:
        Evento Stripe verificato
    """
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
        return event
        
    except ValueError as e:
        logger.error(f"Payload webhook non valido: {e}")
        raise
    except stripe.error.SignatureVerificationError as e:
        logger.error(f"Firma webhook non valida: {e}")
        raise


def handle_webhook_event(event: dict) -> dict:
    """
    Gestisce gli eventi webhook di Stripe.
    
    Restituisce un dizionario con le azioni da compiere.
    """
    event_type = event['type']
    data = event['data']['object']
    
    result = {
        'action': None,
        'user_id': None,
        'details': {}
    }
    
    # Pagamento completato con successo
    if event_type == 'checkout.session.completed':
        result['action'] = 'activate_subscription'
        result['user_id'] = int(data['metadata'].get('telegram_user_id', 0))
        result['details'] = {
            'customer_id': data['customer'],
            'subscription_id': data.get('subscription'),
            'amount_total': data['amount_total'],
        }
        logger.info(f"Checkout completato per utente {result['user_id']}")
    
    # Pagamento ricorrente riuscito
    elif event_type == 'invoice.payment_succeeded':
        if data.get('subscription'):
            result['action'] = 'renew_subscription'
            # Recupera l'user_id dal customer
            customer = stripe.Customer.retrieve(data['customer'])
            result['user_id'] = int(customer.metadata.get('telegram_user_id', 0))
            result['details'] = {
                'amount': data['amount_paid'],
                'subscription_id': data['subscription'],
            }
            logger.info(f"Rinnovo riuscito per utente {result['user_id']}")
    
    # Pagamento fallito
    elif event_type == 'invoice.payment_failed':
        customer = stripe.Customer.retrieve(data['customer'])
        result['action'] = 'payment_failed'
        result['user_id'] = int(customer.metadata.get('telegram_user_id', 0))
        result['details'] = {
            'attempt_count': data.get('attempt_count', 1),
        }
        logger.warning(f"Pagamento fallito per utente {result['user_id']}")
    
    # Abbonamento cancellato
    elif event_type == 'customer.subscription.deleted':
        customer = stripe.Customer.retrieve(data['customer'])
        result['action'] = 'cancel_subscription'
        result['user_id'] = int(customer.metadata.get('telegram_user_id', 0))
        logger.info(f"Abbonamento cancellato per utente {result['user_id']}")
    
    return result
