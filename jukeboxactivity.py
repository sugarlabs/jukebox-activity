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
from sugar.datastore import datastore

OLD_TOOLBAR = False
try:
    from sugar.graphics.toolbarbox import ToolbarBox
    from sugar.graphics.toolbarbox import ToolbarButton
    from sugar.activity.widgets import StopButton
    from sugar.activity.widgets import ActivityToolbarButton

except ImportError:
    OLD_TOOLBAR = True

import pygtk
pygtk.require('2.0')

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

from widgets import PlayListWidget

PLAYLIST_WIDTH_PROP = 1.0 / 3


class JukeboxActivity(activity.Activity):
    UPDATE_INTERVAL = 500

    def __init__(self, handle):
        activity.Activity.__init__(self, handle)
        self._object_id = handle.object_id
        self.set_title(_('Jukebox Activity'))
        self.player = None
        self.max_participants = 1

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
            _view_toolbar.connect('toggle-playlist',
                    self.__toggle_playlist_cb)
            toolbox.add_toolbar(_('View'), _view_toolbar)
            _view_toolbar.show()

            toolbox.show()

            toolbar.grab_focus()
            #self.connect("shared", self._shared_cb)
            activity_toolbar = toolbox.get_activity_toolbar()
            activity_toolbar.remove(activity_toolbar.share)
            activity_toolbar.share = None
            activity_toolbar.remove(activity_toolbar.keep)
            activity_toolbar.keep = None
            self.title_entry = activity_toolbar.title

        else:
            toolbar_box = ToolbarBox()
            activity_button = ActivityToolbarButton(self)
            activity_toolbar = activity_button.page
            toolbar_box.toolbar.insert(activity_button, 0)
            self.title_entry = activity_toolbar.title
            activity_toolbar.stop.hide()

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

            self.control = Control(toolbar_box.toolbar, self)

            separator = gtk.SeparatorToolItem()
            separator.props.draw = False
            separator.set_expand(True)
            toolbar_box.toolbar.insert(separator, -1)

            toolbar_box.toolbar.insert(StopButton(self), -1)

            self.set_toolbar_box(toolbar_box)
            toolbar_box.show_all()
        self.connect("key_press_event", self._key_press_event_cb)

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

        # {'url': 'file://.../media.ogg', 'title': 'My song', object_id: '..'}
        self.playlist = []

        self.jobjectlist = []
        self.playpath = None
        self.currentplaying = None
        self.playflag = False
        self.tags = {}
        self.only_audio = False
        self.got_stream_info = False

        self.tag_reader = TagReader()
        self.tag_reader.connect('get-tags', self.__get_tags_cb)

        self.p_position = gst.CLOCK_TIME_NONE
        self.p_duration = gst.CLOCK_TIME_NONE

        self.bin = gtk.HBox()
        self.bin.show()
        self.playlist_widget = PlayListWidget(self.play)
        self.playlist_widget.update(self.playlist)
        self.playlist_widget.show()
        self.bin.pack_start(self.playlist_widget, expand=False)
        self._empty_widget = gtk.Label("")
        self._empty_widget.show()
        self.videowidget = VideoWidget()
        self._switch_canvas(show_video=False)
        self.set_canvas(self.bin)
        self.show_all()
        self.bin.connect('size-allocate', self.__size_allocate_cb)

        #From ImageViewer Activity
        self._want_document = True
        if self._object_id is None:
            self._show_object_picker = gobject.timeout_add(1000, \
            self._show_picker_cb)

        if handle.uri:
            self.uri = handle.uri
            gobject.idle_add(self._start, self.uri, handle.title)

    def _switch_canvas(self, show_video):
        """Show or hide the video visualization in the canvas.

        When hidden, the canvas is filled with an empty widget to
        ensure redrawing.

        """
        if show_video:
            self.bin.remove(self._empty_widget)
            self.bin.pack_end(self.videowidget)
        else:
            self.bin.pack_end(self._empty_widget)
            self.bin.remove(self.videowidget)
        self.bin.queue_draw()

    def __get_tags_cb(self, tags_reader, order, tags):
        self.playlist[order]['title'] = tags['title']
        self.playlist_widget.update(self.playlist)

    def __size_allocate_cb(self, widget, allocation):
        canvas_size = self.bin.get_allocation()
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
        self._show_object_picker = gobject.timeout_add(1, self._show_picker_cb)

    def _key_press_event_cb(self, widget, event):
        keyname = gtk.gdk.keyval_name(event.keyval)
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
        self.player.stop()
        self.player = GstPlayer(self.videowidget)
        self.player.connect("eos", self._player_eos_cb)
        self.player.connect("error", self._player_error_cb)
        self.player.connect("tag", self._player_new_tag_cb)
        self.player.connect("stream-info", self._player_stream_info_cb)
        url = self.playlist[self.currentplaying]['url']
        if url.startswith('journal://'):
            jobject = datastore.get(url[len("journal://"):])
            url = 'file://' + jobject.file_path
        self.player.set_uri(url)

        self.play_toggled()

        self.check_if_next_prev()
        self.playlist_widget.set_cursor(self.currentplaying)

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
        if not gst.TAG_TITLE in self.tags or \
                not gst.TAG_ARTIST in self.tags:
            return
        album = None
        if gst.TAG_ALBUM in self.tags:
            album = self.tags[gst.TAG_ALBUM]
        self.player.set_overlay(self.tags[gst.TAG_TITLE],
                self.tags[gst.TAG_ARTIST], album)

    def _player_stream_info_cb(self, widget, stream_info):
        if not len(stream_info) or self.got_stream_info:
            return

        GST_STREAM_TYPE_UNKNOWN = 0
        GST_STREAM_TYPE_AUDIO = 1
        GST_STREAM_TYPE_VIDEO = 2
        GST_STREAM_TYPE_TEXT = 3

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
        logging.debug('JukeBoxAtivity.read_file: %s %s', file_path)
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
                gobject.idle_add(self._start, uri['url'], uri['title'],
                        uri['object_id'])
        else:
            # is another media file:
            gobject.idle_add(self._start, self.uri, title, object_id)

    def can_close(self):
        """Activities should override this function if they want to perform
        extra checks before actually closing."""
        if len(self.playlist) > 1 and \
                self.metadata['mime_type'] != 'audio/x-mpegurl':
            # if the activity started with a media file and added more later
            # need create a new file with the file list to no destroy
            # the first opened file
            logging.error('need new file')
            self._jobject = datastore.create()
            self.title_entry.set_text(_('Jukebox playlist'))
            self._jobject.metadata['title'] = _('Jukebox playlist')
            self._jobject.metadata['title_set_by_user'] = '1'
            description = ''
            for uri in self.playlist:
                description += '%s\n' % uri['title']
            self._jobject.metadata['description'] = description
            self._jobject.metadata['mime_type'] = 'audio/x-mpegurl'
            datastore.write(self._jobject)

        return True

    def write_file(self, file_path):
        if len(self.playlist) > 1:
            list_file = open(file_path, 'w')
            for uri in self.playlist:
                list_file.write('#EXTINF: %s\n' % uri['title'])
                list_file.write('%s\n' % uri['url'])
            list_file.close()

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
        if uri.endswith(title) or title is None or title == '' or \
                object_id is not None:
            logging.error('Try get a better title reading tags')
            # TODO: unify this code....
            url = self.playlist[len(self.playlist) - 1]['url']
            if url.find('home') > 0:
                url = url[len("journal://"):]
                url = 'file://' + url
            elif url.startswith('journal://'):
                jobject = datastore.get(url[len("journal://"):])
                url = 'file://' + jobject.file_path
                # jobject.destroy() ??
            self.tag_reader.set_file(url, len(self.playlist) - 1)

        if not self.player:
            # lazy init the player so that videowidget is realized
            # and has a valid widget allocation
            self._switch_canvas(show_video=True)
            self.player = GstPlayer(self.videowidget)
            self.player.connect("eos", self._player_eos_cb)
            self.player.connect("error", self._player_error_cb)
            self.player.connect("tag", self._player_new_tag_cb)
            self.player.connect("stream-info", self._player_stream_info_cb)

        self.playlist_widget.update(self.playlist)

        try:
            if not self.currentplaying:
                logging.info("Playing: " + self.playlist[0]['url'])
                url = self.playlist[0]['url']
                if url.startswith('journal://'):
                    jobject = datastore.get(url[len("journal://"):])
                    url = 'file://' + jobject.file_path

                self.player.set_uri(url)
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
        real = long(scale.get_value() * self.p_duration / 100)  # in ns
        self.player.seek(real)
        # allow for a preroll
        self.player.get_state(timeout=50 * gst.MSECOND)  # 50 ms

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

    def __toggle_playlist_cb(self, toolbar):
        if self.playlist_widget.get_visible():
            self.playlist_widget.hide()
        else:
            self.playlist_widget.show_all()
        self.bin.queue_draw()


