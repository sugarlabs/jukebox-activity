"""
 jukeboxactivity.py
 Activity that plays media.
 Copyright (C) 2007 Andy Wingo <wingo@pobox.com>
 Copyright (C) 2007 Red Hat, Inc.
"""

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
import os

from sugar.activity import activity

import pygtk
pygtk.require('2.0')

import sys

import gobject

import pygst
pygst.require('0.10')
import gst
import gst.interfaces
import gtk

import urllib

class JukeboxActivity(activity.Activity):
    UPDATE_INTERVAL = 500

    def __init__(self, handle):
        activity.Activity.__init__(self, handle)
        self.set_title(_('Jukebox Activity'))

        toolbox = activity.ActivityToolbox(self)
        self.set_toolbox(toolbox)
        toolbox.show()

        self.connect("shared", self._shared_cb)

        if handle.uri:
            pass
        elif self._shared_activity:
            if self.get_shared():
                pass
            else:
                # Wait for a successful join before trying to get the document
                self.connect("joined", self._joined_cb)

        self.update_id = -1
        self.changed_id = -1
        self.seek_timeout_id = -1

        self.p_position = gst.CLOCK_TIME_NONE
        self.p_duration = gst.CLOCK_TIME_NONE

        self.create_ui()
        self.player = GstPlayer(self.videowidget)

        def on_eos():
            self.player.seek(0L)
            self.play_toggled()
        self.player.on_eos = lambda *x: on_eos()

        self.show_all()

        if handle.uri:
            gobject.idle_add(self._start, handle.uri)

    def _joined_cb(self, activity):
        pass

    def _shared_cb(self, activity):
        pass

    def read_file(self, file_path):
        uri = "file://" + urllib.quote(os.path.abspath(file_path))
        gobject.idle_add(self._start, uri)

    def write_file(self, file_path):
        pass

    def _start(self, uri=None):
        if not uri:
            return False
        # FIXME: parse m3u files and extract actual URL
        self.player.set_uri(uri)
        self.play_toggled()
        return False

    def create_ui(self):
        vbox = gtk.VBox()
        self.set_canvas(vbox)

        self.videowidget = VideoWidget()
        vbox.pack_start(self.videowidget)
        
        hbox = gtk.HBox()
        vbox.pack_start(hbox, fill=False, expand=False)
        
        self.pause_image = gtk.image_new_from_stock(gtk.STOCK_MEDIA_PAUSE,
                                                    gtk.ICON_SIZE_BUTTON)
        self.pause_image.show()
        self.play_image = gtk.image_new_from_stock(gtk.STOCK_MEDIA_PLAY,
                                                   gtk.ICON_SIZE_BUTTON)
        self.play_image.show()
        self.button = button = gtk.Button()
        button.add(self.play_image)
        button.set_property('can-default', True)
        button.set_focus_on_click(False)
        button.show()
        hbox.pack_start(button, False)
        button.set_property('has-default', True)
        button.connect('clicked', lambda *args: self.play_toggled())
        
        self.adjustment = gtk.Adjustment(0.0, 0.00, 100.0, 0.1, 1.0, 1.0)
        hscale = gtk.HScale(self.adjustment)
        hscale.set_digits(2)
        hscale.set_update_policy(gtk.UPDATE_CONTINUOUS)
        hscale.connect('button-press-event', self.scale_button_press_cb)
        hscale.connect('button-release-event', self.scale_button_release_cb)
        hscale.connect('format-value', self.scale_format_value_cb)
        hbox.pack_start(hscale)
        self.hscale = hscale

    def play_toggled(self):
        self.button.remove(self.button.child)
        if self.player.is_playing():
            self.player.pause()
            self.button.add(self.play_image)
        else:
            self.player.play()
            if self.update_id == -1:
                self.update_id = gobject.timeout_add(self.UPDATE_INTERVAL,
                                                     self.update_scale_cb)
            self.button.add(self.pause_image)

    def scale_format_value_cb(self, scale, value):
        if self.p_duration == -1:
            real = 0
        else:
            real = value * self.p_duration / 100
        
        seconds = real / gst.SECOND

        return "%02d:%02d" % (seconds / 60, seconds % 60)

    def scale_button_press_cb(self, widget, event):
        # see seek.c:start_seek
        gst.debug('starting seek')
        
        self.button.set_sensitive(False)
        self.was_playing = self.player.is_playing()
        if self.was_playing:
            self.player.pause()

        # don't timeout-update position during seek
        if self.update_id != -1:
            gobject.source_remove(self.update_id)
            self.update_id = -1

        # make sure we get changed notifies
        if self.changed_id == -1:
            self.changed_id = self.hscale.connect('value-changed',
                self.scale_value_changed_cb)
            
    def scale_value_changed_cb(self, scale):
        # see seek.c:seek_cb
        real = long(scale.get_value() * self.p_duration / 100) # in ns
        gst.debug('value changed, perform seek to %r' % real)
        self.player.seek(real)
        # allow for a preroll
        self.player.get_state(timeout=50*gst.MSECOND) # 50 ms

    def scale_button_release_cb(self, widget, event):
        # see seek.cstop_seek
        widget.disconnect(self.changed_id)
        self.changed_id = -1

        self.button.set_sensitive(True)
        if self.seek_timeout_id != -1:
            gobject.source_remove(self.seek_timeout_id)
            self.seek_timeout_id = -1
        else:
            gst.debug('released slider, setting back to playing')
            if self.was_playing:
                self.player.play()

        if self.update_id != -1:
            self.error('Had a previous update timeout id')
        else:
            self.update_id = gobject.timeout_add(self.UPDATE_INTERVAL,
                self.update_scale_cb)

    def update_scale_cb(self):
        self.p_position, self.p_duration = self.player.query_position()
        if self.p_position != gst.CLOCK_TIME_NONE:
            value = self.p_position * 100.0 / self.p_duration
            self.adjustment.set_value(value)

        return True

