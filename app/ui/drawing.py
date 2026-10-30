"""Antialiased graphics using pre-rendered coverage masks and Tk PhotoImage.

Only the standard library is used at runtime. Text remains native Tk text;
rounded surfaces stretch their flat sections without resizing corner pixels.
"""
import base64
import struct
import tkinter as tk
import weakref
import zlib
from collections import OrderedDict
from functools import lru_cache

from ._raster_masks import MASKS

_IMAGE_CACHES = weakref.WeakKeyDictionary()


@lru_cache(maxsize=512)
def _mask(kind, size):
    return zlib.decompress(base64.b64decode(MASKS[(kind, size)]))


def _rgb(canvas, color):
    return tuple(component // 257 for component in canvas.winfo_rgb(color))


def _png(size, rgba):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    rows = b"".join(b"\x00" + rgba[y*size*4:(y+1)*size*4] for y in range(size))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


def _cached_images(canvas, key, make_rgba):
    root = canvas._root()
    cache = _IMAGE_CACHES.setdefault(root, OrderedDict())
    if key not in cache:
        size, images = make_rgba()
        cache[key] = tuple(tk.PhotoImage(master=root, data=base64.b64encode(_png(size, rgba)))
                           for rgba in images)
        if len(cache) > 256:
            cache.popitem(last=False)
    cache.move_to_end(key)
    return cache[key]


def _remember(canvas, tag, images):
    # Live canvas items keep their images even if the bounded shared cache evicts them.
    if not hasattr(canvas, "_graphic_images"):
        canvas._graphic_images = {}
    canvas._graphic_images[tag] = images


def draw_icon(canvas, kind, x, y, size, color, tag="icon"):
    size = max(8, min(64, round(size)))
    if kind == "python":
        layers = (("python_ring", _rgb(canvas, color)), ("python_core", _rgb(canvas, "#E3A91A")))
    elif kind == "package":
        layers = (("box_top", _rgb(canvas, color)), ("box_left", _rgb(canvas, "#2A8CFF")),
                  ("box_right", _rgb(canvas, "#0068DE")))
    else:
        layers = ((kind, _rgb(canvas, color)),)

    def render():
        pixels = bytearray(size * size * 4)
        for name, rgb in layers:
            for index, alpha in enumerate(_mask(name, size)):
                if alpha:
                    offset = index * 4
                    old_alpha = pixels[offset+3]
                    combined = alpha + old_alpha * (255-alpha) / 255
                    for channel in range(3):
                        pixels[offset+channel] = round((rgb[channel]*alpha + pixels[offset+channel]*old_alpha*(255-alpha)/255) / combined)
                    pixels[offset+3] = round(combined)
        return size, (bytes(pixels),)

    images = _cached_images(canvas, ("icon", size, layers), render)
    _remember(canvas, tag, images)
    canvas.delete(tag)
    return canvas.create_image(round(x-size/2), round(y-size/2), anchor="nw", image=images[0], tags=tag)


def _corners(canvas, radius, fill, outline, width):
    fill_rgb = _rgb(canvas, fill)
    border_rgb = _rgb(canvas, outline) if outline else fill_rgb
    border_width = min(radius, max(0, round(width))) if outline else 0

    def render():
        outer = _mask("corner", radius)
        inner_radius = radius - border_width
        inner = _mask("corner", inner_radius) if inner_radius else None
        rgba = bytearray(radius * radius * 4)
        for y in range(radius):
            for x in range(radius):
                index = y*radius+x
                alpha = outer[index]
                if not alpha:
                    continue
                inside = 0
                if x >= border_width and y >= border_width:
                    inside = inner[(y-border_width)*inner_radius+x-border_width] if inner else 255
                inside = min(alpha, inside)
                for channel in range(3):
                    rgba[index*4+channel] = round((border_rgb[channel]*(alpha-inside)+fill_rgb[channel]*inside) / alpha)
                rgba[index*4+3] = alpha
        variants = []
        for flip_x, flip_y in ((False,False),(True,False),(False,True),(True,True)):
            variant = bytearray()
            for y in range(radius):
                for x in range(radius):
                    offset = ((radius-1-y if flip_y else y)*radius +
                              (radius-1-x if flip_x else x))*4
                    variant.extend(rgba[offset:offset+4])
            variants.append(bytes(variant))
        return radius, variants

    return _cached_images(canvas, ("corner", radius, fill_rgb, border_rgb, border_width), render)


def draw_rounded_rectangle(canvas, x1, y1, x2, y2, radius, fill, outline="", width=1, tag="rounded"):
    canvas.delete(tag)
    x1, y1, x2, y2 = map(round, (x1,y1,x2,y2))
    if x2 <= x1 or y2 <= y1:
        return
    radius = min(32, max(1, round(radius)), (x2-x1)//2, (y2-y1)//2)
    if radius < 1:
        canvas.create_rectangle(x1,y1,x2,y2,fill=fill,outline="",tags=tag)
        return
    images = _corners(canvas, radius, fill, outline, width)
    _remember(canvas, tag, images)
    options = {"fill": fill, "outline": "", "tags": tag}
    canvas.create_rectangle(x1+radius,y1,x2-radius,y2,**options)
    canvas.create_rectangle(x1,y1+radius,x2,y2-radius,**options)
    if outline and width:
        border_width = min(radius, max(1,round(width)))
        for box in ((x1+radius,y1,x2-radius,y1+border_width),
                    (x1+radius,y2-border_width,x2-radius,y2),
                    (x1,y1+radius,x1+border_width,y2-radius),
                    (x2-border_width,y1+radius,x2,y2-radius)):
            canvas.create_rectangle(*box,fill=outline,outline="",tags=tag)
    for x,y,img in ((x1,y1,images[0]),(x2-radius,y1,images[1]),
                    (x1,y2-radius,images[2]),(x2-radius,y2-radius,images[3])):
        canvas.create_image(x,y,anchor="nw",image=img,tags=tag)
    canvas.tag_lower(tag)
