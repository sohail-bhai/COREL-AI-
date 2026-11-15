"""Read installed spacing descriptors without connecting to CorelDRAW."""
import io
import json
from pathlib import Path

import pythoncom
from win32com.client import genpy

ROOT = Path(__file__).resolve().parents[1]
TYPELIB = r'C:\Program Files\Corel\CorelDRAW Graphics Suite X7\Programs64\CorelDRAW.tlb'


def main():
    library = pythoncom.LoadTypeLib(TYPELIB)
    result = {'typelib_path': TYPELIB, 'application_connected': False, 'browser_used': False,
              'members': [], 'enums': {}, 'sources': [
        {'url': 'https://community.coreldraw.com/sdk/api/draw/17/p/structspaceproperties.characterspacing?lang=cpp',
         'version': 'X7', 'accessed': '2026-11-15', 'evidence':
         'CharacterSpacing represents a percentage of the Space character; minimum -100, maximum 2000. '
         'The value cannot exceed StructAlignProperties.MaxCharacterSpacing.'},
        {'url': 'https://product.corel.com/help/CorelDRAW/540229932/Main/EN/User-Guide/CorelDRAW-X7.pdf',
         'version': 'X7', 'printed_page': 373, 'accessed': '2026-11-15', 'evidence':
         'Values for adjusting spacing represent a percentage of the space character. '
         'The Character values range from -100 to 2000 percent. All other values range from 0 to 2000 percent. '
         'The adjacent word-spacing instructions use the Paragraph area of the Object properties docker.'},
        {'url': 'https://community.coreldraw.com/sdk/api/draw/17.4/p/structspaceproperties.wordspacing?lang=cpp',
         'version': 'X7.4 (supplementary, not proof for installed 17.0)', 'accessed': '2026-11-15', 'evidence':
         'WordSpacing represents a percentage of the Space character, from 0 to 2000, constrained by '
         'StructAlignProperties.MinWordSpacing and MaxWordSpacing.'}],
        'conclusions': [
            'Installed X7 TextRange does not expose GetSpaceProperties/SetSpaceProperties methods.',
            'Text exposes indexed SpaceProperties/SpacePropertiesInRange dispatch properties; the range structure is described as dynamic and bound.',
            'TextRange.CharSpacing/WordSpacing are Single scalar setters with no units in installed member documentation.',
            'Use Text.GetSpaceProperties(cdrAllFrames=2) and a fresh Application.CreateStructSpaceProperties '
            'with all six fields supplied to Text.SetSpaceProperties(2, structure). These Python method names '
            'are generated from the installed indexed property; they are not TextRange methods.',
            'X7 word percentage units combine installed StructSpaceProperties.WordSpacing with the X7 '
            'user-guide unit basis; X7.4 API remarks are supplementary. Native unit acceptance remains deferred.',
            'Read-only scalar/structure agreement is required, but scalar spacing setters are not used.',
            'Do not guess range start bases, silently use X7.4 as proof for X7, or apply paragraph word spacing to a partial range.']}
    seen = set()
    for index in range(library.GetTypeInfoCount()):
        info = library.GetTypeInfo(index)
        attr = info.GetTypeAttr()
        if attr.typekind == pythoncom.TKIND_COCLASS:
            info = info.GetRefTypeInfo(info.GetRefTypeOfImplType(0))
            attr = info.GetTypeAttr()
        name = info.GetDocumentation(-1)[0]
        if name in seen:
            continue
        seen.add(name)
        if name in ('IVGText', 'IVGTextRange', 'IVGStructSpaceProperties', 'IVGStructAlignProperties', 'IVGApplication'):
            for member in range(attr.cFuncs):
                descriptor = info.GetFuncDesc(member)
                names = info.GetNames(descriptor[0])
                if ('SpaceProperties' in names[0] or names[0] == 'AlignProperties'
                        or 'Spacing' in names[0] and name != 'IVGApplication'):
                    result['members'].append({'interface': name, 'names': names, 'invkind': descriptor[4],
                        'descriptor': repr(tuple(descriptor)), 'documentation': info.GetDocumentation(descriptor[0])[1]})
        if attr.typekind == pythoncom.TKIND_ENUM and name in ('cdrTextFrames', 'cdrTextIndexingType'):
            result['enums'][name] = {info.GetNames(info.GetVarDesc(i)[0])[0]: info.GetVarDesc(i)[1]
                                     for i in range(attr.cVars)}
    class Sink(io.StringIO):
        @property
        def encoding(self):
            return 'utf-8'
    sink = Sink()
    genpy.Generator(library, None, genpy.GeneratorProgress()).generate(sink)
    lines = sink.getvalue().splitlines()
    result['generated_python_bindings'] = {}
    for index, line in enumerate(lines):
        for name in ('CreateStructSpaceProperties', 'GetSpaceProperties', 'SetSpaceProperties', 'GetAlignProperties'):
            if 'def ' + name + '(' in line:
                result['generated_python_bindings'][name] = '\n'.join(lines[index:index + 8])
    result['research_limitations'] = [
        'Direct X7 Text.SpaceProperties/SpacePropertiesInRange requests returned no readable member text on 2026-11-15.',
        'The indexed call signatures and frame enum are established by installed type-library/Python binding inspection.',
        'No application connection, scalar setter trial, live alias test or visual acceptance occurred.']
    (ROOT / 'docs/x7_horizontal_spacing_evidence.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print('Retained horizontal spacing evidence:', len(result['members']), 'members;', len(result['enums']), 'enums; no application connection.')


if __name__ == '__main__':
    main()
