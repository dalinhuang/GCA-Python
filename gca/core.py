from __future__ import print_function

import json
import urllib2
import urllib
from cookielib import CookieJar
from urlparse import urlparse
import os
import sys


class TransportError(Exception):
    def __init__(self, code, message):
        self.message = message
        self.code = code

    def __str__(self):
        return "[%d] %s" % (self.code, self.message)


class BaseObject(object):
    def __init__(self, data):
        self._data = data

    @property
    def uuid(self):
        return self._data['uuid']

    @property
    def raw_data(self):
        return self._data


class Affiliation(BaseObject):
    def __init__(self, data):
        super(Affiliation, self).__init__(data)

    def format_affiliation(self):
        department = self._data['department']
        section = self._data['section']
        address = self._data['address']
        country = self._data['country']

        components = [department, section, address, country]
        active = filter(bool, components)
        return u', '.join(active)


class Author(BaseObject):
    def __init__(self, data):
        super(Author, self).__init__(data)

    @property
    def first_name(self):
        return self._data['firstName']

    @property
    def middle_name(self):
        return self._data['middleName']

    @property
    def last_name(self):
        return self._data['lastName']

    @property
    def affiliations(self):
        return self._data['affiliations']

    def format_name(self):
        d = self._data
        middle = d['middleName'] + u' ' if d['middleName'] else u""
        return d['firstName'] + u' ' + middle + d['lastName']

    def format_affiliation(self):
        af = self._data['affiliations']
        af_corrected = [str(x + 1) for x in sorted(af)]
        return ', '.join(af_corrected)


class Reference(BaseObject):
    def __init__(self, data):
        super(Reference, self).__init__(data)

    @property
    def text(self):
        return self._data['text']


class Figure(BaseObject):
    def __init__(self, data):
        super(Figure, self).__init__(data)

    @property
    def caption(self):
        return self._data['caption']


class Abstract(BaseObject):
    def __init__(self, data):
        super(Abstract, self).__init__(data)
        self.__data = data

    @property
    def title(self):
        return self.__data['title']

    @property
    def text(self):
        return self.__data['text']

    @text.setter
    def text(self, value):
        self.__data['text'] = value

    @property
    def state(self):
        return self.__data['state']

    @property
    def authors(self):
        return [Author(a) for a in self.__data['authors']]

    @property
    def affiliations(self):
        return [Affiliation(a) for a in self.__data['affiliations']]

    @property
    def acknowledgements(self):
        return self.__data['acknowledgements']

    @property
    def references(self):
        return [Reference(r) for r in self.__data['references']]

    @property
    def figures(self):
        return [Figure(f) for f in self.__data['figures']]

    @property
    def log(self):
        log_data = self.__data['stateLog']
        if type(log_data) != list:
            return None
        return [LogEntry(e) for e in log_data]

    @property
    def owners(self):
        owner_data = self.__data['owners']
        if type(owner_data) != list:
            return None
        return [Owner(o) for o in owner_data]

    @property
    def topic(self):
        return self.__data['topic']

    @property
    def is_talk(self):
        return self.__data['isTalk']

    @property
    def reason_for_talk(self):
        return self.__data['reasonForTalk']

    def select_field(self, field):
        def getattr_maybelist(obj, name):
            if obj is None:
                return None
            if type(obj) == list:
                return [x for o in obj for x in getattr_maybelist(o, name)]
            else:
                return [getattr(obj, name)]
        return reduce(getattr_maybelist, field, self)

    @classmethod
    def from_data(cls, data):
        js = json.loads(data)
        return [Abstract(a) for a in js]


class Owner(BaseObject):
    def __init__(self, data):
        super(Owner, self).__init__(data)

    @property
    def email(self):
        return self._data['mail']


class LogEntry(object):
    def __init__(self, data):
        self._data = data

    @property
    def timestamp_str(self):
        return self._data['timestamp']

    @property
    def timestamp(self):
        import isodate
        return isodate.parse_datetime(self._data['timestamp'])

    @property
    def state(self):
        return self._data['state']

    @property
    def editor(self):
        return self._data['editor']

    @property
    def note(self):
        return self._data['note']


