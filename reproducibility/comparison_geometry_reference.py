"""Independent rational moments and literal declared bracket geometry."""
from fractions import Fraction
import math,re
import mpmath as mp

COLORS={'black':[0.,0.,0.,1.],'#ff0000':[1.,0.,0.,1.],'#00ff00':[0.,1.,0.,1.],'#0000ff':[0.,0.,1.,1.]}

def same(actual,expected):
    if isinstance(expected,dict):return isinstance(actual,dict) and actual.keys()==expected.keys() and all(same(actual[k],expected[k]) for k in expected)
    if isinstance(expected,list):return isinstance(actual,list) and len(actual)==len(expected) and all(same(a,b) for a,b in zip(actual,expected))
    if isinstance(expected,bool):return type(actual) is bool and actual==expected
    if isinstance(actual,(float,int)) and isinstance(expected,(float,int)):
        return not isinstance(actual,bool) and math.isclose(actual,expected,rel_tol=1e-9,abs_tol=0.)
    return type(actual)==type(expected) and actual==expected

def real(value,minimum=None,strict=False):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):raise ValueError('Finite real required')
    if minimum is not None and (value<=minimum if strict else value<minimum):raise ValueError('Outside drawing domain')
    return float(value)

def sample(group):
    if not isinstance(group,(list,tuple)):raise ValueError('One real dimension required')
    result=[]
    for value in group:
        if isinstance(value,(list,tuple,dict,complex)):raise ValueError('One real dimension required')
        try:v=float(value)
        except (TypeError,ValueError,OverflowError):continue
        if math.isfinite(v):result.append(Fraction(v))
    return result

def pairs(tokens,count):
    if not isinstance(tokens,(list,tuple)):raise ValueError('Ordered pair sequence required')
    result=[]
    for token in tokens:
        if not isinstance(token,str) or re.fullmatch(r'\s*[0-9]+\s*-\s*[0-9]+\s*',token) is None:raise ValueError('One-based pair required')
        a,b=map(int,token.split('-'))
        if a==b or not 1<=a<=count or not 1<=b<=count:raise ValueError('Distinct existing groups required')
        result.append((a-1,b-1))
    return result

def line(xs,ys,color,lw,zorder,clip):
    return {'x':list(xs),'y':list(ys),'color':COLORS[color],'lw':float(lw),'zorder':float(zorder),'clip_on':clip}

def brackets(centers,requested,labels,p,available=None):
    base=real(p['base_height']);pad=real(p['pad_height'],0.);handles=real(p['handles'],0.)
    span=real(p['visible_y_span'],0.,True);lw=real(p.get('lw',2),0.,True);offset=real(p.get('offset',.1),0.)
    floor=base if p.get('floor') is None else real(p['floor']);star=real(p.get('star_y_offset_frac',.0022) if p.get('star_y_offset_frac') is not None else .0022)
    color=p.get('color','black')
    if color not in COLORS:raise ValueError('Invalid color')
    updated={};lines=[];texts=[];top=floor;topline=None
    for (first,second),label in zip(requested,labels):
        if available is not None and (first not in available or second not in available):continue
        left,right=sorted((centers[first],centers[second]));covered=[x for x in centers if left<=x<=right]
        prior=[x for x in covered if x in updated]
        height=max(updated[x] for x in prior) if len(prior)>=2 else base
        xleft,xright=left+offset,right-offset;mid=float((Fraction(left)+Fraction(right))/2);upper=height+handles
        lines.extend([line([xleft,xleft],[height,upper],color,lw,1,False),line([xright,xright],[height,upper],color,lw,1,False),line([xleft,xright],[upper,upper],color,lw,1,False)])
        nonsig=label in (p.get('significance_ns','ns'),'ns') or isinstance(label,(float,int))
        y=upper+span*.0385 if nonsig else upper+span*star
        texts.append({'x':mid,'y':y,'text':'' if label is None else str(label),'size':18. if nonsig else 35.,'weight':'normal' if nonsig else 'bold','color':COLORS[color],'clip_on':False})
        nextheight=height+pad+handles;updated.update({x:nextheight for x in covered})
        top=max(top,nextheight+handles);topline=upper if topline is None else max(topline,upper)
    return [top,topline],lines,texts

