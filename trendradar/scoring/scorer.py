"""
TrendRadar SEO — scoring/scorer.py
===================================
Calcula el TrendScore (0-100) y las señales de Discover para cada TrendingTopic.

Arquitectura del score
──────────────────────
El TrendScore combina cuatro dimensiones con pesos configurables en config.py:

  [1] INTEREST PEAK (35%)
      Normaliza el pico de interés de Google Trends (0-100 → 0-35 pts).
      Un pico de 100 aporta los 35 pts completos.

  [2] GROWTH VELOCITY (30%)
      Mide la velocidad de crecimiento de la tendencia:
        - Breakout (>100% o marcado por Google): 30 pts
        - >50%: escala lineal hasta 30 pts
        - 0-50%: escala reducida
        - Negativo: 0 pts

  [3] CURVE SHAPE (15%)  ← reemplaza "recency" del config original
      Analiza la FORMA de la serie temporal para saber en qué punto del
      ciclo está el tema:
        - Subiendo ahora mismo (cola derecha > promedio): máximos pts
        - Pico reciente (últimos 2 puntos ≥ 80% del peak): alto
        - Ya bajando pero todavía relevante: medio
        - Caída sostenida: bajo

  [4] MOMENTUM (20%)  ← antes "news_coverage", ahora basado en datos reales
      Compara el valor actual vs el promedio del período:
        - interest_now >> interest_avg → tendencia acelerando → alto
        - interest_now ≈ interest_avg → estable
        - interest_now << interest_avg → ya pasó el pico

Señales de Discover
──────────────────────
Además del score numérico, se calculan señales booleanas específicas
para Google Discover:

  · is_fresh_trend     → pico en las últimas 24-48h (ventana corta)
  · is_accelerating    → curva sigue subiendo en el último tercio
  · is_sustained       → interés alto y sostenido (>48h en peak)
  · has_breakout       → breakout confirmado por Google
  · discover_tier      → "ALTO" / "MEDIO" / "BAJO" según TrendScore

Salida
──────
Devuelve objetos ScoredTopic que envuelven al TrendingTopic original
y añaden las métricas calculadas. El TrendingTopic nunca se modifica.
"""

import math
from dataclasses import dataclass, field
from typing import Optional

from trendradar.config import SCORE_WEIGHTS, DISCOVER_THRESHOLD_HIGH
from trendradar.trends.fetcher import TrendingTopic


# ──────────────────────────────────────────────
# Estructura de salida
# ──────────────────────────────────────────────
@dataclass
class ScoredTopic:
    """
    TrendingTopic enriquecido con TrendScore y señales de Discover.
    El campo `topic` contiene el objeto original sin modificar.
    """
    topic: TrendingTopic

    # Score total (0-100)
    trend_score: float = 0.0

    # Componentes individuales (0-100 cada uno, antes de aplicar peso)
    score_peak:     float = 0.0   # dimensión 1: interest peak
    score_velocity: float = 0.0   # dimensión 2: growth velocity
    score_curve:    float = 0.0   # dimensión 3: curve shape
    score_momentum: float = 0.0   # dimensión 4: momentum

    # Señales Discover
    is_fresh_trend:   bool = False
    is_accelerating:  bool = False
    is_sustained:     bool = False
    has_breakout:     bool = False
    discover_tier:    str  = "BAJO"   # "ALTO" | "MEDIO" | "BAJO"

    # Recomendación editorial
    recommendation:   str  = ""

    # Atajos de acceso al topic original (para la UI)
    @property
    def keyword(self) -> str:
        return self.topic.keyword

    @property
    def geo(self) -> str:
        return self.topic.geo

    @property
    def timeframe_label(self) -> str:
        return self.topic.timeframe_label

    @property
    def interest_peak(self) -> int:
        return self.topic.interest_peak

    @property
    def interest_now(self) -> int:
        return self.topic.interest_now

    @property
    def interest_avg(self) -> float:
        return self.topic.interest_avg

    @property
    def growth_pct(self) -> float:
        return self.topic.growth_pct

    @property
    def is_breakout(self) -> bool:
        return self.topic.is_breakout

    @property
    def related_queries(self) -> list:
        return self.topic.related_queries

    @property
    def raw_interest(self) -> list:
        return self.topic.raw_interest

    def __repr__(self) -> str:
        return (
            f"<ScoredTopic '{self.keyword}' | "
            f"score={self.trend_score:.1f} | tier={self.discover_tier}>"
        )


