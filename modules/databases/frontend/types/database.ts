// All TypeScript types matching the API responses

export type DatabaseEngine = string; // Dynamic from adapter registry

export interface EngineInfo {
  engine: string;
  display_name: string;
  category: 'relational' | 'document' | 'key_value' | 'wide_column' | 'time_series' | 'search' | 'graph' | 'analytical' | 'embedded';
  default_port: number;
  image: string;
  supports_databases: boolean;
  supports_users: boolean;
  supports_backup: boolean;
  is_embedded: boolean;
}

export interface DatabaseInstance {
  id: number;
  name: string;
  engine: string;    // was "type"
  status: 'creating' | 'running' | 'stopped' | 'error' | 'unknown';
  host: string;
  port: number;
  database: string;
  username: string;
  password: string;
  connection_string: string;
  created_at: string;
  error_message?: string;
  sku?: string;
  memory_limit_mb?: number;
  cpu_limit?: number;
  storage_limit_gb?: number;
  external_access?: boolean;
  tls_enabled?: boolean;
  vnet_ip?: string;
}

export interface CreateDatabaseRequest {
  engine: string;
  name?: string;
  database_name: string;
  sku: string;
  memory_limit_mb?: number;
  cpu_limit?: number;
  storage_limit_gb?: number;
  external_access?: boolean;
  tls_enabled?: boolean;
  tls_cert?: string;
  tls_key?: string;
  vnet_name?: string;
}

export interface DatabaseMetrics {
  current: {
    timestamp: number;
    cpu_percent: number;
    memory_used_mb: number;
    memory_limit_mb: number;
    memory_percent: number;
    [key: string]: any; // engine-specific metrics
  };
  history: Array<{
    timestamp: number;
    cpu_percent: number;
    memory_used_mb: number;
    memory_limit_mb: number;
    memory_percent: number;
    [key: string]: any;
  }>;
}

export interface HealthStatus {
  status: 'healthy' | 'unhealthy' | 'degraded' | 'unknown';
  details: Record<string, any>;
  checked_at: string;
}

export interface Snapshot {
  id: number;
  path: string;
  size: number;
  created_at: string;
}

export interface InnerDatabase {
  name: string;
  size?: string;
  tables?: number;
}

export interface DatabaseUser {
  username: string;
  privileges?: string[];
}

export type DatabaseCategory = EngineInfo['category'];

// Category display info
export const CATEGORY_INFO: Record<DatabaseCategory, { label: string; color: string }> = {
  relational: { label: 'Relational SQL', color: 'bg-blue-500' },
  document: { label: 'Document', color: 'bg-green-500' },
  key_value: { label: 'Key-Value', color: 'bg-amber-500' },
  wide_column: { label: 'Wide Column', color: 'bg-purple-500' },
  time_series: { label: 'Time Series', color: 'bg-cyan-500' },
  search: { label: 'Search', color: 'bg-orange-500' },
  graph: { label: 'Graph', color: 'bg-pink-500' },
  analytical: { label: 'Analytical', color: 'bg-indigo-500' },
  embedded: { label: 'Embedded', color: 'bg-gray-500' },
};

// Engine icon mapping
export const ENGINE_ICONS: Record<string, string> = {
  postgresql: '🐘',
  mysql: '🐬',
  mariadb: '🦭',
  mongodb: '🍃',
  redis: '🔴',
  mssql: '🔷',
  oracle: '🔶',
  cockroachdb: '🪳',
  couchdb: '🛋️',
  arangodb: '🥑',
  keydb: '🔑',
  valkey: '🗝️',
  cassandra: '👁️',
  scylladb: '🦑',
  influxdb: '📈',
  timescaledb: '⏱️',
  questdb: '❓',
  elasticsearch: '🔍',
  meilisearch: '🔎',
  typesense: '⌨️',
  neo4j: '🕸️',
  janusgraph: '🌐',
  clickhouse: '🏠',
  duckdb: '🦆',
  h2: '💧',
};
