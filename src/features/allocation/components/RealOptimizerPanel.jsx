import React, { useEffect, useMemo, useState } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import {
  AlertTriangle,
  Download,
  FileText,
  Play,
  Save,
  Scale,
} from 'lucide-react';
import { apiClient } from '../../../services/apiClient.js';

const EMPTY_COSTS = {
  food_procurement_cost_per_kg: '',
  transportation_cost_per_km_kg: '',
  facility_opening_cost: '',
  storage_expansion_cost_per_kg: '',
  vehicle_hiring_cost: '',
  staff_hiring_cost: '',
  uncollected_donation_penalty_per_kg: '',
  unused_food_penalty_per_kg: '',
  unmet_demand_penalty_per_packet: '',
};

const JSON_SECTIONS = [
  {
    key: 'donors',
    title: 'Food donors',
    fields: 'id, name, location, latitude, longitude, available_food_items[]',
    example:
      '[{"id":"donor-1","name":"Local Market","location":"Chennai","latitude":13.08,"longitude":80.27,"available_food_items":[{"food_item":"Rice","quantity_kg":500,"expiry_date":null,"donation_frequency":"ONCE"}]}]',
  },
  {
    key: 'facilities',
    title: 'Foodbanks and FRRAs',
    fields:
      'id, name, facility_type (TIER_I/TIER_II), location, coordinates, storage/transport capacities, workforce capacities',
    example:
      '[{"id":"bank-1","name":"Central Foodbank","facility_type":"TIER_I","location":"Chennai","latitude":13.08,"longitude":80.27,"initial_storage_capacity_kg":1000,"initial_transport_capacity_kg":1500,"existing_paid_employees":2,"existing_volunteers":3,"existing_vehicles":1,"donation_handling_capacity_kg_per_employee":500,"packet_preparation_capacity_per_employee":100,"storage_expansion_options":[],"vehicle_options":[],"max_additional_staff":5}]',
  },
  {
    key: 'beneficiaries',
    title: 'Beneficiaries and demand',
    fields:
      'id, location, coordinates, number_of_beneficiaries, category (CHILDREN/ADULTS/VULNERABLE), required_food_packets, packet_type, priority_multiplier',
    example:
      '[{"id":"site-1","location":"Chennai North","latitude":13.12,"longitude":80.25,"number_of_beneficiaries":100,"category":"CHILDREN","required_food_packets":100,"packet_type":"standard","priority_multiplier":1}]',
  },
  {
    key: 'packet_types',
    title: 'Packet recipes',
    fields: 'id, name, composition_kg (ingredient quantity in kg per packet)',
    example:
      '[{"id":"standard","name":"Standard food packet","composition_kg":{"Rice":0.3,"Pulses":0.06,"Vegetables":0.2}}]',
  },
];

const COST_FIELDS = [
  ['food_procurement_cost_per_kg', 'Food procurement / kg'],
  ['transportation_cost_per_km_kg', 'Transportation / km / kg'],
  ['facility_opening_cost', 'Facility opening'],
  ['storage_expansion_cost_per_kg', 'Storage expansion / kg'],
  ['vehicle_hiring_cost', 'Vehicle hiring'],
  ['staff_hiring_cost', 'Staff hiring'],
  ['uncollected_donation_penalty_per_kg', 'Uncollected donation / kg'],
  ['unused_food_penalty_per_kg', 'Unused food / kg'],
  ['unmet_demand_penalty_per_packet', 'Unmet demand / packet'],
];

const PALETTE = ['#176B76', '#27856F', '#D99A35', '#60758A', '#C94C4C'];

