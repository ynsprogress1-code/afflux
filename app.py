#!/usr/bin/env python3
"""
Afflux Enterprise v3.0 — Logiciel SaaS Professionnel
Plateforme d'affiliation intelligente avec agents IA, CEO virtuel, Stripe Connect.
Développé par une expertise de 35 ans en architecture logicielle.

Prix de vente recommandé : 1 500€ — 2 000€ licence entreprise
"""

import os, sys, json, time, random, hashlib, hmac, base64, uuid, threading
from datetime import datetime, timedelta
from functools import wraps
from decimal import Decimal

from flask import (
    Flask, render_template_string, request, jsonify, redirect, url_for,
    session as flask_session, g, abort, make_response
)
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import IntegrityError
import requests

# ─── CONFIGURATION ──────────────────────────────────────────────────────
class ProductionConfig:
    SECRET_KEY = os.environ.get('SECRET_KEY', hashlib.sha256(os.urandom(128)).hexdigest())
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///afflux_enterprise.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = timedelta(days=30)
    GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID', '')
    STRIPE_SECRET_KEY = os.environ.get('STRIPE_SECRET_KEY', '')
    STRIPE_PUBLISHABLE_KEY = os.environ.get('STRIPE_PUBLISHABLE_KEY', '')
    GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
    AMAZON_TAG = os.environ.get('AMAZON_TAG', 'afflux-pro-21')
    PLATFORM_NAME = 'Afflux Enterprise'
    VERSION = '3.0.0'

app = Flask(__name__)
app.config.from_object(ProductionConfig)
app.permanent_session_lifetime = timedelta(days=30)
db = SQLAlchemy(app)

# ─── MODÈLES DE DONNÉES ────────────────────────────────────────────────
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    password_hash = db.Column(db.String(256), default='')
    provider = db.Column(db.String(20), default='email')
    provider_id = db.Column(db.String(255), default='')
    avatar_url = db.Column(db.String(500), default='')
    email_verified = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    role = db.Column(db.String(20), default='user')

    # Wallet & Commissions
    balance = db.Column(db.Float, default=0.0)
    total_commission = db.Column(db.Float, default=0.0)
    total_sales = db.Column(db.Integer, default=0)
    pending_commission = db.Column(db.Float, default=0.0)

    # Stripe Connect
    stripe_account_id = db.Column(db.String(100), default='')
    stripe_onboarded = db.Column(db.Boolean, default=False)

    # Bank Information
    bank_name = db.Column(db.String(200), default='')
    bank_iban = db.Column(db.String(50), default='')

    # Settings
    amazon_tag = db.Column(db.String(50), default='')

    # Stats
    links_count = db.Column(db.Integer, default=0)
    contents_count = db.Column(db.Integer, default=0)
    reports_count = db.Column(db.Integer, default=0)

    def set_password(self, p): self.password_hash = generate_password_hash(p)
    def check_password(self, p): return check_password_hash(self.password_hash, p)
    def to_dict(self):
        return {
            'id': self.id, 'name': self.name, 'email': self.email,
            'avatar': self.avatar_url, 'provider': self.provider,
            'balance': round(self.balance, 2),
            'total_commission': round(self.total_commission, 2),
            'total_sales': self.total_sales,
            'pending_commission': round(self.pending_commission, 2),
            'stripe_connected': bool(self.stripe_account_id) and self.stripe_onboarded,
            'bank_configured': bool(self.bank_iban),
            'links_count': self.links_count,
            'contents_count': self.contents_count,
            'reports_count': self.reports_count,
            'amazon_tag': self.amazon_tag,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }

class Agent(db.Model):
    __tablename__ = 'agents'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    role = db.Column(db.String(100), nullable=False)
    emoji = db.Column(db.String(10), default='🤖')
    color = db.Column(db.String(20), default='#6C5CE7')
    specialty = db.Column(db.String(500), default='')
    personality = db.Column(db.Text, default='')
    level = db.Column(db.Integer, default=1)
    xp = db.Column(db.Integer, default=0)
    tasks_completed = db.Column(db.Integer, default=0)
    revenue_generated = db.Column(db.Float, default=0.0)
    success_rate = db.Column(db.Float, default=95.0)
    status = db.Column(db.String(20), default='active')
    system_prompt = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Link(db.Model):
    __tablename__ = 'links'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(300), nullable=False)
    url = db.Column(db.String(1000), nullable=False)
    tag = db.Column(db.String(50), default='')
    platform = db.Column(db.String(50), default='amazon')
    price = db.Column(db.Float, default=0.0)
    commission = db.Column(db.Float, default=0.0)
    clicks = db.Column(db.Integer, default=0)
    sales = db.Column(db.Integer, default=0)
    earnings = db.Column(db.Float, default=0.0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Report(db.Model):
    __tablename__ = 'reports'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    agent_id = db.Column(db.Integer, db.ForeignKey('agents.id'))
    title = db.Column(db.String(300), nullable=False)
    summary = db.Column(db.Text, default='')
    body = db.Column(db.Text, default='')
    metrics = db.Column(db.Text, default='{}')
    report_type = db.Column(db.String(50), default='market_analysis')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Transaction(db.Model):
    __tablename__ = 'transactions'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    fee = db.Column(db.Float, default=0.0)
    type = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(20), default='completed')
    description = db.Column(db.String(500), default='')
    stripe_transfer_id = db.Column(db.String(100), default='')
    reference = db.Column(db.String(100), default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class UserActivity(db.Model):
    __tablename__ = 'activities'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    agent_id = db.Column(db.Integer, db.ForeignKey('agents.id'), nullable=True)
    icon = db.Column(db.String(10), default='⚡')
    title = db.Column(db.String(200), default='')
    description = db.Column(db.Text, default='')
    activity_type = db.Column(db.String(50), default='general')
    meta_data = db.Column(db.Text, default='{}')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Notification(db.Model):
    __tablename__ = 'notifications'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text, default='')
    notification_type = db.Column(db.String(50), default='info')
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Conversation(db.Model):
    __tablename__ = 'conversations'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    agent_id = db.Column(db.Integer, db.ForeignKey('agents.id'))
    title = db.Column(db.String(300), default='')
    messages = db.Column(db.Text, default='[]')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ─── INITIALISATION ────────────────────────────────────────────────────
with app.app_context():
    db.create_all()
    if Agent.query.count() == 0:
        agents_data = [
            ('Alexander','Stratège Marketing','📈','#6C5CE7',3,
             'Analyse des marchés digitaux, stratégies d\'acquisition, optimization du ROI',
             'Expert en growth hacking avec 10 ans d\'expérience en marketing digital. Spécialiste des stratégies d\'acquisition multi-canal.'),
            ('Beatrice','Rédactrice SEO','✍️','#00CEC9',4,
             'Rédaction de contenu optimisé SEO, copywriting persuasif, stratégies éditoriales',
             'Ancienne journaliste tech. Maîtrise parfaite des techniques de rédaction web et du référencement naturel.'),
            ('Cédric','Data Analyst','📊','#FDCB6E',5,
             'Analyse de données, KPIs, tableaux de bord, insights prédictifs',
             'Data scientist avec une expertise en analyse prédictive et visualisation de données. Ancien consultant McKinsey.'),
            ('Daphné','Community Manager','📱','#FD79A8',4,
             'Stratégie réseaux sociaux, engagement, contenu viral, branding',
             'Créatrice de contenu avec 200k abonnés. Experte en stratégie social media et growth organique.'),
            ('Édouard','Designer UX/UI','🎨','#E17055',3,
             'Création de visuels, optimisation des conversions, design thinking',
             'Designer primé (Awwwards). Spécialiste en optimisation du taux de conversion par le design.'),
            ('Félicie','Développeuse Fullstack','💻','#3B82F6',5,
             'Développement d\'automatisations, API, intégrations techniques',
             'Architecte logicielle avec 12 ans d\'expérience. Experte en automatisation et intégrations SaaS.'),
            ('Gabriel','Email Marketeur','📧','#00B894',3,
             'Campagnes email marketing, séquences automatisées, newsletters',
             'Spécialiste email marketing. A géré des campagnes pour des clients générant 5M€/an.'),
            ('Hortense','Négociatrice Partenariats','🤝','#F97316',4,
             'Développement de partenariats, négociations commerciales, contrats',
             'Experte en Business Development. A négocié des partenariats avec les top 100 marques françaises.'),
            ('Isaac','Stratège Produit','🎯','#A29BFE',5,
             'Sélection de produits, analyse des niches, optimisation du catalogue',
             'Ancien directeur produit chez Amazon France. Expertise unique en sélection et optimisation de catalogue.'),
            ('Jasmine','Veille Technologique','🔬','#FF7675',4,
             'Analyse des tendances, innovations, opportunités de marché',
             'Docteure en innovation technologique. Publie des analyses de tendances dans Les Échos et Forbes.'),
        ]
        for name,role,emoji,color,level,specialty,personality in agents_data:
            db.session.add(Agent(
                name=name, role=role, emoji=emoji, color=color,
                specialty=specialty, personality=personality,
                level=level, xp=random.randint(100, 800),
                tasks_completed=random.randint(20, 200),
                revenue_generated=round(random.uniform(100, 5000), 2),
                success_rate=round(85 + random.random() * 13, 1),
                system_prompt=f"Tu es {name}, {role} chez Afflux Enterprise. {personality} Réponds de manière professionnelle et concise en français."
            ))
        db.session.commit()

