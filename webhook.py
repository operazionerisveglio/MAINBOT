"""
WEBHOOK SERVER - OPERAZIONE RISVEGLIO
======================================
Server per ricevere i webhook da Stripe e attivare gli abbonamenti.

Questo file crea un piccolo server web che ascolta le notifiche da Stripe.
Quando un pagamento va a buon fine, attiva l'abbonamento dell'utente.

Per avviare: python webhook.py
"""

from aiohttp import web
import logging
from payments import verify_webhook_signature, handle_webhook_event
from database import activate_subscription, deactivate_subscription, record_payment

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def stripe_webhook(request):
    """
    Endpoint che riceve i webhook da Stripe.
    
    Configurazione su Stripe:
    1. Vai su dashboard.stripe.com > Sviluppatori > Webhook
    2. Clicca "Aggiungi endpoint"
    3. URL: https://tuo-dominio.railway.app/webhook
    4. Seleziona gli eventi:
       - checkout.session.completed
       - invoice.payment_succeeded
       - invoice.payment_failed
       - customer.subscription.deleted
    """
    # Leggi il body della richiesta
    payload = await request.read()
    sig_header = request.headers.get('Stripe-Signature')
    
    try:
        # Verifica la firma del webhook
        event = verify_webhook_signature(payload, sig_header)
        
        # Gestisci l'evento
        result = handle_webhook_event(event)
        
        if result['action'] == 'activate_subscription':
            # Attiva l'abbonamento
            activate_subscription(
                user_id=result['user_id'],
                stripe_customer_id=result['details']['customer_id'],
                stripe_subscription_id=result['details'].get('subscription_id')
            )
            
            # Registra il pagamento
            record_payment(
                user_id=result['user_id'],
                stripe_payment_id=event['id'],
                amount=result['details']['amount_total'],
                status='succeeded'
            )
            
            logger.info(f"Abbonamento attivato per utente {result['user_id']}")
        
        elif result['action'] == 'renew_subscription':
            # Rinnova l'abbonamento
            activate_subscription(
                user_id=result['user_id'],
                stripe_customer_id=result['details'].get('customer_id', ''),
                stripe_subscription_id=result['details'].get('subscription_id')
            )
            logger.info(f"Abbonamento rinnovato per utente {result['user_id']}")
        
        elif result['action'] == 'cancel_subscription':
            # Disattiva l'abbonamento
            deactivate_subscription(result['user_id'])
            logger.info(f"Abbonamento cancellato per utente {result['user_id']}")
        
        elif result['action'] == 'payment_failed':
            # Logga il pagamento fallito
            logger.warning(f"Pagamento fallito per utente {result['user_id']}")
            # Potresti voler inviare una notifica all'utente
        
        return web.Response(status=200)
        
    except ValueError as e:
        logger.error(f"Payload non valido: {e}")
        return web.Response(status=400)
    except Exception as e:
        logger.error(f"Errore webhook: {e}")
        return web.Response(status=500)


async def health_check(request):
    """Endpoint per verificare che il server sia attivo."""
    return web.Response(text="OK", status=200)


def create_app():
    """Crea l'applicazione web."""
    app = web.Application()
    app.router.add_post('/webhook', stripe_webhook)
    app.router.add_get('/health', health_check)
    return app


if __name__ == '__main__':
    import os
    port = int(os.getenv('PORT', 8080))
    
    app = create_app()
    logger.info(f"Webhook server avviato sulla porta {port}")
    web.run_app(app, port=port)
