import sys

def is_python3():
    return sys.version_info >= (3,0)

if is_python3():
    import http.server as SimpleHTTPServer
    import socketserver as SocketServer
    from io import StringIO
    
else:
    import SimpleHTTPServer
    import SocketServer
    
    try:
        from cStringIO import StringIO
    except ImportError:
        from StringIO import StringIO

from io import BytesIO
import os
import os
import posixpath
import urllib
import cgi
import shutil
import mimetypes
import signal
import hashlib
import re
import time
import logging
import json
import threading
from shutil import copyfile


f = open(os.path.join(os.getcwd(), "GhettoDropbox/config.json"),"r")
config = json.load(f)
f.close()

port = config["port"]
ip = str(config["ip"])
use_watchdog = True
if "simplewatcher" in config:
    use_watchdog = not config["simplewatcher"]

print("Using watchdog", use_watchdog)

if use_watchdog:
    from watchdog.observers import Observer
    from watchdog.events import LoggingEventHandler
    from watchdog.events import FileSystemEventHandler
    
shares_data_file_path = os.path.join(os.getcwd(), "GhettoDropbox/shares_data.txt")
shares_file_path = os.path.join(os.getcwd(), "GhettoDropbox/shares.txt")

hash_pattern = re.compile('^\/([^\/]*)\/(.*)$')
share_hash = {}




def unquote(path):
    if is_python3():
        return posixpath.normpath(urllib.parse.unquote(path))
    else:
        return posixpath.normpath(urllib.unquote(path))
        
def quote(path):
    if is_python3():
        return posixpath.normpath(urllib.parse.quote(path))
    else:
        return posixpath.normpath(urllib.quote(path))


def create_hash(path):
    hexdigest = hashlib.sha224(path.encode('utf-8')).hexdigest()
    return hexdigest[0:16]

def update_shares(first_run = False):
    share_hash.clear()

    initial_shares = []
    f_shares = open(shares_file_path, "r")
    for line in f_shares:
        line = line.strip('\n')
        initial_shares.append(line)

    f_shares.close()

    f_shares_data = open(shares_data_file_path, "r")
    for line in f_shares_data:
        print("line in shares data", line)
        line = line.strip('\n')
        linedata = line.split(',')
        share_path = linedata[0].strip(' ')
        share_path_hash = linedata[1].strip(' ')
        share_hash[share_path_hash] = share_path

    for share_path in initial_shares:
        if share_path not in share_hash.values():
            key = create_hash(share_path)
            share_hash[key] = share_path
            print("added new share: ", share_path, key)
    
    if not first_run:
        pop_list = []
        for key, value in share_hash.items():
            if value not in initial_shares:
                pop_list.append(key)

        for key in pop_list:
            share_hash.pop(key)
            print("removed share: ", key)
        first_run = False

    f_shares_data.close()
    f_shares_data = open(shares_data_file_path, "w")

    for key, value in share_hash.items():
        print("key", key)
        f_shares_data.write(value)
        f_shares_data.write(", ")
        f_shares_data.write(key)
        f_shares_data.write(", ")
        f_shares_data.write("http://" + ip + ":" + str(port) + "/" + key)
        f_shares_data.write("\n")

    f_shares_data.close()

    for key in share_hash:
        print("share hash: ", key, "=", share_hash[key])





