# Activity that plays media.
#
# Copyright (C) 2007 Andy Wingo <wingo@pobox.com>
# Copyright (C) 2007 Red Hat, Inc.
# Copyright (C) 2008-2010 Kushal Das <kushal@fedoraproject.org>
# Copyright (C) 2013 Manuel Kaufmann <humitos@gmail.com>
#
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


import sys
import logging
from gettext import gettext as _

import gi
gi.require_version('Gdk', '4.0')
gi.require_version('Gtk', '4.0')
gi.require_version('Gst', '1.0')
gi.require_version('SugarExt', '1.0')
gi.require_version('GstVideo', '1.0')

from gi.repository import GObject
from gi.repository import Gdk
from gi.repository import Gtk
from gi.repository import Gio

from sugar4.activity import activity
from sugar4 import mime
from sugar4.datastore import datastore

from sugar4.graphics.toolbarbox import ToolbarBox
from sugar4.graphics.toolbarbox import ToolbarButton
from sugar4.activity.widgets import StopButton
from sugar4.activity.widgets import ActivityToolbarButton
from sugar4.graphics.alert import ErrorAlert
from sugar4.graphics.alert import Alert
from sugar4.graphics.icon import Icon
from sugar4.graphics.toolbutton import ToolButton

from viewtoolbar import ViewToolbar
from controls import Controls
from player import GstPlayer

from playlist import PlayList

import emptypanel

PLAYLIST_WIDTH_PROP = 1.0 / 3


