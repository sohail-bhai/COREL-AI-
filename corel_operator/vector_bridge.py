"""Native bounded curves, exact edits and independently owned shaping derivatives."""
from __future__ import annotations

from .errors import CorelBridgeError,ErrorCode
from .native_tracking import tracked_mutation
from .vector_geometry import (MAX_PATHS,MAX_SEGMENTS,MAX_NODES,normalize_paths,point,seal,
                              paths_match,paths_equivalent,path_equivalent,points_match,plan_curve_edits)
from .vector_topology import plan_curve_topology


class VectorBridgeMixin:
    def _vector_snapshot(self,document,shape,display=False):
        if shape.Type!=self.adapter.CDR_CURVE_SHAPE and (not display or shape.Type not in self.adapter.VECTOR_PRIMITIVE_TYPES):
            raise CorelBridgeError('Curve inspection requires a native curve or supported display-curve object.',ErrorCode.UNSUPPORTED_IN_PROFILE)
        try:
            curve=shape.Curve if shape.Type==self.adapter.CDR_CURVE_SHAPE else shape.DisplayCurve
            count=self._reference_count(curve.SubPaths)
            if not 1<=count<=MAX_PATHS or not 1<=self._reference_count(curve.Nodes)<=MAX_NODES or not 1<=self._reference_count(curve.Segments)<=MAX_SEGMENTS:
                raise CorelBridgeError('The native curve exceeds 64 subpaths, 1000 segments or 2000 nodes, or is empty.',ErrorCode.UNSUPPORTED_IN_PROFILE)
            paths=[]; node_types=[]; native=[]; seen_nodes=set(); seen_segments=set()
            with self._in_inches(document,strict_restore=True):
                for p in range(1,count+1):
                    subpath=self._collection_item(curve.SubPaths,p)
                    nc=self._reference_count(subpath.Nodes); sc=self._reference_count(subpath.Segments)
                    closed=subpath.Closed
                    if type(closed) is not bool or nc<1 or sc<1 or nc>MAX_NODES or sc>MAX_SEGMENTS or nc!=sc+(0 if closed else 1):
                        raise CorelBridgeError('Native curve topology is unavailable or inconsistent.',ErrorCode.COREL_COM_ERROR)
                    nodes=[self._collection_item(subpath.Nodes,i) for i in range(1,nc+1)]
                    segments=[self._collection_item(subpath.Segments,i) for i in range(1,sc+1)]
                    positions=[]; types=[]
                    for node in nodes:
                        key=self._reference_identity(node)
                        if key in seen_nodes or not self._same_com_object(node.SubPath,subpath,strict=True):
                            raise CorelBridgeError('Native node ownership is ambiguous.',ErrorCode.COREL_COM_ERROR)
                        seen_nodes.add(key); positions.append(point({'x':node.PositionX,'y':node.PositionY}))
                        code=node.Type
                        if type(code) is not int or code not in self.adapter.NODE_TYPE_CODES.values():
                            raise CorelBridgeError('Only cusp, smooth and symmetrical native node types are supported.',ErrorCode.UNSUPPORTED_IN_PROFILE)
                        types.append(code)
                    data=[]
                    for i,segment in enumerate(segments):
                        key=self._reference_identity(segment)
                        if key in seen_segments or not self._same_com_object(segment.SubPath,subpath,strict=True) or not self._same_com_object(segment.StartNode,nodes[i],strict=True) or not self._same_com_object(segment.EndNode,nodes[(i+1)%nc],strict=True):
                            raise CorelBridgeError('Native segment connectivity is ambiguous.',ErrorCode.COREL_COM_ERROR)
                        seen_segments.add(key)
                        code=segment.Type
                        if type(code) is not int or code not in self.adapter.SEGMENT_TYPE_CODES.values(): raise CorelBridgeError('Only native line/cubic segments are supported.',ErrorCode.UNSUPPORTED_IN_PROFILE)
                        entry={'type':'line' if code==0 else 'cubic','end':dict(positions[(i+1)%nc])}
                        if code==1:
                            entry['control1']=point({'x':segment.StartingControlPointX,'y':segment.StartingControlPointY})
                            entry['control2']=point({'x':segment.EndingControlPointX,'y':segment.EndingControlPointY})
                        data.append(entry)
                    paths.append({'start':positions[0],'segments':data,'closed':closed}); node_types.append(types)
                    native.append((nodes,segments))
            if len(seen_nodes)!=curve.Nodes.Count or len(seen_segments)!=curve.Segments.Count:
                raise CorelBridgeError('Native aggregate curve counts differ from subpath membership.',ErrorCode.COREL_COM_ERROR)
            transform=self._layout_snapshot(document,shape)
            return seal({'schema':'curve-geometry-v1','shape_identity':self._reference_identity(shape),
                'document_session_id':self._document_session_id(document),'paths':paths,'node_types':node_types,
                'node_count':len(seen_nodes),'segment_count':len(seen_segments),'bounds_inches':transform['bounds_inches'],
                'matrix':transform['matrix']}),native
        except CorelBridgeError: raise
        except Exception as exc: raise CorelBridgeError('Could not inspect native curve geometry safely.',ErrorCode.COREL_COM_ERROR) from exc

    def get_curve_geometry(self,object_name='',shape_index=0,object_reference=None):
        document,shape,identity=self._inspection_target(object_name,shape_index,object_reference)
        snapshot,_=self._vector_snapshot(document,shape,display=True)
        return {'object':identity,'curve':snapshot,'editable':shape.Type==self.adapter.CDR_CURVE_SHAPE,
                'representation':'native_curve' if shape.Type==self.adapter.CDR_CURVE_SHAPE else 'display_curve','verification_status':'implemented_unverified'}

    def _vector_source_signature(self,document,shape):
        transform=self._layout_snapshot(document,shape)
        transform={key:value for key,value in transform.items() if key!='native_z_order'}
        return {'identity':self._reference_identity(shape),'name':shape.Name,'type':shape.Type,
                'transform':transform,'fill':self._fill_readback(shape),'outline':self._outline_readback(shape),
                'curve':self._vector_snapshot(document,shape,display=True)[0]}

    def _vector_layer_members(self,layer):
        count=self._reference_count(layer.Shapes)
        if count>10000: raise CorelBridgeError('Vector ownership inspection exceeds 10000 root objects.',ErrorCode.UNSUPPORTED_IN_PROFILE)
        result=[]
        for i in range(1,count+1): result.append(self._reference_identity(self._collection_item(layer.Shapes,i)))
        if len(set(result))!=len(result): raise CorelBridgeError('Native root membership is ambiguous.',ErrorCode.COREL_COM_ERROR)
        return result

    def _vector_capture(self,document,page,layer,shape,state,allow_owned=False):
        try:
            key=self._reference_identity(shape)
            if key in state['baseline'] or (key in state['owned'] and not allow_owned) or not self._same_com_object(shape.Page,page,strict=True) or not self._same_com_object(shape.Layer,layer,strict=True) or self._vector_layer_members(layer).count(key)!=1:
                raise CorelBridgeError('Native vector output is not an independently owned root on the expected page/layer.',ErrorCode.COREL_COM_ERROR)
            state['owned'][key]=shape
            return shape
        except Exception:
            state['ownership_uncertain']=True; raise

    def _vector_clone(self,document,page,layer,shape,state):
        self._note_mutation(); duplicate=shape.Duplicate(0.,0.)
        duplicate=self._vector_capture(document,page,layer,duplicate,state)
        before=self._vector_source_signature(document,shape); after=self._vector_source_signature(document,duplicate)
        if before['transform']!=after['transform'] or before['fill']!=after['fill'] or before['outline']!=after['outline'] or before['type']!=after['type']:
            raise CorelBridgeError('Copied vector geometry or basic appearance differs from its input.',ErrorCode.COREL_COM_ERROR)
        if shape.Type==self.adapter.CDR_CURVE_SHAPE:
            if self._same_com_object(duplicate.Curve,shape.Curve,strict=True) or not paths_match(before['curve']['paths'],after['curve']['paths']) or before['curve']['node_types']!=after['curve']['node_types']:
                raise CorelBridgeError('Copied curves share native data or differ from the input.',ErrorCode.COREL_COM_ERROR)
        else:
            self._layout_method(duplicate,'ConvertToCurves')(); self._note_mutation()
            if duplicate.Type!=self.adapter.CDR_CURVE_SHAPE: raise CorelBridgeError('Native duplicate did not convert to an editable curve.',ErrorCode.COREL_COM_ERROR)
            converted,_=self._vector_snapshot(document,duplicate)
            if not paths_equivalent(before['curve']['paths'],converted['paths']):
                raise CorelBridgeError('Converted duplicate differs from the original display-curve geometry.',ErrorCode.COREL_COM_ERROR)
        return duplicate

    def _vector_owned_job(self,document,sources,build):
        page=document.ActivePage; layer=sources[0].Layer if sources else page.ActiveLayer
        saved_layer=page.ActiveLayer
        baseline=self._vector_layer_members(layer); signatures=[self._vector_source_signature(document,s) for s in sources]
        state={'baseline':set(baseline),'owned':{},'ownership_uncertain':False}; command_open=False
        def remove_owned(keep):
            members=set(self._vector_layer_members(layer))
            for key,shape in list(state['owned'].items()):
                if key not in keep and key in members:
                    if key in state['baseline'] or not self._same_com_object(shape.Page,page,strict=True) or not self._same_com_object(shape.Layer,layer,strict=True):
                        raise CorelBridgeError('Refusing to delete an unowned vector object.',ErrorCode.COREL_COM_ERROR)
                    self._note_mutation(); shape.Delete(); members.remove(key)
        def sources_match(): return all(self._vector_source_signature(document,s)==signature for s,signature in zip(sources,signatures))
        try:
            self._note_mutation(); document.BeginCommandGroup('AI Vector Operation'); command_open=True
            layer.Activate()
            with self._in_inches(document,strict_restore=True),self._reference_point(document,strict_restore=True):
                outputs=build(page,layer,state)
                if len(outputs)>MAX_PATHS: raise CorelBridgeError('Vector outputs exceed 64 independent curves.',ErrorCode.UNSUPPORTED_IN_PROFILE)
                keep={self._reference_identity(s) for s in outputs}
                if len(keep)!=len(outputs): raise CorelBridgeError('Native vector outputs share identities.',ErrorCode.COREL_COM_ERROR)
                remove_owned(keep)
                members=self._vector_layer_members(layer)
                if set(members)!=set(baseline)|keep or [key for key in members if key in state['baseline']]!=baseline or not sources_match():
                    raise CorelBridgeError('Native vector operation changed original membership/order or measured source state.',ErrorCode.COREL_COM_ERROR)
                objects=[]
                for output in outputs:
                    reference=self._reference_for_shape(document,output)
                    if reference is None: raise CorelBridgeError('Vector output has no complete signed identity.',ErrorCode.COREL_COM_ERROR)
                    objects.append(self.get_curve_geometry(object_reference=reference))
            document.EndCommandGroup(); command_open=False; saved_layer.Activate()
            return {'created':bool(outputs),'empty_result':not outputs,'created_count':len(outputs),'objects':objects,
                'source_preservation':{'verified':True,'scope':'root_membership_relative_order_measured_input_geometry_basic_appearance'},
                'verification_status':'implemented_unverified','warnings':['Native geometry is read back; visual appearance and production readiness remain unverified.']}
        except Exception as exc:
            rollback={'attempted':True,'verified':False}
            try:
                remove_owned(set())
                if command_open: document.EndCommandGroup(); command_open=False
                saved_layer.Activate()
                rollback['verified']=self._vector_layer_members(layer)==baseline and sources_match() and not state['ownership_uncertain']
            except Exception as cleanup: rollback['error_type']=type(cleanup).__name__
            details={'rollback':rollback,'ownership_uncertain':state['ownership_uncertain']}
            if isinstance(exc,CorelBridgeError): details.update(exc.details)
            raise CorelBridgeError('Vector operation could not complete safely. '+('Owned output was discarded and measured sources verified.' if rollback['verified'] else 'Inspect source/output state before exact-operation reconciliation.'),
                exc.code if isinstance(exc,CorelBridgeError) else ErrorCode.COREL_COM_ERROR,details) from exc

    def _vector_inputs(self,object_references,minimum,maximum):
        if type(object_references) is not list or not minimum<=len(object_references)<=maximum:
            raise CorelBridgeError(f'Supply {minimum}-{maximum} signed vector object references.',ErrorCode.INVALID_ARGUMENT)
        document=self._selector_document('',0,object_references[0]); shapes=[]; identities=set(); layer=None
        for reference in object_references:
            shape,fresh=self._resolve_object_reference(document,reference,mutation=True)
            key=self._reference_identity(shape)
            if key in identities: raise CorelBridgeError('Vector inputs must have distinct identities.',ErrorCode.INVALID_ARGUMENT)
            identities.add(key)
            if fresh['ancestor_identities'] or shape.Type not in self.adapter.VECTOR_PRIMITIVE_TYPES:
                raise CorelBridgeError('Shaping inputs must be top-level rectangle, ellipse, polygon or curve objects.',ErrorCode.UNSUPPORTED_IN_PROFILE)
            if layer is not None and not self._same_com_object(shape.Layer,layer,strict=True):
                raise CorelBridgeError('Vector shaping requires inputs on the same page/layer.',ErrorCode.INVALID_ARGUMENT)
            layer=shape.Layer; shapes.append(shape)
            self._layout_method(shape,'Duplicate')
            if shape.Type!=self.adapter.CDR_CURVE_SHAPE: self._layout_method(shape,'ConvertToCurves')
        return document,shapes

    def _vector_free_curve(self,document,paths):
        curve=self.app.CreateCurve(document)
        for path in paths:
            subpath=curve.CreateSubPath(path['start']['x'],path['start']['y'])
            segments=path['segments'][:-1] if path['closed'] and path['segments'][-1]['type']=='line' else path['segments']
            for segment in segments:
                end=segment['end']
                if segment['type']=='line': subpath.AppendLineSegment(end['x'],end['y'])
                else: subpath.AppendCurveSegment2(end['x'],end['y'],segment['control1']['x'],segment['control1']['y'],segment['control2']['x'],segment['control2']['y'])
            if path['closed']: subpath.Closed=True
        return curve

    @tracked_mutation
    def create_vector_path(self,paths,object_name=''):
        normalized=normalize_paths(paths)
        if type(object_name) is not str or len(object_name)>120 or any(ord(c)<32 for c in object_name):
            raise CorelBridgeError('object_name must be at most 120 characters without controls.',ErrorCode.INVALID_ARGUMENT)
        document=self._target_document()
        self._layout_method(self.app,'CreateCurve'); self._layout_method(document.ActivePage.ActiveLayer,'CreateCurve')
        def build(page,layer,state):
            curve=self._vector_free_curve(document,normalized)
            self._note_mutation(); shape=layer.CreateCurve(curve)
            self._vector_capture(document,page,layer,shape,state)
            self._name_shape(document,shape,object_name,'AI_Path')
            snapshot,_=self._vector_snapshot(document,shape)
            if not paths_match(normalized,snapshot['paths']): raise CorelBridgeError('Native path geometry differs from the complete request.',ErrorCode.COREL_COM_ERROR)
            return [shape]
        return self._vector_owned_job(document,[],build)

    @tracked_mutation
    def revise_curve_topology(self,object_reference,expected_fingerprint,insertions=None,deletions=None,result_name=''):
        if type(result_name) is not str or len(result_name)>120 or any(ord(c)<32 for c in result_name):
            raise CorelBridgeError('result_name must be at most 120 characters without controls.',ErrorCode.INVALID_ARGUMENT)
        document,sources=self._vector_inputs([object_reference],1,1); source=sources[0]
        before,_=self._vector_snapshot(document,source,display=True)
        if type(expected_fingerprint) is not str or expected_fingerprint!=before['fingerprint']:
            raise CorelBridgeError('Source geometry changed; inspect before revising topology.',ErrorCode.INVALID_ARGUMENT)
        planned=plan_curve_topology(before,insertions,deletions)
        self._layout_method(self.app,'CreateCurve')
        if source.Type==self.adapter.CDR_CURVE_SHAPE: self._layout_method(source.Curve,'CopyAssign')
        appearance=(self._fill_readback(source),self._outline_readback(source))
        def build(page,layer,state):
            output=self._vector_clone(document,page,layer,source,state)
            curve=self._vector_free_curve(document,planned['paths'])
            self._note_mutation(); self._layout_method(output.Curve,'CopyAssign')(curve)
            count=self._reference_count(output.Curve.Nodes)
            if count!=planned['node_count']:
                raise CorelBridgeError('Native revised node count differs from the complete topology plan.',ErrorCode.COREL_COM_ERROR)
            for i in range(1,count+1):
                self._note_mutation(); self._collection_item(output.Curve.Nodes,i).Type=self.adapter.NODE_TYPE_CODES['cusp']
            self._name_shape(document,output,result_name,'AI_CurveRevision')
            after,_=self._vector_snapshot(document,output)
            if not paths_match(planned['paths'],after['paths']) or after['segment_count']!=planned['segment_count'] or any(code!=0 for types in after['node_types'] for code in types) or appearance!=(self._fill_readback(output),self._outline_readback(output)):
                raise CorelBridgeError('Native revised geometry, node types or basic appearance differ from the complete plan.',ErrorCode.COREL_COM_ERROR)
            return [output]
        result=self._vector_owned_job(document,sources,build)
        result['source_fingerprint']=before['fingerprint']
        result['topology']={key:value for key,value in planned.items() if key!='paths'}
        result['warnings'].append('Insertion uses curve parameter t; deletion follows explicit replacement geometry. Revised nodes are cusp; complex effects and visual fidelity need manual review.')
        return result

    @tracked_mutation
    def edit_curve_geometry(self,expected_fingerprint,node_edits=None,handle_edits=None,convert_edited_nodes_to_cusp=False,
                            object_name='',shape_index=0,object_reference=None):
        document,shape,identity=self._inspection_target(object_name,shape_index,object_reference)
        reference=identity['object_reference']
        if reference is None: raise CorelBridgeError('Curve edits require complete native identity.',ErrorCode.UNSUPPORTED_IN_PROFILE)
        self._resolve_object_reference(document,reference,mutation=True)
        before,native=self._vector_snapshot(document,shape)
        if type(expected_fingerprint) is not str or expected_fingerprint!=before['fingerprint']:
            raise CorelBridgeError('Curve geometry changed or the expected fingerprint is invalid; inspect again.',ErrorCode.INVALID_ARGUMENT)
        planned=plan_curve_edits(before,node_edits,handle_edits,convert_edited_nodes_to_cusp)
        for p,n,_ in planned['moves']: self._layout_method(native[p][0][n],'SetPosition')
        for _,segments in native:
            for segment in segments:
                if segment.Type==self.adapter.SEGMENT_TYPE_CODES['cubic']:
                    self._layout_method(segment,'SetStartingControlPointPosition')
                    self._layout_method(segment,'SetEndingControlPointPosition')
        appearance=(self._fill_readback(shape),self._outline_readback(shape))
        try:
            with self._in_inches(document,strict_restore=True),self._reference_point(document,strict_restore=True):
                if convert_edited_nodes_to_cusp:
                    for p,n in planned['affected_nodes']: self._note_mutation(); native[p][0][n].Type=self.adapter.NODE_TYPE_CODES['cusp']
                for p,n,position in planned['moves']: self._note_mutation(); native[p][0][n].SetPosition(position['x'],position['y'])
                for p,path in enumerate(planned['paths']):
                    for s,segment in enumerate(path['segments']):
                        if segment['type']!='cubic': continue
                        actual=native[p][1][s]
                        for key,prefix in (('control1','Starting'),('control2','Ending')):
                            current=point({'x':getattr(actual,prefix+'ControlPointX'),'y':getattr(actual,prefix+'ControlPointY')})
                            if not points_match(current,segment[key]):
                                self._note_mutation(); getattr(actual,'Set'+prefix+'ControlPointPosition')(segment[key]['x'],segment[key]['y'])
                after,_=self._vector_snapshot(document,shape)
                if not paths_match(after['paths'],planned['paths']) or after['node_types']!=planned['node_types'] or after['node_count']!=before['node_count'] or after['segment_count']!=before['segment_count'] or appearance!=(self._fill_readback(shape),self._outline_readback(shape)):
                    raise CorelBridgeError('Complete native curve readback differs from the planned node/handle edit.',ErrorCode.COREL_COM_ERROR)
            return {'edited':True,'before_fingerprint':before['fingerprint'],'object':identity,'curve':after,
                'verification_status':'implemented_unverified','warnings':['Native curve edits have no automatic undo; uncertain partial failures require worker reconciliation.']}
        except Exception as exc:
            raise CorelBridgeError('Curve edit could not be verified. Inspect the exact target before reconciliation.',
                exc.code if isinstance(exc,CorelBridgeError) else ErrorCode.COREL_COM_ERROR,
                {'rollback':{'attempted':False,'verified':False}}) from exc

    @tracked_mutation
    def boolean_shapes(self,operation,source_reference,target_reference,result_name=''):
        if type(operation) is not str or operation not in ('weld','trim','intersect'):
            raise CorelBridgeError('operation must be weld, trim or intersect.',ErrorCode.INVALID_ARGUMENT)
        document,shapes=self._vector_inputs([source_reference,target_reference],2,2)
        if type(result_name) is not str or len(result_name)>120 or any(ord(c)<32 for c in result_name):
            raise CorelBridgeError('result_name must be at most 120 characters without controls.',ErrorCode.INVALID_ARGUMENT)
        self._layout_method(shapes[0],operation.title())
        if any(not all(path['closed'] for path in self._vector_snapshot(document,s,display=True)[0]['paths']) for s in shapes):
            raise CorelBridgeError('Boolean shaping requires closed input geometry.',ErrorCode.INVALID_ARGUMENT)
        def build(page,layer,state):
            copies=[self._vector_clone(document,page,layer,s,state) for s in shapes]
            if any(not all(path['closed'] for path in self._vector_snapshot(document,s)[0]['paths']) for s in copies):
                raise CorelBridgeError('Boolean shaping requires closed curves.',ErrorCode.INVALID_ARGUMENT)
            self._note_mutation(); result=getattr(copies[0],operation.title())(copies[1],True,True)
            if result is None:
                if operation=='weld': raise CorelBridgeError('Native weld returned no result.',ErrorCode.COREL_COM_ERROR)
                return []
            self._vector_capture(document,page,layer,result,state,allow_owned=True)
            self._name_shape(document,result,result_name,'AI_'+operation.title())
            snapshot,_=self._vector_snapshot(document,result)
            if not all(path['closed'] for path in snapshot['paths']):
                raise CorelBridgeError('Native boolean output must contain closed geometry.',ErrorCode.COREL_COM_ERROR)
            return [result]
        result=self._vector_owned_job(document,shapes,build); result['operation']=operation
        return result

    @tracked_mutation
    def combine_vector_shapes(self,object_references,result_name=''):
        document,shapes=self._vector_inputs(object_references,2,64)
        if type(result_name) is not str or len(result_name)>120 or any(ord(c)<32 for c in result_name):
            raise CorelBridgeError('result_name must be at most 120 characters without controls.',ErrorCode.INVALID_ARGUMENT)
        expected=[path for s in shapes for path in self._vector_snapshot(document,s,display=True)[0]['paths']]
        if len(expected)>MAX_PATHS or sum(len(p['segments']) for p in expected)>MAX_SEGMENTS:
            raise CorelBridgeError('Combined geometry exceeds the curve inspection budget.',ErrorCode.UNSUPPORTED_IN_PROFILE)
        self._layout_method(self.app,'CreateShapeRange')
        def build(page,layer,state):
            copies=[self._vector_clone(document,page,layer,s,state) for s in shapes]
            paths=[path for s in copies for path in self._vector_snapshot(document,s)[0]['paths']]
            if len(paths)>MAX_PATHS or sum(len(p['segments']) for p in paths)>MAX_SEGMENTS:
                raise CorelBridgeError('Combined geometry exceeds the curve inspection budget.',ErrorCode.UNSUPPORTED_IN_PROFILE)
            shape_range=self.app.CreateShapeRange()
            for shape in copies: shape_range.Add(shape)
            self._note_mutation(); result=shape_range.Combine()
            self._vector_capture(document,page,layer,result,state,allow_owned=True)
            self._name_shape(document,result,result_name,'AI_Combined')
            snapshot,_=self._vector_snapshot(document,result)
            if not paths_equivalent(paths,snapshot['paths']): raise CorelBridgeError('Native combined paths differ from the input copies.',ErrorCode.COREL_COM_ERROR)
            return [result]
        return self._vector_owned_job(document,shapes,build)

    @tracked_mutation
    def break_apart_curve(self,object_reference,result_name_prefix='AI_Subpath'):
        document,shapes=self._vector_inputs([object_reference],1,1); source=shapes[0]
        if source.Type!=self.adapter.CDR_CURVE_SHAPE: raise CorelBridgeError('Break-apart requires an inspected native curve.',ErrorCode.UNSUPPORTED_IN_PROFILE)
        if type(result_name_prefix) is not str or not result_name_prefix.strip() or len(result_name_prefix)>110 or any(ord(c)<32 for c in result_name_prefix):
            raise CorelBridgeError('result_name_prefix requires 1-110 characters without controls.',ErrorCode.INVALID_ARGUMENT)
        before,_=self._vector_snapshot(document,source)
        self._layout_method(source,'BreakApartEx')
        def build(page,layer,state):
            duplicate=self._vector_clone(document,page,layer,source,state)
            self._note_mutation(); outputs=duplicate.BreakApartEx()
            if self._reference_count(outputs)!=len(before['paths']): raise CorelBridgeError('Native break-apart count differs from source subpaths.',ErrorCode.COREL_COM_ERROR)
            shapes=[]; candidates=[]
            for i in range(1,len(before['paths'])+1):
                shape=self._collection_item(outputs,i); self._vector_capture(document,page,layer,shape,state,allow_owned=True)
                after,_=self._vector_snapshot(document,shape)
                if len(after['paths'])!=1: raise CorelBridgeError('Each native split output must contain one subpath.',ErrorCode.COREL_COM_ERROR)
                candidates.append((shape,after['paths'][0]))
            for i,path in enumerate(before['paths'],1):
                match=next((j for j,(_,candidate) in enumerate(candidates) if path_equivalent(path,candidate)),None)
                if match is None: raise CorelBridgeError('Native subpath output differs from its source geometry.',ErrorCode.COREL_COM_ERROR)
                shape,_=candidates.pop(match)
                self._name_shape(document,shape,f'{result_name_prefix}_{i:03d}','AI_Subpath')
                shapes.append(shape)
            return shapes
        return self._vector_owned_job(document,shapes,build)
