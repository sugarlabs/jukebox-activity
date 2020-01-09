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

from gi.repository import Gst
from gi.repository import GObject

# Needed for window.get_xid(), xvimagesink.set_window_handle(),
# respectively:
from gi.repository import GdkX11, GstVideo

# Initialize GStreamer
Gst.init(None)


class GstPlayer(GObject.GObject):

    __gsignals__ = {
        'error': (GObject.SignalFlags.RUN_FIRST, None, [str, str]),
        'eos': (GObject.SignalFlags.RUN_FIRST, None, []),
        'play': (GObject.SignalFlags.RUN_FIRST, None, []),
    }

    def __init__(self):
        GObject.GObject.__init__(self)

        self.playing = False
        self.error = False

        # Create GStreamer pipeline
        self.pipeline = Gst.Pipeline()
        # Create bus to get events from GStreamer pipeline
        self.bus = self.pipeline.get_bus()
        self.bus.add_signal_watch()

        self.bus.connect('message::eos', self.__on_eos_message)
        self.bus.connect('message::error', self.__on_error_message)

        # This is needed to make the video output in our DrawingArea
        self.bus.enable_sync_message_emission()
        self.bus.connect('sync-message::element', self.__on_sync_message)

        # Create GStreamer elements
        self.player = Gst.ElementFactory.make('playbin', None)
        # FIXME: visualisation is in separate window
        self.player.props.flags |= 8
        self.pipeline.add(self.player)

    def init_view_area(self, videowidget):
        videowidget.realize()
        self.videowidget = videowidget
        self.videowidget_xid = videowidget.get_window().get_xid()

    def __on_error_message(self, bus, msg):
        self.stop()
        self.playing = False
        self.error = True
        err, debug = msg.parse_error()
        self.emit('error', err, debug)

    def __on_eos_message(self, bus, msg):
        logging.debug('SIGNAL: eos')
        self.playing = False
        self.emit('eos')

    def __on_sync_message(self, bus, msg):
        if msg.get_structure().get_name() == 'prepare-window-handle':
            msg.src.set_window_handle(self.videowidget_xid)

    def set_uri(self, uri):
        self.pipeline.set_state(Gst.State.READY)
        # gstreamer needs the 'file://' prefix
        uri = 'file://' + uri
        logging.debug('URI: %s', uri)
        self.player.set_property('uri', uri)

    def query_position(self):
        "Returns a (position, duration) tuple"

        p_success, position = self.player.query_position(Gst.Format.TIME)
        d_success, duration = self.player.query_duration(Gst.Format.TIME)

        return (p_success and d_success, position, duration)

    def seek(self, location):
        """
        @param location: time to seek to, in nanoseconds
        """

        logging.debug('Seek: %s ns', location)

        self.pipeline.seek_simple(Gst.Format.TIME,
                                  Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT,
                                  location)

    def pause(self):
        logging.debug("pausing player")
        self.pipeline.set_state(Gst.State.PAUSED)
        self.playing = False

    def play(self):
        logging.debug("playing player")
        self.pipeline.set_state(Gst.State.PLAYING)
        self.playing = True
        self.error = False
        self.emit('play')

    def stop(self):
        self.playing = False
        self.pipeline.set_state(Gst.State.NULL)
        logging.debug("stopped player")

    def get_state(self, timeout=1):
        return self.player.get_state(timeout=timeout)

    def is_playing(self):
        return self.playing

    def playing_video(self):
        return self.player.props.n_video > 0
