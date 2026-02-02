# Watch MY Bag Scraper - Dockerfile
# Imagen base con Python 3.11
FROM python:3.11-slim

# Metadatos
LABEL maintainer="Watch MY Bag Scraper"
LABEL description="Aplicación de scraping y monitoreo de relojes en marketplaces"
LABEL version="1.0"

# Variables de entorno
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive

# Directorio de trabajo
WORKDIR /app

# Instalar dependencias del sistema necesarias para Playwright
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Dependencias básicas
    wget \
    gnupg \
    ca-certificates \
    # Dependencias para Playwright/Chromium
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxkbcommon0 \
    libatspi2.0-0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    # Fuentes
    fonts-liberation \
    fonts-noto-color-emoji \
    # Limpieza
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements primero (para cache de Docker)
COPY requirements.txt .

# Instalar dependencias de Python
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Instalar navegadores de Playwright
RUN playwright install chromium && \
    playwright install-deps chromium

# Copiar el código de la aplicación
COPY . .

# Crear directorios necesarios
RUN mkdir -p data/exports data/images logs

# Exponer puerto para el dashboard de Streamlit
EXPOSE 8501

# Script de entrada por defecto (dashboard)
CMD ["streamlit", "run", "dashboard.py", "--server.port=8501", "--server.address=0.0.0.0"]
