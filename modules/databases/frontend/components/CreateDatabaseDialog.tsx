import React, { useState, useEffect, ChangeEvent } from 'react';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Checkbox } from '@/components/ui/checkbox';
import { Slider } from '@/components/ui/slider';
import { Loader2 } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { DATABASE_SKUS } from '../types/database-skus';

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

interface CreateDatabaseDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (data: any) => void; // Using any for now to match the flexible structure, but should be typed ideally
  isSubmitting?: boolean;
  engines?: DatabaseEngine[];
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
  vnetName?: string;
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

export function CreateDatabaseDialog({ open, onOpenChange, onSubmit, isSubmitting = false, engines = [] }: CreateDatabaseDialogProps) {
  const [formState, setFormState] = useState<FormState>(INITIAL_FORM_STATE);
  const [errors, setErrors] = useState<Record<string, string>>({});

  // Fetch system info for SKU filtering
  const { data: systemInfo } = useQuery({
    queryKey: ['databases', 'system-info'],
    queryFn: async () => {
      const response = await api.get('/modules/databases/system-info');
      return response.data;
    },
    enabled: open,
    staleTime: 60000,
  });

  // Fetch available VNets
  const { data: vnetsData } = useQuery({
    queryKey: ['networking', 'vnets'],
    queryFn: async () => {
      const response = await api.get('/networking/vnets');
      return response.data;
    },
    enabled: open,
    refetchInterval: 30000,
  });

  const availableVNets = vnetsData?.vnets?.filter((v: any) => v.status === 'active') || [];

  // Helper to check if SKU exceeds system capacity
  const isSkuUnavailable = (sku: any) => {
    if (!systemInfo || sku.series === 'custom') return false;
    const memoryGb = sku.memoryMb / 1024;
    const systemMemoryGb = systemInfo.total_memory_mb / 1024;
    return sku.cpus > systemInfo.cpu_cores || memoryGb > systemMemoryGb;
  };

  // Reset form when dialog opens
  useEffect(() => {
    if (open) {
      setFormState(INITIAL_FORM_STATE);
      setErrors({});
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
            engine: formState.databaseType,
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
            vnet_name: formState.vnetName || undefined,
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
                  {engines.map((engine) => (
                    <SelectItem key={engine.engine} value={engine.engine}>
                      <div className="flex items-center gap-2">
                        <span>{getCategoryIcon(engine.category)}</span>
                        <span>{engine.display_name}</span>
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

          {/* Virtual Network */}
          <div className="space-y-2">
            <Label htmlFor="vnet">Virtual Network (Optional)</Label>
            <Select
              value={formState.vnetName || "none"}
              onValueChange={(value) => setFormState({ ...formState, vnetName: value === "none" ? undefined : value })}
            >
              <SelectTrigger>
                <SelectValue placeholder="Select VNet or use port mapping" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">No VNet (port mapping)</SelectItem>
                {availableVNets.map((vnet: any) => (
                  <SelectItem key={vnet.id} value={vnet.name}>
                    {vnet.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              {formState.vnetName 
                ? `Database will receive an IP on the ${formState.vnetName} network`
                : "Database will use random port mapping on localhost"}
            </p>
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
                      {idx === 0 && (
                        <div className="px-2 py-1 border-b">
                          <span className="text-[8px] text-muted-foreground uppercase tracking-wide">Burstable</span>
                        </div>
                      )}
                      <SelectItem value={sku.id} disabled={isSkuUnavailable(sku)}>
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
                  <div className="px-2 py-1 border-b">
                    <span className="text-[8px] text-muted-foreground uppercase tracking-wide">General Purpose</span>
                  </div>
                  {DATABASE_SKUS.filter(sku => sku.series === 'general').map((sku) => (
                    <SelectItem key={sku.id} value={sku.id} disabled={isSkuUnavailable(sku)}>
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
                  <div className="px-2 py-1 border-b">
                    <span className="text-[8px] text-muted-foreground uppercase tracking-wide">Memory Optimized</span>
                  </div>
                  {DATABASE_SKUS.filter(sku => sku.series === 'memory').map((sku) => (
                    <SelectItem key={sku.id} value={sku.id} disabled={isSkuUnavailable(sku)}>
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-sm">{sku.name}</span>
                        <span className="text-xs text-muted-foreground">
                          {Math.round(sku.memoryMb / 1024)}GB • {sku.cpus}vCPU
                        </span>
                      </div>
                    </SelectItem>
                  ))}
                  
                  {/* F-series */}
                  <div className="px-2 py-1 border-b">
                    <span className="text-[8px] text-muted-foreground uppercase tracking-wide">Compute Optimized</span>
                  </div>
                  {DATABASE_SKUS.filter(sku => sku.series === 'compute').map((sku) => (
                    <SelectItem key={sku.id} value={sku.id} disabled={isSkuUnavailable(sku)}>
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-sm">{sku.name}</span>
                        <span className="text-xs text-muted-foreground">
                          {Math.round(sku.memoryMb / 1024)}GB • {sku.cpus}vCPU
                        </span>
                      </div>
                    </SelectItem>
                  ))}
                  
                  {/* Custom */}
                  <div className="px-2 py-1 border-b">
                    <span className="text-[8px] text-muted-foreground uppercase tracking-wide">Custom</span>
                  </div>
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

          {/* External Access */}
          <div className="flex items-center justify-between">
            <div>
              <Label className="text-sm font-medium">Allow public access</Label>
              <p className="text-xs text-muted-foreground">Database accessible from any network</p>
            </div>
            <Checkbox
              checked={formState.externalAccess}
              onCheckedChange={(checked) => setFormState({...formState, externalAccess: checked === true})}
            />
          </div>

          {/* TLS */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <div>
                <Label className="text-sm font-medium">TLS Encryption</Label>
                <p className="text-xs text-muted-foreground">Secure with custom certificates</p>
              </div>
              <Checkbox
                checked={formState.tlsEnabled}
                onCheckedChange={(checked) => setFormState({...formState, tlsEnabled: checked === true})}
              />
            </div>

            {formState.tlsEnabled && (
              <div className="space-y-3 pt-2">
                <div className="space-y-1.5">
                  <Label className="text-xs">Certificate (PEM)</Label>
                  <Input
                    type="file"
                    accept=".pem,.crt,.cer"
                    onChange={(e) => e.target.files?.[0] && handleFileUpload(e.target.files[0], 'tlsCert')}
                    className={`text-xs ${errors.tlsCert ? "border-destructive" : ""}`}
                  />
                  {errors.tlsCert && <p className="text-xs text-destructive">{errors.tlsCert}</p>}
                  {formState.tlsCert && <p className="text-xs text-green-600">Certificate loaded</p>}
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
                  {formState.tlsKey && <p className="text-xs text-green-600">Key loaded</p>}
                </div>
              </div>
            )}
          </div>

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
