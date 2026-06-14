"""
TrendRadar SEO — trends/fetcher.py
===================================
Módulo de conexión a Google Trends.

Responsabilidades:
  - Inicializar sesión pytrends con reintentos
  - Recuperar trending searches (real-time y diarios)
  - Recuperar datos de interés a lo largo del tiempo para un keyword
  - Detectar si un tema es "breakout" (crecimiento >100%)
  - Calcular velocidad de crecimiento relativa

Uso independiente (debug):
  python -m trendradar.trends.fetcher
"""

import time
import logging
from dataclasses import dataclass, field
from typing import Optional

import requests
from pytrends.request import TrendReq
from pytrends.exceptions import ResponseError

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


# ──────────────────────────────────────────────
# Estructuras de datos
# ──────────────────────────────────────────────
@dataclass
class TrendingTopic:
    """Representa un tema en tendencia con sus métricas crudas."""
    keyword:        str
    geo:            str
    timeframe_key:  str
    timeframe_label: str

    # Datos de interés (0-100, escala relativa de Google Trends)
    interest_peak:  int   = 0      # valor máximo en el período
    interest_avg:   float = 0.0    # promedio del período
    interest_now:   int   = 0      # valor más reciente

    # Crecimiento
    is_breakout:    bool  = False   # True si Google reporta "Breakout" (>100%)
    growth_pct:     float = 0.0    # % de crecimiento calculado manualmente

    # Metadatos
    related_queries: list = field(default_factory=list)  # top queries relacionadas
    raw_interest:    list = field(default_factory=list)  # serie temporal completa

    def __repr__(self):
        bp = "🔥BREAKOUT" if self.is_breakout else f"+{self.growth_pct:.0f}%"
        return f"<TrendingTopic '{self.keyword}' | peak={self.interest_peak} | {bp}>"


