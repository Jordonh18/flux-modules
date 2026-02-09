import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useParams, useNavigate } from 'react-router-dom';
import { api } from '@/lib/api';
import { useDocumentTitle } from '@/hooks/use-document-title';
import { toast } from 'sonner';

import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '@/components/ui/tabs';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import { Skeleton } from '@/components/ui/skeleton';
import {
  ArrowLeft,
  Play,
  Square,
  RotateCw,
  Trash2,
  RefreshCw,
  Database,
  Activity,
  HardDrive,
  Users,
  FileText,
  Download,
  Upload,
} from 'lucide-react';

import { DatabaseInstance, DatabaseMetrics, HealthStatus, Snapshot, ENGINE_ICONS } from '../types/database';
import { HealthBadge } from '../components/HealthBadge';
import { ConnectionInfo } from '../components/ConnectionInfo';
import { MetricsChart } from '../components/MetricsChart';

export default function DatabasesDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState('overview');

  // --- Queries ---

  const { data: db, isLoading: isDbLoading, error: dbError } = useQuery<DatabaseInstance>({
    queryKey: ['database', id],
    queryFn: async () => {
      const res = await api.get(`/modules/databases/databases`); // Fetch all and find, or assume dedicated endpoint if added
      // Assuming list endpoint for now as per instructions "Fetches: /modules/databases/databases then finds by ID, OR dedicated endpoint"
      // Better to check if endpoint matches ID.
      // Let's try to fetch specific ID if the API supports it, otherwise fallback to list filter.
      // PROMPT says: "Fetches: ... then finds by ID, OR dedicated endpoint"
      // I'll try dedicated first, if it fails, catch? No, let's just stick to what works for list: find
      const all = res.data as DatabaseInstance[];
      const found = all.find(d => d.id === Number(id));
      if (!found) throw new Error('Database not found');
      return found;
    },
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status && ['creating', 'stopping', 'starting'].includes(status) ? 2000 : 10000;
    },
  });

  useDocumentTitle(db ? `${db.name} - Database` : 'Database Details');

  const { data: metrics } = useQuery<DatabaseMetrics>({
    queryKey: ['database-metrics', id],
    queryFn: async () => {
      const res = await api.get(`/modules/databases/databases/${id}/metrics`);
      return res.data;
    },
    enabled: !!db && activeTab === 'metrics',
    refetchInterval: 5000,
  });

  const { data: health } = useQuery<HealthStatus>({
    queryKey: ['database-health', id],
    queryFn: async () => {
      const res = await api.get(`/modules/databases/databases/${id}/health`);
      return res.data;
    },
    enabled: !!db,
    refetchInterval: 30000,
  });
  
  const { data: snapshots, refetch: refetchSnapshots } = useQuery<Snapshot[]>({
    queryKey: ['database-snapshots', id],
    queryFn: async () => {
      const res = await api.get(`/modules/databases/databases/${id}/snapshots`);
      return res.data;
    },
    enabled: !!db && activeTab === 'backups',
  });

  // --- Mutations ---

  const startMutation = useMutation({
    mutationFn: () => api.post(`/modules/databases/databases/${id}/start`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['database', id] });
      toast.success('Database starting...');
    },
    onError: (err: any) => toast.error(err.response?.data?.detail || 'Failed to start'),
  });

  const stopMutation = useMutation({
    mutationFn: () => api.post(`/modules/databases/databases/${id}/stop`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['database', id] });
      toast.success('Database stopping...');
    },
    onError: (err: any) => toast.error(err.response?.data?.detail || 'Failed to stop'),
  });

  const restartMutation = useMutation({
    mutationFn: () => api.post(`/modules/databases/databases/${id}/restart`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['database', id] });
      toast.success('Database restarting...');
    },
    onError: (err: any) => toast.error(err.response?.data?.detail || 'Failed to restart'),
  });

  const deleteMutation = useMutation({
    mutationFn: () => api.delete(`/modules/databases/databases/${id}`),
    onSuccess: () => {
      toast.success('Database deleted');
      navigate('/databases');
    },
    onError: (err: any) => toast.error(err.response?.data?.detail || 'Failed to delete'),
  });
  
  const createSnapshotMutation = useMutation({
    mutationFn: () => api.post(`/modules/databases/databases/${id}/snapshots`),
    onSuccess: () => {
      toast.success('Snapshot created');
      refetchSnapshots();
    },
    onError: (err: any) => toast.error(err.response?.data?.detail || 'Failed to create snapshot'),
  });

  // --- Render ---

  if (isDbLoading) {
    return <div className="p-8 space-y-4">
      <Skeleton className="h-10 w-1/3" />
      <Skeleton className="h-64 w-full" />
    </div>;
  }

  if (dbError || !db) {
    return (
      <div className="flex flex-col items-center justify-center p-12">
        <h2 className="text-xl font-semibold text-destructive">Error Loading Database</h2>
        <p className="text-muted-foreground">The database instance could not be found.</p>
        <Button onClick={() => navigate('/databases')} variant="link" className="mt-4">
          <ArrowLeft className="mr-2 h-4 w-4" /> Back to List
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4">
        <Button 
          variant="ghost" 
          className="w-fit pl-0 hover:bg-transparent" 
          onClick={() => navigate('/databases')}}
        >
          <ArrowLeft className="mr-2 h-4 w-4" /> Back to Databases
        </Button>
        
        <div className="flex flex-col lg:flex-row justify-between lg:items-center gap-4">
          <div className="flex items-center gap-3">
            <div className="bg-muted p-2 rounded-lg text-3xl">
              {ENGINE_ICONS[db.engine] || '💾'}
            </div>
            <div>
              <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
                {db.name}
                <HealthBadge status={health?.status || db.status} />
              </h1>
              <div className="text-sm text-muted-foreground flex items-center gap-2 mt-1">
                <span className="font-mono">{db.host}:{db.port}</span>
                <span>•</span>
                <span className="capitalize">{db.engine}</span>
                <span>•</span>
                <span>{db.sku?.toUpperCase()}</span>
              </div>
            </div>
          </div>

          <div className="flex gap-2">
            {db.status === 'running' ? (
              <>
                <Button variant="outline" size="sm" onClick={() => restartMutation.mutate()}>
                  <RotateCw className="mr-2 h-4 w-4" /> Restart
                </Button>
                <Button variant="outline" size="sm" className="text-amber-600 hover:text-amber-700 hover:bg-amber-50" onClick={() => stopMutation.mutate()}>
                  <Square className="mr-2 h-4 w-4 fill-current" /> Stop
                </Button>
              </>
            ) : (
              <Button variant="outline" size="sm" className="text-green-600 hover:text-green-700 hover:bg-green-50" onClick={() => startMutation.mutate()}>
                <Play className="mr-2 h-4 w-4 fill-current" /> Start
              </Button>
            )}
            
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button variant="destructive" size="sm">
                  <Trash2 className="mr-2 h-4 w-4" /> Delete
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Are you absolutely sure?</AlertDialogTitle>
                  <AlertDialogDescription>
                    This action cannot be undone. This will permanently delete the database 
                    <strong> {db.name} </strong> and remove all data associated with it.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                  <AlertDialogAction onClick={() => deleteMutation.mutate()} className="bg-destructive text-destructive-foreground hover:bg-destructive/90">
                    Delete Database
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </div>
        </div>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-4">
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="metrics">Metrics</TabsTrigger>
          <TabsTrigger value="logs">Logs</TabsTrigger>
          <TabsTrigger value="backups">Backups</TabsTrigger>
          {/* <TabsTrigger value="data">Data Explorer</TabsTrigger> */}
          {/* <TabsTrigger value="users">Users</TabsTrigger> */}
        </TabsList>

        <TabsContent value="overview" className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-7">
            <Card className="col-span-4">
              <CardHeader>
                <CardTitle>Connection Details</CardTitle>
                <CardDescription>Use these credentials to connect to your database</CardDescription>
              </CardHeader>
              <CardContent>
                <ConnectionInfo instance={db} />
              </CardContent>
            </Card>

            <Card className="col-span-3">
               <CardHeader>
                <CardTitle>System Properties</CardTitle>
               </CardHeader>
               <CardContent className="space-y-4">
                 <div className="grid grid-cols-2 gap-2 text-sm">
                   <div className="text-muted-foreground">Engine Version</div>
                   <div className="font-medium text-right">Latest</div>

                   <div className="text-muted-foreground">Created</div>
                   <div className="font-medium text-right">{new Date(db.created_at).toLocaleDateString()}</div>

                   <div className="text-muted-foreground">Storage Limit</div>
                   <div className="font-medium text-right">{db.storage_limit_gb ? `${db.storage_limit_gb} GB` : 'Unlimited'}</div>

                   <div className="text-muted-foreground">Memory Limit</div>
                   <div className="font-medium text-right">{db.memory_limit_mb ? `${db.memory_limit_mb} MB` : 'Default'}</div>
                 </div>
                 <Separator />
                 <div>
                    <h4 className="text-sm font-semibold mb-2 flex items-center">
                        <Activity className="w-4 h-4 mr-2" /> Health Status
                    </h4>
                    <div className="p-3 bg-muted rounded-md text-sm">
                        {health?.details ? (
                            <pre className="whitespace-pre-wrap text-xs font-mono">
                                {JSON.stringify(health.details, null, 2)}
                            </pre>
                        ) : 'No health details available.'}
                    </div>
                 </div>
               </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="metrics">
          <Card>
            <CardHeader>
              <CardTitle>Resource Usage</CardTitle>
              <CardDescription>Real-time performance metrics</CardDescription>
            </CardHeader>
            <CardContent className="pl-2">
                 <div className="h-[400px] w-full">
                     <MetricsChart 
                      metrics={metrics || null}
                      isLoading={!metrics}
                     />
                 </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="logs">
            <Card>
                <CardHeader>
                    <CardTitle>Container Logs</CardTitle>
                </CardHeader>
                <CardContent>
                    <div className="bg-black text-green-400 font-mono p-4 rounded-md h-[500px] overflow-y-auto text-sm">
                        <p className="opacity-50">// Logs fetching not implemented in this demo</p>
                        <p>Listening on 0.0.0.0:{db.port}</p>
                        <p>Connection established...</p>
                    </div>
                </CardContent>
            </Card>
        </TabsContent>

        <TabsContent value="backups">
             <Card>
                 <CardHeader className="flex flex-row items-center justify-between">
                     <div>
                        <CardTitle>Snapshots</CardTitle>
                        <CardDescription>Manage point-in-time backups</CardDescription>
                     </div>
                     <Button onClick={() => createSnapshotMutation.mutate()} disabled={createSnapshotMutation.isPending}>
                       {createSnapshotMutation.isPending ? <RefreshCw className="mr-2 h-4 w-4 animate-spin"/> : <Download className="mr-2 h-4 w-4" />}
                       Create Snapshot
                     </Button>
                 </CardHeader>
                 <CardContent>
                    <Table>
                        <TableHeader>
                            <TableRow>
                                <TableHead>ID</TableHead>
                                <TableHead>Date Created</TableHead>
                                <TableHead>Size</TableHead>
                                <TableHead className="text-right">Actions</TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {snapshots?.map(snap => (
                                <TableRow key={snap.id}>
                                    <TableCell className="font-mono">#{snap.id}</TableCell>
                                    <TableCell>{new Date(snap.created_at).toLocaleString()}</TableCell>
                                    <TableCell>{(snap.size / 1024 / 1024).toFixed(2)} MB</TableCell>
                                    <TableCell className="text-right">
                                        <Button variant="ghost" size="sm" className="text-blue-600">
                                            <Upload className="mr-2 h-3 w-3" /> Restore
                                        </Button>
                                    </TableCell>
                                </TableRow>
                            ))}
                            {!snapshots?.length && (
                                <TableRow>
                                    <TableCell colSpan={4} className="text-center h-24 text-muted-foreground">
                                        No snapshots found.
                                    </TableCell>
                                </TableRow>
                            )}
                        </TableBody>
                    </Table>
                 </CardContent>
             </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