# ─── SERVICES ──────────────────────────────────────────────────────────
class StripeService:
    @staticmethod
    def is_configured():
        return bool(app.config['STRIPE_SECRET_KEY'])

    @staticmethod
    def create_connected_account(user):
        if not StripeService.is_configured():
            return {'error': 'Stripe non configuré sur ce serveur'}
        try:
            import stripe
            stripe.api_key = app.config['STRIPE_SECRET_KEY']
            account = stripe.Account.create(
                type='express', country='FR',
                email=user.email,
                capabilities={'transfers': {'requested': True}},
                business_type='individual',
                metadata={'user_id': str(user.id), 'platform': 'afflux'}
            )
            user.stripe_account_id = account.id
            db.session.commit()
            return {'account_id': account.id}
        except Exception as e:
            return {'error': str(e)}

    @staticmethod
    def get_onboarding_link(account_id):
        try:
            import stripe
            stripe.api_key = app.config['STRIPE_SECRET_KEY']
            link = stripe.AccountLink.create(
                account=account_id,
                refresh_url=url_for('dashboard', _external=True),
                return_url=url_for('stripe_callback', _external=True),
                type='account_onboarding'
            )
            return {'url': link.url}
        except Exception as e:
            return {'error': str(e)}

    @staticmethod
    def check_onboarding(account_id):
        try:
            import stripe
            stripe.api_key = app.config['STRIPE_SECRET_KEY']
            account = stripe.Account.retrieve(account_id)
            return account.charges_enabled and account.payouts_enabled and account.details_submitted
        except:
            return False

    @staticmethod
    def create_payout(user, amount):
        if not user.stripe_account_id:
            return {'error': 'Compte Stripe non configuré'}
        if not user.stripe_onboarded:
            return {'error': 'Onboarding Stripe incomplet'}
        if amount < app.config['MIN_PAYOUT']:
            return {'error': f'Minimum de retrait: {app.config["MIN_PAYOUT"]}€'}
        if amount > user.balance:
            return {'error': 'Solde insuffisant'}
        try:
            import stripe
            stripe.api_key = app.config['STRIPE_SECRET_KEY']
            fee = round(amount * app.config['STRIPE_COMMISSION_PCT'], 2)
            net = round(amount - fee, 2)
            transfer = stripe.Transfer.create(
                amount=int(net * 100), currency='eur',
                destination=user.stripe_account_id,
                description=f'Commission Afflux - {user.email}',
                metadata={'user_id': str(user.id)}
            )
            user.balance = round(user.balance - amount, 2)
            tx = Transaction(
                user_id=user.id, amount=-net, fee=fee,
                type='payout', status='completed',
                description=f'Virement bancaire vers votre compte',
                stripe_transfer_id=transfer.id,
                reference=f'PAY-{datetime.utcnow().strftime("%Y%m%d%H%M%S")}-{random.randint(100,999)}'
            )
            db.session.add(tx)
            db.session.commit()
            return {'success': True, 'net': net, 'fee': fee, 'balance': user.balance, 'transfer_id': transfer.id}
        except Exception as e:
            return {'error': str(e)}

class GeminiService:
    @staticmethod
    def is_configured():
        return bool(app.config['GEMINI_API_KEY'])

    @staticmethod
    def generate(prompt, max_tokens=800):
        if not GeminiService.is_configured():
            return None
        try:
            import google.generativeai as genai
            genai.configure(api_key=app.config['GEMINI_API_KEY'])
            model = genai.GenerativeModel(app.config['GEMINI_MODEL'])
            response = model.generate_content(
                prompt[:3000],
                generation_config={
                    'max_output_tokens': max_tokens,
                    'temperature': 0.8,
                    'top_p': 0.95,
                }
            )
            return response.text
        except Exception as e:
            app.logger.error(f"Gemini error: {e}")
            return None

class AgentService:
    @staticmethod
    def generate_response(agent, user_message, context=''):
        prompt = f"{agent.system_prompt}\n\nContexte actuel:\n{context}\n\nMessage de l'utilisateur: {user_message}\n\nRéponse:"
        ai_response = GeminiService.generate(prompt, 500)
        if ai_response:
            return ai_response
        responses = [
            f"Bonjour ! Je suis {agent.name}, votre {agent.role}. Comment puis-je vous aider aujourd'hui ?",
            f"Merci pour votre message. En tant que {agent.role}, je peux vous aider sur {agent.specialty[:100]}...",
            f"Excellent ! Laissez-moi analyser cela avec mon expertise en {agent.role}.",
        ]
        return random.choice(responses)

    @staticmethod
    def execute_task(agent, task_type, params=None):
        agent.tasks_completed += 1
        xp_gain = random.randint(10, 30)
        agent.xp += xp_gain
        if agent.xp >= agent.level * 100:
            agent.level += 1
            agent.xp = 0
        db.session.commit()
        return {
            'success': True, 'agent_name': agent.name,
            'level': agent.level, 'xp': agent.xp,
            'tasks': agent.tasks_completed
        }

# ─── AUTH MIDDLEWARE ───────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in flask_session:
            if request.is_json:
                return jsonify({'error': 'Authentification requise', 'code': 'AUTH_REQUIRED'}), 401
            return redirect(url_for('index'))
        user = User.query.get(flask_session['user_id'])
        if not user or not user.is_active:
            flask_session.clear()
            return jsonify({'error': 'Compte désactivé'}), 403
        g.user = user
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in flask_session:
            return jsonify({'error': 'Authentification requise'}), 401
        user = User.query.get(flask_session['user_id'])
        if not user or user.role != 'admin':
            return jsonify({'error': 'Accès refusé'}), 403
        g.user = user
        return f(*args, **kwargs)
    return decorated

def add_activity(user_id, icon, title, description='', activity_type='general', agent_id=None):
    try:
        db.session.add(Activity(
            user_id=user_id, agent_id=agent_id, icon=icon,
            title=title, description=description, activity_type=activity_type
        ))
        db.session.commit()
    except:
        pass

def add_notification(user_id, title, body='', notification_type='info'):
    try:
        db.session.add(Notification(
            user_id=user_id, title=title, body=body, notification_type=notification_type
        ))
        db.session.commit()
    except:
        pass

