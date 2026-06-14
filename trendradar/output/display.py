"""
TrendRadar SEO — output/display.py
====================================
Renderizado de resultados en terminal usando Rich.

Exporta:
  - print_header()           → banner del programa
  - print_status()           → mensajes de estado (info / ok / error)
  - print_scored_table()     → tabla principal con TrendScore y Discover
  - print_scored_detail()    → detalle expandido de un ScoredTopic
  - print_news_for_topic()   → lista de noticias relacionadas a un tema
  - print_trending_table()   → tabla básica de TrendingTopics (sin score)
  - console                  → instancia Rich compartida
"""

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.rule import Rule
from rich.columns import Columns
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich import box

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
CLR_FRESH    = "bold cyan"


# ──────────────────────────────────────────────
# Banner
# ──────────────────────────────────────────────
def print_header() -> None:
    """Imprime el banner principal del programa."""
    console.print()
    console.print(Panel(
        "[bold cyan]📡 TrendRadar[/bold cyan] [bold white]SEO[/bold white]\n"
        "[dim cyan]Google Trends · Colombia & Latinoamérica · Discover Intelligence[/dim cyan]",
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
# Tabla principal de ScoredTopics (con TrendScore y Discover)
# ──────────────────────────────────────────────
def print_scored_table(
    scored_topics: list,
    geo:           str,
    timeframe_label: str,
    news_by_topic: dict = None,
) -> None:
    """
    Renderiza la tabla principal de ScoredTopics con TrendScore,
    tier de Discover, recomendación editorial y conteo de noticias.

    Columnas:
      # | Score | Discover | Tema | Curva | Peak | Ahora | Crecimiento | Noticias | Recomendación
    """
    from trendradar.trends.fetcher import _sparkline

    if not scored_topics:
        print_status("Sin datos para mostrar.", kind="warn")
        return

    news_by_topic = news_by_topic or {}

    console.print(Rule(
        f"[bold cyan]TrendRadar · {geo} · {timeframe_label}[/bold cyan]",
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

    table.add_column("#",             justify="right",  style="dim white",  no_wrap=True, width=3)
    table.add_column("Score",         justify="center", style="white",      no_wrap=True, width=7)
    table.add_column("Discover",      justify="center", style="white",      no_wrap=True, width=9)
    table.add_column("Tema",          justify="left",   style="bold white", no_wrap=False, ratio=3)
    table.add_column("Curva",         justify="center", style="white",      no_wrap=True, width=10)
    table.add_column("Peak",          justify="center", style="white",      no_wrap=True, width=6)
    table.add_column("Ahora",         justify="center", style="white",      no_wrap=True, width=6)
    table.add_column("Crecimiento",   justify="right",  style="white",      no_wrap=True, width=13)
    table.add_column("Noticias",      justify="center", style="white",      no_wrap=True, width=9)
    table.add_column("Recomendación", justify="left",   style="dim white",  no_wrap=False, ratio=4)

    for i, s in enumerate(scored_topics, 1):
        # Score con color por nivel
        score_cell = _score_cell(s.trend_score)

        # Tier badge
        tier_cell = _tier_cell(s.discover_tier)

        # Sparkline
        spark = _sparkline(s.raw_interest, width=8) if s.raw_interest else "─" * 8

        # Peak con color
        peak_style, _ = _interest_color(s.interest_peak)
        peak_cell = Text(str(s.interest_peak), style=peak_style)

        # Ahora
        now_style, _ = _interest_color(s.interest_now)
        now_cell = Text(str(s.interest_now), style=now_style)

        # Crecimiento
        growth_cell = _growth_cell(s.growth_pct, s.is_breakout)

        # Noticias
        news_list = news_by_topic.get(s.keyword, [])
        fresh_count = sum(1 for a in news_list if a.is_fresh)
        total_count = len(news_list)
        if total_count:
            news_label = f"📰 {total_count}"
            if fresh_count:
                news_cell = Text(f"📰 {total_count} (🆕{fresh_count})", style=CLR_FRESH)
            else:
                news_cell = Text(f"📰 {total_count}", style="white")
        else:
            news_cell = Text("—", style=CLR_DIM)

        table.add_row(
            str(i),
            score_cell,
            tier_cell,
            s.keyword,
            spark,
            peak_cell,
            now_cell,
            growth_cell,
            news_cell,
            s.recommendation,
        )

    console.print(table)
    console.print()


# ──────────────────────────────────────────────
# Detalle expandido de un ScoredTopic
# ──────────────────────────────────────────────
def print_scored_detail(s, news: list = None) -> None:
    """
    Detalle completo de un ScoredTopic:
      - Score total y tier Discover
      - Componentes del score (4 dimensiones)
      - Señales Discover activas
      - Recomendación editorial
      - Noticias relacionadas
      - Related queries
    """
    from trendradar.trends.fetcher import _sparkline

    console.print(Rule(f"[bold white]{s.keyword}[/bold white]", style="cyan"))
    console.print()

    # ── Score total destacado ──────────────────
    score_color = _score_color(s.trend_score)
    tier_label  = _tier_label(s.discover_tier)

    console.print(Panel(
        f"[{score_color}]TrendScore: {s.trend_score:.1f} / 100[/{score_color}]"
        f"   {tier_label}",
        border_style=score_color,
        padding=(0, 2),
    ))
    console.print()

    # ── Componentes del score ──────────────────
    components = [
        Panel(
            f"[bold]{s.score_peak:.0f}[/bold]\n[dim]Peak interés[/dim]\n[dim](35%)[/dim]",
            border_style="cyan",
        ),
        Panel(
            f"[bold]{s.score_velocity:.0f}[/bold]\n[dim]Velocidad[/dim]\n[dim](30%)[/dim]",
            border_style="magenta" if s.is_breakout else "cyan",
        ),
        Panel(
            f"[bold]{s.score_curve:.0f}[/bold]\n[dim]Forma curva[/dim]\n[dim](15%)[/dim]",
            border_style="cyan",
        ),
        Panel(
            f"[bold]{s.score_momentum:.0f}[/bold]\n[dim]Momentum[/dim]\n[dim](20%)[/dim]",
            border_style="cyan",
        ),
    ]
    console.print(Columns(components, equal=True, expand=True))
    console.print()

    # ── Señales Discover ───────────────────────
    console.print("[bold cyan]Señales Discover:[/bold cyan]")
    signals = [
        ("🔥 Breakout",         s.has_breakout),
        ("🚀 Acelerando",       s.is_accelerating),
        ("⚡ Tendencia fresca",  s.is_fresh_trend),
        ("📌 Sostenida",        s.is_sustained),
    ]
    for label, active in signals:
        style = CLR_OK if active else CLR_DIM
        mark  = "✓" if active else "✗"
        console.print(f"  [{style}]{mark} {label}[/{style}]")
    console.print()

    # ── Serie temporal ─────────────────────────
    if s.raw_interest:
        spark_wide = _sparkline(s.raw_interest, width=40)
        console.print(f"  [dim]Curva:[/dim]  [cyan]{spark_wide}[/cyan]")
        console.print(
            f"  [dim]{len(s.raw_interest)} puntos · "
            f"Peak: {s.interest_peak} · Ahora: {s.interest_now} · "
            f"Promedio: {s.interest_avg:.1f}[/dim]"
        )
        console.print()

    # ── Recomendación ──────────────────────────
    console.print(Panel(
        s.recommendation,
        title="[bold cyan]Recomendación editorial[/bold cyan]",
        border_style="cyan",
        padding=(0, 2),
    ))
    console.print()

    # ── Noticias relacionadas ──────────────────
    if news:
        print_news_for_topic(s.keyword, news)

    # ── Related queries ────────────────────────
    if s.related_queries:
        console.print("[bold cyan]Related queries en Google:[/bold cyan]")
        for q in s.related_queries:
            console.print(f"  [dim]·[/dim] {q}")
        console.print()


# ──────────────────────────────────────────────
# Noticias relacionadas a un tema
# ──────────────────────────────────────────────
def print_news_for_topic(keyword: str, articles: list) -> None:
    """
    Muestra los artículos de noticias encontrados para un tema trending.

    Muestra: título, fuente, fecha, URL y si es artículo fresco.
    """
    if not articles:
        console.print(f"  [dim]No se encontraron noticias para '{keyword}'[/dim]")
        console.print()
        return

    fresh_count = sum(1 for a in articles if a.is_fresh)
    header_extra = f" [bold cyan](🆕 {fresh_count} frescos)[/bold cyan]" if fresh_count else ""
    console.print(f"[bold cyan]Noticias relacionadas:[/bold cyan]{header_extra}")
    console.print()

    for i, art in enumerate(articles, 1):
        # Ícono fresco
        fresh_icon = "[bold cyan]🆕[/bold cyan] " if art.is_fresh else "   "

        # Relevancia como barra simple
        rel_bar = _relevance_bar(art.relevance_score)

        # Título con link clickeable (terminals modernos)
        console.print(
            f"  {i}. {fresh_icon}[bold white]{art.title}[/bold white]"
        )
        console.print(
            f"     [dim]{art.source}[/dim]  ·  "
            f"[dim]{art.published_str()}[/dim]  ·  "
            f"Relevancia: {rel_bar}"
        )
        if art.snippet:
            snippet = art.snippet[:120] + "…" if len(art.snippet) > 120 else art.snippet
            console.print(f"     [dim italic]{snippet}[/dim italic]")
        console.print(f"     [link={art.url}][dim cyan]{art.url[:80]}[/dim cyan][/link]")
        console.print()


# ──────────────────────────────────────────────
# Tabla básica de TrendingTopics (sin score) — legacy
# ──────────────────────────────────────────────
def print_trending_table(topics: list, geo: str, timeframe_label: str) -> None:
    """
    Renderiza la tabla básica con TrendingTopics sin puntuar.
    Columnas: # | Tema | Curva | Peak | Ahora | Crecimiento | Breakout | Related queries
    """
    from trendradar.trends.fetcher import _sparkline

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

    table.add_column("#",               justify="right",  style="dim white",  no_wrap=True, width=3)
    table.add_column("Tema",            justify="left",   style="bold white", no_wrap=False, ratio=3)
    table.add_column("Curva",           justify="center", style="white",      no_wrap=True, width=10)
    table.add_column("Peak",            justify="center", style="white",      no_wrap=True, width=6)
    table.add_column("Ahora",           justify="center", style="white",      no_wrap=True, width=6)
    table.add_column("Crecimiento",     justify="right",  style="white",      no_wrap=True, width=13)
    table.add_column("Breakout",        justify="center", style="white",      no_wrap=True, width=9)
    table.add_column("Related queries", justify="left",   style="dim white",  no_wrap=False, ratio=2)

    for i, topic in enumerate(topics, 1):
        spark        = _sparkline(topic.raw_interest, width=8) if topic.raw_interest else "─" * 8
        peak_style, _= _interest_color(topic.interest_peak)
        peak_cell    = Text(str(topic.interest_peak), style=peak_style)
        now_style, _ = _interest_color(topic.interest_now)
        now_cell     = Text(str(topic.interest_now), style=now_style)
        growth_cell  = _growth_cell(topic.growth_pct, topic.is_breakout)
        breakout_cell= Text("🔥 SÍ", style=CLR_BREAKOUT) if topic.is_breakout else Text("No", style=CLR_DIM)
        related_text = ", ".join(topic.related_queries[:3]) if topic.related_queries else "—"

        table.add_row(
            str(i), topic.keyword, spark,
            peak_cell, now_cell, growth_cell,
            breakout_cell, related_text,
        )

    console.print(table)
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


def _score_color(score: float) -> str:
    """Color rich según el TrendScore."""
    if score >= 75:
        return "bold green"
    if score >= 55:
        return "bold yellow"
    if score >= 35:
        return "yellow"
    return "dim white"


def _score_cell(score: float) -> Text:
    """Celda de TrendScore con color."""
    return Text(f"{score:.0f}", style=_score_color(score))


def _tier_cell(tier: str) -> Text:
    """Badge de tier Discover."""
    styles = {
        "ALTO":  ("⬆ ALTO",  "bold green"),
        "MEDIO": ("→ MEDIO", "bold yellow"),
        "BAJO":  ("⬇ BAJO",  "dim white"),
    }
    label, style = styles.get(tier, ("─", "dim white"))
    return Text(label, style=style)


def _tier_label(tier: str) -> str:
    """Versión markup rich del tier para usar dentro de Panel."""
    labels = {
        "ALTO":  "[bold green]⬆ ALTO potencial Discover[/bold green]",
        "MEDIO": "[bold yellow]→ MEDIO potencial Discover[/bold yellow]",
        "BAJO":  "[dim white]⬇ BAJO potencial Discover[/dim white]",
    }
    return labels.get(tier, "")


def _relevance_bar(score: float, width: int = 5) -> str:
    """Convierte un score 0-1 en una barra visual simple."""
    filled = round(score * width)
    bar    = "█" * filled + "░" * (width - filled)
    pct    = int(score * 100)
    color  = "bold green" if pct >= 70 else ("yellow" if pct >= 40 else "dim white")
    return f"[{color}]{bar}[/{color}] [dim]{pct}%[/dim]"


# ──────────────────────────────────────────────
# Resumen de IA generada
# ──────────────────────────────────────────────
def print_ai_summary(ai_data_by_topic: dict) -> None:
    """Muestra un resumen de los resultados generados por la IA en la consola."""
    if not ai_data_by_topic:
        return

    console.print(Rule("[bold magenta]Planificación Editorial IA[/bold magenta]", style="magenta"))
    console.print()

    for keyword, data in ai_data_by_topic.items():
        if not data:
            continue
        console.print(f"[bold white]Tema:[/bold white] [cyan]{keyword}[/cyan]")
        console.print(f"  [bold]Ángulo:[/bold] {data.get('angulo', 'N/A')}")
        console.print(f"  [bold]Clickbait:[/bold] [yellow]{data.get('clickbait', 'N/A')}[/yellow]")
        console.print(f"  [bold]Entidades:[/bold] [dim]{data.get('entidades', 'N/A')}[/dim]")
        console.print()
