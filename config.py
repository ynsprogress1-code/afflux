"""
Configuration centrale d'Afflux Enterprise
"""
import os
from datetime import timedelta

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', os.urandom(64).hex())
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///afflux.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_SECURE', 'False').lower() == 'true'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = timedelta(days=30)

    # OAuth
    GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID', '')
    GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET', '')
    APPLE_CLIENT_ID = os.environ.get('APPLE_CLIENT_ID', '')
    APPLE_TEAM_ID = os.environ.get('APPLE_TEAM_ID', '')
    APPLE_KEY_ID = os.environ.get('APPLE_KEY_ID', '')
    APPLE_PRIVATE_KEY = os.environ.get('APPLE_PRIVATE_KEY', '')

    # Stripe
    STRIPE_SECRET_KEY = os.environ.get('STRIPE_SECRET_KEY', '')
    STRIPE_PUBLISHABLE_KEY = os.environ.get('STRIPE_PUBLISHABLE_KEY', '')
    STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET', '')
    STRIPE_COMMISSION_PCT = 0.10
    MIN_PAYOUT = 50.0

    # Gemini AI
    GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
    GEMINI_MODEL = os.environ.get('GEMINI_MODEL', 'gemini-1.5-flash')

    # Amazon Affiliation
    DEFAULT_AMAZON_TAG = os.environ.get('AMAZON_TAG', 'afflux-pro-21')

    # Platform
    PLATFORM_NAME = 'Afflux Enterprise'
    PLATFORM_URL = os.environ.get('PLATFORM_URL', 'https://afflux.io')
    SUPPORT_EMAIL = os.environ.get('SUPPORT_EMAIL', 'support@afflux.io')
    APP_VERSION = '3.0.0'

class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///afflux_dev.db')

class ProductionConfig(Config):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'postgresql://user:pass@localhost/afflux')

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
