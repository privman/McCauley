# Cloud + Managed-RDBMS Choice

Justification for committing the feedback-agent system to **Google Cloud** with **Cloud SQL for Postgres** (upgrading to AlloyDB later). Referenced from `design.md` §3.

Two coupled decisions are evaluated here:
1. Which hyperscaler to host on.
2. Which managed Postgres flavor to use.

Since speech (STT + TTS) is already on GCP for cost reasons (see `design.md` §12, decision 5), the hyperscaler choice is not symmetric — putting the app on AWS would pay cross-cloud egress on every voice byte.

---

## Equivalent-sizing monthly cost (3 regions, sized as in `design.md` §3.1)

| Component | AWS | GCP |
|---|---|---|
| Kubernetes (control plane + ~30 nodes total) | EKS $0.10/hr/cluster × 3 + EC2 `m6i.xlarge` × 30 ≈ $13,500 | GKE Autopilot or Standard + `n2-standard-4` × 30 ≈ $12,000 |
| Managed Postgres — vanilla | RDS Postgres `db.r6g.4xlarge` Multi-AZ × 3 ≈ $6,000 | Cloud SQL Postgres HA `db-custom-16-65536` × 3 ≈ $6,000 |
| Managed Postgres — premium | **Aurora Postgres** (same sizing) × 3 ≈ $7,500 | **AlloyDB** (same sizing) × 3 ≈ $7,200 |
| Vector workload | pgvector HNSW inside RDS/Aurora | pgvector inside Cloud SQL, OR **AlloyDB's native ScaNN index** (significantly better recall/latency than HNSW at scale) |
| Cache (Redis) | ElastiCache × 3 ≈ $3,000 | Memorystore × 3 ≈ $3,000 |
| Object storage (180 TB steady-state) | S3 Standard ≈ $4,100 | GCS Standard ≈ $4,000 |
| Observability | Grafana Cloud / self-host (cloud-agnostic) | same |
| **Cross-cloud egress to Google STT/TTS** | 150k voice calls × ~22 MB = ~3.3 TB/mo × $0.09/GB AWS egress ≈ **$300/mo**; symmetric GCP egress to AWS for TTS audio ≈ **$400/mo** | **$0** (same-cloud) |
| **Subtotal (vanilla managed Postgres)** | **~$27,300** | **~$25,000** |
| **Subtotal (premium: Aurora vs AlloyDB)** | **~$28,800** | **~$26,200** |

GCP is ~$2-3k/month cheaper at equivalent sizing, mostly from avoided egress and slightly cheaper compute. At 1M-user scale that's $25-35k/year — not the headline number, but real.

---

## Managed RDBMS — which flavor

The hybrid OLTP + vector + row-level-security workload narrows the field:

| Option | Verdict |
|---|---|
| **Self-managed Postgres on K8s** | Don't. Pager load not justified at this scale. |
| **RDS Postgres** | Fine. Vanilla, supports pgvector, mature. ~$6k/mo. |
| **Aurora Postgres** | ~25% pricier than RDS, better failover and read scaling. Worth it if read traffic dominates; report generation may push that direction post-v1. |
| **AlloyDB** | Postgres-compatible, native ScaNN vector index outperforms pgvector HNSW at >10M chunks, columnar engine helps analytical queries (cohort sentiment, trend dashboards). ~$7.2k/mo. **Best fit for this workload** if we commit to GCP. |
| **Cloud Spanner** | Strong consistency at global scale, but no full Postgres compatibility and no first-class vector index. Overkill and locks us in. |
| **Cloud SQL Postgres** | Good baseline on GCP. Use this in v1; migrate to AlloyDB when vector volume justifies it (cutover is in-place — same wire protocol). |

---

## Other factors beyond cost

| Factor | AWS | GCP |
|---|---|---|
| Enterprise customer mindshare / procurement | Stronger — many HR-tech buyers default to AWS | Catching up but still second |
| Region count for data residency | More regions, esp. APAC and gov clouds | Fewer regions but covers EU/US/major APAC |
| Compliance certifications | Broadest catalog | Strong, parity for SOC 2 / ISO / HIPAA / GDPR |
| Vector tooling | Mature pgvector, Bedrock Knowledge Bases | AlloyDB ScaNN, Vertex AI Vector Search |
| Lock-in risk on premium DB | Aurora — Postgres-compat but proprietary storage | AlloyDB — Postgres-compat but proprietary storage; symmetric risk |
| Speech co-location | Cross-cloud — adds latency (~20-40ms RTT) and egress cost | Same-cloud, lower latency |

---

## Recommendation

Host on **GCP**. Specifically:
- **GKE** for compute (parity with EKS, marginally cheaper).
- **Cloud SQL Postgres** in v1 — same wire protocol as Postgres, supports pgvector, simplest migration path.
- **Move to AlloyDB** when either (a) vector index size exceeds ~10M chunks and pgvector HNSW recall/latency degrades, or (b) report-generation queries (columnar workload) become hot.
- **GCS** for audio/transcripts.
- **Direct browser-to-Google STT/TTS** with ephemeral tokens minted by our backend, so audio bytes never traverse our app servers — cuts egress and CPU even within GCP.

Primary reasons:
1. Avoids cross-cloud egress on every voice byte (~$700/mo at our scale, growing with adoption).
2. AlloyDB gives us a clean upgrade path for vector workloads without leaving Postgres compatibility.
3. ~$2-3k/mo cheaper at equivalent sizing.

## Revisit if

- Target enterprise buyers strongly prefer AWS (common in finance, healthcare) — procurement friction may outweigh the ~$30k/year saving. In that case, stay on AWS with RDS Postgres, and accept the egress as a cost of vendor diversity.
- Anthropic releases a first-party deployment on AWS Bedrock with substantially better pricing or features than the direct API, making cross-cloud less attractive.
- Google deprecates or significantly raises prices on STT/TTS, removing the speech co-location advantage.
