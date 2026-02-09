import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { DATABASE_SKUS, DatabaseSku } from '../types/database-skus';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import { AlertCircle, CheckCircle2, Cpu, Database, HardDrive, Server } from 'lucide-react';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Skeleton } from '@/components/ui/skeleton';

interface SkuSelectorProps {
  selected: string;
  onSelect: (sku: string) => void;
  requiredEngine?: string; 
}

interface SystemInfo {
  cpu_cores: number;
  total_memory_mb: number;
  available_memory_mb: number;
  disk_total_gb: number;
  disk_free_gb: number;
}

export function SkuSelector({ selected, onSelect }: SkuSelectorProps) {
  // Fetch system info to validate SKU capacity
  const { data: systemInfo, isLoading } = useQuery<SystemInfo>({
    queryKey: ['system-info'],
    queryFn: async () => {
      const response = await api.get('/modules/databases/system-info');
      // Fallback/transform if needed, but assuming direct match for now
      return response.data;
    },
    // Don't block UI if this fails, just don't show warnings
    retry: 1
  });

  // Group SKUs by series
  const groupedSkus = useMemo(() => {
    const groups: Record<string, DatabaseSku[]> = {};
    
    // Sort logic to put smaller/cheaper SKUs first
    const sortedSkus = [...DATABASE_SKUS].sort((a, b) => {
      if (a.series !== b.series) return a.series.localeCompare(b.series);
      return a.cpu_limit - b.cpu_limit || a.memory_limit_mb - b.memory_limit_mb;
    });

    sortedSkus.forEach((sku) => {
      if (!groups[sku.series]) {
        groups[sku.series] = [];
      }
      groups[sku.series].push(sku);
    });

    return groups;
  }, []);

  const getSeriesColor = (series: string) => {
    switch (series.toLowerCase()) {
      case 'burstable': return 'text-orange-500 border-orange-500/20 bg-orange-500/10';
      case 'general purpose': return 'text-blue-500 border-blue-500/20 bg-blue-500/10';
      case 'memory optimized': return 'text-purple-500 border-purple-500/20 bg-purple-500/10';
      case 'compute optimized': return 'text-red-500 border-red-500/20 bg-red-500/10';
      default: return 'text-gray-500 border-gray-500/20 bg-gray-500/10';
    }
  };

  const isSkuCompatible = (sku: DatabaseSku): { compatible: boolean; reason?: string } => {
    if (!systemInfo) return { compatible: true }; // Assume compatible if check fails

    if (sku.memory_limit_mb > systemInfo.total_memory_mb) {
      return { compatible: false, reason: `Exceeds system memory (${Math.round(systemInfo.total_memory_mb / 1024)}GB)` };
    }
    
    if (sku.cpu_limit > systemInfo.cpu_cores) {
      return { compatible: false, reason: `Exceeds system CPUs (${systemInfo.cpu_cores} cores)` };
    }

    return { compatible: true };
  };

  if (isLoading) {
    return <div className="space-y-4">
      <Skeleton className="h-24 w-full" />
      <Skeleton className="h-24 w-full" />
      <Skeleton className="h-24 w-full" />
    </div>;
  }

  return (
    <div className="space-y-6">
      {Object.entries(groupedSkus).map(([series, skus]) => {
        // Filter out hidden SKUs or apply other logic if needed
        const visibleSkus = skus; 
        if (visibleSkus.length === 0) return null;

        return (
          <div key={series} className="space-y-3">
            <div className="flex items-center gap-2">
               <Badge variant="outline" className={cn("text-xs font-semibold capitalize", getSeriesColor(series))}>
                 {series}
               </Badge>
               <div className="h-px flex-1 bg-border" />
            </div>
            
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
              {visibleSkus.map((sku) => {
                const { compatible, reason } = isSkuCompatible(sku);
                const isSelected = selected === sku.id;
                
                return (
                  <Card
                    key={sku.id}
                    className={cn(
                      "relative overflow-hidden transition-all",
                      compatible 
                        ? "cursor-pointer hover:border-primary/50 hover:shadow-sm" 
                        : "opacity-60 cursor-not-allowed bg-muted/50",
                      isSelected 
                        ? "border-primary ring-1 ring-primary bg-primary/5" 
                        : "border-border"
                    )}
                    onClick={() => compatible && onSelect(sku.id)}
                  >
                    {isSelected && (
                      <div className="absolute right-0 top-0 rounded-bl-lg bg-primary px-2 py-1 text-[10px] text-primary-foreground">
                        Selected
                      </div>
                    )}
                    
                    <div className="p-4">
                      <div className="flex flex-col gap-1">
                        <h4 className="font-semibold">{sku.name}</h4>
                        <span className="text-xs text-muted-foreground">{sku.description}</span>
                      </div>
                      
                      <div className="mt-4 grid grid-cols-2 gap-y-2 text-sm">
                        <div className="flex items-center gap-1.5 text-muted-foreground">
                          <Cpu className="h-3.5 w-3.5" />
                          <span className="font-medium text-foreground">{sku.cpu_limit} vCPU</span>
                        </div>
                        <div className="flex items-center gap-1.5 text-muted-foreground">
                          <Server className="h-3.5 w-3.5" />
                          <span className="font-medium text-foreground">{sku.memory_limit_mb / 1024} GB</span>
                        </div>
                        <div className="flex items-center gap-1.5 text-muted-foreground col-span-2">
                           <HardDrive className="h-3.5 w-3.5" />
                           <span className="font-medium text-foreground">
                             {sku.storage_limit_gb ? `${sku.storage_limit_gb} GB Storage` : 'Unlimited Storage'}
                           </span>
                        </div>
                      </div>

                      {!compatible && (
                        <div className="mt-3 flex items-center gap-1.5 text-[10px] text-destructive font-medium">
                          <AlertCircle className="h-3 w-3" />
                          {reason}
                        </div>
                      )}
                    </div>
                  </Card>
                );
              })}
            </div>
          </div>
        );
      })}

      {systemInfo && (
         <Alert className="bg-muted/50 border-dashed">
            <Server className="h-4 w-4" />
            <AlertTitle>System Capacity</AlertTitle>
            <AlertDescription className="text-xs text-muted-foreground mt-1">
              Your host has {systemInfo.cpu_cores} CPUs and {Math.round(systemInfo.total_memory_mb / 1024)}GB RAM. 
              SKUs exceeding these limits are disabled.
            </AlertDescription>
         </Alert>
      )}
    </div>
  );
}
