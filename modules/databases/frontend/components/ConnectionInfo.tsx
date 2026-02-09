import { useState } from 'react';
import { Copy, Eye, EyeOff, Check, Terminal } from 'lucide-react';
import { toast } from 'sonner';
import { DatabaseInstance } from '../types/database';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

interface ConnectionInfoProps {
  instance: DatabaseInstance;
}

export function ConnectionInfo({ instance }: ConnectionInfoProps) {
  const [showPassword, setShowPassword] = useState(false);
  const [copiedField, setCopiedField] = useState<string | null>(null);

  const copyToClipboard = (text: string, label: string) => {
    navigator.clipboard.writeText(text);
    setCopiedField(label);
    toast.success(`${label} copied to clipboard`);
    
    setTimeout(() => {
      setCopiedField(null);
    }, 2000);
  };

  const ConnectionField = ({ 
    label, 
    value, 
    isPassword = false,
    copyable = true 
  }: { 
    label: string; 
    value: string | number; 
    isPassword?: boolean;
    copyable?: boolean;
  }) => (
    <div className="space-y-1.5">
      <Label className="text-xs text-muted-foreground">{label}</Label>
      <div className="flex gap-2">
        <div className="relative flex-1">
          <Input 
            readOnly 
            value={value} 
            type={isPassword && !showPassword ? "password" : "text"}
            className="font-mono text-sm bg-muted/30 pr-10"
          />
          {isPassword && (
            <button
              onClick={() => setShowPassword(!showPassword)}
              className="absolute right-3 top-2.5 text-muted-foreground hover:text-foreground"
            >
              {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
          )}
        </div>
        {copyable && (
          <Button
            variant="outline"
            size="icon"
            onClick={() => copyToClipboard(String(value), label)}
            className="shrink-0"
          >
            {copiedField === label ? (
              <Check className="h-4 w-4 text-green-500" />
            ) : (
              <Copy className="h-4 w-4" />
            )}
          </Button>
        )}
      </div>
    </div>
  );

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <Terminal className="h-5 w-5 text-primary" />
          Connection Details
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <ConnectionField 
          label="Connection String" 
          value={instance.connection_string || 'Pending...'} 
        />
        
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <ConnectionField label="Host" value={instance.host} />
          <ConnectionField label="Port" value={instance.port} />
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <ConnectionField label="Username" value={instance.username} />
          <ConnectionField 
            label="Password" 
            value={instance.password || '••••••••'} 
            isPassword 
          />
        </div>

        {instance.database && (
           <ConnectionField label="Database Name" value={instance.database} />
        )}
        
        {instance.external_access && (
           <div className="mt-2 rounded-md bg-yellow-500/10 p-3 text-xs text-yellow-600 dark:text-yellow-400 border border-yellow-500/20">
             <strong>Note:</strong> External access is enabled. Ensure your firewall rules allow traffic on port {instance.port}.
           </div>
        )}
      </CardContent>
    </Card>
  );
}
