"""Gunicorn configuration for production."""
bind = "0.0.0.0:$PORT"
workers = 2
threads = 2
timeout = 120
graceful_timeout = 30
keepalive = 5
accesslog = "-"
errorlog = "-"
loglevel = "info"
preload_app = True
