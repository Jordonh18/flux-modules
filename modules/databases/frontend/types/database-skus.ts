export interface DatabaseSku {
  id: string;
  name: string;
  description: string;
  memoryMb: number;
  cpus: number;
  storageGb: number;
  recommended?: boolean;
  series?: 'burstable' | 'general' | 'memory' | 'compute' | 'custom';
  useCase?: string;
}

export const DATABASE_SKUS: DatabaseSku[] = [
  // B-series: Burstable - Low CPU priority (cpu-shares=512), deprioritized under host contention
  { 
    id: 'b1', 
    name: 'B1', 
    description: 'Burstable', 
    memoryMb: 1024, 
    cpus: 0.5, 
    storageGb: 10,
    series: 'burstable',
    useCase: 'Low CPU priority, yields under host contention'
  },
  { 
    id: 'b2', 
    name: 'B2', 
    description: 'Burstable', 
    memoryMb: 2048, 
    cpus: 1, 
    storageGb: 20,
    series: 'burstable',
    useCase: 'Low CPU priority, yields under host contention'
  },
  { 
    id: 'b4', 
    name: 'B4', 
    description: 'Burstable', 
    memoryMb: 4096, 
    cpus: 2, 
    storageGb: 40,
    series: 'burstable',
    useCase: 'Low CPU priority, yields under host contention'
  },
  
  // D-series: General Purpose - Standard CPU priority (cpu-shares=1024), balanced defaults
  { 
    id: 'd2', 
    name: 'D2', 
    description: 'General Purpose', 
    memoryMb: 4096, 
    cpus: 2, 
    storageGb: 50, 
    recommended: true,
    series: 'general',
    useCase: 'Standard CPU priority, balanced performance'
  },
  { 
    id: 'd4', 
    name: 'D4', 
    description: 'General Purpose', 
    memoryMb: 8192, 
    cpus: 4, 
    storageGb: 100,
    series: 'general',
    useCase: 'Standard CPU priority, balanced performance'
  },
  { 
    id: 'd8', 
    name: 'D8', 
    description: 'General Purpose', 
    memoryMb: 16384, 
    cpus: 8, 
    storageGb: 200,
    series: 'general',
    useCase: 'Standard CPU priority, balanced performance'
  },
  { 
    id: 'd16', 
    name: 'D16', 
    description: 'General Purpose', 
    memoryMb: 32768, 
    cpus: 16, 
    storageGb: 500,
    series: 'general',
    useCase: 'Standard CPU priority, balanced performance'
  },
  { 
    id: 'd32', 
    name: 'D32', 
    description: 'General Purpose', 
    memoryMb: 65536, 
    cpus: 32, 
    storageGb: 1024,
    series: 'general',
    useCase: 'Standard CPU priority, balanced performance'
  },
  { 
    id: 'd64', 
    name: 'D64', 
    description: 'General Purpose', 
    memoryMb: 131072, 
    cpus: 64, 
    storageGb: 2048,
    series: 'general',
    useCase: 'Standard CPU priority, balanced performance'
  },
  
  // E-series: Memory Optimized - No swap (swappiness=0), OOM protection (oom-score-adj=-500)
  { 
    id: 'e2', 
    name: 'E2', 
    description: 'Memory Optimized', 
    memoryMb: 8192, 
    cpus: 2, 
    storageGb: 50,
    series: 'memory',
    useCase: 'No swap, OOM kill protection, keeps data in RAM'
  },
  { 
    id: 'e4', 
    name: 'E4', 
    description: 'Memory Optimized', 
    memoryMb: 16384, 
    cpus: 4, 
    storageGb: 100,
    series: 'memory',
    useCase: 'No swap, OOM kill protection, keeps data in RAM'
  },
  { 
    id: 'e8', 
    name: 'E8', 
    description: 'Memory Optimized', 
    memoryMb: 32768, 
    cpus: 8, 
    storageGb: 200,
    series: 'memory',
    useCase: 'No swap, OOM kill protection, keeps data in RAM'
  },
  { 
    id: 'e16', 
    name: 'E16', 
    description: 'Memory Optimized', 
    memoryMb: 65536, 
    cpus: 16, 
    storageGb: 500,
    series: 'memory',
    useCase: 'No swap, OOM kill protection, keeps data in RAM'
  },
  { 
    id: 'e32', 
    name: 'E32', 
    description: 'Memory Optimized', 
    memoryMb: 131072, 
    cpus: 32, 
    storageGb: 1024,
    series: 'memory',
    useCase: 'No swap, OOM kill protection, keeps data in RAM'
  },
  { 
    id: 'e64', 
    name: 'E64', 
    description: 'Memory Optimized', 
    memoryMb: 262144, 
    cpus: 64, 
    storageGb: 2048,
    series: 'memory',
    useCase: 'No swap, OOM kill protection, keeps data in RAM'
  },
  
  // F-series: Compute Optimized - High CPU priority (cpu-shares=2048), strict no-swap
  { 
    id: 'f2', 
    name: 'F2', 
    description: 'Compute Optimized', 
    memoryMb: 2048, 
    cpus: 2, 
    storageGb: 30,
    series: 'compute',
    useCase: 'High CPU priority, strict no-swap, favored under contention'
  },
  { 
    id: 'f4', 
    name: 'F4', 
    description: 'Compute Optimized', 
    memoryMb: 4096, 
    cpus: 4, 
    storageGb: 60,
    series: 'compute',
    useCase: 'High CPU priority, strict no-swap, favored under contention'
  },
  { 
    id: 'f8', 
    name: 'F8', 
    description: 'Compute Optimized', 
    memoryMb: 8192, 
    cpus: 8, 
    storageGb: 120,
    series: 'compute',
    useCase: 'High CPU priority, strict no-swap, favored under contention'
  },
  { 
    id: 'f16', 
    name: 'F16', 
    description: 'Compute Optimized', 
    memoryMb: 16384, 
    cpus: 16, 
    storageGb: 240,
    series: 'compute',
    useCase: 'High CPU priority, strict no-swap, favored under contention'
  },
  { 
    id: 'f32', 
    name: 'F32', 
    description: 'Compute Optimized', 
    memoryMb: 32768, 
    cpus: 32, 
    storageGb: 480,
    series: 'compute',
    useCase: 'High CPU priority, strict no-swap, favored under contention'
  },
  { 
    id: 'f64', 
    name: 'F64', 
    description: 'Compute Optimized', 
    memoryMb: 65536, 
    cpus: 64, 
    storageGb: 960,
    series: 'compute',
    useCase: 'High CPU priority, strict no-swap, favored under contention'
  },
  
  // Custom: User-defined resources, general purpose behavior
  { 
    id: 'custom', 
    name: 'Custom', 
    description: 'Custom Configuration', 
    memoryMb: 0, 
    cpus: 0, 
    storageGb: 0,
    series: 'custom',
    useCase: 'Define exact resources, uses general purpose behavior'
  },
];
