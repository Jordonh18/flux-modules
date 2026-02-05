/**
 * Databases Module - Database Page
 *
 * Full-featured database management page for Flux.
 * Supports creating containerized databases via Podman.
 */

import { memo, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
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
  Loader2,
  MoreHorizontal,
  Play,
  Plus,
  Square,
  Trash2,
  Eye,
  EyeOff,
} from 'lucide-react';
import { useDocumentTitle } from '@/hooks/use-document-title';
import { toast } from 'sonner';

// Types
interface PodmanStatus {
  installed: boolean;
  version: string | null;
  message: string;
}

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
}

interface CreateDatabaseRequest {
  type: string;
  name?: string;
  database_name: string;
}

// Database type options
const DATABASE_TYPES = [
  { value: 'postgresql', label: 'PostgreSQL', icon: '🐘', description: 'Advanced open-source relational database' },
  { value: 'mysql', label: 'MySQL', icon: '🐬', description: 'World\'s most popular open source database' },
  { value: 'mariadb', label: 'MariaDB', icon: '🦭', description: 'Enhanced MySQL-compatible database' },
  { value: 'mongodb', label: 'MongoDB', icon: '🍃', description: 'Document-oriented NoSQL database' },
  { value: 'redis', label: 'Redis', icon: '🔴', description: 'In-memory data structure store' },
];

// API functions
const databasesApi = {
  getPodmanStatus: () => api.get<PodmanStatus>('/modules/databases/podman/status').then(r => r.data),
  installPodman: () => api.post<PodmanStatus>('/modules/databases/podman/install').then(r => r.data),
  getDatabases: () => api.get<DatabaseInfo[]>('/modules/databases/databases').then(r => r.data),
  createDatabase: (data: CreateDatabaseRequest) => 
    api.post('/modules/databases/databases', data, { timeout: 360000 }).then(r => r.data), // 6 min timeout for image pulls
  startDatabase: (id: number) => api.post(`/modules/databases/databases/${id}/start`).then(r => r.data),
  stopDatabase: (id: number) => api.post(`/modules/databases/databases/${id}/stop`).then(r => r.data),
  deleteDatabase: (id: number) => api.delete(`/modules/databases/databases/${id}`).then(r => r.data),
};

