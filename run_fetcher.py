"""
TrendRadar SEO — run_fetcher.py
================================
Entry point interactivo del módulo Fetcher.

Cómo correr:
  python run_fetcher.py

Flujo:
  1. Seleccionar país (Colombia, México, Argentina, etc.)
  2. Seleccionar intervalo de tiempo
  3. Fetcher obtiene trending keywords (realtime → daily como fallback)
  4. Fetcher obtiene métricas de interés para cada keyword
  5. Tabla rich con resultados
  6. Opción de ver detalle de un tema individual
  7. Opción de nueva consulta o salir
"""

import sys
import logging

# ──────────────────────────────────────────────
# Logging: sólo WARN+ en consola para no ensuciar
# la terminal con debug de pytrends
# ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s | %(name)s | %(message)s",
)
# Mostrar INFO del propio trendradar pero no de libs externas
logging.getLogger("trendradar").setLevel(logging.INFO)

from trendradar.config import GEO_TARGETS, TIMEFRAMES, TOP_N_TRENDING
from trendradar.trends.fetcher import TrendsFetcher
from trendradar.output.display import (
    console,
    print_header,
    print_status,
    print_trending_table,
    print_topic_detail,
)


# ──────────────────────────────────────────────
# Menús de selección
# ──────────────────────────────────────────────
GEO_MENU = {
    "1": ("Colombia",      "CO"),
    "2": ("México",        "MX"),
    "3": ("Argentina",     "AR"),
    "4": ("Chile",         "CL"),
    "5": ("Perú",          "PE"),
    "6": ("Venezuela",     "VE"),
    "7": ("Ecuador",       "EC"),
    "8": ("LATAM global",  ""),
}


def _ask_geo() -> tuple[str, str]:
    """Muestra el menú de países y retorna (nombre, código ISO)."""
    console.print("[bold cyan]País / región:[/bold cyan]")
    for key, (name, code) in GEO_MENU.items():
        label = f"  [{key}] {name}"
        if code:
            label += f" [dim]({code})[/dim]"
        console.print(label)
    console.print()

    while True:
        choice = input("  Selecciona (1-8, default 1): ").strip() or "1"
        if choice in GEO_MENU:
            name, code = GEO_MENU[choice]
            return name, code
        console.print("  [yellow]Opción inválida, intenta de nuevo.[/yellow]")


def _ask_timeframe() -> tuple[str, str, str]:
    """Muestra el menú de intervalos y retorna (key, label, value)."""
    console.print("[bold cyan]Intervalo de tiempo:[/bold cyan]")
    for key, (label, value) in TIMEFRAMES.items():
        console.print(f"  [{key}] {label}  [dim]{value}[/dim]")
    console.print()

    while True:
        choice = input("  Selecciona (1-6, default 3): ").strip() or "3"
        if choice in TIMEFRAMES:
            label, value = TIMEFRAMES[choice]
            return choice, label, value
        console.print("  [yellow]Opción inválida, intenta de nuevo.[/yellow]")


def _ask_detail(topics: list) -> None:
    """Pregunta si el usuario quiere ver el detalle de un tema."""
    if not topics:
        return

    console.print("[dim]Ver detalle de un tema: escribe el número (ej: 3) o Enter para continuar.[/dim]")
    choice = input("  Tema #: ").strip()

    if not choice:
        return

    try:
        idx = int(choice) - 1
        if 0 <= idx < len(topics):
            print_topic_detail(topics[idx])
        else:
            print_status(f"Número fuera de rango (1-{len(topics)}).", kind="warn")
    except ValueError:
        pass


# ──────────────────────────────────────────────
# Flujo principal
# ──────────────────────────────────────────────
def run() -> None:
    print_header()

    fetcher = None   # se instancia después de elegir geo

    while True:
        # ── 1. Selección de geo ────────────────
        geo_name, geo_code = _ask_geo()
        console.print()

        # ── 2. Selección de intervalo ──────────
        tf_key, tf_label, tf_value = _ask_timeframe()
        console.print()

        # ── 3. Inicializar / actualizar fetcher ─
        if fetcher is None:
            fetcher = TrendsFetcher(geo=geo_code or "CO")
        else:
            fetcher.change_geo(geo_code or "CO")

        # ── 4. Obtener trending keywords ───────
        print_status(
            f"Obteniendo trending topics · {geo_name} · {tf_label}...",
            kind="loading",
        )

        keywords = fetcher.get_trending_keywords(geo=geo_code or None)

        if not keywords:
            print_status(
                "No se obtuvieron keywords. "
                "Puede ser una limitación de región o un rate-limit temporal de Google. "
                "Intenta con otro país o espera unos minutos.",
                kind="error",
            )
            console.print()
            if not _ask_retry():
                break
            continue

        print_status(f"{len(keywords)} keywords recuperadas.", kind="ok")
        console.print()

        # ── 5. Obtener métricas de interés ─────
        sample = keywords[:TOP_N_TRENDING]
        print_status(
            f"Analizando interés para {len(sample)} temas en {tf_label}...",
            kind="loading",
        )

        try:
            topics = fetcher.get_trending_by_timeframe(
                keywords=sample,
                timeframe_key=tf_key,
                geo=geo_code or None,
            )
        except Exception as exc:
            print_status(f"Error al obtener métricas de interés: {exc}", kind="error")
            console.print()
            if not _ask_retry():
                break
            continue

        # ── 6. Mostrar tabla ───────────────────
        print_trending_table(topics, geo=geo_name, timeframe_label=tf_label)

        # ── 7. Detalle de un tema ──────────────
        _ask_detail(topics)

        # ── 8. ¿Nueva consulta? ────────────────
        if not _ask_retry():
            break

    console.print("\n[bold cyan]👋 Hasta luego.[/bold cyan]\n")


def _ask_retry() -> bool:
    """Pregunta si el usuario quiere hacer otra consulta. Retorna True = sí."""
    answer = input("¿Nueva consulta? (s/n, default s): ").strip().lower() or "s"
    console.print()
    return answer in ("s", "si", "sí", "y", "yes", "")


# ──────────────────────────────────────────────
# Punto de entrada
# ──────────────────────────────────────────────
if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        console.print("\n\n[dim]Interrumpido por el usuario.[/dim]\n")
        sys.exit(0)
