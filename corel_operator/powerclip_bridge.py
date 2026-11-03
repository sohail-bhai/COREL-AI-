"""Bounded PowerClip trees and source-preserving creation/extraction workflows."""
from __future__ import annotations
import copy
import hashlib
import math

from .errors import CorelBridgeError,ErrorCode
from .native_tracking import tracked_mutation
from .typography import finite_number
from .vector_geometry import paths_match,seal

MAX_CLIP_SHAPES=1000
MAX_CLIP_DEPTH=32
MAX_CLIP_INPUTS=64


def validate_name(value,maximum=120):
    if type(value) is not str or len(value)>maximum or any(ord(c)<32 for c in value):
        raise CorelBridgeError('Output names must be bounded strings without controls.',ErrorCode.INVALID_ARGUMENT)


class PowerClipBridgeMixin:
    def _clip_children(self,shape):
        """An unreadable getter is not treated as proof that clipping is absent."""
        try:
            groups=shape.Shapes if shape.Type==self.adapter.CDR_GROUP_SHAPE else None
            clip=shape.PowerClip
            if clip is not None and not self._same_com_object(clip.Parent,shape,strict=True):
                raise CorelBridgeError('Native PowerClip parent ownership is inconsistent.',ErrorCode.COREL_COM_ERROR)
            return groups,clip
        except CorelBridgeError: raise
        except Exception as exc:
            raise CorelBridgeError('Could not inspect native group/PowerClip ownership; absence cannot be inferred.',ErrorCode.UNSUPPORTED_IN_PROFILE) from exc

    def _clip_tree(self,document,shape,properties=True,seen=None,depth=0):
        seen={} if seen is None else seen
        key=self._reference_identity(shape)
        if key in seen or len(seen)>=MAX_CLIP_SHAPES or depth>MAX_CLIP_DEPTH:
            raise CorelBridgeError('PowerClip trees exceed 1000 shapes/32 levels or contain aliases/cycles.',ErrorCode.UNSUPPORTED_IN_PROFILE)
        seen[key]=shape
        code=shape.Type; sid=shape.StaticID; name=shape.Name
        if type(code) is not int or type(sid) is not int or sid<0 or type(name) is not str:
            raise CorelBridgeError('PowerClip identity metadata is unavailable.',ErrorCode.COREL_COM_ERROR)
        groups,clip=self._clip_children(shape)
        node={'identity':key,'static_id':sid,'object_name':name[:256],'name_sha256':hashlib.sha256(name.encode('utf-8')).hexdigest(),'name_truncated':len(name)>256,
              'shape_type_code':code,'group_children':[],'clip_children':[],'contents_locked':None}
        for collection,field in ((groups,'group_children'),(None if clip is None else clip.Shapes,'clip_children')):
            if collection is None: continue
            count=self._reference_count(collection)
            if count>MAX_CLIP_SHAPES-len(seen):
                raise CorelBridgeError('PowerClip membership exceeds the 1000-shape budget.',ErrorCode.UNSUPPORTED_IN_PROFILE)
            for i in range(1,count+1):
                child=self._collection_item(collection,i)
                if not self._same_com_object(child.Page,shape.Page,strict=True) or not self._same_com_object(child.Layer,shape.Layer,strict=True):
                    raise CorelBridgeError('PowerClip descendants have inconsistent page/layer ownership.',ErrorCode.COREL_COM_ERROR)
                node[field].append(self._clip_tree(document,child,properties,seen,depth+1)[0])
        if clip is not None:
            node['contents_locked']=clip.ContentsLocked
            if type(node['contents_locked']) is not bool:
                raise CorelBridgeError('PowerClip content-lock state is unavailable.',ErrorCode.UNSUPPORTED_IN_PROFILE)
        if properties:
            transform=self._layout_snapshot(document,shape)
            transform.pop('native_z_order',None)
            node.update(transform=transform,fill=self._fill_readback(shape),outline=self._outline_readback(shape),
                        transparency=self._transparency_readback(shape),curve=None,text=None,bitmap=None,
                        supported_payload=code in (*self.adapter.VECTOR_PRIMITIVE_TYPES,self.adapter.CDR_TEXT_SHAPE,self.adapter.CDR_GROUP_SHAPE,5))
            if code in self.adapter.VECTOR_PRIMITIVE_TYPES: node['curve']=self._vector_snapshot(document,shape,display=True)[0]
            elif code==self.adapter.CDR_TEXT_SHAPE:
                text=self._text_readback(shape); body=text['text']
                if type(body) is not str:
                    raise CorelBridgeError('PowerClip text content is unreadable.',ErrorCode.UNSUPPORTED_IN_PROFILE)
                text_type=shape.Text.Type
                if type(text_type) is not int or text_type not in (0,1):
                    raise CorelBridgeError('PowerClip text type is unavailable.',ErrorCode.UNSUPPORTED_IN_PROFILE)
                frame_count=self._reference_count(shape.Text.Frames) if text_type==1 else None
                if text_type==1 and frame_count!=1:
                    raise CorelBridgeError('Linked paragraph stories require a separate source-preserving workflow.',ErrorCode.UNSUPPORTED_IN_PROFILE)
                if text['font'] is not None and (type(text['font']) is not str or len(text['font'])>256):
                    raise CorelBridgeError('PowerClip text font metadata exceeds the supported limit.',ErrorCode.UNSUPPORTED_IN_PROFILE)
                if text['size_points'] is not None and (not math.isfinite(text['size_points']) or text['size_points']<=0):
                    raise CorelBridgeError('PowerClip text size metadata is invalid.',ErrorCode.UNSUPPORTED_IN_PROFILE)
                node['text']={'content_sha256':hashlib.sha256(body.encode('utf-8')).hexdigest(),'character_count':len(body),
                              'text_type_code':text_type,'frame_count':frame_count,
                              'preview':body[:4000],'font':text['font'],'size_points':text['size_points'],'bold':text['bold']}
            elif code==5:
                try:
                    bitmap=shape.Bitmap
                    data={field:getattr(bitmap,field) for field in ('SizeWidth','SizeHeight','ResolutionX','ResolutionY')}
                    if any(type(v) is not int or v<=0 for v in data.values()): raise ValueError('Invalid bitmap metadata')
                    node['bitmap']={**data,'units':'native_bitmap_size_resolution_metadata'}
                except Exception as exc:
                    raise CorelBridgeError('PowerClip bitmap size/resolution metadata is unavailable.',ErrorCode.UNSUPPORTED_IN_PROFILE) from exc
        return node,seen

    @staticmethod
    def _clip_nodes(tree):
        yield tree
        for field in ('group_children','clip_children'):
            for child in tree[field]: yield from PowerClipBridgeMixin._clip_nodes(child)

    def get_powerclip(self,object_name='',shape_index=0,object_reference=None):
        document,shape,identity=self._inspection_target(object_name,shape_index,object_reference)
        tree,nodes=self._clip_tree(document,shape)
        groups,clip=self._clip_children(shape)
        snapshot=seal({'schema':'powerclip-tree-v1','document_session_id':self._document_session_id(document),
                       'frame':tree,'shape_count':len(nodes),'has_powerclip':clip is not None})
        return {'object':identity,'powerclip':snapshot,'verification_status':'implemented_unverified',
                'warnings':['Clipped descendants have source-bound identity metadata; extract independent copies to obtain ordinary editing references. Bitmap pixels, complex effects and rendered clipping need manual review.']}

    def _clip_baseline(self,document,layer):
        roots=self._vector_layer_members(layer); nodes={}
        if len(roots)>MAX_CLIP_SHAPES:
            raise CorelBridgeError('PowerClip ownership scope exceeds 1000 shapes.',ErrorCode.UNSUPPORTED_IN_PROFILE)
        for i in range(1,self._reference_count(layer.Shapes)+1):
            self._clip_tree(document,self._collection_item(layer.Shapes,i),properties=False,seen=nodes)
        return roots,nodes

    def _clip_capture(self,document,shape,state,existing=False):
        key=self._reference_identity(shape)
        known_non_root=False
        try:
            if key in state['baseline_ids'] or (key in state['owned'] and not existing):
                raise CorelBridgeError('PowerClip output reuses an existing identity.',ErrorCode.COREL_COM_ERROR)
            if not self._same_com_object(shape.Page,state['page'],strict=True) or not self._same_com_object(shape.Layer,state['layer'],strict=True):
                raise CorelBridgeError('PowerClip output is on an unexpected page/layer.',ErrorCode.COREL_COM_ERROR)
            if self._vector_layer_members(state['layer']).count(key)!=1:
                known_non_root=existing and key in state['owned']
                raise CorelBridgeError('Returned PowerClip output is not an independently owned layer root.',ErrorCode.COREL_COM_ERROR)
            tree,nodes=self._clip_tree(document,shape,properties=False)
            if set(nodes)&state['baseline_ids']:
                raise CorelBridgeError('PowerClip output contains original/foreign descendants.',ErrorCode.COREL_COM_ERROR)
            if not existing and set(nodes)&set(state['owned']):
                raise CorelBridgeError('PowerClip outputs share owned descendants unexpectedly.',ErrorCode.COREL_COM_ERROR)
            state['owned'].update(nodes)
        except Exception:
            if not known_non_root: state['ownership_uncertain']=True
            raise
        return shape

    def _clip_equivalent(self,left,right,scale=1.,origin=(0.,0.),destination=(0.,0.),fitted=False):
        if left['shape_type_code']!=right['shape_type_code'] or left['name_sha256']!=right['name_sha256'] or len(left['group_children'])!=len(right['group_children']) or len(left['clip_children'])!=len(right['clip_children']): return False
        a=left['transform']['bounds_inches']; b=right['transform']['bounds_inches']
        desired={'x':destination[0]+scale*(a['x']-origin[0]),'y':destination[1]+scale*(a['y']-origin[1]),'width':scale*a['width'],'height':scale*a['height']}
        if any(abs(b[k]-desired[k])>1e-5 for k in desired): return False
        if not fitted and left['transform']!=right['transform']: return False
        if left['fill']!=right['fill'] or left['transparency']!=right['transparency']: return False
        if not fitted and left['outline']!=right['outline']: return False
        if fitted and any(left['outline'][k]!=right['outline'][k] for k in ('type_code','type','present','color')): return False
        if fitted and left['outline']['present']:
            before_width=left['outline']['width_raw']; after_width=right['outline']['width_raw']
            if before_width is not None and (after_width is None or not any(math.isclose(after_width,value,rel_tol=1e-6,abs_tol=1e-8) for value in (before_width,scale*before_width))): return False
        if left['contents_locked']!=right['contents_locked']: return False
        if left['bitmap'] is not None:
            # Effective native resolution can change with fitting; raster dimensions may not.
            keys=('SizeWidth','SizeHeight') if fitted else ('SizeWidth','SizeHeight','ResolutionX','ResolutionY')
            if right['bitmap'] is None or any(left['bitmap'][k]!=right['bitmap'][k] for k in keys): return False
        if left['text'] is not None:
            if right['text'] is None: return False
            keys=('content_sha256','character_count','text_type_code','frame_count','font','bold') if fitted else tuple(left['text'])
            if any(left['text'][k]!=right['text'][k] for k in keys): return False
            if fitted and left['text']['size_points'] is not None:
                original_size=left['text']['size_points']; actual_size=right['text']['size_points']
                if actual_size is None or not any(math.isclose(actual_size,value,rel_tol=1e-6,abs_tol=1e-8) for value in (original_size,scale*original_size)): return False
        if left['curve'] is not None:
            if right['curve'] is None or left['curve']['node_types']!=right['curve']['node_types']: return False
            paths=copy.deepcopy(left['curve']['paths'])
            for path in paths:
                for point in [path['start']]+[p for segment in path['segments'] for k,p in segment.items() if k!='type']:
                    point['x']=destination[0]+scale*(point['x']-origin[0]); point['y']=destination[1]+scale*(point['y']-origin[1])
            if not paths_match(paths,right['curve']['paths']): return False
        for field in ('group_children','clip_children'):
            for a,b in zip(left[field],right[field]):
                if not self._clip_equivalent(a,b,scale,origin,destination,fitted): return False
        return True

    def _clip_clone(self,document,source,state):
        before,source_nodes=self._clip_tree(document,source)
        source_names={key:shape.Name for key,shape in source_nodes.items()}
        self._note_mutation(); output=self._layout_method(source,'Duplicate')(0.,0.)
        self._clip_capture(document,output,state)
        after,output_nodes=self._clip_tree(document,output)
        original_entries=list(self._clip_nodes(before)); copied_entries=list(self._clip_nodes(after))
        if len(original_entries)!=len(copied_entries):
            raise CorelBridgeError('Copied PowerClip topology differs from its source.',ErrorCode.COREL_COM_ERROR)
        for original,cloned in zip(original_entries,copied_entries):
            shape=output_nodes[cloned['identity']]
            if shape.Name!=source_names[original['identity']]:
                self._note_mutation(); shape.Name=source_names[original['identity']]
        after,output_nodes=self._clip_tree(document,output)
        if not self._clip_equivalent(before,after):
            raise CorelBridgeError('Independent PowerClip copy differs from the complete measured source tree.',ErrorCode.COREL_COM_ERROR)
        for original,cloned in zip(self._clip_nodes(before),self._clip_nodes(after)):
            if original['shape_type_code']==self.adapter.CDR_CURVE_SHAPE:
                curve_key=self._reference_identity(output_nodes[cloned['identity']].Curve)
                if curve_key in state['baseline_curves'] or (curve_key in state['owned_curves'] and state['owned_curves'][curve_key]!=cloned['identity']):
                    raise CorelBridgeError('Copied payload curves share original or other owned mutable geometry.',ErrorCode.COREL_COM_ERROR)
                state['owned_curves'][curve_key]=cloned['identity']
            elif original['shape_type_code']==self.adapter.CDR_TEXT_SHAPE:
                story_key=self._reference_identity(output_nodes[cloned['identity']].Text.Story)
                if story_key in state['baseline_stories'] or (story_key in state['owned_stories'] and state['owned_stories'][story_key]!=cloned['identity']):
                    raise CorelBridgeError('Copied text shares an original or other owned mutable story.',ErrorCode.COREL_COM_ERROR)
                state['owned_stories'][story_key]=cloned['identity']
        return output

    def _clip_job(self,document,sources,build):
        page=document.ActivePage; layer=sources[0].Layer; saved_layer=page.ActiveLayer
        baseline,baseline_nodes=self._clip_baseline(document,layer)
        signatures=[self._clip_tree(document,s)[0] for s in sources]
        if len(baseline_nodes)+sum(sum(1 for _ in self._clip_nodes(tree)) for tree in signatures)+1>MAX_CLIP_SHAPES:
            raise CorelBridgeError('Original plus copied trees exceed the 1000-shape ownership budget.',ErrorCode.UNSUPPORTED_IN_PROFILE)
        baseline_curves={self._reference_identity(shape.Curve) for shape in baseline_nodes.values() if shape.Type==self.adapter.CDR_CURVE_SHAPE}
        baseline_stories={self._reference_identity(shape.Text.Story) for shape in baseline_nodes.values() if shape.Type==self.adapter.CDR_TEXT_SHAPE}
        state={'page':page,'layer':layer,'baseline_ids':set(baseline_nodes),'baseline_curves':baseline_curves,
               'baseline_stories':baseline_stories,'owned':{},'owned_curves':{},'owned_stories':{},'ownership_uncertain':False}
        opened=False
        def sources_match(): return all(self._clip_tree(document,s)[0]==signature for s,signature in zip(sources,signatures))
        def discard(keep):
            roots=[self._collection_item(layer.Shapes,i) for i in range(1,self._reference_count(layer.Shapes)+1)]
            for root in roots:
                key=self._reference_identity(root)
                if key in state['baseline_ids'] or key not in state['owned'] or key in keep: continue
                _,tree_nodes=self._clip_tree(document,root,properties=False)
                if not set(tree_nodes)<=set(state['owned']) or set(tree_nodes)&state['baseline_ids']:
                    state['ownership_uncertain']=True
                    raise CorelBridgeError('Refusing to delete a PowerClip tree containing foreign objects.',ErrorCode.COREL_COM_ERROR)
                self._note_mutation(); self._layout_method(root,'Delete')()
        try:
            self._note_mutation(); document.BeginCommandGroup('AI PowerClip Operation'); opened=True
            layer.Activate()
            with self._in_inches(document,strict_restore=True),self._reference_point(document,strict_restore=True):
                outputs,extra=build(state)
                keep={self._reference_identity(shape) for shape in outputs}
                if len(keep)!=len(outputs) or not 1<=len(outputs)<=MAX_CLIP_INPUTS:
                    raise CorelBridgeError('PowerClip output count/identities are inconsistent.',ErrorCode.COREL_COM_ERROR)
                discard(keep)
                roots,actual_nodes=self._clip_baseline(document,layer)
                retained=set()
                for output in outputs:
                    if roots.count(self._reference_identity(output))!=1:
                        raise CorelBridgeError('PowerClip output is not an independent root.',ErrorCode.COREL_COM_ERROR)
                    _,nodes=self._clip_tree(document,output,properties=False); retained.update(nodes)
                if set(roots)!=set(baseline)|keep or [key for key in roots if key in baseline]!=baseline or set(actual_nodes)!=state['baseline_ids']|retained or not sources_match():
                    raise CorelBridgeError('PowerClip operation changed original membership/order or measured source state.',ErrorCode.COREL_COM_ERROR)
                objects=[]
                for output in outputs:
                    reference=self._reference_for_shape(document,output)
                    if reference is None: raise CorelBridgeError('PowerClip output lacks a complete signed editing reference.',ErrorCode.COREL_COM_ERROR)
                    objects.append(self.get_powerclip(object_reference=reference))
            document.EndCommandGroup(); opened=False; saved_layer.Activate()
            return {'created':True,'created_count':len(outputs),'objects':objects,
                    'source_preservation':{'verified':True,'scope':'root_membership_relative_order_complete_measured_source_tree_basic_appearance'},
                    'verification_status':'implemented_unverified','warnings':['Native tree/geometry is read back; bitmap pixels, complex effects and rendered clipping require consolidated/manual verification.'],**extra}
        except Exception as exc:
            rollback={'attempted':True,'verified':False}
            try:
                discard(set())
                if opened: document.EndCommandGroup(); opened=False
                saved_layer.Activate()
                roots,nodes=self._clip_baseline(document,layer)
                rollback['verified']=roots==baseline and set(nodes)==state['baseline_ids'] and sources_match() and not state['ownership_uncertain']
            except Exception as cleanup: rollback['error_type']=type(cleanup).__name__
            raise CorelBridgeError('PowerClip operation could not complete safely. '+('Owned output was discarded and measured sources verified.' if rollback['verified'] else 'Inspect exact source/output state before recovery.'),
                exc.code if isinstance(exc,CorelBridgeError) else ErrorCode.COREL_COM_ERROR,
                {'rollback':rollback,'ownership_uncertain':state['ownership_uncertain']}) from exc

    def _clip_inputs(self,references):
        if type(references) is not list or not 1<=len(references)<=MAX_CLIP_INPUTS+1:
            raise CorelBridgeError('Supply bounded signed frame/content references.',ErrorCode.INVALID_ARGUMENT)
        document=self._selector_document('',0,references[0]); sources=[]; keys=set(); layer=None
        for reference in references:
            shape,fresh=self._resolve_object_reference(document,reference,mutation=True)
            key=self._reference_identity(shape)
            if key in keys or fresh['ancestor_identities']:
                raise CorelBridgeError('PowerClip workflow inputs must be distinct exact root objects.',ErrorCode.INVALID_ARGUMENT)
            if layer is not None and not self._same_com_object(layer,shape.Layer,strict=True):
                raise CorelBridgeError('PowerClip inputs must share one page/layer.',ErrorCode.INVALID_ARGUMENT)
            layer=shape.Layer; keys.add(key); sources.append(shape)
            self._layout_method(shape,'Duplicate')
            tree,_=self._clip_tree(document,shape)
            if any(not node['supported_payload'] for node in self._clip_nodes(tree)):
                raise CorelBridgeError('PowerClip input contains unsupported native effect/shape types.',ErrorCode.UNSUPPORTED_IN_PROFILE)
        return document,sources

    def _clip_extract_owned(self,document,frame,state):
        _,clip=self._clip_children(frame)
        if clip is None or not 1<=self._reference_count(clip.Shapes)<=MAX_CLIP_INPUTS:
            raise CorelBridgeError('Extraction requires 1-64 immediate clipped content roots.',ErrorCode.UNSUPPORTED_IN_PROFILE)
        children=[self._collection_item(clip.Shapes,i) for i in range(1,self._reference_count(clip.Shapes)+1)]
        expected={self._reference_identity(s) for s in children}
        snapshots={self._reference_identity(s):self._clip_tree(document,s)[0] for s in children}
        if not expected<=set(state['owned']): raise CorelBridgeError('Extracted content is not independently owned.',ErrorCode.COREL_COM_ERROR)
        self._note_mutation(); clip.ContentsLocked=False
        self._note_mutation(); outputs=self._layout_method(clip,'ExtractShapes')()
        count=self._reference_count(outputs)
        if count!=len(children): raise CorelBridgeError('Extracted native root count differs from the complete clip.',ErrorCode.COREL_COM_ERROR)
        actual=[self._collection_item(outputs,i) for i in range(1,count+1)]
        if {self._reference_identity(s) for s in actual}!=expected:
            raise CorelBridgeError('Extraction replaced or aliased clipped content identities.',ErrorCode.COREL_COM_ERROR)
        roots=self._vector_layer_members(state['layer'])
        for output in actual:
            self._clip_capture(document,output,state,existing=True)
            if roots.count(self._reference_identity(output))!=1 or self._clip_tree(document,output)[0]!=snapshots[self._reference_identity(output)]:
                raise CorelBridgeError('Extracted content differs from its clipped native geometry/state.',ErrorCode.COREL_COM_ERROR)
        _,remaining=self._clip_children(frame)
        if remaining is not None and self._reference_count(remaining.Shapes)!=0:
            raise CorelBridgeError('Native extraction left content inside the owned frame.',ErrorCode.COREL_COM_ERROR)
        by_id={self._reference_identity(s):s for s in actual}
        return [by_id[self._reference_identity(s)] for s in children]

    @tracked_mutation
    def create_powerclip(self,frame_reference,content_references,fit_kind='none',padding_inches=0.,contents_locked=True,
                         replace_existing_contents=False,result_name=''):
        validate_name(result_name)
        if type(content_references) is not list or not 1<=len(content_references)<=MAX_CLIP_INPUTS:
            raise CorelBridgeError('Supply 1-64 content references.',ErrorCode.INVALID_ARGUMENT)
        if type(fit_kind) is not str or fit_kind not in ('none','contain','cover') or type(contents_locked) is not bool or type(replace_existing_contents) is not bool:
            raise CorelBridgeError('Choose none/contain/cover fitting and boolean content-lock/replacement controls.',ErrorCode.INVALID_ARGUMENT)
        padding=finite_number(padding_inches,'padding_inches',0,100)
        if fit_kind=='none' and padding!=0:
            raise CorelBridgeError('Padding requires contain/cover fitting.',ErrorCode.INVALID_ARGUMENT)
        document,sources=self._clip_inputs([frame_reference]+content_references); frame_source=sources[0]
        frame_tree,_=self._clip_tree(document,frame_source)
        if frame_source.Type not in self.adapter.VECTOR_PRIMITIVE_TYPES or any(not p['closed'] for p in frame_tree['curve']['paths']):
            raise CorelBridgeError('PowerClip frames require closed rectangle/ellipse/polygon/curve geometry.',ErrorCode.UNSUPPORTED_IN_PROFILE)
        if frame_tree['clip_children'] and not replace_existing_contents:
            raise CorelBridgeError('Replacing copied existing contents requires replace_existing_contents=true.',ErrorCode.INVALID_ARGUMENT)
        frame_bounds=frame_tree['transform']['bounds_inches']
        if min(frame_bounds['width'],frame_bounds['height'])<=2*padding:
            raise CorelBridgeError('Padding leaves no positive frame fitting area.',ErrorCode.INVALID_ARGUMENT)
        roots=self._vector_layer_members(frame_source.Layer)
        contents=sorted(sources[1:],key=lambda shape:roots.index(self._reference_identity(shape)))
        source_bounds=[self._layout_snapshot(document,s)['bounds_inches'] for s in contents]
        left=min(b['x'] for b in source_bounds); bottom=min(b['y'] for b in source_bounds)
        source_union={'x':left,'y':bottom,'width':max(b['x']+b['width'] for b in source_bounds)-left,
                      'height':max(b['y']+b['height'] for b in source_bounds)-bottom}
        planned_scale=1.; planned_origin=(0.,0.); planned_destination=(0.,0.)
        if fit_kind!='none':
            if min(source_union['width'],source_union['height'])<=0:
                raise CorelBridgeError('Fitting requires positive complete content bounds.',ErrorCode.INVALID_ARGUMENT)
            width,height=frame_bounds['width']-2*padding,frame_bounds['height']-2*padding
            planned_scale=(min if fit_kind=='contain' else max)(width/source_union['width'],height/source_union['height'])
            planned_origin=(left,bottom)
            planned_destination=(frame_bounds['x']+padding+(width-planned_scale*source_union['width'])/2,
                                 frame_bounds['y']+padding+(height-planned_scale*source_union['height'])/2)
            if not math.isfinite(planned_scale) or not 1e-6<=planned_scale<=1e6:
                raise CorelBridgeError('Fitting scale is outside the supported range.',ErrorCode.INVALID_ARGUMENT)
        self._layout_method(self.app,'CreateShapeRange')
        if len(contents)>1:
            probe=self.app.CreateShapeRange(); self._layout_method(probe,'Add'); self._layout_method(probe,'Group')
        for source in contents: self._layout_method(source,'AddToPowerClip')
        def build(state):
            frame=self._clip_clone(document,frame_source,state)
            _,old_clip=self._clip_children(frame)
            if old_clip is not None and self._reference_count(old_clip.Shapes): self._clip_extract_owned(document,frame,state)
            copies=[self._clip_clone(document,source,state) for source in contents]
            if len(copies)>1:
                before=[self._clip_tree(document,s)[0] for s in copies]
                shape_range=self.app.CreateShapeRange()
                for shape in copies: self._layout_method(shape_range,'Add')(shape)
                self._note_mutation(); payload=self._layout_method(shape_range,'Group')()
                self._clip_capture(document,payload,state,existing=True)
                grouped,_=self._clip_tree(document,payload)
                if [node['identity'] for node in grouped['group_children']]!=[self._reference_identity(s) for s in copies] or any(not self._clip_equivalent(a,b) for a,b in zip(before,grouped['group_children'])):
                    raise CorelBridgeError('Grouped content changed identities/order or complete measured payload geometry.',ErrorCode.COREL_COM_ERROR)
            else: payload=copies[0]
            before,payload_nodes=self._clip_tree(document,payload); bounds=before['transform']['bounds_inches']
            if any(abs(bounds[k]-source_union[k])>1e-5 for k in source_union):
                raise CorelBridgeError('Copied/grouped payload bounds differ from the complete source union.',ErrorCode.COREL_COM_ERROR)
            scale=planned_scale; origin=planned_origin; destination=planned_destination
            if fit_kind!='none':
                locks=[]
                for node in self._clip_nodes(before):
                    if node['contents_locked'] is not None:
                        native_clip=self._clip_children(payload_nodes[node['identity']])[1]
                        locks.append((native_clip,node['contents_locked']))
                        self._note_mutation(); native_clip.ContentsLocked=True
                self._note_mutation(); self._layout_method(payload,'SetSize')(scale*bounds['width'],scale*bounds['height'])
                self._note_mutation(); self._layout_method(payload,'SetPosition')(*destination)
                for native_clip,locked in locks:
                    self._note_mutation(); native_clip.ContentsLocked=locked
            positioned,_=self._clip_tree(document,payload)
            if not self._clip_equivalent(before,positioned,scale,origin,destination,fit_kind!='none'):
                raise CorelBridgeError('Fitted complete payload geometry differs from the affine placement plan.',ErrorCode.COREL_COM_ERROR)
            self._note_mutation(); self._layout_method(payload,'AddToPowerClip')(frame,self.adapter.CDR_FALSE)
            _,clip=self._clip_children(frame)
            if clip is None: raise CorelBridgeError('Native PowerClip was not created.',ErrorCode.COREL_COM_ERROR)
            self._note_mutation(); clip.ContentsLocked=contents_locked
            actual,_=self._clip_tree(document,frame)
            comparison=copy.deepcopy(actual); comparison['clip_children']=copy.deepcopy(frame_tree['clip_children']); comparison['contents_locked']=frame_tree['contents_locked']
            if not self._clip_equivalent(frame_tree,comparison) or len(actual['clip_children'])!=1 or actual['clip_children'][0]['identity']!=self._reference_identity(payload) or not self._clip_equivalent(positioned,actual['clip_children'][0]) or actual['contents_locked']!=contents_locked:
                raise CorelBridgeError('Clipping changed the frame, content geometry/identity or lock state.',ErrorCode.COREL_COM_ERROR)
            self._name_shape(document,frame,result_name,'AI_PowerClip')
            return [frame],{'fit':{'kind':fit_kind,'padding_inches':padding,'scale':scale,'planned_content_bounds_inches':positioned['transform']['bounds_inches']},
                            'content_input_count':len(contents),'contents_locked':contents_locked}
        return self._clip_job(document,sources,build)

    @tracked_mutation
    def extract_powerclip_contents(self,frame_reference,expected_fingerprint,result_name_prefix='AI_Extracted'):
        validate_name(result_name_prefix,110)
        if not result_name_prefix: raise CorelBridgeError('result_name_prefix must not be empty.',ErrorCode.INVALID_ARGUMENT)
        document,sources=self._clip_inputs([frame_reference]); source=sources[0]
        inspected=self.get_powerclip(object_reference=frame_reference)['powerclip']
        if type(expected_fingerprint) is not str or inspected['fingerprint']!=expected_fingerprint:
            raise CorelBridgeError('PowerClip content/frame state changed; inspect before extraction.',ErrorCode.INVALID_ARGUMENT)
        if not 1<=len(inspected['frame']['clip_children'])<=MAX_CLIP_INPUTS:
            raise CorelBridgeError('Extraction requires 1-64 immediate clipped content roots.',ErrorCode.INVALID_ARGUMENT)
        _,clip=self._clip_children(source); self._layout_method(clip,'ExtractShapes')
        def build(state):
            frame=self._clip_clone(document,source,state)
            outputs=self._clip_extract_owned(document,frame,state)
            for index,output in enumerate(outputs,1): self._name_shape(document,output,f'{result_name_prefix}_{index:03d}','AI_Extracted')
            return outputs,{'source_fingerprint':inspected['fingerprint'],'extracted_count':len(outputs)}
        return self._clip_job(document,sources,build)
