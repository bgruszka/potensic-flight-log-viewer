#!/bin/bash

# Start Nginx
nginx

# Start Gunicorn
cd /app
/app/venv/bin/gunicorn -c gunicorn_config.py app:app