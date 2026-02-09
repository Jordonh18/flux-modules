/**
 * Databases Module - Database Page
 *
 * Full-featured database management page for Flux.
 * Supports creating managed PostgreSQL, MySQL, MariaDB, MongoDB, and Redis databases.
 */

import { memo, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { api } from '@/lib/api';
import { cn } from '@/lib/utils';
import { Card, CardContent } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  AlertCircle,
  Copy,
  Database,
  Download,
  ExternalLink,
  Loader2,
  MoreHorizontal,
  Play,
  Plus,
  RefreshCw,
  Square,
  Trash2,
  Eye,
  EyeOff,
} from 'lucide-react';
import { useDocumentTitle } from '@/hooks/use-document-title';
import { toast } from 'sonner';
import { CreateDatabaseDialog } from '../components/CreateDatabaseDialog';

// Types
interface PodmanStatus {
  installed: boolean;
  version: string | null;
  message: string;
}

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
}

interface CreateDatabaseRequest {
  engine: string;
  name?: string;
  database_name: string;
  sku?: string;
  memory_limit_mb?: number;
  cpu_limit?: number;
  storage_limit_gb?: number;
  external_access?: boolean;
  tls_enabled?: boolean;
  tls_cert?: string;
  tls_key?: string;
}

// API functions
const databasesApi = {
  getPodmanStatus: () => api.get<PodmanStatus>('/modules/databases/podman/status').then(r => r.data),
  installPodman: () => api.post<PodmanStatus>('/modules/databases/podman/install').then(r => r.data),
  getEngines: () => api.get<DatabaseEngine[]>('/modules/databases/engines').then(r => r.data),
  getDatabases: () => api.get<DatabaseInfo[]>('/modules/databases/databases').then(r => r.data),
  createDatabase: (data: CreateDatabaseRequest) => 
    api.post('/modules/databases/databases', data, { timeout: 360000 }).then(r => r.data), // 6 min timeout for image pulls
  startDatabase: (id: number) => api.post(`/modules/databases/databases/${id}/start`).then(r => r.data),
  stopDatabase: (id: number) => api.post(`/modules/databases/databases/${id}/stop`).then(r => r.data),
  restartDatabase: (id: number) => api.post(`/modules/databases/databases/${id}/restart`).then(r => r.data),
  deleteDatabase: (id: number) => api.delete(`/modules/databases/databases/${id}`).then(r => r.data),
};

