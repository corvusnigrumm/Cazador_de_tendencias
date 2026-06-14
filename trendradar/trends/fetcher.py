"""
TrendRadar SEO — trends/fetcher.py
===================================
Módulo de extracción de tendencias de Google Trends.

ARQUITECTURA DUAL:
  1. Trending keywords → RSS directo de Google Trends (NO pytrends)
     URL: https://trends.google.com/trending/rss?geo=CO
     Es 100% estable y no requiere ninguna librería especial.

  2. Interest over time → pytrends (para métricas detalladas)
     Solo se usa para build_payload + interest_over_time + related_queries
     que siguen funcionando en pytrends 4.9.2.

Responsabilidades:
  - Extraer trending keywords del RSS de Google Trends
  - Parsear tráfico aproximado y noticias embebidas en el RSS
  - Recuperar datos de interés a lo largo del tiempo (pytrends)
  - Detectar breakout y calcular velocidad de crecimiento
"""

import time
import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlencode

import requests

from trendradar.config import (
    PYTRENDS_TIMEOUT,
    PYTRENDS_RETRIES,
    PYTRENDS_BACKOFF,
    DEFAULT_GEO,
    DEFAULT_LANG,
    DEFAULT_CATEGORY,
    TOP_N_TRENDING,
    TIMEFRAMES,
)

# ──────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────
logger = logging.getLogger(__name__)

# Namespaces del RSS de Google Trends
_NS = {
    "ht": "https://trends.google.com/trending/rss",
    "atom": "http://www.w3.org/2005/Atom",
}

# URL base del RSS de tendencias de Google Trends
_TRENDS_RSS_BASE = "https://trends.google.com/trending/rss"


# ──────────────────────────────────────────────
# Estructuras de datos
# ──────────────────────────────────────────────
@dataclass
class RSSNewsItem:
    """Noticia embebida en el RSS de Google Trends."""
    title:   str
    url:     str
    source:  str
    picture: str = ""


@dataclass
class TrendingTopic:
    """Representa un tema en tendencia con sus métricas crudas."""
    keyword:         str
    geo:             str
    timeframe_key:   str
    timeframe_label: str

    # Datos de interés (0-100, escala relativa de Google Trends)
    interest_peak:  int   = 0
    interest_avg:   float = 0.0
    interest_now:   int   = 0

    # Crecimiento
    is_breakout:    bool  = False
    growth_pct:     float = 0.0

    # Tráfico del RSS (ej: "1000+", "500+")
    approx_traffic: str   = ""

    # Metadatos
    related_queries:  list = field(default_factory=list)
    raw_interest:     list = field(default_factory=list)
    rss_news:         list = field(default_factory=list)   # noticias del RSS
    published:        Optional[datetime] = None

    def __repr__(self):
        bp = "🔥BREAKOUT" if self.is_breakout else f"+{self.growth_pct:.0f}%"
        return f"<TrendingTopic '{self.keyword}' | peak={self.interest_peak} | {bp} | traffic={self.approx_traffic}>"