class JukeboxActivity(activity.Activity):

    __gsignals__ = {
        'playlist-finished': (GObject.SignalFlags.RUN_FIRST, None, []), }

    def __init__(self, handle):
        activity.Activity.__init__(self, handle)

        self.player = None

        self._alert = None
        self._playlist_jobject = None
        self._on_unfullscreen_show_playlist = False

        self.set_title(_('Jukebox Activity'))
        self.max_participants = 1

        toolbar_box = ToolbarBox()
        self._activity_toolbar_button = ActivityToolbarButton(
            self, icon_name="activity-jukebox")
        activity_toolbar = self._activity_toolbar_button.page
        toolbar_box.toolbar.prepend(self._activity_toolbar_button)
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
        toolbar_box.toolbar.append(view_toolbar_button)
        view_toolbar_button.show()

        self._control_toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self._control_toolbar_button = ToolbarButton(
            page=self._control_toolbar,
            icon_name='media-playback-start')
        toolbar_box.toolbar.append(self._control_toolbar_button)
        self._control_toolbar_button.set_visible(False)

        self.set_toolbar_box(toolbar_box)

        key_controller = Gtk.EventControllerKey()
        key_controller.connect('key-pressed', self.__key_pressed_cb)
        self.add_controller(key_controller)
        self.connect('playlist-finished', self.__playlist_finished_cb)

        # We want to be notified when the activity gets the focus or
        # loses it. When it is not active, we don't need to keep
        # reproducing the video
        self.connect('notify::active', self.__notify_active_cb)

        self._video_canvas = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)

        self._playlist_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        self.playlist_widget = PlayList()
        self.playlist_widget.connect('play-index', self.__play_index_cb)
        self.playlist_widget.connect('missing-tracks',
                                     self.__missing_tracks_cb)
        screen_w, screen_h = self._get_screen_size()
        self.playlist_widget.set_size_request(
            int(screen_w * PLAYLIST_WIDTH_PROP), 0)
        self.playlist_widget.show()

        self.playlist_widget.set_vexpand(True)
        self.playlist_widget.set_hexpand(True)
        self._playlist_box.append(self.playlist_widget)

        self._playlist_toolbar = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL)

        move_up = ToolButton("go-up")
        move_up.set_tooltip(_("Move up"))
        move_up.connect("clicked", self._move_up_cb)
        self._playlist_toolbar.append(move_up)

        move_down = ToolButton("go-down")
        move_down.set_tooltip(_("Move down"))
        move_down.connect("clicked", self._move_down_cb)
        self._playlist_toolbar.append(move_down)

        self._playlist_box.append(self._playlist_toolbar)
        self._video_canvas.append(self._playlist_box)

        # Create the player just once
        logging.debug('Instantiating GstPlayer')
        self.player = GstPlayer()
        self.player.connect('eos', self.__player_eos_cb)
        self.player.connect('error', self.__player_error_cb)
        self.player.connect('play', self.__player_play_cb)

        self.control = Controls(self, toolbar_box.toolbar,
                                self._control_toolbar)

        self._separator = Gtk.Separator()
        self._separator.set_hexpand(True)
        toolbar_box.toolbar.append(self._separator)

        self._stop = StopButton(self)
        toolbar_box.toolbar.append(self._stop)

        self._empty_widget = Gtk.Label(label="")
        self.videowidget = self.player.get_video_widget()
        self.set_canvas(self._video_canvas)
        self._init_view_area()

        if len(self.playlist_widget) < 2:
            self._view_toolbar._show_playlist.props.active = False

        self._configure_cb()

        self._volume_monitor = Gio.VolumeMonitor.get()
        self._volume_monitor.connect('mount-added', self.__mount_added_cb)
        self._volume_monitor.connect('mount-removed', self.__mount_removed_cb)

        if handle.object_id is None:
            # The activity was launched from scratch. We need to show
            # the Empty Widget
            self.playlist_widget.hide()
            emptypanel.show(self, 'activity-jukebox',
                            _('No media'), _('Choose media files'),
                            self.control.show_picker_cb)

        self.control.check_if_next_prev()

        display = Gdk.Display.get_default()
        if display:
            monitors = display.get_monitors()
            if monitors and monitors.get_n_items() > 0:
                monitor = monitors.get_item(0)
                monitor.connect("notify::geometry", self._configure_cb)

    def _move_up_cb(self, button):
        self.playlist_widget.move_up()

    def _move_down_cb(self, button):
        self.playlist_widget.move_down()

    def _configure_cb(self, *args):
        toolbar = self.get_toolbar_box().toolbar
        if self._stop.get_parent() == toolbar:
            toolbar.remove(self._stop)
        if self._separator.get_parent() == toolbar:
            toolbar.remove(self._separator)

        screen_w, screen_h = self._get_screen_size()
        if screen_w < screen_h:
            self._control_toolbar_button.show()
            self._control_toolbar_button.set_expanded(True)
            self.control.update_layout(landscape=False)
            toolbar.append(self._separator)
        else:
            self._control_toolbar_button.set_expanded(False)
            self._control_toolbar_button.hide()
            self.control.update_layout(landscape=True)
        toolbar.append(self._stop)

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
        self.view_area.set_vexpand(True)
        self.view_area.set_hexpand(True)
        self._video_canvas.append(self.view_area)

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

    def __key_pressed_cb(self, controller, keyval, keycode, state):
        ctrl = state & Gdk.ModifierType.CONTROL_MASK

        # while activity toolbar is visible, only escape key is taken
        if self._activity_toolbar_button.is_expanded():
            if keyval == Gdk.KEY_Escape:
                self._activity_toolbar_button.set_expanded(False)
                return True

            return False

        # while title is focused, no shortcuts
        if self.title_entry.has_focus():
            return False

        # Shortcut - Space does play or pause
        if keyval == Gdk.KEY_space:
            self.control.button.emit('clicked')
            return True

        # Shortcut - Up does previous playlist item
        if keyval == Gdk.KEY_Up:
            self.control.prev_button.emit('clicked')
            return True

        # Shortcut - Down does next playlist item
        if keyval == Gdk.KEY_Down:
            self.control.next_button.emit('clicked')
            return True

        # Shortcut - Escape does unfullscreen, then playlist hide
        if keyval == Gdk.KEY_Escape:
            if self.is_fullscreen():
                # sugar4.graphics.Window.__key_press_cb will handle it
                return False

            if self._view_toolbar._show_playlist.props.active:
                self._view_toolbar._show_playlist.props.active = False
                return True

        # Shortcut - ctrl-f does fullscreen toggle
        # (fullscreen enable is handled by ToolButton accelerator)
        if ctrl and keyval == Gdk.KEY_f:
            if self.is_fullscreen():
                self.unfullscreen()
                return True

        # Shortcut - ctrl-l does playlist toggle
        # (ToggleToolButton accelerator ineffective when ViewToolbar hidden)
        if ctrl and keyval == Gdk.KEY_l:
            togglebutton = self._view_toolbar._show_playlist
            togglebutton.props.active = not togglebutton.props.active
            return True

        return False

    def __playlist_finished_cb(self, widget):
        self._switch_canvas(show_video=False)
        self._view_toolbar._show_playlist.props.active = True
        self.unfullscreen()

        # Select the first stream to be played when Play button will
        # be pressed
        self.playlist_widget.set_current_playing(0)
        self.control.check_if_next_prev()

    def songchange(self, direction):
        current_playing = self.playlist_widget.get_current_playing()
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
        self.playlist_widget.set_current_playing(index)

        path = self.playlist_widget._items[index]['path']
        if self.playlist_widget.check_available_media(path):
            if self.playlist_widget.is_from_journal(path):
                path = self.playlist_widget.get_path_from_journal(path)
            self.control.check_if_next_prev()

            self.player.set_uri(path)
            self.player.play()
        else:
            self.songchange('next')

    def __play_index_cb(self, widget, index, path):
        # README: this line is no more necessary because of the
        # .playing_video() method
        # self._switch_canvas(show_video=True)
        self.playlist_widget.set_current_playing(index)

        if self.playlist_widget.is_from_journal(path):
            path = self.playlist_widget.get_path_from_journal(path)

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
        self.remove_alert(self._alert)
        self.playlist_widget.update()

    def __mount_removed_cb(self, volume_monitor, device):
        logging.debug('Mountpoint removed. Checking...')
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

        icon = Icon(icon_name='dialog-ok')
        self._alert.add_button(Gtk.ResponseType.APPLY, _('Details'), icon)
        self.add_alert(self._alert)
        self._alert.connect(
            'response', self.__missing_tracks_alert_response_cb, tracks)

    def __missing_tracks_alert_response_cb(self, alert, response_id, tracks):
        if response_id == Gtk.ResponseType.APPLY:
            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            vbox.props.valign = Gtk.Align.CENTER
            label = Gtk.Label(label='')
            label.set_markup(_('<b>Missing tracks</b>'))
            label.set_margin_bottom(15)
            vbox.append(label)

            for track in tracks:
                label = Gtk.Label(label=track['path'])
                vbox.append(label)

            _missing_tracks = Gtk.ScrolledWindow()
            _missing_tracks.set_child(vbox)

            self.view_area.append_page(_missing_tracks, None)

            self.view_area.set_current_page(2)

        self.remove_alert(alert)

    def _alert_cancel_cb(self, alert, response_id):
        self.remove_alert(alert)

    def __player_play_cb(self, widget):
        # Delay the video detection check to give GStreamer time to
        # parse stream metadata and discover video tracks
        GObject.timeout_add(500, self.__check_video_stream)

    def __check_video_stream(self):
        if self.player.playing_video():
            self._switch_canvas(True)
        else:
            # Audio-only: show the playlist instead of a blank video area
            self._switch_canvas(False)
            self._view_toolbar._show_playlist.props.active = True
        return False

    def __player_error_cb(self, widget, message, detail):
        self.player.stop()
        self.control.set_disabled()

        logging.error('ERROR MESSAGE: %s', message)
        logging.error('ERROR DETAIL: %s', detail)

        file_path = self.playlist_widget._items[
            self.playlist_widget.get_current_playing()]['path']
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
        logging.debug('JukeboxActivity.read_file: %s', file_path)

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
                self._playlist_jobject = \
                    self.playlist_widget.create_playlist_jobject()

            # Add the playlist to the playlist jobject description.
            # This is only done if the activity was not started from a
            # playlist or from scratch:
            description = ''
            for uri in self.playlist_widget._items:
                description += '%s\n' % uri['title']
            self._playlist_jobject.metadata['description'] = description

            write_playlist_to_file(self._playlist_jobject.file_path)
            datastore.write(self._playlist_jobject)

    def unfullscreen(self):
        activity.Activity.unfullscreen(self)
        if self._on_unfullscreen_show_playlist:
            self._view_toolbar._show_playlist.props.active = True

    def __go_fullscreen_cb(self, toolbar):
        if self._view_toolbar._show_playlist.props.active:
            self._view_toolbar._show_playlist.props.active = False
            self._on_unfullscreen_show_playlist = True
        self.fullscreen()

    def __toggle_playlist_cb(self, toolbar):
        if self._view_toolbar._show_playlist.props.active:
            self._playlist_box.show()
        else:
            self._playlist_box.hide()
        self._video_canvas.queue_draw()

    def _get_screen_size(self):
        display = Gdk.Display.get_default()
        if display:
            monitors = display.get_monitors()
            if monitors and monitors.get_n_items() > 0:
                monitor = monitors.get_item(0)
                geo = monitor.get_geometry()
                return geo.width, geo.height
        return 1200, 900
