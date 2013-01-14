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

# Activity that plays media.
# Copyright (C) 2007 Andy Wingo <wingo@pobox.com>
# Copyright (C) 2007 Red Hat, Inc.
# Copyright (C) 2008-2010 Kushal Das <kushal@fedoraproject.org>
# Copyright (C) 2013 Manuel Kaufmann <humitos@gmail.com>

import sys
import logging
import tempfile
from gettext import gettext as _
import os

from sugar3.activity import activity
from sugar3.graphics.objectchooser import ObjectChooser
from sugar3 import mime
from sugar3.datastore import datastore

from sugar3.graphics.toolbarbox import ToolbarBox
from sugar3.graphics.toolbarbox import ToolbarButton
from sugar3.activity.widgets import StopButton
from sugar3.activity.widgets import ActivityToolbarButton
from sugar3.graphics.alert import ErrorAlert
from sugar3.graphics.alert import Alert

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gst', '1.0')

from gi.repository import GObject
from gi.repository import Gdk
from gi.repository import Gtk
from gi.repository import Gst
from gi.repository import Gio

import urllib
from viewtoolbar import ViewToolbar
from controls import Controls
from player import GstPlayer

from playlist import PlayList

PLAYLIST_WIDTH_PROP = 1.0 / 3


class JukeboxActivity(activity.Activity):
    UPDATE_INTERVAL = 500

    def __init__(self, handle):
        activity.Activity.__init__(self, handle)
        self._object_id = handle.object_id
        self.set_title(_('Jukebox Activity'))
        self.player = None
        self.max_participants = 1
        self._playlist_jobject = None

        toolbar_box = ToolbarBox()
        activity_button = ActivityToolbarButton(self)
        activity_toolbar = activity_button.page
        toolbar_box.toolbar.insert(activity_button, 0)
        self.title_entry = activity_toolbar.title

        # FIXME: I don't know what is the mission of this line
        # activity_toolbar.stop.hide()

        self.volume_monitor = Gio.VolumeMonitor.get()
        self.volume_monitor.connect('mount-added', self._mount_added_cb)
        self.volume_monitor.connect('mount-removed', self._mount_removed_cb)

        _view_toolbar = ViewToolbar()
        _view_toolbar.connect('go-fullscreen',
                              self.__go_fullscreen_cb)
        _view_toolbar.connect('toggle-playlist',
                              self.__toggle_playlist_cb)
        view_toolbar_button = ToolbarButton(
            page=_view_toolbar,
            icon_name='toolbar-view')
        _view_toolbar.show()
        toolbar_box.toolbar.insert(view_toolbar_button, -1)
        view_toolbar_button.show()

        self.control = Controls(toolbar_box.toolbar, self)

        toolbar_box.toolbar.insert(StopButton(self), -1)

        self.set_toolbar_box(toolbar_box)
        toolbar_box.show_all()

        self.connect("key_press_event", self._key_press_event_cb)

        # We want to be notified when the activity gets the focus or
        # loses it.  When it is not active, we don't need to keep
        # reproducing the video
        self.connect("notify::active", self._notify_active_cb)

        # FIXME: this is related with shared activity and it doesn't work
        # if handle.uri:
        #     pass
        # elif self._shared_activity:
        #     if self.get_shared():
        #         pass
        #     else:
        #         # Wait for a successful join before trying to get the document
        #         self.connect("joined", self._joined_cb)

        self.update_id = -1
        self.changed_id = -1
        self.seek_timeout_id = -1
        self.player = None
        self.uri = None

        # {'url': 'file://.../media.ogg', 'title': 'My song', object_id: '..'}
        self.playlist = []

        self.jobjectlist = []
        self.playpath = None
        self.currentplaying = None
        self.playflag = False
        self._not_found_files = 0

        # README: I changed this because I was getting an error when I
        # tried to modify self.bin with something different than
        # Gtk.Bin

        # self.bin = Gtk.HBox()
        # self.bin.show()

        self.canvas = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self._alert = None

        self.playlist_widget = PlayList(self.play)
        self.playlist_widget.update(self.playlist)
        self.playlist_widget.show()
        self.canvas.pack_start(self.playlist_widget, False, True, 0)
        self._empty_widget = Gtk.Label(label="")
        self._empty_widget.show()
        self.videowidget = VideoWidget()
        self.set_canvas(self.canvas)
        self._init_view_area()
        self.show_all()
        self.canvas.connect('size-allocate', self.__size_allocate_cb)

        #From ImageViewer Activity
        self._want_document = True
        if self._object_id is None:
            self._show_object_picker = GObject.timeout_add(1000, \
            self._show_picker_cb)

        if handle.uri:
            self.uri = handle.uri
            GObject.idle_add(self._start, self.uri, handle.title)

        # Create the player just once
        logging.debug('Instantiating GstPlayer')
        self.player = GstPlayer(self.videowidget)
        self.player.connect("eos", self._player_eos_cb)
        self.player.connect("error", self._player_error_cb)
        self.p_position = Gst.CLOCK_TIME_NONE
        self.p_duration = Gst.CLOCK_TIME_NONE

    def _notify_active_cb(self, widget, event):
        """Sugar notify us that the activity is becoming active or inactive.
        When we are inactive, we stop the player if it is reproducing
        a video.
        """
        if self.player.player.props.uri is not None:
            if not self.player.is_playing() and self.props.active:
                self.player.play()
            if self.player.is_playing() and not self.props.active:
                self.player.pause()

    def _init_view_area(self):
        """
        Use a notebook with two pages, one empty an another
        with the videowidget
        """
        self.view_area = Gtk.Notebook()
        self.view_area.set_show_tabs(False)
        self.view_area.append_page(self._empty_widget, None)
        self.view_area.append_page(self.videowidget, None)
        self.canvas.pack_end(self.view_area, expand=True,
                             fill=True, padding=0)

    def _switch_canvas(self, show_video):
        """Show or hide the video visualization in the canvas.

        When hidden, the canvas is filled with an empty widget to
        ensure redrawing.

        """
        if show_video:
            self.view_area.set_current_page(1)
        else:
            self.view_area.set_current_page(0)
        self.canvas.queue_draw()

    def __size_allocate_cb(self, widget, allocation):
        canvas_size = self.canvas.get_allocation()
        playlist_width = int(canvas_size.width * PLAYLIST_WIDTH_PROP)
        self.playlist_widget.set_size_request(playlist_width, 0)

    def open_button_clicked_cb(self, widget):
        """ To open the dialog to select a new file"""
        #self.player.seek(0L)
        #self.player.stop()
        #self.playlist = []
        #self.playpath = None
        #self.currentplaying = None
        #self.playflag = False
        self._want_document = True
        self._show_object_picker = GObject.timeout_add(1, self._show_picker_cb)

    def _key_press_event_cb(self, widget, event):
        keyname = Gdk.keyval_name(event.keyval)
        logging.info("Keyname Press: %s, time: %s", keyname, event.time)
        if self.title_entry.has_focus():
            return False

        if keyname == "space":
            self.play_toggled()
            return True

    def check_if_next_prev(self):
        if self.currentplaying == 0:
            self.control.prev_button.set_sensitive(False)
        else:
            self.control.prev_button.set_sensitive(True)
        if self.currentplaying == len(self.playlist) - 1:
            self.control.next_button.set_sensitive(False)
        else:
            self.control.next_button.set_sensitive(True)

    def songchange(self, direction):
        #if self.playflag:
        #    self.playflag = False
        #    return
        self.player.seek(0L)
        if direction == "prev" and self.currentplaying > 0:
            self.play(self.currentplaying - 1)
            logging.info("prev: " + self.playlist[self.currentplaying]['url'])
            #self.playflag = True
        elif direction == "next" and \
                self.currentplaying < len(self.playlist) - 1:
            self.play(self.currentplaying + 1)
            logging.info("next: " + self.playlist[self.currentplaying]['url'])
            #self.playflag = True
        else:
            self.play_toggled()
            self.player.stop()
            self._switch_canvas(show_video=False)
            self.player.set_uri(None)
            self.check_if_next_prev()

    def play(self, media_index):
        self._switch_canvas(show_video=True)
        self.currentplaying = media_index
        url = self.playlist[self.currentplaying]['url']
        error = None
        if url.startswith('journal://'):
            try:
                jobject = datastore.get(url[len("journal://"):])
                url = 'file://' + jobject.file_path
            except:
                path = url[len("journal://"):]
                error = _('The file %s was not found') % path

        self.check_if_next_prev()

        if error is None:
            self.player.set_uri(url)
            self.player.play()
        else:
            self.control.set_disabled()
            self._show_error_alert(error)

        self.playlist_widget.set_cursor(self.currentplaying)

    def _player_eos_cb(self, widget):
        self.songchange('next')

    def _show_error_alert(self, title, msg=None):
        self._alert = ErrorAlert()
        self._alert.props.title = title
        if msg is not None:
            self._alert.props.msg = msg
        self.add_alert(self._alert)
        self._alert.connect('response', self._alert_cancel_cb)
        self._alert.show()

    def _mount_added_cb(self, volume_monitor, device):
        self.view_area.set_current_page(0)
        self.remove_alert(self._alert)
        self.playlist_widget.update(self.playlist)

    def _mount_removed_cb(self, volume_monitor, device):
        self.view_area.set_current_page(0)
        self.remove_alert(self._alert)
        self.playlist_widget.update(self.playlist)

    def _show_missing_tracks_alert(self, nro):
        self._alert = Alert()
        title = _('%s tracks not found.') % nro
        self._alert.props.title = title
        self._alert.add_button(Gtk.ResponseType.APPLY, _('Details'))
        self.add_alert(self._alert)
        self._alert.connect('response',
                self.__missing_tracks_alert_response_cb)

    def __missing_tracks_alert_response_cb(self, alert, response_id):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        vbox.props.valign = Gtk.Align.CENTER
        label = Gtk.Label(label='')
        label.set_markup(_('<b>Missing tracks</b>'))
        vbox.pack_start(label, False, False, 15)

        for track in self.playlist_widget.get_missing_tracks():
            path = track['url'].replace('journal://', '')\
                .replace('file://', '')
            label = Gtk.Label(label=path)
            vbox.add(label)

        _missing_tracks = Gtk.ScrolledWindow()
        _missing_tracks.add_with_viewport(vbox)
        _missing_tracks.show_all()

        self.view_area.append_page(_missing_tracks, None)

        self.view_area.set_current_page(2)
        self.remove_alert(alert)

    def _alert_cancel_cb(self, alert, response_id):
        self.remove_alert(alert)

    def _player_error_cb(self, widget, message, detail):
        self.player.stop()
        self.player.set_uri(None)
        self.control.set_disabled()

        file_path = self.playlist[self.currentplaying]['url']\
            .replace('journal://', 'file://')
        mimetype = mime.get_for_file(file_path)

        title = _('Error')
        msg = _('This "%s" file can\'t be played') % mimetype
        self._switch_canvas(False)
        self._show_error_alert(title, msg)

    def _joined_cb(self, activity):
        logging.debug("someone joined")
        pass

    def _shared_cb(self, activity):
        logging.debug("shared start")
        pass

    def _show_picker_cb(self):
        #From ImageViewer Activity
        if not self._want_document:
            return

        # README: some arguments are deprecated so I avoid them

        # chooser = ObjectChooser(_('Choose document'), self,
        #     Gtk.DialogFlags.MODAL |
        #     Gtk.DialogFlags.DESTROY_WITH_PARENT,
        #     what_filter=mime.GENERIC_TYPE_AUDIO)

        chooser = ObjectChooser(self, what_filter=mime.GENERIC_TYPE_AUDIO)

        try:
            result = chooser.run()
            if result == Gtk.ResponseType.ACCEPT:
                jobject = chooser.get_selected_object()
                if jobject and jobject.file_path:
                    logging.error('Adding %s', jobject.file_path)
                    title = jobject.metadata.get('title', None)
                    self._load_file(jobject.file_path, title,
                            jobject.object_id)
        finally:
            #chooser.destroy()
            #del chooser
            pass

    def read_file(self, file_path):
        """Load a file from the datastore on activity start."""
        logging.debug('JukeBoxAtivity.read_file: %s', file_path)
        title = self.metadata.get('title', None)
        self._load_file(file_path, title, self._object_id)

    def _load_file(self, file_path, title, object_id):
        self.uri = os.path.abspath(file_path)
        if os.path.islink(self.uri):
            self.uri = os.path.realpath(self.uri)
        mimetype = mime.get_for_file('file://' + file_path)
        logging.error('read_file mime %s', mimetype)
        if mimetype == 'audio/x-mpegurl':
            # is a M3U playlist:
            for uri in self._read_m3u_playlist(file_path):
                if not self.playlist_widget.check_available_media(uri['url']):
                    self._not_found_files += 1

                GObject.idle_add(self._start, uri['url'], uri['title'],
                        uri['object_id'])
        else:
            # is another media file:
            GObject.idle_add(self._start, self.uri, title, object_id)

        if self._not_found_files > 0:
            self._show_missing_tracks_alert(self._not_found_files)

    def _create_playlist_jobject(self):
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
        self._playlist_jobject = jobject

    def write_file(self, file_path):

        def write_playlist_to_file(file_path):
            """Open the file at file_path and write the playlist.

            It is saved in audio/x-mpegurl format.

            """
            list_file = open(file_path, 'w')
            for uri in self.playlist:
                list_file.write('#EXTINF: %s\n' % uri['title'])
                list_file.write('%s\n' % uri['url'])
            list_file.close()

        if not self.metadata['mime_type']:
            self.metadata['mime_type'] = 'audio/x-mpegurl'

        if self.metadata['mime_type'] == 'audio/x-mpegurl':
            write_playlist_to_file(file_path)

        else:
            if self._playlist_jobject is None:
                self._create_playlist_jobject()

            # Add the playlist to the playlist jobject description.
            # This is only done if the activity was not started from a
            # playlist or from scratch:
            description = ''
            for uri in self.playlist:
                description += '%s\n' % uri['title']
            self._playlist_jobject.metadata['description'] = description

            write_playlist_to_file(self._playlist_jobject.file_path)
            datastore.write(self._playlist_jobject)

    def _read_m3u_playlist(self, file_path):
        urls = []
        title = ''
        for line in open(file_path).readlines():
            line = line.strip()
            if line != '':
                if line.startswith('#EXTINF:'):
                    # line with data
                    #EXTINF: title
                    title = line[len('#EXTINF:'):]
                else:
                    uri = {}
                    uri['url'] = line.strip()
                    uri['title'] = title
                    if uri['url'].startswith('journal://'):
                        uri['object_id'] = uri['url'][len('journal://'):]
                    else:
                        uri['object_id'] = None
                    urls.append(uri)
                    title = ''
        return urls

    def _start(self, uri=None, title=None, object_id=None):
        self._want_document = False
        self.playpath = os.path.dirname(uri)
        if not uri:
            return False

        if title is not None:
            title = title.strip()
        if object_id is not None:
            self.playlist.append({'url': 'journal://' + object_id,
                    'title': title})
        else:
            if uri.startswith("file://"):
                self.playlist.append({'url': uri, 'title': title})
            else:
                uri = "file://" + urllib.quote(os.path.abspath(uri))
                self.playlist.append({'url': uri, 'title': title})

        self.playlist_widget.update(self.playlist)

        try:
            if self.currentplaying is None:
                logging.info("Playing: " + self.playlist[0]['url'])
                url = self.playlist[0]['url']
                if url.startswith('journal://'):
                    jobject = datastore.get(url[len("journal://"):])
                    url = 'file://' + jobject.file_path

                self.player.set_uri(url)
                self.player.play()
                self.currentplaying = 0
                self.play_toggled()
                self.show_all()
            else:
                pass
                #self.player.seek(0L)
                #self.player.stop()
                #self.currentplaying += 1
                #self.player.set_uri(self.playlist[self.currentplaying])
                #self.play_toggled()
        except:
            pass
        self.check_if_next_prev()
        return False

    def play_toggled(self):
        self.control.set_enabled()

        if self.player.is_playing():
            self.player.pause()
            self.control.set_button_play()
        else:
            if self.player.error:
                self.control.set_disabled()
            else:
                self.player.play()
                if self.update_id == -1:
                    self.update_id = GObject.timeout_add(self.UPDATE_INTERVAL,
                                                         self.update_scale_cb)
                self.control.set_button_pause()

    def volume_changed_cb(self, widget, value):
        if self.player:
            self.player.player.set_property('volume', value)

    def scale_button_press_cb(self, widget, event):
        self.control.button.set_sensitive(False)
        self.was_playing = self.player.is_playing()
        if self.was_playing:
            self.player.pause()

        # don't timeout-update position during seek
        if self.update_id != -1:
            GObject.source_remove(self.update_id)
            self.update_id = -1

        # make sure we get changed notifies
        if self.changed_id == -1:
            self.changed_id = self.control.hscale.connect('value-changed',
                self.scale_value_changed_cb)

    def scale_value_changed_cb(self, scale):
        # see seek.c:seek_cb
        real = long(scale.get_value() * self.p_duration / 100)  # in ns
        self.player.seek(real)
        # allow for a preroll
        self.player.get_state(timeout=50 * Gst.MSECOND)  # 50 ms

    def scale_button_release_cb(self, widget, event):
        # see seek.cstop_seek
        widget.disconnect(self.changed_id)
        self.changed_id = -1

        self.control.button.set_sensitive(True)
        if self.seek_timeout_id != -1:
            GObject.source_remove(self.seek_timeout_id)
            self.seek_timeout_id = -1
        else:
            if self.was_playing:
                self.player.play()

        if self.update_id != -1:
            self.error('Had a previous update timeout id')
        else:
            self.update_id = GObject.timeout_add(self.UPDATE_INTERVAL,
                self.update_scale_cb)

    def update_scale_cb(self):
        success, self.p_position, self.p_duration = \
            self.player.query_position()

        if not success:
            return True

        if self.p_position != Gst.CLOCK_TIME_NONE:
            value = self.p_position * 100.0 / self.p_duration
            self.control.adjustment.set_value(value)

            # Update the current time
            seconds = self.p_position * 10 ** -9
            time = '%2d:%02d' % (int(seconds / 60), int(seconds % 60))
            self.control.current_time_label.set_text(time)

        # FIXME: this should be updated just once when the file starts
        # the first time
        if self.p_duration != Gst.CLOCK_TIME_NONE:
            seconds = self.p_duration * 10 ** -9
            time = '%2d:%02d' % (int(seconds / 60), int(seconds % 60))
            self.control.total_time_label.set_text(time)

        return True

    def _erase_playlist_entry_clicked_cb(self, widget):
        self.playlist_widget.delete_selected_items()

    def __go_fullscreen_cb(self, toolbar):
        self.fullscreen()

    def __toggle_playlist_cb(self, toolbar):
        if self.playlist_widget.get_visible():
            self.playlist_widget.hide()
        else:
            self.playlist_widget.show_all()
        self.canvas.queue_draw()


class VideoWidget(Gtk.DrawingArea):
    def __init__(self):
        GObject.GObject.__init__(self)
        self.set_events(Gdk.EventMask.POINTER_MOTION_MASK |
                        Gdk.EventMask.POINTER_MOTION_HINT_MASK |
                        Gdk.EventMask.EXPOSURE_MASK |
                        Gdk.EventMask.KEY_PRESS_MASK |
                        Gdk.EventMask.KEY_RELEASE_MASK)

        self.set_app_paintable(True)
        self.set_double_buffered(False)


if __name__ == '__main__':
    window = Gtk.Window()
    view = VideoWidget()

    #player.connect("eos", self._player_eos_cb)
    #player.connect("error", self._player_error_cb)
    view.show()
    window.add(view)

    def map_cb(widget):
        player = GstPlayer(view)
        player.set_uri(sys.argv[1])
        player.play()

    window.connect('map', map_cb)
    window.maximize()
    window.show_all()
    window.connect("destroy", Gtk.main_quit)
    Gtk.main()
