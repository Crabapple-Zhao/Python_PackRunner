"""Small dependency-free rounded Tkinter widgets used by the main window."""

import math
import tkinter as tk


def draw_rounded_rectangle(
    canvas, x1, y1, x2, y2, radius, fill, outline="", width=1, tag="rounded"
):
    """Draw a rounded rectangle from basic canvas primitives."""
    canvas.delete(tag)
    radius = max(1, min(radius, (x2 - x1) / 2, (y2 - y1) / 2))
    diameter = radius * 2
    options = {"fill": fill, "outline": "", "tags": tag}
    canvas.create_rectangle(x1 + radius, y1, x2 - radius, y2, **options)
    canvas.create_rectangle(x1, y1 + radius, x2, y2 - radius, **options)
    canvas.create_arc(
        x1, y1, x1 + diameter, y1 + diameter,
        start=90, extent=90, style=tk.PIESLICE, **options
    )
    canvas.create_arc(
        x2 - diameter, y1, x2, y1 + diameter,
        start=0, extent=90, style=tk.PIESLICE, **options
    )
    canvas.create_arc(
        x2 - diameter, y2 - diameter, x2, y2,
        start=270, extent=90, style=tk.PIESLICE, **options
    )
    canvas.create_arc(
        x1, y2 - diameter, x1 + diameter, y2,
        start=180, extent=90, style=tk.PIESLICE, **options
    )
    if outline:
        arc_border = {
            "style": tk.ARC,
            "outline": outline,
            "width": width,
            "tags": tag,
        }
        line_border = {"fill": outline, "width": width, "tags": tag}
        canvas.create_arc(
            x1, y1, x1 + diameter, y1 + diameter,
            start=90, extent=90, **arc_border
        )
        canvas.create_arc(
            x2 - diameter, y1, x2, y1 + diameter,
            start=0, extent=90, **arc_border
        )
        canvas.create_arc(
            x2 - diameter, y2 - diameter, x2, y2,
            start=270, extent=90, **arc_border
        )
        canvas.create_arc(
            x1, y2 - diameter, x1 + diameter, y2,
            start=180, extent=90, **arc_border
        )
        canvas.create_line(x1 + radius, y1, x2 - radius, y1, **line_border)
        canvas.create_line(x1 + radius, y2, x2 - radius, y2, **line_border)
        canvas.create_line(x1, y1 + radius, x1, y2 - radius, **line_border)
        canvas.create_line(x2, y1 + radius, x2, y2 - radius, **line_border)
    canvas.tag_lower(tag)


class RoundedFrame(tk.Canvas):
    """Canvas-backed rounded surface with a regular Tk frame for child widgets."""

    def __init__(
        self, parent, fill, background, border, radius=12,
        width=100, height=100, border_width=1, **kwargs
    ):
        super().__init__(
            parent,
            width=width,
            height=height,
            bg=background,
            highlightthickness=0,
            bd=0,
            **kwargs,
        )
        self._fill = fill
        self._border = border
        self._radius = radius
        self._border_width = border_width
        self.content = tk.Frame(self, bg=fill, bd=0, highlightthickness=0)
        self._content_window = self.create_window(
            radius, 2, anchor="nw", window=self.content
        )
        self.bind("<Configure>", self._redraw, add="+")

    def _redraw(self, event=None):
        width = max(2, self.winfo_width())
        height = max(2, self.winfo_height())
        draw_rounded_rectangle(
            self, 1, 1, width - 1, height - 1,
            self._radius, self._fill, self._border,
            self._border_width, "surface",
        )
        # Keep a clear pixel row above and below the child frame so the
        # rounded surface border cannot be painted over by its background.
        self.coords(self._content_window, self._radius, 2)
        self.itemconfigure(
            self._content_window,
            width=max(1, width - self._radius * 2),
            height=max(1, height - 4),
        )


