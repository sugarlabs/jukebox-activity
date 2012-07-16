# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA 02111-1307
# USA

import logging
from gettext import gettext as _

import gi
gi.require_version('Gtk', '3.0')

from gi.repository import GObject
from gi.repository import Gtk
from gi.repository import Pango


COLUMNS_NAME = ('index', 'media')
COLUMNS = dict((name, i) for i, name in enumerate(COLUMNS_NAME))


class PlayListWidget(Gtk.ScrolledWindow):
    def __init__(self, play_callback):
        self._playlist = None
        self._play_callback = play_callback

        GObject.GObject.__init__(self, hadjustment=None,
                                    vadjustment=None)
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.listview = Gtk.TreeView()
        self.treemodel = Gtk.ListStore(int, object)
        self.listview.set_model(self.treemodel)
        selection = self.listview.get_selection()
        selection.set_mode(Gtk.SelectionMode.SINGLE)

        renderer_idx = Gtk.CellRendererText()
        treecol_idx = Gtk.TreeViewColumn(_('No.'))
        treecol_idx.pack_start(renderer_idx, True)
        treecol_idx.set_cell_data_func(renderer_idx, self._set_number)
        self.listview.append_column(treecol_idx)

        renderer_title = Gtk.CellRendererText()
        renderer_title.set_property('ellipsize', Pango.EllipsizeMode.END)
        treecol_title = Gtk.TreeViewColumn(_('Play List'))
        treecol_title.pack_start(renderer_title, True)
        treecol_title.set_cell_data_func(renderer_title, self._set_title)
        self.listview.append_column(treecol_title)

        # we don't support search in the playlist for the moment:
        self.listview.set_enable_search(False)

        self.listview.connect('row-activated', self.__on_row_activated)

        self.add(self.listview)

    def __on_row_activated(self, treeview, path, col):
        model = treeview.get_model()

        treeiter = model.get_iter(path)
        media_idx = model.get_value(treeiter, COLUMNS['index'])
        self._play_callback(media_idx)

    def _set_number(self, column, cell, model, it, data):
        idx = model.get_value(it, COLUMNS['index'])
        cell.set_property('text', idx + 1)

    def _set_title(self, column, cell, model, it, data):
        playlist_item = model.get_value(it, COLUMNS['media'])
        cell.set_property('text', playlist_item['title'])

    def update(self, playlist):
        self.treemodel.clear()
        self._playlist = playlist
        pl = list(enumerate(playlist))
        for i, media in pl:
            self.treemodel.append((i, media))
        self.set_cursor(0)

    def set_cursor(self, index):
        self.listview.set_cursor((index,))

    def delete_selected_items(self):
        selection = self.listview.get_selection()
        sel_model, sel_rows = self.listview.get_selection().get_selected_rows()
        for row in sel_rows:
            index = sel_model.get_value(sel_model.get_iter(row), 0)
            self._playlist.pop(index)
            self.treemodel.remove(self.treemodel.get_iter(row))
        self.update(self._playlist)
