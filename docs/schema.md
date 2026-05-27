# Schema database

Cinque tabelle, normalizzate, designate per il workflow editoriale del progetto.

## papers

Paper/articolo raccolto da una sorgente esterna (PubMed, arXiv, RSS).

| Colonna | Tipo | Note |
|---|---|---|
| id | int PK | |
| source | str(32) | `pubmed` / `arxiv` / `rss` |
| external_id | str(128) | PMID, arXiv ID, GUID feed |
| doi | str(256) | nullable, indicizzato |
| pmid | str(32) | nullable, indicizzato |
| title | text | |
| authors | text | "Last1 X, Last2 Y" |
| journal | str(256) | |
| abstract | text | |
| url | text | link permanente al record |
| published_at | timestamptz | |
| relevance_score | float | 0..10, vedere `services/ingest/relevance.py` |
| technical_level | str(16) | `low` / `medium` / `high` |
| status | str(24) | `new` / `used` / `skipped` |
| created_at | timestamptz | default now() |

Vincolo: `UNIQUE(source, external_id)`.

## contents

Bozza/contenuto Instagram generato (o creato manualmente).

| Colonna | Tipo | Note |
|---|---|---|
| id | int PK | |
| paper_id | int FK papers.id ON DELETE SET NULL | nullable |
| kind | str(24) | `carousel` / `reel` / `post` / `infographic` / `myth_reality` / `mini_explainer` / `bts` / `case_study` / `paper_commentary` |
| title | str(255) | |
| hook | text | prima frase |
| caption | text | |
| hashtags | text | "#a #b #c" |
| cta | text | |
| slides_json | jsonb | lista di `{index, title, body, visual_hint}` |
| reel_script | text | per kind=reel |
| provider | str(32) | `claude` / `openai` / `gemini` / `deepseek` |
| model | str(64) | nome esatto del modello |
| prompt | text | user prompt completo (audit trail) |
| validation_json | jsonb | report di validazione automatica |
| status | str(24) | `draft` / `approved` / `scheduled` / `published` / `rejected` |
| scheduled_at | timestamptz | |
| published_at | timestamptz | |
| created_at | timestamptz | default now() |
| updated_at | timestamptz | default now(), aggiornato on update |

## sources

Citazioni associate a un content, con esito della verifica.

| Colonna | Tipo | Note |
|---|---|---|
| id | int PK | |
| content_id | int FK contents.id ON DELETE CASCADE | |
| kind | str(24) | `doi` / `pmid` / `url` |
| identifier | str(256) | il DOI/PMID/URL |
| title | text | titolo del paper come restituito da CrossRef/PubMed |
| verified | bool | default false |
| verification_message | text | motivo del fallimento se non verificato |
| checked_at | timestamptz | |

## schedule_slots

Slot del calendario editoriale (un content può avere più slot, es. ri-pubblicazioni).

| Colonna | Tipo | Note |
|---|---|---|
| id | int PK | |
| content_id | int FK contents.id ON DELETE CASCADE | |
| slot_at | timestamptz | |
| channel | str(32) | default `instagram` |
| notes | text | |

## analytics

Performance Instagram di un content. Compilato manualmente (oppure futura integrazione Graph API).

| Colonna | Tipo | Note |
|---|---|---|
| id | int PK | |
| content_id | int FK contents.id ON DELETE CASCADE | |
| measured_at | timestamptz | default now() |
| impressions | int | nullable |
| reach | int | nullable |
| likes | int | |
| comments | int | |
| saves | int | |
| shares | int | |

## Flussi di stato

```
[paper.status]   new ─► used    (quando un content lo referenzia)
                  └─► skipped  (manuale dalla UI)

[content.status] draft ─► approved ─► scheduled ─► published
                       └─► rejected
```

## Migrations

Gestite con Alembic. Il file iniziale è `alembic/versions/0001_initial.py`. Per generare migrations nuove dopo aver modificato i modelli:

```bash
docker compose exec api alembic revision --autogenerate -m "descrizione"
docker compose exec api alembic upgrade head
```
