export interface DatabaseSku {
  id: string;
  name: string;
  description: string;
  memoryMb: number;
  cpus: number;
  storageGb: number;
  recommended?: boolean;
}

export const DATABASE_SKUS: DatabaseSku[] = [
  // B-series: Burstable (Cost-Effective)
  { id: 'b1', name: 'B1 Burstable', description: '1 GB RAM, 0.5 vCPU - Dev/Test', memoryMb: 1024, cpus: 0.5, storageGb: 10 },
  { id: 'b2', name: 'B2 Burstable', description: '2 GB RAM, 1 vCPU - Low traffic apps', memoryMb: 2048, cpus: 1, storageGb: 20 },
  { id: 'b4', name: 'B4 Burstable', description: '4 GB RAM, 2 vCPU - Variable workloads', memoryMb: 4096, cpus: 2, storageGb: 40 },
  
  // D-series: General Purpose (Balanced)
  { id: 'd2', name: 'D2 General Purpose', description: '4 GB RAM, 2 vCPU - Small production', memoryMb: 4096, cpus: 2, storageGb: 50, recommended: true },
  { id: 'd4', name: 'D4 General Purpose', description: '8 GB RAM, 4 vCPU - Standard production', memoryMb: 8192, cpus: 4, storageGb: 100 },
  { id: 'd8', name: 'D8 General Purpose', description: '16 GB RAM, 8 vCPU - Large workloads', memoryMb: 16384, cpus: 8, storageGb: 200 },
  { id: 'd16', name: 'D16 General Purpose', description: '32 GB RAM, 16 vCPU - Enterprise scale', memoryMb: 32768, cpus: 16, storageGb: 500 },
  { id: 'd32', name: 'D32 General Purpose', description: '64 GB RAM, 32 vCPU - Mission critical', memoryMb: 65536, cpus: 32, storageGb: 1024 },
  { id: 'd64', name: 'D64 General Purpose', description: '128 GB RAM, 64 vCPU - Maximum scale', memoryMb: 131072, cpus: 64, storageGb: 2048 },
  
  // E-series: Memory Optimized (High RAM)
  { id: 'e2', name: 'E2 Memory Optimized', description: '8 GB RAM, 2 vCPU - Memory intensive', memoryMb: 8192, cpus: 2, storageGb: 50 },
  { id: 'e4', name: 'E4 Memory Optimized', description: '16 GB RAM, 4 vCPU - In-memory databases', memoryMb: 16384, cpus: 4, storageGb: 100 },
  { id: 'e8', name: 'E8 Memory Optimized', description: '32 GB RAM, 8 vCPU - Large caches', memoryMb: 32768, cpus: 8, storageGb: 200 },
  { id: 'e16', name: 'E16 Memory Optimized', description: '64 GB RAM, 16 vCPU - Analytics workloads', memoryMb: 65536, cpus: 16, storageGb: 500 },
  { id: 'e32', name: 'E32 Memory Optimized', description: '128 GB RAM, 32 vCPU - Data warehousing', memoryMb: 131072, cpus: 32, storageGb: 1024 },
  { id: 'e64', name: 'E64 Memory Optimized', description: '256 GB RAM, 64 vCPU - SAP/HANA scale', memoryMb: 262144, cpus: 64, storageGb: 2048 },
  
  // F-series: Compute Optimized (High CPU)
  { id: 'f2', name: 'F2 Compute Optimized', description: '2 GB RAM, 2 vCPU - CPU intensive apps', memoryMb: 2048, cpus: 2, storageGb: 30 },
  { id: 'f4', name: 'F4 Compute Optimized', description: '4 GB RAM, 4 vCPU - Batch processing', memoryMb: 4096, cpus: 4, storageGb: 60 },
  { id: 'f8', name: 'F8 Compute Optimized', description: '8 GB RAM, 8 vCPU - Analytics engines', memoryMb: 8192, cpus: 8, storageGb: 120 },
  { id: 'f16', name: 'F16 Compute Optimized', description: '16 GB RAM, 16 vCPU - High performance', memoryMb: 16384, cpus: 16, storageGb: 240 },
  { id: 'f32', name: 'F32 Compute Optimized', description: '32 GB RAM, 32 vCPU - HPC workloads', memoryMb: 32768, cpus: 32, storageGb: 480 },
  { id: 'f64', name: 'F64 Compute Optimized', description: '64 GB RAM, 64 vCPU - Maximum compute', memoryMb: 65536, cpus: 64, storageGb: 960 },
  
  // Custom: User-defined
  { id: 'custom', name: 'Custom Configuration', description: 'Define your own resources', memoryMb: 0, cpus: 0, storageGb: 0 },
];
