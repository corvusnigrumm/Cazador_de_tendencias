# 📡 TrendRadar SEO

> Herramienta de inteligencia de tendencias basada en Google Trends para maximizar el potencial SEO en Google Discover.

---

## ¿Qué hace?

- 🔍 **Extrae trending topics** en tiempo real desde Google Trends (Colombia, México, Argentina, Chile, Perú, Venezuela, Ecuador, España y LATAM global)
- 📊 **Calcula TrendScore** (0-100) con 4 dimensiones: interés peak, velocidad de crecimiento, forma de la curva y momentum actual
- 🏆 **Clasifica potencial Discover** en tiers: ALTO / MEDIO / BAJO con señales específicas (Breakout, Acelerando, Fresco, Sostenido)
- 📰 **Busca noticias relacionadas** en Google News RSS con detección de artículos frescos (< 6 horas)
- 📤 **Exporta** los resultados a CSV y JSON con estructura completa

---

## Instalación

```bash
# 1. Clonar / descargar el proyecto
cd "VIOLADOR DE TENDENCIAS"

# 2. Crear entorno virtual (recomendado)
python -m venv venv
venv\Scripts\activate      # Windows
# source venv/bin/activate  # Mac/Linux

# 3. Instalar dependencias
pip install -r requirements.txt
```

---

## Uso

```bash
python main.py
```

El programa te guía con menús interactivos:

```
┌─ País / Región ──────────────────────────
│  [1] Colombia (CO)
│  [2] México (MX)
│  [3] Argentina (AR)
│  [4] Chile (CL)
│  [5] Perú (PE)
│  ...
└──────────────────────────────────────────

┌─ Intervalo de Tiempo ────────────────────
│  [1] Última hora       now 1-H
│  [2] Últimas 4 horas   now 4-H
│  [3] Último día        now 1-d
│  [4] Última semana     now 7-d
│  [5] Último mes        today 1-m
│  [6] Últimos 3 meses   today 3-m
└──────────────────────────────────────────

┌─ Categoría ──────────────────────────────
│  [1] Todas
│  [2] Noticias
│  [3] Entretenimiento
│  [4] Deportes
│  ...
└──────────────────────────────────────────
```

---

## Estructura del proyecto

```
VIOLADOR DE TENDENCIAS/
├── main.py                          ← Entry point principal
├── requirements.txt
├── README.md
└── trendradar/                      ← Paquete Python principal
    ├── config.py                    ← Configuración central
    ├── trends/
    │   └── fetcher.py               ← Conexión a Google Trends (pytrends)
    ├── scoring/
    │   └── scorer.py                ← Cálculo de TrendScore y señales Discover
    ├── news/
    │   └── news_fetcher.py          ← Fetching Google News RSS
    └── output/
        ├── display.py               ← Renderizado Rich en terminal
        └── exporter.py              ← Exportación CSV / JSON
```

---

## TrendScore — Cómo se calcula

| Dimensión       | Peso | Descripción |
|-----------------|------|-------------|
| Interest Peak   | 35%  | Pico de interés en Google Trends (0-100) |
| Growth Velocity | 30%  | Velocidad de crecimiento; Breakout = máximo |
| Curve Shape     | 15%  | En qué punto del ciclo está el tema |
| Momentum        | 20%  | ¿Está subiendo o bajando ahora mismo? |

### Señales Discover

| Señal              | Significado |
|--------------------|-------------|
| 🔥 Breakout        | Google lo marca con crecimiento >100% — publicar YA |
| 🚀 Acelerando      | El último tercio del período supera el promedio global |
| ⚡ Tendencia fresca | El pico ocurrió en el último cuarto del período |
| 📌 Sostenida       | Mantiene >70% del peak durante más de la mitad del período |

### Tiers de Discover

| Tier  | Score     | Acción |
|-------|-----------|--------|
| ALTO  | ≥ 65/100  | Publicar en las próximas horas |
| MEDIO | ≥ 45/100  | Monitorear, considerar ángulo diferenciador |
| BAJO  | < 45/100  | Descartar salvo nicho específico |

---

## Exportación

Los archivos se guardan en `exports/` con timestamp:

```
exports/
├── trendradar_export_20250613_010000.csv
└── trendradar_export_20250613_010000.json
```

### Estructura JSON

```json
{
  "metadata": { "generated_at": "...", "geo": "Colombia", "timeframe": "Último día" },
  "topics": [
    {
      "rank": 1,
      "keyword": "Copa América",
      "trend_score": 87.5,
      "discover": { "tier": "ALTO", "has_breakout": true, "is_fresh_trend": true },
      "score_components": { "peak": 100, "velocity": 100, "curve": 90, "momentum": 85 },
      "metrics": { "interest_peak": 100, "interest_now": 94, "growth_pct": 340 },
      "recommendation": "🔥 Publicar YA — breakout activo, ventana de minutos",
      "news": [
        { "title": "...", "url": "...", "source": "...", "is_fresh": true }
      ]
    }
  ]
}
```

---

## Notas sobre Rate Limits

Google Trends tiene límites de frecuencia. Si ves error 429:
- El programa espera automáticamente (30s, 60s, 90s entre reintentos)
- Espera 5-10 minutos antes de volver a consultar
- Usa VPN o cambia de red si el problema persiste

---

## Configuración avanzada

Edita `trendradar/config.py` para ajustar:

```python
TOP_N_TRENDING = 20        # Número de temas a analizar
NEWS_MAX_ARTICLES = 5      # Noticias por tema
NEWS_FRESH_HOURS = 6       # Horas para considerar artículo "fresco"
DISCOVER_THRESHOLD = 65    # Umbral para tier ALTO
NEWS_CACHE_TTL = 900       # Segundos de caché de noticias (15 min)
```
