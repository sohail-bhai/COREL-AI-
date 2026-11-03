"""Controlled zero-bleed PDF export with settings restoration and exclusive publication."""
from __future__ import annotations

import math
import hashlib
import os
import tempfile

from .errors import CorelBridgeError,ErrorCode
from .native_tracking import tracked_mutation
from .pdf_inspection import inspect_pdf,pdf_path,MAX_PAGES,MAX_PDF_BYTES

COLOR_MODES={'rgb':0,'cmyk':1,'native':3}
PDF_VERSIONS={'1.4':3,'1.7':8}


class PdfBridgeMixin:
    @tracked_mutation
    def export_pdf_controlled(self,path: str,color_mode: str='native',pdf_version: str='1.4',text_as_curves: bool=False,
                              require_embedded_fonts: bool=True):
        destination=pdf_path(path)
        if type(color_mode) is not str or color_mode not in COLOR_MODES or type(pdf_version) is not str or pdf_version not in PDF_VERSIONS:
            raise CorelBridgeError('Choose rgb/cmyk/native color and PDF 1.4/1.7.',ErrorCode.INVALID_ARGUMENT)
        if type(text_as_curves) is not bool or type(require_embedded_fonts) is not bool:
            raise CorelBridgeError('Text/export font options must be booleans.',ErrorCode.INVALID_ARGUMENT)
        if destination.exists(): raise CorelBridgeError('The PDF output already exists.',ErrorCode.OUTPUT_EXISTS)
        document=self._target_document()
        count=document.Pages.Count
        if type(count) is not int or not 1<=count<=MAX_PAGES:
            raise CorelBridgeError('Controlled export requires 1-500 pages.',ErrorCode.UNSUPPORTED_IN_PROFILE)
        sizes=[]
        with self._in_inches(document,strict_restore=True):
            for index in range(1,count+1):
                page=self._collection_item(document.Pages,index)
                size={'width':page.SizeWidth,'height':page.SizeHeight}
                if any(type(v) not in (int,float) or not math.isfinite(v) or not .001<=v<=200 for v in size.values()):
                    raise CorelBridgeError('Native page sizes are unavailable or exceed 200 inches.',ErrorCode.UNSUPPORTED_IN_PROFILE)
                sizes.append(size)
        # Fonts/version/range/marks/compression are explicit; ICC conversion and
        # nonzero bleed need separate evidence. Preserve native spots by default.
        requested={'PublishRange':0,'ColorMode':COLOR_MODES[color_mode],'pdfVersion':PDF_VERSIONS[pdf_version],
            'TextAsCurves':text_as_curves,'EmbedFonts':True,'EmbedBaseFonts':True,'SubsetFonts':True,
            'IncludeBleed':False,'Bleed':0,'CropMarks':False,'RegistrationMarks':False,'DensitometerScales':False,
            'FileInformation':False,'EncryptType':0,'BitmapCompression':3,'DownsampleColor':False,'DownsampleGray':False,
            'DownsampleMono':False,'UseColorProfile':False,'ConvertSpotColors':False,'MaintainOPILinks':False,
            'EmbedFile':False,'ComplexFillsAsBitmaps':False}
        requested.update(TextExportMode=0,TrueTypeToType1=False)
        try:
            settings=document.PDFSettings
            original={field:getattr(settings,field) for field in requested}
            if any(type(v) not in (int,bool) for v in original.values()):
                raise CorelBridgeError('PDF setting snapshots must contain readable native integer/boolean values.',ErrorCode.UNSUPPORTED_IN_PROFILE)
        except CorelBridgeError: raise
        except Exception as exc: raise CorelBridgeError('Required X7 PDF settings are unavailable.',ErrorCode.UNSUPPORTED_IN_PROFILE) from exc
        restored=False; temporary_removed=False; temporary=None; inspection=None; failure=None; restore_errors=[]
        try:
            destination.parent.mkdir(parents=True,exist_ok=True)
            temporary=tempfile.TemporaryDirectory(prefix='corel-pdf-',dir=destination.parent)
            staging_path=os.path.join(temporary.name,'export.pdf')
            try:
                for field,value in requested.items():
                    self._note_mutation(); setattr(settings,field,value)
                if any(getattr(settings,field)!=value for field,value in requested.items()):
                    raise CorelBridgeError('Native PDF settings did not match the requested controls.',ErrorCode.COREL_COM_ERROR)
                document.PublishToPDF(staging_path)
                inspection=inspect_pdf(staging_path,count,sizes,require_embedded_fonts)
                if not inspection['checks_passed']:
                    raise CorelBridgeError('The generated PDF failed page or embedded-font checks.',ErrorCode.COREL_COM_ERROR,
                                           {'pdf_checks':inspection['checks']})
            except Exception as exc: failure=exc
            finally:
                for field,value in original.items():
                    try:
                        setattr(settings,field,value)
                        if getattr(settings,field)!=value: restore_errors.append(field)
                    except Exception: restore_errors.append(field)
                restored=not restore_errors
            if not restored: raise CorelBridgeError('Native PDF settings could not be fully restored.',ErrorCode.COREL_COM_ERROR)
            if failure is not None: raise failure
            # Exclusive creation prevents a concurrent file from being replaced.
            created=False
            try:
                with open(staging_path,'rb') as source,open(destination,'xb') as target:
                    created=True
                    copied=0; digest=hashlib.sha256()
                    while True:
                        chunk=source.read(1024*1024)
                        if not chunk: break
                        copied+=len(chunk)
                        if copied>MAX_PDF_BYTES: raise CorelBridgeError('Staged PDF grew beyond its size limit.',ErrorCode.COREL_COM_ERROR)
                        target.write(chunk); digest.update(chunk)
                    if copied!=inspection['bytes'] or digest.hexdigest()!=inspection['source_sha256']:
                        raise CorelBridgeError('Staged PDF changed after structural inspection.',ErrorCode.COREL_COM_ERROR)
            except FileExistsError as exc:
                raise CorelBridgeError('The PDF output appeared during export; it was preserved.',ErrorCode.OUTPUT_EXISTS) from exc
            except Exception:
                if created: destination.unlink()
                raise
            temporary.cleanup(); temporary_removed=True
            inspection['path']=str(destination)
            return {'exported':True,'path':str(destination),'bytes':inspection['bytes'],
                'controls':{'color_mode':color_mode,'pdf_version':pdf_version,'text_as_curves':text_as_curves,
                    'whole_document':True,'embed_fonts':True,'bleed_inches':0,'marks_enabled':False},
                'settings_restored':True,'inspection':inspection,'verification_status':'implemented_unverified',
                'production_ready':False,'warnings':['Zero-bleed export has no ICC/PDF-X/prepress guarantee; native and manual review remain pending.']}
        except Exception as exc:
            if temporary is not None:
                try: temporary.cleanup(); temporary_removed=True
                except Exception: pass
            rollback={'attempted':self._operation_mutation_started,'verified':restored and temporary_removed,
                      'settings_restored':restored,'temporary_removed':temporary_removed}
            details={'rollback':rollback,'restore_failed_properties':restore_errors}
            if isinstance(exc,CorelBridgeError): details.update(exc.details)
            code=exc.code if isinstance(exc,CorelBridgeError) else ErrorCode.COREL_COM_ERROR
            raise CorelBridgeError('Controlled PDF export could not complete. '+('Native settings were restored.' if restored else 'Inspect PDF settings before worker reconciliation.'),code,details) from exc
