"""
TrendRadar SEO — Configuración central
Ajusta aquí los parámetros de región, idioma e intervalos.
"""

# ──────────────────────────────────────────────
# GEOGRAFÍA
# ──────────────────────────────────────────────
# Códigos ISO 3166-1 alpha-2 para los países objetivo
# Google Trends usa estos mismos códigos
GEO_TARGETS = {
    "colombia":    "CO",
    "mexico":      "MX",
    "argentina":   "AR",
    "chile":       "CL",
    "peru":        "PE",
    "venezuela":   "VE",
    "ecuador":     "EC",
    "españa":      "ES",
    "latam":       "",          # string vacío = tendencias globales
}

# País por defecto al arrancar
DEFAULT_GEO = "CO"

# Idioma de la interfaz de pytrends
DEFAULT_LANG = "es"

# ──────────────────────────────────────────────
# INTERVALOS DE TIEMPO
# ──────────────────────────────────────────────
# Formato pytrends: https://pytrends.readthedocs.io
TIMEFRAMES = {
    "1":  ("Última hora",         "now 1-H"),
    "2":  ("Últimas 4 horas",     "now 4-H"),
    "3":  ("Último día",          "now 1-d"),
    "4":  ("Última semana",       "now 7-d"),
    "5":  ("Último mes",          "today 1-m"),
    "6":  ("Últimos 3 meses",     "today 3-m"),
}

# ──────────────────────────────────────────────
# PYTRENDS
# ──────────────────────────────────────────────
PYTRENDS_TIMEOUT  = (10, 25)   # (connect_timeout, read_timeout) en segundos
PYTRENDS_RETRIES  = 3
PYTRENDS_BACKOFF  = 1.5        # factor de espera entre reintentos

# Número de trending topics a recuperar por consulta
TOP_N_TRENDING = 20

# ──────────────────────────────────────────────
# CATEGORÍAS DE GOOGLE TRENDS
# ──────────────────────────────────────────────
# 0 = todas las categorías (default para SEO amplio)
# Referencia: https://github.com/pat310/google-trends-api/wiki/Google-Trends-Categories
CATEGORIES = {
    "todas":           0,
    "noticias":        16,
    "entretenimiento": 3,
    "deportes":        20,
    "negocios":        12,
    "tecnología":      5,
    "ciencia":         8,
    "salud":           45,
    "política":        396,
}

DEFAULT_CATEGORY = 0

# ──────────────────────────────────────────────
# SCORING SEO / DISCOVER
# ──────────────────────────────────────────────
# ── Pesos del Algoritmo TrendScore ───────────────
# Google Discover prioriza fuertemente la frescura extrema y los picos repentinos
SCORE_WEIGHTS = {
    "peak":     0.25,  # Pico de interés histórico reciente (25%) - Reducido
    "velocity": 0.40,  # Velocidad de crecimiento / Breakout (40%) - Aumentado
    "curve":    0.10,  # Forma de la curva (10%)
    "momentum": 0.25,  # Momentum actual (qué tan caliente está AHORA) (25%) - Aumentado
}

# ── Umbrales Discover ──────────────────────────
DISCOVER_THRESHOLD_HIGH = 70.0  # Más exigente para asegurar impacto real
DISCOVER_THRESHOLD_MED  = 50.0

# ──────────────────────────────────────────────
# NOTICIAS RELACIONADAS (Google News RSS)
# ──────────────────────────────────────────────
NEWS_RSS_BASE     = "https://news.google.com/rss/search"
NEWS_MAX_ARTICLES = 5          # artículos por tema trending
NEWS_TIMEOUT      = 8          # segundos por petición
NEWS_CACHE_TTL    = 900        # segundos (15 min) de cache por keyword
NEWS_FRESH_HOURS  = 6          # horas para considerar artículo "fresco"

# Mapeo geo → hl (language-region) para Google News
NEWS_GEO_HL = {
    "CO": "es-419",
    "MX": "es-419",
    "AR": "es-419",
    "CL": "es-419",
    "PE": "es-419",
    "VE": "es-419",
    "EC": "es-419",
    "ES": "es",
    "":   "es-419",   # LATAM global
}

# ──────────────────────────────────────────────
# OUTPUT
# ──────────────────────────────────────────────
OUTPUT_DIR    = "exports"
CSV_FILENAME  = "trendradar_export.csv"
JSON_FILENAME = "trendradar_export.json"
