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

import logging

from gi.repository import Gtk
from gi.repository import Gst
from gi.repository import GObject

from gettext import gettext as _

from sugar4.graphics.toolbutton import ToolButton
from sugar4.graphics.objectchooser import ObjectChooser
from sugar4.graphics import style
from sugar4.graphics.icon import Icon


class Controls(GObject.GObject):
    """Class to create the Control (play, back, forward,
    add, remove, etc) toolbar"""

    SCALE_UPDATE_INTERVAL = 1000
    SCALE_DURATION_TEXT = 100

    def __init__(self, activity, main_toolbar, secondary_toolbar):
        GObject.GObject.__init__(self)

        self.activity = activity
        self.toolbar = main_toolbar
        self.secondary_toolbar = secondary_toolbar

        self._scale_update_id = -1

        self.open_button = ToolButton('list-add')
        self.open_button.set_tooltip(_('Add track'))
        self.open_button.connect('clicked', self.__open_button_clicked_cb)
        self.toolbar.append(self.open_button)

        erase_playlist_entry_btn = ToolButton(icon_name='list-remove')
        erase_playlist_entry_btn.set_tooltip(_('Remove track'))
        erase_playlist_entry_btn.connect(
            'clicked', self.__erase_playlist_entry_clicked_cb)
        self.toolbar.append(erase_playlist_entry_btn)

        self._spacer = Gtk.Separator()
        self._spacer.set_hexpand(False)
        self.toolbar.append(self._spacer)

        self.prev_button = ToolButton('player_rew')
        self.prev_button.set_tooltip(_('Previous'))
        self.prev_button.set_accelerator('Up')
        self.prev_button.connect('clicked', self.__prev_button_clicked_cb)
        self.toolbar.append(self.prev_button)

        self.button = ToolButton('media-playback-start')
        self.button.set_tooltip(_('Play or Pause'))
        self.button.set_accelerator('space')
        self.button.connect('clicked', self._button_clicked_cb)

        self.toolbar.append(self.button)

        self.next_button = ToolButton('player_fwd')
        self.next_button.set_tooltip(_('Next'))
        self.next_button.set_accelerator('Down')
        self.next_button.connect('clicked', self.__next_button_clicked_cb)
        self.toolbar.append(self.next_button)

        self._current_time = Gtk.Box()
        self.current_time_label = Gtk.Label(label='')
        self._current_time.append(self.current_time_label)
        self.toolbar.append(self._current_time)

        self.adjustment = Gtk.Adjustment(
            value=0.0,
            lower=0.0,
            upper=100.0,
            step_increment=0.1,
            page_increment=1.0,
            page_size=1.0)
        self.hscale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL,
                                adjustment=self.adjustment)
        self.hscale.set_draw_value(False)

        # Use change-value signal for reliable user-seek detection in GTK4
        self._user_seeking = False
        self._seek_settle_id = -1
        self.hscale.connect('change-value', self.__scale_change_value_cb)

        self.scale_item = Gtk.Box()
        self.scale_item.set_hexpand(True)
        self.hscale.set_hexpand(True)
        self.scale_item.append(self.hscale)
        self.toolbar.append(self.scale_item)

        self._total_time = Gtk.Box()
        self.total_time_label = Gtk.Label(label='')
        self._total_time.append(self.total_time_label)
        self.toolbar.append(self._total_time)

        self.activity.connect('playlist-finished', self.__playlist_finished_cb)
        self.activity.player.connect('play', self.__player_play)

    def update_layout(self, landscape=True):
        controls = [
            self._spacer,
            self.prev_button,
            self.button,
            self.next_button,
            self._current_time,
            self.scale_item,
            self._total_time]

        if landscape:
            toolbar = self.toolbar
        else:
            toolbar = self.secondary_toolbar

        for control in controls:
            if control is not None:
                if control.get_parent():
                    control.get_parent().remove(control)
                toolbar.append(control)
                control.set_visible(True)

        # The spacer is only shown in landscape mode (original GTK3 behavior)
        self._spacer.set_visible(landscape)

    def __player_play(self, widget):
        if self._scale_update_id == -1:
            self._scale_update_id = GObject.timeout_add(
                self.SCALE_UPDATE_INTERVAL, self.__update_scale_cb)

        # We need to wait for GstPlayer to load the stream's duration
        GObject.timeout_add(self.SCALE_DURATION_TEXT,
                            self.__set_scale_duration)

        self.set_enabled()
        self.set_button_pause()

    def __set_scale_duration(self):
        success, self.p_position, self.p_duration = \
            self.activity.player.query_position()

        if success and self.p_duration != Gst.CLOCK_TIME_NONE:
            seconds = self.p_duration * 10 ** -9
            time = '%2d:%02d' % (int(seconds / 60), int(seconds % 60))
            self.total_time_label.set_text(time)
            # Once we set the total_time we don't need to change it
            # until a new stream is played
            return False
        else:
            # We don't have the stream's duration yet, we need to call
            # this method again
            return True

    def __open_button_clicked_cb(self, widget):
        self.show_picker_cb()

    def __erase_playlist_entry_clicked_cb(self, widget):
        deleted_playing = self.activity.playlist_widget.delete_selected_items()
        if deleted_playing:
            self.activity.emit('playlist-finished')
        self.check_if_next_prev()

    def show_picker_cb(self, button=None):
        chooser = ObjectChooser(self.activity, what_filter='Audio',
                                filter_type=None,
                                show_preview=True)
        result = chooser.run()
        if result == Gtk.ResponseType.ACCEPT:
            jobject = chooser.get_selected_object()
            if jobject and jobject.file_path:
                try:
                    logging.debug('ObjectChooser.file_path: %s',
                                  jobject.file_path)
                    self.activity.playlist_widget.load_file(jobject)
                    self.check_if_next_prev()
                    self.activity._switch_canvas(False)
                    self.activity._view_toolbar._show_playlist.props.active = \
                        True
                finally:
                    jobject.destroy()
        chooser.destroy()

    def __prev_button_clicked_cb(self, widget):
        self.activity.songchange('prev')

    def __next_button_clicked_cb(self, widget):
        self.activity.songchange('next')

    def check_if_next_prev(self):
        current_playing = self.activity.playlist_widget.get_current_playing()
        if len(self.activity.playlist_widget._items) == 0:
            # There is no media in the playlist
            self.prev_button.set_sensitive(False)
            self.button.set_sensitive(False)
            self.next_button.set_sensitive(False)
            self.hscale.set_sensitive(False)
            self.activity._view_toolbar._fullscreen.set_sensitive(False)
        else:
            self.button.set_sensitive(True)
            self.hscale.set_sensitive(True)
            self.activity._view_toolbar._fullscreen.set_sensitive(True)

            if current_playing == 0:
                self.prev_button.set_sensitive(False)
            else:
                self.prev_button.set_sensitive(True)

            items = len(self.activity.playlist_widget._items)
            if current_playing == items - 1:
                self.next_button.set_sensitive(False)
            else:
                self.next_button.set_sensitive(True)

    def _button_clicked_cb(self, widget):
        self.set_enabled()

        if self.activity.player.is_playing():
            self.activity.player.pause()
            self.set_button_play()
            if self._scale_update_id != -1:
                GObject.source_remove(self._scale_update_id)
                self._scale_update_id = -1
        else:
            if self.activity.player.error:
                self.set_disabled()
            else:
                if self.activity.player.player.props.current_uri is None:
                    # There is no stream selected to be played
                    # yet. Select the first one
                    available = self.activity.playlist_widget.\
                        _items[0]['available']
                    if available:
                        path = self.activity.playlist_widget._items[0]['path']
                        self.activity.playlist_widget.emit(
                            'play-index', 0, path)
                        self.activity.playlist_widget.set_current_playing(0)
                else:
                    self.activity.player.play()
                    self.activity._switch_canvas(True)
                    self._scale_update_id = GObject.timeout_add(
                        self.SCALE_UPDATE_INTERVAL, self.__update_scale_cb)

    def set_button_play(self):
        self.button.set_icon_name('media-playback-start')

    def set_button_pause(self):
        self.button.set_icon_name('media-playback-pause')

    def set_disabled(self):
        self.button.set_sensitive(False)
        self.scale_item.set_sensitive(False)
        self.hscale.set_sensitive(False)

    def set_enabled(self):
        self.button.set_sensitive(True)
        self.scale_item.set_sensitive(True)
        self.hscale.set_sensitive(True)

    def __scale_change_value_cb(self, scale, scroll_type, value):
        """Called when the user interacts with the slider."""
        self._user_seeking = True
        self._pending_seek_value = value

        # Cancel any previous seek/settle timeout
        if self._seek_settle_id != -1:
            GObject.source_remove(self._seek_settle_id)

        # Debounce: only actually seek after 100ms of no new drag events
        # This lets the Scale thumb follow the cursor smoothly
        self._seek_settle_id = GObject.timeout_add(
            100, self._do_seek)

        return False  # let the Scale update its visual position immediately

    def _do_seek(self):
        """Debounced seek — fires 100ms after last drag movement."""
        self._seek_settle_id = -1
        if self._pending_seek_value is not None and \
                self.p_duration and self.p_duration != Gst.CLOCK_TIME_NONE:
            location = int(self._pending_seek_value * self.p_duration / 100)
            self.activity.player.seek(location)
        self._pending_seek_value = None
        # Keep _user_seeking True — it will be cleared by the settle timeout
        # Set a new settle timeout to clear the flag after seeking stops
        self._seek_settle_id = GObject.timeout_add(
            300, self._seek_settled)
        return False

    def _seek_settled(self):
        """Called after user stops dragging the slider."""
        self._seek_settle_id = -1
        self._user_seeking = False
        return False

    def __update_scale_cb(self):
        # Don't overwrite the slider value while the user is seeking
        if self._user_seeking:
            return True

        success, self.p_position, self.p_duration = \
            self.activity.player.query_position()

        if success and self.p_position != Gst.CLOCK_TIME_NONE:
            value = self.p_position * 100.0 / self.p_duration
            self.adjustment.set_value(value)

            # Update the current time
            seconds = self.p_position * 10 ** -9
            time = '%2d:%02d' % (int(seconds / 60), int(seconds % 60))
            self.current_time_label.set_text(time)

        return True

    def __playlist_finished_cb(self, widget):
        self.activity.player.stop()
        self.set_button_play()
        self.check_if_next_prev()

        self.adjustment.set_value(0)
        self.current_time_label.set_text('')
        self.total_time_label.set_text('')