class MyRequestHandler(SimpleHTTPServer.SimpleHTTPRequestHandler):
    def list_directory(self, path):
        """Helper to produce a directory listing (absent index.html).
        Return value is either a file object, or None (indicating an
        error).  In either case, the headers are sent, making the
        interface the same as for send_head().
        """
        
        print("listing directory for:", path)
        try:
            list = os.listdir(path)
        except os.error:
            self.send_error(404, "No permission to list directory")
            return None
        list.sort(key=lambda a: a.lower())
        f = BytesIO()
        
        displaypath = cgi.escape(unquote(self.path))
        s = ""
        s += '<!DOCTYPE html PUBLIC "-//W3C//DTD HTML 3.2 Final//EN">' + "\n"
        s += "<html>\n<title>Directory listing for %s</title>\n" % displaypath
        s += "<body>\n<h2>Directory listing for %s</h2>\n" % displaypath
        s += "<hr>\n<ul>\n"
        
        for name in list:
            fullname = os.path.join(path, name)
            displayname = linkname = name
            # Append / for directories or @ for symbolic links
            if os.path.isdir(fullname):
                displayname = name + "/"
                linkname = name + "/"
            if os.path.islink(fullname):
                displayname = name + "@"
                # Note: a link to a directory displays with @ and links with /
            s += '<li><a href="%s">%s</a>\n' % (quote(linkname), cgi.escape(displayname))
            s += "</ul>\n<hr>\n</body>\n</html>\n"
        f.write(s.encode('utf-8'))
        length = f.tell()
        f.seek(0)
        self.send_response(200)
        encoding = sys.getfilesystemencoding()
        self.send_header("Content-type", "text/html; charset=%s" % encoding)
        self.send_header("Content-Length", str(length))
        self.end_headers()
        return f


    def send_head(self):
        """Common code for GET and HEAD commands.
        This sends the response code and MIME headers.
        Return value is either a file object (which has to be copied
        to the outputfile by the caller unless the command was HEAD,
        and must be closed by the caller under all circumstances), or
        None, in which case the caller has nothing further to do.
        """
        print("path printing self.path send head!!!", self.path)
        path = self.translate_path(self.path)
        f = None
        if os.path.isdir(path):
            if not self.path.endswith('/'):
                # redirect browser - doing basically what apache does
                self.send_response(301)
                self.send_header("Location", self.path + "/")
                self.end_headers()
                return None
            for index in "index.html", "index.htm":
                index = os.path.join(path, index)
                if os.path.exists(index):
                    path = index
                    break
            else:
                return self.list_directory(path)
        ctype = self.guess_type(path)
        try:
            # Always read in binary mode. Opening files in text mode may cause
            # newline translations, making the actual size of the content
            # transmitted *less* than the content-length!
            f = open(path, 'rb')
        except IOError:
            print("sending 404")
            print(path, "path")
            self.send_error(404, "File not found")
            return None
        self.send_response(200)
        self.send_header("Content-type", ctype)
        fs = os.fstat(f.fileno())
        self.send_header("Content-Length", str(fs[6]))
        self.send_header("Last-Modified", self.date_time_string(fs.st_mtime))
        self.end_headers()
        return f
        
    def do_GET(self):
        """Serve a GET request."""
        print("path printing!!!", self.path)
        f = self.send_head()
        print("f", f)
        if f:
            self.copyfile(f, self.wfile)
            f.close()

    def translate_path(self, path):
        """Translate a /-separated PATH to the local filename syntax.
        Components that mean special things to the local file system
        (e.g. drive or directory names) are ignored.  (XXX They should
        probably be diagnosed.)
        """

        print("translating path", path)
        # abandon query parameters
        path = path.split('?',1)[0]
        path = path.split('#',1)[0]
        
        path = unquote(path)
            
        words = path.split('/')
        words = filter(None, words)
        path = ""
        i = 0
        for word in words:
            #if word in (os.curdir, os.pardir): continue
            if i==0:
                print("share hash contains", share_hash)
                if word in share_hash:
                    word = share_hash[word]
                else:
                    return "404ErrorNonsense"
            path = os.path.join(path, word)

            i+=1
        print("second fild path", path)

        final_path = os.path.join(os.getcwd(), path)
        print(final_path)
        return final_path

logging.basicConfig(level=logging.INFO,
    format='%(asctime)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S')
path = os.path.join(os.getcwd(), "GhettoDropbox")
observer = None
logging_event_handler = None
update_shares_event_handler = None
update_shares(True)
if use_watchdog:
    class UpdateSharesEventHandler(FileSystemEventHandler):
        def on_modified(self, event):
            if "shares.txt" in event.src_path:
                print("detected change and updating the shares")
                update_shares()
                
    update_shares_event_handler = UpdateSharesEventHandler()
    logging_event_handler = LoggingEventHandler()
    observer = Observer()
    observer.schedule(logging_event_handler, path, recursive=False)
    observer.schedule(update_shares_event_handler, path, recursive=False)
    observer.start()
else:
    class UpdateSharesEventHandler():
        def on_modified(self, filepath):
            if "shares.txt" in filepath:
                print("detected change and updating the shares")
                update_shares()
                
    class WatchedFile():
        def __init__(self, filepath):
            self.filepath = filepath
            self.set_lastmd5(self.calcmd5())
            
        def calcmd5(self):
            f = open(self.filepath, 'rb')
            md5 = hashlib.md5(f.read()).hexdigest()
            f.close()
            return md5
            
        def set_lastmd5(self, lastmd5):
            self.lastmd5 = lastmd5
            
            
    class PollingFileObserver(object):
        def __init__(self):
            self.watched_files = {}
            self.file_event_handlers = []
            self.thread = threading.Thread(target=self.observe)
            self.stop_now = False
        
        def add_file_event_handler(self, handler):
            self.file_event_handlers.append(handler)
        
        def add_watched_file(self, filepath):
            self.watched_files[filepath] = WatchedFile(filepath)
        
        def remove_watched_file(self, filepath):
            del self.watched_files[filepath]
        
        def stop(self):
            self.stop_now = True
            self.thread.join()
            
        def observe(self):
            while True:
                if self.stop_now:
                    return
                time.sleep(2)
                for f in self.watched_files:
                    watched_file = self.watched_files[f]
                    newmd5 = watched_file.calcmd5()
                    if watched_file.lastmd5 != newmd5:
                        self.file_modified_trigger(watched_file.filepath)
                        watched_file.set_lastmd5(newmd5)
                        
        def start(self):
            self.thread.start()
        
        def file_modified_trigger(self, filepath):
            for handler in self.file_event_handlers:
                handler.on_modified(filepath)
                
    observer = PollingFileObserver()
    update_shares_event_handler = UpdateSharesEventHandler()
    observer.add_file_event_handler(update_shares_event_handler)
    observer.add_watched_file(shares_file_path)
    observer.add_watched_file(shares_data_file_path)
    observer.start()

Handler = MyRequestHandler
SocketServer.TCPServer.allow_reuse_address = True
httpd = SocketServer.TCPServer(("", port), Handler)

def signal_handler(signal, frame):
        # close the socket here
        httpd.server_close()
        observer.stop()
        sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

print("serving at port", port)
try:
    httpd.serve_forever()
except:
    print("Closing the server.")
    httpd.server_close()
    observer.stop()
    raise

