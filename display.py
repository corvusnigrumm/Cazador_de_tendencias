"""
TrendRadar SEO — output/display.py
====================================
Renderizado de resultados en terminal usando Rich.

Exporta:
  - print_trending_table()   → tabla principal de trending topics
  - print_topic_detail()     → detalle expandido de un tema
  - print_header()           → banner del programa
  - print_status()           → mensajes de estado (info / ok / error)
  - console                  → instancia Rich compartida
"""

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.rule import Rule
from rich.columns import Columns
from rich import box
from rich.style import Style

# Instancia compartida — importar desde aquí en todos los módulos
console = Console()

# ──────────────────────────────────────────────
# Paleta de colores del proyecto
# ──────────────────────────────────────────────
CLR_BRAND    = "bold cyan"
CLR_OK       = "bold green"
CLR_WARN     = "bold yellow"
CLR_ERR      = "bold red"
CLR_DIM      = "dim white"
CLR_BREAKOUT = "bold magenta"
CLR_HIGH     = "bold green"
CLR_MED      = "yellow"
CLR_LOW      = "dim white"


# ──────────────────────────────────────────────
# Banner
# ──────────────────────────────────────────────
def print_header() -> None:
    """Imprime el banner principal del programa."""
    title = Text()
    title.append("📡 TrendRadar", style="bold cyan")
    title.append(" SEO", style="bold white")

    subtitle = Text(
        "Google Trends · Colombia & Latinoamérica · Discover Intelligence",
        style="dim cyan",
        justify="center",
    )

    console.print()
    console.print(Panel(
        f"{title}\n{subtitle}",
        border_style="cyan",
        padding=(0, 4),
    ))
    console.print()


# ──────────────────────────────────────────────
# Mensajes de estado
# ──────────────────────────────────────────────
def print_status(msg: str, kind: str = "info") -> None:
    """
    Imprime un mensaje de estado con ícono.
    kind: 'info' | 'ok' | 'warn' | 'error' | 'loading'
    """
    icons = {
        "info":    ("ℹ", "cyan"),
        "ok":      ("✅", CLR_OK),
        "warn":    ("⚠️ ", CLR_WARN),
        "error":   ("❌", CLR_ERR),
        "loading": ("⏳", "yellow"),
    }
    icon, style = icons.get(kind, ("·", "white"))
    console.print(f"  {icon}  {msg}", style=style)


# ──────────────────────────────────────────────
# Tabla principal de trending topics
# ──────────────────────────────────────────────
def print_trending_table(topics: list, geo: str, timeframe_label: str) -> None:
    """
    Renderiza la tabla principal con todos los TrendingTopic.

    Columnas:
      # | Tema | Curva | Peak | Ahora | Crecimiento | Breakout | Related queries
    """
    from trendradar.trends.fetcher import _sparkline   # import local para evitar circular

    if not topics:
        print_status("Sin datos para mostrar.", kind="warn")
        return

    console.print(Rule(
        f"[bold cyan]Trending en [white]{geo}[/white] · {timeframe_label}[/bold cyan]",
        style="cyan",
    ))
    console.print()

    table = Table(
        box=box.ROUNDED,
        border_style="cyan",
        header_style="bold cyan",
        show_lines=True,
        expand=True,
    )

    # Definición de columnas
    table.add_column("#",              justify="right",  style="dim white",   no_wrap=True, width=3)
    table.add_column("Tema",           justify="left",   style="bold white",  no_wrap=False, ratio=3)
    table.add_column("Curva",          justify="center", style="white",       no_wrap=True, width=10)
    table.add_column("Peak",           justify="center", style="white",       no_wrap=True, width=6)
    table.add_column("Ahora",          justify="center", style="white",       no_wrap=True, width=6)
    table.add_column("Crecimiento",    justify="right",  style="white",       no_wrap=True, width=13)
    table.add_column("Breakout",       justify="center", style="white",       no_wrap=True, width=9)
    table.add_column("Related queries",justify="left",   style="dim white",   no_wrap=False, ratio=2)

    for i, topic in enumerate(topics, 1):
        # ── Curva sparkline ──
        spark = _sparkline(topic.raw_interest, width=8) if topic.raw_interest else "─" * 8

        # ── Peak con color por intensidad ──
        peak_style, peak_val = _interest_color(topic.interest_peak)
        peak_cell = Text(str(topic.interest_peak), style=peak_style)

        # ── Ahora ──
        now_style, _ = _interest_color(topic.interest_now)
        now_cell = Text(str(topic.interest_now), style=now_style)

        # ── Crecimiento ──
        growth_cell = _growth_cell(topic.growth_pct, topic.is_breakout)

        # ── Breakout badge ──
        breakout_cell = Text("🔥 SÍ", style=CLR_BREAKOUT) if topic.is_breakout else Text("No", style=CLR_DIM)

        # ── Related ──
        related_text = ", ".join(topic.related_queries[:3]) if topic.related_queries else "—"

        table.add_row(
            str(i),
            topic.keyword,
            spark,
            peak_cell,
            now_cell,
            growth_cell,
            breakout_cell,
            related_text,
        )

    console.print(table)
    console.print()


