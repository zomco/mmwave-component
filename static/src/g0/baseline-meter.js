const FIELDS = [
  'uptime_ms',
  'free_heap',
  'min_free_heap',
  'largest_free_block',
  'stack_high_water_bytes',
  'max_loop_us',
  'radar_frames',
  'radar_errors',
  'radar_targets',
];

export function parseBaselineMeter(line) {
  if (typeof line !== 'string' || !line.startsWith('G0METER v=1 ')) return null;
  const body = line.slice('G0METER v=1 '.length);
  const values = {};
  for (const part of body.split(' ')) {
    const eq = part.indexOf('=');
    if (eq <= 0) return null;
    values[part.slice(0, eq)] = part.slice(eq + 1);
  }
  if (values.stack_high_water_unit !== 'bytes') return null;
  if (values.stack_type_bytes !== '1') return null;
  if (values.stack_word_bytes) return null;
  const sample = {
    stack_high_water_unit: 'bytes',
    stack_type_bytes: 1,
    radar_link: values.radar_link,
  };
  for (const key of FIELDS) {
    if (!/^[0-9]+$/.test(values[key] || '')) return null;
    sample[key] = Number(values[key]);
  }
  if (values.last_radar_frame_ms === 'null') sample.last_radar_frame_ms = null;
  else if (/^[0-9]+$/.test(values.last_radar_frame_ms || '')) sample.last_radar_frame_ms = Number(values.last_radar_frame_ms);
  else return null;
  sample.unmeasured = ['config_storage', 'telemetry_coalesced', 'usb_tx'];
  sample.overhead = 'one ESP_LOGI line every 5s on the baseline USB logger; no MWCP buffer and no second radar reader';
  return sample;
}