class GstPlayer:
    def __init__(self, videowidget):
        self.playing = False
        self.player = gst.element_factory_make("playbin", "player")
        # FIXME: hook up to the 'error' signal of the playbin

        xvsink = gst.element_factory_make("xvimagesink", "xvimagesink")
        self.player.set_property("video-sink", xvsink)

        self.videowidget = videowidget
        self.on_eos = False

        bus = self.player.get_bus()
        bus.enable_sync_message_emission()
        bus.add_signal_watch()
        bus.connect('sync-message::element', self.on_sync_message)
        bus.connect('message', self.on_message)

    def set_uri(self, uri):
        self.player.set_property('uri', uri)

    def on_sync_message(self, bus, message):
        if message.structure is None:
            return
        if message.structure.get_name() == 'prepare-xwindow-id':
            self.videowidget.set_sink(message.src)
            message.src.set_property('force-aspect-ratio', True)
            
    def on_message(self, bus, message):
        t = message.type
        if t == gst.MESSAGE_ERROR:
            err, debug = message.parse_error()
            logging.debug("Error: %s - %s" % (err, debug))
            if self.on_eos:
                self.on_eos()
            self.playing = False
        elif t == gst.MESSAGE_EOS:
            if self.on_eos:
                self.on_eos()
            self.playing = False

    def query_position(self):
        "Returns a (position, duration) tuple"
        try:
            position, format = self.player.query_position(gst.FORMAT_TIME)
        except:
            position = gst.CLOCK_TIME_NONE

        try:
            duration, format = self.player.query_duration(gst.FORMAT_TIME)
        except:
            duration = gst.CLOCK_TIME_NONE

        return (position, duration)

    def seek(self, location):
        """
        @param location: time to seek to, in nanoseconds
        """
        gst.debug("seeking to %r" % location)
        event = gst.event_new_seek(1.0, gst.FORMAT_TIME,
            gst.SEEK_FLAG_FLUSH | gst.SEEK_FLAG_ACCURATE,
            gst.SEEK_TYPE_SET, location,
            gst.SEEK_TYPE_NONE, 0)

        res = self.player.send_event(event)
        if res:
            gst.info("setting new stream time to 0")
            self.player.set_new_stream_time(0L)
        else:
            gst.error("seek to %r failed" % location)

    def pause(self):
        gst.info("pausing player")
        self.player.set_state(gst.STATE_PAUSED)
        self.playing = False

    def play(self):
        gst.info("playing player")
        self.player.set_state(gst.STATE_PLAYING)
        self.playing = True
        
    def stop(self):
        self.player.set_state(gst.STATE_NULL)
        gst.info("stopped player")

    def get_state(self, timeout=1):
        return self.player.get_state(timeout=timeout)

    def is_playing(self):
        return self.playing
    
class VideoWidget(gtk.DrawingArea):
    def __init__(self):
        gtk.DrawingArea.__init__(self)
        self.imagesink = None
        self.unset_flags(gtk.DOUBLE_BUFFERED)

    def do_expose_event(self, event):
        if self.imagesink:
            self.imagesink.expose()
            return False
        else:
            return True

    def set_sink(self, sink):
        assert self.window.xid
        self.imagesink = sink
        self.imagesink.set_xwindow_id(self.window.xid)