class RoundedButton(tk.Canvas):
    """Rounded button with explicit hover, border, and disabled states."""

    def __init__(
        self, parent, text, command, width, height, radius,
        background, foreground, hover_background, parent_background,
        font, border="", disabled_background="#ECEFF3",
        disabled_foreground="#A8AFBA", icon_kind=None,
    ):
        super().__init__(
            parent,
            width=width,
            height=height,
            bg=parent_background,
            highlightthickness=0,
            bd=0,
            takefocus=1,
            cursor="hand2",
        )
        self._text = text
        self._command = command
        self._radius = radius
        self._normal_background = background
        self._hover_background = hover_background
        self._foreground = foreground
        self._border = border or background
        self._disabled_background = disabled_background
        self._disabled_foreground = disabled_foreground
        self._font = font
        self._icon_kind = icon_kind
        self._state = tk.NORMAL
        self._hovered = False
        self.bind("<Configure>", self._redraw, add="+")
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self.bind("<Button-1>", self._click)
        self.bind("<Return>", self._click)
        self.bind("<space>", self._click)

    def _redraw(self, _event=None):
        disabled = self._state == tk.DISABLED
        fill = (
            self._disabled_background if disabled
            else self._hover_background if self._hovered
            else self._normal_background
        )
        foreground = self._disabled_foreground if disabled else self._foreground
        border = "#DDE1E7" if disabled else self._border
        draw_rounded_rectangle(
            self, 1, 1, self.winfo_width() - 1, self.winfo_height() - 1,
            self._radius, fill, border, 1, "button",
        )
        self.delete("label")
        text_x = self.winfo_width() / 2 + (10 if self._icon_kind else 0)
        self.create_text(
            text_x,
            self.winfo_height() / 2,
            text=self._text,
            fill=foreground,
            font=self._font,
            tags="label",
        )
        if self._icon_kind:
            self._draw_icon(
                self.winfo_width() / 2 - 32,
                self.winfo_height() / 2,
                foreground,
            )

    def _draw_icon(self, x, y, color):
        kind = self._icon_kind
        line = {"fill": color, "width": 2, "tags": "label"}
        if kind == "file":
            left, top = x - 6, y - 8
            right, bottom = x + 6, y + 8
            fold_left, fold_bottom = x + 1, y - 3
            self.create_line(
                left, top,
                fold_left, top,
                right, fold_bottom,
                right, bottom,
                left, bottom,
                left, top,
                joinstyle=tk.MITER,
                **line,
            )
            self.create_line(
                fold_left, top,
                fold_left, fold_bottom,
                right, fold_bottom,
                joinstyle=tk.MITER,
                **line,
            )
        elif kind == "search":
            self.create_oval(x - 7, y - 7, x + 4, y + 4, outline=color, width=2, tags="label")
            self.create_line(x + 3, y + 3, x + 8, y + 8, **line)
        elif kind == "refresh":
            arrow = {
                "fill": color,
                "width": 2,
                "smooth": True,
                "splinesteps": 24,
                "arrow": tk.LAST,
                "arrowshape": (5, 6, 2),
                "capstyle": tk.ROUND,
                "joinstyle": tk.ROUND,
                "tags": "label",
            }
            self.create_line(
                x - 7, y + 1,
                x - 7, y - 2,
                x - 4, y - 5,
                x + 7, y - 5,
                **arrow,
            )
            self.create_line(
                x + 7, y - 1,
                x + 7, y + 2,
                x + 4, y + 5,
                x - 7, y + 5,
                **arrow,
            )
        elif kind == "folder":
            self.create_polygon(x - 8, y - 5, x - 2, y - 5, x + 1, y - 2, x + 8, y - 2, x + 7, y + 7, x - 8, y + 7, fill=color, outline="", tags="label")
        elif kind == "trash":
            self.create_rectangle(x - 5, y - 5, x + 5, y + 7, outline=color, width=2, tags="label")
            self.create_line(x - 7, y - 7, x + 7, y - 7, **line)
            self.create_line(x - 2, y - 9, x + 2, y - 9, **line)
        elif kind == "copy":
            self.create_rectangle(x - 7, y - 5, x + 3, y + 7, outline=color, width=2, tags="label")
            self.create_rectangle(x - 3, y - 8, x + 7, y + 4, outline=color, width=2, tags="label")

    def _enter(self, _event=None):
        if self._state != tk.DISABLED:
            self._hovered = True
            self._redraw()

    def _leave(self, _event=None):
        self._hovered = False
        self._redraw()

    def _click(self, _event=None):
        if self._state != tk.DISABLED and self._command is not None:
            self._command()
        return "break"

    def set_state(self, state):
        self._state = state
        self.configure(cursor="arrow" if state == tk.DISABLED else "hand2")
        self._redraw()

    def instate(self, states):
        for state in states:
            if state == "disabled" and self._state != tk.DISABLED:
                return False
            if state == "!disabled" and self._state == tk.DISABLED:
                return False
        return True


