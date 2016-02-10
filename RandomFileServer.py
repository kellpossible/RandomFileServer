import SimpleHTTPServer
import SocketServer
import os
import os
import posixpath
import BaseHTTPServer
import urllib
import cgi
import sys
import shutil
import mimetypes
import signal
import hashlib
import re
import time
import logging
from watchdog.observers import Observer
from watchdog.events import LoggingEventHandler
from watchdog.events import FileSystemEventHandler
import json

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

f = open(os.path.join(os.getcwd(), "GhettoDropbox/config.json"),"r")
config = json.load(f)
f.close()

port = config["port"]
ip = str(config["ip"])

shares_data_file_path = os.path.join(os.getcwd(), "GhettoDropbox/shares_data.txt")
shares_file_path = os.path.join(os.getcwd(), "GhettoDropbox/shares.txt")

hash_pattern = re.compile('^\/([^\/]*)\/(.*)$')
share_hash = {}



def create_hash(path):
    hexdigest = hashlib.sha224(path).hexdigest()
    return hexdigest[0:16]

def update_shares():
    share_hash.clear()

    initial_shares = []
    f_shares = open(shares_file_path, "r")
    for line in f_shares:
        line = line.strip('\n')
        initial_shares.append(line)

    f_shares.close()

    f_shares_data = open(shares_data_file_path, "r")
    for line in f_shares_data:
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

    pop_list = []
    for key, value in share_hash.iteritems():
        if value not in initial_shares:
            pop_list.append(key)

    for key in pop_list:
        share_hash.pop(key)
        print("removed share: ", key)

    f_shares_data.close()
    f_shares_data = open(shares_data_file_path, "w")

    for key, value in share_hash.iteritems():
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
        try:
            list = os.listdir(path)
        except os.error:
            self.send_error(404, "No permission to list directory")
            return None
        list.sort(key=lambda a: a.lower())
        f = StringIO()
        displaypath = cgi.escape(urllib.unquote(self.path))
        f.write('<!DOCTYPE html PUBLIC "-//W3C//DTD HTML 3.2 Final//EN">')
        f.write("<html>\n<title>Directory listing for %s</title>\n" % displaypath)
        f.write("<body>\n<h2>Directory listing for %s</h2>\n" % displaypath)
        f.write("<hr>\n<ul>\n")
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
            f.write('<li><a href="%s">%s</a>\n'
                    % (urllib.quote(linkname), cgi.escape(displayname)))
        f.write("</ul>\n<hr>\n</body>\n</html>\n")
        length = f.tell()
        f.seek(0)
        self.send_response(200)
        encoding = sys.getfilesystemencoding()
        self.send_header("Content-type", "text/html; charset=%s" % encoding)
        self.send_header("Content-Length", str(length))
        self.end_headers()
        return f

    def do_GET(self):
        """Serve a GET request."""
        print("path printing!!!", self.path)
        f = self.send_head()
        if f:
            self.copyfile(f, self.wfile)
            f.close()

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
            self.send_error(404, "File not found")
            return None
        self.send_response(200)
        self.send_header("Content-type", ctype)
        fs = os.fstat(f.fileno())
        self.send_header("Content-Length", str(fs[6]))
        self.send_header("Last-Modified", self.date_time_string(fs.st_mtime))
        self.end_headers()
        return f

    def translate_path(self, path):
        """Translate a /-separated PATH to the local filename syntax.
        Components that mean special things to the local file system
        (e.g. drive or directory names) are ignored.  (XXX They should
        probably be diagnosed.)
        """

        print("first file path", path)
        # abandon query parameters
        path = path.split('?',1)[0]
        path = path.split('#',1)[0]
        path = posixpath.normpath(urllib.unquote(path))
        words = path.split('/')
        words = filter(None, words)
        path = ""
        i = 0
        for word in words:
            #if word in (os.curdir, os.pardir): continue
            if i==0:
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


class UpdateSharesEventHandler(FileSystemEventHandler):
    def on_modified(self, event):
        if "shares.txt" in event.src_path:
            print("detected change and updating the shares")
            update_shares()

update_shares()


logging.basicConfig(level=logging.INFO,
    format='%(asctime)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S')
update_shares_event_handler = UpdateSharesEventHandler()
path = os.path.join(os.getcwd(), "GhettoDropbox")
logging_event_handler = LoggingEventHandler()
observer = Observer()
observer.schedule(logging_event_handler, path, recursive=False)
observer.schedule(update_shares_event_handler, path, recursive=False)
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

print "serving at port", port
try:
    httpd.serve_forever()
except:
    print "Closing the server."
    httpd.server_close()
    observer.stop()
    raise

