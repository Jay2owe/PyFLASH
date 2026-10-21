"""One-based pair parsing shared by result selection and effect reporting."""
import re


def parse_pairs(comparisons,count,*,allow_none=False,allow_single=False,allow_self=True):
    if comparisons is None:
        if allow_none:return []
        raise ValueError('Comparisons must be a sequence of one-based pairs.')
    if isinstance(comparisons,str):
        if not allow_single:raise ValueError('Comparisons must be a sequence of one-based pairs.')
        comparisons=[comparisons]
    try:tokens=list(comparisons)
    except TypeError as error:raise ValueError('Comparisons must be a sequence of one-based pairs.') from error
    result=[]
    for token in tokens:
        if not isinstance(token,str) or re.fullmatch(r'\s*[0-9]+\s*-\s*[0-9]+\s*',token) is None:
            raise ValueError('Comparisons must be one-based pairs such as 1-2.')
        first,second=[int(part) for part in token.split('-')]
        if not(1<=first<=count and 1<=second<=count):
            raise ValueError('Comparison group numbers must be between one and the number of groups.')
        if not allow_self and first==second:raise ValueError('Effects require two different groups.')
        result.append((token,first-1,second-1))
    return result
