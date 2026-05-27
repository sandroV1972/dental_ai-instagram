"""Orchestratore della generazione AI: prepara contesto, chiama provider, parsa JSON."""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Optional

from ...core.config import settings
from ..ai import AIProviderError, get_provider
from .prompts import build_system_prompt, build_user_prompt

logger = logging.getLogger(__name__)


@dataclass
class GenerationResult:
    title: str
    hook: Optional[str]
    caption: str
    hashtags: str
    cta: Optional[str]
    slides: list[dict[str, Any]]
    reel_script: Optional[str]
    provider: str
    model: str
    raw_prompt: str
    raw_response: str


_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


def _json_state(text: str) -> tuple[list[str], bool]:
    """Calcola lo stack di parentesi aperte e se si finisce dentro una stringa."""
    stack: list[str] = []
    in_string = False
    escape = False
    for ch in text:
        if escape:
            escape = False
            continue
        if ch == "\\" and in_string:
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch in "{[":
            stack.append(ch)
        elif ch == "}":
            if stack and stack[-1] == "{":
                stack.pop()
        elif ch == "]":
            if stack and stack[-1] == "[":
                stack.pop()
    return stack, in_string


def _close_open_json(text: str, stack: list[str], in_string: bool) -> str:
    """Chiude stringa aperta, virgole/colon penzolanti, e tutte le parentesi rimaste."""
    out = text
    if in_string:
        out += '"'
    # rimuovi spazi/virgole/colon penzolanti alla fine
    out = out.rstrip(" \t\n\r,:")
    # se rimane una "key" senza valore (es. '... "body"'), rimuovila
    # heuristic: se finisce con '"' ma il carattere prima del '"' di apertura era ','/'{'/'['
    if out.endswith('"'):
        # trova la '"' di apertura della key dangling
        open_q = out.rfind('"', 0, len(out) - 1)
        if open_q > 0:
            prev = out[:open_q].rstrip()
            if prev and prev[-1] in ",{[":
                out = prev.rstrip(",")
    for op in reversed(stack):
        out += "}" if op == "{" else "]"
    return out


def _try_repair_truncated_json(s: str) -> str:
    """Best-effort repair per JSON troncato da LLM.

    Strategia in due passi:
    1. Chiude stringa + parentesi aperte. Se parsa, ritorna.
    2. Altrimenti retrocede a ogni virgola fuori-stringa (dalla piu' recente),
       prova a chiudere il prefisso e tenta json.loads. Si ferma alla prima
       valida (preservando piu' contenuto possibile).
    """
    stack, in_string = _json_state(s)
    candidate = _close_open_json(s, list(stack), in_string)
    try:
        json.loads(candidate)
        return candidate
    except json.JSONDecodeError:
        pass

    # posizioni delle virgole fuori-stringa (per troncamento progressivo)
    commas: list[int] = []
    in_str = False
    esc = False
    for i, ch in enumerate(s):
        if esc:
            esc = False
            continue
        if ch == "\\" and in_str:
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if not in_str and ch == ",":
            commas.append(i)

    for idx in reversed(commas):
        sub = s[:idx]
        sub_stack, sub_in_str = _json_state(sub)
        cand = _close_open_json(sub, list(sub_stack), sub_in_str)
        try:
            json.loads(cand)
            return cand
        except json.JSONDecodeError:
            continue

    return candidate  # ultima chance, anche se non parsa


def _extract_json(text: str) -> dict[str, Any]:
    """Estrae un oggetto JSON dal testo, tollerando markdown fence e troncamenti.

    Strategia, in ordine:
    1. json.loads diretto sul testo "ripulito" (rimuove ```json ... ``` se presenti)
    2. regex per estrarre tra prima `{` e ultima `}` e riprovare
    3. repair best-effort per JSON troncato (LLM che esaurisce max_tokens)
    """
    if not text:
        raise ValueError("Risposta AI vuota")
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    m = _JSON_BLOCK_RE.search(text)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    # ultimo tentativo: repair sul JSON troncato (a partire dalla prima `{`)
    start = text.find("{")
    if start >= 0:
        candidate = text[start:]
        try:
            repaired = _try_repair_truncated_json(candidate)
            return json.loads(repaired)
        except (json.JSONDecodeError, ValueError):
            pass
    raise ValueError(
        f"Impossibile estrarre JSON dalla risposta. Lunghezza={len(text)}. "
        f"Prime 400 char: {text[:400]!r} ... ultime 200 char: {text[-200:]!r}"
    )


