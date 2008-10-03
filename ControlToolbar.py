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
import re

import gobject
import gtk

from sugar.graphics.toolbutton import ToolButton
from sugar.graphics.menuitem import MenuItem
from sugar.graphics import iconentry
from sugar.activity import activity


class ControlToolbar(gtk.Toolbar):
    """Class to create the Control (play )toolbar"""

    __gsignals__ = {
        'go-fullscreen': (gobject.SIGNAL_RUN_FIRST,
                          gobject.TYPE_NONE,
                          ([]))
    }


    def __init__(self, toolbox, jukebox):
        gtk.Toolbar.__init__(self)
        self.toolbox = toolbox
        self.jukebox = jukebox

        self.prev_button = gtk.ToolButton(gtk.STOCK_MEDIA_PREVIOUS)
        self.prev_button.show()
        self.prev_button.connect('clicked', self.prev_button_clicked_cb)
        self.insert(self.prev_button, -1)


        self.pause_image = gtk.image_new_from_stock(gtk.STOCK_MEDIA_PAUSE,
                                                    gtk.ICON_SIZE_BUTTON)
        self.pause_image.show()
        self.play_image = gtk.image_new_from_stock(gtk.STOCK_MEDIA_PLAY,
                                                   gtk.ICON_SIZE_BUTTON)
        self.play_image.show()

        self.button = gtk.ToolButton()
        self.button.set_icon_widget(self.play_image)
        self.button.set_property('can-default', True)
        self.button.show()
        self.button.connect('clicked', self._button_clicked_cb)

        self.insert(self.button, -1)

        self.next_button = gtk.ToolButton(gtk.STOCK_MEDIA_NEXT)
        self.next_button.show()
        self.next_button.connect('clicked', self.next_button_clicked_cb)
        self.insert(self.next_button, -1)


        self.adjustment = gtk.Adjustment(0.0, 0.00, 100.0, 0.1, 1.0, 1.0)
        self.hscale = gtk.HScale(self.adjustment)
        self.hscale.set_draw_value(False)
        self.hscale.set_update_policy(gtk.UPDATE_CONTINUOUS)
        self.hscale.connect('button-press-event', jukebox.scale_button_press_cb)
        self.hscale.connect('button-release-event', jukebox.scale_button_release_cb)
        
        self.scale_item = gtk.ToolItem()
        self.scale_item.set_expand(True)
        self.scale_item.add(self.hscale)
        self.insert(self.scale_item, -1)

        spacer = gtk.SeparatorToolItem()
        spacer.props.draw = False
        self.insert(spacer, -1)
        spacer.show()

        self.audioscale = gtk.VolumeButton()
        self.audioscale.connect('value-changed', jukebox.volume_changed_cb)
        self.audioscale.set_value(1)

        self.audio_scale_item = gtk.ToolItem()
        self.audio_scale_item.set_expand(False)
        self.audio_scale_item.add(self.audioscale)
        self.insert(self.audio_scale_item, -1)

        spacer = gtk.SeparatorToolItem()
        spacer.props.draw = False
        self.insert(spacer, -1)
        spacer.show()
        self._fullscreen = ToolButton('view-fullscreen')
        self._fullscreen.set_tooltip(_('Fullscreen'))
        self._fullscreen.connect('clicked', self._fullscreen_cb)
        self.insert(self._fullscreen, -1)
        self._fullscreen.show()
    
    def prev_button_clicked_cb(self,widget):
        self.jukebox.songchange('prev')

    def next_button_clicked_cb(self,widget):
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

    def _fullscreen_cb(self, button):
        self.emit('go-fullscreen')
