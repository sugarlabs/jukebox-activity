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

# Copyright (C) 2013 Manuel Kaufmann <humitos@gmail.com>

import logging

from gi.repository import Gst
from gi.repository import GObject

# Needed for window.get_xid(), xvimagesink.set_window_handle(),
# respectively:
from gi.repository import GdkX11, GstVideo

# Avoid "Fatal Python error: GC object already tracked"
# http://stackoverflow.com/questions/7496629/gstreamer-appsrc-causes-random-crashes
# GObject.threads_init()

# Initialize GStreamer
Gst.init(None)


class GstPlayer(GObject.GObject):

    __gsignals__ = {
        'error': (GObject.SignalFlags.RUN_FIRST, None, [str, str]),
        'eos': (GObject.SignalFlags.RUN_FIRST, None, []),
    }

    def __init__(self, videowidget):
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
        self.pipeline.add(self.player)

        # Set the proper flags to render the vis-plugin
        GST_PLAY_FLAG_VIS = 1 << 3
        GST_PLAY_FLAG_TEXT = 1 << 2
        self.player.props.flags |= GST_PLAY_FLAG_VIS
        self.player.props.flags |= GST_PLAY_FLAG_TEXT

        r = Gst.Registry.get()
        l = [x for x in r.get_feature_list(Gst.ElementFactory)
             if (x.get_metadata('klass') == "Visualization")]
        if len(l):
            e = l.pop()  # take latest plugin in the list
            vis_plug = Gst.ElementFactory.make(e.get_name(), e.get_name())
            self.player.set_property('vis-plugin', vis_plug)

        self.overlay = None
        videowidget.realize()
        self.videowidget = videowidget
        self.videowidget_xid = videowidget.get_window().get_xid()
        self._init_video_sink()

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
        logging.debug('### Setting URI: %s', uri)
        self.player.set_property('uri', uri)

    def _init_video_sink(self):
        self.bin = Gst.Bin()
        videoscale = Gst.ElementFactory.make('videoscale', 'videoscale')
        self.bin.add(videoscale)
        pad = videoscale.get_static_pad("sink")
        ghostpad = Gst.GhostPad.new("sink", pad)
        self.bin.add_pad(ghostpad)
        videoscale.set_property("method", 0)

        textoverlay = Gst.ElementFactory.make('textoverlay', 'textoverlay')
        self.overlay = textoverlay
        self.bin.add(textoverlay)
        conv = Gst.ElementFactory.make("videoconvert", "conv")
        self.bin.add(conv)
        videosink = Gst.ElementFactory.make('autovideosink', 'autovideosink')
        self.bin.add(videosink)

        videoscale.link(textoverlay)
        textoverlay.link(conv)
        conv.link(videosink)

        self.player.set_property("video-sink", self.bin)

    def set_overlay(self, title, artist, album):
        text = "%s\n%s" % (title, artist)
        if album and len(album):
            text += "\n%s" % album
        self.overlay.set_property("text", text)
        self.overlay.set_property("font-desc", "sans bold 14")
        self.overlay.set_property("halignment", "right")
        self.overlay.set_property("valignment", "bottom")
        try:
            # Only in OLPC versions of gstreamer-plugins-base for now
            self.overlay.set_property("line-align", "left")
        except:
            pass

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
