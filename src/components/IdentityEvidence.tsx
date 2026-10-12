import type { ClassificationResult } from '../types';
import profiles from '../../catalog/tracker_profiles.json';

export function EvidenceBadge({classification}: {classification: ClassificationResult}) {
  if (!classification.is_candidate) return null;
  return <span className={`text-[10px] rounded px-2 py-1 ${classification.lab_verified ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-900'}`}>
    {classification.lab_verified ? 'Lab verified' : classification.evidence_level === 'web_reference' ? 'Web reference · not lab verified' : 'Unverified · no lab evidence'}
  </span>;
}

export function IdentityEvidence({classification}: {classification: ClassificationResult}) {
  const evidence = classification.evidence || {};
  return <section className="text-xs border rounded-xl p-3 space-y-2 bg-slate-50">
    <EvidenceBadge classification={classification}/>
    <p>Address type: <strong>{evidence.address_type || 'unknown'}</strong></p>
    <p>Address registrant: <strong>{evidence.oui_registrant || 'Not attributed'}</strong></p>
    <p className="text-slate-500">{evidence.oui_note || 'MAC prefixes are not used when the address type is unknown.'}</p>
    <p>Advertised company IDs: <strong>{evidence.company_names?.join(', ') || 'None observed'}</strong></p>
    <p className="text-slate-500">Company IDs identify the advertised protocol namespace, not necessarily the device manufacturer.</p>
    {!!evidence.compatible_profiles?.length && <div><strong>Compatible product families — not model identification</strong>
      {evidence.compatible_profiles.map((p: {name: string}) => <p key={p.name}>{p.name}</p>)}
    </div>}
    {evidence.rule_evidence?.map((r: {rule_id: string; references: Array<{description: string; url_or_ref?: string}>}) =>
      <details key={r.rule_id}><summary className="cursor-pointer">Evidence: {r.rule_id}</summary>
        {r.references.map((s, i) => <p key={i}>{s.url_or_ref?.startsWith('https://') ? <a className="text-blue-700 underline" href={s.url_or_ref} target="_blank" rel="noreferrer">{s.description}</a> : s.description}</p>)}
      </details>)}
  </section>;
}

export function TrackerResearchCatalog() {
  return <details className="mb-3 bg-white rounded-xl border p-3 text-xs">
    <summary className="font-semibold cursor-pointer">Tracker research catalog · evidence &amp; coverage</summary>
    <p className="mt-2 text-slate-500">All entries below are web references, not lab-verified model fingerprints.</p>
    {profiles.map(p => <div key={p.name} className="mt-3 border-t pt-2">
      <strong>{p.name}</strong><p className="text-amber-800">{p.status}</p><p>{p.signature}</p>
      {p.sources.map((url, i) => <a key={url} className="text-blue-700 underline mr-3" href={url} target="_blank" rel="noreferrer">Source {i + 1}</a>)}
    </div>)}
  </details>;
}
