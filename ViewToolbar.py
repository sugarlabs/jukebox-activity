# Copyright (C) 2008 Kushal Das <kushal@fedoraproject.org>
#
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

from gettext import gettext as _

import gobject
import gtk

from sugar.graphics.toolbutton import ToolButton


class ViewToolbar(gtk.Toolbar):
    """Class to create the view toolbar"""

    __gsignals__ = {
        'go-fullscreen': (gobject.SIGNAL_RUN_FIRST,
                          gobject.TYPE_NONE,
                          ([]))
    }

    def __init__(self, toolbox, jukebox):
        gtk.Toolbar.__init__(self)
        self.toolbox = toolbox
        self.jukebox = jukebox

        self._zoom_tofit = ToolButton('zoom-best-fit')
        self._zoom_tofit.set_tooltip(_('Fit to window'))
        self._zoom_tofit.connect('clicked', self._zoom_tofit_cb)
        self.insert(self._zoom_tofit, -1)
        self._zoom_tofit.show()

        self._zoom_original = ToolButton('zoom-original')
        self._zoom_original.set_tooltip(_('Original size'))
        self._zoom_original.connect('clicked', self._zoom_original_cb)
        self.insert(self._zoom_original, -1)
        self._zoom_original.show()

        spacer = gtk.SeparatorToolItem()
        spacer.props.draw = False
        self.insert(spacer, -1)
        spacer.show()

        self._fullscreen = ToolButton('view-fullscreen')
        self._fullscreen.set_tooltip(_('Fullscreen'))
        self._fullscreen.connect('clicked', self._fullscreen_cb)
        self.insert(self._fullscreen, -1)
        self._fullscreen.show()

    def _zoom_tofit_cb(self, button):
        pass
        #self.jukebox.player.set_fit_to_screen_cb()

    def _zoom_original_cb(self, button):
        pass
        #self.jukebox.player.set_original_to_size_cb()

    def _fullscreen_cb(self, button):
        self.emit('go-fullscreen')