# ──────────────────────────────────────────────
# Scorer principal
# ──────────────────────────────────────────────
class TrendScorer:
    """
    Calcula el TrendScore y las señales de Discover para una lista
    de TrendingTopic.

    Uso:
        scorer = TrendScorer()
        scored = scorer.score_all(topics)
        # scored es list[ScoredTopic], ordenada por trend_score desc
    """

    def __init__(self, weights: Optional[dict] = None, threshold: Optional[int] = None):
        # Pesos configurables (default desde config.py)
        self.weights   = weights   or SCORE_WEIGHTS
        self.threshold = threshold or DISCOVER_THRESHOLD_HIGH
        self._validate_weights()

    def _validate_weights(self) -> None:
        total = sum(self.weights.values())
        if not math.isclose(total, 1.0, abs_tol=0.01):
            raise ValueError(
                f"Los pesos del scorer deben sumar 1.0. Suma actual: {total:.3f}"
            )

    # ── Entry point ────────────────────────────
    def score_all(self, topics: list[TrendingTopic]) -> list["ScoredTopic"]:
        """
        Calcula el score para todos los topics y los devuelve ordenados
        de mayor a menor TrendScore.
        """
        scored = [self._score_one(t) for t in topics]
        scored.sort(key=lambda s: s.trend_score, reverse=True)
        return scored

    def score_one(self, topic: TrendingTopic) -> "ScoredTopic":
        """Versión pública para puntuar un topic individual."""
        return self._score_one(topic)

    # ── Scorer individual ──────────────────────
    def _score_one(self, topic: TrendingTopic) -> "ScoredTopic":
        scored = ScoredTopic(topic=topic)

        # ── Dimensión 1: Interest Peak ─────────
        scored.score_peak = _norm_peak(topic.interest_peak)

        # ── Dimensión 2: Growth Velocity ───────
        scored.score_velocity = _norm_velocity(topic.growth_pct, topic.is_breakout)

        # ── Dimensión 3: Curve Shape ───────────
        scored.score_curve = _norm_curve(topic.raw_interest)

        # ── Dimensión 4: Momentum ──────────────
        scored.score_momentum = _norm_momentum(topic.interest_now, topic.interest_avg)

        # ── TrendScore ponderado ───────────────
        w = self.weights
        scored.trend_score = round(
            scored.score_peak     * w.get("peak",   0.25)
            + scored.score_velocity * w.get("velocity", 0.40)
            + scored.score_curve    * w.get("curve",    0.10)
            + scored.score_momentum * w.get("momentum", 0.25),
            1,
        )

        # ── Señales Discover ───────────────────
        scored.has_breakout    = topic.is_breakout
        scored.is_accelerating = _is_accelerating(topic.raw_interest)
        scored.is_fresh_trend  = _is_fresh(topic.raw_interest, topic.interest_peak)
        scored.is_sustained    = _is_sustained(topic.raw_interest, topic.interest_peak)

        # ── Tier y recomendación ───────────────
        scored.discover_tier   = _tier(scored.trend_score, self.threshold)
        scored.recommendation  = _recommendation(scored)

        return scored


# ──────────────────────────────────────────────
# Funciones de normalización (0 → 100)
# ──────────────────────────────────────────────

def _norm_peak(peak: int) -> float:
    """
    El peak de Google Trends ya está en escala 0-100.
    Lo devolvemos directamente como componente.
    """
    return float(max(0, min(100, peak)))


def _norm_velocity(growth_pct: float, is_breakout: bool) -> float:
    """
    Normaliza la velocidad de crecimiento a 0-100.

    Curva de puntuación:
      - Breakout (Google lo marca como tal): 100 pts
      - >200%: 95 pts
      - 100-200%: 80-95 pts (interpolación lineal)
      - 50-100%: 60-80 pts
      - 0-50%: 0-60 pts (escala reducida)
      - Negativo: 0 pts
    """
    if is_breakout:
        return 100.0

    g = growth_pct
    if g <= 0:
        return 0.0
    if g > 200:
        return 95.0
    if g > 100:
        # 100-200% → 80-95
        return 80.0 + (g - 100) / 100 * 15
    if g > 50:
        # 50-100% → 60-80
        return 60.0 + (g - 50) / 50 * 20
    # 0-50% → 0-60
    return g / 50 * 60


