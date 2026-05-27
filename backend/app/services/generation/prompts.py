"""Prompt scientifici e tone-of-voice per il sistema.

Prompt bilingue (EN/IT). La lingua di OUTPUT viene scelta da
`settings.CONTENT_LANGUAGE` (en|it). Il *system prompt* parla all'AI
in inglese sempre (lingua piu' robusta per istruzioni complesse), ma
istruisce il modello a generare il CONTENUTO nella lingua scelta.

Vincoli applicati sempre:
- ruolo centrale del clinico
- no claim assoluti / no sensazionalismo
- citazioni solo se fornite (no invenzioni)
- prima persona dell'autore (canale personale, non studio)
"""
from __future__ import annotations

from typing import Literal, Optional


SYSTEM_BASE = """You are the scientific editor of a personal Instagram channel run by a dentist who focuses on artificial intelligence applied to clinical practice. The channel builds the author's personal brand as a competent, scientific, trustworthy voice on AI in dentistry.

The author signs as {author_name} ({handle}) — tagline: "{tagline}".

OUTPUT LANGUAGE: write ALL post content (title, hook, slides, caption, CTA, hashtags) in {language_full}. JSON keys stay in English (as schema). Audience: international.

NON-NEGOTIABLE PRINCIPLES:
1. Tone: {voice}.
2. Write in FIRST PERSON of the author when natural (e.g. "in my clinical practice I observe...", "from the literature I follow..."). NEVER use "in our practice", "our team", "we at the clinic": this is a PERSONAL channel, not a corporate one.
3. NEVER claim AI replaces, supersedes, or outperforms the dentist as a whole.
4. ALWAYS reinforce, explicitly or implicitly, that:
   - AI supports the clinician
   - the clinician's judgment remains central
   - the final decision is always human
   - technology improves precision, efficiency and prevention
5. AVOID absolute claims ("always", "100%", "never wrong", "revolutionizes").
   Prefer hedged language ("supports", "may contribute to", "in recent studies").
6. AVOID crypto/AI hype: no explosive emojis, no "game changer", no "the future is here".
7. If you cite a paper, USE ONLY the information explicitly provided in the context.
   NEVER fabricate titles, authors, journals, years, DOIs, or PMIDs.
   If you don't have a source, write generic statements without specific citations.
8. {language_label}: scientific yet accessible to a curious patient.
   Technical terms (CBCT, CNN, semantic segmentation) must be briefly defined.
9. Clinical disclaimer: included at least once. Example (English):
   "Technology supports clinical judgment, which remains central to therapeutic decisions."
   Example (Italian): "La tecnologia supporta il giudizio clinico, che resta centrale nelle decisioni terapeutiche."
10. Never promise medical outcomes. Never diagnose.

Target audience: patients curious about innovation, dental colleagues, students, healthcare professionals.
"""


# --- USER prompt templates (still in English, instruct to produce JSON) ---

CAROUSEL_USER_TEMPLATE = """Generate an Instagram carousel of {n_slides} slides on the topic:
{topic_brief}

Required technical level: {tech_level}.

{paper_block}{extra_block}

Respond ONLY with valid JSON matching this schema (content fields in {language_full}; keys stay English):
{{
  "title": "short scientific title (max 80 chars)",
  "hook": "opening line of slide 1, max 90 chars, engaging but never sensational",
  "slides": [
    {{
      "index": 1,
      "title": "slide title (max 60 chars)",
      "body": "slide body text (max 240 chars, short sentences, mobile-readable)",
      "visual_hint": "ENGLISH visual prompt for the image generator/search (e.g. 'panoramic dental radiograph with AI segmentation overlay', 'John McCarthy at Dartmouth conference 1956'). Keep this in English regardless of content language — it feeds image search/AI."
    }}
    // ... one entry per slide
  ],
  "caption": "complete Instagram caption (max 2000 chars). Must include the clinical disclaimer.",
  "cta": "final call-to-action, one sentence, NOT commercial-aggressive (e.g. 'I will cover this in more depth next week')",
  "hashtags": "10-20 carefully chosen hashtags separated by spaces (dentistry, AI, scientific outreach). Not spammy."
}}

Remember: no absolute claims, central role of the clinician, no sensationalism.
"""


