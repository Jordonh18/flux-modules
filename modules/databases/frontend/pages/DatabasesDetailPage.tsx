/**
 * Database Detail Page
 * 
 * Azure-style database management with tabs for:
 * - Overview: Connection info, stats, and status
 * - Logs: Real-time database logs
 * - Backups: Backup/restore management
 * - Settings: Database configuration
 */

import { memo, useState, useEffect, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useParams, useNavigate } from 'react-router-dom';
import { api } from '@/lib/api';
import { cn } from '@/lib/utils';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
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
  Table,
  Square,
  Trash2,
  Eye,
  EyeOff,
  Upload,
  Clock,
  Search,
  Columns,
  List,
  Cpu,
  MemoryStick,
  Network,
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

// Types
interface DatabaseInfo {
  id: number;
  name: string;
  type: string;
  status: string;
  host: string;
  port: number;
  database: string;
  username: string;
  password: string;
  created_at: string;
  error_message?: string;
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

interface Backup {
  id: number;
  path: string;
  size: number;
  created_at: string;
}

// Database type options
const DATABASE_TYPES: Record<string, { label: string; icon: string; description: string }> = {
  postgresql: { label: 'PostgreSQL', icon: '🐘', description: 'Advanced open-source relational database' },
  mysql: { label: 'MySQL', icon: '🐬', description: 'World\'s most popular open source database' },
  mariadb: { label: 'MariaDB', icon: '🦭', description: 'Enhanced MySQL-compatible database' },
  mongodb: { label: 'MongoDB', icon: '🍃', description: 'Document-oriented NoSQL database' },
  redis: { label: 'Redis', icon: '🔴', description: 'In-memory data structure store' },
};

// API functions
const detailApi = {
  getDatabase: (id: number) => 
    api.get<DatabaseInfo[]>('/modules/databases/databases').then(r => r.data.find(d => d.id === id)),
  getStats: (id: number) => 
    api.get<ContainerStats>(`/modules/databases/databases/${id}/stats`).then(r => r.data),
  getInspect: (id: number) => 
    api.get<InspectInfo>(`/modules/databases/databases/${id}/inspect`).then(r => r.data),
  getLogs: (id: number, lines = 200) => 
    api.get<{ logs: string }>(`/modules/databases/databases/${id}/logs?lines=${lines}`).then(r => r.data),
  getBackups: (id: number) => 
    api.get<{ backups: Backup[] }>(`/modules/databases/databases/${id}/backups`).then(r => r.data),
  createBackup: (id: number) => 
    api.post(`/modules/databases/databases/${id}/backup`).then(r => r.data),
  restoreBackup: (databaseId: number, backupId: number) => 
    api.post(`/modules/databases/databases/${databaseId}/restore/${backupId}`).then(r => r.data),
  deleteBackup: (databaseId: number, backupId: number) => 
    api.delete(`/modules/databases/databases/${databaseId}/backups/${backupId}`).then(r => r.data),
  startDatabase: (id: number) => 
    api.post(`/modules/databases/databases/${id}/start`).then(r => r.data),
  stopDatabase: (id: number) => 
    api.post(`/modules/databases/databases/${id}/stop`).then(r => r.data),
  deleteDatabase: (id: number) => 
    api.delete(`/modules/databases/databases/${id}`).then(r => r.data),
  restartDatabase: (id: number) => 
    api.post(`/modules/databases/databases/${id}/restart`).then(r => r.data),
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

function DatabaseDetailPageContent() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const databaseId = parseInt(id || '0', 10);

  const [showPassword, setShowPassword] = useState(false);
  const [activeTab, setActiveTab] = useState('overview');
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [restoreDialogBackup, setRestoreDialogBackup] = useState<Backup | null>(null);
  const [selectedTable, setSelectedTable] = useState<string>('');
  const logsEndRef = useRef<HTMLDivElement>(null);

  // Queries
  const { data: database, isLoading: dbLoading } = useQuery({
    queryKey: ['databases', 'detail', databaseId],
    queryFn: () => detailApi.getDatabase(databaseId),
    enabled: databaseId > 0,
    refetchInterval: 3000, // Refresh every 3s for real-time status
  });

  useDocumentTitle(database?.name ? ` Database - ${database.name}` : 'Database Details');

  const { data: stats, refetch: refetchStats } = useQuery({
    queryKey: ['databases', 'stats', databaseId],
    queryFn: () => detailApi.getStats(databaseId),
    enabled: databaseId > 0 && database?.status === 'running',
    refetchInterval: 5000,
  });

  const { data: inspect } = useQuery({
    queryKey: ['databases', 'inspect', databaseId],
    queryFn: () => detailApi.getInspect(databaseId),
    enabled: databaseId > 0 && database?.status === 'running',
    staleTime: 30000,
  });

  const { data: logsData, refetch: refetchLogs, isLoading: logsLoading } = useQuery({
    queryKey: ['databases', 'logs', databaseId],
    queryFn: () => detailApi.getLogs(databaseId, 500),
    enabled: databaseId > 0 && activeTab === 'logs',
    refetchInterval: activeTab === 'logs' ? 2000 : false,
  });

  // Auto-scroll logs to bottom when updated
  useEffect(() => {
    if (activeTab === 'logs' && logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logsData, activeTab]);

  const { data: backupsData, refetch: refetchBackups } = useQuery({
    queryKey: ['databases', 'backups', databaseId],
    queryFn: () => detailApi.getBackups(databaseId),
    enabled: databaseId > 0 && activeTab === 'backups',
  });

  // Explorer queries
  const { data: tablesData, isLoading: tablesLoading } = useQuery({
    queryKey: ['databases', 'tables', databaseId],
    queryFn: () => detailApi.getTables(databaseId),
    enabled: databaseId > 0 && activeTab === 'explorer' && database?.status === 'running',
  });

  const { data: schemaData, isLoading: schemaLoading } = useQuery({
    queryKey: ['databases', 'schema', databaseId, selectedTable],
    queryFn: () => detailApi.getTableSchema(databaseId, selectedTable),
    enabled: databaseId > 0 && !!selectedTable && activeTab === 'explorer' && database?.status === 'running',
  });

  const { data: tableData } = useQuery({
    queryKey: ['databases', 'tableData', databaseId, selectedTable],
    queryFn: () => detailApi.getTableData(databaseId, selectedTable, 10),
    enabled: databaseId > 0 && !!selectedTable && activeTab === 'explorer' && database?.status === 'running',
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
      navigate('/modules/databases');
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

  const backupMutation = useMutation({
    mutationFn: () => detailApi.createBackup(databaseId),
    onSuccess: () => {
      refetchBackups();
      toast.success('Backup created successfully');
    },
    onError: (err: any) => toast.error(err.response?.data?.detail || 'Failed to create backup'),
  });

  const restoreMutation = useMutation({
    mutationFn: (backupId: number) => detailApi.restoreBackup(databaseId, backupId),
    onSuccess: () => {
      setRestoreDialogBackup(null);
      toast.success('Database restored successfully');
    },
    onError: (err: any) => toast.error(err.response?.data?.detail || 'Failed to restore backup'),
  });

  const deleteBackupMutation = useMutation({
    mutationFn: (backupId: number) => detailApi.deleteBackup(databaseId, backupId),
    onSuccess: () => {
      refetchBackups();
      toast.success('Backup deleted');
    },
    onError: () => toast.error('Failed to delete backup'),
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

  const typeInfo = database ? DATABASE_TYPES[database.type] || { label: database.type, icon: '📦' } : null;
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
          <div className="flex items-center gap-3">
            <span className="text-3xl">{typeInfo?.icon}</span>
            <div>
              <h1 className="text-2xl font-bold">{database.name}</h1>
              <p className="text-muted-foreground text-sm">{typeInfo?.description}</p>
            </div>
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
              <Button variant="outline" size="sm" onClick={() => restartMutation.mutate()} disabled={restartMutation.isPending || database.status === 'restarting' || database.status === 'stopping'}>
                <RefreshCw className="mr-2 h-4 w-4" />
                Restart
              </Button>
              <Button variant="outline" size="sm" onClick={() => stopMutation.mutate()} disabled={stopMutation.isPending || database.status === 'restarting' || database.status === 'stopping'}>
                <Square className="mr-2 h-4 w-4" />
                Stop
              </Button>
            </>
          ) : database.status === 'stopped' && (
            <Button variant="outline" size="sm" onClick={() => startMutation.mutate()} disabled={startMutation.isPending || database.status === 'starting'}>
              <Play className="mr-2 h-4 w-4" />
              Start
            </Button>
          )}
          <Button variant="destructive" size="sm" onClick={() => setDeleteDialogOpen(true)}>
            <Trash2 className="mr-2 h-4 w-4" />
            Delete
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
          <TabsTrigger value="backups" className="flex items-center gap-2">
            <HardDrive className="h-4 w-4" />
            Backups
          </TabsTrigger>
          <TabsTrigger value="explorer" className="flex items-center gap-2">
            <Table className="h-4 w-4" />
            Explorer
          </TabsTrigger>
        </TabsList>

        {/* Overview Tab */}
        <TabsContent value="overview" className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            {/* Connection Info */}
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">Connection Details</CardTitle>
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
                      {database.type === 'redis' 
                        ? `redis://:${showPassword ? database.password : '********'}@${database.host}:${database.port}/0`
                        : database.type === 'mongodb'
                        ? `mongodb://${database.username}:${showPassword ? database.password : '********'}@${database.host}:${database.port}/${database.database}`
                        : `${database.type === 'postgresql' ? 'postgresql' : 'mysql'}://${database.username}:${showPassword ? database.password : '********'}@${database.host}:${database.port}/${database.database}`
                      }
                    </code>
                  </div>
                  <Button 
                    variant="outline" 
                    size="sm" 
                    className="w-full"
                    onClick={() => {
                      const connString = database.type === 'redis' 
                        ? `redis://:${database.password}@${database.host}:${database.port}/0`
                        : database.type === 'mongodb'
                        ? `mongodb://${database.username}:${database.password}@${database.host}:${database.port}/${database.database}`
                        : `${database.type === 'postgresql' ? 'postgresql' : 'mysql'}://${database.username}:${database.password}@${database.host}:${database.port}/${database.database}`;
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
              </CardHeader>
              <CardContent className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">Type</span>
                  <span className="flex items-center gap-2">
                    <span>{typeInfo?.icon}</span>
                    <span>{typeInfo?.label}</span>
                  </span>
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

            {/* Quick Stats */}
            {isRunning && stats && !stats.error && (
              <Card>
                <CardHeader>
                  <CardTitle className="text-lg flex items-center justify-between">
                    Quick Stats
                    <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => refetchStats()}>
                      <RefreshCw className="h-3 w-3" />
                    </Button>
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-muted-foreground flex items-center gap-2">
                      <Cpu className="h-4 w-4" /> CPU
                    </span>
                    <span className="font-mono">{stats.cpu_percent}</span>
                  </div>
                  <Separator />
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-muted-foreground flex items-center gap-2">
                      <MemoryStick className="h-4 w-4" /> Memory
                    </span>
                    <span className="font-mono">{stats.mem_usage}</span>
                  </div>
                  <Separator />
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-muted-foreground flex items-center gap-2">
                      <Network className="h-4 w-4" /> Network I/O
                    </span>
                    <span className="font-mono text-sm">{stats.net_io}</span>
                  </div>
                  <Separator />
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-muted-foreground flex items-center gap-2">
                      <HardDrive className="h-4 w-4" /> Block I/O
                    </span>
                    <span className="font-mono text-sm">{stats.block_io}</span>
                  </div>
                </CardContent>
              </Card>
            )}
          </div>
        </TabsContent>

        {/* Logs Tab */}
        <TabsContent value="logs" className="space-y-4">
          <Card className="w-full">
            <CardHeader>
              <CardTitle className="text-lg flex items-center justify-between">
                Database Logs
                <Button variant="outline" size="sm" onClick={() => refetchLogs()} disabled={logsLoading}>
                  {logsLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                  <span className="ml-2">Refresh</span>
                </Button>
              </CardTitle>
              <CardDescription>Last 500 lines, auto-refreshes every 2 seconds</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="overflow-hidden min-w-0 rounded-md border bg-muted">
                <ScrollArea className="max-h-[70vh] w-full">
                  <div className="p-4">
                    <pre className="text-xs text-foreground font-mono whitespace-pre-wrap break-all leading-relaxed">
                      {logsData?.logs || 'No logs available'}
                    </pre>
                    <div ref={logsEndRef} />
                  </div>
                </ScrollArea>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Backups Tab */}
        <TabsContent value="backups" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg flex items-center justify-between">
                Backups
                <Button 
                  onClick={() => backupMutation.mutate()} 
                  disabled={backupMutation.isPending || !isRunning}
                >
                  {backupMutation.isPending ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <Download className="mr-2 h-4 w-4" />
                  )}
                  Create Backup
                </Button>
              </CardTitle>
              <CardDescription>
                {isRunning ? 'Create and manage database backups' : 'Start the database to create backups'}
              </CardDescription>
            </CardHeader>
            <CardContent>
              {backupsData?.backups?.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
                  <HardDrive className="h-12 w-12 mb-4 opacity-50" />
                  <p>No backups yet</p>
                  <p className="text-sm">Create your first backup to protect your data</p>
                </div>
              ) : (
                <div className="space-y-2">
                  {backupsData?.backups?.map((backup) => (
                    <div 
                      key={backup.id}
                      className="flex items-center justify-between p-3 rounded-lg border bg-card hover:bg-accent/50 transition-colors"
                    >
                      <div className="flex items-center gap-3">
                        <HardDrive className="h-5 w-5 text-muted-foreground" />
                        <div>
                          <p className="font-medium text-sm">{backup.path.split('/').pop()}</p>
                          <div className="flex items-center gap-2 text-xs text-muted-foreground">
                            <Clock className="h-3 w-3" />
                            {formatDate(backup.created_at)}
                            <span>•</span>
                            {formatBytes(backup.size)}
                          </div>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <Button 
                          variant="outline" 
                          size="sm"
                          onClick={() => setRestoreDialogBackup(backup)}
                          disabled={!isRunning}
                        >
                          <Upload className="mr-2 h-4 w-4" />
                          Restore
                        </Button>
                        <Button 
                          variant="ghost" 
                          size="icon"
                          className="text-destructive hover:text-destructive"
                          onClick={() => deleteBackupMutation.mutate(backup.id)}
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

        {/* Explorer Tab */}
        <TabsContent value="explorer" className="space-y-4">
          {!isRunning ? (
            <Card>
              <CardContent className="flex flex-col items-center justify-center py-12 text-muted-foreground">
                <Table className="h-12 w-12 mb-4 opacity-50" />
                <p>Database is not running</p>
                <p className="text-sm">Start the database to explore tables</p>
              </CardContent>
            </Card>
          ) : (
            <div className="grid gap-4 md:grid-cols-3">
              {/* Tables List */}
              <Card className="md:col-span-1">
                <CardHeader>
                  <CardTitle className="text-lg">
                    Tables
                  </CardTitle>
                  <CardDescription>Select a table to explore</CardDescription>
                </CardHeader>
                <CardContent className="p-0">
                  <ScrollArea className="max-h-[60vh]">
                    <div className="p-4 space-y-2">
                      {database.type === 'redis' ? (
                        <div className="text-sm text-muted-foreground text-center py-8">
                          Redis uses key-value pairs.
                          <br />
                          Use a Redis client to explore data.
                        </div>
                      ) : tablesLoading ? (
                        <div className="text-sm text-muted-foreground text-center py-8">
                          <Loader2 className="h-6 w-6 animate-spin mx-auto mb-2" />
                          Loading tables...
                        </div>
                      ) : !tablesData?.tables || tablesData.tables.length === 0 ? (
                        <div className="text-sm text-muted-foreground text-center py-8">
                          No tables found
                        </div>
                      ) : (
                        <div className="space-y-1">
                          {tablesData.tables.map((tableName) => (
                            <Button
                              key={tableName}
                              variant={selectedTable === tableName ? 'secondary' : 'ghost'}
                              className="w-full justify-start"
                              onClick={() => setSelectedTable(tableName)}
                            >
                              <Table className="h-4 w-4 mr-2" />
                              {tableName}
                            </Button>
                          ))}
                        </div>
                      )}
                    </div>
                  </ScrollArea>
                </CardContent>
              </Card>

              {/* Table Details & Data */}
              <Card className="md:col-span-2">
                <CardHeader>
                  <CardTitle className="text-lg">
                    {selectedTable ? (
                      <>
                        Table: {selectedTable}
                      </>
                    ) : (
                      <>
                        Explorer
                      </>
                    )}
                  </CardTitle>
                  <CardDescription>
                    {selectedTable ? `Viewing structure and data for ${selectedTable}` : 'Select a table from the list'}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  {!selectedTable ? (
                    <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
                      <Search className="h-12 w-12 mb-4 opacity-50" />
                      <p>No table selected</p>
                      <p className="text-sm">Select a table from the list to view its structure and data</p>
                    </div>
                  ) : (
                    <div className="space-y-4">
                      {/* Table Schema */}
                      <div>
                        <h4 className="text-sm font-semibold mb-2">
                          Schema
                        </h4>
                        <ScrollArea className="max-h-[25vh] rounded border">
                          <div className="p-3 space-y-2">
                            {schemaLoading ? (
                              <div className="text-sm text-muted-foreground text-center py-4">
                                <Loader2 className="h-6 w-6 animate-spin mx-auto mb-2" />
                                Loading schema...
                              </div>
                            ) : !schemaData?.schema || schemaData.schema.length === 0 ? (
                              <div className="text-sm text-muted-foreground text-center py-4">
                                No schema information available
                              </div>
                            ) : (
                              schemaData.schema.map((column, idx) => (
                                <div key={idx}>
                                  {idx > 0 && <Separator />}
                                  <div className="flex items-center justify-between text-sm">
                                    <span className="font-mono">{column.name}</span>
                                    <Badge variant="outline" className="text-xs">{column.type}</Badge>
                                  </div>
                                </div>
                              ))
                            )}
                          </div>
                        </ScrollArea>
                      </div>

                      {/* Sample Data */}
                      <div>
                        <h4 className="text-sm font-semibold mb-2">
                          Sample Data (10 rows)
                        </h4>
                        <ScrollArea className="max-h-[25vh] rounded border">
                          <div className="p-3">
                            {!tableData?.data || tableData.data.rows.length === 0 ? (
                              <div className="text-sm text-muted-foreground text-center py-4">
                                {!tableData ? (
                                  <>
                                    <Loader2 className="h-6 w-6 animate-spin mx-auto mb-2" />
                                    <p>Loading data...</p>
                                  </>
                                ) : (
                                  <>
                                    <Database className="h-8 w-8 mx-auto mb-2 opacity-50" />
                                    <p>No data in table</p>
                                  </>
                                )}
                              </div>
                            ) : (
                              <div className="overflow-x-auto">
                                <table className="w-full text-sm">
                                  <thead>
                                    <tr className="border-b">
                                      {tableData.data.columns.map((col, idx) => (
                                        <th key={idx} className="text-left p-2 font-semibold whitespace-nowrap">
                                          {col}
                                        </th>
                                      ))}
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {tableData.data.rows.map((row, rowIdx) => (
                                      <tr key={rowIdx} className="border-b hover:bg-muted/50">
                                        {row.map((cell, cellIdx) => (
                                          <td key={cellIdx} className="p-2 max-w-xs truncate">
                                            {cell}
                                          </td>
                                        ))}
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              </div>
                            )}
                          </div>
                        </ScrollArea>
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>
          )}
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
      <AlertDialog open={!!restoreDialogBackup} onOpenChange={() => setRestoreDialogBackup(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Restore from Backup</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to restore the database from this backup? This will overwrite the current data with the backup data.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => restoreDialogBackup && restoreMutation.mutate(restoreDialogBackup.id)}
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
