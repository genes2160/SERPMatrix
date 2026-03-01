# Audit Run Step Definitions

Each AuditRun consists of ordered execution steps.

---

## Step 1 — FETCH_CLIENT

Purpose:
- Fetch client homepage
- Record PageSnapshot
- Compute hash
- Extract base metadata

Queue: seo_light

---

## Step 2 — CLASSIFY

Purpose:
- Determine niche (dentist, law, ecommerce, etc.)
- Store niche_label on ClientSite
- Store classification meta

Queue: seo_light

---

## Step 3 — KEYWORDS

Purpose:
- Extract keywords from page content
- Create KeywordSetVersion
- Weight keywords

Queue: seo_light

---

## Step 4 — SERP

Purpose:
- Query SERP provider
- Capture top results
- Store SerpSnapshot

Queue: seo_serp

---

## Step 5 — COMPETITORS

Purpose:
- Identify top ranking competitor URLs
- Capture competitor PageSnapshots

Queue: seo_heavy

---

## Step 6 — ANALYZE

Purpose:
- Compute:
  - client_position
  - visibility_score
  - difficulty_score
- Generate KeywordResult records

Queue: seo_heavy

---

## Step 7 — FINALIZE

Purpose:
- Aggregate metrics
- Compute summary
- Generate Recommendations
- Update AuditRun.status

Queue: seo_light

---

## Retry Logic

If step fails:
- Increment attempts
- Create RunStepAttempt record
- Store last_error
- Allow manual retry via API