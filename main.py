"""
TrendRadar SEO — main.py
=========================
Entry point principal integrado.

Flujo completo:
  1. Seleccionar país / región
  2. Seleccionar intervalo de tiempo
  3. Seleccionar categoría (todas / noticias / deportes / etc.)
  4. Obtener trending keywords (realtime → daily fallback)
  5. Calcular TrendScore para cada tema (scorer)
  6. Obtener noticias relacionadas por tema (news fetcher)
  7. Mostrar tabla principal con Score + Discover + Noticias
  8. Ver detalle de un tema individual
  9. Exportar a CSV / JSON
 10. Nueva consulta o salir

Cómo correr:
  python main.py
"""

import sys
import logging

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# ──────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s | %(name)s | %(message)s",
)
# Mostrar INFO del propio trendradar pero no de libs externas
logging.getLogger("trendradar").setLevel(logging.INFO)

# ──────────────────────────────────────────────
# Imports del paquete
# ──────────────────────────────────────────────
from trendradar.config import (
    GEO_TARGETS,
    TIMEFRAMES,
    CATEGORIES,
    TOP_N_TRENDING,
)
from trendradar.trends.fetcher import TrendsFetcher
from trendradar.scoring.scorer import TrendScorer
from trendradar.news.news_fetcher import NewsFetcher
from trendradar.output.display import (
    console,
    print_header,
    print_status,
    print_scored_table,
    print_scored_detail,
    print_news_for_topic,
    print_ai_summary,
)
from trendradar.output.exporter import export_csv, export_json, export_excel
from trendradar.ai.generator import generate_editorial_plan


# ──────────────────────────────────────────────
# Menús de selección
# ──────────────────────────────────────────────
GEO_MENU = {
    "1": ("Colombia",     "CO"),
    "2": ("México",       "MX"),
    "3": ("Argentina",    "AR"),
    "4": ("Chile",        "CL"),
    "5": ("Perú",         "PE"),
    "6": ("Venezuela",    "VE"),
    "7": ("Ecuador",      "EC"),
    "8": ("España",       "ES"),
    "9": ("LATAM global", ""),
}

CAT_MENU = {
    "1": ("Todas",           0),
    "2": ("Noticias",        16),
    "3": ("Entretenimiento", 3),
    "4": ("Deportes",        20),
    "5": ("Negocios",        12),
    "6": ("Tecnología",      5),
    "7": ("Ciencia",         8),
    "8": ("Salud",           45),
    "9": ("Política",        396),
}


# ──────────────────────────────────────────────
# Funciones de selección interactiva
# ──────────────────────────────────────────────
def _ask_geo() -> tuple[str, str]:
    """Muestra el menú de países y retorna (nombre, código ISO)."""
    console.print("[bold cyan]┌─ País / Región ──────────────────────────[/bold cyan]")
    for key, (name, code) in GEO_MENU.items():
        label = f"[dim cyan]│[/dim cyan]  [{key}] {name}"
        if code:
            label += f" [dim]({code})[/dim]"
        console.print(label)
    console.print("[bold cyan]└──────────────────────────────────────────[/bold cyan]")
    console.print()

    while True:
        choice = input("  Selecciona (1-9, default 1): ").strip() or "1"
        if choice in GEO_MENU:
            name, code = GEO_MENU[choice]
            return name, code
        console.print("  [yellow]Opción inválida, intenta de nuevo.[/yellow]")


def _ask_timeframe() -> tuple[str, str, str]:
    """Muestra el menú de intervalos y retorna (key, label, value)."""
    console.print("[bold cyan]┌─ Intervalo de Tiempo ────────────────────[/bold cyan]")
    for key, (label, value) in TIMEFRAMES.items():
        console.print(f"[dim cyan]│[/dim cyan]  [{key}] {label}  [dim]{value}[/dim]")
    console.print("[bold cyan]└──────────────────────────────────────────[/bold cyan]")
    console.print()

    while True:
        choice = input("  Selecciona (1-6, default 3): ").strip() or "3"
        if choice in TIMEFRAMES:
            label, value = TIMEFRAMES[choice]
            return choice, label, value
        console.print("  [yellow]Opción inválida, intenta de nuevo.[/yellow]")


