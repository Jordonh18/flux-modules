/**
 * Database Detail Page
 * 
 * Azure-level database management with tabs for:
 * - Overview: Connection info, stats, and status
 * - Logs: Real-time container logs
 * - Backups: Backup/restore management
 * - Settings: Container configuration
 */

import { memo, useState } from 'react';
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
  BarChart3,
  Square,
  Trash2,
  Eye,
  EyeOff,
  Upload,
  Clock,
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
  container_id: string;
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
const DATABASE_TYPES: Record<string, { label: string; icon: string }> = {
  postgresql: { label: 'PostgreSQL', icon: '🐘' },
  mysql: { label: 'MySQL', icon: '🐬' },
  mariadb: { label: 'MariaDB', icon: '🦭' },
  mongodb: { label: 'MongoDB', icon: '🍃' },
  redis: { label: 'Redis', icon: '🔴' },
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

  // Queries
  const { data: database, isLoading: dbLoading } = useQuery({
    queryKey: ['databases', 'detail', databaseId],
    queryFn: () => detailApi.getDatabase(databaseId),
    enabled: databaseId > 0,
    refetchInterval: 10000,
  });

  useDocumentTitle(database?.name ? `${database.name} - Databases` : 'Database Details');

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
    refetchInterval: activeTab === 'logs' ? 5000 : false,
  });

  const { data: backupsData, refetch: refetchBackups } = useQuery({
    queryKey: ['databases', 'backups', databaseId],
    queryFn: () => detailApi.getBackups(databaseId),
    enabled: databaseId > 0 && activeTab === 'backups',
  });

  // Mutations
  const startMutation = useMutation({
    mutationFn: () => detailApi.startDatabase(databaseId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['databases'] });
      toast.success('Database started');
    },
    onError: () => toast.error('Failed to start database'),
  });

  const stopMutation = useMutation({
    mutationFn: () => detailApi.stopDatabase(databaseId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['databases'] });
      toast.success('Database stopped');
    },
    onError: () => toast.error('Failed to stop database'),
  });

  const deleteMutation = useMutation({
    mutationFn: () => detailApi.deleteDatabase(databaseId),
    onSuccess: () => {
      toast.success('Database deleted');
      navigate('/modules/databases');
    },
    onError: () => toast.error('Failed to delete database'),
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
          <Button variant="ghost" size="icon" onClick={() => navigate('/databases')}>
            <ArrowLeft className="h-5 w-5" />
          </Button>
          <div className="flex items-center gap-3">
            <span className="text-3xl">{typeInfo?.icon}</span>
            <div>
              <h1 className="text-2xl font-bold">{database.name}</h1>
              <p className="text-muted-foreground text-sm font-mono">{database.container_id || 'Creating...'}</p>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Badge 
            variant={isRunning ? 'default' : 'secondary'}
            className={cn(
              "capitalize",
              isRunning && "bg-green-500/10 text-green-700 dark:text-green-400 border-green-500/20"
            )}
          >
            {database.status === 'creating' && <Loader2 className="mr-1 h-3 w-3 animate-spin" />}
            {database.status}
          </Badge>
          {isRunning ? (
            <Button variant="outline" size="sm" onClick={() => stopMutation.mutate()} disabled={stopMutation.isPending}>
              <Square className="mr-2 h-4 w-4" />
              Stop
            </Button>
          ) : database.status !== 'creating' && (
            <Button variant="outline" size="sm" onClick={() => startMutation.mutate()} disabled={startMutation.isPending}>
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
          <TabsTrigger value="stats" className="flex items-center gap-2">
            <BarChart3 className="h-4 w-4" />
            Stats
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
                      <code className="text-sm bg-muted px-2 py-1 rounded">
                        {showPassword ? database.password : '••••••••••••'}
                      </code>
                      <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => setShowPassword(!showPassword)}>
                        {showPassword ? <EyeOff className="h-3 w-3" /> : <Eye className="h-3 w-3" />}
                      </Button>
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
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center justify-between">
                Container Logs
                <Button variant="outline" size="sm" onClick={() => refetchLogs()} disabled={logsLoading}>
                  {logsLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                  <span className="ml-2">Refresh</span>
                </Button>
              </CardTitle>
              <CardDescription>Last 500 lines, auto-refreshes every 5 seconds</CardDescription>
            </CardHeader>
            <CardContent>
              <ScrollArea className="h-[500px] w-full rounded border bg-black p-4">
                <pre className="text-xs text-green-400 font-mono whitespace-pre-wrap">
                  {logsData?.logs || 'No logs available'}
                </pre>
              </ScrollArea>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Backups Tab */}
        <TabsContent value="backups" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center justify-between">
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

        {/* Stats Tab */}
        <TabsContent value="stats" className="space-y-4">
          {!isRunning ? (
            <Card>
              <CardContent className="flex flex-col items-center justify-center py-12 text-muted-foreground">
                <BarChart3 className="h-12 w-12 mb-4 opacity-50" />
                <p>Database is not running</p>
                <p className="text-sm">Start the database to view stats</p>
              </CardContent>
            </Card>
          ) : (
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium flex items-center gap-2">
                    <Cpu className="h-4 w-4" />
                    CPU Usage
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-2xl font-bold">{stats?.cpu_percent || '—'}</p>
                </CardContent>
              </Card>
              
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium flex items-center gap-2">
                    <MemoryStick className="h-4 w-4" />
                    Memory
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-2xl font-bold">{stats?.mem_percent || '—'}</p>
                  <p className="text-xs text-muted-foreground">{stats?.mem_usage || ''}</p>
                </CardContent>
              </Card>
              
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium flex items-center gap-2">
                    <Network className="h-4 w-4" />
                    Network I/O
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-lg font-bold">{stats?.net_io || '—'}</p>
                </CardContent>
              </Card>
              
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium flex items-center gap-2">
                    <HardDrive className="h-4 w-4" />
                    Block I/O
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-lg font-bold">{stats?.block_io || '—'}</p>
                </CardContent>
              </Card>
            </div>
          )}

          {/* Container Details */}
          {isRunning && inspect?.container && (
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">Container Details</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">Image</span>
                  <code className="text-sm bg-muted px-2 py-1 rounded">{inspect.container.image}</code>
                </div>
                <Separator />
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">Container ID</span>
                  <code className="text-sm bg-muted px-2 py-1 rounded">{inspect.container.id}</code>
                </div>
                {inspect.container.network?.ip_address && (
                  <>
                    <Separator />
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-muted-foreground">Internal IP</span>
                      <code className="text-sm bg-muted px-2 py-1 rounded">{inspect.container.network.ip_address}</code>
                    </div>
                  </>
                )}
                <Separator />
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">Processes</span>
                  <span>{stats?.pids || '—'}</span>
                </div>
              </CardContent>
            </Card>
          )}
        </TabsContent>
      </Tabs>

      {/* Delete Confirmation Dialog */}
      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Database</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete "{database.name}"? This will stop the container and permanently delete all data. This action cannot be undone.
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
