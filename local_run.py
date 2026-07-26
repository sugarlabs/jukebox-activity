#!/usr/bin/env python3

import sys
import os
import traceback
import faulthandler

faulthandler.enable()
import gi
import cairo
import logging

os.environ["SUGAR_LOGGER_LEVEL"] = "debug"
logging.basicConfig(level=logging.DEBUG)

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk

gi.require_foreign("cairo")

import dbus.mainloop.glib
dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

# Force the Sugar GTK theme so icons and CSS render correctly in
# standalone mode
os.environ.setdefault("GTK_THEME", "Sugar")
# Set up standalone environment
os.environ.setdefault("SUGAR_BUNDLE_ID", "org.laptop.sugar.Jukebox")
os.environ.setdefault("SUGAR_BUNDLE_NAME", "Jukebox")
os.environ.setdefault("SUGAR_BUNDLE_PATH", os.getcwd())
os.environ.setdefault("SUGAR_ACTIVITY_ROOT", os.path.expanduser(
    "~/.sugar/default/org.laptop.sugar.Jukebox"))

activity_root = os.environ["SUGAR_ACTIVITY_ROOT"]
for subdir in ["tmp", "instance", "data"]:
    os.makedirs(os.path.join(activity_root, subdir), exist_ok=True)


def _setup_icon_theme():
    display = Gdk.Display.get_default()
    if display:
        theme = Gtk.IconTheme.get_for_display(display)
        # Try system path first
        theme.add_search_path("/usr/share/icons/sugar")
        # Try local scratch path for testing
        local_icons = os.path.abspath(
            os.path.join(
                os.path.dirname(__file__),
                '..',
                'sugar-artwork',
                'icons'))
        if os.path.exists(local_icons):
            theme.add_search_path(local_icons)


_setup_icon_theme()

from sugar4.activity.activityhandle import ActivityHandle
from activity import JukeboxActivity


def main():
    def on_activate(app):
        icon_theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
        icon_theme.add_search_path(os.path.join(os.getcwd(), "icons"))

        # Load the CSS Provider
        css_provider = Gtk.CssProvider()
        css_path = os.path.join(os.getcwd(), "activity.css")
        if os.path.exists(css_path):
            css_provider.load_from_path(css_path)
            Gtk.StyleContext.add_provider_for_display(
                Gdk.Display.get_default(),
                css_provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )

        settings = Gtk.Settings.get_default()
        settings.set_property("gtk-icon-theme-name", "Sugar")
        settings.set_property("gtk-theme-name", "Sugar")

        handle = ActivityHandle(
            activity_id="jukebox-local",
            object_id=None
        )
        try:
            win = JukeboxActivity(handle)
            logging.debug("local_run.py sys.argv: %s", sys.argv)
            for arg in sys.argv[1:]:
                logging.debug(
                    "Checking file: %s exists=%s",
                    arg,
                    os.path.exists(arg))
                if os.path.exists(arg):
                    path = os.path.abspath(arg)
                    title = os.path.basename(path)
                    # Load directly into the playlist widget
                    # (read_file requires Sugar Journal metadata)
                    win.playlist_widget.load_file(path, title)
            if len(win.playlist_widget) > 0:
                win.playlist_widget.show()
                win.control.check_if_next_prev()
                win.play_index(0)
            app.add_window(win)
            win.present()
        except Exception as e:
            print("Failed to launch activity: %s" % e, file=sys.stderr)
            traceback.print_exc()
            app.quit()

    app = Gtk.Application(application_id="org.laptop.sugar.Jukebox.local")
    app.connect("activate", on_activate)
    return app.run(None)


if __name__ == "__main__":
    sys.exit(main())