def _ask_category() -> tuple[str, int]:
    """Muestra el menú de categorías y retorna (nombre, código)."""
    console.print("[bold cyan]┌─ Categoría ──────────────────────────────[/bold cyan]")
    for key, (name, code) in CAT_MENU.items():
        console.print(f"[dim cyan]│[/dim cyan]  [{key}] {name}")
    console.print("[bold cyan]└──────────────────────────────────────────[/bold cyan]")
    console.print()

    while True:
        choice = input("  Selecciona (1-9, default 1): ").strip() or "1"
        if choice in CAT_MENU:
            name, code = CAT_MENU[choice]
            return name, code
        console.print("  [yellow]Opción inválida, intenta de nuevo.[/yellow]")


def _ask_fetch_news() -> bool:
    """Pregunta si se deben buscar noticias relacionadas."""
    ans = input("  ¿Buscar noticias relacionadas? (s/n, default s): ").strip().lower() or "s"
    return ans in ("s", "si", "sí", "y", "yes", "")


def _ask_detail(scored_topics: list, news_by_topic: dict) -> None:
    """Pregunta si el usuario quiere ver el detalle de un tema."""
    if not scored_topics:
        return

    console.print(
        "[dim]Ver detalle completo: escribe el número del tema (ej: 3) "
        "o Enter para continuar.[/dim]"
    )
    choice = input("  Tema #: ").strip()

    if not choice:
        return

    try:
        idx = int(choice) - 1
        if 0 <= idx < len(scored_topics):
            s    = scored_topics[idx]
            news = news_by_topic.get(s.keyword, [])
            print_scored_detail(s, news=news)
        else:
            print_status(f"Número fuera de rango (1-{len(scored_topics)}).", kind="warn")
    except ValueError:
        pass


def _ask_export(scored_topics: list, news_by_topic: dict, ai_data_by_topic: dict, meta: dict) -> None:
    """Pregunta si exportar y en qué formato."""
    console.print(
        "[dim]Exportar resultados: [1] Plantilla Excel SEO (Recomendado)  [2] CSV  [3] JSON  [4] Todo  "
        "[Enter] No exportar[/dim]"
    )
    choice = input("  Exportar (1/2/3/4): ").strip()

    if not choice:
        return

    if choice in ("1", "4"):
        path = export_excel(scored_topics, news_by_topic, ai_data_by_topic)
        if path:
            print_status(f"Excel SEO guardado → {path}", kind="ok")

    if choice in ("2", "4"):
        path = export_csv(scored_topics, news_by_topic)
        if path:
            print_status(f"CSV guardado → {path}", kind="ok")

    if choice in ("3", "4"):
        path = export_json(scored_topics, news_by_topic, metadata=meta)
        if path:
            print_status(f"JSON guardado → {path}", kind="ok")

    console.print()


def _ask_retry() -> bool:
    """Pregunta si el usuario quiere hacer otra consulta. Retorna True = sí."""
    answer = input("¿Nueva consulta? (s/n, default s): ").strip().lower() or "s"
    console.print()
    return answer in ("s", "si", "sí", "y", "yes", "")


