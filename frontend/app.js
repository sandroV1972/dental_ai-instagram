// Dashboard SPA + Wizard 5-step + Canvas Editor (Fabric.js)
// Vanilla JS, niente build step.

// =========================================================================
//  API helper
// =========================================================================
const api = (path, opts = {}) =>
  fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts,
  }).then(async (r) => {
    if (!r.ok) {
      const t = await r.text();
      throw new Error(`HTTP ${r.status}: ${t}`);
    }
    const ct = r.headers.get("content-type") || "";
    return ct.includes("application/json") ? r.json() : r.text();
  });

function escapeHtml(s) {
  return (s || "").replace(/[&<>"']/g, (m) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[m]));
}

function statusPill(s) {
  const colors = {
    draft: "bg-amber-100 text-amber-800", approved: "bg-emerald-100 text-emerald-800",
    scheduled: "bg-blue-100 text-blue-800", rejected: "bg-rose-100 text-rose-800",
    published: "bg-slate-800 text-white",
  };
  return `<span class="inline-block px-2 py-0.5 rounded-full text-xs ${colors[s] || "bg-slate-200"}">${s}</span>`;
}

// =========================================================================
//  Tabs
// =========================================================================
const tabs = document.querySelectorAll(".tab-btn");
const panels = document.querySelectorAll("[data-tab-panel]");
tabs.forEach((b) =>
  b.addEventListener("click", () => {
    tabs.forEach((x) => { x.classList.remove("bg-violet-600", "text-white"); x.style.background = ""; x.style.color = ""; });
    b.style.background = "var(--primary)"; b.style.color = "#fff";
    panels.forEach((p) =>
      p.classList.toggle("hidden", p.dataset.tabPanel !== b.dataset.tab),
    );
    if (b.dataset.tab === "papers") loadPapers();
    if (b.dataset.tab === "library") loadReview();
    if (b.dataset.tab === "calendar") loadCalendar();
    if (b.dataset.tab === "analytics") loadAnalytics();
    if (b.dataset.tab === "publish") loadPublishStatus();
  }),
);
document.querySelector('[data-tab="create"]').click();

// Health + providers
api("/health").then((h) => {
  document.getElementById("healthBadge").innerHTML =
    `env: <b>${h.env}</b> · provider: <b>${h.default_provider}</b>`;
  const sel = document.getElementById("w_provider");
  if (sel) {
    h.providers_configured.forEach((p) => {
      const o = document.createElement("option");
      o.value = p; o.textContent = p; sel.appendChild(o);
    });
  }
});

// =========================================================================
//  WIZARD STATE
// =========================================================================
const W = {
  step: 1,
  kind: "carousel",
  source: "pollinations",
  visualPrompt: "",
  variantsSession: null,
  variants: [],          // [{index, url}]
  selectedVariant: null, // {index, url}
  topicPrompt: "",
  techLevel: "medium",
  provider: "",
  targetSlides: 6,
  paperId: null,
  extra: "",
  text: null,            // {title, hook, caption, hashtags, cta, slides: [{index,title,body,visual_hint}], reel_script}
  contentId: null,
  // Canvas: one Fabric instance per slide
  fabric: null,
  canvases: {},          // slideIndex → fabric.Canvas instance (kept once initialised)
  canvasState: {},       // slideIndex → fabric JSON (for switching)
  currentSlide: 1,
};

const STEPS = 5;

function showStep(n) {
  W.step = n;
  document.querySelectorAll("[data-wstep]").forEach((el) => {
    el.classList.toggle("hidden", parseInt(el.dataset.wstep, 10) !== n);
  });
  // Aggiorna stepper
  document.querySelectorAll(".step-dot").forEach((d) => {
    const s = parseInt(d.dataset.step, 10);
    d.classList.remove("active", "done");
    if (s < n) d.classList.add("done");
    else if (s === n) d.classList.add("active");
  });
  document.querySelectorAll(".step-line").forEach((l, idx) => {
    l.classList.toggle("done", idx + 1 < n);
  });
  // Hook per step 4 (init canvas)
  if (n === 4) ensureCanvasEditor();
  if (n === 5) renderFinalizeStep();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function wizardNext() {
  if (W.step === 1) {
    // Pre-popola visualPrompt e topicPrompt se vuoti, sulla base del nulla (l'utente li riempie ora)
    showStep(2);
  } else if (W.step === 2) {
    if (!W.selectedVariant) {
      alert("Scegli una delle 3 opzioni di sfondo prima di proseguire (o usa 'Salta sfondo' per gradient dark).");
      return;
    }
    showStep(3);
  } else if (W.step === 3) {
    if (!W.text) {
      alert("Genera prima il testo dal prompt.");
      return;
    }
    showStep(4);
  } else if (W.step === 4) {
    // salva canvas state corrente prima di passare alla finalize
    saveCurrentCanvasState();
    showStep(5);
  }
}
function wizardBack() {
  if (W.step > 1) showStep(W.step - 1);
}

// --- Step 1: format pickers ---
function setupPicker(containerId, dataAttr, cb) {
  const root = document.getElementById(containerId);
  if (!root) return;
  root.addEventListener("click", (e) => {
    const btn = e.target.closest("button.pick-card");
    if (!btn) return;
    root.querySelectorAll(".pick-card").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    cb(btn.dataset[dataAttr]);
  });
}
setupPicker("w_formatPicker", "kind", (v) => { W.kind = v; });
setupPicker("w_sourcePicker", "source", (v) => { W.source = v; updateSourceHint(); });

const SOURCE_HINTS = {
  pollinations: "✅ <b>FREE, no auth</b>. Funziona con prompt sia inglese sia italiano. Best per concetti astratti, fotografie evocative. 10-40s per immagine.",
  wikimedia: "⚠ Usa <b>nomi propri inglesi e termini brevi</b>. Es: <i>'Alan Turing portrait'</i>, NON <i>'foto di Touring per ricordare la nascita dell'AI'</i>. Wikimedia indicizza solo file reali della sua libreria.",
  unsplash: "📸 Foto stock di alta qualità. Inglese funziona meglio. Richiede UNSPLASH_ACCESS_KEY in .env. Best per studi dentistici moderni, lab, tecnologia.",
  gemini_image: "💳 <b>Richiede billing su Google Cloud</b> con Vertex AI abilitato. Free tier non incluso. Se vedi limit:0 non hai accesso al modello.",
  ai: "💳 <b>Imagen 3 richiede billing</b> su Google Cloud. Stessa cosa di Gemini Image: serve un progetto pagante.",
};
function updateSourceHint() {
  const el = document.getElementById("w_sourceHint");
  if (el) el.innerHTML = SOURCE_HINTS[W.source] || "";
}
// hint iniziale (default pollinations)
setTimeout(updateSourceHint, 0);

// --- Step 2: variants ---
async function wizardGenerateVariants() {
  const vp = document.getElementById("w_visualPrompt").value.trim();
  if (!vp) { alert("Inserisci un visual prompt."); return; }
  W.visualPrompt = vp;
  const status = document.getElementById("w_variantsStatus");
  const area = document.getElementById("w_variantsArea");
  status.textContent = "Generazione in corso (può richiedere 15-45 sec)…";
  area.innerHTML = "";
  document.getElementById("w_genVariantsBtn").disabled = true;
  document.getElementById("w_step2NextBtn").disabled = true;
  W.selectedVariant = null;
  try {
    const res = await api("/wizard/variants", {
      method: "POST",
      body: JSON.stringify({
        visual_hint: vp, source: W.source, n: 3,
        aspect_ratio: W.kind === "post" ? "1:1" : "3:4",
        is_cover: true,
      }),
    });
    if (!res.variants.length) {
      let diagHtml = "";
      if (res.wikimedia_diag) {
        const d = res.wikimedia_diag;
        diagHtml = `
          <div class="mt-2 text-xs text-rose-800">
            Diagnostica Wikimedia:
            <code>raw=${d.raw_pages || 0}, kept=${d.kept || 0}, filtered_ext=${d.filtered_ext || 0}, filtered_size=${d.filtered_size || 0}, filtered_license=${d.filtered_license || 0}, dl_failed=${d.download_failed || 0}</code>
            <div class="mt-1">
              <a class="underline" target="_blank" href="/api/wizard/wikimedia-debug?q=${encodeURIComponent(W.visualPrompt)}">Vedi cosa risponde Wikimedia raw →</a>
            </div>
          </div>`;
      }
      area.innerHTML = `<div class="col-span-3 text-sm text-rose-700 bg-rose-50 border border-rose-200 rounded p-3">
        <div>Nessuna variante generata. ${(res.errors || []).map(e => escapeHtml(e)).join("; ")}</div>
        ${diagHtml}
      </div>`;
      status.textContent = "";
      return;
    }
    W.variantsSession = res.session_id;
    W.variants = res.variants;
    const ts = Date.now();
    area.innerHTML = res.variants.map(v => `
      <div class="variant-card" data-vidx="${v.index}" onclick="selectVariant(${v.index}, '${v.url}')">
        <img src="${v.url}?t=${ts}" class="w-full h-48 object-cover" />
        <div class="p-2 text-xs text-slate-600">Opzione ${v.index}</div>
      </div>`).join("");
    if ((res.errors || []).length) {
      area.innerHTML += `<div class="col-span-3 text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded p-2">Alcune varianti non generate: ${res.errors.map(escapeHtml).join("; ")}</div>`;
    }
    status.textContent = `${res.variants.length} opzioni pronte. Clicca quella che preferisci.`;
  } catch (e) {
    status.innerHTML = `<span class="text-rose-700">Errore: ${e.message}</span>`;
  } finally {
    document.getElementById("w_genVariantsBtn").disabled = false;
  }
}

function selectVariant(idx, url) {
  W.selectedVariant = { index: idx, url };
  document.querySelectorAll(".variant-card").forEach(c => {
    c.classList.toggle("active", parseInt(c.dataset.vidx, 10) === idx);
  });
  document.getElementById("w_step2NextBtn").disabled = false;
}

async function wizardUploadImage(event) {
  const file = event.target.files && event.target.files[0];
  if (!file) return;
  const status = document.getElementById("w_variantsStatus");
  status.textContent = `Upload ${file.name}…`;
  try {
    const fd = new FormData();
    fd.append("file", file);
    const r = await fetch("/api/wizard/upload-image", { method: "POST", body: fd });
    if (!r.ok) throw new Error(await r.text());
    const res = await r.json();
    // Mostra l'immagine uploaded come quarta variante e seleziona automaticamente
    const area = document.getElementById("w_variantsArea");
    const ts = Date.now();
    const html = `
      <div class="variant-card active" data-vidx="upload" onclick="selectVariant('upload', '${res.url}')">
        <img src="${res.url}?t=${ts}" class="w-full h-48 object-cover" />
        <div class="p-2 text-xs text-slate-600">📁 Tua immagine: ${escapeHtml(res.filename || 'upload')}</div>
      </div>`;
    if (area.children.length === 0 || area.querySelector(".text-rose-700, .text-slate-500")) {
      area.innerHTML = html;
    } else {
      area.insertAdjacentHTML("afterbegin", html);
    }
    selectVariant("upload", res.url);
    status.innerHTML = `<span class="text-emerald-700">Immagine caricata, selezionata.</span>`;
  } catch (e) {
    status.innerHTML = `<span class="text-rose-700">Upload fallito: ${e.message}</span>`;
  }
}

function wizardSkipBg() {
  // Salta lo sfondo → niente background, solo dark navy
  W.selectedVariant = { index: 0, url: null };  // url=null → loadSlideIntoCanvas useremo solo colore
  document.getElementById("w_step2NextBtn").disabled = false;
  document.getElementById("w_variantsStatus").innerHTML =
    `<span class="text-slate-600">Sfondo saltato. Le slide useranno solo il colore dark navy.</span>`;
}

// --- Step 3: text generation ---
async function wizardGenerateText() {
  const prompt = document.getElementById("w_topicPrompt").value.trim();
  if (!prompt) { alert("Scrivi un prompt per il contenuto."); return; }
  W.topicPrompt = prompt;
  W.techLevel = document.getElementById("w_techLevel").value;
  W.provider = document.getElementById("w_provider").value || "";
  W.targetSlides = parseInt(document.getElementById("w_targetSlides").value || "6", 10);
  W.paperId = parseInt(document.getElementById("w_paperId").value || "0", 10) || null;
  W.extra = document.getElementById("w_extra").value || "";

  const status = document.getElementById("w_textStatus");
  const area = document.getElementById("w_textPreview");
  status.textContent = "Generazione testo in corso (15-45 sec)…";
  area.innerHTML = "";
  document.getElementById("w_genTextBtn").disabled = true;
  document.getElementById("w_step3NextBtn").disabled = true;

  const payload = {
    kind: W.kind, prompt, paper_id: W.paperId,
    technical_level: W.techLevel,
    provider: W.provider || undefined,
    target_slides: W.targetSlides,
    extra_instructions: W.extra || undefined,
  };
  Object.keys(payload).forEach(k => { if (payload[k] == null || payload[k] === "") delete payload[k]; });

  try {
    // Usiamo l'endpoint /generation (solo testo, niente render — il render lo faremo nel canvas)
    const c = await api("/generation", { method: "POST", body: JSON.stringify(payload) });
    W.contentId = c.id;
    W.text = {
      title: c.title, hook: c.hook, caption: c.caption,
      hashtags: c.hashtags, cta: c.cta, reel_script: c.reel_script,
      slides: c.slides_json || [],
    };
    renderTextPreview();
    status.innerHTML = `<span class="text-emerald-700">Testo pronto (#${c.id}). Puoi modificare qui sotto prima di passare al canvas.</span>`;
    document.getElementById("w_step3NextBtn").disabled = false;
  } catch (e) {
    status.innerHTML = `<span class="text-rose-700">Errore: ${e.message}</span>`;
  } finally {
    document.getElementById("w_genTextBtn").disabled = false;
  }
}

function renderTextPreview() {
  const t = W.text;
  const area = document.getElementById("w_textPreview");
  area.innerHTML = `
    <div class="bg-slate-50 border border-slate-200 rounded-lg p-3 space-y-3">
      <div>
        <label class="text-xs font-medium text-slate-600">Titolo</label>
        <input id="t_title" class="w-full border-slate-300 rounded text-sm mt-1" value="${escapeHtml(t.title || "")}" />
      </div>
      <div>
        <label class="text-xs font-medium text-slate-600">Hook</label>
        <input id="t_hook" class="w-full border-slate-300 rounded text-sm mt-1" value="${escapeHtml(t.hook || "")}" />
      </div>
      ${(t.slides && t.slides.length) ? `
        <div>
          <label class="text-xs font-medium text-slate-600">Slide (${t.slides.length})</label>
          <div class="space-y-2 mt-1" id="t_slidesEditor">
            ${t.slides.map((s, i) => `
              <div class="bg-white border border-slate-200 rounded p-2">
                <div class="text-xs text-slate-400 mb-1">Slide ${s.index ?? i + 1}</div>
                <input data-sl="${i}" data-fld="title" class="t_slide w-full border-slate-300 rounded text-sm mb-1" value="${escapeHtml(s.title || "")}" />
                <textarea data-sl="${i}" data-fld="body" rows="2" class="t_slide w-full border-slate-300 rounded text-sm">${escapeHtml(s.body || "")}</textarea>
              </div>`).join("")}
          </div>
        </div>` : ""}
      <div>
        <label class="text-xs font-medium text-slate-600">Caption (per IG, non per le slide)</label>
        <textarea id="t_caption" rows="4" class="w-full border-slate-300 rounded text-sm mt-1">${escapeHtml(t.caption || "")}</textarea>
      </div>
      <div>
        <label class="text-xs font-medium text-slate-600">Hashtag</label>
        <input id="t_hashtags" class="w-full border-slate-300 rounded text-sm mt-1" value="${escapeHtml(t.hashtags || "")}" />
      </div>
      ${t.cta ? `<div>
        <label class="text-xs font-medium text-slate-600">CTA</label>
        <input id="t_cta" class="w-full border-slate-300 rounded text-sm mt-1" value="${escapeHtml(t.cta)}" />
      </div>` : ""}
      ${t.reel_script ? `<div>
        <label class="text-xs font-medium text-slate-600">Reel script (voiceover)</label>
        <textarea id="t_reel" rows="4" class="w-full border-slate-300 rounded text-sm mt-1">${escapeHtml(t.reel_script)}</textarea>
      </div>` : ""}
    </div>`;
}

function syncTextEditsToState() {
  if (!W.text) return;
  const get = (id) => document.getElementById(id)?.value ?? "";
  W.text.title = get("t_title");
  W.text.hook = get("t_hook");
  W.text.caption = get("t_caption");
  W.text.hashtags = get("t_hashtags");
  if (document.getElementById("t_cta")) W.text.cta = get("t_cta");
  if (document.getElementById("t_reel")) W.text.reel_script = get("t_reel");
  document.querySelectorAll(".t_slide").forEach(el => {
    const i = parseInt(el.dataset.sl, 10);
    const fld = el.dataset.fld;
    if (!W.text.slides[i]) return;
    W.text.slides[i][fld] = el.value;
  });
}

// =========================================================================
//  STEP 4 — CANVAS EDITOR (Fabric.js)
// =========================================================================

const CANVAS_DIMS = {
  carousel: { w: 1080, h: 1350 },
  post:     { w: 1080, h: 1080 },
  story:    { w: 1080, h: 1920 },
  reel:     { w: 1080, h: 1920 },
};

function slidesForEditor() {
  // Per carousel/reel usiamo i slides. Per post/story usiamo una singola slide finta col title/hook
  if (W.kind === "carousel" || W.kind === "reel") {
    return W.text.slides && W.text.slides.length ? W.text.slides : [{
      index: 1, title: W.text.title, body: W.text.hook || "",
    }];
  }
  return [{ index: 1, title: W.text.title, body: W.text.hook || "" }];
}

function ensureCanvasEditor() {
  syncTextEditsToState();
  const canvasEl = document.getElementById("fabricCanvas");
  if (W.fabric) {
    try { W.fabric.dispose(); } catch (_) {}
    W.fabric = null;
  }
  const dim = CANVAS_DIMS[W.kind] || CANVAS_DIMS.carousel;

  // Canvas a PIENA risoluzione (1080x1350 o equivalente).
  // Display via CSS-only (Fabric gestisce la traduzione coordinate mouse).
  W.fabric = new fabric.Canvas(canvasEl, {
    width: dim.w, height: dim.h,
    backgroundColor: "#0f172a",
    preserveObjectStacking: true,
  });
  // CSS scaling: visualizza fino a max 720px di altezza
  const cssH = Math.min(720, dim.h);
  const cssW = Math.round(dim.w * (cssH / dim.h));
  W.fabric.setDimensions({ width: cssW, height: cssH }, { cssOnly: true });

  W.canvasState = {};
  const slides = slidesForEditor();
  W.canvases = slides.map(_ => null);
  W.currentSlide = 1;
  buildThumbStrip(slides);
  loadSlideIntoCanvas(1);
}

function buildThumbStrip(slides) {
  const strip = document.getElementById("slideStrip");
  if (!slides || slides.length <= 1) { strip.innerHTML = ""; return; }
  strip.innerHTML = slides.map((s, i) => `
    <div class="thumb ${i === 0 ? "active" : ""}" data-slide="${i + 1}"
         onclick="switchSlide(${i + 1})" title="${escapeHtml(s.title || "")}">
      <div style="color:#fff; font-size:10px; padding:4px;">${i + 1}</div>
    </div>`).join("");
}

async function switchSlide(n) {
  saveCurrentCanvasState();
  W.currentSlide = n;
  document.querySelectorAll(".thumb").forEach(t => {
    t.classList.toggle("active", parseInt(t.dataset.slide, 10) === n);
  });
  await loadSlideIntoCanvas(n);
}

function saveCurrentCanvasState() {
  if (!W.fabric) return;
  W.canvasState[W.currentSlide] = W.fabric.toJSON(["selectable", "editable"]);
}

/**
 * Carica una slide nel canvas. ASINCRONA: ritorna una Promise che si risolve
 * SOLO quando il background (se presente) e' completamente caricato e disegnato.
 * Usare sempre `await loadSlideIntoCanvas(...)` per evitare export vuoti.
 */
function loadSlideIntoCanvas(slideIdx) {
  return new Promise((resolve) => {
    const slides = slidesForEditor();
    const slide = slides[slideIdx - 1];
    const dim = CANVAS_DIMS[W.kind] || CANVAS_DIMS.carousel;
    const f = W.fabric;
    f.clear();
    // Niente piu' setDimensions/setZoom: il canvas è già a piena risoluzione
    f.backgroundColor = "#0f172a";

    // Determina lo sfondo per QUESTA slide.
    // Priorita': override esplicito per-slide > selectedVariant per slide 1 > nessuna
    // NB: override può essere `null` = "esplicitamente nessuno sfondo"
    let bgUrl;
    if (W.slideBgOverride && Object.prototype.hasOwnProperty.call(W.slideBgOverride, slideIdx)) {
      bgUrl = W.slideBgOverride[slideIdx];
    } else if (slideIdx === 1 && W.selectedVariant) {
      bgUrl = W.selectedVariant.url;
    } else {
      bgUrl = null;
    }

    const finish = () => {
      addDefaultTexts(slide, slideIdx);
      // Ripristina canvas state salvato (se esiste e non e' la prima volta)
      if (W.canvasState[slideIdx]) {
        f.loadFromJSON(W.canvasState[slideIdx], () => {
          f.renderAll();
          resolve();
        });
      } else {
        f.renderAll();
        resolve();
      }
    };

    if (bgUrl) {
      // NB: niente crossOrigin — l'immagine viene servita dal nostro stesso server,
      // ma se mettiamo crossOrigin='anonymous' e il server non aggiunge gli header
      // CORS appropriati, il canvas viene "tainted" e toDataURL ritorna grigio.
      fabric.Image.fromURL(bgUrl, (img) => {
        if (!img || !img.width) {
          // Fallimento caricamento → fallback senza sfondo
          finish();
          return;
        }
        const r = Math.max(dim.w / img.width, dim.h / img.height);
        img.scale(r);
        img.set({
          left: (dim.w - img.width * r) / 2,
          top:  (dim.h - img.height * r) / 2,
          selectable: false, evented: false,
          excludeFromExport: false,
        });
        f.add(img);
        f.sendToBack(img);
        // Overlay scuro per leggibilita' testo
        const overlay = new fabric.Rect({
          left: 0, top: 0, width: dim.w, height: dim.h,
          fill: "rgba(15,23,42,0.55)", selectable: false, evented: false,
        });
        f.add(overlay);
        f.sendToBack(overlay);
        f.sendToBack(img);
        finish();
      });
    } else {
      finish();
    }
  });
}

function addDefaultTexts(slide, slideIdx) {
  const f = W.fabric;
  const dim = CANVAS_DIMS[W.kind] || CANVAS_DIMS.carousel;
  const totalSlides = slidesForEditor().length;
  const isCover = slideIdx === 1;
  const isCTA = slideIdx === totalSlides && totalSlides > 1;

  // Header: handle + slide N/total
  if (totalSlides > 1) {
    const meta = new fabric.Text(`${String(slideIdx).padStart(2, "0")} / ${String(totalSlides).padStart(2, "0")}`, {
      left: dim.w - 100, top: 90, fontSize: 26, fill: "#94a3b8",
      fontFamily: "sans-serif", originX: "right",
    });
    f.add(meta);
  }
  const handle = new fabric.Text("@dr.valenti", {
    left: 90, top: 120, fontSize: 28, fill: "#94a3b8", fontFamily: "sans-serif",
  });
  f.add(handle);
  // accent line
  const accent = new fabric.Rect({
    left: 90, top: 80, width: 64, height: 5, fill: "#38bdf8", selectable: false,
  });
  f.add(accent);

  // Number indicator
  if (!isCover && !isCTA && totalSlides > 1) {
    const num = new fabric.Text(String(slideIdx).padStart(2, "0"), {
      left: 90, top: 220, fontSize: 120, fontWeight: "bold",
      fill: "#334155", fontFamily: "sans-serif",
    });
    f.add(num);
  }

  // Title
  const titleSize = isCover ? 104 : (W.kind === "story" || W.kind === "reel" ? 92 : 72);
  const titleTop = isCover ? Math.round(dim.h * 0.42) : (totalSlides > 1 && !isCTA ? 470 : Math.round(dim.h * 0.40));
  const title = new fabric.Textbox(slide.title || W.text.title || "Title", {
    left: 90, top: titleTop, width: dim.w - 180,
    fontSize: titleSize, fontWeight: "bold", fill: "#ffffff",
    fontFamily: "sans-serif", lineHeight: 1.05,
  });
  f.add(title);

  // Body
  const bodySize = isCover ? 44 : (isCTA ? 56 : 38);
  const bodyText = slide.body || (isCover ? (W.text.hook || "") : "");
  if (bodyText) {
    const body = new fabric.Textbox(bodyText, {
      left: 90, top: titleTop + titleSize * (slide.title ? Math.max(2, slide.title.length / 20) : 2) + 40,
      width: dim.w - 180, fontSize: bodySize,
      fill: isCTA ? "#7dd3fc" : "#e2e8f0", fontFamily: "sans-serif", lineHeight: 1.4,
    });
    f.add(body);
  }

  // Footer
  const footer = new fabric.Text(`Dr. Valenti  ·  Dentistry × Artificial Intelligence`, {
    left: dim.w / 2, top: dim.h - 90, fontSize: 24, fill: "#94a3b8",
    fontFamily: "sans-serif", originX: "center",
  });
  f.add(footer);

  f.renderAll();
}

// --- Toolbar actions ---
function canvasAddText() {
  const t = new fabric.Textbox("Nuovo testo", {
    left: 200, top: 200, width: 600, fontSize: 48, fill: "#ffffff", fontFamily: "sans-serif",
  });
  W.fabric.add(t).setActiveObject(t);
  W.fabric.renderAll();
}
function canvasAddBox() {
  const r = new fabric.Rect({
    left: 150, top: 150, width: 500, height: 200, fill: "#7c3aed", rx: 12, ry: 12,
  });
  W.fabric.add(r).setActiveObject(r);
  W.fabric.renderAll();
}
function canvasAddBoxWithText() {
  const r = new fabric.Rect({ left: 0, top: 0, width: 500, height: 200, fill: "#7c3aed", rx: 12, ry: 12 });
  const t = new fabric.Textbox("Highlight", {
    left: 0, top: 0, width: 480, fontSize: 44, fill: "#ffffff", fontWeight: "bold",
    fontFamily: "sans-serif", textAlign: "center", originX: "left",
  });
  const g = new fabric.Group([r, t], { left: 150, top: 150 });
  W.fabric.add(g).setActiveObject(g);
  W.fabric.renderAll();
}
function canvasAddLine() {
  const r = new fabric.Rect({
    left: 90, top: 600, width: 200, height: 6, fill: "#38bdf8",
  });
  W.fabric.add(r).setActiveObject(r);
  W.fabric.renderAll();
}
function canvasDeleteSelected() {
  const obj = W.fabric.getActiveObject();
  if (obj) { W.fabric.remove(obj); W.fabric.discardActiveObject().renderAll(); }
}
function canvasBringForward() {
  const obj = W.fabric.getActiveObject();
  if (obj) { W.fabric.bringForward(obj); W.fabric.renderAll(); }
}
function canvasSendBackward() {
  const obj = W.fabric.getActiveObject();
  if (obj) { W.fabric.sendBackwards(obj); W.fabric.renderAll(); }
}
function canvasReset() {
  if (!confirm("Ripristinare la slide allo stato iniziale?")) return;
  delete W.canvasState[W.currentSlide];
  loadSlideIntoCanvas(W.currentSlide);
}

/** Upload immagine come sfondo SOLO per la slide corrente (override per-slide). */
async function canvasUploadBgForSlide(event) {
  const file = event.target.files && event.target.files[0];
  if (!file) return;
  try {
    const fd = new FormData();
    fd.append("file", file);
    const r = await fetch("/api/wizard/upload-image", { method: "POST", body: fd });
    if (!r.ok) throw new Error(await r.text());
    const res = await r.json();
    if (!W.slideBgOverride) W.slideBgOverride = {};
    W.slideBgOverride[W.currentSlide] = res.url;
    // Cancella state corrente per ricaricare con nuovo bg
    delete W.canvasState[W.currentSlide];
    await loadSlideIntoCanvas(W.currentSlide);
  } catch (e) {
    alert("Upload fallito: " + e.message);
  }
}

/** Rimuovi qualsiasi sfondo immagine dalla slide corrente. */
async function canvasRemoveBg() {
  if (!W.slideBgOverride) W.slideBgOverride = {};
  W.slideBgOverride[W.currentSlide] = null;
  // Se siamo sulla slide 1 anche disabilita selectedVariant per questa slide
  if (W.currentSlide === 1) {
    W.slideBgOverride[1] = null;  // null esplicito = override "no bg" anche se selectedVariant esiste
  }
  delete W.canvasState[W.currentSlide];
  await loadSlideIntoCanvas(W.currentSlide);
}

// --- Properties panel quando si seleziona qualcosa ---
function bindCanvasSelection() {
  if (!W.fabric) return;
  W.fabric.on("selection:created", showPropsPanel);
  W.fabric.on("selection:updated", showPropsPanel);
  W.fabric.on("selection:cleared", () => {
    document.getElementById("propsPanel").innerHTML = "Seleziona un elemento per modificarne le proprietà.";
  });
}

function showPropsPanel() {
  const obj = W.fabric.getActiveObject();
  if (!obj) return;
  const isText = obj.type === "textbox" || obj.type === "text" || obj.type === "i-text";
  const panel = document.getElementById("propsPanel");
  panel.innerHTML = `
    <div class="text-xs text-slate-700 mb-2">${obj.type}</div>
    ${isText ? `
      <div class="props-row">
        <label>Font size</label>
        <input type="number" value="${Math.round(obj.fontSize)}" min="10" max="200" onchange="propsSet('fontSize', parseInt(this.value))" />
      </div>
      <div class="props-row">
        <label>Bold</label>
        <input type="checkbox" ${obj.fontWeight === 'bold' ? 'checked' : ''} onchange="propsSet('fontWeight', this.checked ? 'bold' : 'normal')" />
      </div>
      <div class="props-row">
        <label>Italic</label>
        <input type="checkbox" ${obj.fontStyle === 'italic' ? 'checked' : ''} onchange="propsSet('fontStyle', this.checked ? 'italic' : 'normal')" />
      </div>
      <div class="props-row">
        <label>Allineamento</label>
        <select onchange="propsSet('textAlign', this.value)">
          ${['left','center','right'].map(a => `<option value="${a}" ${obj.textAlign === a ? 'selected' : ''}>${a}</option>`).join("")}
        </select>
      </div>
    ` : ""}
    <div class="props-row">
      <label>Colore${isText ? ' testo' : ' fill'}</label>
      <input type="color" value="${rgbToHex(obj.fill)}" onchange="propsSet('fill', this.value)" />
    </div>
    ${obj.type === "rect" ? `
      <div class="props-row">
        <label>Arrotondamento</label>
        <input type="number" value="${Math.round(obj.rx || 0)}" min="0" max="60" onchange="propsSetCorner(parseInt(this.value))" />
      </div>` : ""}
    <div class="props-row">
      <label>Opacità</label>
      <input type="number" step="0.1" min="0" max="1" value="${obj.opacity ?? 1}" onchange="propsSet('opacity', parseFloat(this.value))" />
    </div>
  `;
}

function propsSet(key, value) {
  const obj = W.fabric.getActiveObject();
  if (!obj) return;
  obj.set(key, value);
  W.fabric.renderAll();
}
function propsSetCorner(v) {
  const obj = W.fabric.getActiveObject();
  if (!obj) return;
  obj.set({ rx: v, ry: v });
  W.fabric.renderAll();
}
function rgbToHex(c) {
  if (!c) return "#ffffff";
  if (typeof c === "string" && c.startsWith("#")) return c;
  if (typeof c === "string" && c.startsWith("rgb")) {
    const nums = c.match(/\d+/g);
    if (!nums) return "#ffffff";
    return "#" + nums.slice(0, 3).map(n => parseInt(n, 10).toString(16).padStart(2, "0")).join("");
  }
  return "#ffffff";
}

// Aggancia gli handler dopo init canvas
const _origEnsure = ensureCanvasEditor;
ensureCanvasEditor = function() { _origEnsure(); bindCanvasSelection(); };

// =========================================================================
//  STEP 5 — FINALIZE
// =========================================================================

async function exportAllSlidesAsPNG() {
  saveCurrentCanvasState();
  const slides = slidesForEditor();
  const out = [];

  for (let i = 1; i <= slides.length; i++) {
    W.currentSlide = i;
    await loadSlideIntoCanvas(i);
    await new Promise(r => setTimeout(r, 100));  // safety: lascia che il paint completi
    // Niente multiplier: il canvas e' gia' a piena risoluzione 1080x1350 nel backstore,
    // toDataURL ritorna esattamente quelle dimensioni → 1:1 WYSIWYG export.
    const dataUrl = W.fabric.toDataURL({ format: "png" });
    out.push({ index: i, png_base64: dataUrl });
  }
  return out;
}

function renderFinalizeStep() {
  const area = document.getElementById("w_finalizeArea");
  area.innerHTML = `
    <button class="btn-primary" onclick="wizardFinalize()">Salva e prepara asset</button>
    <div id="w_finalizeStatus" class="mt-3 text-sm"></div>
    <div id="w_finalizeResult" class="mt-4"></div>
  `;
}

async function wizardFinalize() {
  syncTextEditsToState();
  const status = document.getElementById("w_finalizeStatus");
  const result = document.getElementById("w_finalizeResult");
  status.innerHTML = "Esportazione PNG dal canvas in corso…";
  result.innerHTML = "";
  let pngs;
  try {
    pngs = await exportAllSlidesAsPNG();
  } catch (e) {
    status.innerHTML = `<span class="text-rose-700">Export canvas fallito: ${e.message}</span>`;
    return;
  }

  status.textContent = "Salvataggio nel sistema…";
  try {
    const payload = {
      kind: W.kind,
      title: W.text.title,
      hook: W.text.hook,
      caption: W.text.caption,
      hashtags: W.text.hashtags || "",
      cta: W.text.cta,
      reel_script: W.text.reel_script,
      slides_meta: (W.text.slides || []).map((s, i) => ({
        index: s.index || i + 1,
        title: s.title, body: s.body, visual_hint: s.visual_hint,
      })),
      slides_png: pngs,
      provider: "wizard",
      paper_id: W.paperId,
      prompt: W.topicPrompt,
    };
    const c = await api("/wizard/finalize", { method: "POST", body: JSON.stringify(payload) });
    status.innerHTML = `<span class="text-emerald-700">Salvato come Content #${c.id}.</span>`;
    const ts = Date.now();
    const imageUrls = pngs.map((p, i) => `/renders/${c.id}/${imageNameFor(c.kind, i + 1, pngs.length)}`);
    result.innerHTML = `
      <div class="bg-slate-50 border border-slate-200 rounded-lg p-3">
        <div class="grid grid-cols-2 md:grid-cols-3 gap-2 mb-3">
          ${imageUrls.map(u => `<a href="${u}?t=${ts}" target="_blank"><img src="${u}?t=${ts}" class="w-full rounded border border-slate-200" /></a>`).join("")}
        </div>
        <div class="flex gap-2 flex-wrap">
          <a class="btn-primary" href="/api/render/${c.id}/zip" target="_blank">📦 Scarica ZIP (PNG + caption.txt)</a>
          ${c.kind === "reel" ? `<button class="btn-ghost" onclick="buildVideoFromFinalize(${c.id})">▶️ Genera video MP4</button>` : ""}
          <button class="btn-ghost" onclick="openInLibraryAfterFinalize(${c.id})">Apri in Libreria</button>
        </div>
        <div id="w_videoArea" class="mt-3"></div>
      </div>`;
  } catch (e) {
    status.innerHTML = `<span class="text-rose-700">Errore salvataggio: ${e.message}</span>`;
  }
}

function imageNameFor(kind, i, total) {
  if (kind === "reel") return `scene_${String(i).padStart(2, "0")}.png`;
  if (kind === "story" && total === 1) return "story.png";
  if (kind === "post" && total === 1) return "main.png";
  return `slide_${String(i).padStart(2, "0")}.png`;
}
async function buildVideoFromFinalize(id) {
  const area = document.getElementById("w_videoArea");
  area.innerHTML = "Build video MP4 in corso (10-30 sec)…";
  try {
    const v = await api(`/render/${id}/video`, { method: "POST" });
    const ts = Date.now();
    area.innerHTML = `
      <video controls class="w-full max-w-sm rounded border border-slate-200" src="${v.video}?t=${ts}"></video>
      <a class="block mt-2 text-xs underline" href="${v.video}?t=${ts}" download>Scarica MP4</a>`;
  } catch (e) {
    area.innerHTML = `<span class="text-rose-700 text-sm">${e.message}</span>`;
  }
}
function openInLibraryAfterFinalize(id) {
  document.querySelector('[data-tab="library"]').click();
  openReview(id);
}

// =========================================================================
//  LIBRARY TAB  (immutato dal vecchio)
// =========================================================================

document.getElementById("reviewStatusFilter").addEventListener("change", loadReview);

async function loadReview() {
  const list = document.getElementById("reviewList");
  const status = document.getElementById("reviewStatusFilter").value;
  list.innerHTML = "<div class='text-slate-500 text-sm'>Caricamento…</div>";
  const q = new URLSearchParams();
  if (status) q.set("status", status);
  q.set("limit", "60");
  try {
    const items = await api("/content?" + q.toString());
    list.innerHTML = items.length
      ? items.map(renderContentCard).join("")
      : "<div class='text-slate-500 text-sm'>Nessun contenuto.</div>";
  } catch (e) { list.innerHTML = `<div class='text-red-600 text-sm'>${e.message}</div>`; }
}

function renderContentCard(c) {
  const validation = c.validation_json || {};
  const ok = validation.ok === false ? "<span class='text-rose-600 text-xs'>⚠ errori</span>" : "";
  return `
    <div class="bg-white border border-slate-200 rounded-lg p-3 hover:border-violet-400 cursor-pointer" onclick="openReview(${c.id})">
      <div class="flex items-center justify-between">
        <div class="font-medium text-sm">${escapeHtml(c.title)}</div>
        ${statusPill(c.status)}
      </div>
      <div class="text-xs text-slate-500 mt-1">${c.kind} · ${c.provider} · ${new Date(c.created_at).toLocaleString()}</div>
      ${ok}
    </div>`;
}

async function openReview(id) {
  document.querySelector('[data-tab="library"]').click();
  const detail = document.getElementById("reviewDetail");
  detail.innerHTML = "<div class='text-slate-500 text-sm'>Caricamento…</div>";
  try {
    const c = await api(`/content/${id}`);
    detail.innerHTML = renderReviewDetail(c);
  } catch (e) { detail.innerHTML = `<div class='text-red-600 text-sm'>${e.message}</div>`; }
}

function renderReviewDetail(c) {
  const v = c.validation_json || { ok: true, issues: [] };
  return `
    <div class="space-y-4">
      <div class="flex items-center justify-between">
        <div>
          <div class="text-xs text-slate-500">#${c.id} · ${c.kind} · ${c.provider}/${c.model || "-"}</div>
          <h3 class="text-xl font-semibold">${escapeHtml(c.title)}</h3>
        </div>
        <div>${statusPill(c.status)}</div>
      </div>
      <div>
        <label class="text-xs font-medium text-slate-600">Caption</label>
        <textarea id="capEdit" rows="6" class="w-full border-slate-300 rounded text-sm mt-1">${escapeHtml(c.caption)}</textarea>
      </div>
      <div>
        <label class="text-xs font-medium text-slate-600">Hashtag</label>
        <input id="hashEdit" class="w-full border-slate-300 rounded text-sm mt-1" value="${escapeHtml(c.hashtags)}" />
      </div>
      <div class="flex flex-wrap gap-2 pt-2 border-t border-slate-200">
        <button class="btn-primary text-sm" onclick="saveEdits(${c.id})">Salva</button>
        <button class="text-sm px-3 py-1.5 bg-emerald-600 text-white rounded" onclick="approve(${c.id})" ${v.ok ? "" : "disabled"}>Approva</button>
        <button class="text-sm px-3 py-1.5 bg-rose-600 text-white rounded" onclick="reject(${c.id})">Rigetta</button>
        <button class="text-sm px-3 py-1.5 bg-blue-600 text-white rounded" onclick="schedulePrompt(${c.id})">Programma</button>
        <a class="btn-ghost text-sm" href="/api/render/${c.id}/zip" target="_blank">📦 Scarica ZIP per IG</a>
      </div>
      <div class="text-xs text-slate-500 mt-2">
        💡 Lo ZIP contiene i PNG + <code>caption.txt</code> con caption e hashtag pronti.
        Caricale manualmente su Instagram (app, Meta Business Suite, o transferiscile via AirDrop sul telefono).
      </div>
      <div id="publishResult_${c.id}" class="text-sm"></div>
    </div>`;
}

async function saveEdits(id) {
  const c = await api(`/content/${id}`);
  const payload = {
    kind: c.kind, title: c.title, hook: c.hook,
    caption: document.getElementById("capEdit").value,
    hashtags: document.getElementById("hashEdit").value,
    cta: c.cta, slides: c.slides_json || [], reel_script: c.reel_script,
    paper_id: c.paper_id, provider: c.provider,
  };
  await api(`/content/${id}`, { method: "PUT", body: JSON.stringify(payload) });
  openReview(id);
}
async function approve(id) {
  try { await api(`/content/${id}/approve`, { method: "POST", body: JSON.stringify({ action: "approve" }) }); }
  catch (e) { alert(e.message); } openReview(id);
}
async function reject(id) {
  await api(`/content/${id}/approve`, { method: "POST", body: JSON.stringify({ action: "reject" }) });
  openReview(id);
}
async function publishToIG(id) {
  const target = document.getElementById(`publishResult_${id}`);
  if (target) target.innerHTML = "<span class='text-slate-500'>Pubblicazione in corso (può richiedere 10-30s)…</span>";
  try {
    const res = await api(`/publish/${id}`, { method: "POST" });
    if (target) target.innerHTML = `<span class='text-emerald-700'>✓ Pubblicato! media_id=${res.media_id} · ${res.image_count} immagini</span>`;
    openReview(id);
  } catch (e) {
    if (target) target.innerHTML = `<span class='text-rose-700'>${e.message}</span>`;
  }
}

async function schedulePrompt(id) {
  const when = prompt("Data ISO (es. 2026-06-01T09:30:00):");
  if (!when) return;
  try {
    await api(`/schedule/${id}`, { method: "POST", body: JSON.stringify({ slot_at: when, channel: "instagram" }) });
    openReview(id); loadCalendar();
  } catch (e) { alert(e.message); }
}

// =========================================================================
//  PAPERS / CALENDAR / ANALYTICS (immutati)
// =========================================================================

async function loadPapers() {
  const list = document.getElementById("papersList");
  list.innerHTML = "<div class='text-slate-500 text-sm'>Caricamento…</div>";
  const status = document.getElementById("paperStatus").value;
  const minScore = parseFloat(document.getElementById("paperMinScore").value || "0");
  const q = new URLSearchParams();
  if (status) q.set("status", status);
  if (minScore > 0) q.set("min_score", String(minScore));
  q.set("limit", "60");
  try {
    const items = await api("/papers?" + q.toString());
    list.innerHTML = items.length
      ? items.map(p => `
        <div class="bg-white border border-slate-200 rounded-lg p-3">
          <div class="flex items-center justify-between gap-3">
            <div>
              <div class="font-medium">${escapeHtml(p.title)}</div>
              <div class="text-xs text-slate-500">${p.source} · ${escapeHtml(p.journal || "—")} · score ${p.relevance_score}</div>
            </div>
            <div class="flex gap-2"><span class="text-xs px-2 py-0.5 rounded bg-slate-100">${p.status}</span></div>
          </div>
        </div>`).join("")
      : "<div class='text-slate-500 text-sm'>Nessun paper.</div>";
  } catch (e) { list.innerHTML = `<div class='text-red-600 text-sm'>${e.message}</div>`; }
}
async function ingest(kind) {
  try {
    const r = await api(`/papers/ingest/${kind}`, { method: "POST" });
    alert(`Ingest ${kind}: fetched=${r.fetched}, inserted=${r.inserted}`);
    loadPapers();
  } catch (e) { alert(e.message); }
}

async function loadCalendar() {
  const list = document.getElementById("calendarList");
  try {
    const items = await api("/schedule");
    list.innerHTML = items.length
      ? items.map(s => `
        <div class="bg-white border border-slate-200 rounded-lg p-3">
          <div class="font-medium">${escapeHtml(s.content_title || `#${s.content_id}`)}</div>
          <div class="text-xs text-slate-500">${new Date(s.slot_at).toLocaleString()} · ${s.channel}</div>
        </div>`).join("")
      : "<div class='text-slate-500 text-sm'>Nessun contenuto programmato.</div>";
  } catch (e) { list.innerHTML = `<div class='text-red-600 text-sm'>${e.message}</div>`; }
}

async function loadAnalytics() {
  const list = document.getElementById("analyticsTop");
  try {
    const top = await api("/analytics/top/engagement");
    list.innerHTML = top.length
      ? top.map(t => `<div class="bg-white border border-slate-200 rounded p-3 flex justify-between">
          <div>${escapeHtml(t.title)} <span class="text-xs text-slate-500">· ${t.kind}</span></div>
          <div class="text-sm">♥ ${t.likes} · 💬 ${t.comments} · 🔖 ${t.saves}</div>
        </div>`).join("")
      : "<div class='text-slate-500 text-sm'>Nessun dato.</div>";
  } catch (e) { list.innerHTML = `<div class='text-red-600 text-sm'>${e.message}</div>`; }
}

// =========================================================================
//  PUBLISH TAB (Instagram OAuth status)
// =========================================================================

async function loadPublishStatus() {
  const area = document.getElementById("publishStatusArea");
  area.innerHTML = "<div class='text-slate-500 text-sm'>Caricamento status…</div>";
  try {
    const s = await api("/publish/status");
    const checks = [
      ["Meta App configurata", s.meta_app_configured],
      ["Token IG presente", s.token_present],
      ["IG Business Account ID", s.ig_business_account_id_set],
      ["PUBLIC_BASE_URL impostata", s.public_base_url_set],
    ];
    area.innerHTML = `
      <ul class="space-y-1">
        ${checks.map(([label, ok]) => `
          <li class="flex items-center gap-2 text-sm">
            <span style="color: ${ok ? '#059669' : '#dc2626'}">${ok ? '✓' : '✗'}</span>
            <span>${label}</span>
          </li>`).join("")}
      </ul>
      <div class="mt-3">
        ${s.meta_app_configured
          ? `<a class="btn-primary inline-block" href="/api/publish/oauth/start">🔐 Autorizza con Meta</a>`
          : `<span class="text-sm text-rose-700">Inserisci META_APP_ID e META_APP_SECRET nel .env, poi restart api.</span>`}
        ${s.ready_to_publish
          ? `<span class="ml-3 text-sm text-emerald-700">✓ Sei pronto a pubblicare! Vai in Libreria → contenuto → 'Pubblica su IG'.</span>`
          : ""}
      </div>`;
  } catch (e) {
    area.innerHTML = `<div class='text-rose-700 text-sm'>${e.message}</div>`;
  }
}

// Inizializza step 1 attivo
showStep(1);
