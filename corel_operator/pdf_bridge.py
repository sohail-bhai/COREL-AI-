"""Controlled PDF export with measured boxes, restoration and exclusive publication."""
from __future__ import annotations

import math
import hashlib
import os
import stat
import tempfile

from .errors import CorelBridgeError,ErrorCode
from .native_tracking import tracked_mutation
from .pdf_inspection import inspect_pdf,pdf_path,MAX_PAGES,MAX_PDF_BYTES
from .pdf_prepress import preflight_pdf
from .typography import finite_number

COLOR_MODES={'rgb':0,'cmyk':1,'native':3}
PDF_VERSIONS={'1.4':3,'1.7':8}
# Installed X7 IPDFVBASettings.Bleed documentation: "tens of micron".
BLEED_UNITS_PER_INCH=2540


def bleed_units(bleed_inches):
    finite_number(bleed_inches,'bleed_inches',0,1)
    units=round(bleed_inches*BLEED_UNITS_PER_INCH)
    if bleed_inches>0 and units==0:
        raise CorelBridgeError('Nonzero bleed must round to at least one native 10-micrometre unit.',ErrorCode.INVALID_ARGUMENT)
    return units


def remove_owned_pdf(path,identity,expected_bytes,expected_digest):
    """Never discard a replaced file or content changed after our writes."""
    if identity is None:
        return {'attempted':False,'verified':True,'reason':'no_output_created'}
    try:
        current=path.lstat()
        if not stat.S_ISREG(current.st_mode) or (current.st_dev,current.st_ino)!=identity:
            return {'attempted':False,'verified':False,'reason':'output_identity_changed'}
        with path.open('rb') as stream:
            opened=os.fstat(stream.fileno())
            if (opened.st_dev,opened.st_ino)!=identity:
                return {'attempted':False,'verified':False,'reason':'output_identity_changed'}
            raw=stream.read(MAX_PDF_BYTES+1)
        current=path.lstat()
        if not stat.S_ISREG(current.st_mode) or (current.st_dev,current.st_ino)!=identity:
            return {'attempted':False,'verified':False,'reason':'output_identity_changed'}
        if len(raw)!=expected_bytes or hashlib.sha256(raw).hexdigest()!=expected_digest:
            return {'attempted':False,'verified':False,'reason':'output_content_changed'}
        path.unlink()
        return {'attempted':True,'verified':True,'reason':'owned_output_removed'}
    except FileNotFoundError:
        return {'attempted':False,'verified':True,'reason':'output_absent'}
    except OSError:
        return {'attempted':True,'verified':False,'reason':'output_cleanup_failed'}


