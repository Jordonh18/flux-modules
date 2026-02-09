# Copilot Instructions — Flux Modules (Module Registry)

## Project Overview

This is the **official module registry** for the Flux platform. It contains self-contained plugin modules that extend Flux with new functionality. Modules are distributed to Flux instances via a registry system — Flux fetches `registry.json` over HTTP and installs modules on demand.

This repo does NOT run independently. Modules are loaded and executed by the Flux core platform (`flux` repo) at runtime.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.10+, async functions, raw SQL via `sqlalchemy.text()` |
| Frontend | React 19, TypeScript, shadcn/ui, TanStack React Query, Tailwind CSS v4 |
| Container Runtime | Podman (rootless) for modules that manage containers |
| Module SDK | Imported from `module_sdk` (defined in the `flux` core repo) |

## Architecture

### Registry System

- **`registry.json`** — Top-level manifest listing all available modules with name, version, path, description, and tags
- **Module directories** — Each module lives in `modules/{module_name}/` with a complete, self-contained structure
- **Flux connection** — Flux instances add this repo as a registry source (via GitHub `owner/repo` format), fetch `registry.json`, and install modules into their local `modules/` directory

### Module Structure (Required Convention)

Every module MUST follow this structure:

```
modules/{module_name}/
├── module.json              # Module manifest (REQUIRED)
├── __init__.py              # Module entry point (REQUIRED)
├── routes.py                # API routes using ModuleRouter (REQUIRED if module has API)
├── hooks.py                 # Lifecycle hooks (optional)
├── frontend/                # Frontend components (optional)
│   ├── components/          # Reusable React components
│   ├── pages/               # Page-level React components
│   └── types/               # TypeScript type definitions
├── migrations/              # Database migrations (optional)
│   ├── 001_initial.sql      # Forward migration
│   └── 001_initial.down.sql # Rollback migration
├── services/                # Business logic services (optional)
│   └── config_templates/    # Configuration templates (optional)
└── data/                    # Runtime data directory (optional)
```

### Module Manifest (`module.json`)

Every module MUST have a `module.json` with:

```json
{
  "name": "module_name",
  "display_name": "Human Readable Name",
  "version": "1.0.0",
  "description": "What this module does",
  "author": "Author Name",
  "license": "MIT",
  "min_app_version": "1.0.0",
  "hooks": {
    "after_module_enable": "hooks:on_enable",
    "after_module_disable": "hooks:on_disable"
  },
  "permissions": [
    {
      "name": "resource:action",
      "display_name": "Human Readable",
      "description": "What this permission allows",
      "resource": "resource",
      "action": "read|write"
    }
  ],
  "navigation": [
    {
      "menu": "main|admin|settings",
      "title": "Nav Label",
      "path": "/route-path",
      "icon": "LucideIconName",
      "required_permission": "resource:action"
    }
  ],
  "dependencies": [],
  "frontend": {
    "enabled": true,
    "entry": "frontend/pages/MainPage.tsx"
  }
}
```

### Connection to Flux Core Repository

This repo is consumed by the Flux core platform. The connection points are:

1. **Registry fetch:** Flux's `server/services/registry_service.py` fetches `registry.json` from this repo via GitHub API
2. **Module install:** Flux's `server/services/module_installer.py` downloads module directories and places them in its local `modules/` folder
3. **Module SDK:** All backend code imports from `module_sdk` — the SDK is defined in the `flux` repo at `module_sdk/__init__.py` and is the source of truth
4. **Shared conventions:** Both repos must agree on manifest format, migration naming, permission format (`resource:action`), hook signatures, and frontend path conventions
5. **Version compatibility:** Each module specifies `min_app_version` in its manifest — this must match the Flux core version it requires

## Coding Conventions

### Python (Module Backend)

- Import EVERYTHING from `module_sdk` — never import directly from FastAPI, SQLAlchemy, or Pydantic
  ```python
  from module_sdk import (
      ModuleRouter, get_db, AsyncSession, text,
      require_permission, Depends, HTTPException,
      BaseModel, Optional, List,
      allocate_vnet_ip, release_vnet_ip,  # VNet hooks
  )
  ```
- Create routers with `ModuleRouter("module_name")` — NOT `APIRouter`
- Routes are auto-mounted at `/api/modules/{module_name}/` — define paths relative to that
- Use raw SQL via `text()` — the Flux project does NOT use ORM models
- All database queries: `await db.execute(text("..."), {...})`
- Use `require_permission("module_name:action")` for endpoint RBAC
- Hooks receive `(data: dict, context)` and return a dict
- Services should be self-contained in the module's `services/` directory
- Use `async def` for all route handlers and service functions
- Python 3.10+ type hints required
- Logging via `logging.getLogger("uvicorn.error")`

### TypeScript (Module Frontend)

- Use the Flux core `@/` path alias for imports (resolved at runtime by the host app)
- Use shadcn/ui components from `@/components/ui/`
- Data fetching via TanStack React Query (`useQuery`, `useMutation`)
- API calls via `api` from `@/lib/api` — module endpoints are at `/api/modules/{module_name}/`
- Permission checks via `usePermissions()` from `@/hooks/usePermissions`
- Use `lucide-react` for icons
- Tailwind CSS v4 for styling
- Framer Motion for animations
- Sonner for toast notifications (`@/lib/toast`)

