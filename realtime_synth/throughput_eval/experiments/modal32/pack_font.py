"""Losslessly pack the v26 display ROMs to free BSRAM for the 32-partial audio state."""
import json
import re


def pack(base, out):
    renderer=(base/'panel_renderer.v').read_text(encoding='utf8')
    direct_fields=re.findall(r'direct_on=1;direct=([^;]+);',renderer)
    # Every bypass field emits a decimal digit. Keep the original digit glyph IDs.
    assert direct_fields and all(x.startswith("8'd48+") and '%10)' in x for x in direct_fields)
    font=[int(v,16) for v in (base/'ui_font.hex').read_text().split()]
    strings=[int(v,16) for v in (base/'ui_strings.hex').read_text().split()]
    digits=set(range(48,58))
    used=set(strings)|digits
    assert len(used)<=256 and len(font)==512*32 and len(strings)==4096
    available=iter(sorted(set(range(256))-digits))
    remap={g:g if g in digits else next(available) for g in sorted(used)}
    packed=[0]*4096
    for g,index in remap.items():
        for row in range(32):
            word=font[g*32+row]
            if 1<=row<=16:
                packed[index*16+(row%16)]=word
            elif word:
                raise ValueError(f'glyph {g}, row {row} would not fit')
    for g in used:
        for row in range(32):
            actual=packed[remap[g]*16+row%16] if 1<=row<=16 else 0
            assert actual==font[g*32+row]
    (out/'compact_ui_font.hex').write_text(''.join(f'{v:04x}\n' for v in packed))
    (out/'compact_ui_strings.hex').write_text(''.join(f'{remap[g]:02x}\n' for g in strings))
    rewrites={
        'reg [8:0] strings[0:4095];reg [15:0] font[0:16383];':'reg [7:0] strings[0:4095];reg [15:0] font[0:4095];',
        '"ui_strings.hex"':'"compact_ui_strings.hex"', '"ui_font.hex"':'"compact_ui_font.hex"',
        ' reg [4:0] row1;':' wire [7:0] font_glyph=direct_on1?direct1[7:0]:glyph1[7:0];\n reg [4:0] row1;',
        'font[{(direct_on1?direct1:glyph1),row1}]':'font[{font_glyph,row1[3:0]}]',
        'enable2<=enable1;':'enable2<=enable1 && row1!=0 && row1<=16;',
    }
    for a,b in rewrites.items():
        assert renderer.count(a)==1,a
        renderer=renderer.replace(a,b)
    (out/'panel_renderer.v').write_text(renderer,encoding='utf8')
    (out/'font_packing.json').write_text(json.dumps(dict(glyphs_used=len(used),
            verified_glyph_rows=32*len(used),original_words=len(font),packed_words=len(packed)),indent=2)+'\n')