function localDateValue() {
  const date = new Date();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${date.getFullYear()}-${month}-${day}`;
}

function formatNumber(value, digits = 1) {
  return Number(value || 0).toLocaleString(undefined, {
    maximumFractionDigits: digits,
  });
}

function downloadCsv(filename, rows) {
  if (!rows.length) return;
  const columns = [...new Set(rows.flatMap(row => Object.keys(row)))];
  const escape = value => {
    const text = value === null || value === undefined ? '' : String(value);
    return `"${text.replaceAll('"', '""')}"`;
  };
  const csv = [
    columns.map(escape).join(','),
    ...rows.map(row => columns.map(column => escape(row[column])).join(',')),
  ].join('\r\n');
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function DataTable({ title, columns, rows, emptyMessage }) {
  return (
    <section className="rounded-xl border border-brand-border bg-white">
      <h3 className="border-b border-brand-border px-4 py-3 text-sm font-bold text-navy-primary">
        {title}
      </h3>
      {rows.length ? (
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-xs">
            <thead className="bg-brand-bg text-text-secondary">
              <tr>
                {columns.map(column => (
                  <th key={column.key} className="whitespace-nowrap px-4 py-2 font-semibold">
                    {column.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-brand-border">
              {rows.map((row, index) => (
                <tr key={`${title}-${index}`}>
                  {columns.map(column => (
                    <td key={column.key} className="whitespace-nowrap px-4 py-2 text-text-primary">
                      {column.render ? column.render(row) : (row[column.key] ?? '—')}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="px-4 py-6 text-xs text-text-secondary">{emptyMessage}</p>
      )}
    </section>
  );
}

function MetricBarChart({ title, data, nameKey, valueKeys, colors = PALETTE }) {
  return (
    <section className="rounded-xl border border-brand-border bg-white p-4">
      <h3 className="mb-3 text-sm font-bold text-navy-primary">{title}</h3>
      <div className="h-56">
        {data.length ? (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 30 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey={nameKey} angle={-15} textAnchor="end" interval={0} height={48} />
              <YAxis />
              <Tooltip />
              {valueKeys.map((key, index) => (
                <Bar key={key.key} dataKey={key.key} name={key.name} fill={colors[index % colors.length]} />
              ))}
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <p className="pt-12 text-center text-xs text-text-secondary">No results for this scenario.</p>
        )}
      </div>
    </section>
  );
}

export function RealOptimizerPanel() {
  const [sections, setSections] = useState(
    Object.fromEntries(JSON_SECTIONS.map(section => [section.key, '']))
  );
  const [costs, setCosts] = useState(EMPTY_COSTS);
  const [planningStartDate, setPlanningStartDate] = useState(localDateValue);
  const [planningDays, setPlanningDays] = useState('7');
  const [budgetCaps, setBudgetCaps] = useState('');
  const [compareEquity, setCompareEquity] = useState(false);
  const [equityWeight, setEquityWeight] = useState('1000');
  const [results, setResults] = useState([]);
  const [selectedResultId, setSelectedResultId] = useState('');
  const [isRunning, setIsRunning] = useState(false);
  const [requestError, setRequestError] = useState('');
  const [savedMessage, setSavedMessage] = useState('');

  useEffect(() => {
    let active = true;
    apiClient('/dataset')
      .then(saved => {
        if (!active) return;
        setSections(previous =>
          Object.fromEntries(
            JSON_SECTIONS.map(section => [
              section.key,
              saved[section.key]?.length
                ? JSON.stringify(saved[section.key], null, 2)
                : '',
            ])
          )
        );
        if (saved.costs) {
          setCosts(
            Object.fromEntries(
              Object.keys(EMPTY_COSTS).map(key => [key, String(saved.costs[key] ?? '')])
            )
          );
        }
        if (saved.planning?.planning_start_date) {
          setPlanningStartDate(saved.planning.planning_start_date);
        }
        if (saved.planning?.planning_days) {
          setPlanningDays(String(saved.planning.planning_days));
        }
      })
      .catch(error => {
        if (active) {
          setRequestError(`Could not load saved inputs: ${error?.message || 'backend unavailable'}`);
        }
      });
    return () => {
      active = false;
    };
  }, []);

  const selectedResult = useMemo(
    () => results.find(result => result.result_id === selectedResultId) || results[0],
    [results, selectedResultId]
  );
  const errorMessage = error => {
    const detail = error?.body?.detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) {
      return detail.map(item => `${item.loc?.slice(-1)[0] || 'Input'}: ${item.msg}`).join('; ');
    }
    return error?.message || 'The optimizer request failed.';
  };

  const buildRequest = () => {
    const missingCosts = COST_FIELDS.filter(([key]) => costs[key] === '').map(([, label]) => label);
    if (missingCosts.length) {
      throw new Error(`Enter all operational costs, using 0 where applicable: ${missingCosts.join(', ')}.`);
    }
    const dataset = {
      donors: JSON.parse(sections.donors),
      facilities: JSON.parse(sections.facilities),
      beneficiaries: JSON.parse(sections.beneficiaries),
      packet_types: JSON.parse(sections.packet_types),
      costs: Object.fromEntries(
        Object.entries(costs).map(([key, value]) => [key, Number(value)])
      ),
      planning_start_date: planningStartDate,
      planning_days: Number(planningDays),
    };
    const caps = budgetCaps
      .split(',')
      .map(value => value.trim())
      .filter(Boolean)
      .map(Number);
    if (caps.some(value => !Number.isFinite(value) || value < 0)) {
      throw new Error('Budget caps must be non-negative numbers separated by commas.');
    }
    if (caps.length > 4) {
      throw new Error('Enter no more than four budget caps per comparison.');
    }
    const scenarios = [
      { name: 'Uncapped cost minimum', budget_cap: null, equity_oriented: false },
      ...caps.map((cap, index) => ({
        name: `Budget scenario ${index + 1}`,
        budget_cap: cap,
        equity_oriented: false,
      })),
    ];
    if (compareEquity) {
      scenarios.push(
        ...[
          { name: 'Uncapped equity priority', budget_cap: null },
          ...caps.map((cap, index) => ({
            name: `Budget ${index + 1} with equity priority`,
            budget_cap: cap,
          })),
        ].map(scenario => ({ ...scenario, equity_oriented: true }))
      );
    }
    return {
      dataset,
      options: {
        scenarios,
        equity_weight: Number(equityWeight),
        solver_time_limit_seconds: 30,
      },
    };
  };

  const runOptimization = async event => {
    event.preventDefault();
    setRequestError('');
    setSavedMessage('');
    setIsRunning(true);
    try {
      const request = buildRequest();
      const response = await apiClient('/optimize', {
        method: 'POST',
        body: JSON.stringify(request),
      });
      setResults(response.results || []);
      setSelectedResultId(response.results?.[0]?.result_id || '');
      if (!response.results?.length) {
        setRequestError('The backend completed the request without returning any scenario results.');
      }
    } catch (error) {
      setRequestError(errorMessage(error));
    } finally {
      setIsRunning(false);
    }
  };

  const saveDataset = async () => {
    setRequestError('');
    setSavedMessage('');
    try {
      const { dataset } = buildRequest();
      const response = await apiClient('/dataset', {
        method: 'PUT',
        body: JSON.stringify(dataset),
      });
      setSavedMessage(
        `Saved ${response.counts.donors} donors, ${response.counts.facilities} facilities, and ${response.counts.beneficiaries} beneficiary records.`
      );
    } catch (error) {
      setRequestError(errorMessage(error));
    }
  };

  const kpis = selectedResult?.kpis;
  const costRows = selectedResult
    ? Object.entries(selectedResult.cost_breakdown || {})
        .filter(
          ([key]) =>
            key !== 'total_operational_cost' &&
            key !== 'mathematical_objective_value'
        )
        .map(([name, value]) => ({ name: name.replaceAll('_', ' '), cost: value }))
    : [];
  const distributionByCategory = selectedResult
    ? Object.values(
        selectedResult.beneficiary_allocations.reduce((groups, row) => {
          const group = groups[row.beneficiary_category] || {
            category: row.beneficiary_category,
            allocated: 0,
            unmet: 0,
          };
          group.allocated += row.packets_allocated;
          group.unmet += row.unmet_demand_packets;
          groups[row.beneficiary_category] = group;
          return groups;
        }, {})
      )
    : [];
  const donatedVsCollected = kpis
    ? [
        { name: 'Donated', kg: kpis.total_donations_available_kg },
        { name: 'Collected', kg: kpis.total_food_collected_kg },
      ]
    : [];
  const wastageData = kpis
    ? [
        { name: 'Uncollected', kg: kpis.total_uncollected_donations_kg },
        { name: 'Unused', kg: kpis.total_unused_food_kg },
        { name: 'Approaching expiry', kg: kpis.food_approaching_expiry_kg },
        { name: 'Expired before plan', kg: kpis.food_expired_before_plan_kg },
      ]
    : [];
  const facilityUtilization = selectedResult
    ? selectedResult.facility_allocations.map(row => ({
        facility: row.facility,
        storage: row.storage_utilization_pct,
        transport: row.transportation_utilization_pct,
      }))
    : [];

  const csvRows = selectedResult
    ? [
        ...selectedResult.donor_allocations.map(row => ({ table: 'donor', ...row })),
        ...selectedResult.facility_allocations.map(row => ({ table: 'facility', ...row })),
      ...selectedResult.food_item_balances.map(row => ({ table: 'food item', ...row })),
      ...selectedResult.beneficiary_allocations.map(row => ({ table: 'beneficiary', ...row })),
    ]
    : [];

  const metricCards = kpis
    ? [
        ['Operational cost', formatNumber(kpis.total_operational_cost, 2)],
        ['Donations available', `${formatNumber(kpis.total_donations_available_kg)} kg`],
        ['Food collected', `${formatNumber(kpis.total_food_collected_kg)} kg`],
        ['Food distributed', `${formatNumber(kpis.total_food_distributed_kg)} kg`],
        ['Food purchased', `${formatNumber(kpis.total_food_purchased_kg)} kg`],
        ['Unused food', `${formatNumber(kpis.total_unused_food_kg)} kg`],
        ['Uncollected donations', `${formatNumber(kpis.total_uncollected_donations_kg)} kg`],
        ['Unmet demand', `${formatNumber(kpis.total_unmet_demand_packets, 0)} packets`],
        ['Food utilization', `${formatNumber(kpis.food_utilization_pct)}%`],
        ['Demand satisfaction', `${formatNumber(kpis.demand_satisfaction_pct)}%`],
        ['Facilities selected', formatNumber(kpis.facilities_required, 0)],
        ['Vehicles required', formatNumber(kpis.vehicles_required, 0)],
        ['Staff required', formatNumber(kpis.staff_required, 0)],
        ['Staff hired', formatNumber(kpis.staff_hired, 0)],
      ]
    : [];

  return (
    <section className="space-y-5 rounded-2xl border border-brand-border bg-brand-bg p-4 md:p-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 text-navy-primary">
            <Scale className="h-5 w-5 text-teal" />
            <h2 className="text-lg font-bold">Food Allocation Optimizer</h2>
          </div>
          <p className="mt-1 max-w-3xl text-xs text-text-secondary">
            Enter your administrator dataset and send it to the Python OR-Tools SCIP solver. No example
            dataset or precomputed optimization result is loaded.
          </p>
        </div>
      </header>

      <form onSubmit={runOptimization} className="space-y-4">
        <div className="grid gap-4 xl:grid-cols-2">
          {JSON_SECTIONS.map(section => (
            <label key={section.key} className="block rounded-xl border border-brand-border bg-white p-4">
              <span className="block text-sm font-bold text-navy-primary">{section.title}</span>
              <span className="mt-1 block text-[11px] leading-5 text-text-secondary">{section.fields}</span>
              <textarea
                aria-label={section.title}
                value={sections[section.key]}
                onChange={event =>
                  setSections(previous => ({ ...previous, [section.key]: event.target.value }))
                }
                placeholder={section.example}
                rows={5}
                spellCheck="false"
                className="mt-3 w-full rounded-lg border border-brand-border bg-brand-bg p-3 font-mono text-[11px] leading-5 text-text-primary outline-none focus:border-teal"
              />
              <span className="mt-2 block text-[10px] text-text-secondary">
                Use valid JSON. Example is illustrative only; recipes are configurable, not nutritional standards.
                For donors, quantity_kg is the amount per donation occurrence.
              </span>
            </label>
          ))}
        </div>

        <section className="rounded-xl border border-brand-border bg-white p-4">
          <h3 className="text-sm font-bold text-navy-primary">Operational costs</h3>
          <p className="mb-3 mt-1 text-[11px] text-text-secondary">
            Enter costs in one consistent currency unit. Values must be non-negative.
          </p>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {COST_FIELDS.map(([key, label]) => (
              <label key={key} className="text-xs font-medium text-text-secondary">
                {label}
                <input
                  type="number"
                  min="0"
                  step="any"
                  required
                  value={costs[key]}
                  onChange={event => setCosts(previous => ({ ...previous, [key]: event.target.value }))}
                  className="mt-1 block w-full rounded-lg border border-brand-border px-3 py-2 text-sm text-text-primary outline-none focus:border-teal"
                />
              </label>
            ))}
          </div>
        </section>

        <section className="grid gap-3 rounded-xl border border-brand-border bg-white p-4 md:grid-cols-2 xl:grid-cols-4">
          <label className="text-xs font-medium text-text-secondary">
            Planning start date
            <input
              type="date"
              required
              value={planningStartDate}
              onChange={event => setPlanningStartDate(event.target.value)}
              className="mt-1 block w-full rounded-lg border border-brand-border px-3 py-2 text-sm text-text-primary"
            />
          </label>
          <label className="text-xs font-medium text-text-secondary">
            Planning horizon (days)
            <input
              type="number"
              min="1"
              max="365"
              required
              value={planningDays}
              onChange={event => setPlanningDays(event.target.value)}
              className="mt-1 block w-full rounded-lg border border-brand-border px-3 py-2 text-sm text-text-primary"
            />
          </label>
          <label className="text-xs font-medium text-text-secondary">
            Budget caps to compare (comma-separated)
            <input
              type="text"
              value={budgetCaps}
              onChange={event => setBudgetCaps(event.target.value)}
              placeholder="Optional, e.g. 50000, 100000"
              className="mt-1 block w-full rounded-lg border border-brand-border px-3 py-2 text-sm text-text-primary"
            />
          </label>
          <label className="text-xs font-medium text-text-secondary">
            Equity objective weight
            <input
              type="number"
              min="0"
              step="any"
              value={equityWeight}
              onChange={event => setEquityWeight(event.target.value)}
              disabled={!compareEquity}
              className="mt-1 block w-full rounded-lg border border-brand-border px-3 py-2 text-sm text-text-primary disabled:bg-brand-bg"
            />
          </label>
          <label className="flex items-center gap-2 text-xs font-medium text-text-secondary md:col-span-2 xl:col-span-4">
            <input
              type="checkbox"
              checked={compareEquity}
              onChange={event => setCompareEquity(event.target.checked)}
              className="accent-teal"
            />
            Also solve equity-oriented scenarios that minimize the gap between beneficiary groups' unmet-demand rates.
          </label>
        </section>

        {requestError && (
          <div role="alert" className="flex gap-2 rounded-xl border border-status-critical-border bg-status-critical-bg/40 p-3 text-sm text-text-primary">
            <AlertTriangle className="h-4 w-4 shrink-0 text-status-critical" />
            <span>{requestError}</span>
          </div>
        )}
        {savedMessage && (
          <div role="status" className="rounded-xl border border-teal/30 bg-teal-light/40 p-3 text-sm text-navy-primary">
            {savedMessage}
          </div>
        )}
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={saveDataset}
            className="inline-flex items-center gap-2 rounded-lg border border-brand-border bg-white px-4 py-2 text-xs font-bold text-navy-primary hover:bg-brand-bg"
          >
            <Save className="h-4 w-4" /> Save input dataset
          </button>
          <button
            type="submit"
            disabled={isRunning}
            className="inline-flex items-center gap-2 rounded-lg bg-teal px-4 py-2 text-xs font-bold text-white hover:bg-navy-primary disabled:cursor-wait disabled:opacity-60"
          >
            <Play className="h-4 w-4" /> {isRunning ? 'Solving with SCIP…' : 'Optimize with SCIP'}
          </button>
        </div>
      </form>

      {selectedResult && (
        <div className="space-y-4 border-t border-brand-border pt-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-lg font-bold text-navy-primary">Optimization results</h2>
              <p className="text-xs text-text-secondary">
                {selectedResult.solver_name} · {selectedResult.solver_status} · Objective value{' '}
                {selectedResult.objective_value === null ? 'unavailable' : formatNumber(selectedResult.objective_value, 2)}
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {results.length > 1 && (
                <select
                  aria-label="Select budget scenario"
                  value={selectedResultId}
                  onChange={event => setSelectedResultId(event.target.value)}
                  className="rounded-lg border border-brand-border bg-white px-3 py-2 text-xs"
                >
                  {results.map(result => (
                    <option key={result.result_id} value={result.result_id}>
                      {result.scenario_name} · {result.solver_status}
                    </option>
                  ))}
                </select>
              )}
              <button
                type="button"
                disabled={!csvRows.length}
                onClick={() => downloadCsv(`food-allocation-${selectedResult.result_id}.csv`, csvRows)}
                className="inline-flex items-center gap-2 rounded-lg border border-brand-border bg-white px-3 py-2 text-xs font-bold text-navy-primary disabled:opacity-50"
              >
                <Download className="h-4 w-4" /> Export CSV
              </button>
              <button
                type="button"
                onClick={() => window.print()}
                className="inline-flex items-center gap-2 rounded-lg border border-brand-border bg-white px-3 py-2 text-xs font-bold text-navy-primary"
              >
                <FileText className="h-4 w-4" /> Print / Save PDF
              </button>
            </div>
          </div>

          {selectedResult.message && (
            <p className={`rounded-lg p-3 text-xs ${selectedResult.solver_status === 'INFEASIBLE' ? 'bg-status-critical-bg text-status-critical' : 'bg-white text-text-secondary'}`}>
              {selectedResult.message}
            </p>
          )}
          {kpis && (
            <>
              <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
                {metricCards.map(([title, value]) => (
                  <div key={title} className="rounded-xl border border-brand-border bg-white p-3">
                    <p className="text-[11px] text-text-secondary">{title}</p>
                    <p className="mt-1 text-base font-bold text-navy-primary">{value}</p>
                  </div>
                ))}
              </div>

              <div className="grid gap-4 xl:grid-cols-2">
                <MetricBarChart
                  title="Donated versus collected food (kg)"
                  data={donatedVsCollected}
                  nameKey="name"
                  valueKeys={[{ key: 'kg', name: 'Kilograms' }]}
                />
                <MetricBarChart
                  title="Food wastage and expiry (kg)"
                  data={wastageData}
                  nameKey="name"
                  valueKeys={[{ key: 'kg', name: 'Kilograms' }]}
                />
                <MetricBarChart
                  title="Food distributed by facility (kg)"
                  data={selectedResult.facility_allocations.map(row => ({
                    facility: row.facility,
                    distributed: row.food_distributed_kg,
                  }))}
                  nameKey="facility"
                  valueKeys={[{ key: 'distributed', name: 'Distributed kg' }]}
                />
                <MetricBarChart
                  title="Demand and allocation by beneficiary location"
                  data={selectedResult.beneficiary_allocations.map(row => ({
                    location: row.beneficiary_location,
                    demand: row.total_demand_packets,
                    allocated: row.packets_allocated,
                  }))}
                  nameKey="location"
                  valueKeys={[
                    { key: 'demand', name: 'Demand packets' },
                    { key: 'allocated', name: 'Allocated packets' },
                  ]}
                />
                <MetricBarChart
                  title="Distribution by beneficiary category (packets)"
                  data={distributionByCategory}
                  nameKey="category"
                  valueKeys={[
                    { key: 'allocated', name: 'Allocated packets' },
                    { key: 'unmet', name: 'Unmet packets' },
                  ]}
                />
                <MetricBarChart
                  title="Operational cost breakdown"
                  data={costRows}
                  nameKey="name"
                  valueKeys={[{ key: 'cost', name: 'Cost' }]}
                />
                <MetricBarChart
                  title="Storage and transportation utilization (%)"
                  data={facilityUtilization}
                  nameKey="facility"
                  valueKeys={[
                    { key: 'storage', name: 'Storage %' },
                    { key: 'transport', name: 'Transportation %' },
                  ]}
                />
              </div>

              {selectedResult.equity_analysis?.groups?.length > 0 && (
                <section className="rounded-xl border border-brand-border bg-white p-4">
                  <h3 className="mb-3 text-sm font-bold text-navy-primary">
                    Equity comparison — unmet-demand rate by group
                  </h3>
                  <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_220px]">
                    <div className="h-52">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={selectedResult.equity_analysis.groups}>
                          <CartesianGrid strokeDasharray="3 3" vertical={false} />
                          <XAxis dataKey="beneficiary_category" />
                          <YAxis unit="%" />
                          <Tooltip />
                          <Bar dataKey="unmet_demand_rate_pct" name="Unmet demand rate">
                            {selectedResult.equity_analysis.groups.map((group, index) => (
                              <Cell key={group.beneficiary_category} fill={PALETTE[index % PALETTE.length]} />
                            ))}
                          </Bar>
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                    <div className="flex flex-col items-center justify-center">
                      <div className="h-36 w-36">
                        <ResponsiveContainer width="100%" height="100%">
                          <PieChart>
                            <Pie
                              data={distributionByCategory}
                              dataKey="allocated"
                              nameKey="category"
                              innerRadius={36}
                              outerRadius={62}
                            >
                              {distributionByCategory.map((row, index) => (
                                <Cell key={row.category} fill={PALETTE[index % PALETTE.length]} />
                              ))}
                            </Pie>
                            <Tooltip />
                          </PieChart>
                        </ResponsiveContainer>
                      </div>
                      <p className="text-center text-[11px] text-text-secondary">
                        Unmet-rate disparity: {formatNumber(selectedResult.equity_analysis.unmet_rate_disparity_pct)}%
                      </p>
                    </div>
                  </div>
                </section>
              )}

              <DataTable
                title="Donor collection allocation"
                rows={selectedResult.donor_allocations}
                columns={[
                  { key: 'donor', label: 'Donor' },
                  { key: 'food_item', label: 'Food item' },
                  { key: 'quantity_donated_kg', label: 'Donated (kg)', render: row => formatNumber(row.quantity_donated_kg) },
                  { key: 'assigned_foodbank', label: 'Assigned foodbank' },
                  { key: 'quantity_collected_kg', label: 'Collected (kg)', render: row => formatNumber(row.quantity_collected_kg) },
                  { key: 'quantity_uncollected_kg', label: 'Uncollected (kg)', render: row => formatNumber(row.quantity_uncollected_kg) },
                ]}
                emptyMessage="No donor collection assignments."
              />
              <DataTable
                title="Facility allocation"
                rows={selectedResult.facility_allocations}
                columns={[
                  { key: 'facility', label: 'Facility' },
                  { key: 'food_received_kg', label: 'Received (kg)', render: row => formatNumber(row.food_received_kg) },
                  { key: 'food_distributed_kg', label: 'Distributed (kg)', render: row => formatNumber(row.food_distributed_kg) },
                  { key: 'food_transferred_kg', label: 'Transferred (kg)', render: row => formatNumber(row.food_transferred_kg) },
                  { key: 'storage_utilization_pct', label: 'Storage %', render: row => `${formatNumber(row.storage_utilization_pct)}%` },
                  { key: 'transportation_utilization_pct', label: 'Transport %', render: row => `${formatNumber(row.transportation_utilization_pct)}%` },
                  { key: 'staff_required', label: 'Staff required' },
                  { key: 'vehicles_required', label: 'Vehicles required' },
                  { key: 'cost_contribution', label: 'Cost contribution', render: row => formatNumber(row.cost_contribution, 2) },
                  { key: 'decision_rationale', label: 'Solver allocation facts' },
                ]}
                emptyMessage="No facility allocations."
              />
              <DataTable
                title="Food balance by facility and item (kg)"
                rows={selectedResult.food_item_balances}
                columns={[
                  { key: 'facility', label: 'Facility' },
                  { key: 'food_item', label: 'Food item' },
                  { key: 'direct_donations_kg', label: 'Direct donations', render: row => formatNumber(row.direct_donations_kg) },
                  { key: 'transferred_in_kg', label: 'Transferred in', render: row => formatNumber(row.transferred_in_kg) },
                  { key: 'purchased_kg', label: 'Purchased', render: row => formatNumber(row.purchased_kg) },
                  { key: 'used_in_packets_kg', label: 'Used in packets', render: row => formatNumber(row.used_in_packets_kg) },
                  { key: 'transferred_out_kg', label: 'Transferred out', render: row => formatNumber(row.transferred_out_kg) },
                  { key: 'unused_kg', label: 'Unused', render: row => formatNumber(row.unused_kg) },
                  { key: 'balance_residual_kg', label: 'Balance residual', render: row => formatNumber(row.balance_residual_kg, 4) },
                ]}
                emptyMessage="No food item balances are available."
              />
              <DataTable
                title="Beneficiary allocation"
                rows={selectedResult.beneficiary_allocations}
                columns={[
                  { key: 'beneficiary_location', label: 'Location' },
                  { key: 'beneficiary_category', label: 'Category' },
                  { key: 'total_demand_packets', label: 'Demand' },
                  { key: 'packets_allocated', label: 'Allocated' },
                  { key: 'unmet_demand_packets', label: 'Unmet' },
                  { key: 'demand_satisfaction_pct', label: 'Satisfaction', render: row => `${formatNumber(row.demand_satisfaction_pct)}%` },
                ]}
                emptyMessage="No beneficiary allocations."
              />
              <DataTable
                title="Allocation decisions and route facts"
                rows={selectedResult.allocation_details}
                columns={[
                  { key: 'facility', label: 'Facility' },
                  { key: 'beneficiary_location', label: 'Beneficiary location' },
                  { key: 'beneficiary_category', label: 'Category' },
                  { key: 'packet_type', label: 'Packet type' },
                  { key: 'packets', label: 'Packets', render: row => formatNumber(row.packets, 0) },
                  { key: 'distance_km', label: 'Distance (km)', render: row => formatNumber(row.distance_km) },
                  { key: 'decision_rationale', label: 'Solver constraint facts' },
                ]}
                emptyMessage="No delivery assignments were selected."
              />
              <div className="rounded-xl border border-brand-border bg-white p-4 text-xs text-text-secondary">
                <strong className="text-navy-primary">Constraint checks:</strong>{' '}
                {Object.entries(selectedResult.constraint_results || {})
                  .map(([name, status]) => `${name.replaceAll('_', ' ')}: ${status}`)
                  .join(' · ')}
              </div>
            </>
          )}
        </div>
      )}
    </section>
  );
}
