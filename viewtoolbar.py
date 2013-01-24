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

# Copyright (C) 2007 Andy Wingo <wingo@pobox.com>
# Copyright (C) 2007 Red Hat, Inc.
# Copyright (C) 2008 Kushal Das <kushal@fedoraproject.org>
# Copyright (C) 2013 Manuel Kaufmann <humitos@gmail.com>

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
        self._show_playlist.set_active(False)
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
