import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import { Activity, AlertCircle, AlertTriangle, CheckCircle2 } from 'lucide-react';

interface HealthBadgeProps {
  status: string;
  size?: 'sm' | 'md' | 'lg';
  showIcon?: boolean;
  className?: string;
}

export function HealthBadge({ 
  status, 
  size = 'md', 
  showIcon = true,
  className 
}: HealthBadgeProps) {
  const normalizedStatus = status?.toLowerCase() || 'unknown';

  const config = {
    healthy: {
      label: 'Healthy',
      variant: 'default', // Custom classes below
      icon: CheckCircle2,
      style: 'bg-green-500/15 text-green-700 hover:bg-green-500/25 dark:text-green-400 border-green-500/20'
    },
    running: { // Alias for healthy in some contexts
      label: 'Running',
      variant: 'default',
      icon: Activity,
      style: 'bg-green-500/15 text-green-700 hover:bg-green-500/25 dark:text-green-400 border-green-500/20'
    },
    unhealthy: {
      label: 'Unhealthy',
      variant: 'destructive',
      icon: AlertCircle,
      style: 'bg-red-500/15 text-red-700 hover:bg-red-500/25 dark:text-red-400 border-red-500/20'
    },
    error: {
      label: 'Error',
      variant: 'destructive',
      icon: AlertCircle,
      style: 'bg-red-500/15 text-red-700 hover:bg-red-500/25 dark:text-red-400 border-red-500/20'
    },
    degraded: {
      label: 'Degraded',
      variant: 'secondary',
      icon: AlertTriangle,
      style: 'bg-yellow-500/15 text-yellow-700 hover:bg-yellow-500/25 dark:text-yellow-400 border-yellow-500/20'
    },
    creating: {
      label: 'Creating',
      variant: 'outline',
      icon: Activity,
      style: 'bg-blue-500/15 text-blue-700 hover:bg-blue-500/25 dark:text-blue-400 border-blue-500/20 animate-pulse'
    },
    stopped: {
      label: 'Stopped',
      variant: 'secondary',
      icon: Activity,
      style: 'bg-slate-500/15 text-slate-700 hover:bg-slate-500/25 dark:text-slate-400 border-slate-500/20'
    },
    unknown: {
      label: 'Unknown',
      variant: 'secondary',
      icon: Activity,
      style: 'bg-gray-500/15 text-gray-700 hover:bg-gray-500/25 dark:text-gray-400 border-gray-500/20'
    },
  };

  // Get config or default to unknown
  const statusConfig = config[normalizedStatus as keyof typeof config] || config.unknown;
  const Icon = statusConfig.icon;

  const sizeClasses = {
    sm: 'px-1.5 py-0.5 text-[10px]',
    md: 'px-2.5 py-0.5 text-xs',
    lg: 'px-3 py-1 text-sm'
  };

  const iconSizes = {
    sm: 'h-3 w-3 mr-1',
    md: 'h-3.5 w-3.5 mr-1.5',
    lg: 'h-4 w-4 mr-2'
  };

  return (
    <Badge 
      variant="outline" 
      className={cn(
        "font-medium border shadow-sm transition-colors",
        statusConfig.style,
        sizeClasses[size],
        className
      )}
    >
      {showIcon && <Icon className={iconSizes[size]} />}
      {statusConfig.label}
    </Badge>
  );
}
