FROM python:3.9-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    nginx \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy application files
COPY . /app/

# Create necessary directories
RUN mkdir -p /var/log/gunicorn /app/uploads

# Install Python dependencies
RUN python -m venv /app/venv && \
    /app/venv/bin/pip install -r requirements.txt && \
    /app/venv/bin/pip install gunicorn

# Configure Nginx
RUN echo 'server {\n\
    listen 80;\n\
    server_name localhost;\n\
    location / {\n\
        proxy_pass http://127.0.0.1:8000;\n\
        proxy_set_header Host \$host;\n\
        proxy_set_header X-Real-IP \$remote_addr;\n\
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;\n\
        proxy_set_header X-Forwarded-Proto \$scheme;\n\
        client_max_body_size 50M;\n\
    }\n\
}' > /etc/nginx/sites-available/default && \
    ln -sf /etc/nginx/sites-available/default /etc/nginx/sites-enabled/default

# Set permissions
RUN chown -R www-data:www-data /app /var/log/gunicorn

# Expose port
EXPOSE 80

# Start Nginx and Gunicorn
COPY docker-entrypoint.sh /
RUN chmod +x /docker-entrypoint.sh
ENTRYPOINT ["/docker-entrypoint.sh"]