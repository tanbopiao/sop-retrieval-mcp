# Scope & Limits — Read This First

This document defines exactly what the test package does, what it does not
do, and what is out of scope. Nothing outside this scope is promised,
implied or guaranteed.

## What this package DOES

1. **Local SOP retrieval.** You load your own procedure documents
   (`.pdf`, `.docx`, `.txt`, `.md`, `.csv`, `.json`, `.log`) and ask
   operational questions. It returns the most relevant passages with
   source attribution: document name, version, and section.
2. **Version awareness.** It detects version markers in documents
   (e.g. "Version: 2.3"), prefers the highest version of the same
   procedure, and flags conflicts when multiple versions of one
   procedure are loaded.
3. **Local-only operation.** Everything runs on your machine. Your
   documents are never uploaded, transmitted or shared. No network
   connection is required after installation.
4. **Free 30-day evaluation.** Unlimited documents, full features,
   from first run.

## What this package does NOT do

- **No ERP / system integration.** Connecting to Saksham AI or any
  external system is part of the paid, managed production version —
  not this package.
- **No user management or permissions.** There is no login, no roles,
  no audit trail. Anyone with access to the machine can query it.
- **No hosting, sync or multi-site sharing.** The index is local to
  one machine. Sharing across sites or teams requires the managed
  version.
- **No automatic updates.** When your SOPs change, you re-ingest the
  updated files yourself. There is no background watching service.
- **No scanned-image reading.** PDFs must contain a text layer.
  Photographs or scans without embedded text cannot be extracted.
- **No compliance certification.** Retrieval results are decision
  support only. Operators must verify answers against the source
  document before acting. This package is not an approved operating
  procedure and carries no regulatory or food-safety certification.
- **No service-level guarantee during the trial.** Support is
  best-effort by email.

## Accuracy expectations

Retrieval quality depends on your documents: clear titles, section
headings and version markers give the best results. The system finds
and cites passages — it does not rewrite, summarise or guarantee that
a passage is the *complete* answer. Always check the cited source.

The evaluation period exists precisely so you can judge accuracy on
your own data before any commitment.

## Beyond the boundary

Anything not listed under "What this package DOES" — integrations,
hosting, permissions, custom models, additional file formats, SLAs —
is available only under a separate paid agreement, subject to prior
written confirmation. Verbal statements, demos or marketing materials
do not extend this scope.
