/**
 * Databases Module - Database Page
 *
 * Database management page for Flux.
 * Currently a placeholder - functionality to be added.
 */

import { Card, CardContent } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { useDocumentTitle } from '@/hooks/use-document-title';

export default function DatabasesPage() {
  useDocumentTitle('Databases');

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold">Databases</h1>
          <p className="text-muted-foreground">View and manage database tables and data</p>
        </div>
      </div>

      {/* Databases table */}
      <Card className="gap-0 py-0">
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="px-4">Table Name</TableHead>
                <TableHead className="px-4">Rows</TableHead>
                <TableHead className="px-4">Size</TableHead>
                <TableHead className="px-4 text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <TableRow>
                <TableCell className="px-4 text-muted-foreground" colSpan={4}>
                  Database functionality coming soon.
                </TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
