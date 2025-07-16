from flask import Blueprint, request, render_template, redirect, url_for, current_app, flash, jsonify
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField
from wtforms.validators import DataRequired, Regexp
from app.models import Lesson, User, Attempt
from app.services.twilio_service import TwilioService
from app.services.openai_service import OpenAIService
from app.services.scheduler import scheduler, add_job
from datetime import datetime, timedelta
import re
from twilio.base.exceptions import TwilioRestException
from app.database import db
import logging
import traceback
import os
import time
import socket
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

bp = Blueprint("admin", __name__)

# Inicializace služeb
try:
    twilio = TwilioService()
except Exception as e:
    logger.error(f"Chyba při inicializaci TwilioService: {str(e)}")
    twilio = None

try:
    openai = OpenAIService()
except Exception as e:
    logger.error(f"Chyba při inicializaci OpenAIService: {str(e)}")
    openai = None

def format_phone_number(phone: str) -> str:
    """Formátuje telefonní číslo do formátu E.164 s mezerami pro zobrazení."""
    # Odstraň všechny nečíselné znaky kromě mezer
    digits = re.sub(r'[^\d\s]', '', phone)
    
    # Pokud číslo začíná 00, nahraď to za +
    if digits.startswith('00'):
        digits = '+420' + digits[2:]
    
    # Pokud číslo začíná 0, nahraď to za +420
    if digits.startswith('0'):
        digits = '+420' + digits[1:]
    
    # Pokud číslo nezačíná +, přidej +420
    if not digits.startswith('+'):
        digits = '+420' + digits
    
    # Odstraň duplicitní +420
    if digits.startswith('+420420'):
        digits = '+420' + digits[7:]
    
    # Odstraň mezery
    digits = digits.replace(' ', '')
    
    # Přidej mezery po +420 a každých 3 číslech
    if len(digits) > 4:
        formatted = digits[:4] + ' '  # +420
        remaining = digits[4:]
        for i in range(0, len(remaining), 3):
            formatted += remaining[i:i+3] + ' '
        return formatted.strip()
    
    return digits

def format_phone_number_e164(phone: str) -> str:
    """Formátuje telefonní číslo do čistého E.164 formátu pro Twilio volání."""
    # Odstraň všechny nečíselné znaky
    digits = re.sub(r'[^\d+]', '', phone)
    
    # Pokud číslo začíná 00, nahraď to za +420
    if digits.startswith('00'):
        digits = '+420' + digits[2:]
    
    # Pokud číslo začíná 0, nahraď to za +420
    elif digits.startswith('0'):
        digits = '+420' + digits[1:]
    
    # Pokud číslo nezačíná +, přidej +420
    elif not digits.startswith('+'):
        digits = '+420' + digits
    
    # Odstraň duplicitní +420
    if digits.startswith('+420420'):
        digits = '+420' + digits[7:]
    
    return digits

class LessonForm(FlaskForm):
    title = StringField("Název", validators=[DataRequired()])
    language = SelectField("Jazyk", choices=[("cs", "Čeština"), ("en", "Angličtina")])
    script = TextAreaField("Skript", validators=[DataRequired()])
    questions = TextAreaField("Otázky (JSON)", validators=[DataRequired()])

class UserForm(FlaskForm):
    name = StringField("Jméno", validators=[DataRequired()])
    phone = StringField("Telefon", validators=[
        DataRequired(),
        Regexp(r'^(\+420|0)?[0-9]{9}$', message="Telefonní číslo musí být ve formátu +420XXXXXXXXX nebo 0XXXXXXXXX")
    ])
    language = SelectField("Jazyk", choices=[("cs", "Čeština"), ("en", "Angličtina")])
    detail = TextAreaField("Detail")

@bp.route("/")
def index():
    """Přesměruje na seznam uživatelů."""
    return redirect(url_for("admin.list_users"))

@bp.route("/lessons")
def list_lessons():
    """Zobrazí seznam lekcí."""
    lessons = Lesson.query.all()
    return render_template("lessons/list.html", lessons=lessons)

