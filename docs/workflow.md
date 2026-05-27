# Workflow operativo

Esempio end-to-end di utilizzo del sistema.

## 1. Setup

```bash
cp .env.example .env
# inserisci almeno ANTHROPIC_API_KEY (o un'altra)
# imposta PUBMED_EMAIL con un'email reale (richiesto da NCBI)
docker compose up --build
```

Il servizio `api` lancia `alembic upgrade head` all'avvio. Il servizio `worker` esegue gli ingest periodici (default ogni 12h).

Dashboard: http://localhost:8000/
Docs OpenAPI: http://localhost:8000/docs

## 2. Ingest manuale (prima volta)

Da dashboard tab Paper → bottoni "Ingest PubMed/arXiv/RSS". Oppure:

```bash
curl -X POST http://localhost:8000/api/papers/ingest/pubmed
curl -X POST http://localhost:8000/api/papers/ingest/arxiv
```

I record vengono salvati con `relevance_score` (0..10) e `technical_level`. Ordinali per score nella dashboard per scegliere i più promettenti.

## 3. Generazione

Tre modi:

### a) Da paper

In Paper tab, clicca "Genera" su un record. Il form di generazione si apre con `paper_id` pre-compilato. Scegli kind, tech_level, provider. Clicca "Genera draft".

### b) Da prompt libero

Tab Genera → lascia paper_id vuoto, compila "Prompt libero" (es. "Spiega come la segmentazione AI sulle radiografie panoramiche supporta il clinico nell'identificare lesioni periapicali, con disclaimer sul ruolo del medico").

### c) API

```bash
curl -X POST http://localhost:8000/api/generation \
  -H 'Content-Type: application/json' \
  -d '{
    "kind": "carousel",
    "prompt": "Come la CNN supporta la rilevazione di carie",
    "technical_level": "medium",
    "provider": "claude",
    "target_slides": 7
  }'
```

## 4. Review

Il draft compare in tab Review (status=draft). Apri il dettaglio:

- **Validazione**: blocchi con badge OK/errori. Click "Rivalida" per riverificare anche le fonti (DOI/PMID via CrossRef/PubMed).
- **Slide**: ognuna con titolo, body, suggerimento visivo.
- **Caption / hashtag**: editabili inline. Click "Salva modifiche" per persistere.
- **Approva** / **Rigetta**: il bottone Approva è disabilitato se ci sono errori di validazione.

## 5. Scheduling

Click "Programma" sul contenuto approvato → inserisci data ISO (es. `2026-06-01T09:30:00`). Lo status passa a `scheduled`.

Esporta il calendario per Buffer/Later/Hootsuite:

```bash
curl -O http://localhost:8000/api/schedule/export.csv
```

## 6. Pubblicazione e analytics

Per ora la pubblicazione effettiva su Instagram è **manuale** (Meta Business Suite, app, o tool terzi). Una volta pubblicato, click "Marca pubblicato" nel dettaglio del content.

Per registrare le performance:

```bash
curl -X POST http://localhost:8000/api/analytics/<content_id> \
  -H 'Content-Type: application/json' \
  -d '{"likes": 240, "comments": 18, "saves": 31, "reach": 4200}'
```

Top engagement: tab Analytics oppure `GET /api/analytics/top/engagement`.

## 7. Validazione fonti — note importanti

Quando rivalidi un content, il sistema:

1. Estrae automaticamente tutti i DOI (regex `10.xxxx/...`) e PMID (`PMID: 12345`) dal testo (titolo, caption, slide, script).
2. Per ogni DOI fa GET `api.crossref.org/works/<doi>` → verifica esistenza + recupera titolo reale.
3. Per ogni PMID fa GET `eutils.ncbi.nlm.nih.gov/.../esummary.fcgi?db=pubmed&id=<pmid>`.
4. Aggiunge issue di tipo `source_not_verified` (severity=error) se la verifica fallisce → l'approvazione viene bloccata.

Questo significa che se l'AI inventa un DOI, il sistema **rifiuta** il contenuto. È la principale safety net contro hallucination scientifica.

## 8. Estensioni roadmap

Per chi vuole proseguire lo sviluppo:

- **Image generation**: aggiungere un service `services/imagegen/` con DALL-E/Stability/Imagen. Mantenere stile minimal medical-tech.
- **Meta Graph API**: aggiungere `services/publishing/instagram_graph.py` per pubblicazione diretta. Richiede un Instagram Business Account collegato a una Facebook Page e un long-lived token.
- **Embeddings + RAG**: aggiungere pgvector come estensione su Postgres, indicizzare gli abstract e usare retrieval per fornire contesto più ricco all'AI.
- **Multi-tenant**: oggi single-studio. Per gestire più studi, aggiungere tenant_id ovunque + auth (JWT).
