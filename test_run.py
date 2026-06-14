import logging
import json
import sys
from pprint import pprint
from trendradar.trends.fetcher import TrendsFetcher
from trendradar.scoring.scorer import TrendScorer
from trendradar.news.news_fetcher import NewsFetcher

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Configurar logging para ver todo el detalle
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")

def test_pipeline():
    print("--- INICIANDO PRUEBA DE PIPELINE ---")
    
    # 1. Fetcher (RSS + pytrends)
    fetcher = TrendsFetcher(geo="CO")
    print("\n1. Obteniendo datos de RSS para Colombia...")
    try:
        rss_data = fetcher.get_trending_with_rss_data(geo="CO")
        print(f"✅ Se obtuvieron {len(rss_data)} temas del RSS.")
        for item in rss_data[:3]:
            print(f"   - {item['keyword']} (Tráfico: {item.get('approx_traffic')})")
    except Exception as e:
        print(f"❌ Error en RSS: {e}")
        return

    if not rss_data:
        print("❌ RSS devolvió 0 temas. Abortando.")
        return

    # 2. Métricas de interés con pytrends
    print("\n2. Obteniendo métricas de interés vía pytrends (timeframe 1-d)...")
    keywords = [item["keyword"] for item in rss_data[:5]] # Probar con los primeros 5
    try:
        raw_topics = fetcher.get_trending_by_timeframe(
            keywords=keywords,
            timeframe_key="3", # 1 día
            geo="CO",
            cat=0,
            rss_data=rss_data
        )
        print(f"✅ Se obtuvieron métricas para {len(raw_topics)} temas.")
        for rt in raw_topics[:3]:
            print(f"   - {rt.keyword}: Peak={rt.interest_peak}, Breakout={rt.is_breakout}, Crecimiento={rt.growth_pct}%")
    except Exception as e:
        print(f"❌ Error en pytrends fallback: {e}")
        return

    # 3. Scorer
    print("\n3. Calculando TrendScore...")
    scorer = TrendScorer()
    try:
        scored_topics = scorer.score_all(raw_topics)
        print(f"✅ Se calcularon scores para {len(scored_topics)} temas.")
        for st in scored_topics[:3]:
            print(f"   - {st.keyword}: Score={st.trend_score:.1f}/100, Tier={st.discover_tier}")
    except Exception as e:
        print(f"❌ Error en Scorer: {e}")
        return

    # 4. News Fetcher
    print("\n4. Buscando noticias relacionadas...")
    news_fetcher = NewsFetcher(geo="CO")
    top_keywords = [st.keyword for st in scored_topics[:3]]
    try:
        news_by_topic = news_fetcher.fetch_batch(keywords=top_keywords, geo="CO")
        print(f"✅ Se obtuvieron noticias para {len(news_by_topic)} temas.")
        for kw, news_list in news_by_topic.items():
            print(f"   - {kw}: {len(news_list)} artículos encontrados.")
            if news_list:
                print(f"     Ej: {news_list[0].title} (Fresco: {news_list[0].is_fresh})")
    except Exception as e:
        print(f"❌ Error en News Fetcher: {e}")
        return

    print("\n--- PRUEBA COMPLETADA CON ÉXITO ---")

if __name__ == "__main__":
    test_pipeline()
