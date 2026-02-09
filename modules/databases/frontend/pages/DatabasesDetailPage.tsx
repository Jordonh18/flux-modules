/**
 * Database Detail Page
 * 
 * Azure-style database management with tabs for:
 * - Overview: Connection info, stats, and status
 * - Logs: Real-time database logs
 * - Snapshots: Snapshot/restore management
 * - Settings: Database configuration
 */

import { memo, useState, useEffect, useRef, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useParams, useNavigate } from 'react-router-dom';
import { api } from '@/lib/api';
import { cn } from '@/lib/utils';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Separator } from '@/components/ui/separator';

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import {
  AlertCircle,
  ArrowLeft,
  Copy,
  Database,
  Download,
  HardDrive,
  Loader2,
  Play,
  RefreshCw,
  ScrollText,
  Square,
  Trash2,
  Upload,
  Clock,
  Cpu,
  MemoryStick,
  Activity,
  BarChart3,
} from 'lucide-react';
import { useDocumentTitle } from '@/hooks/use-document-title';
import { toast } from 'sonner';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import {
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
} from 'recharts';

// Types
interface DatabaseEngine {
  engine: string;
  display_name: string;
  description: string;
  category: string;
  default_port: number;
  supports_databases: boolean;
  supports_users: boolean;
  supports_backup: boolean;
  is_embedded: boolean;
}

interface DatabaseInfo {
  id: number;
  name: string;
  engine: string;
  status: string;
  host: string;
  port: number;
  database: string;
  username: string;
  password: string;
  created_at: string;
  error_message?: string;
  sku?: string;
  memory_limit_mb?: number;
  cpu_limit?: number;
  storage_limit_gb?: number;
  external_access?: boolean;
  tls_enabled?: boolean;
  volume_path?: string;
}

interface ContainerStats {
  container_id: string;
  name: string;
  cpu_percent: string;
  mem_usage: string;
  mem_percent: string;
  net_io: string;
  block_io: string;
  pids: number;
  error?: string;
}

interface InspectInfo {
  container: {
    id: string;
    name: string;
    image: string;
    created: string;
    state: {
      status: string;
      running: boolean;
      started_at: string;
      finished_at: string;
      exit_code: number;
    };
    network: {
      ip_address: string;
      ports: Record<string, any>;
    };
    mounts: Array<{
      source: string;
      destination: string;
      mode: string;
    }>;
  };
  database_size: {
    size: string;
    error?: string;
  };
}

interface Snapshot {
  id: number;
  path: string;
  size: number;
  created_at: string;
}

interface LogEntry {
  timestamp: string;
  level: 'info' | 'warning' | 'error' | 'debug';
  message: string;
}

interface MetricsPoint {
  timestamp: number;
  cpu_percent: number;
  memory_used_mb: number;
  memory_limit_mb: number;
  memory_percent: number;
  connections: number;
  active_queries: number;
  cache_hit_ratio: number | null;
  total_transactions: number | null;
  uptime_seconds: number | null;
  slow_queries: number | null;
}

interface MetricsResponse {
  current: MetricsPoint;
  history: MetricsPoint[];
}

const getCategoryIcon = (category: string) => {
  switch (category) {
    case 'relational': return '🐘';
    case 'nosql': return '🍃';
    case 'keyvalue': return '🔴';
    case 'timeseries': return '📈';
    case 'cache': return '⚡';
    case 'search': return '🔍';
    case 'graph': return '🕸️';
    case 'message_queue': return '📬';
    default: return '📦';
  }
};

const chartColors = {
  cpu: '#3b82f6',
  memory: '#22c55e',
  connections: '#f97316',
  cache: '#a855f7',
};