REEL_USER_TEMPLATE = """Generate an Instagram Reel (30-45 seconds) on the topic:
{topic_brief}

Technical level: {tech_level}.

{paper_block}{extra_block}

A reel is a vertical short video. Produce BOTH:
- a continuous narration script (for voiceover)
- a sequence of 5-7 visual scenes (each will become one ~4s frame in the slideshow video)

Respond ONLY with valid JSON (content in {language_full}; keys English; visual_hint stays English):
{{
  "title": "reel title (max 70 chars)",
  "hook": "opening sentence, first 3 seconds, engaging non-sensational (max 80 chars)",
  "reel_script": "narration script with approximate timing 'SCENE 1 (0-5s): ...\\nSCENE 2 (5-15s): ...'. Max 700 chars.",
  "slides": [
    {{
      "index": 1,
      "title": "short hook on screen (max 50 chars)",
      "body": "one short sentence overlay (max 120 chars, large text for vertical video)",
      "visual_hint": "ENGLISH visual prompt for the scene background (image generator/search)"
    }}
    // 5 to 7 scenes total
  ],
  "caption": "caption under the reel (max 1500 chars), includes clinical disclaimer",
  "cta": "final call-to-action",
  "hashtags": "10-20 hashtags separated by spaces"
}}
"""


STORY_USER_TEMPLATE = """Generate a single Instagram Story (vertical 1080x1920) on the topic:
{topic_brief}

A story is one tall image with very short overlay text. Instagram users tap through stories quickly,
so be PUNCHY and SCANNABLE. No long paragraphs.

Technical level: {tech_level}.

{paper_block}{extra_block}

Respond ONLY with valid JSON (content in {language_full}; keys English; visual_hint stays English):
{{
  "title": "main headline on the story, max 50 chars, big and bold",
  "hook": "one short supporting line, max 80 chars",
  "caption": "short caption (max 500 chars) — used as DM reply prompt / context for the operator. Includes clinical disclaimer.",
  "cta": "tap/swipe-up text or call-to-action (max 40 chars, e.g. 'Read more in the next post')",
  "hashtags": "5-10 hashtags separated by spaces",
  "visual_hint": "ENGLISH visual prompt for the story background"
}}
"""


POST_USER_TEMPLATE = """Generate a single Instagram post (image + caption) on the topic:
{topic_brief}

Technical level: {tech_level}.

{paper_block}{extra_block}

Respond ONLY with valid JSON (content in {language_full}; keys English; visual_hint stays English):
{{
  "title": "title (max 80 chars)",
  "hook": "first line of caption, engaging (max 90 chars)",
  "caption": "complete Instagram caption (max 2000 chars), includes clinical disclaimer",
  "cta": "final call-to-action",
  "hashtags": "10-20 hashtags separated by spaces",
  "visual_hint": "ENGLISH visual prompt for image generator/search"
}}
"""


MYTH_REALITY_USER_TEMPLATE = """Generate a "Myth vs Reality" carousel of {n_slides} slides on the topic:
{topic_brief}

Suggested structure:
- slide 1: cover
- slides 2..{n_minus_1}: alternate "MYTH: ..." with "REALITY: ..."
- last slide: summary + clinical disclaimer

Technical level: {tech_level}.

{paper_block}{extra_block}

Respond ONLY with valid JSON (same schema as the standard carousel; content in {language_full}; keys English; visual_hint stays English).
"""


_LANG_FULL = {"en": "English", "it": "Italian"}
_LANG_LABEL = {"en": "English", "it": "Italian"}


def build_user_prompt(*, kind: str, topic_brief: str, tech_level: str,
                      n_slides: int, paper_context: Optional[str],
                      extra_instructions: Optional[str],
                      language: Literal["en", "it"] = "en") -> str:
    paper_block = ""
    if paper_context:
        paper_block = (
            "Scientific context provided (use ONLY this, do not invent further details):\n"
            f"\"\"\"\n{paper_context}\n\"\"\"\n\n"
        )
    extra_block = ""
    if extra_instructions:
        extra_block = f"Additional user instructions: {extra_instructions}\n\n"

    if kind == "reel":
        tmpl = REEL_USER_TEMPLATE
    elif kind == "post":
        tmpl = POST_USER_TEMPLATE
    elif kind == "story":
        tmpl = STORY_USER_TEMPLATE
    elif kind == "myth_reality":
        tmpl = MYTH_REALITY_USER_TEMPLATE
    else:  # carousel / infographic / mini_explainer / bts / case_study / paper_commentary
        tmpl = CAROUSEL_USER_TEMPLATE

    return tmpl.format(
        topic_brief=topic_brief.strip() or "AI applications in dentistry",
        tech_level=tech_level,
        n_slides=n_slides,
        n_minus_1=max(2, n_slides - 1),
        paper_block=paper_block,
        extra_block=extra_block,
        language_full=_LANG_FULL.get(language, "English"),
    )


def build_system_prompt(*, author_name: str, handle: str, tagline: str, voice: str,
                        language: Literal["en", "it"] = "en") -> str:
    return SYSTEM_BASE.format(
        author_name=author_name, handle=handle, tagline=tagline, voice=voice,
        language_full=_LANG_FULL.get(language, "English"),
        language_label=_LANG_LABEL.get(language, "English"),
    )
