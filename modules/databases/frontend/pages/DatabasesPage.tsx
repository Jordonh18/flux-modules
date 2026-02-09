import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { api } from '@/lib/api';
import { useDocumentTitle } from '@/hooks/use-document-title';
import { toast } from 'sonner';

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert';
import { Skeleton } from '@/components/ui/skeleton';
import {
  MoreHorizontal,
  Plus,
  Search,
  RefreshCw,
  Power,
  RotateCw,
  Trash2,
  Database as DatabaseIcon,
  AlertTriangle,
  Server,
  Play
} from 'lucide-react';

import { DatabaseInstance, EngineInfo, ENGINE_ICONS } from '../types/database';
import { HealthBadge } from '../components/HealthBadge';

export default function DatabasesPage() {
  useDocumentTitle('Databases');
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchTerm, setSearchTerm] = useState('');
  const [engineFilter, setEngineFilter] = useState<string>('all');

  // --- Queries ---

  const { data: podmanStatus, isLoading: isPodmanLoading } = useQuery({
    queryKey: ['podman-status'],
    queryFn: async () => {
      try {
        const res = await api.get('/modules/databases/podman/status');
        return res.data;
      } catch (err) {
        return { installed: false, running: false, version: '' };
      }
    },
  });

  const { data: databases, isLoading: isDatabasesLoading } = useQuery<DatabaseInstance[]>({
    queryKey: ['databases'],
    queryFn: async () => {
      const res = await api.get('/modules/databases/databases');
      return res.data;
    },
    refetchInterval: (query) => {
      // Poll if any database is creating or stopping
      const isTransitional = query.state.data?.some((db) => 
        ['creating', 'stopping', 'starting'].includes(db.status)
      );
      return isTransitional ? 2000 : 10000;
    },
  });

  const { data: engines } = useQuery<EngineInfo[]>({
    queryKey: ['database-engines'],
    queryFn: async () => {
      const res = await api.get('/modules/databases/engines');
      return res.data;
    },
  });

  // --- Mutations ---

  const startMutation = useMutation({
    mutationFn: (id: number) => api.post(`/modules/databases/databases/${id}/start`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['databases'] });
      toast.success('Database starting...');
    },
    onError: (err: any) => toast.error(err.response?.data?.detail || 'Failed to start database'),
  });

  const stopMutation = useMutation({
    mutationFn: (id: number) => api.post(`/modules/databases/databases/${id}/stop`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['databases'] });
      toast.success('Database stopping...');
    },
    onError: (err: any) => toast.error(err.response?.data?.detail || 'Failed to stop database'),
  });

  const restartMutation = useMutation({
    mutationFn: (id: number) => api.post(`/modules/databases/databases/${id}/restart`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['databases'] });
      toast.success('Database restarting...');
    },
    onError: (err: any) => toast.error(err.response?.data?.detail || 'Failed to restart database'),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => api.delete(`/modules/databases/databases/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['databases'] });
      toast.success('Database deleted');
    },
    onError: (err: any) => toast.error(err.response?.data?.detail || 'Failed to delete database'),
  });

  // --- Filter Logic ---

  const filteredDatabases = databases?.filter((db) => {
    const matchesSearch = 
      db.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      db.database.toLowerCase().includes(searchTerm.toLowerCase()) ||
      db.engine.toLowerCase().includes(searchTerm.toLowerCase());
    
    const matchesEngine = engineFilter === 'all' || db.engine === engineFilter;
    
    return matchesSearch && matchesEngine;
  });

  // --- Render ---

  if (isPodmanLoading) {
    return <div className="p-8 space-y-4">
      <Skeleton className="h-12 w-full" />
      <Skeleton className="h-64 w-full" />
    </div>;
  }

  // Not strictly preventing access, but showing a big warning
  const showPodmanWarning = podmanStatus && (!podmanStatus.installed || !podmanStatus.running);

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Databases</h1>
          <p className="text-muted-foreground mt-1">
            Manage your database instances and clusters.
          </p>
        </div>
        <Button onClick={() => navigate('/databases/create')}>
          <Plus className="mr-2 h-4 w-4" /> Create Database
        </Button>
      </div>

      {showPodmanWarning && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Service Unavailable</AlertTitle>
          <AlertDescription>
            The database provisioning service is not {podmanStatus?.installed ? 'running' : 'available'}. 
            Database functionality requires the provisioning engine to be active.
          </AlertDescription>
        </Alert>
      )}

      <Card>
        <CardHeader className="pb-3">
          <div className="flex flex-col sm:flex-row justify-between gap-4">
            <CardTitle>Instances</CardTitle>
            <div className="flex items-center gap-2">
              <div className="relative w-full sm:w-64">
                <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Search instances..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="pl-8"
                />
              </div>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Instance Name</TableHead>
                  <TableHead>Engine</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Connection</TableHead>
                  <TableHead>SKU</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {isDatabasesLoading ? (
                  // Loading Skeletons
                  Array.from({ length: 3 }).map((_, i) => (
                    <TableRow key={i}>
                      <TableCell><Skeleton className="h-6 w-32" /></TableCell>
                      <TableCell><Skeleton className="h-6 w-20" /></TableCell>
                      <TableCell><Skeleton className="h-6 w-24" /></TableCell>
                      <TableCell><Skeleton className="h-6 w-32" /></TableCell>
                      <TableCell><Skeleton className="h-6 w-16" /></TableCell>
                      <TableCell><Skeleton className="h-8 w-8 ml-auto" /></TableCell>
                    </TableRow>
                  ))
                ) : filteredDatabases?.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={6} className="h-32 text-center text-muted-foreground">
                      No databases found. Create one to get started.
                    </TableCell>
                  </TableRow>
                ) : (
                  filteredDatabases?.map((db) => (
                    <TableRow 
                      key={db.id} 
                      className="cursor-pointer hover:bg-muted/50"
                      onClick={() => navigate(`/databases/${db.id}`)}
                    >
                      <TableCell className="font-medium">
                        <div className="flex flex-col">
                          <span>{db.name}</span>
                          <span className="text-xs text-muted-foreground">Created {new Date(db.created_at).toLocaleDateString()}</span>
                        </div>
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <span className="text-xl">{ENGINE_ICONS[db.engine] || '💾'}</span>
                          <span className="capitalize">{db.engine}</span>
                        </div>
                      </TableCell>
                      <TableCell>
                        <HealthBadge status={db.status} />
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-1 text-sm font-mono text-muted-foreground">
                          <Server className="h-3 w-3" />
                          {db.host}:{db.port}
                        </div>
                      </TableCell>
                      <TableCell>
                        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-secondary text-secondary-foreground">
                          {db.sku?.toUpperCase() || 'CUSTOM'}
                        </span>
                      </TableCell>
                      <TableCell className="text-right">
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild onClick={(e) => e.stopPropagation()}>
                            <Button variant="ghost" className="h-8 w-8 p-0">
                              <span className="sr-only">Open menu</span>
                              <MoreHorizontal className="h-4 w-4" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end" onClick={(e) => e.stopPropagation()}>
                            <DropdownMenuLabel>Actions</DropdownMenuLabel>
                            <DropdownMenuItem onClick={() => navigate(`/databases/${db.id}`)}>
                              View Details
                            </DropdownMenuItem>
                            <DropdownMenuSeparator />
                            {db.status === 'running' ? (
                              <>
                                <DropdownMenuItem onClick={() => restartMutation.mutate(db.id)}>
                                  <RotateCw className="mr-2 h-4 w-4" /> Restart
                                </DropdownMenuItem>
                                <DropdownMenuItem onClick={() => stopMutation.mutate(db.id)} className="text-amber-500">
                                  <Power className="mr-2 h-4 w-4" /> Stop
                                </DropdownMenuItem>
                              </>
                            ) : (
                              <DropdownMenuItem onClick={() => startMutation.mutate(db.id)} className="text-green-500">
                                <Play className="mr-2 h-4 w-4" /> Start
                              </DropdownMenuItem>
                            )}
                            <DropdownMenuSeparator />
                            <DropdownMenuItem 
                              onClick={() => {
                                if (confirm('Are you sure you want to delete this database? This action cannot be undone.')) {
                                  deleteMutation.mutate(db.id);
                                }
                              }}
                              className="text-destructive focus:text-destructive"
                            >
                              <Trash2 className="mr-2 h-4 w-4" /> Delete
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
