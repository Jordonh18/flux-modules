# Databases Module

**Module ID:** `620600`
**Version:** `2.0.0`
**Table Prefix:** `620600_databases`

Database-as-a-Service management for the Flux platform. Provisions, manages, and monitors containerized database instances using Podman with 25+ engine support.

## Features

- **25 Database Engines** — Relational, Document, Key-Value, Wide Column, Time Series, Search, Graph, Analytical, and Embedded databases
- **Adapter Architecture** — Each engine has a dedicated adapter implementing a common interface
- **SKU-Based Sizing** — Azure-style B/D/E/F series tiers with CPU, memory, and storage allocation
- **Container Orchestration** — Rootless Podman with security hardening (cap-drop=all, no-new-privileges, pids-limit)
- **Health Monitoring** — Periodic health checks with history tracking
- **Metrics Collection** — CPU, memory, and engine-specific metrics with time-series history
- **Backup & Restore** — Engine-native backup commands with snapshot management
- **Credential Management** — Secure password generation, rotation, and connection string building
- **VNet Integration** — Optional VNet IP allocation for network isolation
- **TLS Support** — Optional TLS encryption with user-provided certificates
- **Jinja2 Config Templates** — Dynamic configuration rendering per engine and SKU

## Supported Engines

| Category | Engines |
|----------|---------|
| Relational SQL | MySQL, PostgreSQL, MariaDB, MSSQL, Oracle, CockroachDB |
| Document | MongoDB, CouchDB, ArangoDB |
| Key-Value | Redis, KeyDB, Valkey |
| Wide Column | Cassandra, ScyllaDB |
| Time Series | InfluxDB, TimescaleDB, QuestDB |
| Search | Elasticsearch, Meilisearch, Typesense |
| Graph | Neo4j, JanusGraph |
| Analytical | ClickHouse, DuckDB |
| Embedded | H2 |

## SKU Tiers

| Series | Description | Podman Behavior |
|--------|-------------|-----------------|
| B-series | Burstable | `cpu-shares=512` — low priority, yields under contention |
| D-series | General Purpose | `cpu-shares=1024` — standard balanced performance |
| E-series | Memory Optimized | `swappiness=0`, `oom-score-adj=-500` — keeps data in RAM |
| F-series | Compute Optimized | `cpu-shares=2048`, `memory-swap=memory` — high CPU priority |

## Architecture

```
modules/databases/
├── module.json              # Module manifest
├── __init__.py              # Constants (MODULE_ID, TABLE_PREFIX, table names)
├── routes.py                # API routes (thin layer → services)
├── hooks.py                 # Lifecycle hooks (enable/disable)
├── config_templates/        # Jinja2 config templates per engine
│   ├── mysql/my.cnf.j2
│   ├── postgresql/postgresql.conf.j2
│   ├── mongodb/mongod.conf.j2
│   └── ...
├── frontend/                # React frontend
│   ├── types/               # TypeScript definitions
│   ├── components/          # Reusable UI components
│   └── pages/               # Page-level components
├── migrations/              # Database migrations
│   ├── 001_initial.sql
│   └── 001_initial.down.sql
├── services/                # Business logic
│   ├── adapters/            # 25 engine adapters
│   │   ├── base.py          # Abstract BaseAdapter
│   │   ├── mysql.py
│   │   ├── postgresql.py
│   │   └── ...
│   ├── instance_manager.py
│   ├── container_orchestrator.py
│   ├── backup_service.py
│   ├── metrics_collector.py
│   ├── health_monitor.py
│   ├── credential_manager.py
│   ├── database_operations.py
│   └── volume_service.py
└── data/                    # Runtime data (gitignored)
    ├── containers/
    ├── backups/
    ├── logs/
    └── tls/
```

## API Endpoints

All routes are mounted at `/api/modules/databases/`.

### System

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| GET | `/status` | — | Module status + Podman check |
| GET | `/requirements` | — | System requirements check |
| GET | `/system-info` | — | Host CPU/RAM information |
| GET | `/podman/status` | — | Podman installation status |
| POST | `/podman/install` | `databases:write` | Install Podman |
| GET | `/engines` | — | List all supported engines |
| GET | `/skus` | — | List all SKU definitions |

### Instance Management

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| GET | `/databases` | `databases:read` | List all instances |
| POST | `/databases` | `databases:write` | Create new instance |
| POST | `/databases/{id}/start` | `databases:write` | Start instance |
| POST | `/databases/{id}/stop` | `databases:write` | Stop instance |
| POST | `/databases/{id}/restart` | `databases:write` | Restart instance |
| DELETE | `/databases/{id}` | `databases:write` | Delete instance |

### Monitoring

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| GET | `/databases/{id}/logs` | `databases:read` | Container logs |
| GET | `/databases/{id}/metrics` | `databases:read` | Performance metrics |
| GET | `/databases/{id}/stats` | `databases:read` | Container stats |
| GET | `/databases/{id}/inspect` | `databases:read` | Detailed container info |
| GET | `/databases/{id}/health` | `databases:read` | Health check status |

### Backup & Restore

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| POST | `/databases/{id}/snapshot` | `databases:write` | Create snapshot |
| GET | `/databases/{id}/snapshots` | `databases:read` | List snapshots |
| POST | `/databases/{id}/restore/{sid}` | `databases:write` | Restore from snapshot |
| DELETE | `/databases/{id}/snapshots/{sid}` | `databases:write` | Delete snapshot |
| GET | `/databases/{id}/export` | `databases:read` | Export as zip |

### Data & Security

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| GET | `/databases/{id}/tables` | `databases:read` | List tables |
| GET | `/databases/{id}/tables/{name}/schema` | `databases:read` | Table schema |
| GET | `/databases/{id}/tables/{name}/data` | `databases:read` | Sample data |
| POST | `/databases/{id}/credentials/rotate` | `databases:write` | Rotate credentials |
| GET | `/databases/{id}/connection-string` | `databases:read` | Connection string |
| POST | `/databases/{id}/databases` | `databases:write` | Create inner database |
| GET | `/databases/{id}/databases` | `databases:read` | List inner databases |
| POST | `/databases/{id}/users` | `databases:write` | Create user |
| GET | `/databases/{id}/users` | `databases:read` | List users |

## Database Tables

All tables use the `620600_databases_` prefix:

| Table | Description |
|-------|-------------|
| `620600_databases_instances` | Database instances (container tracking) |
| `620600_databases_snapshots` | Snapshot/backup records |
| `620600_databases_backups` | Extended backup metadata |
| `620600_databases_metrics` | Time-series metrics data |
| `620600_databases_health_history` | Health check history |
| `620600_databases_credentials` | Stored credentials (hashed) |
| `620600_databases_users` | Database users within instances |
| `620600_databases_databases` | Databases within instances |

## Permissions

| Permission | Description |
|------------|-------------|
| `databases:read` | View databases, metrics, logs, snapshots |
| `databases:write` | Create, modify, delete databases and snapshots |

## Requirements

- **Podman** — Rootless container runtime (auto-installed on module enable)
- **Flux** ≥ 1.0.0 — Core platform with module support

## Development

```bash
# Module runs within Flux — no standalone startup
# Start Flux in dev mode:
cd /path/to/flux
npm run start

# The module is auto-loaded from the modules/ directory
```

## License

MIT