function DatabasesPageContent() {
  useDocumentTitle('Databases');
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  
  // Modal states
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [showPassword, setShowPassword] = useState<number | null>(null);

  // Queries
  const { data: podmanStatus, isLoading: podmanLoading } = useQuery({
    queryKey: ['databases', 'podman-status'],
    queryFn: databasesApi.getPodmanStatus,
    staleTime: 30000,
  });

  const { data: engines = [], isLoading: enginesLoading } = useQuery({
    queryKey: ['databases', 'engines'],
    queryFn: databasesApi.getEngines,
    staleTime: 300000, // Cache for 5 minutes
  });

  const { data: databases, isLoading: databasesLoading } = useQuery({
    queryKey: ['databases', 'list'],
    queryFn: databasesApi.getDatabases,
    enabled: podmanStatus?.installed === true,
    refetchInterval: 3000, // Refresh every 3s to update status
  });

  // Mutations
  const installPodmanMutation = useMutation({
    mutationFn: databasesApi.installPodman,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['databases', 'podman-status'] });
      toast.success('Podman installed successfully');
    },
    onError: (err: any) => {
      toast.error(err.response?.data?.detail || 'Failed to install Podman');
    },
  });

  const createDatabaseMutation = useMutation({
    mutationFn: databasesApi.createDatabase,
    onMutate: async (newDatabase) => {
      // Close modal immediately
      setIsCreateModalOpen(false);
      
      // Cancel outgoing refetches
      await queryClient.cancelQueries({ queryKey: ['databases', 'list'] });
      
      // Snapshot previous value
      const previousDatabases = queryClient.getQueryData<DatabaseInfo[]>(['databases', 'list']);
      
      // Optimistically add the database with "creating" status
      queryClient.setQueryData<DatabaseInfo[]>(['databases', 'list'], (old) => {
        if (!old) return old;
        
        // Create temporary database entry
        const tempDatabase: DatabaseInfo = {
          id: Date.now(), // Temporary ID
          name: newDatabase.name || `${newDatabase.engine}-db`,
          engine: newDatabase.engine,
          status: 'creating',
          host: 'localhost',
          port: 0,
          database: newDatabase.database_name,
          username: 'creating...',
          password: '',
          created_at: new Date().toISOString(),
        };
        
        return [tempDatabase, ...old];
      });
      
      // Return context for rollback
      return { previousDatabases };
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['databases', 'list'] });
    },
    onError: (err: any, _variables, context) => {
      // Rollback on error
      if (context?.previousDatabases) {
        queryClient.setQueryData(['databases', 'list'], context.previousDatabases);
      }
      toast.error(err.response?.data?.detail || err.message || 'Failed to create database');
    },
  });

  const startDatabaseMutation = useMutation({
    mutationFn: databasesApi.startDatabase,
    onMutate: async (databaseId) => {
      await queryClient.cancelQueries({ queryKey: ['databases', 'list'] });
      const previousDatabases = queryClient.getQueryData<DatabaseInfo[]>(['databases', 'list']);
      
      queryClient.setQueryData<DatabaseInfo[]>(['databases', 'list'], (old) => {
        if (!old) return old;
        return old.map(db => 
          db.id === databaseId ? { ...db, status: 'starting' } : db
        );
      });
      
      toast.info('Starting database...');
      return { previousDatabases };
    },
    onError: (_err, _variables, context) => {
      if (context?.previousDatabases) {
        queryClient.setQueryData(['databases', 'list'], context.previousDatabases);
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

  const stopDatabaseMutation = useMutation({
    mutationFn: databasesApi.stopDatabase,
    onMutate: async (databaseId) => {
      await queryClient.cancelQueries({ queryKey: ['databases', 'list'] });
      const previousDatabases = queryClient.getQueryData<DatabaseInfo[]>(['databases', 'list']);
      
      queryClient.setQueryData<DatabaseInfo[]>(['databases', 'list'], (old) => {
        if (!old) return old;
        return old.map(db => 
          db.id === databaseId ? { ...db, status: 'stopping' } : db
        );
      });
      
      toast.info('Stopping database...');
      return { previousDatabases };
    },
    onError: (_err, _variables, context) => {
      if (context?.previousDatabases) {
        queryClient.setQueryData(['databases', 'list'], context.previousDatabases);
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

  const restartDatabaseMutation = useMutation({
    mutationFn: databasesApi.restartDatabase,
    onMutate: async (databaseId) => {
      // Cancel outgoing refetches
      await queryClient.cancelQueries({ queryKey: ['databases', 'list'] });
      
      // Snapshot previous value
      const previousDatabases = queryClient.getQueryData<DatabaseInfo[]>(['databases', 'list']);
      
      // Optimistically update to "restarting" status
      queryClient.setQueryData<DatabaseInfo[]>(['databases', 'list'], (old) => {
        if (!old) return old;
        return old.map(db => 
          db.id === databaseId ? { ...db, status: 'restarting' } : db
        );
      });
      
      toast.info('Restarting database...');
      
      // Return context for rollback
      return { previousDatabases };
    },
    onError: (_err, _variables, context) => {
      // Rollback on error
      if (context?.previousDatabases) {
        queryClient.setQueryData(['databases', 'list'], context.previousDatabases);
      }
      toast.error('Failed to restart database');
    },
    onSuccess: () => {
      toast.success('Database restarted');
    },
    onSettled: () => {
      // Refetch to ensure we have accurate data
      queryClient.invalidateQueries({ queryKey: ['databases'] });
    },
  });

  const deleteDatabaseMutation = useMutation({
    mutationFn: databasesApi.deleteDatabase,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['databases', 'list'] });
      toast.success('Database deleted');
    },
    onError: () => toast.error('Failed to delete database'),
  });

  // Handlers
  const handleCreateSubmit = (data: CreateDatabaseRequest) => {
    createDatabaseMutation.mutate(data);
  };

  const handleDeleteDatabase = (db: DatabaseInfo) => {
    if (confirm(`Are you sure you want to delete "${db.name}"? This will stop the container and remove all data.`)) {
      deleteDatabaseMutation.mutate(db.id);
    }
  };

  const copyToClipboard = (text: string, label: string) => {
    navigator.clipboard.writeText(text);
    toast.success(`${label} copied to clipboard`);
  };

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

  const getDatabaseTypeInfo = (engineName: string) => {
    const engine = engines.find(e => e.engine === engineName);
    return engine ? {
      value: engine.engine,
      label: engine.display_name,
      icon: getCategoryIcon(engine.category),
      description: engine.description
    } : { value: engineName, label: engineName, icon: '📦', description: '' };
  };

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

  // Loading state
  if (podmanLoading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold">Databases</h1>
          <p className="text-muted-foreground">Manage database instances</p>
        </div>
        {podmanStatus?.installed && (
          <Button 
            onClick={() => setIsCreateModalOpen(true)}
            disabled={createDatabaseMutation.isPending}
          >
            {createDatabaseMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Create Database
          </Button>
        )}
      </div>

      {/* Podman Status Alert */}
      {!podmanStatus?.installed && (
        <Card className="border-amber-500/50 bg-amber-500/10">
          <CardContent className="flex items-center justify-between p-4">
            <div className="flex items-center gap-3">
              <AlertCircle className="h-5 w-5 text-amber-500" />
              <div>
                <p className="font-medium">Podman Required</p>
                <p className="text-sm text-muted-foreground">
                  Podman is required to run databases. Install it to get started.
                </p>
              </div>
            </div>
            <Button
              onClick={() => installPodmanMutation.mutate()}
              disabled={installPodmanMutation.isPending}
            >
              {installPodmanMutation.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Download className="mr-2 h-4 w-4" />
              )}
              Install Podman
            </Button>
          </CardContent>
        </Card>
      )}


      {/* Databases Table */}
      {podmanStatus?.installed && (
        <Card className="gap-0 py-0">
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="px-4">Database</TableHead>
                  <TableHead className="px-4">Type</TableHead>
                  <TableHead className="px-4">Status</TableHead>
                  <TableHead className="px-4">Connection</TableHead>
                  <TableHead className="px-4">Credentials</TableHead>
                  <TableHead className="px-4 text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {databasesLoading ? (
                  <TableRow>
                    <TableCell className="px-4 text-center" colSpan={6}>
                      <Loader2 className="mx-auto h-5 w-5 animate-spin" />
                    </TableCell>
                  </TableRow>
                ) : databases?.length === 0 ? (
                  <TableRow>
                    <TableCell className="px-4 text-center text-muted-foreground" colSpan={6}>
                      <div className="py-8">
                        <Database className="mx-auto h-10 w-10 text-muted-foreground/50 mb-2" />
                        <p>No databases yet</p>
                        <p className="text-sm">Click "Create Database" to get started</p>
                      </div>
                    </TableCell>
                  </TableRow>
                ) : (
                  databases?.map((db) => {
                    const typeInfo = getDatabaseTypeInfo(db.engine);
                    return (
                      <TableRow 
                        key={db.id} 
                        className="cursor-pointer hover:bg-muted/50"
                        onClick={() => navigate(`/databases/${db.id}`)}
                      >
                        <TableCell className="px-4">
                          <div>
                            <p className="font-medium">{db.name}</p>
                            <p className="text-xs text-muted-foreground">Created {new Date(db.created_at).toLocaleDateString()}</p>
                          </div>
                        </TableCell>
                        <TableCell className="px-4">
                          <div className="flex items-center gap-2">
                            <span>{typeInfo.icon}</span>
                            <span>{typeInfo.label}</span>
                          </div>
                        </TableCell>
                        <TableCell className="px-4">
                          <span
                            className={cn(
                              "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium capitalize border",
                              getStatusBadgeClass(db.status)
                            )}
                          >
                            {(db.status === 'creating' || db.status === 'restarting' || db.status === 'starting' || db.status === 'stopping') && <Loader2 className="h-3 w-3 animate-spin" />}
                            {db.status}
                          </span>
                        </TableCell>
                        <TableCell className="px-4" onClick={(e) => e.stopPropagation()}>
                          <div className="flex items-center gap-2">
                            <code className="text-xs bg-muted px-2 py-1 rounded">
                              {db.host}:{db.port}/{db.database}
                            </code>
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-6 w-6"
                              onClick={() => copyToClipboard(`${db.host}:${db.port}`, 'Connection')}
                            >
                              <Copy className="h-3 w-3" />
                            </Button>
                          </div>
                        </TableCell>
                        <TableCell className="px-4" onClick={(e) => e.stopPropagation()}>
                          <div className="flex items-center gap-2">
                            <code className="text-xs bg-muted px-2 py-1 rounded">
                              {db.username}:{showPassword === db.id ? db.password : '••••••••'}
                            </code>
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-6 w-6"
                              onClick={() => setShowPassword(showPassword === db.id ? null : db.id)}
                            >
                              {showPassword === db.id ? <EyeOff className="h-3 w-3" /> : <Eye className="h-3 w-3" />}
                            </Button>
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-6 w-6"
                              onClick={() => copyToClipboard(`${db.username}:${db.password}`, 'Credentials')}
                            >
                              <Copy className="h-3 w-3" />
                            </Button>
                          </div>
                        </TableCell>
                        <TableCell className="px-4 text-right" onClick={(e) => e.stopPropagation()}>
                          <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                              <Button variant="ghost" size="icon">
                                <MoreHorizontal className="h-4 w-4" />
                              </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end">
                              <DropdownMenuItem
                                onClick={() => navigate(`/databases/${db.id}`)}
                              >
                                <ExternalLink className="mr-2 h-4 w-4" />
                                Open
                              </DropdownMenuItem>
                              <DropdownMenuSeparator />
                              {(db.status === 'running' || db.status === 'restarting') ? (
                                <>
                                  <DropdownMenuItem
                                    onClick={() => restartDatabaseMutation.mutate(db.id)}
                                    disabled={restartDatabaseMutation.isPending || db.status === 'restarting' || db.status === 'stopping'}
                                  >
                                    <RefreshCw className="mr-2 h-4 w-4" />
                                    Restart
                                  </DropdownMenuItem>
                                  <DropdownMenuItem
                                    onClick={() => stopDatabaseMutation.mutate(db.id)}
                                    disabled={stopDatabaseMutation.isPending || db.status === 'restarting' || db.status === 'stopping'}
                                  >
                                    <Square className="mr-2 h-4 w-4" />
                                    Stop
                                  </DropdownMenuItem>
                                </>
                              ) : db.status === 'stopped' ? (
                                <DropdownMenuItem
                                  onClick={() => startDatabaseMutation.mutate(db.id)}
                                  disabled={startDatabaseMutation.isPending || db.status === 'starting'}
                                >
                                  <Play className="mr-2 h-4 w-4" />
                                  Start
                                </DropdownMenuItem>
                              ) : null}
                              <DropdownMenuSeparator />
                              <DropdownMenuItem
                                onClick={() => handleDeleteDatabase(db)}
                                className="text-destructive focus:text-destructive"
                              >
                                <Trash2 className="mr-2 h-4 w-4" />
                                Delete
                              </DropdownMenuItem>
                            </DropdownMenuContent>
                          </DropdownMenu>
                        </TableCell>
                      </TableRow>
                    );
                  })
                )}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {/* Create Database Modal */}
      <CreateDatabaseDialog 
        open={isCreateModalOpen} 
        onOpenChange={setIsCreateModalOpen}
        onSubmit={handleCreateSubmit}
        isSubmitting={createDatabaseMutation.isPending}
        engines={engines}
      />
    </div>
  );
}

// Memoize the entire page component to prevent re-renders
const DatabasesPage = memo(DatabasesPageContent);
export default DatabasesPage;
