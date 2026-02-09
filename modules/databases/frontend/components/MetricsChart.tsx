import { useMemo } from 'react';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend
} from 'recharts';
import { DatabaseMetrics } from '../types/database';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Activity } from 'lucide-react';
import { format } from 'date-fns';

interface MetricsChartProps {
  metrics: DatabaseMetrics | null;
  isLoading: boolean;
  timeRange?: string;
}

export function MetricsChart({ metrics, isLoading }: MetricsChartProps) {
  const chartData = useMemo(() => {
    if (!metrics?.history) return [];
    
    return metrics.history.map(point => ({
      ...point,
      time: new Date(point.timestamp * 1000),
      // Ensure we don't have nulls that break charts
      cpu_percent: point.cpu_percent || 0,
      memory_percent: point.memory_percent || 0,
    })).sort((a, b) => a.time.getTime() - b.time.getTime());
  }, [metrics]);

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
           <Skeleton className="h-6 w-32" />
           <Skeleton className="h-4 w-48" />
        </CardHeader>
        <CardContent>
           <Skeleton className="h-[200px] w-full" />
        </CardContent>
      </Card>
    );
  }

  if (!metrics || chartData.length === 0) {
    return (
      <Card>
        <CardHeader className="pb-2">
           <CardTitle className="text-base flex items-center gap-2">
             <Activity className="h-4 w-4" /> Performance Metrics
           </CardTitle>
           <CardDescription>Live resource usage</CardDescription>
        </CardHeader>
        <CardContent className="h-[250px] flex items-center justify-center text-muted-foreground">
           No metrics data available
        </CardContent>
      </Card>
    );
  }

  const formatTime = (date: Date) => format(date, 'HH:mm');
  const formatValue = (val: number) => `${val.toFixed(1)}%`;

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="text-base flex items-center gap-2">
              <Activity className="h-4 w-4 text-primary" /> 
              Performance Metrics
            </CardTitle>
            <CardDescription>
              CPU: {metrics.current.cpu_percent.toFixed(1)}% | 
              Mem: {metrics.current.memory_percent.toFixed(1)}% ({metrics.current.memory_used_mb}MB)
            </CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <div className="h-[250px] w-full mt-2">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart
              data={chartData}
              margin={{
                top: 5,
                right: 0,
                left: 0,
                bottom: 0,
              }}
            >
              <defs>
                <linearGradient id="colorCpu" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#8b5cf6" stopOpacity={0.3}/>
                  <stop offset="95%" stopColor="#8b5cf6" stopOpacity={0}/>
                </linearGradient>
                <linearGradient id="colorMem" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#06b6d4" stopOpacity={0.3}/>
                  <stop offset="95%" stopColor="#06b6d4" stopOpacity={0}/>
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" opacity={0.2} vertical={false} />
              <XAxis 
                dataKey="time" 
                tickFormatter={formatTime}
                stroke="#888888"
                fontSize={12}
                tickLine={false}
                axisLine={false}
                minTickGap={30}
              />
              <YAxis 
                tickFormatter={(val) => `${val}%`}
                stroke="#888888"
                fontSize={12}
                tickLine={false}
                axisLine={false}
                domain={[0, (dataMax: number) => Math.min(100, Math.max(dataMax * 1.2, 5))]}
              />
              <Tooltip 
                labelFormatter={(label) => format(label as Date, 'PP pp')}
                formatter={(value: number) => [formatValue(value)]}
                contentStyle={{ 
                  borderRadius: 'var(--radius)', 
                  border: '1px solid var(--border)',
                  backgroundColor: 'var(--background)',
                  color: 'var(--foreground)'
                }}
              />
              <Legend iconType="circle" />
              <Area 
                type="monotone" 
                dataKey="cpu_percent" 
                name="CPU Usage"
                stroke="#8b5cf6" 
                fillOpacity={1} 
                fill="url(#colorCpu)" 
                strokeWidth={2}
              />
              <Area 
                type="monotone" 
                dataKey="memory_percent" 
                name="Memory Usage"
                stroke="#06b6d4" 
                fillOpacity={1} 
                fill="url(#colorMem)" 
                strokeWidth={2}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}
