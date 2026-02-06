import React, { useState, useEffect, ChangeEvent } from 'react';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Checkbox } from '@/components/ui/checkbox';
import { Slider } from '@/components/ui/slider';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { ChevronDown, Loader2, AlertTriangle } from 'lucide-react';
import { DATABASE_SKUS } from '../types/database-skus';

// Copy of DATABASE_TYPES from DatabasesPage.tsx
const DATABASE_TYPES = [
  { value: 'postgresql', label: 'PostgreSQL', icon: '🐘', description: 'Advanced relational DB', useCase: 'Complex queries, JSON, full-text search' },
  { value: 'mysql', label: 'MySQL', icon: '🐬', description: 'Popular relational DB', useCase: 'Web apps, WordPress, reliable ACID transactions' },
  { value: 'mariadb', label: 'MariaDB', icon: '🦭', description: 'MySQL-compatible DB', useCase: 'MySQL alternative with better performance' },
  { value: 'mongodb', label: 'MongoDB', icon: '🍃', description: 'Document database', useCase: 'Flexible schemas, JSON-like documents, real-time' },
  { value: 'redis', label: 'Redis', icon: '🔴', description: 'In-memory cache', useCase: 'Session storage, caching, pub/sub, queues' },
  { value: 'sqlserver', label: 'SQL Server', icon: '🗄️', description: 'Microsoft enterprise DB', useCase: '.NET apps, enterprise Windows workloads' },
  { value: 'cassandra', label: 'Cassandra', icon: '🔷', description: 'Wide-column NoSQL', useCase: 'Massive scale, time-series, IoT data' },
  { value: 'couchdb', label: 'CouchDB', icon: '🛋️', description: 'Document DB with HTTP', useCase: 'Offline-first apps, sync, REST API' },
  { value: 'neo4j', label: 'Neo4j', icon: '🕸️', description: 'Graph database', useCase: 'Relationships, social networks, recommendations' },
  { value: 'influxdb', label: 'InfluxDB', icon: '📈', description: 'Time-series DB', useCase: 'Metrics, monitoring, IoT sensors, analytics' },
  { value: 'elasticsearch', label: 'Elasticsearch', icon: '🔍', description: 'Search & analytics', useCase: 'Full-text search, log analysis, APM' },
];

interface CreateDatabaseDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (data: any) => void; // Using any for now to match the flexible structure, but should be typed ideally
  isSubmitting?: boolean;
}

interface FormState {
  name: string;
  databaseType: string;
  databaseName: string;
  sku: string;
  memoryLimitMb: number;
  cpuLimit: number;
  storageLimitGb: number;
  externalAccess: boolean;
  tlsEnabled: boolean;
  tlsCert?: string;
  tlsKey?: string;
}

const INITIAL_FORM_STATE: FormState = {
  name: '',
  databaseType: 'postgresql',
  databaseName: 'app',
  sku: 'd2', // Default to recommended
  memoryLimitMb: 4096,
  cpuLimit: 2,
  storageLimitGb: 50,
  externalAccess: false,
  tlsEnabled: false,
};

