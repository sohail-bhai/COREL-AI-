"""Native transparency inspection and controlled uniform application/removal."""
from __future__ import annotations

from .errors import CorelBridgeError,ErrorCode
from .native_tracking import tracked_mutation


def native_integer(owner,name):
    try:
        value=getattr(owner,name)
        return value if type(value) is int else None
    except Exception: return None


class TransparencyBridgeMixin:
    def _transparency_readback(self,shape):
        try: native=shape.Transparency
        except Exception: native=None
        code=native_integer(native,'Type')
        names=self.adapter.TRANSPARENCY_TYPE_NAMES
        percent=native_integer(native,'Uniform') if code==1 else None
        percent=percent if percent is not None and 0<=percent<=100 else None
        applied=native_integer(native,'AppliedTo') if code not in (None,0) else None
        merge=native_integer(native,'MergeMode') if code not in (None,0) else None
        return {'available':native is not None,'type_code':code,'type':names.get(code,'unknown'),
                'uniform_percent':percent,'applied_to_code':applied,
                'applied_to':{value:key for key,value in self.adapter.TRANSPARENCY_APPLIED_TO.items()}.get(applied,'unknown'),
                'merge_mode_code':merge,'merge_mode':'normal' if merge==0 else ('none' if code==0 else 'other_or_unavailable')}

    def get_transparency(self,object_name='',shape_index=0,object_reference=None):
        _,shape,identity=self._inspection_target(object_name,shape_index,object_reference)
        value=self._transparency_readback(shape)
        return {'object':identity,'transparency':value,'verification_status':'implemented_unverified',
                'warnings':['Non-uniform transparency details and rendered appearance are outside this inspection.']}

    def _transparency_geometry(self,document,shape):
        if shape.Type==5:
            return {'name':shape.Name,'type':shape.Type,'transform':self._layout_snapshot(document,shape)}
        return self._process_color_geometry(document,shape)

    @tracked_mutation
    def set_uniform_transparency(self,percent,applied_to='fill',replace_existing=False,
                                 object_name='',shape_index=0,object_reference=None):
        if type(percent) is not int or not 0<=percent<=100:
            raise CorelBridgeError('Transparency percent must be an integer 0-100; 0 removes the effect.',ErrorCode.INVALID_ARGUMENT)
        if type(applied_to) is not str or applied_to not in self.adapter.TRANSPARENCY_APPLIED_TO or type(replace_existing) is not bool:
            raise CorelBridgeError('applied_to must be fill, outline or both; replace_existing must be boolean.',ErrorCode.INVALID_ARGUMENT)
        document,shape,identity=self._inspection_target(object_name,shape_index,object_reference)
        reference=identity['object_reference']
        if reference is None: raise CorelBridgeError('Transparency edits require complete native identity.',ErrorCode.UNSUPPORTED_IN_PROFILE)
        self._resolve_object_reference(document,reference,mutation=True)
        before=self._transparency_readback(shape)
        if not before['available'] or before['type_code'] not in self.adapter.TRANSPARENCY_TYPE_NAMES:
            raise CorelBridgeError('Native transparency state is unavailable or unsupported.',ErrorCode.UNSUPPORTED_IN_PROFILE)
        if before['type_code'] not in (0,1) and not replace_existing:
            raise CorelBridgeError('Replacing non-uniform transparency requires replace_existing=true.',ErrorCode.INVALID_ARGUMENT)
        geometry=self._transparency_geometry(document,shape)
        appearance=(self._fill_readback(shape),self._outline_readback(shape))
        native=shape.Transparency
        method=self._layout_method(native,'ApplyNoTransparency' if percent==0 else 'ApplyUniformTransparency')
        try:
            self._note_mutation()
            if percent==0: method()
            else:
                method(percent)
                self._note_mutation(); native.AppliedTo=self.adapter.TRANSPARENCY_APPLIED_TO[applied_to]
                self._note_mutation(); native.MergeMode=self.adapter.CDR_MERGE_NORMAL
            actual=self._transparency_readback(shape)
            valid=actual['available'] and actual['type_code']==(0 if percent==0 else 1)
            if percent:
                valid=valid and actual['uniform_percent']==percent and actual['applied_to']==applied_to and actual['merge_mode_code']==self.adapter.CDR_MERGE_NORMAL
            self._resolve_object_reference(document,reference,mutation=True)
            if not valid or geometry!=self._transparency_geometry(document,shape) or appearance!=(self._fill_readback(shape),self._outline_readback(shape)):
                raise CorelBridgeError('Native transparency or measured geometry/base appearance differs from the request.',ErrorCode.COREL_COM_ERROR)
            return {'updated':True,'removed':percent==0,'object':identity,'before_transparency':before,'transparency':actual,
                    'preservation_verified':True,'verification_status':'implemented_unverified',
                    'warnings':['Native transparency is read back; rendered blend behavior, bitmap pixel preservation and printed output require the consolidated/manual campaign.']}
        except Exception as exc:
            raise CorelBridgeError('Transparency edit could not be verified; inspect the exact target before recovery.',
                exc.code if isinstance(exc,CorelBridgeError) else ErrorCode.COREL_COM_ERROR,
                {'rollback':{'attempted':False,'verified':False}}) from exc
