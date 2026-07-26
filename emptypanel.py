from gi.repository import Gtk

from sugar4.graphics import style
from sugar4.graphics.icon import Icon


def show(activity, icon_name, message, btn_label, btn_callback):
    empty_widgets = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    empty_widgets.add_css_class("background-white")
    empty_widgets.set_vexpand(True)
    empty_widgets.set_hexpand(True)

    center_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    center_box.set_valign(Gtk.Align.CENTER)
    center_box.set_halign(Gtk.Align.CENTER)
    center_box.set_vexpand(True)
    center_box.set_hexpand(True)
    empty_widgets.append(center_box)

    image_icon = Icon(pixel_size=style.LARGE_ICON_SIZE,
                      icon_name=icon_name,
                      stroke_color=style.COLOR_BUTTON_GREY.get_svg(),
                      fill_color=style.COLOR_TRANSPARENT.get_svg())
    image_icon.set_margin_bottom(style.DEFAULT_PADDING)
    center_box.append(image_icon)

    label = Gtk.Label(label='<span foreground="%s"><b>%s</b></span>' %
                      (style.COLOR_BUTTON_GREY.get_html(),
                       message))
    label.set_use_markup(True)
    label.set_margin_bottom(style.DEFAULT_PADDING)
    center_box.append(label)

    hbox = Gtk.Box()
    hbox.set_halign(Gtk.Align.CENTER)
    open_image_btn = Gtk.Button()
    open_image_btn.connect('clicked', btn_callback)

    add_image = Gtk.Image.new_from_icon_name("list-add")
    buttonbox = Gtk.Box(spacing=8)
    buttonbox.append(add_image)
    lbl = Gtk.Label(label=btn_label)
    lbl.set_margin_start(5)
    lbl.set_margin_end(5)
    buttonbox.append(lbl)

    open_image_btn.set_child(buttonbox)
    hbox.append(open_image_btn)
    hbox.set_margin_bottom(style.DEFAULT_PADDING)
    center_box.append(hbox)

    activity.view_area.append_page(empty_widgets, None)
    activity.view_area.set_current_page(2)