def authenticated(method):
    def wrapper(self, *args, **kwargs):
        if not self.is_authenticated:
            self.authenticate()
        return method(self, *args, **kwargs)
    return wrapper


class Session(object):
    def __init__(self, url, authenticator):
        jar = CookieJar()
        opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(jar))

        self.__url = url
        self.__cookie_jar = jar
        self.__url_opener = opener
        self.__auth = authenticator
        self.__is_authenticated = False
        self._guess_mime_ext = None

    @property
    def url(self):
        return self.__url

    @property
    def is_authenticated(self):
        return self.__is_authenticated

    def authenticate(self):
        purl = urlparse(self.url)
        hostname = purl.hostname
        user, password = self.__auth.get_credentials(hostname)
        params = urllib.urlencode({'username': user, 'password': password})
        url_opener = self.__url_opener
        resp = url_opener.open(self.url + "/authenticate/userpass", params)
        code = resp.getcode()
        if code != 200:
            raise TransportError(code, "Could not log in")
        self.__is_authenticated = True
        return code

    @authenticated
    def get_all_abstracts(self, conference, raw=False, full=False):
        url = "%s/api/conferences/%s/allAbstracts" % (self.url, conference)
        data = self._fetch(url)

        if full:
            data = [self._complete_abstract(a) for a in data]

        all_abstracts = [Abstract(abstract) for abstract in data] if not raw else data
        return all_abstracts

    def get_conference(self, conference):
        url = "%s/api/conferences/%s" % (self.url, conference)
        data = self._fetch(url)
        return data

    def get_figure_image(self, uuid, add_ext=True, path=None):
        url = "%s/api/figures/%s/image" % (self.url, uuid)
        data = self._fetch_binary(url)
        if path is not None and not os.path.exists(path):
            os.mkdir(path)

        fn = os.path.join(path, uuid) if path is not None else uuid
        with open(fn, 'w+') as fd:
            fd.write(data)
        if add_ext:
            ext = self._guess_filetype(fn)
            if ext is None:
                sys.stderr.write('[W] Could not determine image type for %s\n' % uuid)
                return fn
            new_fn = fn + '.' + ext
            os.rename(fn, new_fn)
            fn = new_fn
        return fn

    @authenticated
    def get_owners(self, uuid_or_url, otype='abstracts', raw=False):
        url = self._build_url(uuid_or_url, 'owners', otype=otype)
        data = self._fetch(url)
        return data if raw else [Owner(o) for o in data]

    @authenticated
    def get_state_log(self, uuid_or_url, raw=False):
        url = self._build_url(uuid_or_url, 'stateLog', otype='abstracts')
        data = self._fetch(url)
        return data if raw else [LogEntry(e) for e in data]

    def _build_url(self, uuid_or_url, target, otype='abstracts'):
        if uuid_or_url.startswith('http:'):
            url = uuid_or_url
        else:
            url = "%s/api/%s/%s/%s" % (self.url, otype, uuid_or_url, target)
        return url

    def _complete_abstract(self, abstract):
        owners = self.get_owners(abstract['owners'], raw=True)
        abstract.update({'owners': owners})
        log = self.get_state_log(abstract['stateLog'], raw=True)
        abstract.update({'stateLog': log})
        return abstract

    def _fetch_binary(self, url):
        url_opener = self.__url_opener
        resp = url_opener.open(url)
        if resp.getcode() != 200:
            raise TransportError(resp.getcode(), "Could not fetch data")
        data = resp.read()
        return data

    def _fetch(self, url):
        url_opener = self.__url_opener
        resp = url_opener.open(url)
        if resp.getcode() != 200:
            raise TransportError(resp.getcode(), "Could not fetch data")
        data = resp.read()
        text = data.decode('utf-8')
        return json.loads(text)

    def _guess_filetype(self, path):
        import imghdr
        ext = imghdr.what(path)
        if ext is None:
            import subprocess
            if self._guess_mime_ext is None:
                import mimetypes
                mimetypes.init()
                self._guess_mime_ext = mimetypes.guess_extension
            x = subprocess.check_output(['file', '-b', '--mime-type', path]).strip()
            ext = self._guess_mime_ext(x)
        return ext