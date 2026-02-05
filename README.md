# Flux Module Registry

Official module registry for Flux.

## Available Modules

| Module | Description | Version |
|--------|-------------|---------|
| **Databases** | Database management and exploration tools | 1.0.0 |

## Installation

Add this registry to your Flux instance:

1. Go to **Admin > Modules > Browse Registry**
2. Click **Manage Registries**
3. Add: `Jordonh18/flux-modules`

Then install modules directly from the browse interface.

## Structure

```
flux-modules/
├── registry.json           # Registry manifest
├── README.md
└── modules/
    └── Databases/
        ├── module.json
        ├── __init__.py
        ├── routes.py
        ├── hooks.py
        └── frontend/
            └── pages/
                └── DatabasePage.tsx
```
