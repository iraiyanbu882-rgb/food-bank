import React from 'react';
import { Scale } from 'lucide-react';
import { PageHeader } from '../../components/ui/PageHeader.jsx';
import { RealOptimizerPanel } from './components/RealOptimizerPanel.jsx';

export default function AllocationPage() {
  return (
    <div className="space-y-5">
      <PageHeader
        title="Allocation Planning & Optimization"
        subtitle="SCIP mixed-integer optimization for food donation collection, routing, and equitable distribution"
        icon={Scale}
      />
      <RealOptimizerPanel />
    </div>
  );
}
