# Dental AI Content System

Sistema semi-automatico per la generazione, revisione, pianificazione e pubblicazione di contenuti Instagram scientifici sull'intelligenza artificiale applicata all'odontoiatria.

## Filosofia

Il sistema privilegia **qualità scientifica e credibilità professionale rispetto alla viralità pura**. Nessun contenuto viene pubblicato senza approvazione umana. Ogni claim deve poter essere ricondotto a una fonte verificabile (PubMed/DOI).

## Architettura

```
┌──────────────────┐   ┌────────────────┐   ┌────────────────┐
│ Ingest scientifico│──▶│  AI Generation  │──▶│  Validation    │
│ PubMed/arXiv/RSS │   │ Claude/OpenAI/  │   │ Content+Source │
└──────────────────┘   │ Gemini/DeepSeek │   └────────────────┘
                       └────────────────┘            │
                                                     ▼
┌──────────────────┐   ┌────────────────┐   ┌────────────────┐
│   Scheduler      │◀──│  Human Review  │◀──│   Draft Queue  │
│  (manual export) │   │  Approve/Reject│   │   (Postgres)   │
└──────────────────┘   └────────────────┘   └────────────────┘
```

Stack: **Python 3.11 + FastAPI + PostgreSQL 16 + APScheduler**, frontend single-page vanilla JS + Tailwind CDN, tutto containerizzato con Docker Compose.

## Quick start

```bash
cp .env.example .env
# editare .env e inserire almeno una API key (ANTHROPIC_API_KEY consigliata)

docker compose up --build
```

Servizi disponibili:
- API + docs OpenAPI: http://localhost:8000/docs
- Dashboard web: http://localhost:8000/
- PostgreSQL: localhost:5432

## Workflow utente

1. **Ingest** — il worker scarica periodicamente paper da PubMed/arXiv/RSS, calcola uno score di rilevanza per "AI + odontoiatria".
2. **Selezione** — dalla dashboard scegli un paper (o inserisci un prompt libero) e il tipo di output (carousel, reel, post).
3. **Generazione** — l'AI produce hook, caption, struttura slide-by-slide, CTA, hashtag, titolo scientifico breve.
4. **Validazione automatica** — controlli su lunghezza, hashtag count, presenza del disclaimer clinico, blacklist di claim assoluti, verifica DOI/PMID via CrossRef + PubMed.
5. **Review umana** — visualizzi il draft, modifichi, approvi o rigetti.
6. **Scheduling** — assegni una data al calendario editoriale; export per Buffer/Later/Meta Business Suite.
7. **Archivio** — fonti, caption, immagini e (in futuro) analytics restano in DB.

## Multi-provider AI

Il layer `services/ai` espone un'interfaccia unica. È sufficiente impostare le rispettive API key in `.env`:

- `ANTHROPIC_API_KEY` — Claude (consigliato per generazione scientifica)
- `OPENAI_API_KEY` — GPT-4 / GPT-4o
- `GOOGLE_API_KEY` — Gemini
- `DEEPSEEK_API_KEY` — DeepSeek

Il provider di default è configurabile con `DEFAULT_AI_PROVIDER` in `.env`. Ogni richiesta API può comunque sovrascriverlo passando `provider` nel body.

## Validazione

Due livelli, indipendenti:

- **Content rules** (`services/validation/content_rules.py`) — regole deterministiche su caption/slide/hashtag, blacklist di claim assoluti (es. "sostituisce il medico", "diagnosi al 100%"), presenza del disclaimer sul ruolo del clinico.
- **Source check** (`services/validation/source_check.py`) — per ogni paper citato verifica che DOI/PMID esistano davvero via CrossRef e NCBI E-utilities. Mai pubblicare un contenuto con citazioni inventate.

I test unitari in `tests/` coprono entrambi i livelli.

## Struttura

```
backend/app/
├── main.py              # entry FastAPI
├── core/                # config, db, logging
├── models/              # SQLAlchemy: Paper, Content, Source, ScheduleSlot
├── schemas/             # Pydantic
├── api/                 # router REST
├── services/
│   ├── ai/              # provider abstraction (Claude/OpenAI/Gemini/DeepSeek)
│   ├── ingest/          # PubMed, arXiv, RSS, scoring di rilevanza
│   ├── generation/      # carousel/reel/caption + prompts scientifici
│   └── validation/      # content rules + source check
└── workers/             # APScheduler per ingest periodico

frontend/                # dashboard single-page
docs/                    # piano editoriale 30 giorni, schema DB
tests/                   # pytest
```

## Estensioni previste (roadmap)

Le seguenti aree sono predisposte ma da completare in iterazioni successive:
- Image generation (stile medical-tech minimal) tramite DALL-E / Stability / Imagen
- Integrazione diretta Meta Business Suite (Graph API)
- Embeddings + RAG su archivio paper
- Analisi competitor e trend automatici
- Re-purpose carousel→reel→articolo

## Disclaimer

Questo è uno strumento di supporto editoriale. Tutti i contenuti generati devono essere **revisionati da un clinico** prima della pubblicazione. Il sistema impone la presenza del disclaimer "il giudizio del medico resta centrale, l'AI è uno strumento di supporto" ma non lo sostituisce alla revisione umana.
