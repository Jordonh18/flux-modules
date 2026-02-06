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
  // B-series: Burstable (Cost-Effective)
  { 
    id: 'b1', 
    name: 'B1', 
    description: 'Burstable', 
    memoryMb: 1024, 
    cpus: 0.5, 
    storageGb: 10,
    series: 'burstable',
    useCase: 'Dev/test environments with minimal traffic'
  },
  { 
    id: 'b2', 
    name: 'B2', 
    description: 'Burstable', 
    memoryMb: 2048, 
    cpus: 1, 
    storageGb: 20,
    series: 'burstable',
    useCase: 'Small apps with variable CPU usage patterns'
  },
  { 
    id: 'b4', 
    name: 'B4', 
    description: 'Burstable', 
    memoryMb: 4096, 
    cpus: 2, 
    storageGb: 40,
    series: 'burstable',
    useCase: 'Staging environments that don\'t run 24/7'
  },
  
  // D-series: General Purpose (Balanced)
  { 
    id: 'd2', 
    name: 'D2', 
    description: 'General Purpose', 
    memoryMb: 4096, 
    cpus: 2, 
    storageGb: 50, 
    recommended: true,
    series: 'general',
    useCase: 'Balanced workloads, web apps, small APIs'
  },
  { 
    id: 'd4', 
    name: 'D4', 
    description: 'General Purpose', 
    memoryMb: 8192, 
    cpus: 4, 
    storageGb: 100,
    series: 'general',
    useCase: 'Production apps with steady traffic'
  },
  { 
    id: 'd8', 
    name: 'D8', 
    description: 'General Purpose', 
    memoryMb: 16384, 
    cpus: 8, 
    storageGb: 200,
    series: 'general',
    useCase: 'High-traffic apps, e-commerce sites'
  },
  { 
    id: 'd16', 
    name: 'D16', 
    description: 'General Purpose', 
    memoryMb: 32768, 
    cpus: 16, 
    storageGb: 500,
    series: 'general',
    useCase: 'Large-scale production workloads'
  },
  { 
    id: 'd32', 
    name: 'D32', 
    description: 'General Purpose', 
    memoryMb: 65536, 
    cpus: 32, 
    storageGb: 1024,
    series: 'general',
    useCase: 'Mission-critical enterprise applications'
  },
  { 
    id: 'd64', 
    name: 'D64', 
    description: 'General Purpose', 
    memoryMb: 131072, 
    cpus: 64, 
    storageGb: 2048,
    series: 'general',
    useCase: 'Maximum scale general-purpose workloads'
  },
  
  // E-series: Memory Optimized (High RAM)
  { 
    id: 'e2', 
    name: 'E2', 
    description: 'Memory Optimized', 
    memoryMb: 8192, 
    cpus: 2, 
    storageGb: 50,
    series: 'memory',
    useCase: 'Redis cache, session stores'
  },
  { 
    id: 'e4', 
    name: 'E4', 
    description: 'Memory Optimized', 
    memoryMb: 16384, 
    cpus: 4, 
    storageGb: 100,
    series: 'memory',
    useCase: 'In-memory databases, large caches'
  },
  { 
    id: 'e8', 
    name: 'E8', 
    description: 'Memory Optimized', 
    memoryMb: 32768, 
    cpus: 8, 
    storageGb: 200,
    series: 'memory',
    useCase: 'MongoDB with large datasets, Elasticsearch'
  },
  { 
    id: 'e16', 
    name: 'E16', 
    description: 'Memory Optimized', 
    memoryMb: 65536, 
    cpus: 16, 
    storageGb: 500,
    series: 'memory',
    useCase: 'Analytics, real-time data processing'
  },
  { 
    id: 'e32', 
    name: 'E32', 
    description: 'Memory Optimized', 
    memoryMb: 131072, 
    cpus: 32, 
    storageGb: 1024,
    series: 'memory',
    useCase: 'Data warehouses, big data analytics'
  },
  { 
    id: 'e64', 
    name: 'E64', 
    description: 'Memory Optimized', 
    memoryMb: 262144, 
    cpus: 64, 
    storageGb: 2048,
    series: 'memory',
    useCase: 'SAP HANA, massive in-memory workloads'
  },
  
  // F-series: Compute Optimized (High CPU)
  { 
    id: 'f2', 
    name: 'F2', 
    description: 'Compute Optimized', 
    memoryMb: 2048, 
    cpus: 2, 
    storageGb: 30,
    series: 'compute',
    useCase: 'CPU-heavy queries, batch processing'
  },
  { 
    id: 'f4', 
    name: 'F4', 
    description: 'Compute Optimized', 
    memoryMb: 4096, 
    cpus: 4, 
    storageGb: 60,
    series: 'compute',
    useCase: 'Complex calculations, data transformations'
  },
  { 
    id: 'f8', 
    name: 'F8', 
    description: 'Compute Optimized', 
    memoryMb: 8192, 
    cpus: 8, 
    storageGb: 120,
    series: 'compute',
    useCase: 'Analytics engines, computational workloads'
  },
  { 
    id: 'f16', 
    name: 'F16', 
    description: 'Compute Optimized', 
    memoryMb: 16384, 
    cpus: 16, 
    storageGb: 240,
    series: 'compute',
    useCase: 'High-performance computing tasks'
  },
  { 
    id: 'f32', 
    name: 'F32', 
    description: 'Compute Optimized', 
    memoryMb: 32768, 
    cpus: 32, 
    storageGb: 480,
    series: 'compute',
    useCase: 'Parallel processing, scientific computing'
  },
  { 
    id: 'f64', 
    name: 'F64', 
    description: 'Compute Optimized', 
    memoryMb: 65536, 
    cpus: 64, 
    storageGb: 960,
    series: 'compute',
    useCase: 'Maximum CPU for intensive computation'
  },
  
  // Custom: User-defined
  { 
    id: 'custom', 
    name: 'Custom', 
    description: 'Custom Configuration', 
    memoryMb: 0, 
    cpus: 0, 
    storageGb: 0,
    series: 'custom',
    useCase: 'Define exact resources for your needs'
  },
];
