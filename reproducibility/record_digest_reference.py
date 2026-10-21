"""Literal Markdown report templates over independently accepted complete records."""
import math


def number(value,precision):
    if value is None:return 'n/a'
    return format(value,'.'+str(precision)+'g')


def pvalue(value):
    if value is None:return 'n/a'
    return f'{value:.2e}' if value<.0001 else f'{value:.4g}'


def compact(parameters):
    if not isinstance(parameters,dict):return str(parameters)
    parts=[]
    for key,value in parameters.items():
        text=str(value)
        if len(text)>60:text=text[:57]+'...'
        parts.append(f'{key}={text}')
    return ', '.join(parts)


def report(case):
    s=case['summary'];lines=[f"# Results — {s.get('plot','plot')} ({s.get('batch','?')})"]
    metadata=[]
    if s.get('run_id'):metadata.append(f"run `{s['run_id']}`")
    if s.get('timestamp'):metadata.append(s['timestamp'])
    if metadata:lines.append('_'+' · '.join(metadata)+'_')
    if s.get('params'):lines.extend(['',f"**Params:** `{compact(s['params'])}`"])
    records=[item for item in s.get('metrics',[]) or [] if isinstance(item,dict)]
    comparisons=[item for item in records if item.get('kind')=='group_comparison']
    correlations=[item for item in records if item.get('kind')=='correlation']
    if comparisons:
        lines.extend(['','## Group comparisons'])
        for record in comparisons:
            lines.extend([f"### {record.get('metric','metric')}",f"- {record.get('headline','')}"])
            for group in record.get('groups',[]):
                if group.get('mean') is None:lines.append(f"  - **{group['name']}**: n={group.get('n')} (no numeric values)")
                else:lines.append(f"  - **{group['name']}**: n={group.get('n')}, mean={number(group['mean'],4)} ± {number(group.get('sd',0),3)} (SD), median={number(group.get('median'),4)}")
            pairs=[item for item in record.get('pairwise',[]) if item.get('p') is not None and item['p']<.05]
            if pairs:
                text=', '.join(f"{item.get('a','?')} vs {item.get('b','?')} (p={pvalue(item['p'])} {item.get('sig','')})" for item in pairs)
                lines.append('  - significant pairs: '+text)
            for value in record.get('effect_sizes',[])[:6]:
                if not str(value).lower().startswith('effect size'):lines.append(f'  - effect size: {value}')
    if correlations:
        lines.extend(['','## Correlations'])
        for item in correlations:lines.append(f"- {item.get('headline','')}"+(f"  (n={item['n']})" if item.get('n') is not None else ''))
    others=[item for item in records if item.get('kind') not in ('group_comparison','correlation')]
    if others:
        lines.extend(['','## Other records'])
        lines.extend(f"- {item.get('headline') or item.get('kind') or 'record'}" for item in others)
    pipeline=s.get('pipeline')
    if isinstance(pipeline,dict):
        lines.extend(['','## Pipeline summary'])
        for key in ('run_label','n_pairs','n_selected','n_regressions','tests','gate','alpha'):
            if key in pipeline and pipeline[key] is not None:lines.append(f'- **{key}**: {pipeline[key]}')
        groups=pipeline.get('groups')
        if isinstance(groups,list) and groups:
            lines.append('- groups:')
            lines.extend(f"  - {group.get('group','?')}: n_rows={group.get('n_rows')}, n_selected={group.get('n_selected')}" for group in groups[:12] if isinstance(group,dict))
        selected=pipeline.get('selected_pairs')
        if isinstance(selected,list) and selected:
            lines.append(f'- top selected pairs ({min(len(selected),8)} of {len(selected)}):')
            for item in selected[:8]:
                if not isinstance(item,dict):continue
                coefficient=item.get('r') if 'r' in item else item.get('median_abs_r')
                lines.append(f"  - {item.get('y')} vs {item.get('x')}"+(f' (r≈{coefficient:.3g})' if isinstance(coefficient,(int,float)) else ''))
    if not records and not pipeline:lines.extend(['','_No structured statistics were captured for this run (the plot may not compute group tests or correlations)._'])
    return '\n'.join(lines)+'\n'
