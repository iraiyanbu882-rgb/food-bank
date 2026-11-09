import test from 'node:test';
import assert from 'node:assert/strict';
import { getCommandCenterData } from '../src/features/command-center/data/commandCenterData.js';
import { getNetworkMapData } from '../src/features/network-map/data/networkMapData.js';
import { DEFAULT_REGION_INCIDENT, REGIONS } from '../src/mock-data/incidents.mock.js';
import { useAppStore } from '../src/store/useAppStore.js';
import { relocateMapCoordinates } from '../src/utils/relocateMapCoordinates.js';
import {
  getRegionalDemandMapData,
  MOCK_BENEFICIARY_GROUPS,
  MOCK_DEMAND_ITEMS,
} from '../src/features/demand/data/demandData.js';

test('relocates nested Leaflet and GeoJSON coordinates without mutating source data', () => {
  const source = {
    center: [-19.825, 34.86],
    entities: [{ coordinates: [-19.815, 34.87] }],
    routes: [{ points: [[-19.825, 34.86], [-19.815, 34.87]] }],
    geometry: {
      type: 'Polygon',
      coordinates: [[[34.86, -19.825], [34.87, -19.815]]],
    },
  };
  const relocated = relocateMapCoordinates(source, [-19.825, 34.86], [13.0827, 80.2707]);

  assert.deepEqual(relocated.center, [13.0827, 80.2707]);
  assert.deepEqual(relocated.entities[0].coordinates, [13.0927, 80.2807]);
  assert.deepEqual(relocated.routes[0].points[1], [13.0927, 80.2807]);
  assert.deepEqual(relocated.geometry.coordinates[0][0], [80.2707, 13.0827]);
  assert.deepEqual(source.center, [-19.825, 34.86]);
});

test('command centre and network maps relocate synthetic data for every configured region', () => {
  const scenarios = [
    { type: 'Flood', region: 'Beira & Zambezia Corridors', code: 'CYC-IDAI-2' },
    { type: 'Armed Conflict', region: 'Middle East / South Corridor', code: 'ARM-SOUTH-04' },
    { type: 'Pandemic', region: 'Horn of Africa / Lake Basin', code: 'PAN-CHOL-09' },
  ];

  for (const region of REGIONS) {
    for (const scenario of scenarios) {
      const incident = { ...DEFAULT_REGION_INCIDENT, code: scenario.code };
      const commandData = getCommandCenterData(incident, scenario.type, region.id);
      const networkData = getNetworkMapData(incident, scenario.type, region.id);
      const originalNetworkData = getNetworkMapData(incident, scenario.type, scenario.region);
      const originalCoordinate = originalNetworkData.entities[0].coordinates;

      assert.deepEqual(commandData.mapEntities.center, region.center);
      assert.deepEqual(networkData.center, region.center);
      assert.equal(commandData.regionName, region.label);
      assert.equal(networkData.regionName, region.label);
      assert.equal(commandData.isRegionalDemo, true);
      assert.equal(commandData.priorityDemands.length, region.id === 'Tamil Nadu' ? 7 : 6);
      assert.ok(commandData.priorityDemands.every((demand) => demand.id.startsWith(
        region.id === 'Tamil Nadu' ? 'TN-' : region.id === 'Pondy' ? 'PONDY-' : 'KA-'
      )));
      for (const demand of commandData.priorityDemands) {
        assert.equal(demand.requiredQty - demand.availableQty, demand.unmetQty);
      }
      assert.ok(networkData.entities.length > 0);
      assert.deepEqual(networkData.entities[0].coordinates, [
        Number((region.center[0] + originalCoordinate[0] - originalNetworkData.center[0]).toFixed(6)),
        Number((region.center[1] + originalCoordinate[1] - originalNetworkData.center[1]).toFixed(6)),
      ]);
    }
  }
});

test('selecting a configured region creates a supported region incident', () => {
  useAppStore.getState().setSelectedRegion('Pondy');

  const state = useAppStore.getState();
  assert.equal(state.selectedRegion, 'Pondy');
  assert.equal(state.selectedIncident.isSupported, true);
  assert.deepEqual(state.selectedIncident.center, REGIONS.find((item) => item.id === 'Pondy').center);
});

test('demand map relocates beneficiary and demand markers to the selected Indian region', () => {
  for (const region of REGIONS) {
    const data = getRegionalDemandMapData(
      MOCK_BENEFICIARY_GROUPS,
      MOCK_DEMAND_ITEMS,
      region.id
    );

    assert.deepEqual(data.center, region.center);
    assert.ok(data.groups.length > 0);
    assert.ok(data.demands.length > 0);
    assert.ok(data.groups.every((group) => group.region === region.label));
    assert.ok(data.demands.every((demand) => demand.region === region.label));
    assert.deepEqual(data.groups[0].coordinates, [
      Number((region.center[0] - 19.789 + 19.825).toFixed(6)),
      Number((region.center[1] + 34.821 - 34.86).toFixed(6)),
    ]);
  }
});