class TagReader(gobject.GObject):

    __gsignals__ = {
        'get-tags': (gobject.SIGNAL_RUN_FIRST, None, [int, object]),
    }

    def __init__(self):
        gobject.GObject.__init__(self)
        #make a playbin to parse the audio file
        self.pbin = gst.element_factory_make('playbin', 'player')
        fakesink = gst.element_factory_make('fakesink', 'fakesink')
        self.pbin.set_property('video-sink', fakesink)
        #we need to receive signals from the playbin's bus
        self.bus = self.pbin.get_bus()
        #make sure we are watching the signals on the bus
        self.bus.add_signal_watch()
        #what do we do when a tag is part of the bus signal?
        self.bus.connect("message::tag", self.bus_message_tag)

    def bus_message_tag(self, bus, message):
        #we received a tag message
        taglist = message.parse_tag()
        #put the keys in the dictionary
        tags = {}
        for key in taglist.keys():
            tags[key] = taglist[key]
        logging.error('bus_message_tag %s', tags)
        if 'title' in tags:
            self.emit('get-tags', self._order, tags)

    def set_file(self, url, order):
        logging.error('tag_reader url = %s order = %d', url, order)
        self._order = order
        self.pbin.set_state(gst.STATE_NULL)
        #set the uri of the playbin to our audio file
        self.pbin.set_property('uri', url)
        #pause the playbin, we don't really need to play
        self.pbin.set_state(gst.STATE_PAUSED)


class GstPlayer(gobject.GObject):

    __gsignals__ = {
        'error': (gobject.SIGNAL_RUN_FIRST, None, [str, str]),
        'eos': (gobject.SIGNAL_RUN_FIRST, None, []),
        'tag': (gobject.SIGNAL_RUN_FIRST, None, [str, str]),
        'stream-info': (gobject.SIGNAL_RUN_FIRST, None, [object])
    }

    def __init__(self, videowidget):
        gobject.GObject.__init__(self)

        self.playing = False
        self.error = False

        self.player = gst.element_factory_make("playbin", "player")

        r = gst.registry_get_default()
        l = [x for x in r.get_feature_list(gst.ElementFactory)
                if (gst.ElementFactory.get_klass(x) == "Visualization")]
        if len(l):
            e = l.pop()  # take latest plugin in the list
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
                self.emit('stream-info',
                        self.player.props.stream_info_value_array)

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
        conv = gst.element_factory_make("ffmpegcolorspace", "conv")
        self.bin.add(conv)
        videosink = gst.element_factory_make('autovideosink')
        self.bin.add(videosink)
        gst.element_link_many(videoscale, self.filter, textoverlay, conv,
                videosink)
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
