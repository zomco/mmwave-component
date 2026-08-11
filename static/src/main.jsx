import React, { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  AlertTriangle, ArrowRight, Cable, Check, CheckCircle2, ChevronDown, Cpu,
  Crosshair, Github, Globe2, Info, Layers3, Map, Menu, Moon, Move3d, PlugZap,
  Radar, RadioTower, Ruler, ShieldCheck, Sparkles, Sun, Target, Usb, X, Zap,
} from 'lucide-react';
import 'esp-web-tools/dist/web/install-button.js';
import { copy } from './content';
import './index.css';

const GITHUB_URL = 'https://github.com/zomco/mmwave-component';
const HACS_URL = 'https://my.home-assistant.io/redirect/hacs_repository/?owner=zomco&repository=mmwave-card&category=plugin';
const assetUrl = (path) => new URL(path, document.baseURI).href;

const AppContext = createContext(null);

function AppProvider({ children }) {
  const [language, setLanguage] = useState(() => localStorage.getItem('mmwave-language') || (navigator.language.startsWith('zh') ? 'zh' : 'en'));
  const [theme, setTheme] = useState(() => localStorage.getItem('mmwave-theme') || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'));
  const t = copy[language];

  useEffect(() => {
    localStorage.setItem('mmwave-language', language);
    document.documentElement.lang = language === 'zh' ? 'zh-CN' : 'en';
  }, [language]);

  useEffect(() => {
    localStorage.setItem('mmwave-theme', theme);
    document.documentElement.classList.toggle('dark', theme === 'dark');
  }, [theme]);

  return (
    <AppContext.Provider value={{ language, setLanguage, theme, setTheme, t }}>
      {children}
    </AppContext.Provider>
  );
}

const useApp = () => useContext(AppContext);

function Logo() {
  return (
    <a href="#/" className="focus-ring flex items-center gap-3 rounded-lg" aria-label="mmWave Radar home">
      <span className="flex h-10 w-10 items-center justify-center rounded-xl border border-brand-600/20 bg-brand-600/10">
        <img src={assetUrl('favicon.svg')} alt="" className="h-7 w-7" />
      </span>
      <span className="leading-none">
        <strong className="block text-sm font-bold tracking-tight text-slate-950 dark:text-white">mmWave Radar</strong>
        <span className="mt-1 block text-[10px] font-semibold uppercase tracking-[0.18em] text-brand-700 dark:text-brand-300">Spatial firmware</span>
      </span>
    </a>
  );
}

function Header({ route }) {
  const { language, setLanguage, theme, setTheme, t } = useApp();
  const [open, setOpen] = useState(false);
  const navClass = (isActive) => `focus-ring rounded-lg px-3 py-2 text-sm font-semibold transition ${isActive ? 'bg-brand-600/10 text-brand-700 dark:text-brand-300' : 'text-slate-600 hover:text-slate-950 dark:text-slate-300 dark:hover:text-white'}`;

  return (
    <header className="sticky top-0 z-50 border-b border-slate-200/80 bg-[#f4f7f6]/85 backdrop-blur-xl dark:border-white/10 dark:bg-[#06100d]/85">
      <div className="shell flex h-16 items-center justify-between">
        <Logo />
        <nav className="hidden items-center gap-1 md:flex" aria-label="Primary navigation">
          <a href="#/" className={navClass(route === '/')}>{t.navInstall}</a>
          <a href="#/technology" className={navClass(route === '/technology')}>{t.navTechnology}</a>
        </nav>
        <div className="hidden items-center gap-2 md:flex">
          <button className="secondary-button" onClick={() => setLanguage(language === 'zh' ? 'en' : 'zh')}><Globe2 size={16} />{t.language}</button>
          <button className="icon-button" onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')} aria-label={t.theme}>{theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}</button>
          <a className="icon-button" href={GITHUB_URL} target="_blank" rel="noreferrer" aria-label={t.openGithub}><Github size={18} /></a>
        </div>
        <button className="icon-button md:hidden" onClick={() => setOpen((value) => !value)} aria-expanded={open} aria-label="Menu">{open ? <X size={19} /> : <Menu size={19} />}</button>
      </div>
      {open && (
        <div className="shell border-t border-slate-200 py-3 dark:border-white/10 md:hidden">
          <nav className="grid gap-1" onClick={() => setOpen(false)}>
            <a href="#/" className={navClass(route === '/')}>{t.navInstall}</a>
            <a href="#/technology" className={navClass(route === '/technology')}>{t.navTechnology}</a>
          </nav>
          <div className="mt-3 flex gap-2 border-t border-slate-200 pt-3 dark:border-white/10">
            <button className="secondary-button flex-1" onClick={() => setLanguage(language === 'zh' ? 'en' : 'zh')}><Globe2 size={16} />{t.language}</button>
            <button className="icon-button" onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')} aria-label={t.theme}>{theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}</button>
          </div>
        </div>
      )}
    </header>
  );
}

function Hero() {
  const { t } = useApp();
  return (
    <section className="shell grid gap-10 pb-14 pt-14 lg:grid-cols-[1.05fr_.95fr] lg:items-center lg:pb-20 lg:pt-20">
      <div>
        <span className="eyebrow"><Radar size={14} />{t.heroBadge}</span>
        <h1 className="mt-6 max-w-3xl text-4xl font-semibold leading-[1.08] tracking-[-0.045em] text-slate-950 sm:text-6xl dark:text-white">
          {t.heroTitleA}<br /><span className="text-brand-700 dark:text-brand-300">{t.heroTitleB}</span>
        </h1>
        <p className="muted mt-6 max-w-2xl text-base leading-7 sm:text-lg">{t.heroDescription}</p>
        <div className="mt-8 flex flex-col gap-3 sm:flex-row">
          <button onClick={() => document.getElementById('installer')?.scrollIntoView()} className="primary-button">{t.heroPrimary}<ArrowRight size={17} /></button>
          <a href="#/technology" className="secondary-button">{t.heroSecondary}</a>
        </div>
        <div className="mt-8 flex flex-wrap gap-x-5 gap-y-2 text-xs font-medium text-slate-500 dark:text-slate-400">
          {[t.trustNoInstall, t.trustPrivate, t.trustFixed].map((item) => <span className="flex items-center gap-1.5" key={item}><CheckCircle2 size={14} className="text-brand-600" />{item}</span>)}
        </div>
      </div>
      <LivePreview />
    </section>
  );
}

function LivePreview() {
  const { t } = useApp();
  return (
    <div className="surface overflow-hidden p-3 sm:p-4">
      <div className="mb-3 flex items-center justify-between px-1">
        <div><strong className="text-sm text-slate-900 dark:text-white">{t.previewLabel}</strong><span className="mt-0.5 block text-[10px] text-slate-500">LD2450 · ESP32-C3</span></div>
        <span className="inline-flex items-center gap-1.5 rounded-full border border-brand-600/25 bg-brand-600/10 px-2.5 py-1 text-[10px] font-semibold text-brand-700 dark:text-brand-300"><span className="h-1.5 w-1.5 rounded-full bg-brand-500" />{t.previewClear}</span>
      </div>
      <div className="radar-grid radar-sweep relative aspect-[4/3] overflow-hidden rounded-xl border border-white/10">
        <div className="absolute inset-[12%] rounded-[18%] border-2 border-dashed border-brand-400/40" />
        <div className="absolute bottom-[16%] left-1/2 z-10 -translate-x-1/2 text-center">
          <span className="mx-auto flex h-8 w-8 items-center justify-center rounded-lg border border-brand-400/50 bg-brand-500/20 text-brand-300"><RadioTower size={17} /></span>
          <span className="mt-1 block text-[9px] font-semibold text-brand-200">{t.previewRadar}</span>
        </div>
        <div className="absolute left-[32%] top-[36%] z-10 h-3 w-3 rounded-full border-2 border-white bg-brand-400 shadow-[0_0_0_8px_rgba(69,201,154,.12)]" />
        <div className="absolute right-[29%] top-[52%] z-10 h-3 w-3 rounded-full border-2 border-white bg-amber-400 shadow-[0_0_0_8px_rgba(251,191,36,.10)]" />
        <div className="absolute left-[33%] top-[38%] h-[20%] w-[32%] rotate-[17deg] border-t border-dashed border-brand-300/40" />
        <span className="absolute bottom-3 left-3 rounded-md bg-black/40 px-2 py-1 text-[9px] font-semibold text-slate-300">4.0 m × 3.5 m</span>
      </div>
    </div>
  );
}

function CompatibilityNotice({ supported }) {
  const { t } = useApp();
  if (supported) return null;
  return (
    <div className="shell mb-8">
      <div className="flex gap-3 rounded-xl border border-amber-400/35 bg-amber-50 p-4 text-amber-950 dark:bg-amber-400/10 dark:text-amber-100" role="alert">
        <AlertTriangle className="mt-0.5 shrink-0" size={20} />
        <div><strong className="block text-sm">{t.unsupportedTitle}</strong><p className="mt-1 text-sm leading-6 opacity-80">{t.unsupportedBody}</p></div>
      </div>
    </div>
  );
}

function Installer({ models, loading, error, selectedId, setSelectedId, serialSupported }) {
  const { t } = useApp();
  const selected = models.find((model) => model.id === selectedId);
  return (
    <section id="installer" className="shell scroll-mt-24 py-14 sm:py-20">
      <div className="mx-auto max-w-3xl text-center">
        <span className="eyebrow"><PlugZap size={14} />{t.installerEyebrow}</span>
        <h2 className="section-title mt-4">{t.installerTitle}</h2>
        <p className="muted mt-3 leading-7">{t.installerDescription}</p>
      </div>
      <div className="mt-10 grid gap-5 lg:grid-cols-2">
        <div className="surface flex flex-col p-6 sm:p-7">
          <div className="flex items-start gap-3"><span className="step-number">1</span><div><h3 className="font-semibold text-slate-950 dark:text-white">{t.stepDevice}</h3><p className="muted mt-1 text-sm">{t.stepDeviceHint}</p></div></div>
          <label className="relative mt-7 block">
            <span className="sr-only">{t.stepDevice}</span>
            <select className="focus-ring h-12 w-full appearance-none rounded-lg border border-slate-300 bg-white px-4 pr-11 text-sm font-semibold text-slate-900 dark:border-white/10 dark:bg-[#07110e] dark:text-white" value={selectedId} onChange={(event) => setSelectedId(event.target.value)} disabled={loading || Boolean(error)}>
              <option value="">{loading ? t.loadModels : error ? t.loadModelsError : t.selectPlaceholder}</option>
              {models.map((model) => <option key={model.id} value={model.id}>{model.name}</option>)}
            </select>
            <ChevronDown className="pointer-events-none absolute right-4 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
          </label>
          <div className="mt-4 flex items-center justify-between rounded-lg border border-brand-600/20 bg-brand-600/[0.07] px-4 py-3">
            <span className="flex items-center gap-2 text-xs font-semibold text-brand-800 dark:text-brand-200"><Cpu size={16} />{t.fixedChip}</span><strong className="text-sm text-brand-800 dark:text-brand-200">ESP32-C3</strong>
          </div>
          {selected && <div className="mt-auto flex flex-wrap gap-2 pt-5"><span className="rounded-full bg-slate-100 px-3 py-1 text-[11px] font-semibold text-slate-600 dark:bg-white/[0.06] dark:text-slate-300">{t.version}: {selected.version}</span><span className="rounded-full bg-slate-100 px-3 py-1 text-[11px] font-semibold text-slate-600 dark:bg-white/[0.06] dark:text-slate-300">{t.chip}: {selected.chip_family || 'ESP32-C3'}</span></div>}
        </div>
        <div className={`surface flex flex-col p-6 transition sm:p-7 ${selected ? 'ring-1 ring-brand-600/20' : 'opacity-70'}`}>
          <div className="flex items-start gap-3"><span className="step-number">2</span><div><h3 className="font-semibold text-slate-950 dark:text-white">{t.stepFlash}</h3><p className="muted mt-1 text-sm">{t.stepFlashHint}</p></div></div>
          <div className="mt-7 flex-1 rounded-xl border border-slate-200 bg-slate-50 p-4 dark:border-white/10 dark:bg-black/20">
            <div className="mb-4 flex items-center justify-between"><span className="flex items-center gap-2 text-sm font-semibold text-slate-800 dark:text-slate-200"><Usb size={17} />{selected?.name || 'ESP32-C3'}</span><span className={`rounded-full px-2.5 py-1 text-[10px] font-bold ${selected ? 'bg-brand-600/10 text-brand-700 dark:text-brand-300' : 'bg-slate-200 text-slate-500 dark:bg-white/10 dark:text-slate-400'}`}>{selected ? t.flashReady : t.flashWaiting}</span></div>
            {selected && serialSupported ? (
              <esp-web-install-button manifest={selected.manifest}><span slot="unsupported">{t.webSerialUnavailable}</span></esp-web-install-button>
            ) : (
              <button className="primary-button w-full" disabled><Zap size={17} />{serialSupported ? t.flashWaiting : t.webSerialUnavailable}</button>
            )}
            <p className="muted mt-3 text-xs leading-5">{t.flashButtonHint}</p>
          </div>
        </div>
      </div>
      <div className="soft-surface mt-5 grid gap-4 p-5 md:grid-cols-[auto_1fr] md:items-center">
        <strong className="flex items-center gap-2 text-sm text-slate-900 dark:text-white"><ShieldCheck size={18} className="text-brand-600" />{t.beforeFlash}</strong>
        <div className="grid gap-2 text-xs text-slate-600 sm:grid-cols-3 dark:text-slate-400">{[t.checkCable, t.checkClose, t.checkPower].map((item) => <span className="flex items-center gap-1.5" key={item}><Check size={14} className="shrink-0 text-brand-600" />{item}</span>)}</div>
      </div>
    </section>
  );
}

function AfterFlash() {
  const { t } = useApp();
  const steps = [[Usb, t.after1Title, t.after1Body], [RadioTower, t.after2Title, t.after2Body], [CheckCircle2, t.after3Title, t.after3Body]];
  return (
    <section className="border-y border-slate-200/80 bg-white/55 py-14 dark:border-white/10 dark:bg-white/[0.025] sm:py-20">
      <div className="shell"><div className="max-w-2xl"><h2 className="section-title">{t.afterTitle}</h2><p className="muted mt-3">{t.afterDescription}</p></div>
        <div className="mt-9 grid gap-4 lg:grid-cols-3">{steps.map(([Icon, title, body], index) => <article className="soft-surface p-5" key={title}><div className="mb-5 flex items-center justify-between"><span className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-600/10 text-brand-700 dark:text-brand-300"><Icon size={20} /></span><span className="text-xs font-bold text-slate-400">0{index + 1}</span></div><h3 className="font-semibold text-slate-950 dark:text-white">{title}</h3><p className="muted mt-2 text-sm leading-6">{body}</p></article>)}</div>
      </div>
    </section>
  );
}

function HardwareReference({ selected }) {
  const { t } = useApp();
  const [tab, setTab] = useState('wiring');
  const wiring = selected?.wiring_images || [];
  const boardImages = [['esp32c3/front.png', t.boardFront], ['esp32c3/back.png', t.boardBack], ['esp32c3/pinout.png', t.boardPinout]];
  const rows = [[t.wiringPower, t.wiringPowerValue], [t.wiringGround, t.wiringGroundValue], [t.wiringTx, t.wiringTxValue], [t.wiringRx, t.wiringRxValue]];
  return (
    <section className="shell py-14 sm:py-20">
      <div className="flex flex-col justify-between gap-5 sm:flex-row sm:items-end"><div><h2 className="section-title">{t.referenceTitle}</h2><p className="muted mt-3 max-w-2xl">{t.referenceDescription}</p></div><span className="eyebrow"><Cpu size={14} />{selected?.name || 'ESP32-C3'}</span></div>
      <div className="surface mt-8 overflow-hidden">
        <div className="flex gap-1 border-b border-slate-200 p-2 dark:border-white/10">{[['wiring', Cable, t.tabWiring], ['board', Cpu, t.tabBoard]].map(([id, Icon, label]) => <button key={id} onClick={() => setTab(id)} className={`focus-ring flex items-center gap-2 rounded-lg px-4 py-2.5 text-sm font-semibold transition ${tab === id ? 'bg-brand-600/10 text-brand-700 dark:text-brand-300' : 'text-slate-500 hover:text-slate-900 dark:hover:text-white'}`}><Icon size={17} />{label}</button>)}</div>
        <div className="p-5 sm:p-7">
          {tab === 'wiring' ? wiring.length ? <div className="grid gap-4 md:grid-cols-2">{wiring.map((image) => <a href={assetUrl(image)} target="_blank" rel="noreferrer" className="group overflow-hidden rounded-xl border border-slate-200 bg-slate-50 dark:border-white/10 dark:bg-black/20" key={image}><img src={assetUrl(image)} alt={`${selected.name} wiring`} className="h-full max-h-[34rem] w-full object-contain transition group-hover:scale-[1.01]" /></a>)}</div> : <div className="grid gap-6 lg:grid-cols-[.8fr_1.2fr]"><div className="rounded-xl border border-amber-400/30 bg-amber-50 p-5 text-sm leading-6 text-amber-950 dark:bg-amber-400/10 dark:text-amber-100"><Info size={19} className="mb-3" />{t.wiringFallback}</div><div><dl className="overflow-hidden rounded-xl border border-slate-200 dark:border-white/10">{rows.map(([term, description]) => <div className="grid grid-cols-[7rem_1fr] gap-3 border-b border-slate-200 px-4 py-3 text-sm last:border-b-0 dark:border-white/10" key={term}><dt className="font-semibold text-slate-900 dark:text-white">{term}</dt><dd className="text-slate-600 dark:text-slate-400">{description}</dd></div>)}</dl><p className="mt-3 flex gap-2 text-xs text-slate-500"><AlertTriangle size={15} className="shrink-0 text-amber-500" />{t.wiringWarning}</p></div></div> : <div className="grid gap-4 sm:grid-cols-3">{boardImages.map(([image, label]) => <figure className="overflow-hidden rounded-xl border border-slate-200 bg-slate-50 dark:border-white/10 dark:bg-black/20" key={image}><div className="aspect-[4/3] p-4"><img src={assetUrl(image)} alt={`ESP32-C3 ${label}`} className="h-full w-full object-contain" /></div><figcaption className="border-t border-slate-200 px-4 py-3 text-center text-xs font-semibold text-slate-600 dark:border-white/10 dark:text-slate-300">{label}</figcaption></figure>)}</div>}
        </div>
      </div>
    </section>
  );
}

function CardGuide() {
  const { t } = useApp();
  const steps = [
    [Sparkles, t.cardInstall, t.cardInstallBody, null], [Ruler, t.cardPosition, t.cardPositionBody, t.cardPositionDone],
    [Crosshair, t.cardCalibrate, t.cardCalibrateBody, t.cardCalibrateDone], [Target, t.cardVerify, t.cardVerifyBody, t.cardVerifyDone],
  ];
  return (
    <section className="border-t border-slate-200/80 bg-white/55 py-14 dark:border-white/10 dark:bg-white/[0.025] sm:py-20">
      <div className="shell"><div className="max-w-3xl"><span className="eyebrow"><Layers3 size={14} />{t.cardEyebrow}</span><h2 className="section-title mt-4">{t.cardTitle}</h2><p className="muted mt-3 max-w-2xl leading-7">{t.cardDescription}</p></div>
        <div className="mt-10 grid gap-4 lg:grid-cols-2">{steps.map(([Icon, title, body, done], index) => <article className="surface relative overflow-hidden p-6 sm:p-7" key={title}><span className="absolute right-5 top-4 text-5xl font-bold tracking-[-.08em] text-brand-600/[0.07]">0{index + 1}</span><div className="flex h-11 w-11 items-center justify-center rounded-xl bg-brand-600/10 text-brand-700 dark:text-brand-300"><Icon size={21} /></div><h3 className="mt-5 text-lg font-semibold text-slate-950 dark:text-white">{title}</h3><p className="muted mt-2 text-sm leading-7">{body}</p>{index === 0 && <a href={HACS_URL} target="_blank" rel="noreferrer" className="secondary-button mt-5">{t.cardInstallAction}<ArrowRight size={15} /></a>}{done && <p className="mt-5 flex gap-2 rounded-lg border border-brand-600/15 bg-brand-600/[0.06] p-3 text-xs font-medium leading-5 text-brand-800 dark:text-brand-200"><CheckCircle2 size={16} className="mt-0.5 shrink-0" />{done}</p>}</article>)}</div>
      </div>
    </section>
  );
}

function InstallerPage() {
  const [models, setModels] = useState([]);
  const [selectedId, setSelectedId] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const serialSupported = Boolean(navigator.serial && window.isSecureContext);

  useEffect(() => {
    const isLocalPreview = ['localhost', '127.0.0.1'].includes(window.location.hostname);
    fetch(assetUrl(isLocalPreview ? 'models.preview.json' : 'models.json'))
      .then((response) => { if (!response.ok) throw new Error('models'); return response.json(); })
      .then((items) => {
        const compatible = items.filter((item) => !item.chip_family || item.chip_family.toUpperCase().includes('ESP32-C3'));
        setModels(compatible);
        if (compatible.length === 1) setSelectedId(compatible[0].id);
      })
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, []);

  const selected = useMemo(() => models.find((model) => model.id === selectedId), [models, selectedId]);
  return <><Hero /><CompatibilityNotice supported={serialSupported} /><Installer {...{ models, loading, error, selectedId, setSelectedId, serialSupported }} /><AfterFlash /><HardwareReference selected={selected} /><CardGuide /></>;
}

function TechnologyPage() {
  const { t } = useApp();
  const problems = [[Move3d, t.problem1, t.problem1Body], [ShieldCheck, t.problem2, t.problem2Body], [Target, t.problem3, t.problem3Body]];
  const pipeline = [[Cable, t.pipe1, t.pipe1Body], [Move3d, t.pipe2, t.pipe2Body], [Map, t.pipe3, t.pipe3Body], [RadioTower, t.pipe4, t.pipe4Body]];
  return (
    <main>
      <section className="shell py-14 sm:py-20"><div className="max-w-4xl"><span className="eyebrow"><Cpu size={14} />{t.techEyebrow}</span><h1 className="mt-5 text-4xl font-semibold leading-tight tracking-[-.04em] text-slate-950 sm:text-6xl dark:text-white">{t.techTitle}</h1><p className="muted mt-6 max-w-3xl text-lg leading-8">{t.techDescription}</p><div className="mt-8 flex max-w-3xl gap-3 rounded-xl border border-brand-600/20 bg-brand-600/[0.07] p-4 text-sm leading-6 text-brand-900 dark:text-brand-100"><Info className="mt-0.5 shrink-0" size={19} /><p>{t.techNote}</p></div></div></section>
      <section className="border-y border-slate-200/80 bg-white/55 py-14 dark:border-white/10 dark:bg-white/[0.025] sm:py-20"><div className="shell"><h2 className="section-title">{t.problemsTitle}</h2><div className="mt-8 grid gap-4 lg:grid-cols-3">{problems.map(([Icon, title, body]) => <article className="surface p-6" key={title}><Icon className="text-brand-600" size={23} /><h3 className="mt-5 font-semibold text-slate-950 dark:text-white">{title}</h3><p className="muted mt-2 text-sm leading-6">{body}</p></article>)}</div></div></section>
      <section className="shell py-14 sm:py-20"><h2 className="section-title">{t.pipelineTitle}</h2><div className="mt-8 grid gap-3 lg:grid-cols-4">{pipeline.map(([Icon, title, body], index) => <div className="relative" key={title}><article className="soft-surface h-full p-5"><div className="flex items-center justify-between"><span className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-600/10 text-brand-700 dark:text-brand-300"><Icon size={20} /></span><span className="text-xs font-bold text-slate-400">0{index + 1}</span></div><h3 className="mt-5 font-semibold text-slate-950 dark:text-white">{title}</h3><p className="muted mt-2 text-xs leading-5">{body}</p></article>{index < pipeline.length - 1 && <ArrowRight className="absolute -right-3 top-1/2 z-10 hidden -translate-y-1/2 rounded-full bg-[#f4f7f6] p-1 text-brand-600 dark:bg-[#06100d] lg:block" size={24} />}</div>)}</div>
        <div className="mt-8 grid gap-4 lg:grid-cols-2"><article className="surface p-6 sm:p-7"><Move3d className="text-brand-600" /><h3 className="mt-5 text-xl font-semibold text-slate-950 dark:text-white">{t.coordinateTitle}</h3><p className="muted mt-3 leading-7">{t.coordinateBody}</p><code className="mt-5 block overflow-x-auto rounded-lg bg-[#08130f] p-4 text-xs text-brand-200">room = Rz(yaw) · Ry(pitch) · Rx(roll) · local + position</code></article><article className="surface p-6 sm:p-7"><Map className="text-brand-600" /><h3 className="mt-5 text-xl font-semibold text-slate-950 dark:text-white">{t.boundaryTitle}</h3><p className="muted mt-3 leading-7">{t.boundaryBody}</p><div className="mt-5 flex items-center gap-3 rounded-lg border border-slate-200 p-4 dark:border-white/10"><span className="h-12 w-16 rounded-[45%_20%_35%_25%] border-2 border-dashed border-brand-500 bg-brand-500/10" /><span className="text-xs font-semibold text-slate-600 dark:text-slate-300">transform → point-in-polygon → publish / drop</span></div></article></div>
      </section>
      <section className="border-y border-slate-200/80 bg-white/55 py-14 dark:border-white/10 dark:bg-white/[0.025] sm:py-20"><div className="shell grid gap-10 lg:grid-cols-2"><div><h2 className="section-title">{t.scenariosTitle}</h2><div className="mt-6 grid gap-3 sm:grid-cols-2">{t.scenarios.map((item) => <div className="soft-surface flex gap-3 p-4 text-sm font-medium text-slate-700 dark:text-slate-200" key={item}><CheckCircle2 className="shrink-0 text-brand-600" size={18} />{item}</div>)}</div></div><div><h2 className="section-title">{t.limitsTitle}</h2><ul className="mt-6 space-y-3">{t.limits.map((item) => <li className="flex gap-3 text-sm leading-6 text-slate-600 dark:text-slate-400" key={item}><AlertTriangle className="mt-0.5 shrink-0 text-amber-500" size={17} />{item}</li>)}</ul></div></div></section>
      <section className="shell py-14 sm:py-20"><div className="max-w-3xl"><h2 className="section-title">{t.compareTitle}</h2><p className="muted mt-3">{t.compareDescription}</p></div><div className="surface mt-8 overflow-x-auto"><table className="w-full min-w-[760px] border-collapse text-left text-sm"><thead><tr className="bg-brand-600/[0.07]">{t.compareHeaders.map((header, index) => <th className={`border-b border-slate-200 px-5 py-4 font-semibold dark:border-white/10 ${index === 1 ? 'text-brand-700 dark:text-brand-300' : 'text-slate-900 dark:text-white'}`} key={header}>{header}</th>)}</tr></thead><tbody>{t.compareRows.map((row) => <tr className="border-b border-slate-200 last:border-0 dark:border-white/10" key={row[0]}>{row.map((cell, index) => <td className={`px-5 py-4 align-top leading-6 ${index === 0 ? 'font-semibold text-slate-900 dark:text-white' : index === 1 ? 'bg-brand-600/[0.025] text-slate-700 dark:text-slate-200' : 'text-slate-600 dark:text-slate-400'}`} key={cell}>{cell}</td>)}</tr>)}</tbody></table></div></section>
      <section className="shell pb-20"><div className="overflow-hidden rounded-2xl bg-[#08130f] p-7 text-white shadow-card sm:flex sm:items-center sm:justify-between sm:p-10"><div><h2 className="text-2xl font-semibold">{t.techCtaTitle}</h2><p className="mt-2 text-sm text-slate-400">{t.techCtaBody}</p></div><a href="#/" className="primary-button mt-6 sm:mt-0">{t.navInstall}<ArrowRight size={17} /></a></div></section>
    </main>
  );
}

function Footer() {
  const { t } = useApp();
  return <footer className="border-t border-slate-200 py-8 dark:border-white/10"><div className="shell flex flex-col gap-3 text-xs text-slate-500 sm:flex-row sm:items-center sm:justify-between"><span>{t.footerBuilt}</span><a className="focus-ring inline-flex items-center gap-1.5 rounded text-slate-600 hover:text-brand-700 dark:text-slate-300 dark:hover:text-brand-300" href={GITHUB_URL} target="_blank" rel="noreferrer"><Github size={14} />{t.footerSource}</a></div></footer>;
}

function App() {
  const readRoute = () => window.location.hash.replace(/^#/, '') || '/';
  const [route, setRoute] = useState(readRoute);

  useEffect(() => {
    const updateRoute = () => setRoute(readRoute());
    window.addEventListener('hashchange', updateRoute);
    return () => window.removeEventListener('hashchange', updateRoute);
  }, []);

  useEffect(() => window.scrollTo({ top: 0, behavior: 'auto' }), [route]);

  return <AppProvider><Header route={route} />{route === '/technology' ? <TechnologyPage /> : <InstallerPage />}<Footer /></AppProvider>;
}

createRoot(document.getElementById('root')).render(<React.StrictMode><App /></React.StrictMode>);
