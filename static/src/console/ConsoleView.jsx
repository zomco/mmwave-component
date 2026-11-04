import React, { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, Check, Circle, Download, Plug, Unplug, Usb } from 'lucide-react';
import { consoleCopy } from './copy.js';
import { checksFromSession, csvCell, redactExport, targetRows } from './observe.js';

const NUMBER_FIELDS = [
  ['install.x_cm', 'X', 'cm', -2000, 2000, 1],
  ['install.y_cm', 'Y', 'cm', -2000, 2000, 1],
  ['install.z_cm', 'Z', 'cm', 50, 600, 1],
  ['install.yaw_deg', 'Yaw', 'deg', -180, 180, 0.1],
  ['install.pitch_deg', 'Pitch', 'deg', -90, 90, 0.5],
  ['install.roll_deg', 'Roll', 'deg', -90, 90, 0.5],
];

function download(name, text, type) {
  const blob = new Blob([text], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = name;
  link.click();
  URL.revokeObjectURL(url);
}

function Layer({ label, value }) {
  return <div className="soft-surface px-3 py-2"><div className="muted text-xs">{label}</div><div className="mt-1 text-sm font-semibold">{value}</div></div>;
}

function Banner({ children }) {
  return <p className="notice mt-4" role="status"><AlertTriangle size={16} aria-hidden="true" /> {children}</p>;
}

export default function ConsoleView({ language, session, snapshot, support, onConnect, onDisconnect, busy, portPhase = 'idle', holdDisconnect = false, selectedModel }) {
  const t = consoleCopy[language] || consoleCopy.en;
  const [tab, setTab] = useState('quick');
  const [message, setMessage] = useState('');
  const [includeNetwork, setIncludeNetwork] = useState(false);
  const [paused, setPaused] = useState(false);
  const [frozen, setFrozen] = useState(null);
  const [recording, setRecording] = useState([]);
  const [recordOn, setRecordOn] = useState(false);
  const snap = snapshot;
  const sim = snap.simulation;

  useEffect(() => {
    if (!recordOn || !snap.telemetry) return;
    setRecording((rows) => rows.concat([{ at: Date.now(), body: snap.telemetry }]).slice(-600));
  }, [recordOn, snap.telemetry]);

  useEffect(() => {
    const onHide = (event) => {
      if (snap.pending && event) event.returnValue = t.leavePending;
    };
    window.addEventListener('beforeunload', onHide);
    return () => window.removeEventListener('beforeunload', onHide);
  }, [snap.pending, t.leavePending]);

  useEffect(() => {
    if (!session || typeof session.touchClock !== 'function') return undefined;
    const timer = setInterval(() => session.touchClock(), 1000);
    return () => clearInterval(timer);
  }, [session]);

  const view = session && typeof session.observationView === 'function'
    ? session.observationView()
    : { presence: 'unknown', targets: 'unknown', vitals: 'none', vitalFields: [], live: false, historical: false };
  const checks = useMemo(() => checksFromSession(session), [session, snap]);
  const shown = paused && frozen ? frozen : snap.telemetry;
  const boundary = snap.draft ? snap.draft['geometry.boundary_cm'] : null;
  const display = paused
    ? { presence: 'paused', targets: 'paused', historical: true, live: false, vitalFields: (view.vitalFields || []).map((field) => ({ ...field, state: 'paused', value: null })) }
    : view;
  const sampleFresh = display.live && view.presence !== 'stale' && view.targets !== 'stale';
  const rows = targetRows(shown, boundary).map((row) => sampleFresh ? row : { ...row, quality: 'stale' });

  const connect = async () => {
    setMessage('');
    const result = await onConnect();
    if (result && result.reason === 'chooser_cancelled') setMessage(t.cancelled);
    else if (result && result.reason === 'no_web_serial') setMessage(t.unsupported);
    else if (result && result.reason === 'insecure_context') setMessage(t.insecure);
    else if (result && result.reason === 'installer_holds_port') setMessage(t.installerHold);
    else if (result && (result.reason === 'port_busy' || result.reason === 'peer_holds_port')) setMessage(t.busy);
    else if (result && result.reason === 'timeout') setMessage(t.noResponse);
    else if (result && !result.ok) setMessage(result.reason || t.noResponse);
  };

  const rehandshake = async () => {
    setMessage('');
    if (!session || typeof session.rehandshake !== 'function') return;
    try {
      const result = await session.rehandshake();
      if (result && !result.ok) setMessage(result.reason || t.noResponse);
    } catch (error) {
      setMessage(error && error.message ? error.message : t.noResponse);
    }
  };

  return <section id="console" className="scroll-mt-24 mt-12" aria-label={t.title}>
    <div className="surface p-5 sm:p-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <span className="eyebrow"><Usb size={14} aria-hidden="true" />{t.nav}</span>
          <h2 className="section-title mt-4">{t.title}</h2>
          <p className="muted mt-3 max-w-3xl text-sm leading-7">{t.intro}</p>
        </div>
        <div className="flex gap-2">
          {snap.layers.protocol === 'session_expired' && <button className="primary-button" onClick={rehandshake}>{t.rehandshake}</button>}
          {holdDisconnect || snap.layers.port === 'open' || snap.layers.protocol === 'online' || snap.layers.protocol === 'handshake' || snap.layers.protocol === 'session_expired'
            ? <button className="secondary-button" onClick={onDisconnect} disabled={portPhase === 'closing'}><Unplug size={16} />{t.disconnect}</button>
            : <button className="primary-button" onClick={connect} disabled={!support.ok || busy || portPhase === 'installer' || portPhase === 'connecting' || portPhase === 'closing'}><Plug size={16} />{t.connect}</button>}
        </div>
      </div>
      <p className="muted mt-3 text-xs leading-6">{t.verifiedBoard}</p>
      {!support.ok && <Banner>{support.reason === 'insecure_context' ? t.insecure : t.unsupported}</Banner>}
      {sim && <Banner>{snap.mode === 'replay' ? t.replayBanner : t.simBanner}</Banner>}
      {snap.layers.protocol === 'handshake' && <p className="notice mt-4" role="status">{t.handshake} {t.waiting}</p>}
      {snap.layers.protocol === 'no_response' && <Banner>{t.noResponse}</Banner>}
      {snap.layers.protocol === 'session_expired' && <Banner>{t.sessionExpired}</Banner>}
      {portPhase === 'installer' && <p className="notice mt-4" role="status">{t.installerHold}</p>}
      {portPhase === 'closing' && <p className="notice mt-4" role="status">{t.closingPort}</p>}
      {portPhase === 'close_failed' && <p className="notice mt-4" role="status">{t.closeFailed}</p>}
      {portPhase === 'installer_unconfirmed' && <p className="notice mt-4" role="status">{t.afterInstaller}</p>}
      {message && <p className="notice mt-4" role="status">{message}</p>}
      <div className="mt-5 grid gap-3 sm:grid-cols-5">
        <Layer label={t.layers.port} value={snap.layers.port} />
        <Layer label={t.layers.protocol} value={snap.layers.protocol} />
        <Layer label={t.layers.radar} value={snap.layers.radar} />
        <Layer label={t.layers.data} value={snap.layers.data} />
        <Layer label={t.layers.config} value={snap.layers.config} />
      </div>
      {snap.identity && <div className="soft-surface mt-4 p-4 text-sm leading-7">
        <div className="font-semibold">{snap.identity.configured_model || '—'} · {snap.identity.dimension || '—'} · {snap.identity.firmware_version || '—'}</div>
        <p className="muted mt-1 text-xs">{t.modelNote}</p>
        {selectedModel && snap.identity.configured_model && selectedModel !== snap.identity.configured_model && <p className="notice mt-3">{t.modelMismatch}</p>}
      </div>}
      {snap.pending && <Banner>{t.leavePending}</Banner>}
      <div className="step-nav mt-6" role="tablist" aria-label={t.title}>
        {['quick', 'live', 'config', 'diag'].map((id) => <button key={id} role="tab" aria-selected={tab === id} className={tab === id ? 'current' : ''} onClick={() => setTab(id)}>{t.tabs[id]}</button>)}
      </div>
      <div className="mt-6" role="tabpanel">
        {tab === 'quick' && <Quick t={t} checks={checks} reading={view} snap={snap} />}
        {tab === 'live' && <Live t={t} snap={snap} shown={shown} rows={rows} reading={display} paused={paused} onPause={() => { setFrozen(snap.telemetry); setPaused(true); }} onResume={() => setPaused(false)} recordOn={recordOn} recording={recording} onRecord={() => { setRecordOn((v) => !v); if (recordOn) setRecording([]); }} />}
        {tab === 'config' && <Config t={t} session={session} snap={snap} />}
        {tab === 'diag' && <Diag t={t} session={session} snap={snap} includeNetwork={includeNetwork} setIncludeNetwork={setIncludeNetwork} />}
      </div>
    </div>
  </section>;
}

function Quick({ t, checks, reading, snap }) {
  const labels = { usb: t.steps.usb, radar: t.steps.radar, presence: t.steps.presence, config: t.steps.config };
  return <div>
    <p className="muted text-sm leading-7">{t.quickLead}</p>
    <ul className="mt-4 space-y-3">
      {checks.map((item) => <li key={item.id} className="soft-surface flex items-start justify-between gap-3 p-4">
        <div><div className="font-semibold">{labels[item.id]}</div><div className="muted mt-1 text-xs">{item.id === 'presence' && item.state !== 'present' && item.state !== 'absent' ? t.presenceHint : ''}</div></div>
        <Mark state={item.state} label={t.states[item.state] || item.state} />
      </li>)}
    </ul>
    <p className="muted mt-4 text-sm">{t.noHa}</p>
    <p className="muted mt-2 text-xs">{t.states[reading.presence] || reading.presence} · {t.states[reading.targets] || reading.targets}{reading.historical ? ' · ' + t.historical : ''}{snap.telemetry ? ' · seq ' + snap.telemetry.source_seq : ''}</p>
  </div>;
}

function Mark({ state, label }) {
  const good = state === 'pass' || state === 'present' || state === 'absent';
  return <span className={"inline-flex shrink-0 items-center gap-2 whitespace-nowrap text-sm font-semibold " + (good ? 'text-brand-700 dark:text-brand-300' : '')}>{good ? <Check size={16} /> : <Circle size={14} />}{label}</span>;
}

function Live({ t, snap, shown, rows, reading, paused, onPause, onResume, recordOn, recording, onRecord }) {
  const oneD = rows.some((row) => row.oneD) || (snap.identity && snap.identity.dimension === '1D');
  return <div>
    <p className="muted text-sm leading-7">{t.liveLead}</p>
    <div className="mt-4 flex flex-wrap gap-2">
      <button className="secondary-button" onClick={paused ? onResume : onPause}>{paused ? t.resume : t.pause}</button>
      <button className="secondary-button" onClick={onRecord}>{recordOn ? t.stopRecord : t.record}</button>
      <button className="secondary-button" disabled={!recording.length} onClick={() => download('mmwave-observations.jsonl', recording.map((row) => JSON.stringify(redactExport(row))).join('\n'), 'application/x-ndjson')}><Download size={16} />{t.exportJson}</button>
      <button className="secondary-button" disabled={!recording.length} onClick={() => download('mmwave-observations.csv', toCsv(recording), 'text/csv')}><Download size={16} />{t.exportCsv}</button>
    </div>
    <p className="muted mt-3 text-xs">{t.recordLimit} {t.idUnstable}</p>
    {paused && <p className="notice mt-4" role="status">{t.pausedView}</p>}
    {!paused && reading.historical && <p className="notice mt-4" role="status">{t.historical}</p>}
    <div className="mt-4 grid gap-4 lg:grid-cols-[1.2fr_0.8fr]">
      <div className="radar-grid relative min-h-64 overflow-hidden rounded-2xl p-4 text-brand-100">
        {oneD ? <RangeAxis rows={rows} /> : <Plan rows={rows} boundary={snap.draft && snap.draft['geometry.boundary_cm']} />}
      </div>
      <div className="space-y-3 text-sm">
        <div className="soft-surface p-4"><div className="muted text-xs">{t.steps.presence}</div><div className="mt-1 font-semibold">{t.states[reading.presence] || reading.presence}</div></div>
        {rows.map((row) => <div key={row.key} className={"soft-surface p-4 " + (row.faded ? 'opacity-60' : '')}>
          <div className="font-semibold">{row.oneD ? row.rangeCm + ' cm' : formatPoint(row.room)}</div>
          <div className="muted mt-1 text-xs">{t.states[row.quality] || row.quality} · sample {row.sampleMs == null ? '—' : row.sampleMs}{row.faded ? ' · ' + t.outside : ''}</div>
        </div>)}
        {!rows.length && <p className="notice">{t.states[reading.targets] || reading.targets}</p>}
        <Vitals t={t} fields={reading.vitalFields} />
      </div>
    </div>
  </div>;
}

function RangeAxis({ rows }) {
  const max = 600;
  return <div>
    <div className="relative mt-16 h-3 rounded-full bg-white/20">
      {rows.filter((row) => typeof row.rangeCm === 'number').map((row) => <span key={row.key} className="absolute top-1/2 h-4 w-4 -translate-y-1/2 rounded-full bg-brand-300" style={{ left: Math.max(0, Math.min(100, (row.rangeCm / max) * 100)) + '%' }} />)}
    </div>
    <div className="mt-3 flex justify-between text-xs"><span>0</span><span>{max} cm</span></div>
  </div>;
}

function Plan({ rows, boundary }) {
  const points = Array.isArray(boundary) ? boundary : [];
  const poly = points.map((point) => (point.x + 400) + ',' + (400 - point.y)).join(' ');
  return <svg viewBox="0 0 800 800" className="h-full w-full" role="img">
    {poly && <polygon points={poly} fill="none" stroke="#7fe0b9" strokeDasharray="8 6" />}
    {rows.filter((row) => Array.isArray(row.room)).map((row) => <circle key={row.key} cx={row.room[0] + 400} cy={400 - row.room[1]} r="10" fill={row.faded ? '#94a3b8' : '#45c99a'} opacity={row.faded ? 0.45 : 1} />)}
  </svg>;
}

function Vitals({ t, fields }) {
  if (!fields || !fields.length) return null;
  return <details className="soft-surface p-4"><summary>{t.vitals}</summary><ul className="mt-3 space-y-2 text-xs">{fields.map((field) => <li key={field.key}>{field.key}: {field.state === 'valid' ? String(field.value) : (t.states[field.state] || field.state)}</li>)}</ul></details>;
}

function formatPoint(point) {
  if (!Array.isArray(point)) return '—';
  return point.map((n) => Number(n).toFixed(0)).join(', ') + ' cm';
}

function toCsv(recording) {
  const header = ['at', 'source_seq', 'origin', 'presence_quality', 'presence_value', 'target_count'].map(csvCell).join(',');
  const lines = recording.map((row) => [row.at, row.body.source_seq, row.body.origin, row.body.presence && row.body.presence.quality, row.body.presence && row.body.presence.value, Array.isArray(row.body.targets) ? row.body.targets.length : ''].map(csvCell).join(','));
  return [header].concat(lines).join('\n');
}

function Config({ t, session, snap }) {
  const draft = snap.draft || {};
  const changes = session.localChanges();
  const keys = Object.keys(changes);
  const setNumber = (key, raw) => session.editDraft(key, raw === '' ? null : Number(raw));
  const phase = snap.save.phase;
  const locked = phase === 'unknown' || phase === 'committing' || phase === 'validating' || phase === 'reading' || phase === 'recovering';
  const conflicted = phase === 'conflict';
  const readbackBlocked = snap.save.message === 'persisted_readback_failed';
  const run = (work) => { Promise.resolve(work()).catch(() => {}); };
  return <div>
    <p className="muted text-sm leading-7">{t.configLead}</p>
    {snap.save.phase === 'unknown' && <Banner>{t.unknownSave}</Banner>}
    {snap.save.phase === 'conflict' && <Banner>{t.conflict}</Banner>}
    {snap.save.phase === 'conflict' && <IncomingCompare t={t} draft={draft} incoming={snap.incomingConfig} />}
    {(snap.save.message === 'persisted_and_read_back' || snap.save.message === 'confirmed_by_status') && <p className="notice mt-4" role="status"><Check size={16} /> {t.persisted}</p>}
    {snap.save.message === 'persisted_readback_failed' && <Banner>{t.readbackFailed}</Banner>}
    {(snap.save.message === 'read_disconnected' || snap.save.message === 'config_read_failed') && <Banner>{t.readFailed}</Banner>}
    {snap.save.message === 'readback_diverged' && <Banner>{t.readbackDiverged}</Banner>}
    <h3 className="mt-5 font-semibold">{t.install}</h3>
    <p className="muted mt-1 text-xs">{t.yawHelp}</p>
    <div className="mt-3 grid gap-3 sm:grid-cols-2">
      {NUMBER_FIELDS.filter(([key]) => draft[key] !== undefined || session.supports(key)).map(([key, label, unit]) => <label key={key} className="block text-sm font-semibold">{label} ({t.units[unit]})
        <input className="field mt-2" inputMode="decimal" disabled={locked || conflicted} aria-invalid={snap.fieldErrors[key] ? 'true' : 'false'} value={draft[key] ?? ''} onChange={(event) => setNumber(key, event.target.value)} />
        {snap.fieldErrors[key] && <span className="mt-1 block text-xs text-red-700" role="alert">{t.fieldError}: {snap.fieldErrors[key]}</span>}
      </label>)}
    </div>
    {session.supports('geometry.boundary_cm') && <Boundary t={t} value={draft['geometry.boundary_cm']} error={snap.fieldErrors['geometry.boundary_cm']} onChange={(value) => session.editDraft('geometry.boundary_cm', value)} />}
    {session.supports('range.window_cm') && <RangeWindow t={t} value={draft['range.window_cm']} onChange={(value) => session.editDraft('range.window_cm', value)} />}
    <h3 className="mt-6 font-semibold">{t.diff}</h3>
    {keys.length === 0 ? <p className="muted mt-2 text-sm">{t.noChanges}</p> : <ul className="mt-2 space-y-1 text-sm">{keys.map((key) => <li key={key}><code>{key}</code> → {JSON.stringify(changes[key])}</li>)}</ul>}
    <div className="mt-5 flex flex-wrap gap-2">
      <button className="secondary-button" onClick={() => run(() => session.validateDraft())} disabled={locked || conflicted}>{t.validate}</button>
      <button className="primary-button" onClick={() => run(() => session.commitDraft())} disabled={locked || conflicted || readbackBlocked || keys.length === 0}>{t.save}</button>
      <button className="secondary-button" onClick={() => run(() => session.discardDraft())} disabled={locked || conflicted}>{t.discard}</button>
      <button className="secondary-button" onClick={() => run(() => session.reloadFromDevice())} disabled={locked}>{t.reload}</button>
      {snap.save.phase === 'unknown' && <>
        <button className="primary-button" onClick={() => session.recoverPending()}>{t.queryStatus}</button>
        <button className="secondary-button" onClick={() => session.abandonPending()}>{t.abandon}</button>
      </>}
    </div>
    {snap.save.phase === 'unknown' && <p className="muted mt-3 text-xs leading-6">{t.abandonHint}</p>}
    <Wifi t={t} session={session} snap={snap} />
  </div>;
}

function IncomingCompare({ t, draft, incoming }) {
  if (!incoming || !Array.isArray(incoming.items)) return null;
  const next = Object.fromEntries(incoming.items.map((item) => [item.key, item.value]));
  const keys = Object.keys(next).filter((key) => JSON.stringify(next[key]) !== JSON.stringify((draft || {})[key])).slice(0, 8);
  if (!keys.length) return null;
  return <div className="mt-3 text-sm">
    <p className="muted">{t.incomingHint}</p>
    <ul className="mt-2 space-y-1">{keys.map((key) => <li key={key}><code>{key}</code> → {JSON.stringify(next[key])}</li>)}</ul>
  </div>;
}

function Boundary({ t, value, error, onChange }) {
  const points = Array.isArray(value) ? value : [];
  const edit = (index, axis, raw) => {
    const next = points.map((point, i) => i === index ? { ...point, [axis]: raw === '' ? '' : Number(raw) } : point);
    onChange(next);
  };
  return <div className="mt-6">
    <h3 className="font-semibold">{t.boundary}</h3>
    <p className="muted mt-1 text-xs">{t.localFrame} / {t.roomFrame}</p>
    {points.map((point, index) => <div key={index} className="mt-2 flex gap-2">
      <label className="text-sm">X<input className="field mt-1" inputMode="decimal" value={point.x} onChange={(event) => edit(index, 'x', event.target.value)} /></label>
      <label className="text-sm">Y<input className="field mt-1" inputMode="decimal" value={point.y} onChange={(event) => edit(index, 'y', event.target.value)} /></label>
    </div>)}
    <div className="mt-3 flex gap-2">
      <button className="secondary-button" type="button" onClick={() => onChange(points.concat([{ x: 0, y: 0 }]))}>{t.addPoint}</button>
      <button className="secondary-button" type="button" onClick={() => onChange(points.slice(0, -1))}>{t.removePoint}</button>
    </div>
    {error && <p className="mt-2 text-xs text-red-700" role="alert">{t.fieldError}: {error}</p>}
  </div>;
}

function RangeWindow({ t, value, onChange }) {
  const window = value || { min: 0, max: 0 };
  return <div className="mt-6">
    <h3 className="font-semibold">{t.range}</h3>
    <div className="mt-2 flex gap-2">
      <label className="text-sm">min<input className="field mt-1" inputMode="decimal" value={window.min} onChange={(event) => onChange({ ...window, min: Number(event.target.value) })} /></label>
      <label className="text-sm">max<input className="field mt-1" inputMode="decimal" value={window.max} onChange={(event) => onChange({ ...window, max: Number(event.target.value) })} /></label>
    </div>
  </div>;
}

function Wifi({ t, session, snap }) {
  const [ssid, setSsid] = useState('');
  const [password, setPassword] = useState('');
  const declared = snap.capabilities.some((item) => String(item.id || '').startsWith('wifi'));
  if (!snap.sessionLive) return null;
  if (!declared) return <p className="muted mt-6 text-sm">{t.wifiUnsupported} {t.wifiSkip}</p>;
  return <div className="mt-6 border-t border-slate-200 pt-5 dark:border-white/10">
    <h3 className="font-semibold">{t.wifiTitle}</h3>
    <p className="muted mt-1 text-sm">{t.wifiSkip} {t.scanMissing}</p>
    <div className="mt-3 grid gap-3 sm:grid-cols-2">
      <label className="text-sm font-semibold">{t.ssid}<input className="field mt-2" value={ssid} autoComplete="off" onChange={(event) => setSsid(event.target.value)} /></label>
      <label className="text-sm font-semibold">{t.password}<input className="field mt-2" type="password" value={password} autoComplete="new-password" onChange={(event) => setPassword(event.target.value)} /></label>
    </div>
    <button className="secondary-button mt-3" onClick={async () => { await session.provisionWifi({ ssid, password }); setPassword(''); }}>{t.provision}</button>
    <JobList t={t} jobs={snap.jobs} />
  </div>;
}

function JobList({ t, jobs }) {
  if (!jobs.length) return null;
  return <ul className="mt-3 space-y-2 text-sm">{jobs.map((job) => <li key={job.job_id}>{job.action_id || job.job_id}: {job.state}{job.verified ? '' : ' · ' + t.jobUnknown}</li>)}</ul>;
}

function Diag({ t, session, snap, includeNetwork, setIncludeNetwork }) {
  const status = snap.status || {};
  const counters = status.counters || {};
  return <div>
    <p className="muted text-sm leading-7">{t.diagLead}</p>
    <h3 className="mt-4 font-semibold">{t.health}</h3>
    <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-2">
      {['uptime_ms', 'radar_link', 'config_revision', 'config_storage'].map((key) => <div key={key} className="soft-surface p-3"><dt className="muted text-xs">{key}</dt><dd className="mt-1 font-semibold">{status[key] == null ? '—' : String(status[key])}</dd></div>)}
      {Object.entries(counters).map(([key, value]) => <div key={key} className="soft-surface p-3"><dt className="muted text-xs">{key}</dt><dd className="mt-1 font-semibold">{String(value)}</dd></div>)}
    </dl>
    <h3 className="mt-6 font-semibold">{t.logs}</h3>
    {!snap.logs.length && <p className="muted mt-2 text-sm">{t.noLogs}</p>}
    <ul className="mt-2 space-y-2 text-sm">{snap.logs.slice(-12).map((entry, index) => <li key={index} className="soft-surface p-3">{entry.level} · {entry.source} · {entry.message}</li>)}</ul>
    <label className="check-row mt-4"><input type="checkbox" checked={includeNetwork} onChange={(event) => setIncludeNetwork(event.target.checked)} />{t.includeNetwork}</label>
    <button className="secondary-button mt-3" onClick={() => download('mmwave-diagnostic.json', JSON.stringify(session.diagnosticExport({ includeNetwork }), null, 2), 'application/json')}><Download size={16} />{t.exportDiag}</button>
  </div>;
}
