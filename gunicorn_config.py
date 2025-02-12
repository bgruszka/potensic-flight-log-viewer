bind = "0.0.0.0:8000"
workers = 3
worker_class = "sync"
timeout = 120
accesslog = "/var/log/gunicorn/access.log"
errorlog = "/var/log/gunicorn/error.log"
capture_output = True
loglevel = "info"