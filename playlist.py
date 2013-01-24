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

import os
import logging
import tempfile
from gettext import gettext as _

from gi.repository import GObject
from gi.repository import Gtk
from gi.repository import Pango

from sugar3 import mime
from sugar3.datastore import datastore
from sugar3.activity import activity
from sugar3.graphics.icon import CellRendererIcon


COLUMNS_NAME = ('index', 'title', 'available')
COLUMNS = dict((name, i) for i, name in enumerate(COLUMNS_NAME))


class PlayList(Gtk.ScrolledWindow):

    __gsignals__ = {
        'play-index': (GObject.SignalFlags.RUN_FIRST, None, [int, str]),
        }

    def __init__(self):
        self._not_found_files = 0
        self._current_playing = None
        self._items = []

        GObject.GObject.__init__(self, hadjustment=None,
                                 vadjustment=None)
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.listview = Gtk.TreeView()
        self.treemodel = Gtk.ListStore(int, object, bool)
        self.listview.set_model(self.treemodel)
        selection = self.listview.get_selection()
        selection.set_mode(Gtk.SelectionMode.SINGLE)

        renderer_icon = CellRendererIcon(self.listview)
        renderer_icon.props.icon_name = 'emblem-notification'
        renderer_icon.props.width = 20
        renderer_icon.props.height = 20
        renderer_icon.props.size = 20
        treecol_icon = Gtk.TreeViewColumn()
        treecol_icon.pack_start(renderer_icon, False)
        treecol_icon.set_cell_data_func(renderer_icon, self._set_icon)
        self.listview.append_column(treecol_icon)

        renderer_idx = Gtk.CellRendererText()
        treecol_idx = Gtk.TreeViewColumn(_('No.'))
        treecol_idx.pack_start(renderer_idx, True)
        treecol_idx.set_cell_data_func(renderer_idx, self._set_number)
        self.listview.append_column(treecol_idx)

        renderer_title = Gtk.CellRendererText()
        renderer_title.set_property('ellipsize', Pango.EllipsizeMode.END)
        treecol_title = Gtk.TreeViewColumn(_('Track'))
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
        index = model.get_value(treeiter, COLUMNS['index'])
        # TODO: put the path inside the ListStore
        path = self._items[index]['path']
        # TODO: check if the stream is available before emitting the signal
        self._current_playing = index
        self.set_cursor(index)
        self.emit('play-index', index, path)

    def _set_number(self, column, cell, model, it, data):
        idx = model.get_value(it, COLUMNS['index'])
        cell.set_property('text', idx + 1)

    def _set_title(self, column, cell, model, it, data):
        title = model.get_value(it, COLUMNS['title'])
        available = model.get_value(it, COLUMNS['available'])

        cell.set_property('text', title)
        sensitive = True
        if not available:
            sensitive = False
        cell.set_property('sensitive', sensitive)

    def _set_icon(self, column, cell, model, it, data):
        available = model.get_value(it, COLUMNS['available'])
        cell.set_property('visible', not available)

    def set_cursor(self, index):
        self.listview.set_cursor((index,))

    def delete_selected_items(self):
        selection = self.listview.get_selection()
        sel_model, sel_rows = self.listview.get_selection().get_selected_rows()
        for row in sel_rows:
            index = sel_model.get_value(sel_model.get_iter(row), 0)
            self._items.pop(index)
            self.treemodel.remove(self.treemodel.get_iter(row))

    def check_available_media(self, path):
        if os.path.exists(path):
            return True
        else:
            return False

    def get_missing_tracks(self):
        missing_tracks = []
        for track in self._playlist:
            if not track['available']:
                missing_tracks.append(track)
        return missing_tracks

    def _load_m3u_playlist(self, file_path):
        for uri in self._read_m3u_playlist(file_path):
            if not self.check_available_media(uri['path']):
                self._not_found_files += 1

            self._add_track(uri['path'], uri['title'])

    def _load_stream(self, file_path, title=None):
        # TODO: read id3 here
        if os.path.islink(file_path):
            file_path = os.path.realpath(file_path)
        self._add_track(file_path, title)

    def load_file(self, jobject, title=None):
        logging.debug('#### jobject: %s', type(jobject))
        if isinstance(jobject, datastore.RawObject) or \
           isinstance(jobject, datastore.DSObject):
            file_path = jobject.file_path
            title = jobject.metadata['title']
        else:
            file_path = jobject

        mimetype = mime.get_for_file('file://' + file_path)
        logging.info('read_file mime %s', mimetype)
        if mimetype == 'audio/x-mpegurl':
            # is a M3U playlist:
            self._load_m3u_playlist(file_path)
        else:
            # is not a M3U playlist
            self._load_stream(file_path, title)

    def update(self):
        for tree_item, playlist_item in zip(self.treemodel, self._items):
            tree_item[2] = self.check_available_media(playlist_item['path'])

    def _add_track(self, file_path, title):
        available = self.check_available_media(file_path)
        item = {'path': file_path,
                'title': title,
                'available': available}
        self._items.append(item)
        index = len(self._items) - 1
        self.treemodel.append((index, item['title'], available))

    def _read_m3u_playlist(self, file_path):
        urls = []
        title = ''
        for line in open(file_path).readlines():
            line = line.strip()
            if line != '':
                if line.startswith('#EXTINF:'):
                    # line with data
                    # EXTINF: title
                    title = line[len('#EXTINF:'):]
                else:
                    uri = {}
                    uri['path'] = line.strip()
                    uri['title'] = title
                    urls.append(uri)
                    title = ''
        return urls

    def create_playlist_jobject(self):
        """Create an object in the Journal to store the playlist.

        This is needed if the activity was not started from a playlist
        or from scratch.
        """

        jobject = datastore.create()
        jobject.metadata['mime_type'] = "audio/x-mpegurl"
        jobject.metadata['title'] = _('Jukebox playlist')

        temp_path = os.path.join(activity.get_activity_root(),
                                 'instance')
        if not os.path.exists(temp_path):
            os.makedirs(temp_path)

        jobject.file_path = tempfile.mkstemp(dir=temp_path)[1]
        return jobject