# ──────────────────────────────────────────────
# Cliente: RSS directo + pytrends para métricas
# ──────────────────────────────────────────────
class TrendsFetcher:
    """
    Extrae trending topics de Google Trends.

    Estrategia DUAL:
      - Trending keywords: RSS directo (100% estable, sin pytrends)
      - Métricas de interés: pytrends (interest_over_time, related_queries)
    """

    def __init__(
        self,
        geo:      str   = DEFAULT_GEO,
        lang:     str   = DEFAULT_LANG,
        timeout:  tuple = PYTRENDS_TIMEOUT,
        retries:  int   = PYTRENDS_RETRIES,
        backoff:  float = PYTRENDS_BACKOFF,
    ):
        self.geo     = geo
        self.lang    = lang
        self.timeout = timeout
        self.retries = retries
        self.backoff = backoff
        self._pytrends_client = None  # lazy init — solo cuando se necesita

    # ── pytrends lazy init ─────────────────────
    def _get_pytrends(self):
        """Inicializa pytrends solo cuando se necesita para métricas detalladas."""
        if self._pytrends_client is None:
            try:
                from pytrends.request import TrendReq
                logger.debug("Inicializando pytrends (geo=%s, lang=%s)", self.geo, self.lang)
                self._pytrends_client = TrendReq(
                    hl=f"{self.lang}-{self.geo}",
                    tz=300,
                    timeout=self.timeout,
                    retries=0,          # evitar urllib3 Retry bug
                    backoff_factor=0,
                    requests_args={"verify": True},
                )
            except Exception as exc:
                logger.warning("No se pudo inicializar pytrends: %s", exc)
                self._pytrends_client = None
        return self._pytrends_client

    # ── Retry genérico ─────────────────────────
    def _retry(self, fn, *args, label="operación", **kwargs):
        """Ejecuta fn con reintentos y backoff. Manejo especial de 429."""
        last_exc = None
        for attempt in range(1, self.retries + 1):
            try:
                return fn(*args, **kwargs)
            except Exception as exc:
                exc_str = str(exc).lower()
                is_rate_limit = "429" in exc_str or "too many requests" in exc_str

                if is_rate_limit:
                    wait = 30 * attempt
                    logger.warning(
                        "[%s] ⚠️  Rate limit (429). Esperando %ds... (%d/%d)",
                        label, wait, attempt, self.retries,
                    )
                else:
                    wait = self.backoff ** attempt
                    logger.warning(
                        "[%s] intento %d/%d falló (%s). Esperando %.1fs...",
                        label, attempt, self.retries, exc, wait,
                    )

                last_exc = exc
                time.sleep(wait)

        raise last_exc

    # ══════════════════════════════════════════════
    #  OBTENER TRENDING KEYWORDS — VÍA RSS DIRECTO
    # ══════════════════════════════════════════════

    def get_trending_keywords(self, geo: Optional[str] = None) -> list[str]:
        """
        Punto de entrada principal: extrae trending keywords del RSS de Google Trends.
        NO usa pytrends. Es 100% estable.

        Returns:
            Lista de keywords trending, máximo TOP_N_TRENDING items.
        """
        geo = geo or self.geo
        items = self._fetch_rss_items(geo)
        keywords = [item["keyword"] for item in items]
        return keywords[:TOP_N_TRENDING]

    def get_trending_with_rss_data(self, geo: Optional[str] = None) -> list[dict]:
        """
        Extrae trending keywords CON datos adicionales del RSS:
        tráfico aproximado, noticias embebidas, fecha de publicación.

        Returns:
            Lista de dicts con keys: keyword, approx_traffic, pub_date, news[]
        """
        geo = geo or self.geo
        return self._fetch_rss_items(geo)[:TOP_N_TRENDING]

    def _fetch_rss_items(self, geo: str) -> list[dict]:
        """
        Hace GET al RSS de Google Trends y parsea los items.

        URL: https://trends.google.com/trending/rss?geo=CO

        Cada item contiene:
          - title (keyword trending)
          - ht:approx_traffic ("1000+", "500+", etc.)
          - pubDate
          - ht:news_item[] (noticias relacionadas con título, URL, fuente)
        """
        url = f"{_TRENDS_RSS_BASE}?{urlencode({'geo': geo})}"
        logger.info("Fetching Google Trends RSS | geo=%s | url=%s", geo, url)

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "application/rss+xml, application/xml, text/xml",
        }

        try:
            resp = requests.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
        except Exception as exc:
            logger.error("Error al descargar RSS de Google Trends: %s", exc)
            return []

        return self._parse_rss(resp.content, geo)

    def _parse_rss(self, content: bytes, geo: str) -> list[dict]:
        """Parsea el XML del RSS de Google Trends."""
        try:
            root = ET.fromstring(content)
        except ET.ParseError as exc:
            logger.error("Error parseando XML del RSS: %s", exc)
            return []

        items = []
        for item_el in root.findall(".//item"):
            keyword = item_el.findtext("title", "").strip()
            if not keyword:
                continue

            # Tráfico aproximado
            approx_traffic = item_el.findtext("ht:approx_traffic", "", _NS).strip()

            # Fecha de publicación
            pub_str = item_el.findtext("pubDate", "")
            pub_date = None
            if pub_str:
                try:
                    from email.utils import parsedate_to_datetime
                    pub_date = parsedate_to_datetime(pub_str)
                except Exception:
                    pass

            # Noticias embebidas
            news_items = []
            for ni in item_el.findall("ht:news_item", _NS):
                news_title  = ni.findtext("ht:news_item_title", "", _NS).strip()
                news_url    = ni.findtext("ht:news_item_url", "", _NS).strip()
                news_source = ni.findtext("ht:news_item_source", "", _NS).strip()
                news_pic    = ni.findtext("ht:news_item_picture", "", _NS).strip()
                if news_title and news_url:
                    news_items.append({
                        "title":   news_title,
                        "url":     news_url,
                        "source":  news_source,
                        "picture": news_pic,
                    })

            items.append({
                "keyword":        keyword,
                "approx_traffic": approx_traffic,
                "pub_date":       pub_date,
                "news":           news_items,
                "geo":            geo,
            })

        logger.info("  → %d trending topics extraídos del RSS", len(items))
        return items

    # ══════════════════════════════════════════════
    #  MÉTRICAS DETALLADAS — VÍA PYTRENDS
    # ══════════════════════════════════════════════

    def get_trending_by_timeframe(
        self,
        keywords:       list[str],
        timeframe_key:  str = "3",
        geo:            Optional[str] = None,
        cat:            int = DEFAULT_CATEGORY,
        rss_data:       list[dict] = None,
    ) -> list[TrendingTopic]:
        """
        Para una lista de keywords, recupera interés detallado via pytrends
        y construye TrendingTopic con métricas completas.

        Si pytrends falla, devuelve TrendingTopic con los datos del RSS
        (keyword + tráfico + noticias) sin métricas de interés.

        Args:
            keywords:       Lista de términos (máx 5 por batch en pytrends).
            timeframe_key:  Clave TIMEFRAMES (ej: "3" = último día).
            geo:            País ISO. Usa self.geo si None.
            cat:            Categoría Google Trends.
            rss_data:       Datos del RSS (si ya se obtuvieron).
        """
        geo = geo or self.geo
        tf_label, tf_value = TIMEFRAMES[timeframe_key]
        rss_lookup = {}
        if rss_data:
            rss_lookup = {item["keyword"]: item for item in rss_data}

        # Intentar pytrends para métricas detalladas
        client = self._get_pytrends()
        if client is not None:
            try:
                return self._fetch_with_pytrends(
                    client, keywords, timeframe_key, tf_label, tf_value,
                    geo, cat, rss_lookup,
                )
            except Exception as exc:
                logger.warning(
                    "pytrends falló para interest_over_time: %s. "
                    "Usando solo datos del RSS.", exc
                )

        # Fallback: crear TrendingTopics con datos del RSS solamente
        logger.info("Creando TrendingTopics con datos del RSS (sin pytrends)")
        return self._build_topics_from_rss(keywords, geo, timeframe_key, tf_label, rss_lookup)

    def _fetch_with_pytrends(
        self, client, keywords, timeframe_key, tf_label, tf_value,
        geo, cat, rss_lookup,
    ) -> list[TrendingTopic]:
        """Obtiene métricas detalladas via pytrends."""
        logger.info(
            "Recuperando interés via pytrends | %d keywords | geo=%s | tf=%s",
            len(keywords), geo, tf_value,
        )

        topics: list[TrendingTopic] = []
        batches = _chunk(keywords, 5)

        for batch in batches:
            client.build_payload(
                kw_list=batch, cat=cat,
                timeframe=tf_value, geo=geo, gprop="",
            )

            df_interest = self._retry(
                client.interest_over_time,
                label="interest_over_time",
            )

            try:
                df_related = self._retry(
                    client.related_queries,
                    label="related_queries",
                )
            except Exception:
                df_related = None

            for kw in batch:
                topic = self._build_topic(
                    kw, geo, timeframe_key, tf_label,
                    df_interest, df_related,
                )
                # Enriquecer con datos RSS
                rss = rss_lookup.get(kw, {})
                topic.approx_traffic = rss.get("approx_traffic", "")
                topic.published = rss.get("pub_date")
                topic.rss_news = [
                    RSSNewsItem(**n) for n in rss.get("news", [])
                ]
                topics.append(topic)
                logger.debug("  → %r", topic)

            if len(batches) > 1:
                time.sleep(1.5)

        topics.sort(key=lambda t: t.interest_peak, reverse=True)
        return topics

    def _build_topics_from_rss(
        self, keywords, geo, timeframe_key, tf_label, rss_lookup,
    ) -> list[TrendingTopic]:
        """Crea TrendingTopics usando solo datos del RSS (sin pytrends)."""
        topics = []
        for kw in keywords:
            rss = rss_lookup.get(kw, {})

            # Estimar interés a partir del tráfico aproximado
            traffic_str = rss.get("approx_traffic", "0")
            estimated_interest = _traffic_to_interest(traffic_str)

            topic = TrendingTopic(
                keyword=kw,
                geo=geo,
                timeframe_key=timeframe_key,
                timeframe_label=tf_label,
                interest_peak=estimated_interest,
                interest_avg=float(estimated_interest * 0.7),
                interest_now=estimated_interest,
                growth_pct=_traffic_to_growth(traffic_str),
                raw_interest=_synthetic_interest_curve(estimated_interest),
                approx_traffic=traffic_str,
                published=rss.get("pub_date"),
                rss_news=[RSSNewsItem(**n) for n in rss.get("news", [])],
            )
            topics.append(topic)

        # Ordenar por tráfico estimado descendente
        topics.sort(key=lambda t: t.interest_peak, reverse=True)
        return topics

    # ── Builder de TrendingTopic (con pytrends data) ──
    def _build_topic(
        self, kw, geo, timeframe_key, timeframe_label,
        df_interest, df_related,
    ) -> TrendingTopic:
        """Construye TrendingTopic desde DataFrames de pytrends."""
        topic = TrendingTopic(
            keyword=kw, geo=geo,
            timeframe_key=timeframe_key,
            timeframe_label=timeframe_label,
        )

        if df_interest is not None and not df_interest.empty and kw in df_interest.columns:
            series = df_interest[kw].dropna()
            raw = series.tolist()
            topic.raw_interest  = raw
            topic.interest_peak = int(series.max())
            topic.interest_avg  = round(float(series.mean()), 2)
            topic.interest_now  = int(series.iloc[-1]) if len(series) > 0 else 0
            topic.growth_pct    = _calc_growth(raw)

        if df_related and kw in df_related:
            rising = df_related[kw].get("rising")
            if rising is not None and not rising.empty:
                topic.related_queries = rising["query"].head(5).tolist()
                breakout_mask = rising["value"].astype(str).str.lower().str.contains("breakout")
                topic.is_breakout = bool(breakout_mask.any())
                numeric_values = rising["value"][~breakout_mask]
                if not numeric_values.empty:
                    try:
                        topic.growth_pct = max(topic.growth_pct, _cap_growth(float(numeric_values.iloc[0])))
                    except (ValueError, TypeError):
                        pass

        return topic

    # ── Utilidades ─────────────────────────────
    def change_geo(self, new_geo: str) -> None:
        """Cambia el país objetivo. Resetea pytrends."""
        logger.info("Cambiando geo: %s → %s", self.geo, new_geo)
        self.geo = new_geo
        self._pytrends_client = None


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────
def _chunk(lst: list, size: int) -> list[list]:
    """Divide una lista en sublistas de tamaño máximo `size`."""
    return [lst[i:i + size] for i in range(0, len(lst), size)]


