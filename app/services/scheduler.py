from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
from typing import List
import logging
import os

from app.models import Attempt, User
from app.services.twilio_service import TwilioService
from flask import current_app

logger = logging.getLogger(__name__)

# Vytvoření globálního scheduleru s konfigurací
scheduler = BackgroundScheduler(
    timezone='UTC',
    job_defaults={
        'coalesce': True,
        'max_instances': 1
    }
)

class SchedulerService:
    def __init__(self, db_session, twilio_service: TwilioService):
        self.db = db_session
        self.twilio = twilio_service
    
    def start(self):
        """Spustí plánovač."""
        try:
            scheduler.add_job(
                self._check_due_attempts,
                IntervalTrigger(minutes=5),
                id="check_due_attempts",
                replace_existing=True
            )
            if not scheduler.running:
                scheduler.start()
                logger.info("Scheduler byl úspěšně spuštěn")
        except Exception as e:
            logger.error(f"Chyba při spouštění scheduleru: {str(e)}")
            raise
    
    def stop(self):
        """Zastaví plánovač."""
        try:
            if scheduler.running:
                scheduler.shutdown()
                logger.info("Scheduler byl úspěšně zastaven")
        except Exception as e:
            logger.error(f"Chyba při zastavování scheduleru: {str(e)}")
            raise
    
    def _check_due_attempts(self):
        """Zkontroluje a spustí hovory pro opakování lekcí."""
        try:
            now = datetime.utcnow()
            
            # Najdi pokusy, které jsou na řadě
            stmt = select(Attempt).where(Attempt.next_due <= now)
            attempts = self.db.execute(stmt).scalars().all()
            
            for attempt in attempts:
                # Získej uživatele
                user = self.db.get(User, attempt.user_id)
                if not user:
                    continue
                
                # Spusť hovor
                base_url = current_app.config['WEBHOOK_BASE_URL'].rstrip('/')
                webhook_url = f"{base_url}/voice/?attempt_id={attempt.id}"
                self.twilio.call(user.phone, webhook_url)
                
            logger.info(f"Kontrola pokusů dokončena, nalezeno {len(attempts)} pokusů")
        except Exception as e:
            logger.error(f"Chyba při kontrole pokusů: {str(e)}")
            raise

def init_scheduler():
    """Inicializuje a spustí scheduler."""
    try:
        if not scheduler.running:
            scheduler.start()
            logger.info("Scheduler byl úspěšně inicializován a spuštěn")
    except Exception as e:
        logger.error(f"Chyba při inicializaci scheduleru: {str(e)}")
        raise

def add_job(func, trigger, **trigger_args):
    """Přidá novou úlohu do scheduleru."""
    try:
        scheduler.add_job(func, trigger, **trigger_args)
        logger.info(f"Úloha byla úspěšně přidána do scheduleru: {func.__name__}")
    except Exception as e:
        logger.error(f"Chyba při přidávání úlohy do scheduleru: {str(e)}")
        raise

def remove_job(job_id):
    """Odstraní úlohu ze scheduleru."""
    try:
        scheduler.remove_job(job_id)
        logger.info(f"Úloha byla úspěšně odstraněna ze scheduleru: {job_id}")
    except Exception as e:
        logger.error(f"Chyba při odstraňování úlohy ze scheduleru: {str(e)}")
        raise

def shutdown_scheduler():
    """Vypne scheduler."""
    try:
        if scheduler.running:
            scheduler.shutdown()
            logger.info("Scheduler byl úspěšně vypnut")
    except Exception as e:
        logger.error(f"Chyba při vypínání scheduleru: {str(e)}")
        raise 