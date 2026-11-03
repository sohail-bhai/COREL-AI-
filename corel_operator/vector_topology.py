"""Source-indexed line/cubic splitting and explicit nonadjacent node removal."""
from __future__ import annotations
import copy

from .typography import finite_number
from .vector_geometry import (MAX_EDITS, MAX_NODES, index, invalid, node_points,
                              normalize_paths, point, points_match)


def interpolate(a, b, t):
    return point({key: (1-t)*a[key]+t*b[key] for key in ('x', 'y')})


def split_segment(start, segment, t):
    """De Casteljau subdivision; t is the original curve parameter, not arc length."""
    if segment['type']=='line':
        middle=interpolate(start, segment['end'], t)
        return {'type':'line','end':middle}, copy.deepcopy(segment)
    a=interpolate(start, segment['control1'], t)
    b=interpolate(segment['control1'], segment['control2'], t)
    c=interpolate(segment['control2'], segment['end'], t)
    d=interpolate(a, b, t); e=interpolate(b, c, t); middle=interpolate(d, e, t)
    return ({'type':'cubic','control1':a,'control2':d,'end':middle},
            {'type':'cubic','control1':e,'control2':c,'end':copy.deepcopy(segment['end'])})


def plan_curve_topology(snapshot, insertions=None, deletions=None):
    insertions=[] if insertions is None else insertions
    deletions=[] if deletions is None else deletions
    if type(insertions) is not list or type(deletions) is not list or not 1<=len(insertions)+len(deletions)<=MAX_EDITS:
        invalid('Supply 1-200 insertion/deletion entries using the inspected source indices.')
    paths=normalize_paths(snapshot['paths']); additions={}; removals={}
    for entry in insertions:
        if type(entry) is not dict or set(entry)!={'subpath_index','segment_index','t'}:
            invalid('Insertions require subpath_index, segment_index and t.')
        p=index(entry['subpath_index'],len(paths)); s=index(entry['segment_index'],len(paths[p]['segments']))
        t=finite_number(entry['t'],'t',.000001,.999999)
        times=additions.setdefault((p,s),[])
        if t in times: invalid('Duplicate insertion parameters are ambiguous.')
        times.append(t)
    for entry in deletions:
        if type(entry) is not dict or set(entry)!={'subpath_index','node_index','replacement'}:
            invalid('Deletions require subpath_index, node_index and an explicit replacement.')
        p=index(entry['subpath_index'],len(paths)); nodes=node_points(paths[p]); n=index(entry['node_index'],len(nodes))
        if (p,n) in removals: invalid('A source node cannot be deleted twice.')
        if not paths[p]['closed'] and n in (0,len(nodes)-1):
            invalid('Open endpoints cannot be removed; explicit path cropping is separate work.')
        replacement=entry['replacement']
        if type(replacement) is not dict or replacement.get('type') not in ('line','cubic'):
            invalid('A deletion must explicitly reconnect its neighbours with a line or cubic.')
        fields={'type'} if replacement['type']=='line' else {'type','control1','control2'}
        if set(replacement)!=fields: invalid('Replacement fields must match line/cubic semantics; endpoints are retained neighbours.')
        removals[p,n]={'type':replacement['type'],**{key:point(replacement[key]) for key in fields-{'type'}}}
    for (p,n) in removals:
        path=paths[p]; count=len(node_points(path))
        neighbours=((n-1)%count,(n+1)%count)
        if any((p,i) in removals for i in neighbours): invalid('Adjacent source-node deletions require a separate inspected revision.')
        if any((p,s) in additions for s in ((n-1)%len(path['segments']),n)):
            invalid('Insertions cannot target either source segment replaced by a deletion.')
    result=[]; inserted=[]; deleted=[]; mapping=[]
    for p,path in enumerate(paths):
        nodes=node_points(path); retained=[i for i in range(len(nodes)) if (p,i) not in removals]
        if len(retained)<(1 if path['closed'] else 2):
            invalid('A revision must retain a closed-path start or both open endpoints.')
        segments=[]; cursor=1; start=copy.deepcopy(nodes[retained[0]])
        mapping.append({'subpath_index':p+1,'node_index':retained[0]+1,'result_node_index':1})
        edges=retained if path['closed'] else retained[:-1]
        for edge_index,r in enumerate(edges):
            next_position=(edge_index+1)%len(retained); q=retained[next_position]
            original_next=(r+1)%len(nodes)
            if original_next!=q:
                segment={**copy.deepcopy(removals[p,original_next]),'end':copy.deepcopy(nodes[q])}
                times=[]
            else:
                segment=copy.deepcopy(path['segments'][r]); times=sorted(additions.get((p,r),[]))
            edge_start=nodes[r]; previous=0.
            for t in times:
                left,segment=split_segment(edge_start,segment,(t-previous)/(1-previous))
                if left['type']=='line' and points_match(edge_start,left['end']):
                    invalid('Insertion points are too close for the native coordinate tolerance.')
                segments.append(left); cursor+=1
                inserted.append({'subpath_index':p+1,'segment_index':r+1,'t':t,'result_node_index':cursor})
                edge_start=left['end']; previous=t
            if segment['type']=='line' and points_match(edge_start,segment['end']):
                invalid('A revision would create a collapsed line segment.')
            segments.append(segment)
            if not path['closed'] or q!=retained[0]:
                cursor+=1; mapping.append({'subpath_index':p+1,'node_index':q+1,'result_node_index':cursor})
        if path['closed']:
            minimum=3 if all(segment['type']=='line' for segment in segments) else 2
            if len(segments)<minimum:
                invalid('A closed line-only revision needs three nodes; a curved closed revision needs two.')
        result.append({'start':start,'segments':segments,'closed':path['closed']})
        deleted.extend({'subpath_index':p+1,'node_index':n+1} for n in range(len(nodes)) if (p,n) in removals)
    result=normalize_paths(result); count=sum(len(node_points(path)) for path in result)
    if count>MAX_NODES: invalid('Revised topology exceeds the 2000-node budget.')
    mapping.sort(key=lambda entry:(entry['subpath_index'],entry['node_index']))
    return {'paths':result,'node_count':count,'segment_count':sum(len(path['segments']) for path in result),
            'inserted_count':len(inserted),'deleted_count':len(deleted),'inserted_nodes':inserted,
            'deleted_nodes':deleted,'retained_node_map':mapping,'geometry_changed':bool(deletions),
            'output_node_type':'cusp'}
