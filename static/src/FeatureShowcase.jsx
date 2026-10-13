import React, { useEffect, useId, useRef, useState } from 'react';
import { ArrowRight, Monitor, Pause, Play } from 'lucide-react';
import { DEMO_DURATION_MS, STILL_PROGRESS, demoFrame } from './feature-demo';

function useDemoPlayer(section) {
  const [playing, setPlaying] = useState(() => !window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  const [visible, setVisible] = useState(false);
  const [foreground, setForeground] = useState(() => !document.hidden);
  const [progress, setProgress] = useState(() => playing ? 0 : STILL_PROGRESS);
  const elapsed = useRef(progress * DEMO_DURATION_MS);

  useEffect(() => {
    const motion = window.matchMedia('(prefers-reduced-motion: reduce)');
    const reduce = () => { if (motion.matches) setPlaying(false); };
    const visibility = () => setForeground(!document.hidden);
    motion.addEventListener('change', reduce);
    document.addEventListener('visibilitychange', visibility);
    const observer = new IntersectionObserver(([entry]) => setVisible(entry.isIntersecting));
    observer.observe(section.current);
    return () => {
      observer.disconnect();
      motion.removeEventListener('change', reduce);
      document.removeEventListener('visibilitychange', visibility);
    };
  }, [section]);

  useEffect(() => {
    if (!playing || !visible || !foreground) return;
    let frame;
    let last;
    let rendered = 0;
    const tick = (now) => {
      // Cap elapsed jumps when the browser stalls; render at no more than 30 fps.
      if (last !== undefined) elapsed.current = (elapsed.current + Math.min(now - last, 100)) % DEMO_DURATION_MS;
      last = now;
      if (now - rendered >= 1000 / 30) {
        setProgress(elapsed.current / DEMO_DURATION_MS);
        rendered = now;
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [playing, visible, foreground]);

  const seek = (value) => {
    setPlaying(false);
    elapsed.current = value * DEMO_DURATION_MS;
    setProgress(value);
  };
  return { playing, setPlaying, progress, seek };
}

function Scene({ title, description, children }) {
  const id = useId();
  return <svg className="feature-scene" viewBox="0 0 336 244" role="img" aria-labelledby={`${id}-title`} aria-describedby={`${id}-desc`}>
    <title id={`${id}-title`}>{title}</title>
    <desc id={`${id}-desc`}>{description}</desc>
    <defs><pattern id={`${id}-grid`} width="20" height="20" patternUnits="userSpaceOnUse"><path d="M 20 0 H 0 V 20" className="demo-grid-line" fill="none" /></pattern></defs>
    <rect width="336" height="244" fill={`url(#${id}-grid)`} />
    {children}
  </svg>;
}

function Target({ x, y, active = true }) {
  return <g transform={`translate(${x} ${y})`} className={active ? 'demo-target' : 'demo-target is-excluded'}>
    <circle r="15" className="demo-target-halo" />
    <circle r="6" className="demo-target-dot" />
    {!active && <path d="m -3 -3 6 6 m 0 -6 -6 6" className="demo-cross" />}
  </g>;
}

function Status({ children, active = true, x = 36, width = 264 }) {
  return <g className={`demo-status ${active ? 'is-active' : ''}`}>
    <rect x={x} y="207" width={width} height="25" rx="7" />
    <circle cx={x + 13} cy="219.5" r="3" fill={active ? 'currentColor' : 'none'} stroke="currentColor" />
    <text x={x + 24} y="223.5">{children}</text>
  </g>;
}

function AlignmentScene({ t, frame }) {
  return <Scene title={t.title} description={t.description}>
    <rect x="36" y="34" width="264" height="155" rx="5" className="demo-room" />
    <path d="M 106 156 V 92 H 240" className="demo-reference-path" />
    <text x="36" y="22" className="demo-label">{t.route}</text>
    <g transform={`translate(${frame.offset} 0) rotate(${frame.angle} 66 172)`}>
      <path d="M 106 156 V 92 H 240" className="demo-trace" />
      {[ [106, 156], [106, 126], [106, 92], [148, 92], [194, 92], [240, 92] ].map(([x, y], i) => <circle key={i} cx={x} cy={y} r={i === 5 ? 6 : 3} className="demo-trace-dot" opacity={0.35 + i * 0.13} />)}
    </g>
    <path d="M 66 172 82 145 A 32 32 0 0 0 50 145 Z" className="demo-cone" />
    <rect x="60" y="168" width="12" height="9" rx="2" className="demo-radar" />
    <text x="86" y="179" className="demo-label">{t.radar}</text>
    <Status active={frame.state === 'after'}>{t[frame.state]}</Status>
  </Scene>;
}

function BoundaryScene({ t, frame }) {
  const corners = [[36, 34], [238, 34], [238, 114], [300, 114], [300, 189], [36, 189]];
  return <Scene title={t.title} description={t.description}>
    <path d="M 238 34 H 300 V 114" className="demo-corridor" />
    <path d="M 36 34 H 238 V 114 H 300 V 189 H 36 Z" className="demo-boundary" />
    {corners.map(([x, y]) => <rect key={`${x}-${y}`} x={x - 2.5} y={y - 2.5} width="5" height="5" rx="1" className="demo-handle" />)}
    <text x="56" y="61" className="demo-label">{t.room}</text>
    <text x="269" y="52" textAnchor="middle" className="demo-label">{t.hall}</text>
    <path d="M 268 74 V 164" className="demo-reference-path" />
    <Target x={frame.x} y={frame.y} active={frame.inside} />
    <Status active={frame.inside}>{frame.inside ? t.inside : t.outside}</Status>
  </Scene>;
}

function ZonesScene({ t, frame }) {
  return <Scene title={t.title} description={t.description}>
    <rect x="36" y="34" width="264" height="155" rx="5" className="demo-room" />
    <rect x="44" y="42" width="108" height="139" rx="5" className={`demo-zone ${frame.sofa ? 'is-occupied' : ''}`} />
    <rect x="180" y="42" width="112" height="139" rx="5" className={`demo-zone ${frame.desk ? 'is-occupied' : ''}`} />
    <text x="98" y="63" textAnchor="middle" className="demo-label">{t.sofa}</text>
    <text x="236" y="63" textAnchor="middle" className="demo-label">{t.desk}</text>
    <g className="demo-furniture">
      <path d="M 68 99 V 86 Q 68 80 74 80 H 122 Q 128 80 128 86 V 99 M 63 94 H 72 V 110 H 124 V 94 H 133 V 116 H 63 Z M 71 116 V 121 M 125 116 V 121 M 98 81 V 110" />
      <rect x="207" y="80" width="58" height="30" rx="3" />
      <path d="M 214 110 V 121 M 258 110 V 121 M 227 87 H 247 V 100 H 227 Z M 237 100 V 105 M 232 105 H 242" />
    </g>
    <path d="M 97 149 H 233" className="demo-reference-path" />
    <Target x={frame.x} y={frame.y} />
    <Status x={36} width={127} active={frame.sofa}>{t.sofa} · {frame.sofa ? t.occupied : t.empty}</Status>
    <Status x={173} width={127} active={frame.desk}>{t.desk} · {frame.desk ? t.occupied : t.empty}</Status>
  </Scene>;
}

export default function FeatureShowcase({ t, onGuide }) {
  const section = useRef(null);
  const player = useDemoPlayer(section);
  const frame = demoFrame(player.progress);
  const scenes = [['alignment', AlignmentScene], ['boundary', BoundaryScene], ['zones', ZonesScene]];
  return <section ref={section} id="features" className="feature-showcase scroll-mt-24 pt-14" aria-labelledby="features-title">
    {/* Preserve incoming links to the former comparison, without keeping its UI. */}
    <span id="comparison" className="scroll-mt-24" />
    <div className="feature-heading">
      <div><h2 id="features-title" className="section-title">{t.title}</h2><p className="muted mt-3 text-sm leading-7">{t.intro}</p></div>
      <div className="demo-controls">
        <button type="button" className="secondary-button" onClick={() => player.setPlaying(!player.playing)} aria-controls="feature-scenes">
          {player.playing ? <Pause size={14} aria-hidden="true" /> : <Play size={14} aria-hidden="true" />}{player.playing ? t.pause : t.play}
        </button>
        <input type="range" min="0" max="1000" step="1" value={Math.round(player.progress * 1000)} aria-label={t.progress} aria-valuetext={`${Math.round(player.progress * 100)}%`} onFocus={() => player.setPlaying(false)} onChange={(event) => player.seek(Number(event.target.value) / 1000)} />
      </div>
    </div>
    <div id="feature-scenes" className="feature-cards mt-6">
      {scenes.map(([key, Illustration], index) => <article className="feature-card" key={key}>
        <div className="feature-card-kicker"><span>0{index + 1}</span>{t[key].label}</div>
        <Illustration t={t[key]} frame={frame[key]} />
        <div className="feature-card-copy"><h3>{t[key].title}</h3><p>{t[key].body}</p></div>
      </article>)}
    </div>
    <p className="feature-disclaimer">{t.note}</p>
    <div className="feature-card-guide"><p><Monitor size={18} aria-hidden="true" />{t.cardHint}</p><button type="button" className="text-link" onClick={onGuide}>{t.cardLink}<ArrowRight size={15} aria-hidden="true" /></button></div>
  </section>;
}
