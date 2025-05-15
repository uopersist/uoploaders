import json
import os
import asyncio
from uopmeta.schemas.prefined import pkm_schema
from sqluop import adaptor as sql_adaptor
from mongouop import adaptor as mongo_adaptor
from uopclient.connect import direct
from uopclient.uop_connect import register_adaptor
from functools import reduce

def brave_path():
    return os.path.join(os.getenv("HOME"), ".config/BraveSoftware/Brave-Browser/Default/Bookmarks")

class BMFolder:
    FolderType = 'folder'
    URLType = 'url'
    DateAdded = 'date_added'
    DateLastUsed = 'date_last_used'
    URLField = 'url'
    TitleField = 'name'

    def __init__(self, name, children, parent=None):
        self._name = name
        self.urls = []
        self.subfolders = {}
        self.url_path = [name] if name else []
        if parent:
            self.url_path = parent.url_path + self.url_path
        if children:
            self.process(children)

    def as_dict(self):
        return dict(
            name=self._name,
            urls=self.urls,
            subfolders={s._name: s.as_dict() for s in self.subfolders.values()}
        )

    def url_data(self, url_object):
        return dict(
            url=url_object[self.URLField],
            created_at=url_object[self.DateAdded],
            last_used=url_object[self.DateLastUsed],
            title=url_object.get(self.TitleField)
        )

    def process(self, children):
        for child in children:
            type = child.get('type')
            if type == self.FolderType:
                name = child.get(self.TitleField)
                self.subfolders[name] = self.__class__(name, child.get('children'), parent=self)
            elif type == self.URLType:
                self.urls.append(self.url_data(child))

class URLInfo:
    SkipPrefixes = [
        'imported from chrome',
        'imported from firefox',
        'bookmarks',
        'other bookmarks'
    ]
    def __init__(self, url_data, a_path = None):
        self.data = url_data
        self.paths = set()
        if a_path:
            self.add_path(a_path)

    def clean_path(self, a_path):
        rs = []
        for index, part in enumerate(a_path):
            if part.lower() not in self.SkipPrefixes:
                return a_path[index:]


    def add_path(self, a_path):
        a_path = self.clean_path(a_path)
        if a_path:
            path_t = tuple(a_path)
            if path_t not in self.paths:
                self.paths.add(path_t)

    def combine_paths(self, paths):
        self.paths |= paths

class BraveFolder(BMFolder):
    def __init__(self, name, children, parent=None):
        super().__init__(name, children, parent=parent)

class FirefoxFolder(BMFolder):
    FolderType = 'text/x-moz-place-container'
    URLType = 'text/x-moz-place'
    DateAdded = 'dateAdded'
    DateLastUsed = 'lastModified'
    URLField = 'uri'
    TitleField = 'title'

    def __init__(self, name, children, parent=None):
        super().__init__(name, children, parent=parent)


class BookmarkLoader:
    FolderClass = BMFolder

    def __init__(self, path):
        with open(path) as f:
            self._data = json.load(f)
        self._raw = self.extract_top_json()
        self._processed = self.extract_top_folder()
        self._urls = {}

    def urls(self):
        if not self._urls:
            self.compute_url_paths()
        return self._urls

    def extract_top_json(self):
        return self._data['roots']['bookmark_bar']

    def contents(self):
        return self._processed.as_dict()

    def compute_url_paths(self):
        """
        Compute and return dict of unique urls, their data and the
        folder paths to them
        :return:
        """
        def get_info(url_data):
            url = url_data['url']
            if url not in self._urls:
                self._urls[url] = URLInfo(url_data)
            return self._urls[url]

        def process_folder(folder: BMFolder):
            path = folder.url_path
            for url in folder.urls:
                info = get_info(url)
                info.add_path(path)
            for sub in folder.subfolders.values():
                process_folder(sub)

        process_folder(self._processed)

    def extract_top_folder(self):
        return self.FolderClass('', self.extract_top_json()['children'])

class BraveBookmarkLoader(BookmarkLoader):
    FolderClass = BraveFolder
    def __init__(self, path):
        super().__init__(path)

    def extract_top_json(self):
        return self._data['roots']['bookmark_bar']

class FirefoxBockmarkLoader(BookmarkLoader):
    FolderClass = FirefoxFolder
    def __init__(self, path):
        super().__init__(path)

    def extract_top_json(self):
        for child in self._data['children']:
            if child[self.FolderClass.TitleField] == 'menu':
                return child

def combined_urls(url_map, collected = None):
    collected = collected or {}
    for url,info in url_map.items():
        known = collected.get(url)
        if known:
            known.combine_paths(info.paths)
        else:
            collected[url] = info
    return collected

async def a_direct_connect(db_type, dbname, db_adapter=None, **db_args):

    if db_adapter:
        register_adaptor(db_type, db_adapter)
    return await direct.DirectConnection.get_connection('sqlite', dbname, schemas=[pkm_schema])


def gather_urls(**path_loaders):
    loaded_urls = []
    for path, loader in path_loaders.items():
        loaded = loader(path)
        loaded_urls.append(loaded)
    return reduce(lambda prev, next: combined_urls(next, prev), loaded_urls, {})

class DBURLUpdater:
    def __init__(self, **path_loaders):
        self._urls = gather_urls(**path_loaders)

    async def update(self):
        self._connect = await a_connect('sqlite', db_name='bookmarks.db')