# ──────────────────────────────────────────────
# Flujo principal
# ──────────────────────────────────────────────
def run() -> None:
    print_header()

    fetcher      = None
    news_fetcher = None
    scorer       = TrendScorer()

    while True:

        # ── 1. Selección de geo ──────────────────
        geo_name, geo_code = _ask_geo()
        console.print()

        # ── 2. Selección de intervalo ────────────
        tf_key, tf_label, tf_value = _ask_timeframe()
        console.print()

        # ── 3. Selección de categoría ────────────
        cat_name, cat_code = _ask_category()
        console.print()

        # ── 4. ¿Buscar noticias? ─────────────────
        fetch_news = _ask_fetch_news()
        console.print()

        # ── 5. Inicializar / actualizar fetchers ──
        effective_geo = geo_code or "CO"

        if fetcher is None:
            fetcher = TrendsFetcher(geo=effective_geo)
        else:
            fetcher.change_geo(effective_geo)

        if news_fetcher is None or news_fetcher.geo != effective_geo:
            news_fetcher = NewsFetcher(geo=effective_geo, use_cache=True)

        # ── 6. Obtener trending keywords (VÍA RSS) ──────────
        print_status(
            f"Obteniendo trending topics · {geo_name} · {tf_label} · {cat_name}...",
            kind="loading",
        )

        rss_data = fetcher.get_trending_with_rss_data(geo=geo_code or None)
        keywords = [item["keyword"] for item in rss_data]

        if not keywords:
            print_status(
                "No se obtuvieron keywords. Verifica tu conexión a internet o el país seleccionado.",
                kind="error",
            )
            console.print()
            if not _ask_retry():
                break
            continue

        print_status(f"{len(keywords)} keywords recuperadas del RSS.", kind="ok")
        console.print()

        # ── 7. Obtener métricas de interés ────────
        sample = keywords[:TOP_N_TRENDING]
        print_status(
            f"Analizando {len(sample)} temas en Google Trends ({tf_label})...",
            kind="loading",
        )

        try:
            raw_topics = fetcher.get_trending_by_timeframe(
                keywords=sample,
                timeframe_key=tf_key,
                geo=geo_code or None,
                cat=cat_code,
                rss_data=rss_data,
            )
        except Exception as exc:
            print_status(f"Error al obtener métricas de interés: {exc}", kind="error")
            console.print()
            if not _ask_retry():
                break
            continue

        # ── 8. Calcular TrendScore ─────────────────
        print_status("Calculando TrendScore y señales Discover...", kind="loading")
        scored_topics = scorer.score_all(raw_topics)
        print_status(f"Score calculado para {len(scored_topics)} temas.", kind="ok")
        console.print()

        # ── 9. Buscar noticias relacionadas ────────
        news_by_topic: dict = {}
        if fetch_news and scored_topics:
            top_keywords = [s.keyword for s in scored_topics[:10]]  # top 10 por eficiencia
            print_status(
                f"Buscando noticias para los top {len(top_keywords)} temas...",
                kind="loading",
            )
            try:
                news_by_topic = news_fetcher.fetch_batch(
                    keywords=top_keywords,
                    geo=geo_code or None,
                )
                total_news = sum(len(v) for v in news_by_topic.values())
                fresh_news = sum(
                    sum(1 for a in v if a.is_fresh)
                    for v in news_by_topic.values()
                )
                print_status(
                    f"{total_news} artículos encontrados "
                    f"(🆕 {fresh_news} frescos en las últimas 6h).",
                    kind="ok",
                )
            except Exception as exc:
                print_status(f"Advertencia: no se pudieron obtener noticias ({exc})", kind="warn")
            console.print()

        # ── 10. Mostrar tabla principal ────────────
        print_scored_table(
            scored_topics,
            geo=geo_name,
            timeframe_label=tf_label,
            news_by_topic=news_by_topic,
        )

        # ── 11. Detalle de un tema ─────────────────
        _ask_detail(scored_topics, news_by_topic)

        # ── 12. Generación IA (Planificación Editorial) ────
        ai_data_by_topic = {}
        ans = input("  ¿Generar plan editorial con IA (Groq+HF) para el Top 5? (s/n, default s): ").strip().lower() or "s"
        if ans in ("s", "si", "sí", "y", "yes", "") and scored_topics:
            top_5 = scored_topics[:5]
            print_status(f"Generando ángulos y títulos con IA para {len(top_5)} temas...", kind="loading")
            for i, s in enumerate(top_5, 1):
                # Extraer hasta 5 títulos de noticias para dar contexto a Groq
                news_list = news_by_topic.get(s.keyword, [])
                news_titles = [n.title for n in news_list[:5]]
                print_status(f"[{i}/{len(top_5)}] Consultando IA para '{s.keyword}'...", kind="loading")
                res = generate_editorial_plan(s.keyword, news_titles)
                ai_data_by_topic[s.keyword] = res
            print_status("Generación IA completada.", kind="ok")
            console.print()
            print_ai_summary(ai_data_by_topic)

        # ── 13. Exportar ───────────────────────────
        meta = {
            "geo":       geo_name,
            "geo_code":  geo_code,
            "timeframe": tf_label,
            "category":  cat_name,
        }
        _ask_export(scored_topics, news_by_topic, ai_data_by_topic, meta)

        # ── 14. ¿Nueva consulta? ───────────────────
        if not _ask_retry():
            break

    console.print("\n[bold cyan]👋 Hasta luego. ¡A publicar tendencias![/bold cyan]\n")


# ──────────────────────────────────────────────
# Punto de entrada
# ──────────────────────────────────────────────
if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        console.print("\n\n[dim]Interrumpido por el usuario.[/dim]\n")
        sys.exit(0)
