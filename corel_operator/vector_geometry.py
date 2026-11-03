"""Canonical inch-based line/cubic paths and complete curve-edit preflight."""
from __future__ import annotations
import copy
import hashlib
import json
import math

from .errors import CorelBridgeError,ErrorCode
from .typography import finite_number

MAX_PATHS=64
MAX_SEGMENTS=1000
MAX_NODES=2000
MAX_EDITS=200
POINT_TOLERANCE=.00001


def invalid(message): raise CorelBridgeError(message,ErrorCode.INVALID_ARGUMENT)


def point(value):
    if type(value) is not dict or set(value)!={'x','y'}: invalid('Points require x/y coordinates in inches.')
    return {key:finite_number(value[key],key,-10000,10000) for key in ('x','y')}


def normalize_paths(paths):
    if type(paths) is not list or not 1<=len(paths)<=MAX_PATHS: invalid('paths must contain 1-64 subpaths.')
    result=[]; total=0
    for path in paths:
        if type(path) is not dict or set(path)!={'start','segments','closed'} or type(path['closed']) is not bool:
            invalid('Each path requires start, segments and a boolean closed flag.')
        start=point(path['start']); current=start; segments=[]
        if type(path['segments']) is not list or not 1<=len(path['segments'])<=MAX_SEGMENTS: invalid('Each path needs bounded line/cubic segments.')
        for segment in path['segments']:
            if type(segment) is not dict or segment.get('type') not in ('line','cubic'): invalid('Segments must be line or cubic dictionaries.')
            fields={'type','end'} if segment['type']=='line' else {'type','end','control1','control2'}
            if set(segment)!=fields: invalid('Segment fields do not match the line/cubic contract.')
            normalized={'type':segment['type'],**{key:point(segment[key]) for key in fields-{'type'}}}
            if normalized['type']=='line' and normalized['end']==current: invalid('A line segment must have distinct endpoints.')
            segments.append(normalized); current=normalized['end']
        if path['closed'] and current!=start: segments.append({'type':'line','end':dict(start)})
        total+=len(segments)
        if total>MAX_SEGMENTS: invalid('A curve may contain at most 1000 segments including closing lines.')
        result.append({'start':start,'segments':segments,'closed':path['closed']})
    return result


