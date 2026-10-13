import React, { useId } from 'react';
import { textFor } from './catalog';

const specKeys = ['horizontalAngle', 'verticalAngle', 'rangeResolution', 'angleResolution', 'positionInterval'];

export default function RadarDetails({ radar, language, t }) {
  const titleId = useId();
  const specs = [
    [t.range, radar.range],
    ...specKeys.map((key) => [t.specs[key], radar.detectionSpecs?.[key]]),
  ];
  const sourceLabel = textFor(radar.specificationSource?.label, language);
  return <section className="soft-surface mt-5 p-4" aria-labelledby={titleId}>
    <h3 id={titleId} className="text-sm font-semibold">{t.specs.title}</h3>
    <dl className="mt-4 grid grid-cols-2 gap-x-5 gap-y-4 text-sm sm:grid-cols-3">
      {specs.map(([label, value]) => <div key={label} className="min-w-0">
        <dt className="muted text-xs leading-5">{label}</dt>
        <dd className="mt-1 leading-6">{textFor(value, language).trim() || t.specs.unknown}</dd>
      </div>)}
    </dl>
    <div className="mt-4 border-t border-slate-200 pt-3 dark:border-white/10">
      <p className="muted text-xs leading-5">{textFor(radar.specificationNote, language) || t.specs.hint}</p>
      {sourceLabel && radar.specificationSource?.url && <a className="text-link mt-2 inline-block text-xs leading-5" href={radar.specificationSource.url} target="_blank" rel="noreferrer">{sourceLabel} ↗</a>}
      <p className="muted mt-3 text-sm leading-6">{textFor(radar.limitations, language)}</p>
      <a className="text-link mt-3 inline-block" href={radar.docs} target="_blank" rel="noreferrer">{t.docs} ↗</a>
    </div>
  </section>;
}
