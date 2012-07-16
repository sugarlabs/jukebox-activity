# Copyright (C) 2007 Andy Wingo <wingo@pobox.com>
# Copyright (C) 2007 Red Hat, Inc.
# Copyright (C) 2008 Kushal Das <kushal@fedoraproject.org>
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA

import logging

from gettext import gettext as _

from gi.repository import GObject
from gi.repository import Gtk

from sugar3.graphics.toolbutton import ToolButton
from sugar3.graphics.toggletoolbutton import ToggleToolButton


class ViewToolbar(Gtk.Toolbar):
    __gtype_name__ = 'ViewToolbar'

    __gsignals__ = {
        'go-fullscreen': (GObject.SignalFlags.RUN_FIRST,
                          None,
                         ([])),
        'toggle-playlist': (GObject.SignalFlags.RUN_FIRST,
                            None,
                            ([]))
    }

    def __init__(self):
        GObject.GObject.__init__(self)

        self._show_playlist = ToggleToolButton('view-list')
        self._show_playlist.set_active(True)
        self._show_playlist.set_tooltip(_('Show Playlist'))
        self._show_playlist.connect('toggled', self._playlist_toggled_cb)
        self.insert(self._show_playlist, -1)
        self._show_playlist.show()

        self._fullscreen = ToolButton('view-fullscreen')
        self._fullscreen.set_tooltip(_('Fullscreen'))
        self._fullscreen.connect('clicked', self._fullscreen_cb)
        self.insert(self._fullscreen, -1)
        self._fullscreen.show()

    def _fullscreen_cb(self, button):
        self.emit('go-fullscreen')

    def _playlist_toggled_cb(self, button):
        self.emit('toggle-playlist')


class Control(GObject.GObject):
    """Class to create the Control (play) toolbar"""

    def __init__(self, toolbar, jukebox):
        GObject.GObject.__init__(self)

        self.toolbar = toolbar
        self.jukebox = jukebox

        self.open_button = ToolButton('list-add')
        self.open_button.set_tooltip(_('Add track'))
        self.open_button.show()
        self.open_button.connect('clicked', jukebox.open_button_clicked_cb)
        self.toolbar.insert(self.open_button, -1)

        erase_playlist_entry_btn = ToolButton(icon_name='list-remove')
        erase_playlist_entry_btn.set_tooltip(_('Remove track'))
        erase_playlist_entry_btn.connect('clicked',
                 jukebox._erase_playlist_entry_clicked_cb)
        self.toolbar.insert(erase_playlist_entry_btn, -1)

        spacer = Gtk.SeparatorToolItem()
        self.toolbar.insert(spacer, -1)
        spacer.show()

        self.prev_button = ToolButton('player_rew')
        self.prev_button.set_tooltip(_('Previous'))
        self.prev_button.show()
        self.prev_button.connect('clicked', self.prev_button_clicked_cb)
        self.toolbar.insert(self.prev_button, -1)

        self.pause_image = Gtk.Image.new_from_stock(Gtk.STOCK_MEDIA_PAUSE,
                                                    Gtk.IconSize.BUTTON)
        self.pause_image.show()
        self.play_image = Gtk.Image.new_from_stock(Gtk.STOCK_MEDIA_PLAY,
                                                   Gtk.IconSize.BUTTON)
        self.play_image.show()

        self.button = Gtk.ToolButton()
        self.button.set_icon_widget(self.play_image)
        self.button.set_property('can-default', True)
        self.button.show()
        self.button.connect('clicked', self._button_clicked_cb)

        self.toolbar.insert(self.button, -1)

        self.next_button = ToolButton('player_fwd')
        self.next_button.set_tooltip(_('Next'))
        self.next_button.show()
        self.next_button.connect('clicked', self.next_button_clicked_cb)
        self.toolbar.insert(self.next_button, -1)

        current_time = Gtk.ToolItem()
        self.current_time_label = Gtk.Label(label='')
        current_time.add(self.current_time_label)
        current_time.show()
        toolbar.insert(current_time, -1)

        self.adjustment = Gtk.Adjustment(0.0, 0.00, 100.0, 0.1, 1.0, 1.0)
        self.hscale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL,
                                adjustment=self.adjustment)
        self.hscale.set_draw_value(False)
        # FIXME: this seems to be deprecated
        # self.hscale.set_update_policy(Gtk.UPDATE_CONTINUOUS)
        logging.debug("FIXME: AttributeError: 'Scale' object has no "
                      "attribute 'set_update_policy'")
        self.hscale.connect('button-press-event',
                jukebox.scale_button_press_cb)
        self.hscale.connect('button-release-event',
                jukebox.scale_button_release_cb)

        self.scale_item = Gtk.ToolItem()
        self.scale_item.set_expand(True)
        self.scale_item.add(self.hscale)
        self.toolbar.insert(self.scale_item, -1)

        total_time = Gtk.ToolItem()
        self.total_time_label = Gtk.Label(label='')
        total_time.add(self.total_time_label)
        total_time.show()
        toolbar.insert(total_time, -1)

    def prev_button_clicked_cb(self, widget):
        self.jukebox.songchange('prev')

    def next_button_clicked_cb(self, widget):
        self.jukebox.songchange('next')

    def _button_clicked_cb(self, widget):
        self.jukebox.play_toggled()

    def set_button_play(self):
        self.button.set_icon_widget(self.play_image)

    def set_button_pause(self):
        self.button.set_icon_widget(self.pause_image)

    def set_disabled(self):
        self.button.set_sensitive(False)
        self.scale_item.set_sensitive(False)
        self.hscale.set_sensitive(False)

    def set_enabled(self):
        self.button.set_sensitive(True)
        self.scale_item.set_sensitive(True)
        self.hscale.set_sensitive(True)
