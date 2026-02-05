/**
 * Databases Module - Database Page
 *
 * Database management page for Flux.
 * Currently a placeholder - functionality to be added.
 */

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Database } from 'lucide-react';

export default function DatabasePage() {
  return (
    <div className="container mx-auto py-6">
      <div className="mb-6">
        <h1 className="text-3xl font-bold tracking-tight">Database</h1>
        <p className="text-muted-foreground">
          Database management and exploration
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Database className="h-5 w-5" />
            Database Explorer
          </CardTitle>
          <CardDescription>
            View and manage database tables and data
          </CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-muted-foreground">
            Database functionality coming soon.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
