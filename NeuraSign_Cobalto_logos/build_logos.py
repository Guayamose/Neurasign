#!/usr/bin/env python3
"""NeuraSign 05. Reproducible SVG masters; Python standard library only."""
import json, math
from pathlib import Path
from html import escape

ROOT = Path(__file__).resolve().parent
TYPE = json.loads((ROOT / 'wordmark_paths.json').read_text())
GEOMETRY = {
    'unit': 2, 'width': 64, 'rise': 42, 'vertical_edge': 136,
    'translation': [76, 62], 'corner_radius': 3,
    'bounds': [140, 240], 'centroid': [70, 120],
    'horizontal_gap': 12, 'clearspace': 32,
    'wordmark_ink_height': 128, 'symbol_wordmark_gap': 100,
    'slope_degrees': math.degrees(math.atan2(42, 64)),
}

def n(v):
    return f'{v:.5f}'.rstrip('0').rstrip('.')

def rounded_polygon(vertices, radius):
    """Exact circular fillets of equal radius at every convex vertex."""
    segments=[]
    for i,(x,y) in enumerate(vertices):
        px,py=vertices[i-1];qx,qy=vertices[(i+1)%len(vertices)]
        a=(px-x,py-y);b=(qx-x,qy-y)
        la=math.hypot(*a);lb=math.hypot(*b)
        a=(a[0]/la,a[1]/la);b=(b[0]/lb,b[1]/lb)
        theta=math.acos(max(-1,min(1,a[0]*b[0]+a[1]*b[1])))
        setback=radius/math.tan(theta/2)
        start=(x+a[0]*setback,y+a[1]*setback)
        end=(x+b[0]*setback,y+b[1]*setback)
        sweep=1 if (-a[0]*b[1]+a[1]*b[0])>0 else 0
        segments.append((start,end,sweep))
    out=[]
    for i,(start,end,sweep) in enumerate(segments):
        out.append(f'{"M" if i==0 else "L"}{n(start[0])} {n(start[1])}')
        out.append(f'A{n(radius)} {n(radius)} 0 0 {sweep} {n(end[0])} {n(end[1])}')
    return ' '.join(out)+' Z'

BAR = rounded_polygon([(0,42),(64,0),(64,136),(0,178)],3)
X0,Y0,X1,Y1 = TYPE['bounds']
WORD_SCALE=128/(Y1-Y0)
WORD_WIDTH=(X1-X0)*WORD_SCALE
IMAGO_WIDTH=140+100+WORD_WIDTH

def symbol(color='#101114',x=0,y=0,scale=1):
    return (f'<g transform="translate({n(x)} {n(y)}) scale({n(scale)})" fill="{color}">'
            f'<path d="{BAR}"/><path d="{BAR}" transform="translate(76 62)"/></g>')

def wordmark(color='#101114',x=0,y=0,scale=1):
    inner=''.join(f'<path d="{g["path"]}"/>' for g in TYPE['paths'])
    return (f'<g transform="translate({n(x)} {n(y)}) scale({n(scale*WORD_SCALE)}) translate({n(-X0)} {n(-Y0)})" fill="{color}">{inner}</g>')

def imago(accent='#101114',ink='#101114',x=0,y=0,scale=1):
    return f'<g transform="translate({n(x)} {n(y)}) scale({n(scale)})">'+symbol(accent)+wordmark(ink,240,56)+'</g>'

def svg(w,h,body,title,desc='',background=None):
    bg=f'<rect width="100%" height="100%" fill="{background}"/>' if background else ''
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{n(w)}" height="{n(h)}" viewBox="0 0 {n(w)} {n(h)}" role="img" aria-labelledby="title desc">'
            f'<title id="title">{escape(title)}</title><desc id="desc">{escape(desc)}</desc>{bg}{body}</svg>')

def write(path,content):
    p=ROOT/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(content)

def export_set(folder,accent,ink):
    desc='Reconstrucción geométrica del concepto 05. Dos piezas idénticas. Letras convertidas a trazados. Sin imágenes ni fuentes externas.'
    write(folder/'neurasign-isotipo.svg',svg(204,304,symbol(accent,32,32),'NeuraSign / isotipo',desc))
    write(folder/'neurasign-logotipo.svg',svg(WORD_WIDTH+64,192,wordmark(ink,32,32),'NeuraSign / logotipo',desc))
    write(folder/'neurasign-imagotipo.svg',svg(IMAGO_WIDTH+64,304,imago(accent,ink,32,32),'NeuraSign / imagotipo horizontal',desc))
    w=WORD_WIDTH+64
    write(folder/'neurasign-imagotipo-vertical.svg',svg(w,496,symbol(accent,(w-140)/2,32)+wordmark(ink,32,336),'NeuraSign / imagotipo vertical',desc))
    write(folder/'neurasign-favicon.svg',svg(256,256,symbol(accent,(256-140*.8)/2,32,.8),'NeuraSign / favicon',desc))

def text(t,x,y,size=24,color='#171A22',weight=400):
    return f'<text x="{x}" y="{y}" fill="{color}" font-family="Inter,Arial,sans-serif" font-size="{size}" font-weight="{weight}">{escape(t)}</text>'

def line(x1,y1,x2,y2,color='#B8C0CB',width=1,dash=''):
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="{width}"'+(f' stroke-dasharray="{dash}"' if dash else '')+'/>'

if __name__ == "__main__":
    export_set(Path("svg/principal"),"#2854E8","#131A2A")
    export_set(Path("svg/fondo-oscuro"),"#6C8BFF","#FFFFFF")
    export_set(Path("svg/monocromo"),"#131A2A","#131A2A")
    export_set(Path("svg/blanco"),"#FFFFFF","#FFFFFF")