@bp.route("/lessons/new", methods=["GET", "POST"])
def new_lesson():
    """Vytvoří novou lekci."""
    form = LessonForm()
    if form.validate_on_submit():
        lesson = Lesson(
            title=form.title.data,
            language=form.language.data,
            script=form.script.data,
            questions=form.questions.data
        )
        db.session.add(lesson)
        db.session.commit()
        return redirect(url_for("admin.list_lessons"))
    return render_template("lessons/form.html", form=form)

@bp.route("/lessons/<int:id>/edit", methods=["GET", "POST"])
def edit_lesson(id):
    """Upraví existující lekci."""
    lesson = Lesson.query.get_or_404(id)
    form = LessonForm(obj=lesson)
    if form.validate_on_submit():
        lesson.title = form.title.data
        lesson.language = form.language.data
        lesson.script = form.script.data
        lesson.questions = form.questions.data
        db.session.commit()
        return redirect(url_for("admin.list_lessons"))
    return render_template("lessons/form.html", form=form)

@bp.route("/lessons/generate-questions", methods=["POST"])
def generate_questions():
    """Vygeneruje testovací otázky pomocí AI."""
    if not openai:
        return jsonify({"error": "OpenAI služba není dostupná. Zkontrolujte konfiguraci."}), 503
        
    script = request.json.get("script")
    language = request.json.get("language", "cs")
    
    if not script:
        return jsonify({"error": "Chybí text skriptu"}), 400
    
    try:
        questions = openai.generate_questions(script, language)
        if not questions:
            return jsonify({"error": "Nepodařilo se vygenerovat otázky. Zkontrolujte, zda máte správně nakonfigurovaný OpenAI API klíč."}), 500
        return jsonify({"questions": questions})
    except Exception as e:
        logger.error(f"Chyba při generování otázek: {str(e)}")
        return jsonify({"error": f"Chyba při generování otázek: {str(e)}"}), 500

@bp.route("/users", methods=['GET'])
def list_users():
    try:
        users = db.session.query(User).all()
        return render_template("users/list.html", users=users)
    except Exception as e:
        logger.error(f"Chyba při získávání uživatelů: {str(e)}")
        flash(f"Chyba při získávání uživatelů: {str(e)}", "error")
        return render_template("users/list.html", users=[])