class RoundedProgressBar(tk.Canvas):
    """Compact rounded progress bar with determinate and busy modes."""

    def __init__(
        self, parent, height, radius, background, foreground,
        parent_background, width=100,
    ):
        super().__init__(
            parent,
            width=width,
            height=height,
            bg=parent_background,
            highlightthickness=0,
            bd=0,
        )
        self._bar_height = height
        self._radius = radius
        self._track = background
        self._foreground = foreground
        self._mode = "determinate"
        self._value = 0.0
        self._phase = 0.0
        self._direction = 1
        self._after_id = None
        self._interval = 12
        self.bind("<Configure>", self._redraw, add="+")

    def configure(self, cnf=None, **kwargs):
        options = dict(cnf or {})
        options.update(kwargs)
        if "mode" in options:
            self._mode = options.pop("mode")
        if "value" in options:
            self._value = max(0.0, min(100.0, float(options.pop("value"))))
        result = super().configure(**options) if options else None
        self._redraw()
        return result

    config = configure

    def start(self, interval=12):
        self._interval = max(8, int(interval))
        if self._after_id is None:
            self._tick()

    def stop(self):
        if self._after_id is not None:
            self.after_cancel(self._after_id)
            self._after_id = None
        self._phase = 0.0
        self._direction = 1
        self._redraw()

    def _tick(self):
        if self._mode != "indeterminate":
            self._after_id = None
            return
        self._phase += self._direction * 1.8
        if self._phase >= 100.0:
            self._phase = 100.0
            self._direction = -1
        elif self._phase <= 0.0:
            self._phase = 0.0
            self._direction = 1
        self._redraw()
        self._after_id = self.after(self._interval, self._tick)

    def _redraw(self, _event=None):
        if not self.winfo_exists():
            return
        width = self.winfo_width()
        height = self.winfo_height()
        if width < 4 or height < 4:
            return
        inset = 1
        draw_rounded_rectangle(
            self,
            inset,
            inset,
            width - inset,
            height - inset,
            min(self._radius, (height - inset * 2) / 2),
            self._track,
            "",
            tag="progress_track",
        )
        self.delete("progress_fill")
        inner_left = inset
        inner_right = width - inset
        available = max(1, inner_right - inner_left)
        if self._mode == "indeterminate":
            segment = max(height * 3, available * 0.18)
            travel = max(0.0, available - segment)
            fill_left = inner_left + travel * self._phase / 100.0
            fill_right = min(inner_right, fill_left + segment)
        elif self._value > 0:
            fill_left = inner_left
            fill_right = inner_left + available * self._value / 100.0
        else:
            return
        draw_rounded_rectangle(
            self,
            fill_left,
            inset,
            fill_right,
            height - inset,
            min(self._radius, (height - inset * 2) / 2),
            self._foreground,
            "",
            tag="progress_fill",
        )
        self.tag_raise("progress_fill")


