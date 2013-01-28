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
import emptypanel
from gettext import gettext as _

from sugar3.activity import activity
from sugar3 import mime
from sugar3.datastore import datastore

from sugar3.graphics.toolbarbox import ToolbarBox
from sugar3.graphics.toolbarbox import ToolbarButton
from sugar3.activity.widgets import StopButton
from sugar3.activity.widgets import ActivityToolbarButton
from sugar3.graphics.alert import ErrorAlert
from sugar3.graphics.alert import Alert
from sugar3.graphics.icon import Icon

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gst', '1.0')

from gi.repository import GObject
from gi.repository import Gdk
from gi.repository import Gtk
from gi.repository import Gio

from viewtoolbar import ViewToolbar
from controls import Controls
from player import GstPlayer

from playlist import PlayList

PLAYLIST_WIDTH_PROP = 1.0 / 3


class JukeboxActivity(activity.Activity):

    __gsignals__ = {
        'playlist-finished': (GObject.SignalFlags.RUN_FIRST, None, []),
        }

    def __init__(self, handle):
        activity.Activity.__init__(self, handle)

        self.player = None

        self._alert = None
        self._playlist_jobject = None

        self.set_title(_('Jukebox Activity'))
        self.max_participants = 1

        toolbar_box = ToolbarBox()
        activity_button = ActivityToolbarButton(self)
        activity_toolbar = activity_button.page
        toolbar_box.toolbar.insert(activity_button, 0)
        self.title_entry = activity_toolbar.title

        self._view_toolbar = ViewToolbar()
        self._view_toolbar.connect('go-fullscreen',
                             self.__go_fullscreen_cb)
        self._view_toolbar.connect('toggle-playlist',
                             self.__toggle_playlist_cb)
        view_toolbar_button = ToolbarButton(
            page=self._view_toolbar,
            icon_name='toolbar-view')
        self._view_toolbar.show()
        toolbar_box.toolbar.insert(view_toolbar_button, -1)
        view_toolbar_button.show()

        self.set_toolbar_box(toolbar_box)
        toolbar_box.show_all()

        self.connect('key_press_event', self.__key_press_event_cb)
        self.connect('playlist-finished', self.__playlist_finished_cb)

        # We want to be notified when the activity gets the focus or
        # loses it. When it is not active, we don't need to keep
        # reproducing the video
        self.connect('notify::active', self.__notify_active_cb)

        self._video_canvas = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)

        self.playlist_widget = PlayList()
        self.playlist_widget.connect('play-index', self.__play_index_cb)
        self.playlist_widget.connect('missing-tracks',
                                     self.__missing_tracks_cb)
        self.playlist_widget.set_size_request(
            Gdk.Screen.width() * PLAYLIST_WIDTH_PROP, 0)
        self.playlist_widget.show()
        self._video_canvas.pack_start(self.playlist_widget, False, True, 0)

        # Create the player just once
        logging.debug('Instantiating GstPlayer')
        self.player = GstPlayer()
        self.player.connect('eos', self.__player_eos_cb)
        self.player.connect('error', self.__player_error_cb)
        self.player.connect('play', self.__player_play_cb)

        self.control = Controls(self, toolbar_box.toolbar)

        toolbar_box.toolbar.insert(StopButton(self), -1)

        self._empty_widget = Gtk.Label(label="")
        self._empty_widget.show()
        self.videowidget = VideoWidget()
        self.set_canvas(self._video_canvas)
        self._init_view_area()
        self.show_all()

        self.player.init_view_area(self.videowidget)

        volume_monitor = Gio.VolumeMonitor.get()
        volume_monitor.connect('mount-added', self.__mount_added_cb)
        volume_monitor.connect('mount-removed', self.__mount_removed_cb)

        if handle.object_id is None:
            # The activity was launched from scratch. We need to show
            # the Empty Widget
            self.playlist_widget.hide()
            emptypanel.show(self, 'activity-jukebox',
                            _('No media'), _('Choose media files'),
                            self.control.show_picker_cb)

        self.control.check_if_next_prev()

    def __notify_active_cb(self, widget, event):
        """Sugar notify us that the activity is becoming active or inactive.
        When we are inactive, we stop the player if it is reproducing
        a video.
        """

        logging.debug('JukeboxActivity notify::active signal received')

        if self.player.player.props.current_uri is not None and \
                self.player.playing_video():
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
        self._video_canvas.pack_end(self.view_area, expand=True,
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
        self._video_canvas.queue_draw()

    def __key_press_event_cb(self, widget, event):
        keyname = Gdk.keyval_name(event.keyval)
        logging.info("Keyname Press: %s, time: %s", keyname, event.time)
        if self.title_entry.has_focus():
            return False

        if keyname == "space":
            self.control._button_clicked_cb(None)
            return True

    def __playlist_finished_cb(self, widget):
        self._switch_canvas(show_video=False)
        self._view_toolbar._show_playlist.set_active(True)
        self.unfullscreen()

        # Select the first stream to be played when Play button will
        # be pressed
        self.playlist_widget._current_playing = 0
        self.control.check_if_next_prev()

    def songchange(self, direction):
        current_playing = self.playlist_widget._current_playing
        if direction == 'prev' and current_playing > 0:
            self.play_index(current_playing - 1)
        elif direction == 'next' and \
                current_playing < len(self.playlist_widget._items) - 1:
            self.play_index(current_playing + 1)

        else:
            self.emit('playlist-finished')

    def play_index(self, index):
        # README: this line is no more necessary because of the
        # .playing_video() method
        # self._switch_canvas(show_video=True)
        self.playlist_widget._current_playing = index

        path = self.playlist_widget._items[index]['path']
        self.control.check_if_next_prev()

        self.player.set_uri(path)
        self.player.play()

    def __play_index_cb(self, widget, index, path):
        # README: this line is no more necessary because of the
        # .playing_video() method
        # self._switch_canvas(show_video=True)
        self.playlist_widget._current_playing = index

        self.control.check_if_next_prev()

        self.player.set_uri(path)
        self.player.play()

    def __player_eos_cb(self, widget):
        self.songchange('next')

    def _show_error_alert(self, title, msg=None):
        self._alert = ErrorAlert()
        self._alert.props.title = title
        if msg is not None:
            self._alert.props.msg = msg
        self.add_alert(self._alert)
        self._alert.connect('response', self._alert_cancel_cb)
        self._alert.show()

    def __mount_added_cb(self, volume_monitor, device):
        logging.debug('Mountpoint added. Checking...')
        self.view_area.set_current_page(0)
        self.remove_alert(self._alert)
        self.playlist_widget.update()

    def __mount_removed_cb(self, volume_monitor, device):
        logging.debug('Mountpoint removed. Checking...')
        self.view_area.set_current_page(0)
        self.remove_alert(self._alert)
        self.playlist_widget.update()

    def __missing_tracks_cb(self, widget, tracks):
        self._show_missing_tracks_alert(tracks)

    def _show_missing_tracks_alert(self, tracks):
        self._alert = Alert()
        title = _('%s tracks not found.') % len(tracks)
        self._alert.props.title = title
        icon = Icon(icon_name='dialog-cancel')
        self._alert.add_button(Gtk.ResponseType.CANCEL, _('Dismiss'), icon)
        icon.show()

        icon = Icon(icon_name='dialog-ok')
        self._alert.add_button(Gtk.ResponseType.APPLY, _('Details'), icon)
        icon.show()
        self.add_alert(self._alert)
        self._alert.connect(
            'response', self.__missing_tracks_alert_response_cb, tracks)

    def __missing_tracks_alert_response_cb(self, alert, response_id, tracks):
        if response_id == Gtk.ResponseType.APPLY:
            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            vbox.props.valign = Gtk.Align.CENTER
            label = Gtk.Label(label='')
            label.set_markup(_('<b>Missing tracks</b>'))
            vbox.pack_start(label, False, False, 15)

            for track in tracks:
                label = Gtk.Label(label=track['path'])
                vbox.add(label)

            _missing_tracks = Gtk.ScrolledWindow()
            _missing_tracks.add_with_viewport(vbox)
            _missing_tracks.show_all()

            self.view_area.append_page(_missing_tracks, None)

            self.view_area.set_current_page(2)

        self.remove_alert(alert)

    def _alert_cancel_cb(self, alert, response_id):
        self.remove_alert(alert)

    def __player_play_cb(self, widget):
        # Do not show the visualization widget if we are playing just
        # an audio stream

        def callback():
            if self.player.playing_video():
                self._switch_canvas(True)
            else:
                self._switch_canvas(False)
            return False

        # HACK: we need a timeout here because gstreamer returns
        # n-video = 0 if we call it immediately
        GObject.timeout_add(1000, callback)

    def __player_error_cb(self, widget, message, detail):
        self.player.stop()
        self.control.set_disabled()

        logging.error('ERROR MESSAGE: %s', message)
        logging.error('ERROR DETAIL: %s', detail)

        file_path = self.playlist_widget._items[self.playlist_widget._current_playing]['path']
        mimetype = mime.get_for_file(file_path)

        title = _('Error')
        msg = _('This "%s" file can\'t be played') % mimetype
        self._switch_canvas(False)
        self._show_error_alert(title, msg)

    def can_close(self):
        # We need to put the Gst.State in NULL so gstreamer can
        # cleanup the pipeline
        self.player.stop()
        return True

    def read_file(self, file_path):
        """Load a file from the datastore on activity start."""
        logging.debug('JukeBoxAtivity.read_file: %s', file_path)

        title = self.metadata['title']
        self.playlist_widget.load_file(file_path, title)

    def write_file(self, file_path):

        def write_playlist_to_file(file_path):
            """Open the file at file_path and write the playlist.

            It is saved in audio/x-mpegurl format.

            """

            list_file = open(file_path, 'w')
            for uri in self.playlist_widget._items:
                list_file.write('#EXTINF:%s\n' % uri['title'])
                list_file.write('%s\n' % uri['path'])
            list_file.close()

        if not self.metadata['mime_type']:
            self.metadata['mime_type'] = 'audio/x-mpegurl'

        if self.metadata['mime_type'] == 'audio/x-mpegurl':
            write_playlist_to_file(file_path)

        else:
            if self._playlist_jobject is None:
                self._playlist_jobject = self.playlist_widget.create_playlist_jobject()

            # Add the playlist to the playlist jobject description.
            # This is only done if the activity was not started from a
            # playlist or from scratch:
            description = ''
            for uri in self.playlist_widget._items:
                description += '%s\n' % uri['title']
            self._playlist_jobject.metadata['description'] = description

            write_playlist_to_file(self._playlist_jobject.file_path)
            datastore.write(self._playlist_jobject)

    def __go_fullscreen_cb(self, toolbar):
        self.fullscreen()

    def __toggle_playlist_cb(self, toolbar):
        if self._view_toolbar._show_playlist.get_active():
            self.playlist_widget.show_all()
        else:
            self.playlist_widget.hide()
        self._video_canvas.queue_draw()


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