@bp.route("/users", methods=['POST'])
def create_user():
    try:
        logger.info("Začínám vytvářet nového uživatele")
        form = UserForm()
        logger.info(f"Formulář validace: {form.validate_on_submit()}")
        logger.info(f"Formulář data: {form.data}")
        
        if form.validate_on_submit():
            logger.info("Formulář je validní, vytvářím uživatele")
            user = User(
                name=form.name.data,
                phone=format_phone_number(form.phone.data),
                language=form.language.data,
                detail=form.detail.data
            )
            logger.info(f"Vytvořen uživatel: {user.__dict__}")
            
            db.session.add(user)
            logger.info("Uživatel přidán do session")
            
            try:
                db.session.commit()
                logger.info("Uživatel úspěšně uložen do databáze")
                flash("Uživatel byl úspěšně vytvořen", "success")
                return redirect(url_for("admin.list_users"))
            except Exception as e:
                logger.error(f"Chyba při ukládání do databáze: {str(e)}")
                db.session.rollback()
                raise
                
        logger.warning("Formulář není validní")
        return render_template("users/form.html", form=form)
    except Exception as e:
        logger.error(f"Chyba při vytváření uživatele: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        flash(f"Chyba při vytváření uživatele: {str(e)}", "error")
        return render_template("users/form.html", form=form)

@bp.route("/users/<int:user_id>", methods=['GET'])
def get_user(user_id):
    try:
        user = db.session.query(User).get(user_id)
        if not user:
            flash("Uživatel nenalezen", "error")
            return redirect(url_for("admin.list_users"))
        form = UserForm(obj=user)
        return render_template("users/form.html", form=form, user=user)
    except Exception as e:
        logger.error(f"Chyba při získávání uživatele: {str(e)}")
        flash(f"Chyba při získávání uživatele: {str(e)}", "error")
        return redirect(url_for("admin.list_users"))

@bp.route("/users/<int:user_id>", methods=['PUT'])
def update_user(user_id):
    try:
        user = db.session.query(User).get(user_id)
        if not user:
            flash("Uživatel nenalezen", "error")
            return redirect(url_for("admin.list_users"))
        
        form = UserForm()
        if form.validate_on_submit():
            user.name = form.name.data
            user.phone = format_phone_number(form.phone.data)
            user.language = form.language.data
            user.detail = form.detail.data
            db.session.commit()
            flash("Uživatel byl úspěšně upraven", "success")
            return redirect(url_for("admin.list_users"))
        return render_template("users/form.html", form=form, user=user)
    except Exception as e:
        db.session.rollback()
        logger.error(f"Chyba při aktualizaci uživatele: {str(e)}")
        flash(f"Chyba při aktualizaci uživatele: {str(e)}", "error")
        return render_template("users/form.html", form=form, user=user)

@bp.route("/users/<int:user_id>", methods=['DELETE'])
def delete_user(user_id):
    try:
        user = db.session.query(User).get(user_id)
        if not user:
            flash("Uživatel nenalezen", "error")
            return redirect(url_for("admin.list_users"))
        
        db.session.delete(user)
        db.session.commit()
        flash("Uživatel byl úspěšně smazán", "success")
        return redirect(url_for("admin.list_users"))
    except Exception as e:
        db.session.rollback()
        logger.error(f"Chyba při mazání uživatele: {str(e)}")
        flash(f"Chyba při mazání uživatele: {str(e)}", "error")
        return redirect(url_for("admin.list_users"))

@bp.route("/users/new", methods=["GET", "POST"])
def new_user():
    """Vytvoří nového uživatele."""
    try:
        form = UserForm()
        if form.validate_on_submit():
            try:
                user = User(
                    name=form.name.data,
                    phone=format_phone_number(form.phone.data),
                    language=form.language.data,
                    detail=form.detail.data
                )
                db.session.add(user)
                db.session.commit()
                flash("Uživatel byl úspěšně vytvořen", "success")
                return redirect(url_for("admin.list_users"))
            except Exception as e:
                db.session.rollback()
                logger.error(f"Chyba při vytváření uživatele v databázi: {str(e)}")
                flash(f"Chyba při vytváření uživatele: {str(e)}", "error")
        return render_template("users/form.html", form=form)
    except Exception as e:
        logger.error(f"Kritická chyba v new_user endpointu: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        flash(f"Kritická chyba: {str(e)}", "error")
        return render_template("users/form.html", form=UserForm())

@bp.route("/users/<int:id>/edit", methods=["GET", "POST"])
def edit_user(id):
    """Upraví existujícího uživatele."""
    user = User.query.get_or_404(id)
    form = UserForm(obj=user)
    if form.validate_on_submit():
        user.name = form.name.data
        user.phone = format_phone_number(form.phone.data)
        user.language = form.language.data
        user.detail = form.detail.data
        db.session.commit()
        flash("Uživatel byl úspěšně upraven", "success")
        return redirect(url_for("admin.list_users"))
    return render_template("users/form.html", form=form)

@bp.route("/users/<int:user_id>/call", methods=["POST"])
def call_user(user_id):
    """Zavolá uživateli s vybranou lekcí."""
    try:
        logger.info(f"Začínám volání uživatele s ID: {user_id}")
        
        if not twilio:
            logger.error("Twilio služba není dostupná")
            flash("Twilio služba není dostupná. Zkontrolujte konfiguraci.", "error")
            return redirect(url_for("admin.list_users"))
            
        user = User.query.get_or_404(user_id)
        logger.info(f"Našel jsem uživatele: {user.name} (ID: {user.id})")
        logger.info(f"Telefonní číslo uživatele: {user.phone}")
        
        # Formátování telefonního čísla pro Twilio (bez mezer)
        formatted_phone = format_phone_number_e164(user.phone)
        logger.info(f"Formátované telefonní číslo pro Twilio: {formatted_phone}")
        
        # Najdi nejnovější lekci v jazyce uživatele
        lesson = Lesson.query.filter_by(language=user.language).order_by(Lesson.created_at.desc()).first()
        
        if not lesson:
            logger.error(f"Není k dispozici žádná lekce v jazyce {user.language}")
            flash("Není k dispozici žádná lekce v jazyce uživatele", "error")
            return redirect(url_for("admin.list_users"))
            
        logger.info(f"Našel jsem lekci: {lesson.title} (ID: {lesson.id})")
        
        try:
            # Vytvoř nový pokus v transakci
            with db.session.begin_nested():
                attempt = Attempt(
                    user_id=user.id,
                    lesson_id=lesson.id,
                    next_due=datetime.utcnow()
                )
                logger.info(f"Vytvářím nový pokus pro uživatele {user.id} a lekci {lesson.id}")
                logger.info(f"Attempt data: user_id={attempt.user_id}, lesson_id={attempt.lesson_id}, next_due={attempt.next_due}")
                db.session.add(attempt)
            
            # Commit transakce
            db.session.commit()
            logger.info(f"Pokus byl úspěšně vytvořen s ID: {attempt.id}")
            logger.info(f"Ověřuji data pokusu po vytvoření:")
            logger.info(f"- user_id: {attempt.user_id}")
            logger.info(f"- lesson_id: {attempt.lesson_id}")
            logger.info(f"- next_due: {attempt.next_due}")
            
            # Zavolej uživateli
            webhook_url = f"{current_app.config['WEBHOOK_BASE_URL']}/voice/?attempt_id={attempt.id}"
            logger.info(f"Volám uživatele {formatted_phone} s webhook URL: {webhook_url}")
            
            call_result = twilio.call(formatted_phone, webhook_url)
            logger.info(f"Volání bylo úspěšně zahájeno: {call_result}")
            
            flash(f"Volání uživateli {user.name} bylo zahájeno", "success")
        except TwilioRestException as e:
            db.session.rollback()
            logger.error(f"Twilio chyba při volání: {str(e)}")
            if "není ověřeno" in str(e):
                flash(f"Nelze zavolat na číslo {formatted_phone}, protože není ověřeno. Pro zkušební účet Twilio je nutné nejprve ověřit číslo na https://www.twilio.com/console/phone-numbers/verified", "error")
            else:
                flash(f"Chyba při volání: {str(e)}", "error")
        except Exception as e:
            db.session.rollback()
            logger.error(f"Neočekávaná chyba při volání: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            flash(f"Neočekávaná chyba: {str(e)}", "error")
        
        return redirect(url_for("admin.list_users"))
    except Exception as e:
        logger.error(f"Kritická chyba při volání uživatele: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        flash(f"Kritická chyba při volání: {str(e)}", "error")
        return redirect(url_for("admin.list_users"))

@bp.route('/network-test')
def network_test():
    """Diagnostický endpoint pro testování síťového připojení."""
    results = {}
    
    # Test DNS resoluce
    try:
        socket.gethostbyname('api.twilio.com')
        results['dns_twilio'] = 'OK'
    except Exception as e:
        results['dns_twilio'] = f'CHYBA: {str(e)}'
    
    try:
        socket.gethostbyname('api.openai.com')
        results['dns_openai'] = 'OK'
    except Exception as e:
        results['dns_openai'] = f'CHYBA: {str(e)}'
    
    # Test HTTP připojení
    try:
        response = requests.get('https://httpbin.org/ip', timeout=10)
        results['http_test'] = f'OK - IP: {response.json().get("origin", "unknown")}'
    except Exception as e:
        results['http_test'] = f'CHYBA: {str(e)}'
    
    return jsonify(results)

@bp.route('/db-test')
def db_test():
    """Test endpoint pro ověření databáze."""
    results = {}
    
    try:
        # Test připojení k databázi
        db.session.execute('SELECT 1')
        results['db_connection'] = 'OK'
    except Exception as e:
        results['db_connection'] = f'CHYBA: {str(e)}'
    
    try:
        # Test tabulky User
        user_count = User.query.count()
        results['user_table'] = f'OK - {user_count} uživatelů'
    except Exception as e:
        results['user_table'] = f'CHYBA: {str(e)}'
    
    try:
        # Test tabulky Lesson
        lesson_count = Lesson.query.count()
        results['lesson_table'] = f'OK - {lesson_count} lekcí'
    except Exception as e:
        results['lesson_table'] = f'CHYBA: {str(e)}'
    
    return jsonify(results) 