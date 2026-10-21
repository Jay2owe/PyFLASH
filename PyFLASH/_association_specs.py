"""One validator for both association interfaces; preserve their return schemas."""
from collections.abc import Mapping

def normalize_association_specs(associations, *, include_label=False):
    if isinstance(associations, Mapping):
        items=list(associations.items())
    elif isinstance(associations,(list,tuple)):
        items=[(None,spec) for spec in associations]
    else:
        raise ValueError('associations must be a named mapping or an ordered list of specification mappings')
    if not items:raise ValueError('associations cannot be empty')
    output=[];used_names=set()
    for index,(name,spec) in enumerate(items):
        if not isinstance(spec,Mapping):raise ValueError(f'association {index+1} must be a mapping')
        x,y=spec.get('x'),spec.get('y')
        if x is None or y is None:raise ValueError(f'association {index+1} requires x and y')
        x,y=str(x),str(y)
        if x==y:raise ValueError(f'association {index+1} has identical x and y')
        covariates=spec.get('covariates',[])
        if covariates is None:covariates=[]
        elif isinstance(covariates,str):covariates=[covariates]
        else:
            try:covariates=list(covariates)
            except TypeError as exc:raise ValueError(f'association {index+1} covariates must be a column name or iterable of names') from exc
        covariates=[str(v) for v in covariates]
        if any(v in {x,y} for v in covariates):raise ValueError(f'association {index+1} repeats x or y as a covariate')
        if len(set(covariates))!=len(covariates):raise ValueError(f'association {index+1} repeats a covariate')
        name=None if name is None else str(name)
        if name is not None:
            if name in used_names:raise ValueError('association names must be unique')
            used_names.add(name)
        row={'name':name}
        if include_label:row['label']=name if name is not None else f'{x} vs {y}'
        row.update(x=x,y=y,covariates=covariates);output.append(row)
    return output