# ──────────────────────────────────────────────
# Cliente pytrends con reintentos
# ──────────────────────────────────────────────
class TrendsFetcher:
    """
    Wrapper sobre pytrends con:
      - Reintentos automáticos con backoff exponencial
      - Soporte multi-geo (Colombia, México, Argentina, etc.)
      - Retorno de objetos TrendingTopic listos para el scorer
    """

    def __init__(
        self,
        geo:      str = DEFAULT_GEO,
        lang:     str = DEFAULT_LANG,
        timeout:  tuple = PYTRENDS_TIMEOUT,
        retries:  int   = PYTRENDS_RETRIES,
        backoff:  float = PYTRENDS_BACKOFF,
    ):
        self.geo     = geo
        self.lang    = lang
        self.timeout = timeout
        self.retries = retries
        self.backoff = backoff
        self._client = self._build_client()

    # ── Inicialización ─────────────────────────
    def _build_client(self) -> TrendReq:
        """Crea sesión pytrends con configuración de timeout."""
        logger.debug("Inicializando cliente pytrends (geo=%s, lang=%s)", self.geo, self.lang)
        return TrendReq(
            hl=f"{self.lang}-{self.geo}",
            tz=300,                         # UTC-5 (Colombia)
            timeout=self.timeout,
            retries=self.retries,
            backoff_factor=self.backoff,
            requests_args={"verify": True},
        )

    def _retry(self, fn, *args, label="operación", **kwargs):
        """
        Ejecuta fn(*args, **kwargs) con reintentos y backoff exponencial.

        Manejo especial de 429 (rate-limit de Google Trends):
          - Espera más larga que el backoff normal (60s en último intento)
          - Loguea instrucción clara para el usuario
        """
        last_exc = None
        for attempt in range(1, self.retries + 1):
            try:
                return fn(*args, **kwargs)
            except Exception as exc:
                exc_str = str(exc).lower()

                # Detectar 429 explícitamente
                is_rate_limit = (
                    "429" in exc_str
                    or "too many requests" in exc_str
                    or "response code: 429" in exc_str
                )

                if is_rate_limit:
                    wait = 30 * attempt          # 30s, 60s, 90s
                    logger.warning(
                        "[%s] ⚠️  Rate limit de Google (429). "
                        "Esperando %ds antes del intento %d/%d...",
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

    # ── Trending Searches (real-time) ──────────
    def get_realtime_trending(self, geo: Optional[str] = None) -> list[str]:
        """
        Recupera los trending searches en tiempo real de Google.
        Devuelve lista de strings (keywords).

        Nota: realtime_trending_searches() no acepta timeframe —
        siempre refleja las últimas horas. Para control de intervalo
        usar get_trending_by_timeframe().
        """
        geo = geo or self.geo
        logger.info("Recuperando realtime trending | geo=%s", geo)

        df = self._retry(
            self._client.realtime_trending_searches,
            pn=geo,
            label="realtime_trending",
        )

        if df is None or df.empty:
            logger.warning("realtime_trending_searches devolvió vacío para geo=%s", geo)
            return []

        # pytrends devuelve DataFrame con columna 'title'
        keywords = df["title"].dropna().tolist()
        logger.info("  → %d trending topics encontrados", len(keywords))
        return keywords[:TOP_N_TRENDING]

    # ── Trending by Timeframe ──────────────────
    def get_trending_by_timeframe(
        self,
        keywords:       list[str],
        timeframe_key:  str = "3",
        geo:            Optional[str] = None,
        cat:            int = DEFAULT_CATEGORY,
    ) -> list[TrendingTopic]:
        """
        Para una lista de keywords, recupera su interés en el período
        seleccionado y construye objetos TrendingTopic con métricas crudas.

        Args:
            keywords:      Lista de términos (máx 5 por llamada en pytrends).
            timeframe_key: Clave del dict TIMEFRAMES (ej: "3" = último día).
            geo:           País ISO (ej: "CO"). Usa self.geo si None.
            cat:           Categoría Google Trends (0 = todas).

        Returns:
            Lista de TrendingTopic ordenada por interest_peak descendente.
        """
        geo = geo or self.geo
        tf_label, tf_value = TIMEFRAMES[timeframe_key]

        logger.info(
            "Recuperando interés | keywords=%s | geo=%s | timeframe=%s",
            keywords, geo, tf_value
        )

        # pytrends acepta máximo 5 keywords por payload
        # Si vienen más, hacemos batches de 5
        topics: list[TrendingTopic] = []
        batches = _chunk(keywords, 5)

        for batch in batches:
            self._client.build_payload(
                kw_list=batch,
                cat=cat,
                timeframe=tf_value,
                geo=geo,
                gprop="",
            )

            # Interés a lo largo del tiempo
            df_interest = self._retry(
                self._client.interest_over_time,
                label="interest_over_time",
            )

            # Consultas relacionadas (para detectar breakout)
            df_related = self._retry(
                self._client.related_queries,
                label="related_queries",
            )

            for kw in batch:
                topic = self._build_topic(
                    kw, geo, timeframe_key, tf_label,
                    df_interest, df_related,
                )
                topics.append(topic)
                logger.debug("  → %r", topic)

            # Pausa cortés entre batches para no disparar rate-limit
            if len(batches) > 1:
                time.sleep(1.2)

        # Ordenar por pico de interés, mayor primero
        topics.sort(key=lambda t: t.interest_peak, reverse=True)
        return topics

    # ── Daily Trending Searches ────────────────
    def get_daily_trending(self, geo: Optional[str] = None) -> list[str]:
        """
        Recupera los trending searches diarios (top stories del día).
        Útil para ventana de 24h cuando realtime no está disponible.
        """
        geo = geo or self.geo
        logger.info("Recuperando daily trending | geo=%s", geo)

        df = self._retry(
            self._client.today_searches,
            pn=geo,
            label="today_searches",
        )

        if df is None or df.empty:
            return []

        keywords = df.tolist() if hasattr(df, "tolist") else df["query"].tolist()
        logger.info("  → %d daily topics encontrados", len(keywords))
        return keywords[:TOP_N_TRENDING]

    # ── Builder interno ────────────────────────
    def _build_topic(
        self,
        kw:             str,
        geo:            str,
        timeframe_key:  str,
        timeframe_label: str,
        df_interest,
        df_related,
    ) -> TrendingTopic:
        """
        Construye un TrendingTopic a partir de los DataFrames de pytrends.
        Calcula peak, promedio, valor actual y velocidad de crecimiento.
        """
        topic = TrendingTopic(
            keyword=kw,
            geo=geo,
            timeframe_key=timeframe_key,
            timeframe_label=timeframe_label,
        )

        # ── Interés en el tiempo ───────────────
        if df_interest is not None and not df_interest.empty and kw in df_interest.columns:
            series = df_interest[kw].dropna()
            raw    = series.tolist()

            topic.raw_interest  = raw
            topic.interest_peak = int(series.max())
            topic.interest_avg  = round(float(series.mean()), 2)
            topic.interest_now  = int(series.iloc[-1]) if len(series) > 0 else 0

            # Velocidad: comparar primera mitad vs segunda mitad del período
            topic.growth_pct = _calc_growth(raw)

        # ── Breakout y related queries ─────────
        if df_related and kw in df_related:
            rising = df_related[kw].get("rising")
            if rising is not None and not rising.empty:
                # Guardar top 5 related queries
                topic.related_queries = rising["query"].head(5).tolist()

                # Detectar breakout: pytrends usa "Breakout" como valor en 'value'
                breakout_mask = rising["value"].astype(str).str.lower().str.contains("breakout")
                topic.is_breakout = bool(breakout_mask.any())

                # Si hay valor numérico de crecimiento, usarlo
                numeric_values = rising["value"][~breakout_mask]
                if not numeric_values.empty:
                    try:
                        max_growth = float(numeric_values.iloc[0])
                        topic.growth_pct = max(topic.growth_pct, max_growth)
                    except (ValueError, TypeError):
                        pass

        return topic

    # ── Utilidades públicas ────────────────────
    def change_geo(self, new_geo: str) -> None:
        """Cambia el país objetivo y reconstruye el cliente."""
        logger.info("Cambiando geo: %s → %s", self.geo, new_geo)
        self.geo = new_geo
        self._client = self._build_client()

    def get_trending_keywords(self, geo: Optional[str] = None) -> list[str]:
        """
        Punto de entrada unificado para obtener keywords trending.

        Estrategia con fallback automático:
          1. Intenta realtime_trending_searches (más fresco)
          2. Si falla o devuelve vacío → fallback a today_searches (diario)
          3. Si ambos fallan → lista vacía + log de error

        Args:
            geo: País ISO. Usa self.geo si None.

        Returns:
            Lista de keywords, máximo TOP_N_TRENDING items.
        """
        geo = geo or self.geo

        # Intento 1: realtime
        try:
            keywords = self.get_realtime_trending(geo=geo)
            if keywords:
                logger.info("✅ Fuente: realtime_trending (%d keywords)", len(keywords))
                return keywords
            logger.info("realtime vacío, intentando daily...")
        except Exception as exc:
            logger.warning("realtime_trending falló (%s). Intentando daily...", exc)

        # Intento 2: daily
        try:
            keywords = self.get_daily_trending(geo=geo)
            if keywords:
                logger.info("✅ Fuente: daily_trending (%d keywords)", len(keywords))
                return keywords
        except Exception as exc:
            logger.error("daily_trending también falló (%s).", exc)

        logger.error("❌ No se pudieron obtener trending keywords para geo=%s", geo)
        return []


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────
def _chunk(lst: list, size: int) -> list[list]:
    """Divide una lista en sublistas de tamaño máximo `size`."""
    return [lst[i:i + size] for i in range(0, len(lst), size)]


def _calc_growth(series: list[int | float]) -> float:
    """
    Calcula el % de crecimiento comparando la segunda mitad del período
    contra la primera mitad.

    Retorna 0.0 si no hay datos suficientes o la primera mitad es 0.
    """
    if len(series) < 4:
        return 0.0

    mid    = len(series) // 2
    first  = sum(series[:mid]) / mid
    second = sum(series[mid:]) / (len(series) - mid)

    if first == 0:
        return 100.0 if second > 0 else 0.0

    return round(((second - first) / first) * 100, 2)


def _sparkline(series: list[int | float], width: int = 8) -> str:
    """
    Convierte una serie numérica en un sparkline de caracteres Unicode.
    Ejemplo: [10, 30, 20, 80, 100] → '▁▃▂▇█'

    Útil para mostrar la forma de la curva de tendencia en la terminal.
    """
    BLOCKS = " ▁▂▃▄▅▆▇█"

    if not series:
        return " " * width

    # Reducir a `width` puntos si la serie es más larga
    if len(series) > width:
        step   = len(series) / width
        series = [series[int(i * step)] for i in range(width)]

    mn, mx = min(series), max(series)
    rng    = mx - mn or 1

    chars = [BLOCKS[int((v - mn) / rng * (len(BLOCKS) - 1))] for v in series]
    return "".join(chars)


# ──────────────────────────────────────────────
# Ejecución directa para debug
# ──────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    print("\n🔍 TrendRadar — Fetcher Debug\n")
    geo_input = input("País (CO / MX / AR / CL / PE — default CO): ").strip().upper() or "CO"

    fetcher = TrendsFetcher(geo=geo_input)

    # 1. Trending en tiempo real
    print(f"\n[1/2] Recuperando realtime trending ({geo_input})...")
    try:
        trending = fetcher.get_realtime_trending()
        if trending:
            print(f"  ✅ {len(trending)} temas encontrados:")
            for i, t in enumerate(trending[:10], 1):
                print(f"     {i:02d}. {t}")
        else:
            print("  ⚠️  Sin resultados (puede ser limitación de región)")
    except Exception as e:
        print(f"  ❌ Error: {e}")
        trending = []

    # 2. Interés detallado para los primeros 5
    if trending:
        sample = trending[:5]
        print(f"\n[2/2] Recuperando interés detallado para: {sample}")
        print("      Intervalo: Último día (now 1-d)\n")
        try:
            topics = fetcher.get_trending_by_timeframe(sample, timeframe_key="3")
            for topic in topics:
                print(f"  📊 {topic.keyword}")
                print(f"     Peak: {topic.interest_peak} | Avg: {topic.interest_avg}")
                print(f"     Ahora: {topic.interest_now} | Crecimiento: +{topic.growth_pct:.0f}%")
                print(f"     Breakout: {'🔥 SÍ' if topic.is_breakout else 'No'}")
                if topic.related_queries:
                    print(f"     Related: {', '.join(topic.related_queries[:3])}")
                print()
        except Exception as e:
            print(f"  ❌ Error en interest_over_time: {e}")
            sys.exit(1)

    print("✅ Fetcher OK\n")