def _calc_growth(series: list) -> float:
    """% de crecimiento: segunda mitad vs primera mitad del período."""
    if len(series) < 4:
        return 0.0
    mid    = len(series) // 2
    first  = sum(series[:mid]) / mid
    second = sum(series[mid:]) / (len(series) - mid)
    if first == 0:
        return 100.0 if second > 0 else 0.0
    return _cap_growth(((second - first) / first) * 100)


def _cap_growth(value: float, max_pct: float = 1000.0) -> float:
    """Evita porcentajes ilegibles cuando la base inicial es casi cero."""
    return round(max(-100.0, min(max_pct, value)), 2)


def _traffic_to_interest(traffic_str: str) -> int:
    """
    Convierte el tráfico aproximado del RSS ("1000+", "500+", "200+")
    a un valor de interés estimado (0-100).

    Mapeo heurístico:
      200+   → 30
      500+   → 50
      1000+  → 70
      2000+  → 80
      5000+  → 90
      10000+ → 95
      50000+ → 100
    """
    try:
        num = int(traffic_str.replace("+", "").replace(",", "").strip())
    except (ValueError, AttributeError):
        return 20  # default bajo

    if num >= 50000:
        return 100
    if num >= 10000:
        return 95
    if num >= 5000:
        return 90
    if num >= 2000:
        return 80
    if num >= 1000:
        return 70
    if num >= 500:
        return 50
    if num >= 200:
        return 30
    return 20