class RoundedEntry(tk.Canvas):
    """Flat entry embedded in a rounded, focus-aware border."""

    def __init__(
        self, parent, textvariable, height, radius, background,
        parent_background, border, focus_border, foreground, font,
        width=240, left_padding=13, right_padding=13,
    ):
        super().__init__(
            parent,
            width=width,
            height=height,
            bg=parent_background,
            highlightthickness=0,
            bd=0,
            cursor="xterm",
        )
        self._height = height
        self._radius = radius
        self._fill = background
        self._border = border
        self._focus_border = focus_border
        self._left_padding = left_padding
        self._right_padding = right_padding
        self._focused = False
        self.entry = tk.Entry(
            self,
            textvariable=textvariable,
            bg=background,
            fg=foreground,
            insertbackground=foreground,
            selectbackground=focus_border,
            selectforeground="#FFFFFF",
            relief=tk.FLAT,
            bd=0,
            highlightthickness=0,
            font=font,
        )
        self._entry_window = self.create_window(
            left_padding, height / 2, anchor="w", window=self.entry
        )
        self.entry.bind("<FocusIn>", self._focus_in, add="+")
        self.entry.bind("<FocusOut>", self._focus_out, add="+")
        super().bind("<Button-1>", lambda _event: self.entry.focus_set())
        super().bind("<Configure>", self._redraw, add="+")

    def _redraw(self, _event=None):
        border = self._focus_border if self._focused else self._border
        draw_rounded_rectangle(
            self, 1, 1, self.winfo_width() - 1, self.winfo_height() - 1,
            self._radius, self._fill, border, 1, "entry_surface",
        )
        self.coords(
            self._entry_window,
            self._left_padding,
            self.winfo_height() / 2,
        )
        self.itemconfigure(
            self._entry_window,
            width=max(
                20,
                self.winfo_width() - self._left_padding - self._right_padding,
            ),
            height=max(20, self.winfo_height() - 8),
        )

    def _focus_in(self, _event=None):
        self._focused = True
        self._redraw()

    def _focus_out(self, _event=None):
        self._focused = False
        self._redraw()

    def bind(self, sequence=None, func=None, add=None):
        return self.entry.bind(sequence, func, add if add is not None else "+")

    def focus_set(self):
        return self.entry.focus_set()

    def get(self):
        return self.entry.get()