def fingerprint(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def seal(value): return {**value,'fingerprint':fingerprint(value)}


def points_match(left,right): return all(abs(left[key]-right[key])<=POINT_TOLERANCE for key in ('x','y'))


def paths_match(left,right):
    if len(left)!=len(right): return False
    for before,after in zip(left,right):
        if before['closed']!=after['closed'] or len(before['segments'])!=len(after['segments']) or not points_match(before['start'],after['start']): return False
        for a,b in zip(before['segments'],after['segments']):
            if a['type']!=b['type'] or any(not points_match(a[key],b[key]) for key in a if key!='type'): return False
    return True


def path_equivalent(left,right):
    """Compare segment geometry while allowing native traversal rotation/reversal."""
    if left['closed']!=right['closed'] or len(left['segments'])!=len(right['segments']): return False
    def edges(path):
        result=[]; start=path['start']
        for segment in path['segments']:
            result.append({'start':start,**segment}); start=segment['end']
        return result
    a=edges(left); b=edges(right)
    reverse=[]
    for segment in reversed(b):
        entry={'type':segment['type'],'start':segment['end'],'end':segment['start']}
        if segment['type']=='cubic': entry.update(control1=segment['control2'],control2=segment['control1'])
        reverse.append(entry)
    for candidate in (b,reverse):
        for offset in (range(len(candidate)) if left['closed'] else (0,)):
            sequence=candidate[offset:]+candidate[:offset]
            if all(x['type']==y['type'] and all(points_match(x[k],y[k]) for k in x if k!='type') for x,y in zip(a,sequence)): return True
    return False


def paths_equivalent(left,right):
    if len(left)!=len(right): return False
    remaining=list(right)
    for path in left:
        match=next((i for i,candidate in enumerate(remaining) if path_equivalent(path,candidate)),None)
        if match is None: return False
        remaining.pop(match)
    return True


def index(value,maximum):
    if type(value) is not int or not 1<=value<=maximum: invalid('Curve edit indices are outside the inspected geometry.')
    return value-1


def node_points(path):
    return [path['start']]+[segment['end'] for segment in (path['segments'][:-1] if path['closed'] else path['segments'])]


def shifted(value,dx,dy): return point({'x':value['x']+dx,'y':value['y']+dy})


def check_constraints(paths,node_types):
    for path,types in zip(paths,node_types):
        nodes=node_points(path); segments=path['segments']
        for i,(position,code) in enumerate(zip(nodes,types)):
            if code==0 or (not path['closed'] and i in (0,len(nodes)-1)): continue
            incoming=segments[i-1]; outgoing=segments[i%len(segments)]
            previous=nodes[(i-1)%len(nodes)]
            a=incoming.get('control2',previous); b=outgoing.get('control1',outgoing['end'])
            ax,ay=a['x']-position['x'],a['y']-position['y']; bx,by=b['x']-position['x'],b['y']-position['y']
            la,lb=math.hypot(ax,ay),math.hypot(bx,by)
            if la*lb>POINT_TOLERANCE**2 and (abs(ax*by-ay*bx)>POINT_TOLERANCE*max(la,lb) or ax*bx+ay*by>POINT_TOLERANCE**2):
                invalid('Requested handles violate a smooth/symmetrical node; explicitly convert edited nodes to cusp.')
            if code==2 and incoming['type']==outgoing['type']=='cubic' and abs(la-lb)>POINT_TOLERANCE:
                invalid('Symmetrical node handles require equal lengths or explicit cusp conversion.')


def plan_curve_edits(snapshot,node_edits=None,handle_edits=None,convert_edited_nodes_to_cusp=False):
    nodes=[] if node_edits is None else node_edits; handles=[] if handle_edits is None else handle_edits
    if type(nodes) is not list or type(handles) is not list or not 1<=len(nodes)+len(handles)<=MAX_EDITS:
        invalid('Supply 1-200 bounded node/handle edits.')
    if type(convert_edited_nodes_to_cusp) is not bool: invalid('convert_edited_nodes_to_cusp must be a boolean.')
    paths=copy.deepcopy(snapshot['paths']); types=copy.deepcopy(snapshot['node_types']); seen=set(); affected=set()
    moves=[]; controls=[]
    for edit in nodes:
        if type(edit) is not dict or set(edit)-{'subpath_index','node_index','position','translate_handles'} or not {'subpath_index','node_index','position'}<=set(edit):
            invalid('Node edits require subpath_index, node_index and position; translate_handles is optional.')
        p=index(edit['subpath_index'],len(paths)); n=index(edit['node_index'],len(types[p])); position=point(edit['position'])
        if (p,n) in seen: invalid('A node cannot be moved twice in one request.')
        seen.add((p,n)); translate=edit.get('translate_handles',True)
        if type(translate) is not bool: invalid('translate_handles must be a boolean.')
        old=node_points(snapshot['paths'][p])[n]; dx=position['x']-old['x']; dy=position['y']-old['y']
        path=paths[p]; segments=path['segments']
        if n==0: path['start']=position
        if n>0 or path['closed']:
            incoming=segments[n-1]; incoming['end']=dict(position)
            if translate and incoming['type']=='cubic': incoming['control2']=shifted(incoming['control2'],dx,dy)
        if n<len(segments) and translate and segments[n]['type']=='cubic': segments[n]['control1']=shifted(segments[n]['control1'],dx,dy)
        affected.add((p,n)); moves.append((p,n,position))
    seen=set()
    for edit in handles:
        if type(edit) is not dict or set(edit)-{'subpath_index','segment_index','control1','control2'} or not {'subpath_index','segment_index'}<=set(edit) or not {'control1','control2'}&set(edit):
            invalid('Handle edits require subpath_index/segment_index and control1 and/or control2.')
        p=index(edit['subpath_index'],len(paths)); s=index(edit['segment_index'],len(paths[p]['segments']))
        if (p,s) in seen: invalid('A segment cannot have duplicate handle edit entries.')
        seen.add((p,s)); segment=paths[p]['segments'][s]
        if segment['type']!='cubic': invalid('Only cubic segments have editable control points.')
        for key in ('control1','control2'):
            if key in edit:
                segment[key]=point(edit[key]); affected.add((p,s if key=='control1' else (s+1)%len(types[p])))
        controls.append((p,s))
    if convert_edited_nodes_to_cusp:
        for p,n in affected: types[p][n]=0
    check_constraints(paths,types)
    return {'paths':paths,'node_types':types,'moves':moves,'affected_nodes':sorted(affected),'explicit_handle_segments':controls}