# ──────────────────────────────────────────────
# Detalle expandido de un tema
# ──────────────────────────────────────────────
def print_topic_detail(topic) -> None:
    """
    Muestra el detalle completo de un TrendingTopic:
    métricas, serie temporal y related queries.
    """
    from trendradar.trends.fetcher import _sparkline

    console.print(Rule(f"[bold white]{topic.keyword}[/bold white]", style="cyan"))
    console.print()

    # Métricas principales en columnas
    metrics = [
        Panel(f"[bold cyan]{topic.interest_peak}[/bold cyan]\n[dim]Peak interés[/dim]",   border_style="cyan"),
        Panel(f"[bold white]{topic.interest_avg}[/bold white]\n[dim]Promedio[/dim]",       border_style="white"),
        Panel(f"[bold white]{topic.interest_now}[/bold white]\n[dim]Ahora[/dim]",          border_style="white"),
        Panel(_growth_str(topic.growth_pct, topic.is_breakout) + "\n[dim]Crecimiento[/dim]", border_style="magenta" if topic.is_breakout else "green"),
    ]
    console.print(Columns(metrics, equal=True, expand=True))
    console.print()

    # Serie temporal
    if topic.raw_interest:
        spark_wide = _sparkline(topic.raw_interest, width=40)
        console.print(f"  [dim]Serie temporal:[/dim]  [cyan]{spark_wide}[/cyan]")
        console.print(f"  [dim]Puntos: {len(topic.raw_interest)} · Período: {topic.timeframe_label}[/dim]")
        console.print()

    # Related queries
    if topic.related_queries:
        console.print("  [bold cyan]Related queries:[/bold cyan]")
        for q in topic.related_queries:
            console.print(f"    [dim]·[/dim] {q}")
        console.print()

    # Geo / timeframe
    console.print(f"  [dim]Geo: {topic.geo} · Intervalo: {topic.timeframe_label}[/dim]")
    console.print()


# ──────────────────────────────────────────────
# Helpers internos
# ──────────────────────────────────────────────
def _interest_color(value: int) -> tuple[str, str]:
    """Devuelve (estilo rich, etiqueta) según el nivel de interés (0-100)."""
    if value >= 75:
        return CLR_HIGH, "alto"
    if value >= 40:
        return CLR_MED, "medio"
    return CLR_LOW, "bajo"


def _growth_cell(growth_pct: float, is_breakout: bool) -> Text:
    """Construye el Text de la celda de crecimiento."""
    if is_breakout:
        return Text("🔥 BREAKOUT", style=CLR_BREAKOUT)
    if growth_pct > 0:
        return Text(f"▲ +{growth_pct:.0f}%", style=CLR_HIGH if growth_pct >= 50 else CLR_MED)
    if growth_pct < 0:
        return Text(f"▼ {growth_pct:.0f}%", style=CLR_ERR)
    return Text("→ estable", style=CLR_DIM)


def _growth_str(growth_pct: float, is_breakout: bool) -> str:
    """Versión string (con markup rich) para usar dentro de Panel."""
    if is_breakout:
        return "[bold magenta]🔥 BREAKOUT[/bold magenta]"
    if growth_pct > 0:
        color = "green" if growth_pct >= 50 else "yellow"
        return f"[{color}]▲ +{growth_pct:.0f}%[/{color}]"
    if growth_pct < 0:
        return f"[red]▼ {growth_pct:.0f}%[/red]"
    return "[dim]→ estable[/dim]"
