# Radar Janja MVP Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Build a Vercel-ready static dashboard that monitors official public-spending/travel records associated with Janja / Rosângela da Silva / Primeira-Dama.

**Architecture:** A Python scanner downloads official annual travel ZIP files from Portal da Transparência, extracts matching CSV rows, classifies them conservatively, and writes JSON/CSV. A static HTML/CSS/JS dashboard reads the JSON and presents totals, filters, source methodology, and X-ready draft snippets.

**Tech Stack:** Static HTML/CSS/JS, Python stdlib, Portal da Transparência downloads, Vercel static hosting.

---

### Task 1: Create static project skeleton

**Objective:** Create package metadata, Vercel config, README, and directories.

**Files:**
- Create: `package.json`
- Create: `vercel.json`
- Create: `README.md`
- Create: `data/raw/`, `data/processed/`, `scripts/`

**Verification:** Run `npm run check` after checker exists.

### Task 2: Build official-data scanner

**Objective:** Download yearly Portal da Transparência travel ZIPs and extract records matching safe search terms.

**Files:**
- Create: `scripts/scan_radar_janja.py`
- Output: `data/processed/radar-janja.json`
- Output: `data/processed/radar-janja.csv`

**Verification:** Run `npm run scan` and confirm JSON has summary + records.

### Task 3: Build dashboard UI

**Objective:** Create a premium responsive dashboard with totals, filters, methodology, records, and publication-safe language.

**Files:**
- Create: `index.html`
- Create: `styles.css`
- Create: `app.js`

**Verification:** Run local server and inspect browser console + mobile viewport.

### Task 4: Add static validation

**Objective:** Validate required files and schema before deploy.

**Files:**
- Create: `scripts/check_project.py`

**Verification:** `npm run check` passes.

### Task 5: Deployment prep

**Objective:** Confirm Vercel-ready static build and no accidental publishing to X.

**Verification:** `npm run scan`, `npm run check`, local browser smoke test.
