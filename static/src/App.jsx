import React, { useEffect, useMemo, useRef, useState } from 'react';
import { ArrowRight, Check, ChevronLeft, Cpu, Globe2, Moon, Radar, Search, Sun, Usb, Zap } from 'lucide-react';
import { copy } from './content';
import FeatureShowcase from './FeatureShowcase';
import RadarDetails from './RadarDetails';
import { boards, radars, textFor, compatibleReleases, defaultRelease, parseReleaseIndex, verifyManifest } from './catalog';

const repo = 'https://github.com/zomco/mmwave-component';
const asset = (path) => new URL(path, document.baseURI).href;
const preference = (key, fallback, allowed) => { try { const value = localStorage.getItem(key); return allowed.includes(value) ? value : fallback; } catch { return fallback; } };
const persist = (key, value) => { try { localStorage.setItem(key, value); } catch { /* Private mode may block storage. */ } };
const yaml = 'type: custom:mmwave-card\nradar_model: r60abd1\npresence_entity: binary_sensor.REPLACE_presence\nx_entity: sensor.REPLACE_raw_x\ny_entity: sensor.REPLACE_raw_y\nz_entity: sensor.REPLACE_raw_z\nroom_w: 400\nroom_d: 350';

function BoardDiagram({ board, t, compact = false }) {
  const [failed, setFailed] = useState(false);
  if (failed) return <p className="notice">{t.pinPending}</p>;
  return <div className={`relative mx-auto ${compact ? 'w-40' : 'max-w-sm'}`}>
    <img src={asset(board.image)} alt={board.name} className="w-full" onError={() => setFailed(true)} />
    <svg viewBox="0 0 1024 1024" className="absolute inset-0 h-full w-full" role="img" aria-label={t.reference}>
      {board.pinMap.map((pin) => {
        const left = pin.x < 0.5;
        const x = pin.x * 1024;
        const y = pin.y * 1024;
        const label = pin.id === 'uart_tx' ? 'TX · 21' : pin.id === 'uart_rx' ? 'RX · 20' : pin.label;
        return <g key={pin.id}>
          <title>{pin.label}</title>
          <circle cx={x} cy={y} r="15" fill="none" stroke={pin.color} strokeWidth="8" />
          {!compact && <>
            <line x1={x + (left ? -20 : 20)} y1={y} x2={left ? 220 : 804} y2={y} stroke={pin.color} strokeWidth="4" />
            <text x={left ? 207 : 817} y={y + 12} textAnchor={left ? 'end' : 'start'} fontSize="36" fontWeight="700" fill={pin.color} stroke="#fff" strokeWidth="4" paintOrder="stroke">{label}</text>
          </>}
        </g>;
      })}
    </svg>
  </div>;
}
function DeviceImage({ device, kind, t }) {
  const [failed, setFailed] = useState(false);
  if (kind === 'board' && device.image && device.pinMap) return <div className="device-image"><BoardDiagram board={device} t={t} compact /></div>;
  return <div className="device-image">{device.image && !failed ? <><img src={asset(device.image)} alt={device.imageStatus === 'placeholder' ? t.placeholder : device.name} onError={() => setFailed(true)} />{device.imageStatus === 'placeholder' && <small>{t.placeholder}</small>}</> : <><span aria-hidden="true">{kind === 'radar' ? <Radar size={72} strokeWidth={1} /> : <Cpu size={72} strokeWidth={1} />}</span><small>{t.placeholder}</small></>}</div>;
}
function DevicePicker({ kind, devices, selected, onSelect, language, t }) {
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState('all');
  const filters = kind === 'radar' ? ['all', '1D', '2D'] : ['all', 'ESP32-C3'];
  const visible = devices.filter((d) => d.name.toLowerCase().includes(query.trim().toLowerCase()) && (filter === 'all' || (kind === 'radar' ? d.dimension : d.chipFamily) === filter));
  return <><div className="picker-toolbar"><label className="search-field"><Search size={18} aria-hidden="true" /><input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder={kind === 'radar' ? t.searchRadar : t.searchBoard} aria-label={kind === 'radar' ? t.searchRadar : t.searchBoard} /></label><div className="flex flex-wrap gap-2">{filters.map((f) => <button key={f} className={`filter-chip ${filter === f ? 'is-active' : ''}`} aria-pressed={filter === f} onClick={() => setFilter(f)}>{f === 'all' ? t.all : f}</button>)}</div></div>
    <div className="device-grid">{visible.map((device) => <button key={device.id} className={`device-card ${selected?.id === device.id ? 'is-selected' : ''}`} aria-pressed={selected?.id === device.id} onClick={() => onSelect(device.id)}><div className="flex items-center justify-between gap-3"><strong>{device.name}</strong>{selected?.id === device.id && <Check size={19} aria-label={t.selected} />}</div><span className="device-badge">{device.dimension || device.chipFamily}</span><DeviceImage {...{ device, kind, t }} /><p className="muted text-sm leading-6">{textFor(device.description, language)}</p></button>)}</div>
    {!visible.length && <p className="notice" role="status">{t.empty}</p>}</>;
}
function Wiring({ radar, board, t, language }) {
  const rows = [['UART_TX · GPIO21', 'RX', '#0891B2'], ['UART_RX · GPIO20', 'TX', '#7C3AED'], ['GND', 'GND', '#475569'], [radar.power || '—', radar.power || '—', '#DC2626']];
  return <div className="mt-8 border-t border-slate-200 pt-6 dark:border-white/10"><h3 className="text-lg font-semibold">{t.wiring}</h3><p className="muted mt-2 text-sm leading-6">{t.wiringHint}</p><div className="mt-5 grid gap-6 md:grid-cols-2"><div className="soft-surface p-4">
    {board.image && board.pinMap ? <BoardDiagram board={board} t={t} /> : <p className="muted text-sm leading-6">{t.pinPending}</p>}
    {board.pinMap && <><div className="flex flex-wrap gap-2 text-xs">{board.pinMap.map((p) => <span key={p.id}><span className="pin-dot" style={{ background: p.color }} />{p.label}</span>)}</div><p className="notice mt-3">{language === 'zh' ? 'USB 朝上、元件面朝前。仅为仓库参考布局，非通用接线认证；请核对实物丝印。每排两个孔属于同一引脚。' : 'USB at top, component side facing you. Repository reference layout only, not universal wiring certification. Match physical labels; two holes per row are one pin.'}</p></>}
    <div className="mt-3 flex flex-wrap gap-2"><a className="secondary-button" href={asset(board.reference)} target="_blank" rel="noreferrer">{t.reference}</a><a className="secondary-button" href={asset(board.frontReference)} target="_blank" rel="noreferrer">{t.frontReference}</a></div></div><div><table className="wiring-table"><thead><tr><th>{t.controller}</th><th>{t.radar}</th></tr></thead><tbody>{rows.map(([from, to, color]) => <tr key={from}><td><span className="pin-dot" style={{ background: color }} />{from}</td><td>{from.startsWith('UART_RX') ? '←' : '→'} {to}</td></tr>)}</tbody></table><p className="notice mt-3">{textFor(radar.powerNote, language)}</p><p className="muted mt-2 text-xs">UART: {radar.baudRate} bps · 8N1 · 3V3 {language === 'zh' ? '不接本型号电源' : 'not used for this radar supply'}</p></div></div></div>;
}
function Flash({ radar, board, wiringConfirmed, t }) {
  const [releases, setReleases] = useState([]);
  const [state, setState] = useState('loading');
  const [retry, setRetry] = useState(0);
  const [selected, setSelected] = useState('');
  const [alpha, setAlpha] = useState(false);
  const [verified, setVerified] = useState({ key: '', url: '', error: false });
  const serial = Boolean(navigator.serial && window.isSecureContext);
  useEffect(() => {
    const controller = new AbortController();
    setState('loading'); setReleases([]);
    fetch(asset('releases.json'), { signal: controller.signal, cache: 'no-cache' }).then((r) => { if (!r.ok) throw new Error('index'); return r.json(); }).then((data) => { setReleases(parseReleaseIndex(data)); setState('ready'); }).catch((e) => { if (e.name !== 'AbortError') setState('error'); });
    return () => controller.abort();
  }, [retry]);
  const compatible = useMemo(() => compatibleReleases(releases, radar, board), [releases, radar, board]);
  useEffect(() => { setSelected(defaultRelease(compatible)); setAlpha(false); }, [compatible]);
  const release = compatible.find((r) => r.id === selected);
  const key = release ? `${radar.id}/${board.id}/${release.id}` : '';
  useEffect(() => {
    setVerified({ key: '', url: '', error: false });
    if (!release || !serial) return;
    const controller = new AbortController();
    verifyManifest(release, document.baseURI, controller.signal).then((url) => { if (!controller.signal.aborted) setVerified({ key, url, error: false }); }).catch((e) => { if (!controller.signal.aborted && e.name !== 'AbortError') setVerified({ key, url: '', error: true }); });
    return () => controller.abort();
  }, [release, key, serial, retry]);
  const ready = release && wiringConfirmed && serial && verified.key === key && verified.url && (release.channel === 'beta' || alpha);
  return <><p className="muted leading-7">{t.firmwareHint}</p>{!serial && <p className="notice mt-4" role="alert">{t.browser}</p>}
    {state === 'loading' && <p className="notice mt-4" role="status">{t.loading}</p>}{state === 'error' && <p className="notice mt-4" role="alert">{t.loadError} <button className="text-link" onClick={() => setRetry((n) => n + 1)}>{t.retry}</button></p>}
    {state === 'ready' && !compatible.length && <p className="notice mt-4" role="status">{t.noReleases}</p>}
    <label className="mt-6 block text-sm font-semibold">{t.version}<select className="field mt-2" value={selected} disabled={!compatible.length} onChange={(e) => { setSelected(e.target.value); setAlpha(false); }}><option value="">{t.selectVersion}</option>{['beta', 'alpha'].map((channel) => <optgroup key={channel} label={t[channel]}>{compatible.filter((r) => r.channel === channel).map((r) => <option key={r.id} value={r.id}>{r.version} · {r.publishedAt.slice(0, 10)}</option>)}</optgroup>)}</select></label>
    {!!compatible.length && !compatible.some((r) => r.channel === 'beta') && <p className="notice mt-3">{t.noBeta}</p>}
    {release && <div className="soft-surface mt-4 p-4"><div className="flex flex-wrap gap-3 text-xs"><span>{radar.name} · {board.name}</span><span>{release.publishedAt.slice(0, 10)}</span><span>{t.commit}: {release.sourceCommit.slice(0, 8)}</span><span>{t.binary}: {release.binaryVersion || release.version}</span></div><a className="text-link mt-3 inline-block" href={`${repo}/releases/tag/${encodeURIComponent(release.version)}`} target="_blank" rel="noreferrer">{t.notes} ↗</a></div>}
    {release?.channel === 'alpha' && <label className="check-row mt-4"><input type="checkbox" checked={alpha} onChange={(e) => setAlpha(e.target.checked)} />{t.alphaConfirm}</label>}
    <p className="notice mt-4">{t.erase}</p><div className="mt-5" aria-live="polite">{release && serial && (!verified.key ? <p>{t.verify}</p> : verified.error && <p role="alert">{t.verifyError} <button className="text-link" onClick={() => setRetry((n) => n + 1)}>{t.retry}</button></p>)}</div>
    <div className="mt-5">{ready ? <esp-web-install-button key={key} manifest={verified.url}><button slot="activate" className="primary-button w-full"><Zap size={18} />{t.flash}</button><span slot="unsupported">{t.browser}</span><span slot="not-allowed">{t.browser}</span></esp-web-install-button> : <><button className="primary-button w-full" disabled><Usb size={18} />{t.flash}</button>{!wiringConfirmed && <p className="muted mt-2 text-sm">{t.prepare}</p>}</>}</div><p className="muted mt-3 text-sm leading-6">{t.flashHint}</p>
    <details className="mt-6"><summary>{t.troubleshoot}</summary><dl className="mt-4 space-y-4">{t.trouble.map(([title, body]) => <div key={title}><dt className="font-semibold">{title}</dt><dd className="muted mt-1 text-sm leading-6">{body}</dd></div>)}</dl></details></>;
}
function Guide({ radar, t }) {
  const [copied, setCopied] = useState('');
  const copyYaml = async () => { try { await navigator.clipboard.writeText(yaml); setCopied(t.copied); } catch { setCopied(t.copyError); } };
  return <><p className="muted leading-7">{t.guideHint}</p><div className="mt-5 space-y-3">{t.guide.map(([title, body], index) => <details className="guide-item" key={index} open={index === 0 ? true : undefined}><summary><span>{index + 1}</span>{title}</summary><p className="muted mt-3 text-sm leading-7">{radar?.dimension === '1D' && [4, 5].includes(index) ? t.oneDGuide : body}</p>{index === 2 && <a className="secondary-button mt-4" href="https://my.home-assistant.io/redirect/hacs_repository/?owner=zomco&repository=mmwave-card&category=plugin" target="_blank" rel="noreferrer">{t.installCard} ↗</a>}</details>)}</div><a className="text-link mt-5 inline-block" href={radar?.cardDocs || 'https://github.com/zomco/mmwave-card'} target="_blank" rel="noreferrer">{t.cardDocs} ↗</a>{radar?.id === 'r60abd1' && <details className="guide-item mt-4"><summary>{t.example}</summary><pre className="code-block mt-3"><code>{yaml}</code></pre><button className="secondary-button mt-3" onClick={copyYaml}>{t.copy}</button><span role="status" className="ml-3 text-xs">{copied}</span></details>}</>;
}
export default function App() {
  const [language, setLanguage] = useState(() => preference('mmwave-language', navigator.language.startsWith('zh') ? 'zh' : 'en', ['zh', 'en']));
  const [theme, setTheme] = useState(() => preference('mmwave-theme', matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light', ['dark', 'light']));
  const [step, setStep] = useState(0);
  const [radarId, setRadar] = useState('');
  const [boardId, setBoard] = useState('');
  const [wiringConfirmed, confirmWiring] = useState(false);
  const heading = useRef(null);
  const t = copy[language];
  const radar = radars.find((r) => r.id === radarId);
  const board = boards.find((b) => b.id === boardId);
  useEffect(() => { persist('mmwave-language', language); document.documentElement.lang = language === 'zh' ? 'zh-CN' : 'en'; }, [language]);
  useEffect(() => { persist('mmwave-theme', theme); document.documentElement.classList.toggle('dark', theme === 'dark'); }, [theme]);
  useEffect(() => { const redirect = () => { if (location.hash.startsWith('#/')) history.replaceState(null, '', `${location.pathname}${location.search}#diy`); }; redirect(); window.addEventListener('hashchange', redirect); return () => window.removeEventListener('hashchange', redirect); }, []);
  const go = (index) => { setStep(index); requestAnimationFrame(() => { heading.current?.focus(); document.getElementById('diy')?.scrollIntoView({ block: 'start' }); }); };
  const selectRadar = (id) => { setRadar(id); confirmWiring(false); };
  const selectBoard = (id) => { setBoard(id); confirmWiring(false); };
  return <><a className="skip-link" href="#diy">{t.skip}</a><header className="site-header"><div className="shell flex items-center justify-between gap-3 py-4"><a href="#diy" className="flex items-center gap-3 font-semibold"><Radar className="text-brand-600" />MMWave <span className="hidden text-xs font-normal sm:inline">DIY</span></a><div className="flex gap-2"><button className="secondary-button" onClick={() => setLanguage(language === 'zh' ? 'en' : 'zh')}><Globe2 size={16} />{t.language}</button><button className="icon-button" aria-label={t.theme} onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}>{theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}</button><a href={repo} className="secondary-button hidden sm:inline-flex" target="_blank" rel="noreferrer">GitHub ↗</a></div></div></header>
    <main className="shell pb-16"><section className="py-10 sm:py-14"><span className="eyebrow">{t.badge}</span><h1 className="mt-5 text-3xl font-semibold tracking-tight sm:text-5xl">{t.title}</h1><p className="muted mt-4 max-w-2xl leading-7">{t.subtitle}</p></section>
      <section id="diy" className="scroll-mt-24"><nav className="step-nav" aria-label={t.selection}>{t.steps.map((title, index) => <button key={title} className={step === index ? 'current' : ''} aria-current={step === index ? 'step' : undefined} onClick={() => go(index)}><span>{index + 1}</span>{title}</button>)}</nav><div className="mt-5 grid items-start gap-5 lg:grid-cols-[1fr_260px]"><div className="surface min-w-0 p-5 sm:p-8"><h2 ref={heading} tabIndex={-1} className="section-title outline-none">{t.steps[step]}</h2><div className="mt-4">
        {step === 0 && <><p className="muted leading-7">{t.radarHint}</p><DevicePicker kind="radar" devices={radars} selected={radar} onSelect={selectRadar} {...{ language, t }} />{radar && <RadarDetails {...{ radar, language, t }} />}</>}
        {step === 1 && <><p className="muted leading-7">{t.boardHint}</p><DevicePicker kind="board" devices={boards} selected={board} onSelect={selectBoard} {...{ language, t }} />{radar && board ? <><Wiring {...{ radar, board, t, language }} /><label className="check-row mt-5"><input type="checkbox" checked={wiringConfirmed} onChange={(e) => confirmWiring(e.target.checked)} />{t.boardConfirm}</label></> : <p className="notice mt-5">{t.prepare}</p>}</>}
        {step === 2 && <Flash {...{ radar, board, wiringConfirmed, t }} />}{step === 3 && <Guide {...{ radar, t }} />}
        </div><div className="mt-8 flex flex-wrap justify-between gap-3 border-t border-slate-200 pt-5 dark:border-white/10">{step > 0 ? <button className="secondary-button" onClick={() => go(step - 1)}><ChevronLeft size={16} />{t.back}</button> : <span />}{step < 3 && <button className="primary-button" disabled={step === 0 ? !radar : step === 1 ? !radar || !board || !wiringConfirmed : false} onClick={() => go(step + 1)}>{step === 2 ? t.flashDone : t.next}<ArrowRight size={16} /></button>}</div></div>
        <aside className="soft-surface p-5"><h2 className="text-sm font-semibold">{t.selection}</h2><dl className="mt-4 space-y-4 text-sm"><div><dt className="muted text-xs">{t.steps[0]}</dt><dd className="mt-1">{radar?.name || '—'}</dd></div><div><dt className="muted text-xs">{t.steps[1]}</dt><dd className="mt-1">{board?.name || '—'}</dd></div></dl><p className="muted mt-5 border-t border-slate-200 pt-4 text-xs leading-6 dark:border-white/10">GPIO21 TX → RX<br />GPIO20 RX ← TX<br />GND ↔ GND</p><a className="text-link mt-4 inline-block text-xs" href="#features">{t.features.link}</a></aside></div></section>
      <FeatureShowcase t={t.features} onGuide={() => go(3)} />
    </main><footer className="shell border-t border-slate-200 py-6 text-xs text-slate-500 dark:border-white/10">{t.footer}</footer></>;
}