def report(case):
    try:
        if case.get('axes_mode')=='none':raise ValueError('Axes required')
        if case.get('kind')=='renderer':
            p=case['parameters'];centers=[real(x) for x in p['centers']]
            if len(set(centers))!=len(centers):raise ValueError('Distinct centers required')
            labels=p.get('annotations') or [];requested=pairs(p.get('comparisons') or [],len(centers))
            if labels and len(labels)!=len(requested):raise ValueError('Every bracket needs one label')
            result,lines,texts=brackets(centers,requested,labels,p)
            return {'bracket_top':result,'ylim':case['ylim'],'lines':lines,'texts':texts,'anchors':[]}
        p=case['parameters'];groups=[sample(g) for g in case['groups']];count=len(groups)
        if case.get('bar_mode')=='none' and p.get('group_positions') is None:
            return {'maximum':None,'ylim':case['ylim'],'lines':[],'texts':[],'anchors':[]}
        centers=case['positions'] if p.get('group_positions') is None else p['group_positions']
        centers=[real(x) for x in centers]
        if len(centers)!=count or len(set(centers))!=count:raise ValueError('Every group needs one distinct center')
        figure_colors=case['scatter_colors']
        if case.get('fallback'):
            mapped=[[] for _ in centers];figure_colors=['black']*count
            source_groups=groups if case.get('scatter_mode','points')=='points' else [[] for _ in groups]
            for original,group in enumerate(source_groups):
                if not group:continue
                point=Fraction(case['positions'][original])
                nearest=min(range(count),key=lambda i:abs(Fraction(centers[i])-point))
                mapped[nearest].extend(group);figure_colors[nearest]=case['scatter_colors'][original]
            groups=mapped
        width=real(p.get('errobar_width',.12),0.);lw=real(p.get('lw',2),0.,True);pad=real(p.get('pad',10),0.,True);fraction=real(p.get('handles_fraction',.3),0.)
        override=None if p.get('max_override') is None else real(p['max_override'])
        if type(p.get('draw_error_bars',True)) is not bool:raise ValueError('Drawing choice is Boolean')
        colors=p.get('group_colors')
        if colors is not None and (not isinstance(colors,(list,tuple)) or any(c not in COLORS for c in colors)):raise ValueError('Color sequence required')
        labels=p.get('annotations') or [];tokens=p.get('comparisons')
        if tokens is None:tokens=[f'{a+1}-{a+gap+1}' for gap in range(1,count) for a in range(count-gap)] if labels else []
        requested=pairs(tokens,count)
        if labels and len(labels)!=len(requested):raise ValueError('Every requested bracket needs one label')
        bottom,top=map(float,case['ylim']);lines=[];texts=[];patches=[]
        active={i:g for i,g in enumerate(groups) if g}
        if not active:return {'maximum':None,'ylim':[bottom,top],'lines':lines,'texts':texts,'anchors':patches}
        means={};sems={}
        with mp.workdps(80):
            for i,g in active.items():
                mean=sum(g)/len(g);variance=sum((v-mean)**2 for v in g)/((len(g)-1)*len(g)) if len(g)>1 else Fraction(0)
                means[i]=float(mean);sems[i]=float(mp.sqrt(mp.mpf(variance.numerator)/variance.denominator))
        upper={i:means[i]+sems[i] for i in active};outward={i:means[i]+sems[i] if means[i]>=0 else means[i]-sems[i] for i in active}
        maximum=max(max(float(v) for g in active.values() for v in g),max(upper.values()))
        if override is not None:maximum=max(maximum,override)
        if not all(math.isfinite(v) for v in [*means.values(),*sems.values(),*upper.values(),*outward.values(),maximum]):raise ValueError('Drawing extent is unrepresentable')
        required=max(upper.values())*1.03
        if top<required:top=required
        if min(outward.values())<bottom:bottom=min(outward.values())*1.03
        span=top-bottom
        if not math.isfinite(span) or span<=0:span=max(abs(top),abs(bottom),1.)
        if p.get('draw_error_bars',True):
            for i in active:
                color=colors[i] if colors is not None and i<len(colors) else figure_colors[i] if case.get('fallback') else 'black'
                lines.extend([line([centers[i],centers[i]],[means[i],outward[i]],color,2.5,2.5,True),line([centers[i]-width,centers[i]+width],[outward[i],outward[i]],color,2.5,2.6,True)])
        bp={'base_height':top+span/pad,'pad_height':span/pad,'handles':span/pad*fraction,'visible_y_span':span,'lw':lw,'floor':maximum}
        result,bracketlines,texts=brackets(centers,requested,labels,bp,set(active));lines.extend(bracketlines)
        if result[1] is not None:
            patches.append({'x':centers[0],'y':result[1]+span*.07,'width':max(abs(case['xlim'][1]-case['xlim'][0]),1.)*1e-9,'height':span*1e-9,'gid':'pyflash-comparison-height-anchor'})
        return {'maximum':maximum,'ylim':[bottom,top],'lines':lines,'texts':texts,'anchors':patches}
    except (ValueError,TypeError,OverflowError):return {'error':'ValueError','axes_unchanged':True}
