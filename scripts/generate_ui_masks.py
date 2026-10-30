"""Development-only asset generator: python scripts/generate_ui_masks.py.

Requires Pillow only when regenerating masks. The application uses the generated
alpha masks through the standard library, with no Pillow or SVG runtime.
"""
import base64
import math
import zlib
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

SUPERSAMPLE = 8
RESAMPLE = getattr(Image, "Resampling", Image).LANCZOS


def icon_mask(kind, size):
    image = Image.new("L", (size * SUPERSAMPLE, size * SUPERSAMPLE))
    draw = ImageDraw.Draw(image)
    unit = size * SUPERSAMPLE / 24

    def points(values):
        return [(round(x * unit), round(y * unit)) for x, y in values]

    def line(values, width=1.8):
        coordinates = points(values)
        stroke = max(1, round(width * unit))
        draw.line(coordinates, fill=255, width=stroke, joint="curve")
        radius = stroke / 2
        for x, y in coordinates:
            draw.ellipse((x-radius, y-radius, x+radius-1, y+radius-1), fill=255)

    def polygon(values):
        draw.polygon(points(values), fill=255)

    def ellipse(box, fill=255, outline=None, width=1.8):
        coordinates = tuple(round(value * unit) for value in box)
        draw.ellipse(coordinates, fill=fill, outline=outline, width=max(1, round(width*unit)))

    if kind == "file":
        line([(6,3),(13,3),(18,8),(18,21),(6,21),(6,3)])
        line([(13,3),(13,8),(18,8)])
    elif kind == "search":
        ellipse((3,3,16,16), fill=None, outline=255)
        line([(14.5,14.5),(21,21)])
    elif kind == "refresh":
        # One true circular arc, duplicated by 180 degrees for exact symmetry.
        # Arrowheads follow the circle tangent, with a broader inner wing so
        # they remain recognizable at the button's native display size.
        center = (size*SUPERSAMPLE-1)/2
        radius = 8*unit
        stroke = max(1, round(2.3*unit))
        outer = radius+stroke/2
        angle = -45
        draw.arc((center-outer,center-outer,center+outer,center+outer),
                 angle-145, angle-12, fill=255, width=stroke)
        radians = math.radians(angle)
        nx,ny = math.cos(radians),math.sin(radians)
        tx,ty = -ny,nx
        tip = (center+radius*nx,center+radius*ny)
        back = (tip[0]-tx*3*unit,tip[1]-ty*3*unit)
        draw.polygon([tip,(back[0]+nx*2.1*unit,back[1]+ny*2.1*unit),
                      (back[0]-nx*3.5*unit,back[1]-ny*3.5*unit)], fill=255)
        start = math.radians(angle-145)
        x,y = center+radius*math.cos(start),center+radius*math.sin(start)
        draw.ellipse((x-stroke/2,y-stroke/2,x+stroke/2-1,y+stroke/2-1),fill=255)
        image = ImageChops.lighter(image, image.transpose(getattr(Image,"Transpose",Image).ROTATE_180))
        # Area coverage avoids the extra faint halos of a Lanczos filter on
        # this small, high-contrast circular symbol.
        return image.resize((size,size), getattr(Image,"Resampling",Image).BOX).tobytes()
    elif kind == "folder":
        polygon([(2,5),(9,5),(12,8),(22,8),(21,20),(2,20)])
    elif kind == "trash":
        line([(6,7),(7,21),(17,21),(18,7)])
        line([(4,6),(20,6)])
        line([(9,6),(9,3),(15,3),(15,6)])
    elif kind == "copy":
        line([(7,8),(3,8),(3,21),(16,21),(16,17)])
        line([(8,3),(21,3),(21,16),(8,16),(8,3)])
    elif kind == "chevron":
        line([(5,9),(12,16),(19,9)], width=2)
    elif kind == "close":
        line([(6,6),(18,18)])
        line([(18,6),(6,18)])
    elif kind == "plus":
        line([(5,12),(19,12)])
        line([(12,5),(12,19)])
    elif kind == "check":
        line([(5,12),(10,17),(20,6)], width=2.2)
    elif kind == "play":
        polygon([(7,4),(21,12),(7,20)])
    elif kind == "stop":
        polygon([(5,5),(19,5),(19,19),(5,19)])
    elif kind == "exe":
        # A parcel with a lid and two visible sides, readable at button size.
        line([(12,2.5),(21,7),(21,17),(12,21.5),(3,17),(3,7),(12,2.5)], width=2)
        line([(3,7),(12,11.5),(21,7)], width=2)
        line([(12,11.5),(12,21.5)], width=2)
    elif kind == "dot":
        ellipse((2,2,22,22))
    elif kind == "python_ring":
        ellipse((2,2,22,22))
        ellipse((5,5,19,19), fill=0)
    elif kind == "python_core":
        ellipse((7.5,7.5,16.5,16.5))
    elif kind == "box_top":
        polygon([(12,2),(22,7),(12,12),(2,7)])
    elif kind == "box_left":
        polygon([(2,8.5),(11,13),(11,23),(2,18.5)])
    elif kind == "box_right":
        polygon([(13,13),(22,8.5),(22,18.5),(13,23)])
    elif kind == "image":
        line([(3,4),(21,4),(21,20),(3,20),(3,4)])
        ellipse((15,7,18,10))
        line([(4,18),(9,12),(13,16),(16,13),(20,18)], width=1.4)
    elif kind == "gear":
        polygon([(12+10*math.cos(i*math.pi/16), 12+10*math.sin(i*math.pi/16))
                 if i % 4 in (0,1) else
                 (12+8*math.cos(i*math.pi/16),12+8*math.sin(i*math.pi/16))
                 for i in range(32)])
        ellipse((8,8,16,16), fill=0)
    elif kind == "terminal":
        line([(3,4),(21,4),(21,20),(3,20),(3,4)])
        line([(7,9),(10,12),(7,15)])
        line([(13,15),(17,15)])
    else:
        raise ValueError(kind)
    return image.resize((size, size), RESAMPLE).tobytes()


def corner_mask(radius):
    # One quadrant, mirrored at runtime; opposite corners stay pixel symmetric.
    diameter = radius * SUPERSAMPLE * 2
    image = Image.new("L", (diameter, diameter))
    ImageDraw.Draw(image).ellipse((0, 0, diameter-1, diameter-1), fill=255)
    return image.resize((radius*2, radius*2), RESAMPLE).crop((0,0,radius,radius)).tobytes()


def main():
    kinds = ("file", "search", "refresh", "folder", "trash", "copy", "chevron",
             "close", "plus", "check", "play", "stop", "exe", "dot", "python_ring",
             "python_core", "box_top", "box_left", "box_right", "image", "gear", "terminal")
    lines = ['"""Generated by scripts/generate_ui_masks.py; do not hand-edit."""', "", "MASKS = {"]
    count = 0
    for kind in kinds + ("corner",):
        for size in range(1, 33) if kind == "corner" else range(8, 65):
            raw = corner_mask(size) if kind == "corner" else icon_mask(kind, size)
            data = base64.b64encode(zlib.compress(raw, 9)).decode("ascii")
            lines.append('    (%r, %d): %r,' % (kind, size, data))
            count += 1
    lines.append("}\n")
    output = Path(__file__).resolve().parents[1] / "app/ui/_raster_masks.py"
    output.write_text("\n".join(lines), encoding="utf-8")
    print("Generated", count, "antialiased masks:", output, output.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