function DatabasesPageContent() {
  useDocumentTitle('Databases');
  const queryClient = useQueryClient();
  
  // Modal states
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [showPassword, setShowPassword] = useState<number | null>(null);
  
  // Create form state
  const [createForm, setCreateForm] = useState({
    type: 'postgresql',
    name: '',
    database_name: 'app',
  });

  // Queries
  const { data: podmanStatus, isLoading: podmanLoading } = useQuery({
    queryKey: ['databases', 'podman-status'],
    queryFn: databasesApi.getPodmanStatus,
    staleTime: 30000,
  });

  const { data: databases, isLoading: databasesLoading } = useQuery({
    queryKey: ['databases', 'list'],
    queryFn: databasesApi.getDatabases,
    enabled: podmanStatus?.installed === true,
    refetchInterval: 10000, // Refresh every 10s to update container status
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
    onMutate: () => {
      // Close modal immediately and reset form
      setIsCreateModalOpen(false);
      setCreateForm({ type: 'postgresql', name: '', database_name: 'app' });
      
      toast.info('Creating database... This may take a few minutes if the image needs to be downloaded.', {
        duration: 10000,
      });
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['databases', 'list'] });
      toast.success(data.message || 'Database created successfully');
    },
    onError: (err: any) => {
      toast.error(err.response?.data?.detail || err.message || 'Failed to create database');
      queryClient.invalidateQueries({ queryKey: ['databases', 'list'] });
    },
  });

  const startDatabaseMutation = useMutation({
    mutationFn: databasesApi.startDatabase,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['databases', 'list'] });
      toast.success('Database started');
    },
    onError: () => toast.error('Failed to start database'),
  });

  const stopDatabaseMutation = useMutation({
    mutationFn: databasesApi.stopDatabase,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['databases', 'list'] });
      toast.success('Database stopped');
    },
    onError: () => toast.error('Failed to stop database'),
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
  const handleCreateDatabase = (e: React.FormEvent) => {
    e.preventDefault();
    createDatabaseMutation.mutate({
      type: createForm.type,
      name: createForm.name || undefined,
      database_name: createForm.database_name,
    });
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

  const getStatusBadgeVariant = (status: string) => {
    switch (status.toLowerCase()) {
      case 'running': return 'default';
      case 'creating': return 'default';
      case 'error': return 'destructive';
      case 'stopped':
      case 'exited': return 'secondary';
      default: return 'outline';
    }
  };

  const getDatabaseTypeInfo = (type: string) => {
    return DATABASE_TYPES.find(t => t.value === type) || { value: type, label: type, icon: '📦' };
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
          <p className="text-muted-foreground">Manage containerized database instances</p>
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
                  Podman is required to run database containers. Install it to get started.
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
                    const typeInfo = getDatabaseTypeInfo(db.type);
                    return (
                      <TableRow key={db.id}>
                        <TableCell className="px-4">
                          <div>
                            <p className="font-medium">{db.name}</p>
                            <p className="text-xs text-muted-foreground font-mono">{db.container_id}</p>
                          </div>
                        </TableCell>
                        <TableCell className="px-4">
                          <div className="flex items-center gap-2">
                            <span>{typeInfo.icon}</span>
                            <span>{typeInfo.label}</span>
                          </div>
                        </TableCell>
                        <TableCell className="px-4">
                          <Badge 
                            variant={getStatusBadgeVariant(db.status)} 
                            className={cn(
                              "capitalize flex items-center gap-1 w-fit",
                              db.status === 'running' && "bg-green-500/10 text-green-700 dark:text-green-400 border-green-500/20"
                            )}
                          >
                            {db.status === 'creating' && <Loader2 className="h-3 w-3 animate-spin" />}
                            {db.status}
                          </Badge>
                        </TableCell>
                        <TableCell className="px-4">
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
                        <TableCell className="px-4">
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
                        <TableCell className="px-4 text-right">
                          <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                              <Button variant="ghost" size="icon">
                                <MoreHorizontal className="h-4 w-4" />
                              </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end">
                              {db.status === 'running' ? (
                                <DropdownMenuItem
                                  onClick={() => stopDatabaseMutation.mutate(db.id)}
                                  disabled={stopDatabaseMutation.isPending}
                                >
                                  <Square className="mr-2 h-4 w-4" />
                                  Stop
                                </DropdownMenuItem>
                              ) : (
                                <DropdownMenuItem
                                  onClick={() => startDatabaseMutation.mutate(db.id)}
                                  disabled={startDatabaseMutation.isPending}
                                >
                                  <Play className="mr-2 h-4 w-4" />
                                  Start
                                </DropdownMenuItem>
                              )}
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
      <Dialog open={isCreateModalOpen} onOpenChange={setIsCreateModalOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create Database</DialogTitle>
            <DialogDescription>
              Create a new containerized database instance
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={handleCreateDatabase} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="type">Database Type</Label>
              <Select
                value={createForm.type}
                onValueChange={(value) => setCreateForm({ ...createForm, type: value })}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select database type" />
                </SelectTrigger>
                <SelectContent>
                  {DATABASE_TYPES.map((type) => (
                    <SelectItem key={type.value} value={type.value}>
                      <div className="flex items-center gap-2">
                        <span>{type.icon}</span>
                        <span>{type.label}</span>
                      </div>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">
                {DATABASE_TYPES.find(t => t.value === createForm.type)?.description}
              </p>
            </div>

            <div className="space-y-2">
              <Label htmlFor="name">Container Name (optional)</Label>
              <Input
                id="name"
                placeholder="e.g., my-postgres"
                value={createForm.name}
                onChange={(e) => setCreateForm({ ...createForm, name: e.target.value })}
              />
              <p className="text-xs text-muted-foreground">
                Leave blank to auto-generate a name
              </p>
            </div>

            <div className="space-y-2">
              <Label htmlFor="database_name">Database Name</Label>
              <Input
                id="database_name"
                placeholder="app"
                value={createForm.database_name}
                onChange={(e) => setCreateForm({ ...createForm, database_name: e.target.value })}
                required
              />
            </div>

            <div className="rounded-lg bg-muted p-3 text-sm">
              <p className="font-medium mb-1">Auto-configured:</p>
              <ul className="text-muted-foreground space-y-1">
                <li>• Secure random username (non-root)</li>
                <li>• Strong random password</li>
                <li>• Available port on host</li>
              </ul>
            </div>

            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => setIsCreateModalOpen(false)}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={createDatabaseMutation.isPending}>
                {createDatabaseMutation.isPending && (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                )}
                Create
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// Memoize the entire page component to prevent re-renders
const DatabasesPage = memo(DatabasesPageContent);
export default DatabasesPage;