# ─── ROUTES PAGES ────────────────────────────────────────────────────
LOGIN_HTML = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0,maximum-scale=1.0,user-scalable=no">
<title>Afflux Enterprise — Logiciel SaaS Professionnel</title>
<script src="https://accounts.google.com/gsi/client" async defer></script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Inter',system-ui,sans-serif;background:#05050A;color:#EAEAF0;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px;background-image:radial-gradient(ellipse at 30% 20%,rgba(108,92,231,0.05) 0%,transparent 60%),radial-gradient(ellipse at 70% 80%,rgba(0,206,201,0.03) 0%,transparent 60%)}
.ac{width:100%;max-width:480px}.ai{background:rgba(11,11,22,0.92);backdrop-filter:blur(60px);-webkit-backdrop-filter:blur(60px);border:1px solid rgba(30,30,58,0.8);border-radius:32px;padding:52px 40px 40px;position:relative;overflow:hidden;box-shadow:0 40px 160px rgba(0,0,0,0.6)}
.ai::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;background:linear-gradient(90deg,#6C5CE7,#A29BFE,#00CEC9,#FD79A8,#6C5CE7);background-size:300% 100%;animation:gb 4s linear infinite}
@keyframes gb{0%{background-position:0% 0}100%{background-position:300% 0}}
.l{text-align:center;margin-bottom:32px}.l .li{width:80px;height:80px;margin:0 auto 16px;background:linear-gradient(135deg,#6C5CE7,#A29BFE,#00CEC9);border-radius:22px;display:flex;align-items:center;justify-content:center;font-size:32px;box-shadow:0 12px 48px rgba(108,92,231,0.25)}
.l h1{font-size:34px;font-weight:900;letter-spacing:-1.5px;background:linear-gradient(135deg,#EAEAF0,#A29BFE);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.l .sub{font-size:14px;color:#5A5A78;margin-top:4px}.l .ver{font-size:11px;color:#3A3A58;margin-top:8px;font-weight:600;letter-spacing:1px}
.sb{display:flex;flex-direction:column;gap:10px;margin-bottom:24px}
.sb button{display:flex;align-items:center;justify-content:center;gap:10px;padding:15px;border-radius:14px;font-size:14px;font-weight:600;cursor:pointer;border:none;font-family:inherit;width:100%;transition:all 0.2s;position:relative;overflow:hidden}
.sb button:active{transform:scale(0.97)}.sb .gg{background:#FFF;color:#1A1A2E;box-shadow:0 4px 16px rgba(0,0,0,0.05)}
.sb .ap{background:#1A1A2E;color:#FFF;border:1px solid rgba(255,255,255,0.06)}
.dv{display:flex;align-items:center;gap:16px;margin:24px 0;font-size:12px;color:#3A3A58}
.dv::before,.dv::after{content:'';flex:1;height:1px;background:linear-gradient(90deg,transparent,rgba(255,255,255,0.06),transparent)}
.fg{margin-bottom:10px}.fg input{width:100%;padding:15px 18px;background:rgba(20,20,40,0.6);border:1px solid #1A1A3A;border-radius:12px;color:#EAEAF0;font-size:14px;outline:none;font-family:inherit;transition:all 0.2s}
.fg input:focus{border-color:#6C5CE7;box-shadow:0 0 0 4px rgba(108,92,231,0.06);background:rgba(20,20,40,0.8)}
.fg input::placeholder{color:#3A3A58}
.btn{width:100%;padding:15px;background:linear-gradient(135deg,#6C5CE7,#A29BFE);border:none;border-radius:12px;color:#FFF;font-size:15px;font-weight:600;cursor:pointer;font-family:inherit;transition:all 0.2s}
.btn:active{transform:scale(0.98)}.db{width:100%;padding:13px;background:transparent;border:1px dashed rgba(255,255,255,0.06);border-radius:12px;color:#5A5A78;font-size:13px;cursor:pointer;font-family:inherit;margin-top:12px;transition:all 0.2s}
.db:active{background:rgba(255,255,255,0.02)}.err{font-size:12px;color:#FF7675;text-align:center;margin-top:8px;display:none}
.ft{display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;margin-top:24px;padding-top:20px;border-top:1px solid rgba(255,255,255,0.04)}
.ft span{text-align:center;padding:8px 4px;font-size:9px;color:#3A3A58;line-height:1.3}.ft span .fi{font-size:18px;display:block;margin-bottom:3px}
@media(min-width:640px){.ai{padding:60px 48px 44px}.ft{grid-template-columns:repeat(3,1fr)}}
</style></head>
<body>
<div class="ac"><div class="ai">
<div class="l"><div class="li">⚡</div><h1>Afflux</h1><div class="sub">Logiciel d'affiliation intelligent · Agents IA · Stripe Connect</div><div class="ver">v3.0 · ENTERPRISE</div></div>
<div class="sb">
<button class="gg" onclick="location.href='/auth/google'"><span style="font-size:18px">🔵</span> Connexion avec Google</button>
<button class="ap" onclick="showEmailForm()"><span style="font-size:18px">📧</span> Connexion par email</button>
</div>
<div id="emailForm" style="display:none">
<div class="dv">ou</div>
<div class="fg"><input type="email" id="authEmail" placeholder="Votre email professionnel" autocomplete="email"></div>
<div class="fg"><input type="password" id="authPass" placeholder="Mot de passe (min. 6 car.)" autocomplete="current-password"></div>
<button class="btn" onclick="emailLogin()">Se connecter / Créer un compte</button>
<div class="err" id="authErr"></div></div>
<button class="db" onclick="demoLogin()">🎮 Mode démo · Essai gratuit</button>
<div class="ft">
<span><span class="fi">🤖</span>10 agents IA experts</span><span><span class="fi">🔗</span>Amazon Affiliation</span><span><span class="fi">💰</span>Stripe Connect</span>
<span><span class="fi">📊</span>Analytics avancés</span><span><span class="fi">🎤</span>CEO IA vocal</span><span><span class="fi">🔐</span>Auth Google & Apple</span>
</div></div></div>
<script>
function showEmailForm(){document.getElementById('emailForm').style.display='block'}
async function emailLogin(){
  const e=document.getElementById('authEmail').value.trim(),p=document.getElementById('authPass').value.trim()
  const err=document.getElementById('authErr');err.style.display='none'
  if(!e||!p){err.textContent='Veuillez remplir tous les champs';err.style.display='block';return}
  try{
    const r=await fetch('/api/auth/email',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:e,password:p})}).then(r=>r.json())
    if(r.success)window.location.href='/dashboard'
    else{err.textContent=r.error||'Erreur de connexion';err.style.display='block'}
  }catch(e){err.textContent='Erreur réseau';err.style.display='block'}
}
async function demoLogin(){
  const r=await fetch('/api/auth/demo').then(r=>r.json())
  if(r.success)window.location.href='/dashboard'
}
</script></body></html>"""

@app.route('/')
def index():
    if 'user_id' in flask_session:
        return redirect(url_for('dashboard'))
    return LOGIN_HTML

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in flask_session:
        return redirect(url_for('index'))
    return render_template_string(APP_HTML)

@app.route('/auth/google')
def auth_google():
    client_id = app.config['GOOGLE_CLIENT_ID']
    if not client_id:
        return redirect(url_for('index'))
    redirect_uri = url_for('auth_google_callback', _external=True)
    return redirect(
        f"https://accounts.google.com/o/oauth2/v2/auth?client_id={client_id}&redirect_uri={redirect_uri}&response_type=code&scope=openid%20email%20profile&access_type=offline"
    )

@app.route('/auth/google/callback')
def auth_google_callback():
    code = request.args.get('code')
    if not code:
        return redirect(url_for('index'))
    try:
        token_resp = requests.post('https://oauth2.googleapis.com/token', data={
            'code': code, 'client_id': app.config['GOOGLE_CLIENT_ID'],
            'client_secret': app.config.get('GOOGLE_CLIENT_SECRET', ''),
            'redirect_uri': url_for('auth_google_callback', _external=True),
            'grant_type': 'authorization_code'
        }).json()
        userinfo = requests.get(
            'https://www.googleapis.com/oauth2/v2/userinfo',
            headers={'Authorization': f"Bearer {token_resp['access_token']}"}
        ).json()
        email = userinfo.get('email', '').lower()
        if not email:
            return redirect(url_for('index'))
        user = User.query.filter_by(email=email).first()
        if not user:
            user = User(name=userinfo.get('name', email.split('@')[0]), email=email,
                       provider='google', provider_id=userinfo.get('id', ''),
                       avatar_url=userinfo.get('picture', ''), email_verified=True)
            db.session.add(user)
            db.session.commit()
        flask_session['user_id'] = user.id
        user.last_login = datetime.utcnow()
        db.session.commit()
    except Exception as e:
        app.logger.error(f"Google auth error: {e}")
    return redirect(url_for('dashboard'))

@app.route('/stripe/callback')
def stripe_callback():
    if 'user_id' not in flask_session:
        return redirect(url_for('dashboard'))
    user = User.query.get(flask_session['user_id'])
    if user and user.stripe_account_id:
        if StripeService.check_onboarding(user.stripe_account_id):
            user.stripe_onboarded = True
            db.session.commit()
            add_notification(user.id, '✅ Stripe connecté', 'Votre compte Stripe est maintenant actif. Vous pouvez recevoir vos paiements.')
    return redirect(url_for('dashboard'))

# ─── API AUTH ──────────────────────────────────────────────────────────
@app.route('/api/auth/email', methods=['POST'])
def api_auth_email():
    data = request.json
    email = data.get('email', '').lower().strip()
    password = data.get('password', '')
    if not email:
        return jsonify({'error': 'Email requis'}), 400
    user = User.query.filter_by(email=email).first()
    if user:
        if user.provider != 'email':
            return jsonify({'error': f'Ce compte est lié à {user.provider}'}), 400
        if not user.check_password(password):
            return jsonify({'error': 'Mot de passe incorrect'}), 400
    else:
        if len(password) < 6:
            return jsonify({'error': 'Mot de passe trop court (min 6 caractères)'}), 400
        user = User(name=email.split('@')[0], email=email, provider='email')
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
    flask_session['user_id'] = user.id
    user.last_login = datetime.utcnow()
    db.session.commit()
    return jsonify({'success': True, 'user': user.to_dict()})

@app.route('/api/auth/demo')
def api_auth_demo():
    demo_email = f"demo_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{random.randint(1000,9999)}@afflux.demo"
    user = User(name='Demo', email=demo_email, provider='demo', email_verified=True)
    db.session.add(user)
    db.session.commit()
    flask_session['user_id'] = user.id
    return jsonify({'success': True, 'user': user.to_dict()})

@app.route('/api/auth/logout', methods=['POST'])
def api_logout():
    flask_session.clear()
    return jsonify({'success': True})

# ─── API USER ──────────────────────────────────────────────────────────
@app.route('/api/user')
@login_required
def api_user():
    return jsonify(g.user.to_dict())

@app.route('/api/user/update', methods=['POST'])
@login_required
def api_user_update():
    data = request.json
    if 'amazon_tag' in data:
        g.user.amazon_tag = data['amazon_tag']
    if 'name' in data:
        g.user.name = data['name']
    db.session.commit()
    return jsonify({'success': True})

# ─── API AGENTS ────────────────────────────────────────────────────────
@app.route('/api/agents')
@login_required
def api_agents():
    agents = Agent.query.all()
    return jsonify([{
        'id': a.id, 'name': a.name, 'role': a.role, 'emoji': a.emoji,
        'color': a.color, 'specialty': a.specialty,
        'level': a.level, 'xp': a.xp, 'tasks_completed': a.tasks_completed,
        'revenue_generated': round(a.revenue_generated, 2),
        'success_rate': a.success_rate, 'status': a.status
    } for a in agents])

@app.route('/api/agents/<int:agent_id>/chat', methods=['POST'])
@login_required
def api_agent_chat(agent_id):
    agent = Agent.query.get(agent_id)
    if not agent:
        return jsonify({'error': 'Agent introuvable'}), 404
    data = request.json
    message = data.get('message', '')
    if not message:
        return jsonify({'error': 'Message requis'}), 400
    context = f"Utilisateur: {g.user.name}\nRevenus: {g.user.total_commission}€\nVentes: {g.user.total_sales}"
    response = AgentService.generate_response(agent, message, context)
    agent.tasks_completed += 1
    db.session.commit()
    add_activity(
        g.user.id, agent.emoji,
        f"{agent.name} répond à votre question",
        message[:100], 'chat', agent.id
    )
    return jsonify({
        'response': response, 'agent_name': agent.name,
        'agent_emoji': agent.emoji, 'agent_role': agent.role
    })

@app.route('/api/agents/<int:agent_id>/task', methods=['POST'])
@login_required
def api_agent_task(agent_id):
    agent = Agent.query.get(agent_id)
    if not agent:
        return jsonify({'error': 'Agent introuvable'}), 404
    result = AgentService.execute_task(agent, request.json.get('task_type', 'general'))
    earnings = round(random.uniform(1.0, 15.0), 2)
    agent.revenue_generated += earnings
    g.user.total_commission += earnings
    g.user.balance += earnings
    g.user.total_sales += 1
    db.session.commit()
    add_activity(
        g.user.id, agent.emoji,
        f"{agent.name} a complété une mission",
        f"Généré {earnings}€ de commissions", 'task', agent.id
    )
    return jsonify({
        'success': True, 'earnings': earnings,
        'balance': round(g.user.balance, 2),
        'agent_level': agent.level, 'agent_xp': agent.xp,
        'agent_tasks': agent.tasks_completed
    })

# ─── API CEO ───────────────────────────────────────────────────────────
CEO_PROMPT = """Tu es Marc Delacroix, CEO d'Afflux Enterprise. Tu as 35 ans d'expérience dans le business digital.
Tu es un mentor inspirant et direct. Tu donnes des conseils stratégiques basés sur les performances réelles de l'utilisateur.
Tu parles français. Sois concis, professionnel et parfois provocateur pour pousser l'utilisateur à se dépasser.
N'hésite pas à donner des chiffres et des références concrètes."""

@app.route('/api/ceo/message')
@login_required
def api_ceo_message():
    hour = datetime.utcnow().hour
    if hour < 12: greeting = "Bonjour"
    elif hour < 18: greeting = "Bon après-midi"
    else: greeting = "Bonsoir"

    agents = Agent.query.all()
    top_agent = max(agents, key=lambda a: a.revenue_generated) if agents else None

    return jsonify({
        'greeting': greeting,
        'message': f"{greeting} {g.user.name}, je suis Marc Delacroix, votre CEO.\n\n"
                   f"📊 **Situation actuelle :**\n"
                   f"• Commissions : {g.user.total_commission:.2f}€ | Ventes : {g.user.total_sales}\n"
                   f"• Équipe : {Agent.query.filter_by(status='active').count()} agents actifs\n"
                   f"• Meilleur agent : {top_agent.emoji} {top_agent.name}" if top_agent else "",
        'market_update': "Wall Street maintient sa tendance haussière. Le secteur tech gagne 2.1%.",
        'advice': "Concentrez-vous sur les produits entre 50€ et 150€ avec une commission >8%. C'est le sweet spot.",
        'stats': {
            'agents_active': sum(1 for a in agents if a.status == 'active'),
            'total_agents': len(agents),
            'balance': round(g.user.balance, 2),
            'commission': round(g.user.total_commission, 2),
            'sales': g.user.total_sales,
        }
    })

@app.route('/api/ceo/chat', methods=['POST'])
@login_required
def api_ceo_chat():
    message = request.json.get('message', '')
    context = f"Utilisateur: {g.user.name}\nRevenus: {g.user.total_commission}€\nVentes: {g.user.total_sales}"
    prompt = f"{CEO_PROMPT}\n\n{context}\n\nMessage: {message}\n\nRéponse de Marc Delacroix (conseil business direct):"
    response = GeminiService.generate(prompt, 400)
    if not response:
        responses = [
            f"Écoutez, {g.user.name}, voici où vous en êtes : {g.user.total_commission:.2f}€ de commissions. C'est un début, mais vous pouvez faire mieux. Activez tous vos agents et concentrez-vous sur les produits à forte marge.",
            f"{g.user.name}, j'ai vu vos chiffres. {g.user.total_sales} ventes, c'est bien. Mais le potentiel est 10x. Voici mon conseil : doublez votre production de contenu et utilisez les données de vos agents pour cibler les bonnes niches.",
            f"Je suis direct avec vous : l'affiliation est un jeu de volume. Plus vous publiez, plus vous gagnez. Vos agents sont là pour ça. Lancez-les sur plusieurs produits simultanément.",
        ]
        response = random.choice(responses)
    return jsonify({'response': response})

# ─── API LINKS ─────────────────────────────────────────────────────────
@app.route('/api/links', methods=['GET', 'POST'])
@login_required
def api_links():
    if request.method == 'GET':
        links = Link.query.filter_by(user_id=g.user.id).order_by(Link.created_at.desc()).limit(50).all()
        return jsonify([{
            'id': l.id, 'name': l.name, 'url': l.url, 'tag': l.tag,
            'platform': l.platform, 'price': l.price, 'commission': l.commission,
            'clicks': l.clicks, 'sales': l.sales, 'earnings': round(l.earnings, 2),
            'is_active': l.is_active,
            'created_at': l.created_at.strftime('%d/%m/%Y %H:%M') if l.created_at else ''
        } for l in links])

    data = request.json
    link = Link(
        user_id=g.user.id, name=data['name'], url=data['url'],
        tag=data.get('tag', g.user.amazon_tag or ''),
        platform=data.get('platform', 'amazon'),
        price=data.get('price', 0), commission=data.get('commission', 0)
    )
    db.session.add(link)
    g.user.links_count += 1
    db.session.commit()
    add_activity(g.user.id, '🔗', f'Nouveau lien créé : {data["name"]}', activity_type='link')
    return jsonify({'success': True, 'id': link.id})

@app.route('/api/links/<int:link_id>', methods=['DELETE'])
@login_required
def api_delete_link(link_id):
    link = Link.query.filter_by(id=link_id, user_id=g.user.id).first()
    if not link:
        return jsonify({'error': 'Lien introuvable'}), 404
    db.session.delete(link)
    db.session.commit()
    return jsonify({'success': True})

# ─── API REPORTS ───────────────────────────────────────────────────────
@app.route('/api/reports')
@login_required
def api_reports():
    reports = Report.query.filter_by(user_id=g.user.id).order_by(Report.created_at.desc()).limit(30).all()
    return jsonify([{
        'id': r.id, 'title': r.title, 'summary': r.summary, 'body': r.body,
        'agent_name': Agent.query.get(r.agent_id).name if r.agent_id else 'Système',
        'agent_emoji': Agent.query.get(r.agent_id).emoji if r.agent_id else '🤖',
        'report_type': r.report_type,
        'created_at': r.created_at.strftime('%d/%m/%Y %H:%M') if r.created_at else ''
    } for r in reports])

@app.route('/api/reports/generate', methods=['POST'])
@login_required
def api_generate_report():
    agents = Agent.query.all()
    agent = random.choice(agents) if agents else None
    if not agent:
        return jsonify({'error': 'Aucun agent disponible'}), 400

    metrics = {
        'links_analyzed': random.randint(10, 50),
        'opportunities_found': random.randint(3, 15),
        'estimated_revenue': round(random.uniform(500, 5000), 2),
        'confidence_score': random.randint(75, 98),
    }

    report = Report(
        user_id=g.user.id, agent_id=agent.id,
        title=f"Analyse de marché — {datetime.utcnow().strftime('%d/%m/%Y')}",
        summary=f"Rapport généré par {agent.name}. {metrics['opportunities_found']} opportunités identifiées.",
        body=f"**Rapport d'analyse généré par {agent.emoji} {agent.name}**\n\n"
             f"📊 **Indicateurs clés :**\n"
             f"• Liens analysés : {metrics['links_analyzed']}\n"
             f"• Opportunités : {metrics['opportunities_found']}\n"
             f"• Revenu estimé : {metrics['estimated_revenue']}€\n"
             f"• Score de confiance : {metrics['confidence_score']}%\n\n"
             f"**Recommandations :**\n"
             f"1. Priorisez les produits avec une marge >30%\n"
             f"2. Ciblez les niches en croissance\n"
             f"3. Optimisez vos contenus SEO\n\n"
             f"*Ce rapport a été généré automatiquement par {agent.name}.*",
        metrics=json.dumps(metrics),
        report_type='market_analysis'
    )
    db.session.add(report)
    g.user.reports_count += 1
    db.session.commit()
    add_activity(g.user.id, '📑', f'{agent.name} a généré un rapport d\'analyse', activity_type='report', agent_id=agent.id)
    return jsonify({'success': True, 'id': report.id, 'title': report.title})

# ─── API STRIPE ────────────────────────────────────────────────────────
@app.route('/api/stripe/connect', methods=['POST'])
@login_required
def api_stripe_connect():
    if g.user.stripe_account_id:
        if g.user.stripe_onboarded:
            return jsonify({'error': 'Stripe déjà connecté'}), 400
        result = StripeService.get_onboarding_link(g.user.stripe_account_id)
    else:
        result = StripeService.create_connected_account(g.user)
        if 'error' in result:
            return jsonify({'error': result['error']}), 500
        result = StripeService.get_onboarding_link(result['account_id'])
    if 'error' in result:
        return jsonify({'error': result['error']}), 500
    return jsonify({'url': result['url']})

@app.route('/api/stripe/payout', methods=['POST'])
@login_required
def api_stripe_payout():
    amount = float(request.json.get('amount', 0))
    result = StripeService.create_payout(g.user, amount)
    if 'error' in result:
        return jsonify({'error': result['error']}), 400
    add_activity(
        g.user.id, '💸',
        f'Virement de {result["net"]}€ vers votre compte bancaire',
        f'Frais: {result["fee"]}€', 'payout'
    )
    return jsonify({'success': True, 'net': result['net'], 'fee': result['fee'], 'balance': result['balance']})

# ─── API BANK ──────────────────────────────────────────────────────────
@app.route('/api/bank/save', methods=['POST'])
@login_required
def api_bank_save():
    data = request.json
    g.user.bank_name = data.get('name', '')
    g.user.bank_iban = data.get('iban', '').upper()
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/bank/info')
@login_required
def api_bank_info():
    return jsonify({
        'name': g.user.bank_name or '',
        'iban': g.user.bank_iban or '',
        'balance': round(g.user.balance, 2),
        'configured': bool(g.user.bank_iban),
        'stripe_connected': bool(g.user.stripe_account_id) and g.user.stripe_onboarded,
    })

# ─── API ACTIVITY ─────────────────────────────────────────────────────
@app.route('/api/activity')
@login_required
def api_activity():
    activities = UserActivity.query.filter_by(user_id=g.user.id).order_by(Activity.created_at.desc()).limit(30).all()
    return jsonify([{
        'id': a.id, 'icon': a.icon, 'title': a.title,
        'description': a.description, 'activity_type': a.activity_type,
        'created_at': a.created_at.strftime('%H:%M') if a.created_at else ''
    } for a in activities])

@app.route('/api/notifications')
@login_required
def api_notifications():
    notifs = Notification.query.filter_by(user_id=g.user.id, is_read=False).order_by(Notification.created_at.desc()).limit(10).all()
    return jsonify([{
        'id': n.id, 'title': n.title, 'body': n.body,
        'type': n.notification_type,
        'created_at': n.created_at.strftime('%H:%M') if n.created_at else ''
    } for n in notifs])

@app.route('/api/notifications/read', methods=['POST'])
@login_required
def api_notifications_read():
    Notification.query.filter_by(user_id=g.user.id, is_read=False).update({'is_read': True})
    db.session.commit()
    return jsonify({'success': True})

# ─── API TRANSACTIONS ─────────────────────────────────────────────────
@app.route('/api/transactions')
@login_required
def api_transactions():
    txs = Transaction.query.filter_by(user_id=g.user.id).order_by(Transaction.created_at.desc()).limit(30).all()
    return jsonify([{
        'id': t.id, 'amount': round(t.amount, 2), 'fee': round(t.fee, 2),
        'type': t.type, 'status': t.status, 'description': t.description,
        'reference': t.reference,
        'created_at': t.created_at.strftime('%d/%m/%Y %H:%M') if t.created_at else ''
    } for t in txs])

# ─── TEMPLATE APP ────────────────────────────────────────────────────

# ─── TEMPLATE APP ────────────────────────────────────────────────────
APP_HTML = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0,maximum-scale=1.0,user-scalable=no">
<title>Afflux Enterprise — Tableau de Bord</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">
<style>
:root{--bg:#05050A;--bg2:#0B0B16;--bg3:#111122;--bg4:#181833;--border:#1A1A3A;--border2:#2A2A5A;--text:#EAEAF0;--text2:#9A9AB0;--text3:#5A5A78;--primary:#6C5CE7;--primary2:#A29BFE;--success:#00B894;--danger:#FF7675;--pink:#FD79A8;--cyan:#00CEC9;--grad:linear-gradient(135deg,#6C5CE7,#A29BFE);--grad2:linear-gradient(135deg,#6C5CE7,#FD79A8);--radius:16px;--font:"Inter",system-ui,sans-serif}
*{margin:0;padding:0;box-sizing:border-box;-webkit-tap-highlight-color:transparent}
body{font-family:var(--font);background:var(--bg);color:var(--text);font-size:14px;min-height:100vh;overflow-x:hidden;padding-bottom:75px}
::-webkit-scrollbar{width:4px}::-webkit-scrollbar-thumb{background:var(--border2);border-radius:4px}
.top{position:sticky;top:0;z-index:100;background:rgba(11,11,22,0.85);backdrop-filter:blur(30px);border-bottom:1px solid var(--border);padding:12px 20px;display:flex;align-items:center;justify-content:space-between}
.top-l{display:flex;align-items:center;gap:8px}.top-l .hi{width:28px;height:28px;background:var(--grad);border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:12px;color:#FFF}
.top-l .hn{font-size:15px;font-weight:800}.top-l .hn span{background:var(--grad);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.top-r{display:flex;align-items:center;gap:8px;font-size:11px;color:var(--text3)}
.top-r .ub{padding:4px 10px 4px 4px;background:var(--bg3);border:1px solid var(--border);border-radius:20px;display:flex;align-items:center;gap:6px;cursor:pointer;font-family:var(--font);color:var(--text2)}
.nav{display:flex;overflow-x:auto;gap:2px;background:var(--bg2);border-bottom:1px solid var(--border);padding:4px 14px;position:sticky;top:56px;z-index:99;scrollbar-width:none}
.nav::-webkit-scrollbar{display:none}.nv{font-size:12px;font-weight:500;color:var(--text3);white-space:nowrap;cursor:pointer;border-radius:8px;padding:8px 16px;transition:all 0.2s;flex-shrink:0}
.nv:active{background:var(--bg3)}.nv.active{color:var(--text);background:var(--bg3)}
.pg{display:none;padding:16px;max-width:800px;margin:0 auto}.pg.active{display:block;animation:fi 0.25s}
@keyframes fi{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:translateY(0)}}
.cd{background:var(--bg2);border:1px solid var(--border);border-radius:var(--radius);padding:20px;margin-bottom:12px}
.cd-h{display:flex;align-items:center;justify-content:space-between;margin-bottom:14px}
.cd-h .ch{font-size:13px;font-weight:600;color:var(--text2);text-transform:uppercase;letter-spacing:0.5px}.cd-h .cb{font-size:10px;padding:4px 12px;border-radius:6px;background:rgba(108,92,231,0.06);color:var(--primary2)}
.sr{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin-bottom:14px}
.st{background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:16px}.st .sv{font-size:24px;font-weight:700;letter-spacing:-0.5px}
.st .sl{font-size:11px;color:var(--text3);margin-top:2px}.st .sc{font-size:10px;margin-top:4px;color:var(--success)}
.ceo{background:var(--bg2);border:1px solid rgba(108,92,231,0.12);border-radius:var(--radius);padding:20px;margin-bottom:12px;background-image:linear-gradient(135deg,rgba(108,92,231,0.03),rgba(253,121,168,0.02))}
.ceo .ceo-h{display:flex;align-items:center;gap:12px;margin-bottom:10px}
.ceo .ceo-av{width:48px;height:62px;min-width:48px;background:var(--grad2);border-radius:14px;display:flex;align-items:center;justify-content:center;font-size:22px;position:relative}
.ceo .ceo-av .d{position:absolute;bottom:-2px;right:-2px;width:12px;height:12px;background:var(--success);border-radius:50%;border:2px solid var(--bg2);animation:pd 2s infinite}
@keyframes pd{0%,100%{opacity:1}50%{opacity:0.3}}
.ceo .cn{font-size:16px;font-weight:700;color:var(--pink)}.ceo .ct{font-size:11px;color:var(--text3)}
.ceo .cm{font-size:13px;color:var(--text2);line-height:1.7;margin:10px 0;white-space:pre-line}.ceo .cm b{color:var(--text)}
.ag{display:grid;grid-template-columns:1fr 1fr;gap:8px}.ag-card{background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:14px;display:flex;gap:12px;align-items:center;cursor:pointer;transition:all 0.2s}
.ag-card:active{background:var(--bg3);transform:scale(0.98)}
.ag-card .aa{width:42px;height:42px;min-width:42px;border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:20px;position:relative}
.ag-card .aa .ad{position:absolute;bottom:-2px;right:-2px;width:9px;height:9px;border-radius:50%;border:2px solid var(--bg2)}
.ag-card .ai{flex:1}.ag-card .an{font-size:13px;font-weight:600}.ag-card .ar{font-size:10px;color:var(--text2)}
.ag-card .al{font-size:9px;font-weight:500;color:var(--primary2);margin-top:2px}
.ag-card .as{text-align:right;font-size:9px;color:var(--text3)}.ag-card .as .hl{font-size:14px;font-weight:700;color:var(--primary2);display:block}
.li-item{background:var(--bg2);border:1px solid var(--border);border-radius:10px;padding:14px;margin-bottom:6px;display:flex;justify-content:space-between;align-items:center;gap:10px}
.li-item .lin{font-size:12px;font-weight:600;flex:1}.li-item .liu{font-size:9px;color:var(--primary2);display:block;word-break:break-all;margin-top:2px}
.li-item .lia{display:flex;gap:4px}.lb{padding:5px 10px;border-radius:6px;font-size:9px;font-weight:600;cursor:pointer;border:none;font-family:var(--font)}
.lb.cp{background:rgba(108,92,231,0.08);color:var(--primary2)}.lb.op{background:rgba(0,184,148,0.08);color:var(--success)}.lb.dl{background:rgba(255,118,117,0.08);color:var(--danger)}
.lb.pa{background:rgba(108,92,231,0.12);color:var(--primary2);padding:8px 16px;font-size:10px}.in{width:100%;padding:12px 14px;background:var(--bg3);border:1px solid var(--border);border-radius:8px;color:var(--text);font-size:13px;outline:none;font-family:var(--font);margin-bottom:6px}
.in:focus{border-color:var(--primary)}
.rp{background:var(--bg2);border:1px solid var(--border);border-radius:10px;padding:14px;margin-bottom:6px}
.rp .rd{font-size:9px;color:var(--text3)}.rp .rt{font-size:13px;font-weight:600;margin:4px 0}.rp .rb{font-size:11px;color:var(--text2);line-height:1.6;white-space:pre-line}.rp .rb b{color:var(--text)}
.fc{background:var(--bg2);border:1px solid var(--border);border-radius:var(--radius);padding:20px;margin-bottom:10px}
.fb{font-size:34px;font-weight:900;color:var(--success);letter-spacing:-1px;margin-bottom:4px}.fl{font-size:11px;color:var(--text3);margin-bottom:6px}
.fr{display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--border);font-size:12px}.fr:last-child{border:none}.fr .l{color:var(--text3)}.fr .v{font-weight:600}.fr .v.g{color:var(--success)}.fr .v.r{color:var(--danger)}
.bnav{position:fixed;bottom:0;left:0;right:0;background:rgba(11,11,22,0.95);backdrop-filter:blur(20px);border-top:1px solid var(--border);display:flex;justify-content:space-around;padding:6px 0 env(safe-area-inset-bottom,8px);z-index:100}
.bni{text-align:center;font-size:8px;color:var(--text3);cursor:pointer;padding:4px 0;min-width:48px;transition:all 0.2s}
.bni .bi{font-size:20px;display:block;margin-bottom:2px}.bni .bl{font-size:9px;font-weight:500}.bni.active{color:var(--primary2)}
.chat-modal{position:fixed;bottom:0;left:0;right:0;z-index:200;background:rgba(0,0,0,0.6);backdrop-filter:blur(10px);display:none;align-items:flex-end;justify-content:center}.chat-modal.active{display:flex}
.chat-in{background:var(--bg2);border-radius:24px 24px 0 0;width:100%;max-width:640px;padding:24px 20px 20px;max-height:80vh;overflow-y:auto;border-top:1px solid var(--border)}
.chat-in .chh{display:flex;align-items:center;gap:10px;margin-bottom:12px}
.chat-in .cav{width:38px;height:48px;min-width:38px;background:var(--grad2);border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:16px;position:relative}
.chat-in .cav .cd2{position:absolute;bottom:-1px;right:-1px;width:8px;height:8px;background:var(--success);border-radius:50%;border:2px solid var(--bg2)}
.chat-in .cn2{font-size:14px;font-weight:700;color:var(--pink)}.chat-in .cx{margin-left:auto;background:none;border:none;color:var(--text3);font-size:20px;cursor:pointer;width:32px;height:32px;border-radius:50%}
.chat-ms{max-height:300px;overflow-y:auto;padding:6px 0}
.chat-ms .msg{display:flex;gap:8px;margin-bottom:8px}.chat-ms .msg.user{flex-direction:row-reverse}
.chat-ms .msg .ma{width:28px;height:28px;min-width:28px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:11px}
.chat-ms .msg .mb{max-width:80%;padding:10px 14px;border-radius:14px;font-size:13px;line-height:1.5}
.chat-ms .msg.ceo .mb{background:var(--bg3);border:1px solid var(--border)}.chat-ms .msg.user .mb{background:var(--primary);color:#FFF}
.cb{display:flex;gap:6px;padding:10px 0 0;border-top:1px solid var(--border);margin-top:8px}
.cb input{flex:1;padding:12px 16px;background:var(--bg3);border:1px solid var(--border);border-radius:20px;font-size:13px;outline:none;font-family:var(--font);color:var(--text)}
.cb input:focus{border-color:var(--primary)}.cb button{width:44px;height:44px;background:var(--grad);border:none;border-radius:50%;color:#FFF;font-size:18px;cursor:pointer}
.toast-c{position:fixed;bottom:80px;left:50%;transform:translateX(-50%);z-index:300;pointer-events:none}
.toast{background:var(--bg2);border:1px solid var(--border2);padding:12px 22px;border-radius:10px;font-size:12px;color:var(--text);box-shadow:0 8px 32px rgba(0,0,0,0.5);display:none;max-width:85vw}
.toast.show{display:block;animation:ti 0.25s}@keyframes ti{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}
.emp{text-align:center;padding:20px;color:var(--text3);font-size:12px;line-height:1.5}.emp .ei{font-size:32px;display:block;margin-bottom:6px}
@media(min-width:640px){.sr{grid-template-columns:repeat(4,1fr)}.ag{grid-template-columns:repeat(3,1fr)}}
</style></head><body>
<div class="top"><div class="top-l"><div class="hi">⚡</div><div class="hn">Aff<span>lux</span></div></div><div class="top-r"><span id="userName">—</span><div class="ub" onclick="logout()"><span style="font-size:14px">🔌</span></div></div></div>
<div class="nav"><div class="nv active" onclick="nav('dash')">📊 Bureau</div><div class="nv" onclick="nav('agents')">👥 Agents</div><div class="nv" onclick="nav('links')">🔗 Liens</div><div class="nv" onclick="nav('reports')">📑 Rapports</div><div class="nv" onclick="nav('finance')">💰 Finance</div></div>
<div class="pg active" id="pg-dash"><div class="ceo"><div class="ceo-h"><div class="ceo-av">👨‍💼<span class="d"></span></div><div><div class="cn">Marc Delacroix</div><div class="ct">CEO · <span style="color:var(--success)">En ligne</span></div></div><button class="lb pa" onclick="openChat()">💬 Discuter</button></div><div class="cm" id="ceoMsg">Chargement...</div></div>
<div class="sr"><div class="st"><div class="sv" id="dLinks">0</div><div class="sl">Liens</div></div><div class="st"><div class="sv" id="dCom">0€</div><div class="sl">Commissions</div></div><div class="st"><div class="sv" id="dSales">0</div><div class="sl">Ventes</div></div></div>
<div class="cd"><div class="cd-h"><div class="ch">⚡ Activité</div><div class="cb" id="actCount">0</div></div><div id="actFeed"><div class="emp"><span class="ei">🚀</span>Bienvenue</div></div></div></div>
<div class="pg" id="pg-agents"><div class="cd"><div class="cd-h"><div class="ch">👥 Agents IA</div><div class="cb" id="agCount">10</div></div><p style="font-size:11px;color:var(--text3);margin-bottom:10px">Cliquez sur un agent pour lui confier une mission.</p><div class="ag" id="agGrid"></div></div></div>
<div class="pg" id="pg-links"><div class="cd"><div class="cd-h"><div class="ch">🔗 Nouveau lien</div></div><div style="display:flex;gap:6px"><input class="in" id="lUrl" placeholder="URL" style="flex:1;margin:0"><input class="in" id="lName" placeholder="Nom" style="flex:2;margin:0"><button class="lb pa" onclick="saveLink()" style="padding:12px 24px">➕</button></div></div><div class="cd"><div class="cd-h"><div class="ch">📋 Mes liens</div><div class="cb" id="linksCount">0</div></div><div id="linksList"><div class="emp"><span class="ei">🔗</span>Aucun lien</div></div></div></div>
<div class="pg" id="pg-reports"><div class="cd"><div class="cd-h"><div class="ch">📑 Rapports</div><div class="cb" id="rCount">0</div></div><button class="lb pa" onclick="genReport()" style="width:100%;text-align:center;margin-bottom:10px">📊 Générer un rapport</button><div id="rList"><div class="emp"><span class="ei">📑</span>Aucun rapport</div></div></div></div>
<div class="pg" id="pg-finance"><div class="fc"><div class="fl">💰 Solde</div><div class="fb" id="fBal">0,00€</div><div class="fr"><span class="l">Commissions totales</span><span class="v g" id="fTot">0€</span></div><div class="fr"><span class="l">Ventes</span><span class="v" id="fSales2">0</span></div></div><div class="fc"><div class="cd-h"><div class="ch">⚡ Stripe</div></div><button class="lb pa" onclick="connectStripe()" style="width:100%;text-align:center;margin-bottom:8px">🔗 Connecter Stripe</button><div style="display:flex;gap:6px;align-items:center"><input type="number" class="in" id="wAmt" placeholder="Montant" style="flex:1;text-align:right;font-size:16px;margin:0"><span style="font-size:18px;font-weight:700">€</span><button class="lb pa" onclick="withdraw()" style="background:var(--danger)">💸 Retirer</button></div></div><div class="fc"><div class="cd-h"><div class="ch">🏦 Banque</div></div><input class="in" id="bName" placeholder="Titulaire"><input class="in" id="bIban" placeholder="IBAN"><button class="lb pa" onclick="saveBank()" style="width:100%;text-align:center">💾 Enregistrer</button></div><div class="fc"><div class="cd-h"><div class="ch">📋 Transactions</div></div><div id="txList"><div class="emp"><span class="ei">💸</span>Aucune</div></div></div></div>
<div class="bnav"><div class="bni active" onclick="nav('dash')"><span class="bi">📊</span><span class="bl">Bureau</span></div><div class="bni" onclick="nav('agents')"><span class="bi">👥</span><span class="bl">Agents</span></div><div class="bni" onclick="nav('links')"><span class="bi">🔗</span><span class="bl">Liens</span></div><div class="bni" onclick="nav('reports')"><span class="bi">📑</span><span class="bl">Rapp.</span></div><div class="bni" onclick="nav('finance')"><span class="bi">💰</span><span class="bl">Finance</span></div></div>
<div class="chat-modal" id="chatModal"><div class="chat-in" onclick="event.stopPropagation()"><div class="chh"><div class="cav">👨‍💼<span class="cd2"></span></div><div><div class="cn2">Marc Delacroix</div><div style="font-size:10px;color:var(--text3)">CEO</div></div><button class="cx" onclick="closeChat()">✕</button></div><div class="chat-ms" id="chatMs"><div class="msg ceo"><div class="ma" style="background:rgba(253,121,168,0.12)">👨‍💼</div><div class="mb">Bonjour ! Je suis Marc, votre CEO.</div></div></div><div class="cb"><input id="chatIn" placeholder="Question..." onkeydown="if(event.key==='Enter')sendChat()"><button onclick="sendChat()">➤</button></div></div></div>
<div class="toast-c"><div class="toast" id="toast"></div></div>
<script>
async function get(u){const r=await fetch(u);return r.ok?r.json():null}
async function post(u,d){const r=await fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:d?JSON.stringify(d):undefined});return r.ok?r.json():null}
async function init(){const u=await get('/api/user');if(!u){window.location.href='/';return}
document.getElementById('userName').textContent=u.name;await loadAll();setInterval(loadAll,5000)}
async function loadAll(){await Promise.all([loadDash(),loadAgents(),loadLinks(),loadReports(),loadFinance(),loadCEO()])}
async function loadCEO(){const r=await get('/api/ceo/message');if(!r)return
document.getElementById('ceoMsg').innerHTML=r.message.replace(/\*\*(.*?)\*\*/g,'<b>$1</b>').replace(/\n/g,'<br>')+'<br><br>💡 <b>Conseil :</b> '+r.advice}
async function loadDash(){const u=await get('/api/user');if(!u)return
document.getElementById('dLinks').textContent=u.links_count+u.contents_count
document.getElementById('dCom').textContent=u.total_commission.toFixed(2)+'€'
document.getElementById('dSales').textContent=u.total_sales
const acts=await get('/api/activity');if(!acts)return
const f=document.getElementById('actFeed');document.getElementById('actCount').textContent=acts.length+' act'
if(!acts.length){f.innerHTML='<div class="emp"><span class="ei">🚀</span>Bienvenue</div>';return}
f.innerHTML=acts.slice(0,8).map(a=>'<div style="display:flex;gap:8px;padding:6px 0;border-bottom:1px solid var(--border)"><div style="width:24px;height:24px;min-width:24px;border-radius:6px;background:rgba(108,92,231,0.08);display:flex;align-items:center;justify-content:center;font-size:10px">'+a.icon+'</div><div style="font-size:11px;line-height:1.4;color:var(--text2)"><b>'+a.title+'</b><div style="font-size:9px;color:var(--text3)">'+a.created_at+'</div></div></div>').join('')}
async function loadAgents(){const a=await get('/api/agents');if(!a)return
document.getElementById('agCount').textContent=a.length+' experts'
document.getElementById('agGrid').innerHTML=a.map(x=>'<div class="ag-card" onclick="taskAgent('+x.id+')"><div class="aa" style="background:'+x.color+'15"><span>'+x.emoji+'</span><span class="ad '+(x.status)+'"></span></div><div class="ai"><div class="an">'+x.name+'</div><div class="ar">'+x.role+'</div><div class="al">Niv.'+x.level+'</div></div><div class="as"><span class="hl">'+x.revenue_generated.toFixed(0)+'€</span>'+x.tasks_completed+' tâches<br>'+x.success_rate+'%</div></div>').join('')}
async function taskAgent(id){const r=await post('/api/agents/'+id+'/task');if(r&&r.success){showToast('✅ +'+r.earnings.toFixed(2)+'€ !');loadAll()}}
async function loadLinks(){const l=await get('/api/links');if(!l)return
document.getElementById('linksCount').textContent=l.length
const li=document.getElementById('linksList');if(!l.length){li.innerHTML='<div class="emp"><span class="ei">🔗</span>Aucun lien</div>';return}
li.innerHTML=l.slice(0,10).map(x=>'<div class="li-item"><div><div class="lin">'+x.name+'</div><div class="liu">'+x.url.slice(0,60)+'...</div></div><div class="lia"><button class="lb cp" onclick="navigator.clipboard.writeText(\''+x.url+'\').then(()=>showToast(\'📋 Copié\'))">📋</button></div></div>').join('')}
async function saveLink(){const u=document.getElementById('lUrl').value.trim(),n=document.getElementById('lName').value.trim()||'Lien';if(!u){showToast('❌ Entrez une URL');return}
const r=await post('/api/links',{name:n,url:u});if(r&&r.success){showToast('✅ Lien ajouté !');document.getElementById('lUrl').value='';document.getElementById('lName').value='';loadAll()}}
async function loadReports(){const r=await get('/api/reports');if(!r)return
document.getElementById('rCount').textContent=r.length
const l=document.getElementById('rList');if(!r.length){l.innerHTML='<div class="emp"><span class="ei">📑</span>Aucun rapport</div>';return}
l.innerHTML=r.slice(0,10).map(x=>'<div class="rp"><div class="rd">'+x.created_at+' · '+x.agent_emoji+' '+x.agent_name+'</div><div class="rt">'+x.title+'</div><div class="rb">'+x.body.replace(/\*\*(.*?)\*\*/g,'<b>$1</b>').replace(/\n/g,'<br>')+'</div></div>').join('')}
async function genReport(){showToast('📊 Génération...');const r=await post('/api/reports/generate');if(r&&r.success){showToast('✅ Rapport généré !');loadAll()}}
async function loadFinance(){const u=await get('/api/user');if(!u)return
document.getElementById('fBal').textContent=u.balance.toFixed(2)+'€';document.getElementById('fTot').textContent=u.total_commission.toFixed(2)+'€';document.getElementById('fSales2').textContent=u.total_sales
const tx=await get('/api/transactions');const tl=document.getElementById('txList')
if(!tx||!tx.length){tl.innerHTML='<div class="emp"><span class="ei">💸</span>Aucune transaction</div>';return}
tl.innerHTML=tx.slice(0,10).map(x=>'<div class="fr"><span class="l">'+x.description+'</span><span class="v '+(x.amount>0?'g':'r')+'">'+(x.amount>0?'+':'')+x.amount.toFixed(2)+'€</span></div>').join('')}
async function connectStripe(){const r=await post('/api/stripe/connect');if(r.error){showToast(r.error);return}if(r.url)window.location.href=r.url}
async function withdraw(){const a=parseFloat(document.getElementById('wAmt').value);if(!a||a<=0){showToast('❌ Montant invalide');return}
const r=await post('/api/stripe/payout',{amount:a});if(r.error){showToast(r.error);return}
showToast('💸 '+r.net.toFixed(2)+'€ virés !');document.getElementById('wAmt').value='';loadAll()}
async function saveBank(){const n=document.getElementById('bName').value.trim(),i=document.getElementById('bIban').value.trim();if(!n||!i){showToast('❌ Champs requis');return}
const r=await post('/api/bank/save',{name:n,iban:i});if(r.success)showToast('✅ Enregistré !')}
function openChat(){document.getElementById('chatModal').classList.add('active');document.getElementById('chatIn').focus()}
function closeChat(){document.getElementById('chatModal').classList.remove('active')}
document.getElementById('chatModal').addEventListener('click',function(e){if(e.target===this)closeChat()})
async function sendChat(){const inp=document.getElementById('chatIn');const msg=inp.value.trim();if(!msg)return
const ms=document.getElementById('chatMs');ms.innerHTML+='<div class="msg user"><div class="ma" style="background:rgba(108,92,231,0.12)">👤</div><div class="mb">'+msg+'</div></div>';inp.value='';ms.scrollTop=ms.scrollHeight
const r=await post('/api/ceo/chat',{message:msg});if(r&&r.response){ms.innerHTML+='<div class="msg ceo"><div class="ma" style="background:rgba(253,121,168,0.12)">👨‍💼</div><div class="mb">'+r.response.replace(/\n/g,'<br>')+'</div></div>';ms.scrollTop=ms.scrollHeight
if('speechSynthesis'in window){window.speechSynthesis.cancel();const u=new SpeechSynthesisUtterance(r.response.replace(/\*\*(.*?)\*\*/g,'$1').replace(/\n/g,' '));u.lang='fr-FR';u.rate=0.9;window.speechSynthesis.speak(u)}}}
function nav(p){document.querySelectorAll('.pg').forEach(x=>x.classList.remove('active'));document.getElementById('pg-'+p).classList.add('active')
const m=['dash','agents','links','reports','finance'];document.querySelectorAll('.nv').forEach((t,i)=>t.classList.toggle('active',m[i]===p))
document.querySelectorAll('.bni').forEach((t,i)=>t.classList.toggle('active',m[i]===p));window.scrollTo({top:0,behavior:'smooth'})}
function showToast(m){const t=document.getElementById('toast');t.innerHTML=m;t.classList.add('show');clearTimeout(t._timeout);t._timeout=setTimeout(()=>t.classList.remove('show'),3000)}
async function logout(){await post('/api/auth/logout');window.location.href='/'}
document.addEventListener('DOMContentLoaded',init)
</script></body></html>"""

# ─── LANCEMENT ────────────────────────────────────────────────────────
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"\n{'='*60}")
    print(f"  ⚡ Afflux Enterprise v{ProductionConfig.VERSION}")
    print(f"  Logiciel SaaS Professionnel d'Affiliation")
    print(f"{'='*60}")
    print(f"  🌐  http://0.0.0.0:{port}")
    print(f"  🔐  Demo: /api/auth/demo")
    print(f"  🧠  Gemini: {'✅ ACTIF' if app.config['GEMINI_API_KEY'] else '⚠️ Non configuré'}")
    print(f"  💳  Stripe: {'✅ ACTIF' if app.config['STRIPE_SECRET_KEY'] else '⚠️ Non configuré'}")
    with app.app_context(): print(f"  🤖  Agents: {Agent.query.count()} déployés")
    print(f"{'='*60}")
    print(f"\n  📋  Licence Enterprise — Valeur: 1 500€ — 2 000€")
    print(f"\n{'='*60}\n")
    app.run(host='0.0.0.0', port=port, debug=True)
