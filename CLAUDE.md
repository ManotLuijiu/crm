# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Frappe CRM — an open-source CRM built on the Frappe Framework. Vue 3 SPA frontend served at `/crm`, Python/Frappe backend. Licensed AGPLv3.

**Branches**: `develop` (unstable, targets Frappe v16), `main` (stable, v15.x).

## Common Commands

### Frontend Development
```bash
cd /Users/manotlj/frappe-bench/apps/crm
yarn install          # Installs root + frontend deps (via postinstall hook)
yarn dev              # Vite dev server on port 8080
yarn build            # Production build → copies index.html to crm/www/crm.html
```

### Backend / Full Stack
```bash
bench start                                    # Start Frappe dev server (from bench root)
bench --site <site> migrate                    # Run migrations after schema changes
bench build --app crm                          # Build frontend assets via bench
```

### Testing
```bash
bench --site <site> run-tests --app crm                           # All tests
bench --site <site> run-tests --module crm.fcrm.doctype.crm_deal  # Single module
bench --site <site> run-tests --doctype "CRM Deal"                # Single doctype
```

### Linting
```bash
ruff check crm/          # Python lint (configured in pyproject.toml)
ruff format crm/         # Python format (double quotes, tab indent)
npx prettier --check frontend/src/   # Frontend format check
```

## Architecture

### Backend (`crm/`)

- **`api/`** — Whitelisted API endpoints called by the frontend (`doc.py`, `dashboard.py`, `activities.py`, `views.py`, `notifications.py`, `session.py`, etc.)
- **`fcrm/doctype/`** — ~40 DocTypes. Core entities: `CRM Lead`, `CRM Deal`, `CRM Organization`, `CRM Call Log`, `CRM Task`, `FCRM Note`. Settings: `FCRM Settings`, `CRM Global Settings`, `ERPNext CRM Settings`.
- **`integrations/`** — Twilio voice, Exotel, WhatsApp message handling
- **`lead_syncing/`** — Background sync from Facebook Lead Ads and other sources (scheduled at various cron intervals)
- **`overrides/`** — Extends Frappe's `Contact` and `Email Template` DocType classes
- **`patches/`** — Data migration scripts run during `bench migrate`
- **`hooks.py`** — Document event hooks, scheduled tasks, doctype class overrides, website routing (`/crm/<path>` → SPA)

### Frontend (`frontend/src/`)

- **Vue 3** + **Vue Router 4** + **Pinia** state management
- **Frappe UI** component library with **TailwindCSS** styling
- **`pages/`** — Route-level components: Leads, Deals, Contacts, Organizations, CallLogs, Notes, Tasks, Calendar, Dashboard. Mobile variants (`MobileLead.vue`, `MobileDeal.vue`, etc.) auto-selected at `< 768px`.
- **`components/`** — Shared UI components (layouts, modals, activities, fields, views)
- **`stores/`** — Pinia stores: `session`, `users`, `views`, `settings`, `notifications`, `statuses`, `meta`, `global`, `organizations`
- **`composables/`** — Vue 3 composition utilities
- **`router.js`** — All routes under `/crm` base path. Home redirects to default view or Leads.
- **Socket.io** for real-time updates
- **PWA** support via `vite-plugin-pwa`

### Key Data Flow

1. Frontend calls `frappe.call` / `createResource` to whitelisted Python methods in `crm/api/`
2. API methods interact with DocTypes via `frappe.get_doc`, `frappe.get_list`, etc.
3. Document event hooks in `hooks.py` trigger side effects (notifications, ERPNext sync, WhatsApp handling)
4. Socket.io pushes real-time updates back to the frontend

### SPA Entry Point

`crm/www/crm.py` provides the Jinja context (CSRF token, boot data). The built `crm.html` is served at `/crm`. All sub-routes are handled client-side via `website_route_rules` in `hooks.py`.

## Code Style

- **Python**: Ruff — line length 110, tabs, double quotes, target py310. Config in `pyproject.toml`.
- **JavaScript/Vue**: Prettier — no semicolons, single quotes. Config in `frontend/.prettierrc.json`.
- **CSS**: TailwindCSS with Frappe UI preset. Custom styles scoped via component.

## Key Conventions

- DocType names are prefixed with `CRM` (e.g., `CRM Deal`, `CRM Lead`) or `FCRM` (e.g., `FCRM Note`, `FCRM Settings`)
- API endpoints are `@frappe.whitelist()` decorated functions in `crm/api/`
- Frontend uses `frappe-ui` components (`Button`, `Dialog`, `Input`, `Badge`, `Dropdown`, etc.)
- Build output path: `/assets/crm/frontend/` (set as Vite base)
- The `postinstall` script in root `package.json` auto-runs `yarn install` in `frontend/`
