"""Generacion editorial con proveedores de IA opcionales."""

import json
import logging

import requests

from trendradar.ai.config_ai import AI_CONFIG


logger = logging.getLogger(__name__)
groq_client = None


def generate_editorial_plan(keyword: str, news_context: list[str]) -> dict:
    """
    Genera angulo, titulo y entidades para una tendencia.

    La funcion nunca debe tumbar el pipeline: si un proveedor falla,
    devuelve un fallback editorial util y deja el error en logs.
    """
    logger.info("Generando plan editorial con IA para: %s", keyword)

    result = _fallback_editorial_plan(keyword, news_context)

    client = _get_groq_client()
    if client:
        groq_res = _generate_with_groq(client, keyword, news_context)
        if groq_res:
            result["angulo"] = _sanitize_ai_text(groq_res.get("angulo")) or result["angulo"]
            title = _sanitize_ai_text(groq_res.get("clickbait"))
            result["clickbait"] = _limit_title(title) or result["clickbait"]

    hf_key = AI_CONFIG.get("hf_api_key")
    if hf_key:
        hf_res = _generate_with_hf(keyword, hf_key.strip())
        if hf_res and hf_res != "N/A":
            result["entidades"] = hf_res

    return result


def _get_groq_client():
    """Inicializa Groq de forma perezosa para que sea opcional."""
    global groq_client
    if groq_client is not None:
        return groq_client

    api_key = AI_CONFIG.get("groq_api_key")
    if not api_key:
        logger.warning("GROQ_API_KEY no configurada; usando fallback editorial local.")
        return None

    try:
        from groq import Groq

        groq_client = Groq(api_key=api_key)
        return groq_client
    except Exception as exc:
        logger.warning("Groq no disponible: %s", exc)
        return None


def _generate_with_groq(client, keyword: str, news_context: list[str]) -> dict:
    context_text = "\n".join(f"- {title}" for title in news_context[:5])
    if not context_text:
        context_text = "Sin noticias recientes disponibles."

    prompt = f"""
Eres un editor SEO experto en Google Discover para medios digitales en espanol.

Tema en tendencia: "{keyword}"

Titulares recientes de competidores:
{context_text}

Devuelve solo un objeto JSON valido con estas llaves:
- "angulo": un enfoque unico para cubrir la tendencia sin repetir a la competencia. Maximo 2 oraciones.
- "clickbait": un titulo llamativo, etico y claro. Maximo 60 caracteres.

No uses Markdown. No incluyas texto fuera del JSON.
"""

    last_error = None
    for model in AI_CONFIG.get("groq_models", [AI_CONFIG["groq_model"]]):
        try:
            response = client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=model,
                temperature=0.7,
                max_tokens=300,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content or "{}"
            data = _parse_json_object(content)
            if data:
                return data
        except Exception as exc:
            last_error = exc
            logger.warning("Groq fallo con modelo %s: %s", model, exc)

    if last_error:
        logger.error("Groq no pudo generar contenido para '%s': %s", keyword, last_error)
    return {}


def _generate_with_hf(keyword: str, api_key: str) -> str:
    model = AI_CONFIG["hf_model"]
    api_url = f"https://api-inference.huggingface.co/models/{model}"
    headers = {"Authorization": f"Bearer {api_key}"}
    prompt = (
        f"Eres experto en SEO semantico. Dame 5 a 10 entidades relacionadas "
        f"con '{keyword}'. Responde solo una lista separada por comas."
    )

    try:
        response = requests.post(
            api_url,
            headers=headers,
            json={
                "inputs": prompt,
                "parameters": {"max_new_tokens": 100, "temperature": 0.4},
            },
            timeout=20,
        )
    except requests.RequestException as exc:
        logger.warning("Hugging Face no disponible: %s", exc)
        return "N/A"

    if response.status_code != 200:
        logger.warning("Hugging Face respondio %s: %s", response.status_code, response.text[:300])
        return "N/A"

    data = response.json()
    if isinstance(data, list) and data and "generated_text" in data[0]:
        text = data[0]["generated_text"].strip()
        return _clean_hf_output(text, prompt)

    if isinstance(data, dict) and data.get("error"):
        logger.warning("Hugging Face respondio error: %s", data["error"])

    return "N/A"


def _parse_json_object(content: str) -> dict:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(content[start : end + 1])
            except json.JSONDecodeError:
                pass
    logger.warning("Respuesta IA no es JSON valido: %s", content[:300])
    return {}


def _clean_hf_output(text: str, prompt: str) -> str:
    text = text.replace(prompt, "").strip()
    if "[/INST]" in text:
        text = text.split("[/INST]", 1)[1].strip()
    return _sanitize_ai_text(text.strip(" \n\t:-"))[:500] or "N/A"


def _sanitize_ai_text(value: str | None) -> str:
    if not value:
        return ""
    replacements = {
        "\u0104": "",
        "\u00bf": "",
        "\u00a1": "",
    }
    text = str(value)
    for old, new in replacements.items():
        text = text.replace(old, new)
    return " ".join(text.split()).strip()


def _fallback_editorial_plan(keyword: str, news_context: list[str]) -> dict:
    base = keyword.strip()
    context_hint = ""
    if news_context:
        context_hint = f" Partir del debate que ya abrieron titulares recientes sobre {base}."

    return {
        "angulo": (
            f"Explicar por que {base} esta ganando interes y que debe saber el lector ahora."
            f"{context_hint}"
        ),
        "clickbait": _short_title(base),
        "entidades": _fallback_entities(base, news_context),
    }


def _short_title(keyword: str) -> str:
    title = f"{keyword}: lo que cambia ahora"
    return _limit_title(title)


def _limit_title(title: str) -> str:
    if len(title) <= 60:
        return title
    return title[:57].rstrip() + "..."


def _fallback_entities(keyword: str, news_context: list[str]) -> str:
    words: list[str] = []
    for text in [keyword, *news_context[:3]]:
        for raw in text.replace(",", " ").replace(":", " ").split():
            word = raw.strip(" .;!?()[]\"'").lower()
            if len(word) > 3 and word not in words:
                words.append(word)
    return ", ".join(words[:10]) or keyword
