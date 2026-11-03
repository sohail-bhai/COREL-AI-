"""Controlled process colors with exact target and native component readback."""
from __future__ import annotations
import math

from .errors import CorelBridgeError,ErrorCode
from .native_tracking import tracked_mutation


def validate_process_color(value):
    fields={'rgb':('red','green','blue'),'cmyk':('cyan','magenta','yellow','black')}
    if type(value) is not dict or type(value.get('model')) is not str or value['model'] not in fields:
        raise CorelBridgeError('Process colors require an explicit rgb or cmyk model.',ErrorCode.INVALID_ARGUMENT)
    channels=fields[value['model']]; maximum=255 if value['model']=='rgb' else 100
    if set(value)!={'model',*channels} or any(type(value[key]) is not int or not 0<=value[key]<=maximum for key in channels):
        raise CorelBridgeError('RGB channels must be integers 0-255; CMYK channels must be integers 0-100, with exact model fields.',ErrorCode.INVALID_ARGUMENT)
    return dict(value),tuple(value[key] for key in channels)


class AppearanceBridgeMixin:
    def _process_color_geometry(self,document,shape):
        if shape.Type not in (*self.adapter.VECTOR_PRIMITIVE_TYPES,self.adapter.CDR_TEXT_SHAPE):
            raise CorelBridgeError('Process colors support individual vectors and text; group/bitmap/effect targets require separate workflows.',ErrorCode.UNSUPPORTED_IN_PROFILE)
        geometry=self._layout_snapshot(document,shape)
        geometry['name']=shape.Name; geometry['type']=shape.Type
        if shape.Type==self.adapter.CDR_TEXT_SHAPE:
            geometry['text']=self._text_readback(shape)
            if any(geometry['text'][key] is None for key in ('text','font','size_points')):
                raise CorelBridgeError('Process-color text targets require readable whole-story content/font/size.',ErrorCode.UNSUPPORTED_IN_PROFILE)
        else: geometry['curve']=self._vector_snapshot(document,shape,display=True)[0]
        return geometry

    @tracked_mutation
    def set_process_color(self,color,channel='fill',replace_non_uniform=False,
                          object_name='',shape_index=0,object_reference=None):
        requested,components=validate_process_color(color)
        if type(channel) is not str or channel not in ('fill','outline') or type(replace_non_uniform) is not bool:
            raise CorelBridgeError('channel must be fill or outline; replace_non_uniform must be boolean.',ErrorCode.INVALID_ARGUMENT)
        document,shape,identity=self._inspection_target(object_name,shape_index,object_reference)
        reference=identity['object_reference']
        if reference is None: raise CorelBridgeError('Process colors require complete native identity.',ErrorCode.UNSUPPORTED_IN_PROFILE)
        self._resolve_object_reference(document,reference,mutation=True)
        geometry=self._process_color_geometry(document,shape)
        before_fill=self._fill_readback(shape); before_outline=self._outline_readback(shape)
        if channel=='fill':
            if before_fill['type_code'] not in self.adapter.FILL_TYPE_NAMES:
                raise CorelBridgeError('Native fill type is unavailable or unsupported.',ErrorCode.UNSUPPORTED_IN_PROFILE)
            if before_fill['type_code'] not in (0,1) and not replace_non_uniform:
                raise CorelBridgeError('Replacing a non-uniform fill requires replace_non_uniform=true.',ErrorCode.INVALID_ARGUMENT)
            apply=self._layout_method(shape.Fill,'ApplyUniformFill')
        else:
            width=before_outline['width_raw']
            if before_outline['type_code']!=1 or type(width) not in (int,float) or not math.isfinite(width) or width<=0:
                raise CorelBridgeError('Outline colors require an existing readable ordinary outline; creation/width/effects are separate work.',ErrorCode.UNSUPPORTED_IN_PROFILE)
            apply=None
        method='CreateRGBColor' if requested['model']=='rgb' else 'CreateCMYKColor'
        create=self._layout_method(self.app,method)
        try:
            native_color=create(*components); prepared=self._color_readback(native_color)
        except Exception as exc:
            raise CorelBridgeError('Could not prepare a native process color.',ErrorCode.COREL_COM_ERROR) from exc
        expected={key:value for key,value in requested.items() if key!='model'}
        if not prepared or prepared['model']!=requested['model'] or prepared['value']!=expected:
            raise CorelBridgeError('Native color factory did not retain the requested process model/components.',ErrorCode.UNSUPPORTED_IN_PROFILE)
        try:
            self._note_mutation()
            if channel=='fill': apply(native_color)
            else: shape.Outline.Color=native_color
            fill=self._fill_readback(shape); outline=self._outline_readback(shape)
            actual=fill['color'] if channel=='fill' else outline['color']
            if not actual or actual['model']!=requested['model'] or actual['value']!=expected:
                raise CorelBridgeError('Native color readback differs from the requested process model/components.',ErrorCode.COREL_COM_ERROR)
            if channel=='fill':
                preserved=fill['type_code']==1 and outline==before_outline
            else:
                preserved=fill==before_fill and all(outline[key]==before_outline[key] for key in ('type_code','type','present','width_raw','width_units'))
            self._resolve_object_reference(document,reference,mutation=True)
            if not preserved or geometry!=self._process_color_geometry(document,shape):
                raise CorelBridgeError('Color assignment changed measured geometry/text or the other appearance channel.',ErrorCode.COREL_COM_ERROR)
            return {'updated':True,'object':identity,'channel':channel,'requested_color':requested,'actual_color':actual,
                    'actual_fill':fill,'actual_outline':outline,'preservation_verified':True,
                    'verification_status':'implemented_unverified',
                    'warnings':['Process components are read back; ICC conversion, separations, spot colors and visual/print correctness remain unverified. Outline width units remain unresolved.']}
        except Exception as exc:
            raise CorelBridgeError('Process color assignment could not be verified; inspect the exact target before recovery.',
                exc.code if isinstance(exc,CorelBridgeError) else ErrorCode.COREL_COM_ERROR,
                {'rollback':{'attempted':False,'verified':False}}) from exc