def _traffic_to_growth(traffic_str: str) -> float:
    """Estima crecimiento cuando solo hay datos del RSS."""
    try:
        num = int(traffic_str.replace("+", "").replace(",", "").strip())
    except (ValueError, AttributeError):
        return 0.0

    if num >= 10000:
        return 120.0
    if num >= 5000:
        return 90.0
    if num >= 2000:
        return 70.0
    if num >= 1000:
        return 50.0
    if num >= 500:
        return 30.0
    if num >= 200:
        return 15.0
    return 5.0


def _synthetic_interest_curve(interest: int) -> list[int]:
    """
    Curva minima para que el fallback RSS conserve senales de momentum.
    pytrends sigue siendo la fuente preferida cuando esta disponible.
    """
    interest = max(0, min(100, int(interest)))
    multipliers = (0.25, 0.35, 0.50, 0.70, 0.85, 1.0)
    return [max(1, round(interest * m)) for m in multipliers]


def _sparkline(series: list, width: int = 8) -> str:
    """
    Convierte una serie numérica en un sparkline Unicode.
    Ejemplo: [10, 30, 20, 80, 100] → '▁▃▂▇█'
    """
    BLOCKS = " ▁▂▃▄▅▆▇█"

    if not series:
        return " " * width

    if len(series) > width:
        step   = len(series) / width
        series = [series[int(i * step)] for i in range(width)]

    mn, mx = min(series), max(series)
    rng    = mx - mn or 1

    chars = [BLOCKS[int((v - mn) / rng * (len(BLOCKS) - 1))] for v in series]
    return "".join(chars)