### Database Migrations

- Place in `migrations/` directory within the module
- Sequential numbering: `001_initial.sql`, `002_add_column.sql`, etc.
- **ALWAYS provide rollback files:** `001_initial.down.sql` for every `001_initial.sql`
- Use SQLite-compatible syntax (Flux default) — avoid database-specific features
- IDs should be `INTEGER PRIMARY KEY AUTOINCREMENT`
- Table names should be prefixed with the module name (e.g., `databases_instances`)
- Foreign keys to core tables (e.g., `users`) are acceptable

### Hooks

- Define hook handlers in `hooks.py`
- Register hooks in `module.json` under the `hooks` key
- Standard lifecycle hooks: `after_module_enable`, `after_module_disable`
- Custom hooks follow the pattern: `on_{event_name}`
- Hook handlers are async: `async def on_enable(data: dict, context) -> dict:`

## Versioning Rules

### Module Versioning (SemVer)

Each module has its own independent version tracked in **three places** that MUST stay in sync:

1. **`module.json`** → `"version"` field
2. **`__init__.py`** → `__version__` variable
3. **`registry.json`** → module entry `"version"` field

### When to Bump the Version

After completing ANY code change to a module, evaluate the impact and bump the version in ALL THREE locations:

#### MAJOR (X.0.0) — Breaking changes
- Removing or renaming API endpoints
- Changing request/response schemas in breaking ways
- Database migrations that break existing data (column removal, type changes)
- Removing permissions or changing permission names
- Changing hook signatures
- Removing frontend pages or changing route paths
- Bumping `min_app_version` to a new major version of Flux

#### MINOR (0.X.0) — New features, non-breaking additions
- Adding new API endpoints
- Adding new database tables or columns (with defaults)
- Adding new permissions
- Adding new navigation entries
- Adding new frontend pages or major UI features
- Adding new hook handlers
- Adding new service capabilities
- Adding new SKU tiers, config templates, or supported database types
- Non-breaking schema additions

#### PATCH (0.0.X) — Fixes and improvements
- Bug fixes in routes, services, or frontend
- Security patches
- Performance improvements
- CSS/styling tweaks
- Typo fixes in UI text or error messages
- Dependency updates within the module
- Documentation updates
- Refactors with no behavior change
- Fixing broken queries or edge cases

### Version Bump Procedure

1. **Identify what changed** — routes, services, migrations, frontend, manifest, etc.
2. **Determine impact level** — breaking (major), new feature (minor), or fix (patch)
3. **Update version in `module.json`** → `"version": "X.Y.Z"`
4. **Update version in `__init__.py`** → `__version__ = "X.Y.Z"`
5. **Update version in `registry.json`** → matching module entry `"version": "X.Y.Z"`
6. **Reset lower components** — bumping minor resets patch to 0; bumping major resets minor and patch to 0

### Examples

| Change | Level | Before → After |
|--------|-------|----------------|
| Fixed container stop not cleaning up properly | PATCH | 1.0.0 → 1.0.1 |
| Added snapshot restore endpoint | MINOR | 1.0.1 → 1.1.0 |
| Added Redis support with new SKU tiers | MINOR | 1.1.0 → 1.2.0 |
| Changed `/databases` response schema (breaking) | MAJOR | 1.2.0 → 2.0.0 |
| Fixed CSS alignment on detail page | PATCH | 2.0.0 → 2.0.1 |
| Added new migration for monitoring tables | MINOR | 2.0.1 → 2.1.0 |
| Renamed `databases:read` permission | MAJOR | 2.1.0 → 3.0.0 |

### Registry Versioning

The top-level `registry.json` `"version"` field tracks the **registry version** (not individual module versions). Bump it when:

- **PATCH:** Updated module metadata (descriptions, tags) without code changes
- **MINOR:** Added a new module to the registry
- **MAJOR:** Removed a module or changed the registry schema format

## Creating a New Module

1. Create `modules/{module_name}/` directory
2. Create `module.json` manifest with all required fields
3. Create `__init__.py` with `__version__ = "1.0.0"` and any module-level init
4. Create `routes.py` using `ModuleRouter("module_name")` if the module has API endpoints
5. Create `hooks.py` with lifecycle hooks if needed
6. Create `migrations/` with initial `.sql` and `.down.sql` if the module needs database tables
7. Create `frontend/` with React pages/components if the module has a UI
8. Add the module entry to `registry.json`
9. Update the `README.md` available modules table

## Important Notes

- Modules MUST be fully self-contained — no cross-module imports
- The Module SDK (`module_sdk`) is defined in the `flux` core repo — do NOT modify it here
- Module frontend components run inside the Flux host app — they share the same React context, router, and UI library
- All module API routes are namespaced under `/api/modules/{module_name}/` automatically
- Database table names should be prefixed with the module name to avoid collisions
- Always test modules against the `min_app_version` of Flux they declare
- VNet IP allocation is optional — only use if the module manages networked containers
- Podman is the container runtime — do NOT use Docker commands
- Config templates in `services/config_templates/` are mounted into containers at runtime
- The `data/` directory is for runtime data only — it should be `.gitignore`d except for its initial structure
