# SEO Audit Engine — POC Specification

## Overview

This project implements a scalable, traceable SEO audit engine designed to:

- Analyze client websites
- Capture SERP data
- Extract keywords
- Measure ranking visibility
- Identify competitors
- Generate structured recommendations
- Track improvement over time

The system is built around audit runs, step execution tracking, and database-driven observability.

---

## Core Principles

1. Database is the source of truth.
2. Every audit is fully traceable.
3. Each step execution is recorded.
4. Failure is first-class (retryable).
5. Observability is mandatory.
6. Horizontal scalability via Celery queues.
7. JWT-secured API.

---

## High-Level Architecture

Client → API → AuditRun → RunSteps → Celery Tasks → DB Updates → Report

---

## Primary Entities

- ClientSite
- AuditRun
- RunStep
- RunStepAttempt
- PageSnapshot
- KeywordSetVersion
- SerpSnapshot
- KeywordResult
- Recommendation

---

## Audit Lifecycle

1. Create ClientSite
2. Create AuditRun
3. Auto-generate RunSteps
4. Trigger async execution
5. Persist results
6. Compute summary
7. Generate recommendations
8. Mark run SUCCESS or FAILED

---

## Queues

- seo_light → lightweight steps
- seo_serp → SERP capture
- seo_heavy → competitor & analysis

---

## Authentication

- JWT-based
- Access + Refresh tokens
- Token rotation enabled
- Blacklisting enabled

---

## Observability

- Flower for Celery monitoring
- RunStep status tracking
- RunStepAttempt error recording
- Summary stored per run
- Error summaries stored per run

---

## Scalability Model

- Stateless web containers
- Redis broker
- PostgreSQL storage
- Multiple worker pools
- Queue-based routing
- Prefetch = 1 for reliability
- Late ACKs enabled