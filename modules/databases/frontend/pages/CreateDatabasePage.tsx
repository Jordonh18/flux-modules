import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { api } from '@/lib/api';
import { useDocumentTitle } from '@/hooks/use-document-title';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import { Loader2, ChevronRight, ChevronLeft, Database, CheckCircle2 } from 'lucide-react';
import { cn } from '@/lib/utils'; // Assuming global utils for classNames

import { EngineSelector } from '../components/EngineSelector';
import { SkuSelector } from '../components/SkuSelector';
import { CreateDatabaseRequest, ENGINE_ICONS } from '../types/database';

export default function CreateDatabasePage() {
  useDocumentTitle('Create Database');
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  
  const [step, setStep] = useState(1);
  const [formData, setFormData] = useState<Partial<CreateDatabaseRequest>>({
    sku: 'db-std-2', // Default SKU
    external_access: false,
    tls_enabled: false,
  });

  // --- Mutations ---

  const createMutation = useMutation({
    mutationFn: (data: CreateDatabaseRequest) => 
      api.post('/modules/databases/databases', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['databases'] });
      toast.success('Database creation started');
      navigate('/databases');
    },
    onError: (err: any) => {
      toast.error(err.response?.data?.detail || 'Failed to create database');
    },
  });

  // --- Handlers ---

  const handleNext = () => {
    if (step === 1 && !formData.engine) {
      toast.error('Please select a database engine');
      return;
    }
    if (step === 2) {
      if (!formData.name) {
        toast.error('Instance name is required');
        return;
      }
      if (!formData.database_name) {
        toast.error('Database name is required');
        return;
      }
    }
    setStep(step + 1);
  };

  const handleBack = () => setStep(step - 1);

  const handleSubmit = () => {
    if (!formData.engine || !formData.name || !formData.database_name || !formData.sku) {
      toast.error('Missing required fields');
      return;
    }
    
    createMutation.mutate(formData as CreateDatabaseRequest);
  };

  const updateField = (field: keyof CreateDatabaseRequest, value: any) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  // --- Render Steps ---

  const renderStepIndicator = () => (
    <div className="flex items-center justify-center mb-8">
      {[1, 2, 3, 4].map((i) => (
        <div key={i} className="flex items-center">
          <div className={cn(
            "flex items-center justify-center w-8 h-8 rounded-full border-2 text-sm font-bold transition-colors",
            step === i ? "border-primary bg-primary text-primary-foreground" : 
            step > i ? "border-primary bg-primary text-primary-foreground" : "border-muted-foreground text-muted-foreground"
          )}>
            {step > i ? <CheckCircle2 className="w-5 h-5" /> : i}
          </div>
          {i < 4 && (
            <div className={cn(
              "w-12 h-1 mx-2 rounded",
              step > i ? "bg-primary" : "bg-muted"
            )} />
          )}
        </div>
      ))}
    </div>
  );

  return (
    <div className="container max-w-4xl py-6 mx-auto">
      <div className="mb-6">
        <h1 className="text-3xl font-bold tracking-tight">Create Database</h1>
        <p className="text-muted-foreground">
          Deploy a new database instance in seconds.
        </p>
      </div>

      {renderStepIndicator()}

      <Card className="min-h-[400px] flex flex-col">
        <CardHeader>
          <CardTitle>
            {step === 1 && "Select Database Engine"}
            {step === 2 && "Configure Instance"}
            {step === 3 && "Network & Security"}
            {step === 4 && "Review & Create"}
          </CardTitle>
          <CardDescription>
            {step === 1 && "Choose the type of database you want to deploy."}
            {step === 2 && "Set the name, internal database name, and performance tier."}
            {step === 3 && "Configure external access and encryption settings."}
            {step === 4 && "Verify your settings before deployment."}
          </CardDescription>
        </CardHeader>
        
        <CardContent className="flex-1">
          {step === 1 && (
            <EngineSelector 
              selected={formData.engine} 
              onSelect={(engine) => updateField('engine', engine)} 
            />
          )}

          {step === 2 && (
            <div className="space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="name">Instance Name</Label>
                  <Input 
                    id="name" 
                    placeholder="my-postgres-prod" 
                    value={formData.name || ''}
                    onChange={(e) => updateField('name', e.target.value)}
                  />
                  <p className="text-xs text-muted-foreground">The display name for this instance in Flux.</p>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="dbname">Database Name</Label>
                  <Input 
                    id="dbname" 
                    placeholder="app_db" 
                    value={formData.database_name || ''}
                    onChange={(e) => updateField('database_name', e.target.value)}
                  />
                  <p className="text-xs text-muted-foreground">The initial internal database to create.</p>
                </div>
              </div>
              
              <div className="space-y-2">
                <Label>Performance Tier (SKU)</Label>
                <div className="h-[300px] overflow-y-auto border rounded-md p-2">
                   <SkuSelector 
                     selected={formData.sku || ''}
                     onSelect={(sku) => updateField('sku', sku)}
                   />
                </div>
              </div>
            </div>
          )}

          {step === 3 && (
            <div className="space-y-6 max-w-md">
              <div className="flex items-start space-x-3 p-4 border rounded-md">
                <Checkbox 
                  id="external" 
                  checked={formData.external_access}
                  onCheckedChange={(c) => updateField('external_access', !!c)}
                />
                <div className="grid gap-1.5 leading-none">
                  <Label htmlFor="external" className="text-base font-medium">Enable External Access</Label>
                  <p className="text-sm text-muted-foreground">
                    Expose this database on a random host port. Required if you need to connect from outside the cluster.
                  </p>
                </div>
              </div>

              <div className="flex items-start space-x-3 p-4 border rounded-md">
                <Checkbox 
                  id="tls" 
                  checked={formData.tls_enabled}
                  onCheckedChange={(c) => updateField('tls_enabled', !!c)}
                />
                <div className="grid gap-1.5 leading-none">
                  <Label htmlFor="tls" className="text-base font-medium">Enable TLS/SSL</Label>
                  <p className="text-sm text-muted-foreground">
                    Encrypt connections with self-signed certificates or provide your own custom certs later.
                  </p>
                </div>
              </div>
              
              <div className="space-y-2">
                 <Label>VNet (Optional)</Label>
                 <Input 
                   placeholder="default" 
                   value={formData.vnet_name || ''}
                   onChange={(e) => updateField('vnet_name', e.target.value)}
                 />
                 <p className="text-xs text-muted-foreground">Attach to a specific virtual network for container-to-container communication.</p>
              </div>
            </div>
          )}

          {step === 4 && (
            <div className="space-y-4">
              <div className="bg-muted/50 p-4 rounded-md space-y-3">
                <div className="grid grid-cols-2 gap-2 text-sm">
                  <span className="text-muted-foreground">Engine:</span>
                  <span className="font-medium flex items-center gap-2">
                    {formData.engine && <span className="text-lg">{ENGINE_ICONS[formData.engine]}</span>}
                    {formData.engine}
                  </span>
                  
                  <span className="text-muted-foreground">Instance Name:</span>
                  <span className="font-medium">{formData.name}</span>
                  
                  <span className="text-muted-foreground">Database Name:</span>
                  <span className="font-medium">{formData.database_name}</span>
                  
                  <span className="text-muted-foreground">SKU:</span>
                  <span className="font-medium">{formData.sku?.toUpperCase()}</span>
                  
                  <span className="text-muted-foreground">Access:</span>
                  <span className="font-medium">{formData.external_access ? 'External (Public Port)' : 'Internal Only'}</span>
                  
                  <span className="text-muted-foreground">Encryption:</span>
                  <span className="font-medium">{formData.tls_enabled ? 'TLS Enabled' : 'None'}</span>
                </div>
              </div>
              <p className="text-sm text-muted-foreground">
                Clicking Create will provision a new container. This may take a few moments depending on the image size.
              </p>
            </div>
          )}
        </CardContent>
        
        <CardFooter className="flex justify-between border-t pt-6">
          <Button 
            variant="outline" 
            onClick={step === 1 ? () => navigate('/databases') : handleBack}
            disabled={createMutation.isPending}
          >
            {step === 1 ? 'Cancel' : <><ChevronLeft className="mr-2 h-4 w-4" /> Back</>}
          </Button>
          
          <Button 
            onClick={step === 4 ? handleSubmit : handleNext} 
            disabled={createMutation.isPending}
          >
             {createMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
             {step === 4 ? 'Create Database' : <>{step === 1 ? 'Next: Configure' : 'Next'} <ChevronRight className="ml-2 h-4 w-4" /></>}
          </Button>
        </CardFooter>
      </Card>
    </div>
  );
}
