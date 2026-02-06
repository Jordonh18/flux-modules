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
  { id: 'd1', name: 'D1', description: 'Development / Testing', memoryMb: 2048, cpus: 1, storageGb: 20 },
  { id: 'd2', name: 'D2', description: 'Small Production', memoryMb: 4096, cpus: 2, storageGb: 50, recommended: true },
  { id: 'd4', name: 'D4', description: 'Standard Production', memoryMb: 8192, cpus: 4, storageGb: 100 },
  { id: 'd8', name: 'D8', description: 'Large Workloads', memoryMb: 16384, cpus: 8, storageGb: 200 },
  { id: 'd16', name: 'D16', description: 'Enterprise Scale', memoryMb: 32768, cpus: 16, storageGb: 500 },
  { id: 'custom', name: 'Custom', description: 'Configure your own', memoryMb: 0, cpus: 0, storageGb: 0 },
];