export function CreateDatabaseDialog({ open, onOpenChange, onSubmit, isSubmitting = false }: CreateDatabaseDialogProps) {
  const [formState, setFormState] = useState<FormState>(INITIAL_FORM_STATE);
  const [isAdvancedOpen, setIsAdvancedOpen] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});

  // Reset form when dialog opens
  useEffect(() => {
    if (open) {
      setFormState(INITIAL_FORM_STATE);
      setErrors({});
      setIsAdvancedOpen(false);
    }
  }, [open]);

  const handleSkuSelect = (skuId: string) => {
    const sku = DATABASE_SKUS.find(s => s.id === skuId);
    if (!sku) return;

    setFormState(prev => {
      const newState = { ...prev, sku: skuId };
      // Only update resource values if not switching to custom (keep previous valid values or set defaults)
      // Or if switching FROM custom to a preset, update them.
      if (skuId !== 'custom') {
        newState.memoryLimitMb = sku.memoryMb;
        newState.cpuLimit = sku.cpus;
        newState.storageLimitGb = sku.storageGb;
      }
      return newState;
    });
  };

  const handleFileUpload = (file: File, field: 'tlsCert' | 'tlsKey') => {
    const reader = new FileReader();
    reader.onload = () => {
      const base64 = (reader.result as string).split(',')[1];
      setFormState(prev => ({ ...prev, [field]: base64 }));
    };
    reader.readAsDataURL(file);
  };

  const validate = (): boolean => {
    const newErrors: Record<string, string> = {};

    if (!formState.databaseName.trim()) {
      newErrors.databaseName = 'Database name is required';
    }

    if (formState.sku === 'custom') {
      if (formState.memoryLimitMb < 512) newErrors.memory = 'Minimum 512MB RAM required';
      if (formState.cpuLimit < 0.5) newErrors.cpu = 'Minimum 0.5 vCPU required';
      if (formState.storageLimitGb < 1) newErrors.storage = 'Minimum 1GB storage required';
    }

    if (formState.tlsEnabled) {
      if (!formState.tlsCert) newErrors.tlsCert = 'Certificate file is required';
      if (!formState.tlsKey) newErrors.tlsKey = 'Private key file is required';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (validate()) {
        // Construct the payload to match what the API expects
        // Note: The backend expects snake_case usually, but the prompt's FormState interface uses camelCase.
        // I will pass the formState as is, and let the parent component or the API layer handle mapping if needed. 
        // OR better yet, map it here to match the existing CreateDatabaseRequest structure + new fields.
        
        // Existing CreateDatabaseRequest: type, name, database_name.
        // New fields from prompt: sku, memory_limit_mb, cpu_limit, storage_limit_gb, external_access, tls_enabled, tls_cert, tls_key
        
        const payload = {
            type: formState.databaseType,
            name: formState.name || undefined,
            database_name: formState.databaseName,
            sku: formState.sku,
            memory_limit_mb: formState.memoryLimitMb,
            cpu_limit: formState.cpuLimit,
            storage_limit_gb: formState.storageLimitGb,
            external_access: formState.externalAccess,
            tls_enabled: formState.tlsEnabled,
            tls_cert: formState.tlsCert,
            tls_key: formState.tlsKey,
        };
        
        onSubmit(payload);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Create Database</DialogTitle>
          <DialogDescription>
            Configure your new managed database instance
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-6">
          {/* Basic Info */}
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="name">Name (Optional)</Label>
              <Input
                id="name"
                placeholder="e.g. production-db"
                value={formState.name}
                onChange={(e) => setFormState({ ...formState, name: e.target.value })}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="type">Engine</Label>
              <Select
                value={formState.databaseType}
                onValueChange={(value) => setFormState({ ...formState, databaseType: value })}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="max-h-[400px]">
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
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="database_name">Database Name</Label>
            <Input
              id="database_name"
              placeholder="app_db"
              value={formState.databaseName}
              onChange={(e) => setFormState({ ...formState, databaseName: e.target.value })}
              className={errors.databaseName ? "border-red-500" : ""}
            />
            {errors.databaseName && <p className="text-xs text-red-500">{errors.databaseName}</p>}
          </div>

          {/* Compute + Storage Selection */}
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="compute">Compute</Label>
              <Select
                value={formState.sku}
                onValueChange={handleSkuSelect}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="max-h-[400px]">
                  {/* B-series */}
                  {DATABASE_SKUS.filter(sku => sku.series === 'burstable').map((sku, idx) => (
                    <React.Fragment key={sku.id}>
                      {idx === 0 && <div className="border-b my-1" />}
                      <SelectItem value={sku.id}>
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-sm">{sku.name}</span>
                          <span className="text-xs text-muted-foreground">
                            {Math.round(sku.memoryMb / 1024)}GB • {sku.cpus}vCPU
                          </span>
                        </div>
                      </SelectItem>
                    </React.Fragment>
                  ))}
                  
                  {/* D-series */}
                  <div className="border-b my-1" />
                  {DATABASE_SKUS.filter(sku => sku.series === 'general').map((sku) => (
                    <SelectItem key={sku.id} value={sku.id}>
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-sm">{sku.name}</span>
                        <span className="text-xs text-muted-foreground">
                          {Math.round(sku.memoryMb / 1024)}GB • {sku.cpus}vCPU
                        </span>
                        {sku.recommended && (
                          <span className="text-[10px] px-1.5 py-0.5 bg-green-500/10 text-green-600 dark:text-green-400 rounded">
                            Recommended
                          </span>
                        )}
                      </div>
                    </SelectItem>
                  ))}
                  
                  {/* E-series */}
                  <div className="border-b my-1" />
                  {DATABASE_SKUS.filter(sku => sku.series === 'memory').map((sku) => (
                    <SelectItem key={sku.id} value={sku.id}>
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-sm">{sku.name}</span>
                        <span className="text-xs text-muted-foreground">
                          {Math.round(sku.memoryMb / 1024)}GB • {sku.cpus}vCPU
                        </span>
                      </div>
                    </SelectItem>
                  ))}
                  
                  {/* F-series */}
                  <div className="border-b my-1" />
                  {DATABASE_SKUS.filter(sku => sku.series === 'compute').map((sku) => (
                    <SelectItem key={sku.id} value={sku.id}>
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-sm">{sku.name}</span>
                        <span className="text-xs text-muted-foreground">
                          {Math.round(sku.memoryMb / 1024)}GB • {sku.cpus}vCPU
                        </span>
                      </div>
                    </SelectItem>
                  ))}
                  
                  {/* Custom */}
                  <div className="border-b my-1" />
                  {DATABASE_SKUS.filter(sku => sku.series === 'custom').map((sku) => (
                    <SelectItem key={sku.id} value={sku.id}>
                      <span className="font-semibold text-sm">{sku.name}</span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="storage">Storage</Label>
              <Select
                value={formState.storageLimitGb.toString()}
                onValueChange={(value) => setFormState({ ...formState, storageLimitGb: parseInt(value) })}
                disabled={formState.sku === 'custom'}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="10">10 GB</SelectItem>
                  <SelectItem value="20">20 GB</SelectItem>
                  <SelectItem value="50">50 GB</SelectItem>
                  <SelectItem value="100">100 GB</SelectItem>
                  <SelectItem value="200">200 GB</SelectItem>
                  <SelectItem value="500">500 GB</SelectItem>
                  <SelectItem value="1024">1 TB</SelectItem>
                  <SelectItem value="2048">2 TB</SelectItem>
                </SelectContent>
              </Select>
              {formState.sku === 'custom' && (
                <p className="text-xs text-muted-foreground">Configure below in Custom section</p>
              )}
            </div>
          </div>

          {/* Custom SKU Config */}
          {formState.sku === 'custom' && (
            <div className="space-y-4 p-4 rounded-md border bg-muted/30">
              <div className="space-y-2">
                <div className="flex justify-between items-center">
                  <Label htmlFor="memory-slider">Memory</Label>
                  <span className="text-sm font-medium">{formState.memoryLimitMb} MB</span>
                </div>
                <Slider
                  id="memory-slider"
                  min={512}
                  max={65536}
                  step={512}
                  value={[formState.memoryLimitMb]}
                  onValueChange={(value) => setFormState({...formState, memoryLimitMb: value[0]})}
                />
                {errors.memory && <p className="text-xs text-destructive">{errors.memory}</p>}
              </div>

              <div className="space-y-2">
                <div className="flex justify-between items-center">
                  <Label htmlFor="cpu-slider">vCPUs</Label>
                  <span className="text-sm font-medium">{formState.cpuLimit}</span>
                </div>
                <Slider
                  id="cpu-slider"
                  min={0.5}
                  max={32}
                  step={0.5}
                  value={[formState.cpuLimit]}
                  onValueChange={(value) => setFormState({...formState, cpuLimit: value[0]})}
                />
                {errors.cpu && <p className="text-xs text-destructive">{errors.cpu}</p>}
              </div>

              <div className="space-y-2">
                <div className="flex justify-between items-center">
                  <Label htmlFor="storage-slider">Storage</Label>
                  <span className="text-sm font-medium">{formState.storageLimitGb} GB</span>
                </div>
                <Slider
                  id="storage-slider"
                  min={1}
                  max={1000}
                  step={1}
                  value={[formState.storageLimitGb]}
                  onValueChange={(value) => setFormState({...formState, storageLimitGb: value[0]})}
                />
                {errors.storage && <p className="text-xs text-destructive">{errors.storage}</p>}
              </div>
            </div>
          )}

          {/* Advanced Options */}
          <Collapsible open={isAdvancedOpen} onOpenChange={setIsAdvancedOpen}>
            <CollapsibleTrigger className="flex items-center w-full text-sm font-medium hover:underline">
              <ChevronDown className={`w-4 h-4 mr-2 transition-transform ${isAdvancedOpen ? '' : '-rotate-90'}`} />
              Advanced Options
            </CollapsibleTrigger>
            
            <CollapsibleContent className="mt-4 space-y-3">
              {/* External Access */}
              <div className="flex items-center justify-between p-3 rounded-md border bg-amber-50 dark:bg-amber-950/20 border-amber-200 dark:border-amber-900/50">
                <div className="flex items-center gap-2">
                  <AlertTriangle className="h-4 w-4 text-amber-600 dark:text-amber-500 flex-shrink-0" />
                  <div>
                    <Label className="text-sm font-medium cursor-pointer">Allow public access</Label>
                    <p className="text-xs text-muted-foreground">Database accessible from any network</p>
                  </div>
                </div>
                <Checkbox
                  checked={formState.externalAccess}
                  onCheckedChange={(checked) => setFormState({...formState, externalAccess: checked === true})}
                />
              </div>

              {/* TLS */}
              <div className="p-3 rounded-md border space-y-3">
                <div className="flex items-center justify-between">
                  <div>
                    <Label className="text-sm font-medium cursor-pointer">TLS Encryption</Label>
                    <p className="text-xs text-muted-foreground">Secure with custom certificates</p>
                  </div>
                  <Checkbox
                    checked={formState.tlsEnabled}
                    onCheckedChange={(checked) => setFormState({...formState, tlsEnabled: checked === true})}
                  />
                </div>

                {formState.tlsEnabled && (
                  <div className="space-y-3 pt-2 border-t">
                    <div className="space-y-1.5">
                      <Label className="text-xs">Certificate (PEM)</Label>
                      <Input
                        type="file"
                        accept=".pem,.crt,.cer"
                        onChange={(e) => e.target.files?.[0] && handleFileUpload(e.target.files[0], 'tlsCert')}
                        className={`text-xs ${errors.tlsCert ? "border-destructive" : ""}`}
                      />
                      {errors.tlsCert && <p className="text-xs text-destructive">{errors.tlsCert}</p>}
                      {formState.tlsCert && <p className="text-xs text-green-600">✓ Certificate loaded</p>}
                    </div>

                    <div className="space-y-1.5">
                      <Label className="text-xs">Private Key (PEM)</Label>
                      <Input
                        type="file"
                        accept=".key,.pem"
                        onChange={(e) => e.target.files?.[0] && handleFileUpload(e.target.files[0], 'tlsKey')}
                        className={`text-xs ${errors.tlsKey ? "border-destructive" : ""}`}
                      />
                      {errors.tlsKey && <p className="text-xs text-destructive">{errors.tlsKey}</p>}
                      {formState.tlsKey && <p className="text-xs text-green-600">✓ Key loaded</p>}
                    </div>
                  </div>
                )}
              </div>
            </CollapsibleContent>
          </Collapsible>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Create Database
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