// API functions
const detailApi = {
  getEngines: () => api.get<DatabaseEngine[]>('/modules/databases/engines').then(r => r.data),
  getDatabase: (id: number) => 
    api.get<DatabaseInfo[]>('/modules/databases/databases').then(r => r.data.find(d => d.id === id)),
  getStats: (id: number) => 
    api.get<ContainerStats>(`/modules/databases/databases/${id}/stats`).then(r => r.data),
  getInspect: (id: number) => 
    api.get<InspectInfo>(`/modules/databases/databases/${id}/inspect`).then(r => r.data),
  getLogs: (id: number, lines = 200, level = '') => 
    api.get<{ entries: LogEntry[] }>(`/modules/databases/databases/${id}/logs?lines=${lines}${level ? `&level=${level}` : ''}`).then(r => r.data),
  getMetrics: (id: number) =>
    api.get<MetricsResponse>(`/modules/databases/databases/${id}/metrics`).then(r => r.data),
  getSnapshots: (id: number) => 
    api.get<{ snapshots: Snapshot[] }>(`/modules/databases/databases/${id}/snapshots`).then(r => r.data),
  createSnapshot: (id: number) => 
    api.post(`/modules/databases/databases/${id}/snapshot`).then(r => r.data),
  restoreSnapshot: (databaseId: number, snapshotId: number) => 
    api.post(`/modules/databases/databases/${databaseId}/restore/${snapshotId}`).then(r => r.data),
  deleteSnapshot: (databaseId: number, snapshotId: number) => 
    api.delete(`/modules/databases/databases/${databaseId}/snapshots/${snapshotId}`).then(r => r.data),
  startDatabase: (id: number) => 
    api.post(`/modules/databases/databases/${id}/start`).then(r => r.data),
  stopDatabase: (id: number) => 
    api.post(`/modules/databases/databases/${id}/stop`).then(r => r.data),
  deleteDatabase: (id: number) => 
    api.delete(`/modules/databases/databases/${id}`).then(r => r.data),
  restartDatabase: (id: number) => 
    api.post(`/modules/databases/databases/${id}/restart`).then(r => r.data),
  exportDatabase: (id: number) =>
    api.get(`/modules/databases/databases/${id}/export`, { responseType: 'blob' }),
  getTables: (id: number) => 
    api.get<{ tables: string[] }>(`/modules/databases/databases/${id}/tables`).then(r => r.data),
  getTableSchema: (id: number, tableName: string) => 
    api.get<{ schema: Array<{ name: string; type: string; nullable: string }> }>(`/modules/databases/databases/${id}/tables/${tableName}/schema`).then(r => r.data),
  getTableData: (id: number, tableName: string, limit = 10) => 
    api.get<{ data: { rows: string[][]; columns: string[] } }>(`/modules/databases/databases/${id}/tables/${tableName}/data?limit=${limit}`).then(r => r.data),
};

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`;
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleString();
}

function formatLogTimestamp(ts: string): string {
  try {
    const d = new Date(ts);
    if (isNaN(d.getTime())) return ts.slice(0, 23);
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) +
      '.' + String(d.getMilliseconds()).padStart(3, '0');
  } catch {
    return ts.slice(0, 23);
  }
}

function formatUptime(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (h < 24) return `${h}h ${m}m`;
  const d = Math.floor(h / 24);
  return `${d}d ${h % 24}h`;
}

function DatabaseDetailPageContent() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const databaseId = parseInt(id || '0', 10);

  const [showPassword, setShowPassword] = useState(false);
  const [activeTab, setActiveTab] = useState('overview');
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [restoreDialogSnapshot, setRestoreDialogSnapshot] = useState<Snapshot | null>(null);
  const [logLevelFilter, setLogLevelFilter] = useState('all');
  const [logSearch, setLogSearch] = useState('');
  const [metricsRange, setMetricsRange] = useState('1h');
  const logsEndRef = useRef<HTMLDivElement>(null);

  // Queries
  const { data: database, isLoading: dbLoading } = useQuery({
    queryKey: ['databases', 'detail', databaseId],
    queryFn: () => detailApi.getDatabase(databaseId),
    enabled: databaseId > 0,
    refetchInterval: 3000, // Refresh every 3s for real-time status
  });

  useDocumentTitle(database?.name ? ` Database - ${database.name}` : 'Database Details');

  const { data: inspect } = useQuery({
    queryKey: ['databases', 'inspect', databaseId],
    queryFn: () => detailApi.getInspect(databaseId),
    enabled: databaseId > 0 && database?.status === 'running',
    staleTime: 30000,
  });

  const { data: logsData, refetch: refetchLogs, isLoading: logsLoading } = useQuery({
    queryKey: ['databases', 'logs', databaseId, logLevelFilter],
    queryFn: () => detailApi.getLogs(databaseId, 500, logLevelFilter === 'all' ? '' : logLevelFilter),
    enabled: databaseId > 0 && activeTab === 'logs',
    refetchInterval: activeTab === 'logs' ? 3000 : false,
  });

  // Filter logs by search term client-side
  const filteredLogs = useMemo(() => {
    const entries = logsData?.entries || [];
    if (!logSearch) return entries;
    const q = logSearch.toLowerCase();
    return entries.filter(e => e.message.toLowerCase().includes(q));
  }, [logsData, logSearch]);

  const { data: metricsData } = useQuery({
    queryKey: ['databases', 'metrics', databaseId],
    queryFn: () => detailApi.getMetrics(databaseId),
    enabled: databaseId > 0 && database?.status === 'running' && (activeTab === 'metrics' || activeTab === 'overview'),
    refetchInterval: (activeTab === 'metrics' || activeTab === 'overview') ? 1000 : false,
  });

  // Filter metrics history by selected time range
  const filteredHistory = useMemo(() => {
    if (!metricsData?.history) return [];
    const rangeSeconds: Record<string, number> = {
      '1h': 3600, '6h': 21600, '12h': 43200, '1d': 86400, '7d': 604800, '30d': 2592000,
    };
    const cutoff = (Date.now() / 1000) - (rangeSeconds[metricsRange] || 3600);
    return metricsData.history.filter((p: MetricsPoint) => p.timestamp >= cutoff);
  }, [metricsData?.history, metricsRange]);

  const hasCacheHitData = useMemo(
    () => filteredHistory.some((p) => p.cache_hit_ratio != null),
    [filteredHistory]
  );

  // Auto-scroll logs to bottom when updated
  useEffect(() => {
    if (activeTab === 'logs' && logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logsData, activeTab]);

  const { data: snapshotsData, refetch: refetchSnapshots } = useQuery({
    queryKey: ['databases', 'snapshots', databaseId],
    queryFn: () => detailApi.getSnapshots(databaseId),
    enabled: databaseId > 0 && activeTab === 'snapshots',
  });

  // Mutations
  const startMutation = useMutation({
    mutationFn: () => detailApi.startDatabase(databaseId),
    onMutate: async () => {
      await queryClient.cancelQueries({ queryKey: ['databases', 'detail', databaseId] });
      const previousDatabase = queryClient.getQueryData<DatabaseInfo>(['databases', 'detail', databaseId]);
      
      queryClient.setQueryData<DatabaseInfo>(['databases', 'detail', databaseId], (old) => {
        if (!old) return old;
        return { ...old, status: 'starting' };
      });
      
      toast.info('Starting database...');
      return { previousDatabase };
    },
    onError: (_err, _variables, context) => {
      if (context?.previousDatabase) {
        queryClient.setQueryData(['databases', 'detail', databaseId], context.previousDatabase);
      }
      toast.error('Failed to start database');
    },
    onSuccess: () => {
      toast.success('Database started');
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['databases'] });
    },
  });

  const stopMutation = useMutation({
    mutationFn: () => detailApi.stopDatabase(databaseId),
    onMutate: async () => {
      await queryClient.cancelQueries({ queryKey: ['databases', 'detail', databaseId] });
      const previousDatabase = queryClient.getQueryData<DatabaseInfo>(['databases', 'detail', databaseId]);
      
      queryClient.setQueryData<DatabaseInfo>(['databases', 'detail', databaseId], (old) => {
        if (!old) return old;
        return { ...old, status: 'stopping' };
      });
      
      toast.info('Stopping database...');
      return { previousDatabase };
    },
    onError: (_err, _variables, context) => {
      if (context?.previousDatabase) {
        queryClient.setQueryData(['databases', 'detail', databaseId], context.previousDatabase);
      }
      toast.error('Failed to stop database');
    },
    onSuccess: () => {
      toast.success('Database stopped');
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['databases'] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () => detailApi.deleteDatabase(databaseId),
    onSuccess: () => {
      toast.success('Database deleted');
      navigate('/databases');
    },
    onError: () => toast.error('Failed to delete database'),
  });

  const restartMutation = useMutation({
    mutationFn: () => detailApi.restartDatabase(databaseId),
    onMutate: async () => {
      // Cancel outgoing refetches
      await queryClient.cancelQueries({ queryKey: ['databases', 'detail', databaseId] });
      
      // Snapshot previous value
      const previousDatabase = queryClient.getQueryData<DatabaseInfo>(['databases', 'detail', databaseId]);
      
      // Optimistically update to "restarting" status
      queryClient.setQueryData<DatabaseInfo>(['databases', 'detail', databaseId], (old) => {
        if (!old) return old;
        return { ...old, status: 'restarting' };
      });
      
      toast.info('Restarting database...');
      
      // Return context for rollback
      return { previousDatabase };
    },
    onError: (error: any, _variables, context) => {
      // Rollback on error
      if (context?.previousDatabase) {
        queryClient.setQueryData(['databases', 'detail', databaseId], context.previousDatabase);
      }
      toast.error(error.response?.data?.detail || 'Failed to restart database');
    },
    onSuccess: () => {
      toast.success('Database restarted');
    },
    onSettled: () => {
      // Refetch to ensure we have accurate data
      queryClient.invalidateQueries({ queryKey: ['databases'] });
    },
  });

  const exportMutation = useMutation({
    mutationFn: () => detailApi.exportDatabase(databaseId),
    onSuccess: (response) => {
      const blob = response.data as Blob;
      const disposition = response.headers?.['content-disposition'] as string | undefined;
      const match = disposition?.match(/filename="?([^";]+)"?/i);
      const fallbackName = `${database.name || 'database'}-export.sql`;
      const fileName = match?.[1] || fallbackName;
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = fileName;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      toast.success('Export complete');
    },
    onError: (err: any) => {
      const status = err?.response?.status;
      if (status === 401 || status === 403) {
        toast.error('Export failed: authentication required. Please sign in again.');
        return;
      }
      toast.error(err?.response?.data?.detail || 'Failed to export database');
    },
  });

  const snapshotMutation = useMutation({
    mutationFn: () => detailApi.createSnapshot(databaseId),
    onSuccess: () => {
      refetchSnapshots();
      toast.success('Snapshot created successfully');
    },
    onError: (err: any) => toast.error(err.response?.data?.detail || 'Failed to create snapshot'),
  });

  const restoreMutation = useMutation({
    mutationFn: (snapshotId: number) => detailApi.restoreSnapshot(databaseId, snapshotId),
    onSuccess: () => {
      setRestoreDialogSnapshot(null);
      toast.success('Database restored successfully');
    },
    onError: (err: any) => toast.error(err.response?.data?.detail || 'Failed to restore snapshot'),
  });

  const deleteSnapshotMutation = useMutation({
    mutationFn: (snapshotId: number) => detailApi.deleteSnapshot(databaseId, snapshotId),
    onSuccess: () => {
      refetchSnapshots();
      toast.success('Snapshot deleted');
    },
    onError: () => toast.error('Failed to delete snapshot'),
  });

  const getStatusBadgeClass = (status: string) => {
    switch (status.toLowerCase()) {
      case 'running':
        return 'status-badge-running';
      case 'stopped':
      case 'exited':
        return 'status-badge-stopped';
      case 'creating':
        return 'status-badge-creating';
      case 'starting':
        return 'status-badge-starting';
      case 'stopping':
        return 'status-badge-stopping';
      case 'restarting':
        return 'status-badge-restarting';
      case 'error':
        return 'status-badge-error';
      default:
        return 'status-badge-default';
    }
  };

  const copyToClipboard = (text: string, label: string) => {
    navigator.clipboard.writeText(text);
    toast.success(`${label} copied to clipboard`);
  };

  const typeInfo = database && engines.length > 0 ? (
    engines.find(e => e.engine === database.engine) || 
    { engine: database.engine, display_name: database.engine, category: 'other', description: '' }
  ) : null;

  const isRunning = database?.status === 'running';

  if (dbLoading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  if (!database) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-4">
        <AlertCircle className="h-12 w-12 text-muted-foreground" />
        <p className="text-muted-foreground">Database not found</p>
        <Button variant="outline" onClick={() => navigate('/databases')}>
          <ArrowLeft className="mr-2 h-4 w-4" />
          Back to Databases
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-4">
          <div>
            <h1 className="text-2xl font-bold">{database.name}</h1>
            <p className="text-muted-foreground text-sm">{typeInfo?.description}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span
            className={cn(
              "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium capitalize border",
              getStatusBadgeClass(database.status)
            )}
          >
            {(database.status === 'creating' || database.status === 'restarting' || database.status === 'starting' || database.status === 'stopping') && <Loader2 className="mr-1 h-3 w-3 animate-spin" />}
            {database.status}
          </span>
          {(database.status === 'running' || database.status === 'restarting' || database.status === 'stopping') ? (
            <>
              <Button variant="outline" size="sm" className="inline-flex items-center justify-center gap-2" onClick={() => restartMutation.mutate()} disabled={restartMutation.isPending || database.status === 'restarting' || database.status === 'stopping'}>
                <RefreshCw className="h-4 w-4 shrink-0" />
                <span className="leading-none">Restart</span>
              </Button>
              <Button variant="outline" size="sm" className="inline-flex items-center justify-center gap-2" onClick={() => stopMutation.mutate()} disabled={stopMutation.isPending || database.status === 'restarting' || database.status === 'stopping'}>
                <Square className="h-4 w-4 shrink-0" />
                <span className="leading-none">Stop</span>
              </Button>
            </>
          ) : database.status === 'stopped' && (
            <Button variant="outline" size="sm" className="inline-flex items-center justify-center gap-2" onClick={() => startMutation.mutate()} disabled={startMutation.isPending || database.status === 'starting'}>
              <Play className="h-4 w-4 shrink-0" />
              <span className="leading-none">Start</span>
            </Button>
          )}
          <Button 
            variant="outline" 
            size="sm" 
            className="inline-flex items-center justify-center gap-2"
            onClick={() => exportMutation.mutate()}
            disabled={database.status !== 'running' || exportMutation.isPending}
          >
            <Download className="h-4 w-4 shrink-0" />
            <span className="leading-none">{exportMutation.isPending ? 'Exporting...' : 'Export'}</span>
          </Button>
          <Button variant="destructive" size="sm" className="inline-flex items-center justify-center gap-2" onClick={() => setDeleteDialogOpen(true)}>
            <Trash2 className="h-4 w-4 shrink-0" />
            <span className="leading-none">Delete</span>
          </Button>
        </div>
      </div>

      {/* Error Message */}
      {database.error_message && (
        <Card className="border-destructive/50 bg-destructive/10">
          <CardContent className="flex items-center gap-3 p-4">
            <AlertCircle className="h-5 w-5 text-destructive" />
            <div>
              <p className="font-medium text-destructive">Error</p>
              <p className="text-sm">{database.error_message}</p>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="overview" className="flex items-center gap-2">
            <Database className="h-4 w-4" />
            Overview
          </TabsTrigger>
          <TabsTrigger value="logs" className="flex items-center gap-2">
            <ScrollText className="h-4 w-4" />
            Logs
          </TabsTrigger>
          <TabsTrigger value="metrics" className="flex items-center gap-2">
            <BarChart3 className="h-4 w-4" />
            Metrics
          </TabsTrigger>
          <TabsTrigger value="snapshots" className="flex items-center gap-2">
            <HardDrive className="h-4 w-4" />
            Snapshots
          </TabsTrigger>
        </TabsList>

        {/* Overview Tab */}
        <TabsContent value="overview" className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            {/* Connection Info */}
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">Connection Details</CardTitle>
                <CardDescription>Host and access credentials</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-muted-foreground">Host</span>
                    <div className="flex items-center gap-2">
                      <code className="text-sm bg-muted px-2 py-1 rounded">{database.host}:{database.port}</code>
                      <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => copyToClipboard(`${database.host}:${database.port}`, 'Host')}>
                        <Copy className="h-3 w-3" />
                      </Button>
                    </div>
                  </div>
                  <Separator />
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-muted-foreground">Database</span>
                    <div className="flex items-center gap-2">
                      <code className="text-sm bg-muted px-2 py-1 rounded">{database.database}</code>
                      <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => copyToClipboard(database.database, 'Database')}>
                        <Copy className="h-3 w-3" />
                      </Button>
                    </div>
                  </div>
                  <Separator />
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-muted-foreground">Username</span>
                    <div className="flex items-center gap-2">
                      <code className="text-sm bg-muted px-2 py-1 rounded">{database.username}</code>
                      <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => copyToClipboard(database.username, 'Username')}>
                        <Copy className="h-3 w-3" />
                      </Button>
                    </div>
                  </div>
                  <Separator />
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-muted-foreground">Password</span>
                    <div className="flex items-center gap-2">
                      <code 
                        className="text-sm bg-muted px-2 py-1 rounded cursor-default"
                        onMouseEnter={() => setShowPassword(true)}
                        onMouseLeave={() => setShowPassword(false)}
                      >
                        {showPassword ? database.password : '••••••••••••'}
                      </code>
                      <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => copyToClipboard(database.password, 'Password')}>
                        <Copy className="h-3 w-3" />
                      </Button>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Connection String */}
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">Connection String</CardTitle>
                <CardDescription>Use this to connect from your application</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  <div className="flex items-start gap-2">
                    <code className="flex-1 text-xs bg-muted p-3 rounded break-all">
                      {database.engine === 'redis' 
                        ? `redis://:${showPassword ? database.password : '********'}@${database.host}:${database.port}/0`
                        : database.engine === 'mongodb'
                        ? `mongodb://${database.username}:${showPassword ? database.password : '********'}@${database.host}:${database.port}/${database.database}`
                        : `${database.engine === 'postgresql' ? 'postgresql' : 'mysql'}://${database.username}:${showPassword ? database.password : '********'}@${database.host}:${database.port}/${database.database}`
                      }
                    </code>
                  </div>
                  <Button 
                    variant="outline" 
                    size="sm" 
                    className="w-full"
                    onClick={() => {
                      const connString = database.engine === 'redis' 
                        ? `redis://:${database.password}@${database.host}:${database.port}/0`
                        : database.engine === 'mongodb'
                        ? `mongodb://${database.username}:${database.password}@${database.host}:${database.port}/${database.database}`
                        : `${database.engine === 'postgresql' ? 'postgresql' : 'mysql'}://${database.username}:${database.password}@${database.host}:${database.port}/${database.database}`;
                      copyToClipboard(connString, 'Connection string');
                    }}
                  >
                    <Copy className="mr-2 h-4 w-4" />
                    Copy Connection String
                  </Button>
                </div>
              </CardContent>
            </Card>

            {/* Database Info */}
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">Database Info</CardTitle>
                <CardDescription>Identity and lifecycle details</CardDescription>
              </CardHeader>
              <CardContent className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">Type</span>
                  <span>{typeInfo?.display_name}</span>
                </div>
                <Separator />
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">Size</span>
                  <span>{inspect?.database_size?.size || '—'}</span>
                </div>
                <Separator />
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">Created</span>
                  <span className="text-sm">{formatDate(database.created_at)}</span>
                </div>
                {inspect?.container?.state?.started_at && (
                  <>
                    <Separator />
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-muted-foreground">Started</span>
                      <span className="text-sm">{formatDate(inspect.container.state.started_at)}</span>
                    </div>
                  </>
                )}
              </CardContent>
            </Card>

            {/* Compute & Storage SKU */}
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">Instance Configuration</CardTitle>
                <CardDescription>Compute and storage resources</CardDescription>
              </CardHeader>
              <CardContent className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">SKU Tier</span>
                  <Badge variant="outline" className="font-mono">
                    {database.sku?.toUpperCase() || 'B2'}
                  </Badge>
                </div>
                <Separator />
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground flex items-center gap-2">
                    <Cpu className="h-4 w-4" /> vCPUs
                  </span>
                  <span className="font-mono">{database.cpu_limit || 1.0} {database.cpu_limit === 1 ? 'vCore' : 'vCores'}</span>
                </div>
                <Separator />
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground flex items-center gap-2">
                    <MemoryStick className="h-4 w-4" /> Memory
                  </span>
                  <span className="font-mono">{((database.memory_limit_mb || 2048) / 1024).toFixed(1)} GB</span>
                </div>
                <Separator />
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground flex items-center gap-2">
                    <HardDrive className="h-4 w-4" /> Storage
                  </span>
                  <span className="font-mono">{database.storage_limit_gb || 20} GB</span>
                </div>
              </CardContent>
            </Card>

            {/* Network & Security */}
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">Network & Security</CardTitle>
                <CardDescription>Access and encryption settings</CardDescription>
              </CardHeader>
              <CardContent className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">
                    Public Access
                  </span>
                  <Badge variant={database.external_access ? 'default' : 'secondary'}>
                    {database.external_access ? 'Enabled' : 'Disabled'}
                  </Badge>
                </div>
                {database.external_access && (
                  <>
                    <Separator />
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-muted-foreground">Public Endpoint</span>
                      <code className="text-xs bg-muted px-2 py-1 rounded">
                        0.0.0.0:{database.port}
                      </code>
                    </div>
                  </>
                )}
                {!database.external_access && (
                  <>
                    <Separator />
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-muted-foreground">Private Endpoint</span>
                      <code className="text-xs bg-muted px-2 py-1 rounded">
                        127.0.0.1:{database.port}
                      </code>
                    </div>
                  </>
                )}
                <Separator />
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">TLS/SSL</span>
                  <Badge variant={database.tls_enabled ? 'default' : 'outline'}>
                    {database.tls_enabled ? 'Enabled' : 'Not Configured'}
                  </Badge>
                </div>
                {database.volume_path && (
                  <>
                    <Separator />
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-muted-foreground">Persistent Storage</span>
                      <Badge variant="default">Enabled</Badge>
                    </div>
                  </>
                )}
              </CardContent>
            </Card>

            {/* Quick Stats */}
            {isRunning && metricsData?.current && (
              <Card>
                <CardHeader>
                  <CardTitle className="text-lg flex items-center justify-between">
                    Performance
                  </CardTitle>
                  <CardDescription>Live runtime highlights</CardDescription>
                </CardHeader>
                <CardContent className="space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-muted-foreground flex items-center gap-2">
                      <Cpu className="h-4 w-4" /> CPU
                    </span>
                    <span className="font-mono">{metricsData.current.cpu_percent}%</span>
                  </div>
                  <Separator />
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-muted-foreground flex items-center gap-2">
                      <MemoryStick className="h-4 w-4" /> Memory
                    </span>
                    <span className="font-mono">{metricsData.current.memory_used_mb.toFixed(0)} / {metricsData.current.memory_limit_mb.toFixed(0)} MB</span>
                  </div>
                  <Separator />
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-muted-foreground flex items-center gap-2">
                      <Activity className="h-4 w-4" /> Connections
                    </span>
                    <span className="font-mono">{metricsData.current.connections}</span>
                  </div>
                  {metricsData.current.cache_hit_ratio != null && (
                    <>
                      <Separator />
                      <div className="flex items-center justify-between">
                        <span className="text-sm text-muted-foreground flex items-center gap-2">
                          <BarChart3 className="h-4 w-4" /> Cache Hit Ratio
                        </span>
                        <span className="font-mono">{metricsData.current.cache_hit_ratio}%</span>
                      </div>
                    </>
                  )}
                  {metricsData.current.uptime_seconds != null && (
                    <>
                      <Separator />
                      <div className="flex items-center justify-between">
                        <span className="text-sm text-muted-foreground flex items-center gap-2">
                          <Clock className="h-4 w-4" /> Uptime
                        </span>
                        <span className="font-mono text-sm">{formatUptime(metricsData.current.uptime_seconds)}</span>
                      </div>
                    </>
                  )}
                </CardContent>
              </Card>
            )}
          </div>
        </TabsContent>

        {/* Logs Tab */}
        <TabsContent value="logs" className="space-y-4">
          <Card className="w-full">
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="text-lg">Database Logs</CardTitle>
                  <CardDescription>Server logs, auto-refreshes every 3 seconds</CardDescription>
                </div>
                <div className="flex items-center gap-2">
                  <Select value={logLevelFilter} onValueChange={setLogLevelFilter}>
                    <SelectTrigger className="w-[120px] h-8 text-xs">
                      <SelectValue placeholder="All levels" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All levels</SelectItem>
                      <SelectItem value="error">Error</SelectItem>
                      <SelectItem value="warning">Warning</SelectItem>
                      <SelectItem value="info">Info</SelectItem>
                      <SelectItem value="debug">Debug</SelectItem>
                    </SelectContent>
                  </Select>
                  <Button variant="outline" size="sm" onClick={() => refetchLogs()} disabled={logsLoading}>
                    {logsLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                  </Button>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <div className="overflow-hidden min-w-0 rounded-md border bg-muted">
                <div className="max-h-[70vh] w-full overflow-y-auto">
                  <div className="p-4">
                    <pre className="text-xs text-foreground font-mono whitespace-pre-wrap break-all leading-relaxed">
                      {filteredLogs.length > 0
                        ? filteredLogs.map((e, i) => 
                            `${e.timestamp ? e.timestamp : ''} [${e.level.toUpperCase()}] ${e.message}`
                          ).join('\n')
                        : 'No logs available'}
                    </pre>
                    <div ref={logsEndRef} />
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Metrics Tab */}
        <TabsContent value="metrics" className="space-y-4">
          {!isRunning ? (
            <Card>
              <CardContent className="flex flex-col items-center justify-center py-12 text-muted-foreground">
                <BarChart3 className="h-12 w-12 mb-4 opacity-50" />
                <p>Start the database to view metrics</p>
              </CardContent>
            </Card>
          ) : (
            <>
              {/* Time range selector */}
              <div className="flex items-center justify-between">
                <p className="text-sm text-muted-foreground">
                  {filteredHistory.length} data points
                </p>
                <div className="flex items-center gap-1 rounded-lg border p-1">
                  {['1h', '6h', '12h', '1d', '7d', '30d'].map((range) => (
                    <Button
                      key={range}
                      variant={metricsRange === range ? 'default' : 'ghost'}
                      size="sm"
                      className="h-7 px-2.5 text-xs"
                      onClick={() => setMetricsRange(range)}
                    >
                      {range}
                    </Button>
                  ))}
                </div>
              </div>

              {/* Summary cards */}
              {metricsData?.current && (
                <div className="grid gap-4 grid-cols-2 md:grid-cols-4">
                  <Card>
                    <CardContent className="pt-4 pb-3 px-4">
                      <p className="text-xs text-muted-foreground mb-1">CPU Usage</p>
                      <p className="text-2xl font-bold">{metricsData.current.cpu_percent}%</p>
                    </CardContent>
                  </Card>
                  <Card>
                    <CardContent className="pt-4 pb-3 px-4">
                      <p className="text-xs text-muted-foreground mb-1">Memory</p>
                      <p className="text-2xl font-bold">{metricsData.current.memory_percent.toFixed(1)}%</p>
                      <p className="text-xs text-muted-foreground">{metricsData.current.memory_used_mb.toFixed(0)} / {metricsData.current.memory_limit_mb.toFixed(0)} MB</p>
                    </CardContent>
                  </Card>
                  <Card>
                    <CardContent className="pt-4 pb-3 px-4">
                      <p className="text-xs text-muted-foreground mb-1">Connections</p>
                      <p className="text-2xl font-bold">{metricsData.current.connections}</p>
                      <p className="text-xs text-muted-foreground">{metricsData.current.active_queries} active</p>
                    </CardContent>
                  </Card>
                  <Card>
                    <CardContent className="pt-4 pb-3 px-4">
                      <p className="text-xs text-muted-foreground mb-1">Cache Hit Ratio</p>
                      <p className="text-2xl font-bold">{metricsData.current.cache_hit_ratio != null ? `${metricsData.current.cache_hit_ratio}%` : '—'}</p>
                      {metricsData.current.cache_hit_ratio == null && (
                        <p className="text-xs text-muted-foreground">Waiting for connections</p>
                      )}
                    </CardContent>
                  </Card>
                </div>
              )}

              {/* Charts */}
              {filteredHistory.length > 1 ? (
                <div className="grid gap-4 md:grid-cols-2">
                  {/* CPU Chart */}
                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm font-medium">CPU Usage</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="h-[200px]">
                        <ResponsiveContainer width="100%" height="100%">
                          <LineChart data={filteredHistory}>
                            <Tooltip
                              labelFormatter={(v) => new Date(v * 1000).toLocaleTimeString()}
                              formatter={(v: number) => [`${v.toFixed(2)}%`, 'CPU']}
                              contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid hsl(var(--border))', background: 'hsl(var(--popover))', color: 'hsl(var(--foreground))' }}
                            />
                            <Line type="monotone" dataKey="cpu_percent" stroke={chartColors.cpu} strokeWidth={1.75} dot={false} />
                          </LineChart>
                        </ResponsiveContainer>
                      </div>
                    </CardContent>
                  </Card>

                  {/* Memory Chart */}
                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm font-medium">Memory Usage</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="h-[200px]">
                        <ResponsiveContainer width="100%" height="100%">
                          <LineChart data={filteredHistory}>
                            <Tooltip
                              labelFormatter={(v) => new Date(v * 1000).toLocaleTimeString()}
                              formatter={(v: number) => [`${v.toFixed(1)} MB`, 'Memory']}
                              contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid hsl(var(--border))', background: 'hsl(var(--popover))', color: 'hsl(var(--foreground))' }}
                            />
                            <Line type="monotone" dataKey="memory_used_mb" stroke={chartColors.memory} strokeWidth={1.75} dot={false} />
                          </LineChart>
                        </ResponsiveContainer>
                      </div>
                    </CardContent>
                  </Card>

                  {/* Connections Chart */}
                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm font-medium">Connections</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="h-[200px]">
                        <ResponsiveContainer width="100%" height="100%">
                          <LineChart data={filteredHistory}>
                            <Tooltip
                              labelFormatter={(v) => new Date(v * 1000).toLocaleTimeString()}
                              formatter={(v: number) => [v, 'Connections']}
                              contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid hsl(var(--border))', background: 'hsl(var(--popover))', color: 'hsl(var(--foreground))' }}
                            />
                            <Line type="monotone" dataKey="connections" stroke={chartColors.connections} strokeWidth={1.75} dot={false} />
                          </LineChart>
                        </ResponsiveContainer>
                      </div>
                    </CardContent>
                  </Card>

                  {/* Cache Hit Ratio Chart */}
                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm font-medium">Cache Hit Ratio</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="h-[200px]">
                        {hasCacheHitData ? (
                          <ResponsiveContainer width="100%" height="100%">
                            <LineChart data={filteredHistory}>
                              <Tooltip
                                labelFormatter={(v) => new Date(v * 1000).toLocaleTimeString()}
                                formatter={(v: number | null) => [v != null ? `${v}%` : '—', 'Cache Hit']}
                                contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid hsl(var(--border))', background: 'hsl(var(--popover))', color: 'hsl(var(--foreground))' }}
                              />
                              <Line type="monotone" dataKey="cache_hit_ratio" stroke={chartColors.cache} strokeWidth={1.75} dot={false} connectNulls />
                            </LineChart>
                          </ResponsiveContainer>
                        ) : (
                          <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                            No cache data yet - waiting for connections
                          </div>
                        )}
                      </div>
                    </CardContent>
                  </Card>
                </div>
              ) : (
                <Card>
                  <CardContent className="flex flex-col items-center justify-center py-12 text-muted-foreground">
                    <Loader2 className="h-8 w-8 mb-3 animate-spin opacity-50" />
                    <p className="text-sm">Collecting metrics data...</p>
                    <p className="text-xs mt-1">Charts will appear after a few data points are recorded</p>
                  </CardContent>
                </Card>
              )}
            </>
          )}
        </TabsContent>

        {/* Snapshots Tab */}
        <TabsContent value="snapshots" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg flex items-center justify-between">
                Snapshots
                <Button 
                  onClick={() => snapshotMutation.mutate()} 
                  disabled={snapshotMutation.isPending || !isRunning}
                >
                  {snapshotMutation.isPending ? 'Creating...' : 'Create Snapshot'}
                </Button>
              </CardTitle>
              <CardDescription>
                {isRunning ? 'Create and manage database snapshots' : 'Start the database to create snapshots'}
              </CardDescription>
            </CardHeader>
            <CardContent>
              {snapshotsData?.snapshots?.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
                  <HardDrive className="h-12 w-12 mb-4 opacity-50" />
                  <p>No snapshots yet</p>
                  <p className="text-sm">Create your first snapshot to protect your data</p>
                </div>
              ) : (
                <div className="space-y-2">
                  {snapshotsData?.snapshots?.map((snapshot) => (
                    <div 
                      key={snapshot.id}
                      className="flex items-center justify-between p-3 rounded-lg border bg-card hover:bg-accent/50 transition-colors"
                    >
                      <div className="flex items-center gap-3">
                        <HardDrive className="h-5 w-5 text-muted-foreground" />
                        <div>
                          <p className="font-medium text-sm">{snapshot.path.split('/').pop()}</p>
                          <div className="flex items-center gap-2 text-xs text-muted-foreground">
                            <Clock className="h-3 w-3" />
                            {formatDate(snapshot.created_at)}
                            <span>•</span>
                            {formatBytes(snapshot.size)}
                          </div>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <Button 
                          variant="outline" 
                          size="sm"
                          onClick={() => setRestoreDialogSnapshot(snapshot)}
                          disabled={!isRunning}
                        >
                          <Upload className="mr-2 h-4 w-4" />
                          Restore
                        </Button>
                        <Button 
                          variant="ghost" 
                          size="icon"
                          className="text-destructive hover:text-destructive"
                          onClick={() => deleteSnapshotMutation.mutate(snapshot.id)}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Delete Confirmation Dialog */}
      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Database</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete "{database.name}"? This will permanently delete all data. This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => deleteMutation.mutate()}
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Restore Confirmation Dialog */}
      <AlertDialog open={!!restoreDialogSnapshot} onOpenChange={() => setRestoreDialogSnapshot(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Restore from Snapshot</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to restore the database from this snapshot? This will overwrite the current data with the snapshot data.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => restoreDialogSnapshot && restoreMutation.mutate(restoreDialogSnapshot.id)}
            >
              Restore
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

const DatabaseDetailPage = memo(DatabaseDetailPageContent);
export default DatabaseDetailPage;
