"""
TrendRadar SEO — news/news_fetcher.py
=======================================
Módulo de extracción de noticias desde Google News RSS.

Responsabilidades:
  - Buscar artículos relacionados a un keyword trending en Google News
  - Parsear el feed RSS con feedparser
  - Calcular relevancia del artículo vs el keyword
  - Detectar artículos "frescos" (publicados en las últimas N horas)
  - Cachear resultados para no spamear Google News (TTL configurable)

Uso:
    fetcher = NewsFetcher(geo="CO")
    articles = fetcher.fetch(keyword="inteligencia artificial", max_articles=5)
    for art in articles:
        print(art.title, art.source, art.published, art.url)
"""

import time
import logging
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional
from urllib.parse import urlencode

import requests
import feedparser

from trendradar.config import (
    NEWS_RSS_BASE,
    NEWS_MAX_ARTICLES,
    NEWS_TIMEOUT,
    NEWS_CACHE_TTL,
    NEWS_FRESH_HOURS,
    NEWS_GEO_HL,
    DEFAULT_GEO,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Estructura de datos
# ──────────────────────────────────────────────
@dataclass
class NewsArticle:
    """Representa un artículo de noticias relacionado a un trending topic."""
    title:       str
    url:         str
    source:      str
    published:   Optional[datetime]
    snippet:     str

    # Señales de calidad
    is_fresh:         bool  = False   # publicado en las últimas NEWS_FRESH_HOURS horas
    relevance_score:  float = 0.0    # 0.0-1.0 qué tan relevante al keyword

    def published_str(self) -> str:
        """Fecha de publicación formateada para display."""
        if self.published is None:
            return "—"
        now = datetime.now(tz=timezone.utc)
        delta = now - self.published
        hours = delta.total_seconds() / 3600

        if hours < 1:
            mins = int(delta.total_seconds() / 60)
            return f"hace {mins}m"
        if hours < 24:
            return f"hace {int(hours)}h"
        days = int(hours / 24)
        return f"hace {days}d"

    def __repr__(self) -> str:
        fresh = "🆕" if self.is_fresh else ""
        return f"<NewsArticle {fresh}'{self.title[:40]}...' | {self.source} | rel={self.relevance_score:.2f}>"


# ──────────────────────────────────────────────
# Cache simple en memoria
# ──────────────────────────────────────────────
class _SimpleCache:
    """Cache en memoria con TTL. No persiste entre ejecuciones."""

    def __init__(self, ttl_seconds: int = NEWS_CACHE_TTL):
        self._store: dict[str, tuple[float, list]] = {}
        self.ttl = ttl_seconds

    def get(self, key: str) -> Optional[list]:
        if key in self._store:
            ts, data = self._store[key]
            if time.time() - ts < self.ttl:
                return data
            del self._store[key]
        return None

    def set(self, key: str, data: list) -> None:
        self._store[key] = (time.time(), data)

    def clear(self) -> None:
        self._store.clear()


# Cache compartido entre instancias
_cache = _SimpleCache()


# ──────────────────────────────────────────────
# NewsFetcher
# ──────────────────────────────────────────────
class NewsFetcher:
    """
    Extrae artículos de Google News RSS para un keyword trending.

    Uso básico:
        fetcher = NewsFetcher(geo="CO")
        articles = fetcher.fetch("Petro Colombia")

    Con caché:
        fetcher = NewsFetcher(geo="CO", use_cache=True)
    """

    def __init__(
        self,
        geo:         str  = DEFAULT_GEO,
        use_cache:   bool = True,
        timeout:     int  = NEWS_TIMEOUT,
        fresh_hours: int  = NEWS_FRESH_HOURS,
    ):
        self.geo         = geo
        self.use_cache   = use_cache
        self.timeout     = timeout
        self.fresh_hours = fresh_hours
        self._hl         = NEWS_GEO_HL.get(geo, "es-419")

    def fetch(
        self,
        keyword:      str,
        max_articles: int = NEWS_MAX_ARTICLES,
        geo:          Optional[str] = None,
    ) -> list[NewsArticle]:
        """
        Busca artículos de noticias para un keyword en Google News RSS.

        Args:
            keyword:      Término de búsqueda (ej: "Copa América 2025").
            max_articles: Número máximo de artículos a retornar.
            geo:          País ISO para adaptar el idioma del feed.

        Returns:
            Lista de NewsArticle, ordenada por relevancia desc.
        """
        geo = geo or self.geo
        hl  = NEWS_GEO_HL.get(geo, "es-419")

        # ── Cache ─────────────────────────────
        cache_key = _cache_key(keyword, geo)
        if self.use_cache:
            cached = _cache.get(cache_key)
            if cached is not None:
                logger.debug("Cache hit para '%s' (geo=%s)", keyword, geo)
                return cached[:max_articles]

        # ── Construir URL del RSS ──────────────
        url = _build_rss_url(keyword, hl, geo)
        logger.info("Fetching news | keyword='%s' | url=%s", keyword, url)

        # ── Parsear feed ───────────────────────
        articles = []
        try:
            feed = self._fetch_feed(url, hl)
            entries = feed.get("entries", [])

            if not entries:
                logger.warning("Google News RSS sin resultados para '%s'", keyword)

            for entry in entries[:max_articles * 2]:   # sobreasegurar para filtrar
                article = self._parse_entry(entry, keyword)
                if article:
                    articles.append(article)

        except Exception as exc:
            logger.error("Error fetching news para '%s': %s", keyword, exc)
            return []

        # ── Ordenar por relevancia desc ────────
        articles.sort(key=lambda a: a.relevance_score, reverse=True)
        articles = articles[:max_articles]

        # ── Guardar en cache ───────────────────
        if self.use_cache:
            _cache.set(cache_key, articles)

        logger.info("  → %d artículos encontrados para '%s'", len(articles), keyword)
        return articles

    def fetch_batch(
        self,
        keywords:     list[str],
        max_articles: int = NEWS_MAX_ARTICLES,
        geo:          Optional[str] = None,
    ) -> dict[str, list[NewsArticle]]:
        """
        Fetching de noticias para múltiples keywords con pausa cortés.

        Returns:
            dict keyword → lista de NewsArticle
        """
        results = {}
        for i, kw in enumerate(keywords):
            results[kw] = self.fetch(kw, max_articles=max_articles, geo=geo)
            if i < len(keywords) - 1:
                time.sleep(0.8)  # pausa cortés entre requests
        return results

    # ── Internos ──────────────────────────────

    def _fetch_feed(self, url: str, hl: str) -> dict:
        """Descarga y parsea el feed RSS. Usa requests + feedparser."""
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept-Language": f"{hl},es;q=0.9,en;q=0.8",
        }

        resp = requests.get(url, headers=headers, timeout=self.timeout)
        resp.raise_for_status()

        feed = feedparser.parse(resp.content)
        return feed

    def _parse_entry(self, entry: dict, keyword: str) -> Optional[NewsArticle]:
        """
        Parsea una entrada del feed RSS en un NewsArticle.
        Retorna None si el entry está malformado.
        """
        try:
            title   = _clean_text(entry.get("title", ""))
            url     = _extract_url(entry)
            source  = _extract_source(entry)
            snippet = _clean_text(entry.get("summary", ""))
            pub_dt  = _parse_date(entry)

            if not title or not url:
                return None

            is_fresh = (
                pub_dt is not None
                and (datetime.now(tz=timezone.utc) - pub_dt).total_seconds()
                < self.fresh_hours * 3600
            )

            relevance = _calc_relevance(title + " " + snippet, keyword)

            return NewsArticle(
                title=title,
                url=url,
                source=source,
                published=pub_dt,
                snippet=snippet[:200] if snippet else "",
                is_fresh=is_fresh,
                relevance_score=relevance,
            )

        except Exception as exc:
            logger.debug("Error parseando entry: %s | %s", entry.get("title", "?"), exc)
            return None


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _build_rss_url(keyword: str, hl: str = "es-419", geo: str = DEFAULT_GEO) -> str:
    """
    Construye la URL del RSS de Google News para un keyword.

    Formato:
      https://news.google.com/rss/search?q=<keyword>&hl=es-419&gl=CO&ceid=CO:es
    """
    # Determinar gl (país) y ceid desde hl
    gl = (geo or DEFAULT_GEO).upper()
    lang = "es" if hl.startswith("es") else hl.split("-", 1)[0]
    ceid = f"{gl}:{lang}"

    params = {
        "q":    keyword,
        "hl":   hl,
        "gl":   gl,
        "ceid": ceid,
    }
    return f"{NEWS_RSS_BASE}?{urlencode(params)}"