def _norm_curve(series: list) -> float:
    """
    Analiza la forma de la curva de interés para detectar en qué
    punto del ciclo está el tema.

    Lógica:
      1. Divide la serie en tres tercios: inicio, medio, final
      2. Compara el tercio final vs los anteriores
      3. Más alto el final → más puntos (el tema sigue subiendo ahora)

    Casos especiales:
      - Serie vacía o muy corta: 50 pts (neutral)
      - Último punto = pico máximo: 100 pts (subiendo ahora mismo)
      - Pico en el último tercio: 80-100 pts
      - Pico en el tercio medio: 40-60 pts (ya pasó el mejor momento)
      - Pico en el primer tercio: 10-30 pts (tendencia vieja)
    """
    if not series or len(series) < 3:
        return 50.0

    n    = len(series)
    peak = max(series)
    if peak == 0:
        return 0.0

    # Serie sin varianza (todos los valores iguales) → neutral
    if len(set(series)) == 1:
        return 50.0

    # Índice de la ÚLTIMA ocurrencia del pico
    peak_idx      = max(i for i, v in enumerate(series) if v == peak)
    peak_position = peak_idx / (n - 1)   # 0.0=inicio, 1.0=final

    # Promedios del último tercio vs los dos tercios anteriores
    cut       = max(1, n * 2 // 3)
    avg_early = sum(series[:cut]) / cut
    avg_late  = sum(series[cut:]) / (n - cut) if n - cut > 0 else avg_early
    is_truly_rising = avg_late > avg_early * 1.05   # 5% de margen

    # ¿El último valor es el pico Y realmente está subiendo?
    if series[-1] == peak and peak_position >= 0.5 and is_truly_rising:
        return 100.0

    # ¿El pico está en el último tercio?
    if peak_position >= 0.66:
        # Escalar según cuánto cayó desde el pico al final
        drop = (peak - series[-1]) / peak
        return max(70.0, 100.0 - drop * 40)

    # ¿Pico en el tercio medio?
    if peak_position >= 0.33:
        drop = (peak - series[-1]) / peak
        return max(30.0, 60.0 - drop * 40)

    # Pico en el primer tercio → tendencia vieja
    drop = (peak - series[-1]) / peak
    return max(5.0, 30.0 - drop * 25)


def _norm_momentum(interest_now: int, interest_avg: float) -> float:
    """
    Compara el valor actual con el promedio del período para medir
    el momentum actual del tema.

    Ratio = interest_now / interest_avg
      - ratio > 1.5 → acelerando fuerte (100 pts)
      - ratio 1.0-1.5 → creciendo (60-100 pts)
      - ratio ≈ 1.0 → estable (50 pts)
      - ratio < 1.0 → desacelerando (0-50 pts)
    """
    if interest_avg <= 0:
        return float(interest_now)    # sin referencia, usar valor directo

    ratio = interest_now / interest_avg

    if ratio >= 1.5:
        return 100.0
    if ratio >= 1.0:
        # 1.0-1.5 → 50-100 pts (lineal)
        return 50.0 + (ratio - 1.0) / 0.5 * 50
    # < 1.0 → 0-50 pts
    return max(0.0, ratio / 1.0 * 50)


# ──────────────────────────────────────────────
# Señales Discover
# ──────────────────────────────────────────────

def _is_accelerating(series: list) -> bool:
    """
    True si el último tercio de la serie tiene promedio mayor que
    el promedio global → el tema sigue ganando velocidad.
    """
    if len(series) < 4:
        return False
    n          = len(series)
    last_third = series[-(n // 3):]
    avg_all    = sum(series) / n
    avg_last   = sum(last_third) / len(last_third)
    return avg_last > avg_all * 1.1   # 10% por encima del promedio


def _is_fresh(series: list, peak: int) -> bool:
    """
    True si el pico ocurrió en el último cuarto de la serie.
    Indica que la tendencia es reciente y tiene recorrido.
    """
    if not series or peak == 0:
        return False
    n      = len(series)
    last_q = series[-(max(1, n // 4)):]
    return peak in last_q


def _is_sustained(series: list, peak: int) -> bool:
    """
    True si la serie mantiene valores altos (≥70% del peak) durante
    al menos la mitad del período → tema con permanencia, ideal para
    Discover que premia contenido con engagement prolongado.
    """
    if not series or peak == 0:
        return False
    threshold  = peak * 0.70
    high_count = sum(1 for v in series if v >= threshold)
    return high_count >= len(series) / 2


# ──────────────────────────────────────────────
# Tier y recomendación editorial
# ──────────────────────────────────────────────

def _tier(score: float, threshold: int) -> str:
    """
    Clasifica el TrendScore en tres tiers de potencial Discover.

      ALTO  → score >= threshold      (≥65 por defecto)
      MEDIO → score >= threshold - 20 (≥45)
      BAJO  → resto
    """
    if score >= threshold:
        return "ALTO"
    if score >= threshold - 20:
        return "MEDIO"
    return "BAJO"


def _recommendation(s: "ScoredTopic") -> str:
    """
    Genera una recomendación editorial corta y accionable basada en
    la combinación de señales del ScoredTopic.

    Prioridad: breakout > acelerando+fresco > sostenido > en declive
    """
    if s.has_breakout and s.is_fresh_trend:
        return "🔥 Publicar YA — breakout activo, ventana de minutos"

    if s.has_breakout:
        return "🔥 Publicar urgente — breakout confirmado por Google"

    if s.is_accelerating and s.is_fresh_trend:
        return "🚀 Alta prioridad — tendencia fresca y en aceleración"

    if s.is_accelerating:
        return "📈 Prioridad alta — el tema sigue subiendo ahora"

    if s.is_fresh_trend and s.discover_tier == "ALTO":
        return "⚡ Buena ventana — tendencia reciente, potencial Discover alto"

    if s.is_sustained and s.discover_tier in ("ALTO", "MEDIO"):
        return "📌 Tema sostenido — buen candidato para nota de profundidad"

    if s.discover_tier == "MEDIO":
        return "👀 Monitorear — relevante pero ya pasó el pico más fuerte"

    if s.interest_peak < 30:
        return "🔇 Interés bajo — descartar salvo nicho específico"

    return "⏳ En declive — considerar ángulo diferenciador si se cubre"