class PdfBridgeMixin:
    @tracked_mutation
    def export_pdf_controlled(self,path: str,color_mode: str='native',pdf_version: str='1.4',text_as_curves: bool=False,
                              require_embedded_fonts: bool=True,bleed_inches: float=0,crop_marks: bool=False,
                              registration_marks: bool=False,preserve_overprints: bool=True):
        destination=pdf_path(path)
        native_bleed=bleed_units(bleed_inches)
        if type(color_mode) is not str or color_mode not in COLOR_MODES or type(pdf_version) is not str or pdf_version not in PDF_VERSIONS:
            raise CorelBridgeError('Choose rgb/cmyk/native color and PDF 1.4/1.7.',ErrorCode.INVALID_ARGUMENT)
        if any(type(value) is not bool for value in (text_as_curves,require_embedded_fonts,crop_marks,registration_marks,preserve_overprints)):
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
        # Explicit range/fonts/marks/compression and researched bleed conversion.
        # Native/manual color, mark appearance and artwork bleed remain pending.
        requested={'PublishRange':0,'ColorMode':COLOR_MODES[color_mode],'pdfVersion':PDF_VERSIONS[pdf_version],
            'TextAsCurves':text_as_curves,'EmbedFonts':True,'EmbedBaseFonts':True,'SubsetFonts':True,
            'IncludeBleed':native_bleed>0,'Bleed':native_bleed,'CropMarks':crop_marks,'RegistrationMarks':registration_marks,
            'Overprints':preserve_overprints,'DensitometerScales':False,
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
        restored=False; temporary_removed=False; temporary=None; inspection=None; prepress=None; failure=None; restore_errors=[]
        output_identity=None; copied=0; digest=hashlib.sha256()
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
                has_production_boxes=native_bleed>0 or crop_marks or registration_marks
                inspection=inspect_pdf(staging_path,count,None if has_production_boxes else sizes,require_embedded_fonts)
                if not inspection['checks_passed']:
                    raise CorelBridgeError('The generated PDF failed page or embedded-font checks.',ErrorCode.COREL_COM_ERROR,
                                           {'pdf_checks':inspection['checks']})
                try:
                    prepress=preflight_pdf(staging_path,expected_trim_sizes=sizes if has_production_boxes else None,
                        expected_bleed_inches=native_bleed/BLEED_UNITS_PER_INCH if has_production_boxes else None,
                        require_embedded_fonts=require_embedded_fonts)
                except CorelBridgeError as exc:
                    raise CorelBridgeError('Native PDF prepress inspection failed.',ErrorCode.COREL_COM_ERROR) from exc
                if prepress['source_sha256']!=inspection['source_sha256']:
                    raise CorelBridgeError('Staged PDF changed between structure and prepress observations.',ErrorCode.COREL_COM_ERROR)
                if not prepress['checks_passed']:
                    raise CorelBridgeError('The generated PDF failed measured trim/bleed box checks.',ErrorCode.COREL_COM_ERROR,
                        {'prepress_checks':prepress['checks']})
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
            try:
                with open(staging_path,'rb') as source,open(destination,'xb') as target:
                    owned=os.fstat(target.fileno()); output_identity=(owned.st_dev,owned.st_ino)
                    while True:
                        chunk=source.read(1024*1024)
                        if not chunk: break
                        if copied+len(chunk)>MAX_PDF_BYTES: raise CorelBridgeError('Staged PDF grew beyond its size limit.',ErrorCode.COREL_COM_ERROR)
                        target.write(chunk); copied+=len(chunk); digest.update(chunk)
                    if copied!=inspection['bytes'] or digest.hexdigest()!=inspection['source_sha256']:
                        raise CorelBridgeError('Staged PDF changed after structural inspection.',ErrorCode.COREL_COM_ERROR)
            except FileExistsError as exc:
                raise CorelBridgeError('The PDF output appeared during export; it was preserved.',ErrorCode.OUTPUT_EXISTS) from exc
            temporary.cleanup(); temporary_removed=True
            final=destination.lstat()
            if not stat.S_ISREG(final.st_mode) or (final.st_dev,final.st_ino)!=output_identity:
                raise CorelBridgeError('Published PDF ownership changed before final readback.',ErrorCode.COREL_COM_ERROR)
            with destination.open('rb') as target:
                opened=os.fstat(target.fileno())
                if (opened.st_dev,opened.st_ino)!=output_identity:
                    raise CorelBridgeError('Published PDF ownership changed during final readback.',ErrorCode.COREL_COM_ERROR)
                final_bytes=target.read(MAX_PDF_BYTES+1)
            final=destination.lstat()
            if ((final.st_dev,final.st_ino)!=output_identity or len(final_bytes)!=copied
                    or hashlib.sha256(final_bytes).hexdigest()!=digest.hexdigest()):
                raise CorelBridgeError('Published PDF bytes changed before final acceptance.',ErrorCode.COREL_COM_ERROR)
            inspection['path']=str(destination)
            prepress['path']=str(destination)
            return {'exported':True,'path':str(destination),'bytes':inspection['bytes'],
                'controls':{'color_mode':color_mode,'pdf_version':pdf_version,'text_as_curves':text_as_curves,
                    'whole_document':True,'embed_fonts':True,'bleed_inches':native_bleed/BLEED_UNITS_PER_INCH,
                    'requested_bleed_inches':bleed_inches,'native_bleed_units':native_bleed,'bleed_units_per_inch':BLEED_UNITS_PER_INCH,
                    'marks_enabled':crop_marks or registration_marks,'crop_marks':crop_marks,'registration_marks':registration_marks,
                    'preserve_overprints':preserve_overprints},
                'settings_restored':True,'inspection':inspection,'prepress':prepress,'verification_status':'implemented_unverified',
                'production_ready':False,'warnings':['Bleed units use installed X7 documentation; native conversion and mark appearance await consolidated verification.',
                    'Measured boxes do not establish artwork bleed coverage, ICC/PDF-X compliance, color accuracy or printer readiness.']}
        except Exception as exc:
            if temporary is not None:
                try: temporary.cleanup(); temporary_removed=True
                except Exception: pass
            output_cleanup=remove_owned_pdf(destination,output_identity,copied,digest.hexdigest())
            rollback={'attempted':self._operation_mutation_started,'verified':restored and temporary_removed and output_cleanup['verified'],
                      'settings_restored':restored,'temporary_removed':temporary_removed,'output_cleanup':output_cleanup}
            details={'rollback':rollback,'restore_failed_properties':restore_errors}
            if isinstance(exc,CorelBridgeError): details.update(exc.details)
            code=exc.code if isinstance(exc,CorelBridgeError) else ErrorCode.COREL_COM_ERROR
            raise CorelBridgeError('Controlled PDF export could not complete. '+('Native settings were restored.' if restored else 'Inspect PDF settings before worker reconciliation.'),code,details) from exc
