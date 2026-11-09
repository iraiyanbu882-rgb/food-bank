const COORDINATE_FIELDS = new Set(['center', 'coordinates', 'points']);

const roundCoordinate = (value) => Number(value.toFixed(6));

function relocateCoordinatePair(pair, sourceCenter, targetCenter, order) {
  const [first, second, ...rest] = pair;
  const latitude = order === 'lnglat' ? second : first;
  const longitude = order === 'lnglat' ? first : second;
  const relocated = [
    roundCoordinate(targetCenter[0] + latitude - sourceCenter[0]),
    roundCoordinate(targetCenter[1] + longitude - sourceCenter[1]),
  ];

  return order === 'lnglat'
    ? [relocated[1], relocated[0], ...rest]
    : [...relocated, ...rest];
}

function relocateValue(value, sourceCenter, targetCenter, order = 'latlng', isGeoJson = false) {
  if (Array.isArray(value)) {
    if (
      value.length >= 2 &&
      Number.isFinite(value[0]) &&
      Number.isFinite(value[1])
    ) {
      return relocateCoordinatePair(value, sourceCenter, targetCenter, order);
    }

    return value.map((item) => relocateValue(item, sourceCenter, targetCenter, order, isGeoJson));
  }

  if (!value || typeof value !== 'object') return value;

  const relocated = {};
  const hasLatLng = Number.isFinite(value.lat) && Number.isFinite(value.lng);
  const hasLatitudeLongitude =
    Number.isFinite(value.latitude) && Number.isFinite(value.longitude);

  for (const [key, nestedValue] of Object.entries(value)) {
    if (hasLatLng && key === 'lat') {
      relocated.lat = roundCoordinate(targetCenter[0] + value.lat - sourceCenter[0]);
    } else if (hasLatLng && key === 'lng') {
      relocated.lng = roundCoordinate(targetCenter[1] + value.lng - sourceCenter[1]);
    } else if (hasLatitudeLongitude && key === 'latitude') {
      relocated.latitude = roundCoordinate(
        targetCenter[0] + value.latitude - sourceCenter[0]
      );
    } else if (hasLatitudeLongitude && key === 'longitude') {
      relocated.longitude = roundCoordinate(
        targetCenter[1] + value.longitude - sourceCenter[1]
      );
    } else if (key === 'geometry') {
      relocated[key] = relocateValue(nestedValue, sourceCenter, targetCenter, 'lnglat', true);
    } else if (COORDINATE_FIELDS.has(key)) {
      relocated[key] = relocateValue(
        nestedValue,
        sourceCenter,
        targetCenter,
        isGeoJson ? 'lnglat' : 'latlng',
        isGeoJson
      );
    } else {
      relocated[key] = relocateValue(nestedValue, sourceCenter, targetCenter, order, isGeoJson);
    }
  }

  return relocated;
}

export function relocateMapCoordinates(value, sourceCenter, targetCenter) {
  if (
    !Array.isArray(sourceCenter) ||
    !Array.isArray(targetCenter) ||
    sourceCenter.length < 2 ||
    targetCenter.length < 2 ||
    !sourceCenter.every(Number.isFinite) ||
    !targetCenter.every(Number.isFinite)
  ) {
    return value;
  }

  return relocateValue(value, sourceCenter, targetCenter);
}