class RoundedScrollbar(tk.Canvas):
    """Minimal dark scrollbar without legacy arrows or native borders."""

    def __init__(
        self, parent, command, width, background, track, thumb,
        hover_thumb, min_thumb=28,
    ):
        super().__init__(
            parent,
            width=width,
            bg=background,
            highlightthickness=0,
            bd=0,
            cursor="arrow",
        )
        self._command = command
        self._track = track
        self._thumb = thumb
        self._hover_thumb = hover_thumb
        self._min_thumb = min_thumb
        self._first = 0.0
        self._last = 1.0
        self._thumb_top = 0
        self._thumb_bottom = 0
        self._drag_offset = None
        self._hovered = False
        self.bind("<Configure>", self._redraw, add="+")
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self.bind("<Button-1>", self._press)
        self.bind("<B1-Motion>", self._drag)
        self.bind("<ButtonRelease-1>", self._release)

    def set(self, first, last):
        self._first = max(0.0, min(1.0, float(first)))
        self._last = max(self._first, min(1.0, float(last)))
        self._redraw()

    def _redraw(self, _event=None):
        self.delete("scroll_track")
        self.delete("scroll_thumb")
        width = self.winfo_width()
        height = self.winfo_height()
        if width < 4 or height < 10 or self._last - self._first >= 0.999:
            self.configure(cursor="arrow")
            return

        top = 4
        bottom = height - 4
        track_height = max(1, bottom - top)
        visible = max(0.01, self._last - self._first)
        thumb_height = min(
            track_height,
            max(self._min_thumb, round(track_height * visible)),
        )
        travel = max(1, track_height - thumb_height)
        max_first = max(0.0001, 1.0 - visible)
        thumb_top = top + round(travel * min(1.0, self._first / max_first))
        thumb_bottom = min(bottom, thumb_top + thumb_height)
        self._thumb_top = thumb_top
        self._thumb_bottom = thumb_bottom
        self.configure(cursor="hand2")

        self._draw_symmetric_pill(
            "scroll_track", top, bottom, self._track
        )
        self._draw_symmetric_pill(
            "scroll_thumb", thumb_top, thumb_bottom,
            self._hover_thumb if self._hovered else self._thumb,
        )
        self.tag_raise("scroll_thumb")

    def _draw_symmetric_pill(self, tag, top, bottom, color):
        """Rasterize a vertically rounded bar with mirrored left/right edges."""
        self.delete(tag)
        width = self.winfo_width()
        if width < 2:
            return
        left = 0
        right = width - 1
        center = (left + right) / 2.0
        radius = min(4.0, (right - left) / 2.0, (bottom - top) / 2.0)
        first = max(0, math.ceil(top))
        last = min(self.winfo_height() - 1, math.floor(bottom))
        for row in range(first, last + 1):
            distance = min(row - top, bottom - row)
            if distance >= radius:
                half_width = center - left
            else:
                inside = max(0.0, radius * radius - (radius - distance) ** 2)
                half_width = math.sqrt(inside)
            x1 = max(left, int(math.ceil(center - half_width)))
            x2 = min(right, int(math.floor(center + half_width)))
            if x2 >= x1:
                self.create_rectangle(
                    x1, row, x2 + 1, row + 1,
                    fill=color, outline="", tags=tag,
                )

    def _enter(self, _event=None):
        self._hovered = True
        self._redraw()

    def _leave(self, _event=None):
        self._hovered = False
        self._redraw()

    def _press(self, event):
        if self._last - self._first >= 0.999:
            return "break"
        if self._thumb_top <= event.y <= self._thumb_bottom:
            self._drag_offset = event.y - self._thumb_top
        else:
            self._drag_offset = (self._thumb_bottom - self._thumb_top) / 2
            self._move_to(event.y)
        return "break"

    def _drag(self, event):
        if self._drag_offset is not None:
            self._move_to(event.y)
        return "break"

    def _release(self, _event=None):
        self._drag_offset = None
        return "break"

    def _move_to(self, pointer_y):
        height = self.winfo_height()
        top = 4
        bottom = height - 4
        thumb_height = max(1, self._thumb_bottom - self._thumb_top)
        travel = max(1, bottom - top - thumb_height)
        thumb_top = pointer_y - (self._drag_offset or thumb_height / 2)
        travel_fraction = max(0.0, min(1.0, (thumb_top - top) / travel))
        max_first = max(0.0, 1.0 - (self._last - self._first))
        self._command("moveto", travel_fraction * max_first)


