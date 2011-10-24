"""
 jukeboxactivity.py
 Activity that plays media.
 Copyright (C) 2007 Andy Wingo <wingo@pobox.com>
 Copyright (C) 2007 Red Hat, Inc.
 Copyright (C) 2008-2010 Kushal Das <kushal@fedoraproject.org>
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
from sugar.graphics.objectchooser import ObjectChooser
from sugar import mime

OLD_TOOLBAR = False
try:
    from sugar.graphics.toolbarbox import ToolbarBox
    from sugar.graphics.toolbarbox import ToolbarButton
    from sugar.activity.widgets import StopButton
except ImportError:
    OLD_TOOLBAR = True

from sugar.graphics.toolbutton import ToolButton
from sugar.graphics.xocolor import XoColor
from sugar import profile
from sugar.bundle.activitybundle import ActivityBundle
from sugar.graphics.icon import Icon

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
from ControlToolbar import Control, ViewToolbar
from ConfigParser import ConfigParser
cf = ConfigParser()


class JukeboxActivity(activity.Activity):
    UPDATE_INTERVAL = 500

    def __init__(self, handle):
        activity.Activity.__init__(self, handle)
        self._object_id = handle.object_id
        self.set_title(_('Jukebox Activity'))
        self.player = None

        if OLD_TOOLBAR:
            toolbox = activity.ActivityToolbox(self)
            self.set_toolbox(toolbox)
            toolbar = gtk.Toolbar()
            self.control = Control(toolbar, self)
            toolbox.add_toolbar(_('Play'), toolbar)

            toolbar.show()

            _view_toolbar = ViewToolbar()
            _view_toolbar.connect('go-fullscreen',
                    self.__go_fullscreen_cb)
            toolbox.add_toolbar(_('View'), _view_toolbar)
            _view_toolbar.show()

            toolbox.show()

            toolbox.connect("key_press_event", self._key_press_event_cb)

            toolbar.grab_focus()
            #self.connect("shared", self._shared_cb)
            activity_toolbar = toolbox.get_activity_toolbar()
            activity_toolbar.remove(activity_toolbar.share)
            activity_toolbar.share = None
            activity_toolbar.remove(activity_toolbar.keep)
            activity_toolbar.keep = None

        else:
            toolbar_box = ToolbarBox()
            activity_button = ToolButton()
            color = XoColor(profile.get_color())
            bundle = ActivityBundle(activity.get_bundle_path())
            icon = Icon(file=bundle.get_icon(), xo_color=color)
            activity_button.set_icon_widget(icon)
            activity_button.show()
            toolbar_box.toolbar.insert(activity_button, 0)

            _view_toolbar = ViewToolbar()
            _view_toolbar.connect('go-fullscreen',
                    self.__go_fullscreen_cb)
            view_toolbar_button = ToolbarButton(
                    page=_view_toolbar,
                    icon_name='toolbar-view')
            _view_toolbar.show()
            toolbar_box.toolbar.insert(view_toolbar_button, -1)
            view_toolbar_button.show()

            self.control = Control(toolbar_box.toolbar, self)

            separator = gtk.SeparatorToolItem()
            separator.props.draw = False
            separator.set_expand(True)
            toolbar_box.toolbar.insert(separator, -1)

            toolbar_box.toolbar.insert(StopButton(self), -1)

            self.set_toolbar_box(toolbar_box)
            toolbar_box.show_all()
            toolbar_box.connect("key_press_event", self._key_press_event_cb)

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
        self.player = None
        self.uri = None
        self.playlist = []
        self.jobjectlist = []
        self.playpath = None
        self.currentplaying = None
        self.playflag = False
        self.tags = {}
        self.only_audio = False
        self.got_stream_info = False

        self.p_position = gst.CLOCK_TIME_NONE
        self.p_duration = gst.CLOCK_TIME_NONE

        self.bin = gtk.HBox()
        self._empty_widget = gtk.Label("")
        self._empty_widget.show()
        self.videowidget = VideoWidget()
        self._switch_canvas(show_video=False)
        self.set_canvas(self.bin)
        self.show_all()
        #From ImageViewer Activity
        self._want_document = True
        if self._object_id is None:
            self._show_object_picker = gobject.timeout_add(1000, \
            self._show_picker_cb)

        if handle.uri:
            self.uri = handle.uri
            gobject.idle_add(self._start, self.uri)
            
    def _switch_canvas(self, show_video):
        """Show or hide the video visualization in the canvas.

        When hidden, the canvas is filled with an empty widget to
        ensure redrawing.

        """
        if show_video:
            self.bin.remove(self._empty_widget)
            self.bin.add(self.videowidget)
        else:
            self.bin.add(self._empty_widget)
            self.bin.remove(self.videowidget)
        self.bin.queue_draw()


    def open_button_clicked_cb(self, widget):
        """ To open the dialog to select a new file"""
        #self.player.seek(0L)
        #self.player.stop()
        #self.playlist = []
        #self.playpath = None
        #self.currentplaying = None
        #self.playflag = False
        self._want_document = True
        self._show_object_picker = gobject.timeout_add(1, self._show_picker_cb)


    def _key_press_event_cb(self, widget, event):
        keyname = gtk.gdk.keyval_name(event.keyval)
        logging.info ("Keyname Press: %s, time: %s", keyname, event.time)
        if keyname == "space":
            try:
                self.player.play_toggled()
            except:
                pass
    
    def check_if_next_prev(self):
        if self.currentplaying == 0:
            self.control.prev_button.set_sensitive(False)
        else:
            self.control.prev_button.set_sensitive(True)
        if self.currentplaying  == len(self.playlist) - 1:
            self.control.next_button.set_sensitive(False)
        else:
            self.control.next_button.set_sensitive(True)


    def songchange(self,direction):
        #if self.playflag:
        #    self.playflag = False
        #    return
        self.player.seek(0L)
        if direction == "prev" and self.currentplaying  > 0:
            self.currentplaying -= 1
            self.player.stop()
            self._switch_canvas(show_video=True)
            self.player = GstPlayer(self.videowidget)
            self.player.connect("error", self._player_error_cb)
            self.player.connect("tag", self._player_new_tag_cb)
            self.player.connect("stream-info", self._player_stream_info_cb)
            self.player.set_uri(self.playlist[self.currentplaying])
            logging.info("prev: " + self.playlist[self.currentplaying])
            #self.playflag = True
            self.play_toggled()
            self.player.connect("eos", self._player_eos_cb)
        elif direction == "next" and self.currentplaying  < len(self.playlist) - 1:
            self.currentplaying += 1
            self.player.stop()
            self._switch_canvas(show_video=True)
            self.player = GstPlayer(self.videowidget)
            self.player.connect("error", self._player_error_cb)
            self.player.connect("tag", self._player_new_tag_cb)
            self.player.connect("stream-info", self._player_stream_info_cb)
            self.player.set_uri(self.playlist[self.currentplaying])
            logging.info("NExt: " + self.playlist[self.currentplaying])
            #self.playflag = True
            self.play_toggled()
            self.player.connect("eos", self._player_eos_cb)
        else:
            self.play_toggled()
            self.player.stop()
            self._switch_canvas(show_video=False)
            self.player.set_uri(None)
        self.check_if_next_prev()


    def _player_eos_cb(self, widget):
        self.songchange('next')

    def _player_error_cb(self, widget, message, detail):
        self.player.stop()
        self.player.set_uri(None)
        self.control.set_disabled()
        self.bin.remove(self.videowidget)
        text = gtk.Label("Error: %s - %s" % (message, detail))
        text.show_all()
        self.bin.add(text)

    def _player_new_tag_cb(self, widget, tag, value):
        if not tag in [gst.TAG_TITLE, gst.TAG_ARTIST, gst.TAG_ALBUM]:
            return
        self.tags[tag] = value
        self._update_overlay()

    def _update_overlay(self):
        if self.only_audio == False:
            return
        if not self.tags.has_key(gst.TAG_TITLE) or not self.tags.has_key(gst.TAG_ARTIST):
            return
        album = None
        if self.tags.has_key(gst.TAG_ALBUM):
            album = self.tags[gst.TAG_ALBUM]
        self.player.set_overlay(self.tags[gst.TAG_TITLE], self.tags[gst.TAG_ARTIST], album)

    def _player_stream_info_cb(self, widget, stream_info):
        if not len(stream_info) or self.got_stream_info:
            return

        GST_STREAM_TYPE_UNKNOWN = 0
        GST_STREAM_TYPE_AUDIO   = 1
        GST_STREAM_TYPE_VIDEO   = 2
        GST_STREAM_TYPE_TEXT    = 3

        only_audio = True
        for item in stream_info:
            if item.props.type == GST_STREAM_TYPE_VIDEO:
                only_audio = False
        self.only_audio = only_audio
        self.got_stream_info = True
        self._update_overlay()

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

        chooser = ObjectChooser(_('Choose document'), self,
            gtk.DIALOG_MODAL |
            gtk.DIALOG_DESTROY_WITH_PARENT,
            what_filter=mime.GENERIC_TYPE_AUDIO)

        try:
            result = chooser.run()
            if result == gtk.RESPONSE_ACCEPT:
                jobject = chooser.get_selected_object()
                if jobject and jobject.file_path:
                    self.jobjectlist.append(jobject)
                    self._start(jobject.file_path)
        finally:
            #chooser.destroy()
            #del chooser
            pass

    def read_file(self, file_path):
        self.uri = os.path.abspath(file_path)
        if os.path.islink(self.uri):
            self.uri = os.path.realpath(self.uri)
        gobject.idle_add(self._start, self.uri)

    def getplaylist(self, links):
        result = []
        for x in links:
            if x.startswith('http://'):
                result.append(x)
            elif x.startswith('#'):
                continue
            else:
                result.append('file://' + urllib.quote(os.path.join(self.playpath,x)))
        return result

    def _start(self, uri=None):
        self._want_document = False
        self.playpath = os.path.dirname(uri)
        if not uri:
            return False
        # FIXME: parse m3u files and extract actual URL
        if uri.endswith(".m3u") or uri.endswith(".m3u8"):
            self.playlist.extend(self.getplaylist([line.strip() for line in open(uri).readlines()]))
        elif uri.endswith('.pls'):
            try:
                cf.readfp(open(uri))
                x = 1
                while True:
                    self.playlist.append(cf.get("playlist",'File'+str(x)))
                    x += 1
            except:
                #read complete
                pass
        else:
            self.playlist.append("file://" + urllib.quote(os.path.abspath(uri)))
        if not self.player:
            # lazy init the player so that videowidget is realized
            # and has a valid widget allocation
            self._switch_canvas(show_video=True)
            self.player = GstPlayer(self.videowidget)
            self.player.connect("eos", self._player_eos_cb)
            self.player.connect("error", self._player_error_cb)
            self.player.connect("tag", self._player_new_tag_cb)
            self.player.connect("stream-info", self._player_stream_info_cb)

        try:
            if not self.currentplaying:
                logging.info("Playing: " + self.playlist[0])
                self.player.set_uri(self.playlist[0])
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
        if self.player.is_playing():
            self.player.pause()
            self.control.set_button_play()
        else:
            if self.player.error:
                self.control.set_disabled()
            else:
                self.player.play()
                if self.update_id == -1:
                    self.update_id = gobject.timeout_add(self.UPDATE_INTERVAL,
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
            gobject.source_remove(self.update_id)
            self.update_id = -1

        # make sure we get changed notifies
        if self.changed_id == -1:
            self.changed_id = self.control.hscale.connect('value-changed',
                self.scale_value_changed_cb)

    def scale_value_changed_cb(self, scale):
        # see seek.c:seek_cb
        real = long(scale.get_value() * self.p_duration / 100) # in ns
        self.player.seek(real)
        # allow for a preroll
        self.player.get_state(timeout=50*gst.MSECOND) # 50 ms

    def scale_button_release_cb(self, widget, event):
        # see seek.cstop_seek
        widget.disconnect(self.changed_id)
        self.changed_id = -1

        self.control.button.set_sensitive(True)
        if self.seek_timeout_id != -1:
            gobject.source_remove(self.seek_timeout_id)
            self.seek_timeout_id = -1
        else:
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
            self.control.adjustment.set_value(value)

        return True

    def __go_fullscreen_cb(self, toolbar):
        self.fullscreen()


class GstPlayer(gobject.GObject):
    __gsignals__ = {
        'error': (gobject.SIGNAL_RUN_FIRST, None, [str, str]),
        'eos'  : (gobject.SIGNAL_RUN_FIRST, None, []),
        'tag'  : (gobject.SIGNAL_RUN_FIRST, None, [str, str]),
        'stream-info' : (gobject.SIGNAL_RUN_FIRST, None, [object])
    }

    def __init__(self, videowidget):
        gobject.GObject.__init__(self)

        self.playing = False
        self.error = False

        self.player = gst.element_factory_make("playbin", "player")

        r = gst.registry_get_default()
        l = [x for x in r.get_feature_list(gst.ElementFactory) if (gst.ElementFactory.get_klass(x) == "Visualization")]
        if len(l):
            e = l.pop() # take latest plugin in the list
            vis_plug = gst.element_factory_make(e.get_name())
            self.player.set_property('vis-plugin', vis_plug)

        self.overlay = None
        videowidget.realize()
        self.videowidget = videowidget
        self.videowidget_xid = videowidget.window.xid
        self._init_video_sink()

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
            self.videowidget.set_sink(message.src, self.videowidget_xid)
            message.src.set_property('force-aspect-ratio', True)
            
    def on_message(self, bus, message):
        t = message.type
        if t == gst.MESSAGE_ERROR:
            err, debug = message.parse_error()
            logging.debug("Error: %s - %s" % (err, debug))
            self.error = True
            self.emit("eos")
            self.playing = False
            self.emit("error", str(err), str(debug))
        elif t == gst.MESSAGE_EOS:
            self.emit("eos")
            self.playing = False
        elif t == gst.MESSAGE_TAG:
            tags = message.parse_tag()
            for tag in tags.keys():
                self.emit('tag', str(tag), str(tags[tag]))
        elif t == gst.MESSAGE_STATE_CHANGED:
            old, new, pen = message.parse_state_changed()
            if old == gst.STATE_READY and new == gst.STATE_PAUSED:
                self.emit('stream-info', self.player.props.stream_info_value_array)

    def _init_video_sink(self):
        self.bin = gst.Bin()
        videoscale = gst.element_factory_make('videoscale')
        self.bin.add(videoscale)
        pad = videoscale.get_pad("sink")
        ghostpad = gst.GhostPad("sink", pad)
        self.bin.add_pad(ghostpad)
        videoscale.set_property("method", 0)

        caps_string = "video/x-raw-yuv, "
        r = self.videowidget.get_allocation()
        if r.width > 500 and r.height > 500:
            # Sigh... xvimagesink on the XOs will scale the video to fit
            # but ximagesink in Xephyr does not.  So we live with unscaled
            # video in Xephyr so that the XO can work right.
            w = 480
            h = float(w) / float(float(r.width) / float(r.height))
            caps_string += "width=%d, height=%d" % (w, h)
        else:
            caps_string += "width=480, height=360"
        caps = gst.Caps(caps_string)
        self.filter = gst.element_factory_make("capsfilter", "filter")
        self.bin.add(self.filter)
        self.filter.set_property("caps", caps)

        textoverlay = gst.element_factory_make('textoverlay')
        self.overlay = textoverlay
        self.bin.add(textoverlay)
        conv = gst.element_factory_make ("ffmpegcolorspace", "conv");
        self.bin.add(conv)
        videosink = gst.element_factory_make('autovideosink')
        self.bin.add(videosink)
        gst.element_link_many(videoscale, self.filter, textoverlay, conv, videosink)
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
        event = gst.event_new_seek(1.0, gst.FORMAT_TIME,
            gst.SEEK_FLAG_FLUSH | gst.SEEK_FLAG_ACCURATE,
            gst.SEEK_TYPE_SET, location,
            gst.SEEK_TYPE_NONE, 0)

        res = self.player.send_event(event)
        if res:
            self.player.set_new_stream_time(0L)
        else:
            logging.debug("seek to %r failed" % location)

    def pause(self):
        logging.debug("pausing player")
        self.player.set_state(gst.STATE_PAUSED)
        self.playing = False

    def play(self):
        logging.debug("playing player")
        self.player.set_state(gst.STATE_PLAYING)
        self.playing = True
        self.error = False
        
    def stop(self):
        self.player.set_state(gst.STATE_NULL)
        logging.debug("stopped player")

    def get_state(self, timeout=1):
        return self.player.get_state(timeout=timeout)

    def is_playing(self):
        return self.playing
    
class VideoWidget(gtk.DrawingArea):
    def __init__(self):
        gtk.DrawingArea.__init__(self)
        self.set_events(gtk.gdk.POINTER_MOTION_MASK |
        gtk.gdk.POINTER_MOTION_HINT_MASK |
        gtk.gdk.EXPOSURE_MASK |
        gtk.gdk.KEY_PRESS_MASK |
        gtk.gdk.KEY_RELEASE_MASK) 
        self.imagesink = None
        self.unset_flags(gtk.DOUBLE_BUFFERED)
        self.set_flags(gtk.APP_PAINTABLE)

    def do_expose_event(self, event):
        if self.imagesink:
            self.imagesink.expose()
            return False
        else:
            return True

    def set_sink(self, sink, xid):
        self.imagesink = sink
        self.imagesink.set_xwindow_id(xid)



if __name__ == '__main__':
    window = gtk.Window()

    view = VideoWidget()

    #view.set_file_location(sys.argv[1])

    player = GstPlayer(view)
    #player.connect("eos", self._player_eos_cb)
    #player.connect("error", self._player_error_cb)
    #player.connect("tag", self._player_new_tag_cb)
    #player.connect("stream-info", self._player_stream_info_cb)

    window.add(view)

    player.set_uri('http://78.46.73.237:8000/prog')
    player.play()
    window.show_all()
    


    gtk.main()


