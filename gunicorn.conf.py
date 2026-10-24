import os

bind = "0.0.0.0:8000"
workers = int(os.getenv("WEB_CONCURRENCY", "3"))
timeout = 60
graceful_timeout = 30
max_requests = 1000
max_requests_jitter = 100
accesslog = "-"
errorlog = "-"
# Do not log query strings, JWTs or request bodies.
access_log_format = '%(h)s %(t)s "%(m)s %(U)s %(H)s" %(s)s %(b)s %(L)s'
forwarded_allow_ips = ""