def _topic_brief(paper_title: Optional[str], abstract: Optional[str], free_prompt: Optional[str]) -> str:
    if free_prompt:
        return free_prompt.strip()
    if paper_title:
        return paper_title.strip()
    return "Applicazioni dell'AI in odontoiatria"


def _paper_context(paper_title: Optional[str], abstract: Optional[str],
                   journal: Optional[str], authors: Optional[str],
                   doi: Optional[str], pmid: Optional[str]) -> Optional[str]:
    if not paper_title and not abstract:
        return None
    parts = []
    if paper_title:
        parts.append(f"Titolo: {paper_title}")
    if authors:
        parts.append(f"Autori: {authors}")
    if journal:
        parts.append(f"Rivista: {journal}")
    if doi:
        parts.append(f"DOI: {doi}")
    if pmid:
        parts.append(f"PMID: {pmid}")
    if abstract:
        parts.append(f"Abstract:\n{abstract}")
    return "\n".join(parts)


def generate_content(
    *,
    kind: str,
    provider_name: Optional[str] = None,
    free_prompt: Optional[str] = None,
    paper_title: Optional[str] = None,
    paper_abstract: Optional[str] = None,
    paper_journal: Optional[str] = None,
    paper_authors: Optional[str] = None,
    paper_doi: Optional[str] = None,
    paper_pmid: Optional[str] = None,
    technical_level: str = "medium",
    target_slides: Optional[int] = None,
    extra_instructions: Optional[str] = None,
) -> GenerationResult:
    """Genera un draft di contenuto Instagram a partire da prompt libero e/o paper."""
    provider = get_provider(provider_name)
    n_slides = target_slides or 6
    n_slides = max(settings.CAROUSEL_MIN_SLIDES, min(settings.CAROUSEL_MAX_SLIDES, n_slides))

    system_prompt = build_system_prompt(
        author_name=settings.AUTHOR_NAME,
        handle=settings.INSTAGRAM_HANDLE,
        tagline=settings.BRAND_TAGLINE,
        voice=settings.BRAND_VOICE,
        language=settings.CONTENT_LANGUAGE,
    )
    user_prompt = build_user_prompt(
        kind=kind,
        topic_brief=_topic_brief(paper_title, paper_abstract, free_prompt),
        tech_level=technical_level,
        n_slides=n_slides,
        paper_context=_paper_context(
            paper_title, paper_abstract, paper_journal, paper_authors, paper_doi, paper_pmid,
        ),
        extra_instructions=extra_instructions,
        language=settings.CONTENT_LANGUAGE,
    )

    try:
        resp = provider.complete(
            system=system_prompt, user=user_prompt,
            json_mode=True, temperature=0.4, max_tokens=4096,
        )
    except AIProviderError:
        raise
    except Exception as e:  # noqa: BLE001
        raise AIProviderError(f"Errore inatteso dal provider: {e}") from e

    try:
        data = _extract_json(resp.text)
    except ValueError as e:
        raise AIProviderError(f"Risposta AI non parsabile: {e}") from e

    slides = data.get("slides") or []
    # Normalizza slides
    norm_slides = []
    for i, s in enumerate(slides, start=1):
        if not isinstance(s, dict):
            continue
        norm_slides.append({
            "index": int(s.get("index", i)),
            "title": str(s.get("title", "")).strip(),
            "body": str(s.get("body", "")).strip(),
            "visual_hint": (s.get("visual_hint") or None),
        })

    return GenerationResult(
        title=str(data.get("title", "")).strip()[:255] or _topic_brief(paper_title, paper_abstract, free_prompt)[:255],
        hook=(str(data.get("hook")).strip() if data.get("hook") else None),
        caption=str(data.get("caption", "")).strip(),
        hashtags=str(data.get("hashtags", "")).strip(),
        cta=(str(data.get("cta")).strip() if data.get("cta") else None),
        slides=norm_slides,
        reel_script=(str(data.get("reel_script")).strip() if data.get("reel_script") else None),
        provider=provider.name,
        model=provider.model,
        raw_prompt=user_prompt,
        raw_response=resp.text,
    )