class RoundedSelect(tk.Canvas):
    """Rounded fixed-choice selector with a wide arrow target."""

    def __init__(
        self, parent, variable, values, width, height, radius,
        background, parent_background, border, focus_border,
        foreground, muted, font,
    ):
        super().__init__(
            parent,
            width=width,
            height=height,
            bg=parent_background,
            highlightthickness=0,
            bd=0,
            takefocus=1,
            cursor="hand2",
        )
        self._variable = variable
        self._values = tuple(values)
        self._radius = radius
        self._fill = background
        self._border = border
        self._focus_border = focus_border
        self._foreground = foreground
        self._muted = muted
        self._font = font
        self._hovered = False
        self._popup = None
        self._outside_bind_id = None
        self._variable.trace_add("write", self._redraw)
        self.bind("<Configure>", self._redraw, add="+")
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self.bind("<Button-1>", self._open)
        self.bind("<Return>", self._open)
        self.bind("<space>", self._open)
        self.bind("<Down>", lambda _event: self._step_value(1))
        self.bind("<Up>", lambda _event: self._step_value(-1))
        self.bind("<Destroy>", self._on_destroy, add="+")

    def _redraw(self, *_):
        self.delete("select_content")
        border = self._focus_border if self._hovered else self._border
        draw_rounded_rectangle(
            self, 1, 1, self.winfo_width() - 1, self.winfo_height() - 1,
            self._radius, self._fill, border, 1, "select_surface",
        )
        # Keep the arrow target visually compact: about one eighth of the
        # selector width instead of the former quarter-width block.
        arrow_width = max(22, round(self.winfo_width() / 8))
        split_x = self.winfo_width() - arrow_width
        self.create_line(
            split_x, 6, split_x, self.winfo_height() - 6,
            fill=self._border, tags="select_content",
        )
        self.create_text(
            13, self.winfo_height() / 2,
            text=self._variable.get(), anchor="w",
            fill=self._foreground, font=self._font, tags="select_content",
        )
        center_x = split_x + arrow_width / 2
        center_y = self.winfo_height() / 2
        self.create_line(
            center_x - 5, center_y - 2, center_x, center_y + 3,
            center_x + 5, center_y - 2,
            fill=self._muted, width=2, joinstyle=tk.ROUND,
            tags="select_content",
        )

    def _enter(self, _event=None):
        self._hovered = True
        self._redraw()

    def _leave(self, _event=None):
        self._hovered = False
        self._redraw()

    def _open(self, _event=None):
        self.focus_set()
        if self._popup is not None and self._popup.winfo_exists():
            self._close_popup()
            return "break"

        row_height = max(30, self.winfo_height() - 6)
        popup_width = self.winfo_width()
        popup_height = row_height * len(self._values) + 2
        x = self.winfo_rootx()
        y = self.winfo_rooty() + self.winfo_height() + 2
        root = self.winfo_toplevel()
        x -= root.winfo_rootx()
        y -= root.winfo_rooty()
        x = max(0, min(x, root.winfo_width() - popup_width))
        if y + popup_height > root.winfo_height():
            y = max(0, self.winfo_rooty() - root.winfo_rooty() - popup_height - 2)

        popup = tk.Frame(
            root,
            bg=self._border,
            bd=0,
            highlightthickness=0,
            takefocus=1,
        )
        self._popup = popup
        popup.place(x=x, y=y, width=popup_width, height=popup_height)

        selected = self._variable.get()
        for index, value in enumerate(self._values):
            is_selected = value == selected
            row = tk.Label(
                popup,
                text=value,
                bg="#EAF0FF" if is_selected else self._fill,
                fg=self._focus_border if is_selected else self._foreground,
                font=self._font,
                anchor="w",
                padx=13,
                cursor="hand2",
                bd=0,
                highlightthickness=0,
            )
            row.place(
                x=1,
                y=1 + index * row_height,
                width=popup_width - 2,
                height=row_height,
            )
            row.bind(
                "<Enter>",
                lambda _event, widget=row: widget.configure(
                    bg="#EAF0FF", fg=self._focus_border
                ),
            )
            row.bind(
                "<Leave>",
                lambda _event, widget=row, active=is_selected: widget.configure(
                    bg="#EAF0FF" if active else self._fill,
                    fg=self._focus_border if active else self._foreground,
                ),
            )
            row.bind(
                "<Button-1>",
                lambda _event, choice=value: self._choose(choice),
            )

        popup.bind("<Escape>", lambda _event: self._close_popup())
        popup.lift()
        popup.focus_set()
        self.after_idle(self._activate_outside_close)
        return "break"

    def _choose(self, value):
        self._variable.set(value)
        self._close_popup()
        self.focus_set()
        return "break"

    def _step_value(self, direction):
        try:
            current = self._values.index(self._variable.get())
        except ValueError:
            current = 0
        selected = max(0, min(len(self._values) - 1, current + direction))
        self._variable.set(self._values[selected])
        return "break"

    def _activate_outside_close(self):
        popup = self._popup
        if popup is None or not popup.winfo_exists():
            return
        root = self.winfo_toplevel()
        self._outside_bind_id = root.bind(
            "<Button-1>", self._outside_click, add="+"
        )

    def _outside_click(self, event):
        popup = self._popup
        if popup is None or not popup.winfo_exists():
            return
        widget = event.widget
        while widget is not None:
            if widget == popup:
                return
            widget = widget.master
        self._close_popup()

    def _close_popup(self):
        popup = self._popup
        self._popup = None
        root = self.winfo_toplevel()
        if self._outside_bind_id is not None:
            root.unbind("<Button-1>", self._outside_bind_id)
            self._outside_bind_id = None
        if popup is not None and popup.winfo_exists():
            popup.destroy()

    def _on_destroy(self, event):
        if event.widget == self:
            self._close_popup()
