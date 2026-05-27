"""Test sulle regole di validazione contenuti.

Coprono i casi piu' importanti del progetto:
- caption troppo lunga
- claim sensazionalistici / assoluti
- mancanza del disclaimer clinico
- vincoli carousel/reel
"""
from backend.app.services.validation.content_rules import validate_content_rules


CAPTION_OK = (
    "L'intelligenza artificiale puo' supportare il clinico nell'analisi delle radiografie "
    "panoramiche, accelerando la rilevazione di lesioni periapicali. Il giudizio clinico "
    "resta centrale: la decisione finale e' sempre del dentista. #odontoiatria #AI"
)

SLIDES_OK = [
    {"index": 1, "title": "Intro", "body": "AI come supporto al clinico in radiologia odontoiatrica."},
    {"index": 2, "title": "Come funziona", "body": "Reti CNN addestrate su dataset annotati supportano l'identificazione di pattern."},
    {"index": 3, "title": "Limiti", "body": "Bias di dataset, generalizzazione, falsi positivi: il clinico filtra."},
    {"index": 4, "title": "Conclusione", "body": "Il giudizio clinico resta centrale. L'AI riduce il carico cognitivo."},
]


def test_valid_carousel():
    r = validate_content_rules(
        kind="carousel", title="AI in radiologia odontoiatrica",
        caption=CAPTION_OK, hashtags="#odontoiatria #AI #radiologia",
        slides=SLIDES_OK,
    )
    assert r.ok, [i.message for i in r.issues]


def test_absolute_claim_detected():
    bad = CAPTION_OK + " L'AI sostituira' i dentisti entro pochi anni."
    r = validate_content_rules(
        kind="post", title="t", caption=bad, hashtags="#a",
    )
    codes = {i.code for i in r.issues}
    assert "absolute_claim" in codes
    assert r.ok is False


def test_missing_disclaimer_detected():
    bad = "L'AI analizza radiografie con grande precisione." * 5
    r = validate_content_rules(
        kind="post", title="Titolo Valido AI",
        caption=bad, hashtags="#odontoiatria #AI",
    )
    codes = {i.code for i in r.issues}
    assert "missing_clinical_disclaimer" in codes


def test_caption_too_long():
    long_caption = CAPTION_OK + ("x" * 3000)
    r = validate_content_rules(
        kind="post", title="T",
        caption=long_caption, hashtags="#a",
    )
    codes = {i.code for i in r.issues}
    assert "caption_too_long" in codes


def test_carousel_too_few_slides():
    r = validate_content_rules(
        kind="carousel", title="AI",
        caption=CAPTION_OK, hashtags="#a",
        slides=SLIDES_OK[:2],
    )
    codes = {i.code for i in r.issues}
    assert "carousel_too_few_slides" in codes


def test_reel_requires_script():
    r = validate_content_rules(
        kind="reel", title="AI in odontoiatria",
        caption=CAPTION_OK, hashtags="#a",
        reel_script=None,
    )
    codes = {i.code for i in r.issues}
    assert "reel_script_missing" in codes


def test_too_many_hashtags():
    ht = " ".join(f"#tag{i}" for i in range(45))
    r = validate_content_rules(
        kind="post", title="AI in odontoiatria",
        caption=CAPTION_OK, hashtags=ht,
    )
    codes = {i.code for i in r.issues}
    assert "hashtags_too_many" in codes


def test_english_caption_valid():
    """English caption with EN disclaimer should also validate."""
    caption_en = (
        "AI can support the clinician in analyzing panoramic radiographs, "
        "speeding up the detection of periapical lesions. Clinical judgment "
        "remains central: the final decision is always the dentist's. "
        "#dentistry #AI"
    )
    r = validate_content_rules(
        kind="post", title="AI in dental imaging",
        caption=caption_en, hashtags="#dentistry #AI",
    )
    assert r.ok, [i.message for i in r.issues]


def test_english_absolute_claim_detected():
    bad_en = (
        "AI will replace the dentists soon. Our model has 100% accuracy "
        "and is never wrong. The future is here."
    )
    r = validate_content_rules(
        kind="post", title="x", caption=bad_en, hashtags="#a",
    )
    codes = [i.code for i in r.issues]
    assert codes.count("absolute_claim") >= 3  # multiple matches expected
