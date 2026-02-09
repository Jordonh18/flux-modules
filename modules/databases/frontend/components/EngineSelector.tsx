import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Search, Info } from 'lucide-react';
import {
  EngineInfo,
  CATEGORY_INFO,
  ENGINE_ICONS,
  DatabaseCategory,
} from '../types/database';
import { cn } from '@/lib/utils';
import { Skeleton } from '@/components/ui/skeleton';

interface EngineSelectorProps {
  selected?: string;
  onSelect: (engine: string) => void;
}

export function EngineSelector({ selected, onSelect }: EngineSelectorProps) {
  const [searchTerm, setSearchTerm] = useState('');

  const { data: engines, isLoading } = useQuery<EngineInfo[]>({
    queryKey: ['database-engines'],
    queryFn: async () => {
      const response = await api.get('/modules/databases/engines');
      return response.data;
    },
  });

  const filteredEngines = useMemo(() => {
    if (!engines) return [];
    if (!searchTerm) return engines;
    const term = searchTerm.toLowerCase();
    return engines.filter(
      (e) =>
        e.display_name.toLowerCase().includes(term) ||
        e.engine.toLowerCase().includes(term) ||
        e.category.toLowerCase().includes(term)
    );
  }, [engines, searchTerm]);

  // Group by category
  const groupedEngines = useMemo(() => {
    const groups: Partial<Record<DatabaseCategory, EngineInfo[]>> = {};
    
    // Initialize groups based on Category Info order for consistent display
    (Object.keys(CATEGORY_INFO) as DatabaseCategory[]).forEach(cat => {
      groups[cat] = [];
    });

    filteredEngines.forEach((engine) => {
      if (!groups[engine.category]) {
        groups[engine.category] = [];
      }
      groups[engine.category]!.push(engine);
    });
    
    // Remove empty groups
    return Object.entries(groups).filter(([_, list]) => list && list.length > 0) as [DatabaseCategory, EngineInfo[]][];
  }, [filteredEngines]);

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-full" />
        <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-4">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <Skeleton key={i} className="h-32 w-full" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="relative">
        <Search className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
        <Input
          placeholder="Search database engines..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          className="pl-9"
        />
      </div>

      {groupedEngines.length === 0 ? (
        <div className="py-8 text-center text-muted-foreground">
          No database engines found matching your search.
        </div>
      ) : (
        <div className="space-y-8">
          {groupedEngines.map(([category, categoryEngines]) => (
            <div key={category} className="space-y-3">
              <div className="flex items-center gap-2 border-b pb-2">
                <div
                  className={cn(
                    "h-3 w-3 rounded-full",
                    CATEGORY_INFO[category].color
                  )}
                />
                <h3 className="font-medium text-foreground">
                  {CATEGORY_INFO[category].label}
                </h3>
                <Badge variant="secondary" className="ml-auto text-xs">
                  {categoryEngines.length}
                </Badge>
              </div>

              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4">
                {categoryEngines.map((engine) => (
                  <Card
                    key={engine.engine}
                    className={cn(
                      "cursor-pointer transition-all hover:border-primary/50 hover:shadow-sm",
                      selected === engine.engine
                        ? "border-primary ring-1 ring-primary"
                        : "border-border"
                    )}
                    onClick={() => onSelect(engine.engine)}
                  >
                    <div className="p-4">
                      <div className="flex items-start justify-between">
                        <div className="text-3xl" role="img" aria-label={engine.display_name}>
                          {ENGINE_ICONS[engine.engine] || '💾'}
                        </div>
                        {selected === engine.engine && (
                          <div className="h-2 w-2 rounded-full bg-primary" />
                        )}
                      </div>
                      
                      <div className="mt-4">
                        <h4 className="font-semibold">{engine.display_name}</h4>
                        <p className="mt-1 text-xs text-muted-foreground">
                          {engine.description}
                        </p>
                      </div>

                      <div className="mt-3 flex flex-wrap gap-1">
                        {engine.is_embedded && (
                          <Badge variant="outline" className="text-[10px] h-5 px-1.5">
                            Embedded
                          </Badge>
                        )}
                        {!engine.supports_users && (
                          <Badge variant="secondary" className="text-[10px] h-5 px-1.5 opacity-70" title="No user management">
                            No Users
                          </Badge>
                        )}
                      </div>
                    </div>
                  </Card>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