def _extract_url(entry: dict) -> str:
    """Extrae la URL limpia del artículo."""
    # Google News wrappea el link; intentar el link directo primero
    link = entry.get("link", "")
    if link:
        return link
    # Fallback a id (que suele ser la URL)
    return entry.get("id", "")


def _extract_source(entry: dict) -> str:
    """Extrae el nombre de la fuente/medio del entry."""
    # Intentar source.title (feedparser lo parsea así)
    source = entry.get("source", {})
    if isinstance(source, dict):
        return source.get("title", "")

    # Fallback: extraer del título (Google News incluye '- Fuente' al final)
    title = entry.get("title", "")
    if " - " in title:
        return title.rsplit(" - ", 1)[-1].strip()

    return "—"


def _clean_text(text: str) -> str:
    """Limpia HTML básico del texto."""
    import re
    text = re.sub(r"<[^>]+>", " ", text)           # remover tags HTML
    text = re.sub(r"\s+", " ", text).strip()       # normalizar espacios
    return text


def _parse_date(entry: dict) -> Optional[datetime]:
    """
    Intenta parsear la fecha de publicación del entry RSS.
    Retorna datetime aware (UTC) o None si falla.
    """
    # feedparser ya parsea published_parsed como time.struct_time UTC
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed:
        try:
            return datetime(*parsed[:6], tzinfo=timezone.utc)
        except Exception:
            pass

    # Fallback: parsear el string manualmente
    pub_str = entry.get("published", "") or entry.get("updated", "")
    if pub_str:
        try:
            from email.utils import parsedate_to_datetime
            return parsedate_to_datetime(pub_str).astimezone(timezone.utc)
        except Exception:
            pass

    return None


def _calc_relevance(text: str, keyword: str) -> float:
    """
    Calcula un score de relevancia simple basado en coincidencia de términos.

    Estrategia:
      - Divide el keyword en palabras
      - Cuenta cuántas aparecen en el texto (case-insensitive)
      - Retorna proporción (0.0-1.0)

    Una mejora futura sería usar TF-IDF o embeddings,
    pero para velocidad de terminal este heurístico es suficiente.
    """
    if not keyword or not text:
        return 0.0

    text_lower    = text.lower()
    keyword_words = [w.strip() for w in keyword.lower().split() if len(w) > 2]

    if not keyword_words:
        return 0.5  # keyword muy corto, asumir relevante

    matches = sum(1 for w in keyword_words if w in text_lower)

    # Bonus si el keyword completo aparece en el texto
    if keyword.lower() in text_lower:
        return min(1.0, (matches / len(keyword_words)) + 0.3)

    return matches / len(keyword_words)


def _cache_key(keyword: str, geo: str) -> str:
    """Genera una clave de caché reproducible para keyword+geo."""
    raw = f"{keyword.lower().strip()}:{geo.upper()}"
    return hashlib.md5(raw.encode()).hexdigest()
