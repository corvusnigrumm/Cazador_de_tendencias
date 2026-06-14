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
    "todas":          0,
    "noticias":       16,
    "entretenimiento": 3,
    "deportes":       20,
    "negocios":       12,
    "tecnología":     5,
    "ciencia":        8,
    "salud":          45,
    "política":       396,
}

DEFAULT_CATEGORY = 0

# ──────────────────────────────────────────────
# SCORING SEO / DISCOVER
# ──────────────────────────────────────────────
# Pesos para el cálculo del TrendScore (deben sumar 1.0)
SCORE_WEIGHTS = {
    "interest_peak":    0.35,   # valor máximo de interés (0-100)
    "growth_velocity":  0.30,   # velocidad de crecimiento (breakout = 100%)
    "news_coverage":    0.20,   # cobertura de medios relacionados
    "recency":          0.15,   # qué tan reciente es el pico de tendencia
}

# Umbral mínimo de TrendScore para ser marcado como "Alto potencial Discover"
DISCOVER_THRESHOLD = 65

# ──────────────────────────────────────────────
# NOTICIAS RELACIONADAS (Google News RSS)
# ──────────────────────────────────────────────
NEWS_RSS_BASE = "https://news.google.com/rss/search"
NEWS_MAX_ARTICLES = 5          # artículos por tema trending
NEWS_TIMEOUT = 8               # segundos

# ──────────────────────────────────────────────
# OUTPUT
# ──────────────────────────────────────────────
OUTPUT_DIR = "exports"
CSV_FILENAME = "trendradar_export.csv"
JSON_FILENAME = "trendradar_export.json"
